from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderView(QWidget):
    """Vue provisoire des outils non encore implémentés."""

    def __init__(self, title: str, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = QLabel(title, objectName="h1")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d = QLabel(description, objectName="muted")
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d.setWordWrap(True)
        s = QLabel("À venir", objectName="badge")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for w in (t, d, s):
            layout.addWidget(w, alignment=Qt.AlignmentFlag.AlignHCenter)
