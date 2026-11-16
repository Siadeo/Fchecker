from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QStackedWidget, QTabWidget, QWidget

from fchecker.core.document import InvoiceDocument
from fchecker.core.findings import Finding
from fchecker.core.registry import Registry
from fchecker.core.report import Report
from fchecker.ui.models.findings_model import FindingsTableModel
from fchecker.ui.widgets.xml_view import XmlView

log = logging.getLogger(__name__)


class DocumentTab(QSplitter):
    """Un document ouvert : vues d'outil (créées au premier affichage) + volet contextuel."""

    def __init__(self, doc: InvoiceDocument, registry: Registry, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.doc = doc
        self.registry = registry
        self.findings = FindingsTableModel(self)
        self.reports: dict[str, Report] = {}
        self.current_tool: str | None = None
        self._views: dict[str, QWidget] = {}

        self.stack = QStackedWidget(objectName="toolStack")
        self.addWidget(self.stack)

        self.context = QTabWidget()
        self.context.setDocumentMode(True)
        self._pdf_view = None
        self._search = None
        self._xml_view: XmlView | None = None
        if doc.is_pdf:
            self.context.addTab(QWidget(), "PDF")  # remplacé au premier affichage
        self.context.addTab(QWidget(), "XML")
        self.context.currentChanged.connect(self._ensure_context_tab)
        self.addWidget(self.context)
        self.setStretchFactor(0, 1)
        self.setStretchFactor(1, 1)
        self.setChildrenCollapsible(False)
        self._sized = False

    # --- Vues d'outil ----------------------------------------------------------
    def show_tool(self, tool_id: str) -> None:
        view = self._views.get(tool_id)
        if view is None:
            view = self._create_view(tool_id)
            self._views[tool_id] = view
            self.stack.addWidget(view)
            if tool_id in self.reports and hasattr(view, "show_report"):
                view.show_report(self.reports[tool_id])
        self.stack.setCurrentWidget(view)
        self.current_tool = tool_id

    def _create_view(self, tool_id: str) -> QWidget:
        try:
            view = self.registry.get_tool(tool_id).create_view(self.stack, self.doc)
            if (signal := getattr(view, "xml_line_requested", None)) is not None:  # ex. visionneuse
                signal.connect(self.reveal_xml_line)
            return view
        except Exception as exc:
            log.exception("Vue de l'outil %s indisponible", tool_id)
            from fchecker.ui.widgets.placeholder import PlaceholderView

            return PlaceholderView("Outil indisponible", f"{tool_id} : {exc}", self.stack)

    def set_report(self, report: Report) -> None:
        self.reports[report.tool_id] = report
        for tool_id, view in self._views.items():
            if hasattr(view, "show_report") and tool_id in (report.tool_id, "dashboard"):
                view.show_report(report)

    # --- Volet contextuel ------------------------------------------------------
    def set_context_visible(self, visible: bool) -> None:
        self.context.setVisible(visible)
        if visible:
            self._ensure_context_tab(self.context.currentIndex())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._sized and self.width() > 0:  # répartition initiale 55 % outil / 45 % document
            self._sized = True
            self.setSizes([int(self.width() * 0.55), int(self.width() * 0.45)])
        self._ensure_context_tab(self.context.currentIndex())

    def _ensure_context_tab(self, index: int) -> None:
        if index < 0 or not self.context.isVisible():
            return
        label = self.context.tabText(index)
        if label == "PDF" and self._pdf_view is None:
            self._pdf_view = self._build_pdf_view()
            self._replace_tab(index, self._pdf_view, label)
        elif label == "XML" and self._xml_view is None:
            self._xml_view = XmlView(self.doc.xml_bytes.decode("utf-8", errors="replace"))
            self._replace_tab(index, self._xml_view, label)

    def refresh_theme(self) -> None:
        if self._xml_view is not None:
            self._xml_view.refresh_theme()

    def _replace_tab(self, index: int, widget: QWidget, label: str) -> None:
        self.context.blockSignals(True)
        old = self.context.widget(index)
        self.context.removeTab(index)
        self.context.insertTab(index, widget, label)
        self.context.setCurrentIndex(index)
        self.context.blockSignals(False)
        old.deleteLater()

    def _build_pdf_view(self) -> QWidget:
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtPdfWidgets import QPdfView

        # Le document appartient à l'onglet, pas à la vue : enfant de QPdfView, il serait détruit
        # après elle et émettrait ses signaux vers une vue à moitié détruite (crash natif).
        pdf = QPdfDocument(self)
        view = QPdfView(self.context)
        pdf.load(str(self.doc.path))
        view.setDocument(pdf)
        view.setPageMode(QPdfView.PageMode.MultiPage)
        view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        return view

    def dispose(self) -> None:
        """À appeler avant ``deleteLater()`` : détache le PDF de sa vue avant toute destruction.

        L'ordre de destruction des enfants Qt ne garantit pas que QPdfDocument / QPdfSearchModel
        disparaissent avant QPdfView ; leurs signaux tardifs vers la vue provoquent un crash natif.
        """
        view = self._pdf_view
        if view is None:
            return
        pdf = view.document()
        view.setSearchModel(None)
        view.setDocument(None)
        if self._search is not None:
            self._search.setDocument(None)
        if pdf is not None:
            pdf.close()

    def reveal(self, finding: Finding) -> None:
        """Navigation depuis le panneau Problèmes : valeur surlignée dans le PDF, sinon ligne XML."""
        if finding.pdf_hint and self.doc.is_pdf:
            self._show_context_tab("PDF")
            self._highlight_pdf(finding.pdf_hint)
        elif finding.line is not None:
            self.reveal_xml_line(finding.line)

    def reveal_xml_line(self, line: int) -> None:
        """Affiche l'onglet XML et surligne ``line`` (fichier d'origine), dépliage compris."""
        self._show_context_tab("XML")
        if self._xml_view is not None:
            self._xml_view.goto_line(line)

    def _show_context_tab(self, label: str) -> None:
        self.set_context_visible(True)
        for i in range(self.context.count()):
            if self.context.tabText(i) == label:
                self.context.setCurrentIndex(i)
                self._ensure_context_tab(i)

    def _highlight_pdf(self, text: str) -> None:
        from PySide6.QtCore import QTimer
        from PySide6.QtPdf import QPdfSearchModel

        view = self._pdf_view
        if view is None:
            return
        if self._search is None:
            self._search = QPdfSearchModel(self)
            self._search.setDocument(view.document())
            view.setSearchModel(self._search)
        self._search.setSearchString(text)
        # La recherche est asynchrone : on sélectionne le 1er résultat dès qu'il est disponible.
        # Timer rattaché à l'onglet : annulé s'il est fermé entre-temps (sinon modèle déjà détruit).
        QTimer.singleShot(150, self, lambda: view.setCurrentSearchResultIndex(0) if self.pdf_match_count() else None)

    def pdf_match_count(self) -> int:
        from PySide6.QtCore import QModelIndex

        return self._search.rowCount(QModelIndex()) if self._search is not None else 0
