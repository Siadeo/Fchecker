from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QMarginsF, QUrl, Signal
from PySide6.QtGui import QPageLayout, QPageSize
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from fchecker.core.document import InvoiceDocument

from .render import render_invoice

log = logging.getLogger(__name__)

LINE_MESSAGE = "fchecker:xml-line:"  # préfixe émis par le script du gabarit (rendu interactif)


def _viewer_page(parent: QWidget, on_line):
    """Page WebEngine qui transmet les clics sur une valeur (messages console du gabarit) à ``on_line``.

    Messages console plutôt que QWebChannel (qwebchannel.js inaccessible depuis ``about:blank``) ou
    schéma d'URL personnalisé (à enregistrer avant la création de ``QApplication``).
    """
    from PySide6.QtWebEngineCore import QWebEnginePage

    class ViewerPage(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, line_number, source_id) -> None:
            if message.startswith(LINE_MESSAGE):
                try:
                    on_line(int(message[len(LINE_MESSAGE):]))
                except ValueError:
                    pass
                return
            super().javaScriptConsoleMessage(level, message, line_number, source_id)

    return ViewerPage(parent)


class ViewerView(QWidget):
    """Rendu HTML de la facture (QtWebEngine, chargé à la première ouverture).

    Un clic sur une valeur émet ``xml_line_requested`` avec sa ligne dans le XML d'origine.
    """

    xml_line_requested = Signal(int)

    def __init__(self, doc: InvoiceDocument, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.html = render_invoice(doc)  # export : sans script
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bar = QWidget(objectName="problemsHeader")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 6, 12, 6)
        bl.addWidget(QLabel("Visionneuse — survolez une valeur pour voir son BT, cliquez pour la situer dans le XML",
                            objectName="muted"))
        bl.addStretch(1)
        self.btn_pdf = QPushButton("Exporter en PDF…")
        self.btn_html = QPushButton("Exporter en HTML…")
        self.btn_pdf.clicked.connect(self.export_pdf)
        self.btn_html.clicked.connect(self.export_html)
        bl.addWidget(self.btn_html)
        bl.addWidget(self.btn_pdf)
        layout.addWidget(bar)

        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView

            self.web = QWebEngineView(self)
            self.web.setPage(_viewer_page(self.web, self.xml_line_requested.emit))
            self.web.setHtml(render_invoice(doc, interactive=True), QUrl("about:blank"))
        except Exception:  # WebEngine absent/indisponible : rendu simplifié
            log.exception("QtWebEngine indisponible, rendu simplifié")
            from PySide6.QtWidgets import QTextBrowser

            self.web = QTextBrowser(self)
            self.web.setHtml(self.html)
            self.btn_pdf.setEnabled(False)
        layout.addWidget(self.web, 1)

    def _default_name(self, ext: str) -> str:
        return str(Path(self.doc.path).with_name(f"{Path(self.doc.path).stem}_lisible.{ext}"))

    def export_html(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en HTML", self._default_name("html"), "HTML (*.html)")
        if path:
            Path(path).write_text(self.html, encoding="utf-8")

    def export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en PDF", self._default_name("pdf"), "PDF (*.pdf)")
        if not path:
            return
        page = self.web.page()
        page.pdfPrintingFinished.connect(self._pdf_done)
        layout = QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0))
        page.printToPdf(path, layout)

    def _pdf_done(self, path: str, ok: bool) -> None:
        self.web.page().pdfPrintingFinished.disconnect(self._pdf_done)
        if not ok:
            QMessageBox.warning(self, "Export PDF", f"L'export a échoué : {path}")
