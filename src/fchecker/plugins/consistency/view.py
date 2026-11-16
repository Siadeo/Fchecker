from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from fchecker.core.report import Report
from fchecker.ui import theme

_ICON = {"trouvé": "✓", "absent": "✗", "divergent": "≠", "sans objet": "–"}


class ConsistencyView(QWidget):
    def __init__(self, spec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(QLabel(spec.name, objectName="h1"))
        self.summary = QLabel("Comparaison non effectuée — F5 pour lancer les contrôles.", objectName="muted")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["", "Champ", "XML", "PDF", "État"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setMinimumWidth(460)
        h = self.tree.header()
        for col, mode in enumerate((QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch,
                                    QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.ResizeToContents,
                                    QHeaderView.ResizeMode.ResizeToContents)):
            h.setSectionResizeMode(col, mode)
        layout.addWidget(self.tree, 1)
        note = QLabel("Égalité exacte des montants et des dates ; formats d'affichage usuels acceptés "
                      "(1 234,56 · 1234.56 · 24/09/26 · 24 septembre 2026…).", objectName="muted")
        note.setWordWrap(True)
        layout.addWidget(note)

    def show_report(self, report: Report) -> None:
        p = theme.palette()
        colors = {"trouvé": p.ok, "absent": p.error, "divergent": p.error, "sans objet": p.text_muted}
        self.tree.clear()
        rows = report.meta.get("fields", [])
        for r in rows:
            item = QTreeWidgetItem([_ICON[r["status"]], f"{r['label']} ({r['bt']})", r["xml"], r["pdf"], r["status"]])
            item.setForeground(0, QColor(colors[r["status"]]))
            item.setForeground(4, QColor(colors[r["status"]]))
            item.setTextAlignment(0, Qt.AlignmentFlag.AlignCenter)
            self.tree.addTopLevelItem(item)
        checked = [r for r in rows if r["status"] != "sans objet"]
        ok = sum(r["status"] == "trouvé" for r in checked)
        if not rows:
            self.summary.setText("Comparaison impossible : PDF sans texte exploitable.")
        else:
            self.summary.setText(f"{ok} / {len(checked)} champ(s) concordant(s) entre le PDF et le XML.")
