"""Rapport de contrôle : contexte commun, rendu HTML (Jinja2) et JSON. Sans Qt."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import Enum
from functools import cache

from jinja2 import Environment, PackageLoader, select_autoescape

from fchecker import __version__

from .document import InvoiceDocument, profile_label
from .findings import Severity
from .invoice import invoice_of
from .labels import day, money
from .report import Report

TOOL_LABELS = {"validator": "Validateur", "mentions": "Mentions obligatoires", "consistency": "Cohérence PDF ↔ XML"}


def build_context(doc: InvoiceDocument, reports: dict[str, Report]) -> dict:
    raw = doc.pdf_bytes or doc.xml_bytes
    inv = invoice_of(doc)
    findings = sorted((f for r in reports.values() for f in r.findings), key=lambda f: (f.severity, f.rule_id))
    counts = {s: 0 for s in Severity}
    for f in findings:
        counts[f.severity] += 1
    packs: dict[str, str] = {}
    for r in reports.values():
        packs.update(r.rule_packs)
    blocking = counts[Severity.FATAL] + counts[Severity.ERROR]
    return {
        "tool_version": __version__,
        "generated_at": datetime.now(),
        "document": {
            "name": doc.display_name, "path": str(doc.path), "sha256": hashlib.sha256(raw).hexdigest(),
            "format": doc.format.value, "profile": doc.profile or "",
            "profile_label": profile_label(doc.profile) if doc.profile else "",
            "pdfa": doc.pdf_info.pdfa_label if doc.pdf_info else None,
        },
        "invoice": {
            "number": str(inv.number) if inv.number else "", "issue_date": day(inv.issue_date),
            "seller": inv.seller.name.text if inv.seller.name else "",
            "buyer": inv.buyer.name.text if inv.buyer.name else "",
            "total_with_vat": money(inv.totals.with_vat, inv.currency),
        },
        "verdict": "Non conforme" if blocking else ("Conforme avec avertissements" if counts[Severity.WARNING]
                                                    else "Conforme"),
        "counts": counts,
        "rule_packs": packs,
        "findings": findings,
        "checks": reports["validator"].meta.get("checks", []) if "validator" in reports else [],
        "mentions": reports["mentions"].meta.get("mentions", []) if "mentions" in reports else [],
        "consistency": reports["consistency"].meta.get("fields", []) if "consistency" in reports else [],
        "tools": [TOOL_LABELS.get(k, k) for k in reports],
    }


@cache
def _env() -> Environment:
    return Environment(loader=PackageLoader("fchecker.core", "templates"), autoescape=select_autoescape(["j2"]),
                       trim_blocks=True, lstrip_blocks=True)


def render_html(doc: InvoiceDocument, reports: dict[str, Report]) -> str:
    return _env().get_template("report.html.j2").render(r=build_context(doc, reports), Severity=Severity)


def _json_default(value):
    if isinstance(value, Enum):
        return value.value if not isinstance(value, Severity) else value.name
    if isinstance(value, (datetime,)):
        return value.isoformat(timespec="seconds")
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value))


def render_json(doc: InvoiceDocument, reports: dict[str, Report]) -> str:
    ctx = build_context(doc, reports)
    ctx["counts"] = {s.name: n for s, n in ctx["counts"].items()}
    ctx["findings"] = [{
        "rule_id": f.rule_id, "severity": f.severity.name, "source": f.source.value, "title": f.display_message,
        "message": f.message, "explanation": f.explanation, "bt": f.bt, "line": f.line, "suggestion": f.suggestion,
    } for f in ctx["findings"]]
    # Copies : ne jamais modifier les métadonnées des rapports (réutilisées par l'interface).
    ctx["checks"] = [{**c, "counts": {s.name: n for s, n in c["counts"].items()}} for c in ctx["checks"]]
    return json.dumps(ctx, default=_json_default, ensure_ascii=False, indent=2)
