import pytest
from PySide6.QtCore import QSize

from fchecker.ui import theme


def _opaque(img, x0, y0, x1, y1) -> int:
    return sum(1 for x in range(x0, x1) for y in range(y0, y1) if img.pixelColor(x, y).alpha() > 0)


@pytest.mark.parametrize("dpr", [1.0, 1.25, 1.5, 2.0])
def test_icon_not_clipped_on_scaled_screen(qapp, dpr):
    """Écran mis à l'échelle : l'icône entière est dessinée, pas seulement son quart haut-gauche."""
    img = theme.icon("run", "#000000", 24).pixmap(QSize(24, 24), dpr).toImage()
    w, h = img.width(), img.height()
    # Triangle « run » : il occupe aussi la moitié droite et la moitié basse de l'icône.
    assert _opaque(img, w // 2, 0, w, h) > 0 and _opaque(img, 0, h // 2, w, h) > 0
    assert _opaque(img, 0, 0, w // 2, h // 2) > 0
