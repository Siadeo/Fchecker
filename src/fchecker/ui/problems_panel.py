from __future__ import annotations

from html import escape

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSplitter,
    QTableView,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from fchecker.core.findings import Finding, Severity
from fchecker.ui import theme
from fchecker.ui.models.findings_model import FindingRole, FindingsFilterProxy, FindingsTableModel

# Icônes de ui/theme/icons (couleurs figées dans le SVG) ; créées à l'instanciation, après la QApplication.
_FILTER_LABELS = {Severity.FATAL: "fatal", Severity.ERROR: "error", Severity.WARNING: "warning", Severity.INFO: "info"}


class ProblemsPanel(QDockWidget):
    """Liste commune des constats du document actif (vue ; le modèle est fourni par l'onglet)."""

    finding_selected = Signal(object)
    finding_activated = Signal(object)  # double-clic → navigation (XML, visionneuse, PDF)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("CONTRÔLES", parent)
        self.setObjectName("problemsDock")
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)

        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget(objectName="problemsHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 4, 8, 4)
        self._filters: dict[Severity, QToolButton] = {}
        for sev in Severity:
            b = QToolButton(objectName="severityFilter", checkable=True, checked=True)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setIcon(theme.icon(_FILTER_LABELS[sev], size=16))
            b.setIconSize(QSize(16, 16))
            b.setToolTip(f"Afficher / masquer : {sev.label}")
            b.toggled.connect(self._apply_filters)
            self._filters[sev] = b
            hl.addWidget(b)
        hl.addSpacing(8)
        self._search = QLineEdit(placeholderText="Filtrer (règle, BT, texte…)", clearButtonEnabled=True)
        self._search.setFixedWidth(260)
        hl.addWidget(self._search)
        hl.addStretch(1)
        root.addWidget(header)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableView()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.doubleClicked.connect(lambda idx: self.finding_activated.emit(idx.data(FindingRole)))
        split.addWidget(self.table)

        self.detail = QTextBrowser(objectName="findingDetail", openExternalLinks=True)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        root.addWidget(split, 1)
        self.setWidget(body)

        self.proxy = FindingsFilterProxy(self)
        self._search.textChanged.connect(self.proxy.set_text)
        self._empty = FindingsTableModel(self)  # source quand aucun document n'est ouvert
        self._model: FindingsTableModel | None = None
        self.proxy.setSourceModel(self._empty)
        self.table.setModel(self.proxy)  # le proxy reste le même : sélection connectée une seule fois
        self.table.selectionModel().currentRowChanged.connect(self._on_current)
        self.set_model(None)

    # ------------------------------------------------------------------------
    def set_model(self, model: FindingsTableModel | None) -> None:
        if self._model is not None:
            for sig in (self._model.modelReset, self._model.rowsInserted):
                sig.disconnect(self._refresh_counts)
        self._model = model
        self.proxy.setSourceModel(model if model is not None else self._empty)
        if model is not None:
            model.modelReset.connect(self._refresh_counts)
            model.rowsInserted.connect(self._refresh_counts)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for col, width in ((0, 34), (1, 110), (2, 70), (3, 56)):
            self.table.setColumnWidth(col, width)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self._refresh_counts()
        self.show_detail(None)

    def _refresh_counts(self, *_) -> None:
        counts = self._model.counts() if self._model else {s: 0 for s in Severity}
        for sev, b in self._filters.items():
            b.setText(str(counts[sev]))

    def _apply_filters(self) -> None:
        self.proxy.set_severities({s for s, b in self._filters.items() if b.isChecked()})

    def _on_current(self, current, _previous) -> None:
        f = current.data(FindingRole) if current.isValid() else None
        self.show_detail(f)
        if f is not None:
            self.finding_selected.emit(f)

    def show_detail(self, f: Finding | None) -> None:
        """Fiche du constat, traduite par le catalogue de règles."""
        self.detail.setHtml(finding_html(f))


def finding_html(f: Finding | None) -> str:
    if f is None:
        return "<p style='opacity:.7'>Sélectionnez un constat pour afficher son explication.</p>"
    muted = "opacity:.7"
    parts = [f"<p style='font-size:11pt'><b>{escape(f.display_message)}</b></p>"]
    if f.details:
        parts.append(f"<p>{escape(f.details)}</p>")
    if not f.translated:
        parts.append(f"<p style='{muted}'><i>Traduction manquante pour cette règle.</i></p>")
    if f.explanation:
        paras = "".join(f"<p>{escape(p)}</p>" for p in f.explanation.split("\n\n"))
        parts.append(paras)
    if f.suggestion:
        parts.append(f"<p><b>Correction :</b> {escape(f.suggestion)}</p>")
    if f.example:
        parts.append(f"<p style='{muted}'>Exemple :</p><pre style='margin-left:8px'>{escape(f.example)}</pre>")
    rows = [("Règle", f.rule_id), ("Gravité", f.severity.label), ("Source", f.source.value),
            ("Champ", f.bt), ("Ligne XML", f.line)]
    if f.message != f.display_message:
        rows.append(("Message d'origine", f.message))
    body = "".join(
        f"<tr><td style='padding-right:12px;{muted};vertical-align:top'>{escape(k)}</td><td>{escape(str(v))}</td></tr>"
        for k, v in rows if v not in (None, "")
    )
    parts.append(f"<table style='margin-top:6px'>{body}</table>")
    if f.listing:
        if f.listing_title:
            parts.append(f"<p style='margin-top:10px'><b>{escape(f.listing_title)}</b></p>")
        parts.append("<ul>" + "".join(f"<li>{escape(item)}</li>" for item in f.listing) + "</ul>")
    return "".join(parts)
