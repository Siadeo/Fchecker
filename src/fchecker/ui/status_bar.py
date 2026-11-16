from __future__ import annotations

from PySide6.QtWidgets import QLabel, QStatusBar, QWidget

from fchecker.core.document import InvoiceDocument, profile_label


class StatusBar(QStatusBar):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizeGripEnabled(False)
        self.doc_label = QLabel("Aucun document")
        self.time_label = QLabel("")
        self.directory_label = QLabel("Annuaire Peppol : non vérifié")
        self.addWidget(self.doc_label, 1)
        self.addPermanentWidget(self.time_label)
        self.addPermanentWidget(self.directory_label)

    def show_document(self, doc: InvoiceDocument | None) -> None:
        if doc is None:
            self.doc_label.setText("Aucun document")
            self.time_label.setText("")
            return
        parts = [doc.format.value]
        if doc.profile:
            parts.append(profile_label(doc.profile))  # libellé court (ex. EN 16931)
        if doc.pdf_info and doc.pdf_info.pdfa_label:
            parts.append(doc.pdf_info.pdfa_label)
        self.doc_label.setText(" · ".join(parts))

    def show_duration(self, seconds: float | None, what: str = "validé") -> None:
        self.time_label.setText("" if seconds is None else f"{what} en {seconds:.2f} s".replace(".", ","))

    def show_directory(self, findings) -> None:
        """État de l'annuaire Peppol déduit des constats PEP-* de la dernière validation."""
        dirs = [f for f in findings if f.rule_id.startswith("PEP-")]
        if not dirs:
            state = "non vérifié"
        elif any(f.rule_id == "PEP-06" and "désactivée" in f.message for f in dirs):
            state = "désactivé"
        elif any(f.rule_id == "PEP-06" for f in dirs):
            state = "hors ligne"
        elif all("(cache)" in f.message for f in dirs if f.rule_id != "PEP-00"):
            state = "cache"
        else:
            state = "en ligne"
        self.directory_label.setText(f"Annuaire Peppol : {state}")
