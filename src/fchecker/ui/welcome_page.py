from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget


class WelcomePage(QWidget):
    open_requested = Signal()
    recent_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("documentArea")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.drop_zone = QFrame(objectName="dropZone")
        self.drop_zone.setFixedSize(520, 240)
        dz = QVBoxLayout(self.drop_zone)
        dz.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz.setSpacing(10)
        title = QLabel("Déposez une facture ici", objectName="h1")
        hint = QLabel("PDF Factur-X, XML CII ou XML UBL", objectName="muted")
        btn = QPushButton("Ouvrir un fichier…  (Ctrl+O)", objectName="primary")
        btn.clicked.connect(self.open_requested)
        for w in (title, hint, btn):
            dz.addWidget(w, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(self.drop_zone, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._recent_box = QVBoxLayout()
        self._recent_box.setSpacing(0)
        outer.addSpacing(24)
        self._recent_title = QLabel("Récents", objectName="muted")
        outer.addWidget(self._recent_title, alignment=Qt.AlignmentFlag.AlignHCenter)
        holder = QWidget()
        holder.setLayout(self._recent_box)
        outer.addWidget(holder, alignment=Qt.AlignmentFlag.AlignHCenter)

    def set_drag_active(self, active: bool) -> None:
        self.drop_zone.setProperty("dragActive", active)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)

    def set_recent(self, paths: list[str]) -> None:
        while (item := self._recent_box.takeAt(0)) is not None:
            if w := item.widget():
                w.deleteLater()
        existing = [p for p in paths if Path(p).exists()]
        self._recent_title.setVisible(bool(existing))
        for p in existing:
            b = QPushButton(Path(p).name, objectName="linkButton")
            b.setToolTip(p)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, path=p: self.recent_requested.emit(path))
            self._recent_box.addWidget(b)
