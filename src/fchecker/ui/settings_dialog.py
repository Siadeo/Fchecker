from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fchecker.core import settings as app_settings
from fchecker.core.referentiels import CATEGORIES, REFERENTIELS, Referentiel


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Paramètres")
        self.setMinimumWidth(720)
        s = app_settings.get()
        layout = QVBoxLayout(self)

        peppol = QGroupBox("Annuaire Peppol")
        pform = QFormLayout(peppol)
        self.peppol = QCheckBox("Vérifier l'adresse du destinataire dans l'annuaire Peppol (accès réseau)")
        self.peppol.setChecked(s.peppol_enabled)
        self.peppol_url = QLineEdit(s.peppol_url)
        self.timeout = QDoubleSpinBox(minimum=1, maximum=60, decimals=0, suffix=" s", value=s.peppol_timeout)
        self.cache = QDoubleSpinBox(minimum=0, maximum=720, decimals=0, suffix=" h", value=s.peppol_cache_hours)
        clear = QPushButton("Vider le cache")
        clear.clicked.connect(self._clear_cache)
        pform.addRow(self.peppol)
        pform.addRow("URL de l'API", self.peppol_url)
        pform.addRow("Délai maximal", self.timeout)
        pform.addRow("Durée du cache", self.cache)
        pform.addRow("", clear)
        self.peppol.toggled.connect(self._sync)
        layout.addWidget(peppol)

        packs = QGroupBox("Référentiels utilisés")
        pl = QVBoxLayout(packs)
        self.referentiels = self._referentiels_table()
        pl.addWidget(self.referentiels)
        layout.addWidget(packs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._sync(self.peppol.isChecked())

    @staticmethod
    def _referentiels_table() -> QTableWidget:
        """Tableau en lecture seule, regroupé par catégorie (lignes de titre sur toute la largeur)."""
        lignes: list[str | Referentiel] = []
        for categorie in CATEGORIES:
            lignes.append(categorie)
            lignes.extend(r for r in REFERENTIELS if r.categorie == categorie)
        table = QTableWidget(len(lignes), 3)
        table.setHorizontalHeaderLabels(["Référentiel", "Version", "Publication"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.verticalHeader().hide()
        table.setMinimumHeight(240)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for row, ligne in enumerate(lignes):
            if isinstance(ligne, str):
                item = QTableWidgetItem(ligne)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                table.setItem(row, 0, item)
                table.setSpan(row, 0, 1, 3)
                continue
            infobulle = f"{ligne.editeur} — {ligne.usage}"
            if ligne.note:
                infobulle += f"\n{ligne.note}"
            for col, texte in enumerate((ligne.nom, ligne.version, ligne.publication)):
                item = QTableWidgetItem(texte)
                item.setToolTip(infobulle)
                table.setItem(row, col, item)
        return table

    def _sync(self, on: bool) -> None:
        for w in (self.peppol_url, self.timeout, self.cache):
            w.setEnabled(on)

    def _clear_cache(self) -> None:
        from fchecker.core.services.peppol import LookupCache

        for name in ("peppol.sqlite", "smp.sqlite"):
            LookupCache(app_settings.cache_dir() / name).clear()
        QMessageBox.information(self, "Annuaire Peppol", "Cache de l'annuaire Peppol vidé.")

    def accept(self) -> None:
        try:
            app_settings.save(replace(
                app_settings.get(),
                peppol_enabled=self.peppol.isChecked(),
                peppol_url=self.peppol_url.text().strip() or app_settings.Settings().peppol_url,
                peppol_timeout=self.timeout.value(),
                peppol_cache_hours=self.cache.value(),
            ))
        except OSError as exc:  # ex. application installée dans un dossier protégé en écriture
            QMessageBox.warning(self, "Paramètres", f"Impossible d'enregistrer les réglages :\n{exc}")
            return
        super().accept()
