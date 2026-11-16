"""Cohérence entre le PDF visuel et le XML : numéro, dates, totaux, SIREN (égalité exacte)."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fchecker.core.findings import Finding, Severity, Source
from fchecker.core.invoice import invoice_of
from fchecker.core.plugin import Tool
from fchecker.core.report import Report

from . import matchers
from .pdf_text import extract_text

MIN_TEXT = 40  # en deçà : PDF image (scan) sans texte exploitable


@dataclass(frozen=True)
class FieldSpec:
    rule: str
    bt: str
    label: str
    kind: str                # id | date | amount | siren
    absent: Severity
    divergent: Severity


FIELDS = (
    FieldSpec("COH-01", "BT-1", "N° de facture", "id", Severity.ERROR, Severity.ERROR),
    FieldSpec("COH-02", "BT-2", "Date de facture", "date", Severity.ERROR, Severity.ERROR),
    FieldSpec("COH-03", "BT-9", "Date d'échéance", "date", Severity.WARNING, Severity.ERROR),
    FieldSpec("COH-04", "BT-109", "Total HT", "amount", Severity.ERROR, Severity.ERROR),
    FieldSpec("COH-05", "BT-110", "Total TVA", "amount", Severity.ERROR, Severity.ERROR),
    FieldSpec("COH-06", "BT-112", "Total TTC", "amount", Severity.ERROR, Severity.ERROR),
    FieldSpec("COH-07", "BT-115", "Net à payer", "amount", Severity.WARNING, Severity.ERROR),
    FieldSpec("COH-08", "BT-30", "SIREN du vendeur", "siren", Severity.ERROR, Severity.ERROR),
    FieldSpec("COH-09", "BT-47", "SIREN du client", "siren", Severity.WARNING, Severity.WARNING),
)


def fmt(value) -> str:
    if isinstance(value, Decimal):
        q = f"{value:,.2f}".replace(",", " ").replace(".", ",")
        return q
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return str(value)


def xml_values(inv) -> dict[str, object]:
    t = inv.totals
    values = {
        "BT-1": inv.number.text if inv.number else None,
        "BT-2": inv.issue_date,
        "BT-9": inv.due_date,
        "BT-109": t.without_vat,
        "BT-110": t.vat,
        "BT-112": t.with_vat,
        "BT-115": t.due if t.due is not None and t.due != t.with_vat else None,  # redondant si = TTC
        "BT-30": inv.seller.siren,
        "BT-47": inv.buyer.siren,
    }
    return values


class ConsistencyTool(Tool):
    def accepts(self, doc):
        return doc.is_pdf

    def run(self, doc, ctx) -> Report:
        start = time.perf_counter()
        report = Report(tool_id=self.spec.id)
        rows: list[dict] = []
        text = extract_text(doc.pdf_bytes or b"")
        if len(text.strip()) < MIN_TEXT:
            self.publish(Finding("COH-10", Severity.WARNING, Source.CONSISTENCY,
                                 "Le PDF ne contient pas de texte exploitable (document scanné ?) : comparaison "
                                 "PDF ↔ XML impossible sans OCR."), report, ctx)
            report.meta["fields"] = rows
            return report

        inv = invoice_of(doc)
        values = xml_values(inv)
        dates = matchers.dates(text)
        amounts = matchers.amounts(text)
        for spec in FIELDS:
            ctx.check_cancelled()
            xml = values.get(spec.bt)
            if xml is None:
                rows.append({"rule": spec.rule, "bt": spec.bt, "label": spec.label, "xml": "—", "pdf": "",
                             "status": "sans objet"})
                continue
            status, pdf_value = self._compare(spec, xml, text, dates, amounts)
            rows.append({"rule": spec.rule, "bt": spec.bt, "label": spec.label, "xml": fmt(xml),
                         "pdf": pdf_value or "", "status": status})
            line = inv.lines_of.get(spec.bt)
            if status == "absent":
                self.publish(Finding(spec.rule, spec.absent, Source.CONSISTENCY,
                                     f"{spec.label} du XML ({fmt(xml)}) introuvable dans le PDF.",
                                     bt=spec.bt, line=line), report, ctx)
            elif status == "divergent":
                self.publish(Finding(spec.rule, spec.divergent, Source.CONSISTENCY,
                                     f"{spec.label} divergent : PDF « {pdf_value} », XML « {fmt(xml)} ».",
                                     bt=spec.bt, line=line, pdf_hint=pdf_value), report, ctx)
        report.meta["fields"] = rows
        report.duration = time.perf_counter() - start
        return report

    @staticmethod
    def _compare(spec: FieldSpec, xml, text, dates, amounts) -> tuple[str, str | None]:
        if spec.kind == "id":
            return ("trouvé", xml) if matchers.has_identifier(text, xml) else ("absent", None)
        if spec.kind == "siren":
            hit = matchers.find_siren(text, xml)
            return ("trouvé", hit) if hit else ("absent", None)
        tokens = dates if spec.kind == "date" else amounts
        for t in tokens:
            if t.value == xml:
                return "trouvé", t.text
        labelled = matchers.labelled_values(text, spec.bt, spec.kind)
        if labelled:
            return "divergent", labelled[0].text
        return "absent", None

    def create_view(self, parent, doc):
        from .view import ConsistencyView

        return ConsistencyView(self.spec, parent)
