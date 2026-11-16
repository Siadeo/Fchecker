"""Thème : QSS généré à partir des tokens + icônes SVG recolorées."""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from importlib import resources
from string import Template

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPalette, QPixmap, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from .tokens import DARK, LIGHT, Palette


class ThemeMode(str, Enum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


_current: Palette = LIGHT


def palette() -> Palette:
    return _current


def resolve(mode: ThemeMode) -> Palette:
    if mode is ThemeMode.SYSTEM:
        hints = QGuiApplication.styleHints()
        return DARK if hints.colorScheme() == Qt.ColorScheme.Dark else LIGHT
    return DARK if mode is ThemeMode.DARK else LIGHT


def apply(app: QApplication, mode: ThemeMode = ThemeMode.SYSTEM) -> Palette:
    global _current
    _current = resolve(mode)
    tmpl = resources.files(__package__).joinpath("app.qss.tmpl").read_text(encoding="utf-8")
    values = _current.as_dict() | {"close_icon": _icon_file("close", _current.text_muted)}
    app.setStyleSheet(Template(tmpl).substitute(values))

    # Palette Qt alignée sur les tokens (widgets non stylés, QPdfView, dialogues natifs).
    qp = QPalette()
    qp.setColor(QPalette.ColorRole.Window, QColor(_current.bg))
    qp.setColor(QPalette.ColorRole.Base, QColor(_current.surface))
    qp.setColor(QPalette.ColorRole.AlternateBase, QColor(_current.bg))
    qp.setColor(QPalette.ColorRole.Text, QColor(_current.text))
    qp.setColor(QPalette.ColorRole.WindowText, QColor(_current.text))
    qp.setColor(QPalette.ColorRole.Button, QColor(_current.surface))
    qp.setColor(QPalette.ColorRole.ButtonText, QColor(_current.text))
    qp.setColor(QPalette.ColorRole.Highlight, QColor(_current.selection))
    qp.setColor(QPalette.ColorRole.HighlightedText, QColor(_current.text))
    qp.setColor(QPalette.ColorRole.PlaceholderText, QColor(_current.text_muted))
    app.setPalette(qp)
    icon.cache_clear()
    return _current


def _icon_file(name: str, color: str) -> str:
    """Le QSS n'accepte que des chemins : icône recolorée écrite dans le cache utilisateur."""
    from platformdirs import user_cache_path

    target = user_cache_path("fchecker", appauthor=False) / "icons" / f"{name}-{color.lstrip('#')}.svg"
    if not target.exists():
        svg = resources.files(__package__).joinpath("icons", f"{name}.svg").read_text(encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(svg.replace("currentColor", color), encoding="utf-8")
    return target.as_posix()


@lru_cache(maxsize=256)
def icon(name: str, color: str | None = None, size: int = 24) -> QIcon:
    """Icône SVG monochrome (``currentColor``) recolorée avec un token."""
    icons = resources.files(__package__).joinpath("icons")
    path = icons.joinpath(f"{name}.svg")
    if not path.is_file():  # plugin externe sans icône fournie
        path = icons.joinpath("plugin.svg")
    svg = path.read_text(encoding="utf-8")
    svg = svg.replace("currentColor", color or _current.text_muted)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    result = QIcon()
    for scale in (1, 2):
        pm = QPixmap(QSize(size * scale, size * scale))
        pm.fill(Qt.GlobalColor.transparent)
        pm.setDevicePixelRatio(scale)
        painter = QPainter(pm)
        # Cible explicite en coordonnées logiques : sans elle, le SVG est rendu à la taille physique
        # (×2) et seul son quart haut-gauche apparaît sur un écran mis à l'échelle (125 %, 150 %…).
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        result.addPixmap(pm)
    return result
