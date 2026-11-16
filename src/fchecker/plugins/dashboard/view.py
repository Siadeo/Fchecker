from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from fchecker.core.document import InvoiceDocument, profile_label
from fchecker.core.findings import Severity
from fchecker.core.report import Report
from fchecker.ui import theme

_TOOLS = (("validator", "Validateur"), ("mentions", "Mentions obligatoires"), ("consistency", "Cohérence PDF ↔ XML"))


def _fmt_size(n: int) -> str:
    return f"{n / 1024:.1f} Ko" if n < 1024 * 1024 else f"{n / 1024 / 1024:.2f} Mo"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n > 1 else ''}"


class DashboardView(QWidget):
    def __init__(self, doc: InvoiceDocument, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.doc = doc
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel(doc.display_name, objectName="h1")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(title)

        self.verdict = QLabel("Contrôles non exécutés — F5 pour tout valider.", objectName="muted")
        layout.addWidget(self.verdict)

        synth = QFrame(objectName="card")
        self.grid = QGridLayout(synth)
        self.grid.setHorizontalSpacing(12)
        self._rows: dict[str, tuple[QLabel, QLabel]] = {}
        for i, (tool_id, label) in enumerate(_TOOLS):
            if tool_id == "consistency" and not doc.is_pdf:
                continue
            light = QLabel("●")
            light.setStyleSheet(f"color: {theme.palette().border}; font-size: 14pt;")
            text = QLabel("non exécuté", objectName="muted")
            self.grid.addWidget(light, i, 0)
            self.grid.addWidget(QLabel(label), i, 1)
            self.grid.addWidget(text, i, 2)
            self._rows[tool_id] = (light, text)
        self.grid.setColumnStretch(2, 1)
        layout.addWidget(synth)

        card = QFrame(objectName="card")
        form = QFormLayout(card)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(16)
        rows = [
            ("Format", doc.format.value),
            ("Syntaxe XML", doc.format.syntax),
            ("Profil", f"{profile_label(doc.profile)}  ({doc.profile})" if doc.profile else "—"),
            ("Taille XML", _fmt_size(len(doc.xml_bytes))),
        ]
        if (info := doc.pdf_info) is not None:
            rows += [
                ("PDF", f"version {info.pdf_version}, {info.page_count} page(s), {_fmt_size(len(doc.pdf_bytes or b''))}"),
                ("PDF/A (déclaré)", info.pdfa_label or "non déclaré"),
                ("Pièce jointe", f"{info.attachment_name} ({info.af_relationship or 'AFRelationship absent'})"),
                ("Niveau Factur-X XMP (PDF)", info.fx_conformance_level or "—"),
            ]
        for label, value in rows:
            v = QLabel(value)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(QLabel(label, objectName="muted"), v)
        layout.addWidget(card)
        layout.addStretch(1)
        self._reports: dict[str, Report] = {}

    def show_report(self, report: Report) -> None:
        self._reports[report.tool_id] = report
        p = theme.palette()
        if report.tool_id in self._rows:
            c = report.counts()
            errors = c[Severity.FATAL] + c[Severity.ERROR]
            color = p.error if errors else (p.warning if c[Severity.WARNING] else p.ok)
            parts = [_plural(errors, "erreur"), _plural(c[Severity.WARNING], "avertissement")]
            light, text = self._rows[report.tool_id]
            light.setStyleSheet(f"color: {color}; font-size: 14pt;")
            text.setText(" · ".join(parts))
        total = {s: 0 for s in Severity}
        for r in self._reports.values():
            for s, n in r.counts().items():
                total[s] += n
        blocking = total[Severity.FATAL] + total[Severity.ERROR]
        if blocking:
            self.verdict.setText(f"Facture non conforme : {_plural(blocking, 'erreur')} à corriger.")
            color = p.error
        elif total[Severity.WARNING]:
            self.verdict.setText(f"Conforme, avec {_plural(total[Severity.WARNING], 'avertissement')} à examiner.")
            color = p.warning
        else:
            self.verdict.setText("Aucune erreur détectée.")
            color = p.ok
        self.verdict.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 11pt;")
