from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QToolButton, QVBoxLayout, QWidget

from fchecker.core.plugin import ToolSpec
from fchecker.ui import theme

BAR_WIDTH = 80
BUTTON_HEIGHT = 58


class ActivityBar(QWidget):
    """Colonne d'icônes libellées, générée depuis le registre de plugins."""

    tool_selected = Signal(str)
    settings_requested = Signal()

    def __init__(self, specs: list[ToolSpec], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("activityBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(BAR_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}
        for i, spec in enumerate(specs):
            shortcut = f" (Ctrl+{i + 1})" if i < 9 else ""
            b = self._make_button(
                spec.icon, spec.short_label, f"<b>{spec.name}</b>{shortcut}<br>{spec.description}"
            )
            b.setCheckable(True)
            b.setProperty("toolId", spec.id)
            b.clicked.connect(lambda _=False, tid=spec.id: self.tool_selected.emit(tid))
            self._group.addButton(b)
            self._buttons[spec.id] = b
            layout.addWidget(b)
            # Filet entre deux outils : aucun sous le dernier outil ni sous Paramètres.
            if i < len(specs) - 1:
                layout.addWidget(self._make_separator(), 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        settings = self._make_button("settings", "PARAMÈTRES", "Paramètres")
        settings.clicked.connect(self.settings_requested)
        layout.addWidget(settings)
        self._icons = {s.id: s.icon for s in specs}
        self._icons["__settings"] = "settings"
        self._settings = settings

    def _make_button(self, icon_name: str, label: str, tooltip: str) -> QToolButton:
        b = QToolButton(self)
        b.setIcon(theme.icon(icon_name))
        b.setIconSize(QSize(24, 24))
        b.setText(label)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        b.setToolTip(tooltip)
        b.setFixedSize(BAR_WIDTH, BUTTON_HEIGHT)
        b.setAutoRaise(True)
        return b

    def _make_separator(self) -> QFrame:
        sep = QFrame(self)
        sep.setObjectName("activitySep")
        sep.setFixedSize(BAR_WIDTH - 24, 1)
        return sep

    def buttons(self) -> dict[str, QToolButton]:
        return dict(self._buttons)

    def set_current(self, tool_id: str) -> None:
        if b := self._buttons.get(tool_id):
            b.setChecked(True)
        self._refresh_icons()

    def set_enabled_tools(self, enabled: set[str] | None) -> None:
        """``None`` : aucun document ouvert → tous les outils désactivés."""
        for tid, b in self._buttons.items():
            b.setEnabled(enabled is not None and tid in enabled)

    def _refresh_icons(self) -> None:
        p = theme.palette()
        for tid, b in self._buttons.items():
            b.setIcon(theme.icon(self._icons[tid], p.accent if b.isChecked() else None))

    def refresh_theme(self) -> None:
        self._settings.setIcon(theme.icon("settings"))
        self._refresh_icons()
