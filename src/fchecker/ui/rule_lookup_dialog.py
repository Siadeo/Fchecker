"""Recherche d'une règle par code ou par texte, sans document ouvert (ex. rejet d'une plateforme)."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from fchecker.core.rules_catalog import candidate_keys, catalog


def entry_html(key: str, e: dict) -> str:
    muted = "opacity:.7"
    parts = [f"<p style='font-size:12pt'><b>{escape(e.get('id', key))}</b></p>"]
    if e.get("title"):
        parts.append(f"<p><b>{escape(e['title'])}</b></p>")
    for variant in e.get("variants") or []:
        parts.append(f"<p style='{muted}'>Variante : {escape(variant)}</p>")
    if e.get("explanation"):
        parts.extend(f"<p>{escape(p)}</p>" for p in str(e["explanation"]).split("\n\n"))
    if e.get("context"):
        parts.append(f"<p><span style='{muted}'>Contexte :</span> {escape(e['context'])}</p>")
    if e.get("correction"):
        parts.append(f"<p><b>Correction :</b> {escape(e['correction'])}</p>")
    if e.get("example"):
        parts.append(f"<p style='{muted}'>Exemple :</p><pre>{escape(e['example'])}</pre>")
    if e.get("bt"):
        parts.append(f"<p><span style='{muted}'>Champs :</span> {escape(', '.join(e['bt']))}</p>")
    if e.get("original"):
        parts.append(f"<p style='{muted}'>Texte original (anglais) : {escape(e['original'])}</p>")
    if e.get("source"):
        parts.append(f"<p style='{muted}'>Source : {escape(e['source'])}</p>")
    return "".join(parts)


class RuleLookupDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, initial: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Règles")
        self.resize(900, 560)
        layout = QVBoxLayout(self)
        self.search = QLineEdit(
            placeholderText="Filtrer par code (BR-CO-15, BR-FR-05, G1.43…) ou par mots (pénalités, SIRET…)",
            clearButtonEnabled=True)
        layout.addWidget(self.search)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.results = QListWidget()
        self.detail = QTextBrowser(objectName="findingDetail")
        split.addWidget(self.results)
        split.addWidget(self.detail)
        split.setSizes([320, 580])
        layout.addWidget(split, 1)
        self.count = QLabel("", objectName="muted")
        layout.addWidget(self.count)

        self._timer = QTimer(self, singleShot=True, interval=150)  # recherche pendant la frappe, sans à-coups
        self._timer.timeout.connect(self._refresh)
        self.search.textChanged.connect(lambda _: self._timer.start())
        self.results.currentItemChanged.connect(self._show)
        self._refresh()
        self._select(initial)

    def _refresh(self) -> None:
        self.results.clear()
        hits = catalog().lookup(self.search.text())
        for key, entry in hits:
            item = QListWidgetItem(f"{entry.get('id', key)} — {str(entry.get('title', ''))[:90]}")
            item.setData(Qt.ItemDataRole.UserRole, (key, entry))
            self.results.addItem(item)
        self.count.setText(f"{len(hits)} règle(s)")
        if hits:
            self.results.setCurrentRow(0)
        else:
            self.detail.clear()

    def _select(self, rule_id: str) -> None:
        """Sélectionne la règle (ou, à défaut, sa règle de base) dans la liste complète."""
        if not rule_id:
            return
        rows = {self.results.item(i).data(Qt.ItemDataRole.UserRole)[0]: i for i in range(self.results.count())}
        for key in candidate_keys(rule_id):
            if key in rows:
                self.results.setCurrentRow(rows[key])
                self.results.scrollToItem(self.results.currentItem(), QListWidget.ScrollHint.PositionAtCenter)
                return

    def _show(self, item: QListWidgetItem | None, _previous=None) -> None:
        if item is not None:
            key, entry = item.data(Qt.ItemDataRole.UserRole)
            self.detail.setHtml(entry_html(key, entry))
