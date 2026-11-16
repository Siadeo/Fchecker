from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from fchecker.core.findings import Severity
from fchecker.core.report import Report
from fchecker.ui import theme


class ValidatorView(QWidget):
    def __init__(self, spec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(QLabel(spec.name, objectName="h1"))
        self.status = QLabel("Validation non exécutée — F5 pour lancer tous les contrôles.", objectName="muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Contrôle", "Résultat", "Erreurs", "Avert.", "Infos"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        h = self.tree.header()
        h.setStretchLastSection(False)
        h.setMinimumSectionSize(48)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 5):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setMinimumWidth(460)
        layout.addWidget(self.tree, 1)

        self.packs = QLabel("", objectName="muted")
        self.packs.setWordWrap(True)
        self.packs.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.packs)

    def show_report(self, report: Report) -> None:
        p = theme.palette()
        self.tree.clear()
        blocking = 0
        for check in report.meta.get("checks", []):
            counts = check["counts"]
            errors = counts[Severity.FATAL] + counts[Severity.ERROR]
            blocking += errors
            if errors:
                verdict, color = "Non conforme", p.error
            elif counts[Severity.WARNING]:
                verdict, color = "Avertissements", p.warning
            else:
                verdict, color = "Conforme", p.ok
            item = QTreeWidgetItem([
                check["label"], verdict, str(errors), str(counts[Severity.WARNING]),
                str(counts[Severity.INFO]),
            ])
            item.setForeground(1, QColor(color))
            for col in range(2, 5):
                item.setTextAlignment(col, Qt.AlignmentFlag.AlignCenter)
            self.tree.addTopLevelItem(item)
        total = f"{report.duration:.2f} s".replace(".", ",")
        self.status.setText(
            f"Facture non conforme : {blocking} erreur(s) bloquante(s) — détail dans le panneau Problèmes."
            if blocking else f"Aucune erreur bloquante ({total})."
        )
        self.packs.setText("Référentiels : " + " · ".join(f"{k} {v}" for k, v in report.rule_packs.items()))
