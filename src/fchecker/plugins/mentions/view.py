from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from fchecker.core.report import Report
from fchecker.ui import theme

from .predicates import Status

_ICON = {Status.OK: "✓", Status.MISSING: "✗", Status.CHECK: "⚠", Status.NA: "–", Status.INFO: "ℹ"}


class MentionsView(QWidget):
    def __init__(self, spec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(QLabel(spec.name, objectName="h1"))
        self.summary = QLabel("Mentions non vérifiées — F5 pour lancer les contrôles.", objectName="muted")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["", "Mention", "État", "Détail"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setWordWrap(True)
        self.tree.setMinimumWidth(460)
        h = self.tree.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tree.setColumnWidth(1, 250)
        layout.addWidget(self.tree, 1)

    def show_report(self, report: Report) -> None:
        p = theme.palette()
        colors = {Status.OK: p.ok, Status.MISSING: p.error, Status.CHECK: p.warning, Status.NA: p.text_muted,
                  Status.INFO: p.info}
        self.tree.clear()
        counts = {s: 0 for s in Status}
        for m in report.meta.get("mentions", []):
            status: Status = m["status"]
            counts[status] += 1
            detail = m["detail"]
            if m.get("covered_by"):
                detail += f"  [contrôlé par {', '.join(m['covered_by'])} — Validateur]"
            item = QTreeWidgetItem([_ICON[status], m["label"], status.value, detail])
            item.setToolTip(1, f"{m['id']} — {m['legal']}\nChamp : {m['bt']}")
            item.setToolTip(3, detail)
            item.setForeground(0, QColor(colors[status]))
            item.setForeground(2, QColor(colors[status]))
            item.setTextAlignment(0, Qt.AlignmentFlag.AlignCenter)
            self.tree.addTopLevelItem(item)
        self.summary.setText(
            f"{counts[Status.OK]} présente(s) · {counts[Status.MISSING]} absente(s) · "
            f"{counts[Status.CHECK]} à vérifier · {counts[Status.NA]} sans objet"
        )
