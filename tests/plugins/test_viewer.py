from pathlib import Path

import pytest

from fchecker.core.invoice import invoice_of
from fchecker.core.loader import load
from fchecker.plugins.viewer.render import render_invoice
from fchecker.plugins.viewer.view import LINE_MESSAGE, _viewer_page

EXAMPLES = Path(__file__).parents[1] / "fixtures" / "en16931"


def test_sample_rendering(facturx_path):
    html = render_invoice(load(facturx_path))
    for expected in ("F202500003", "LE VENDEUR", "LE CLIENT", "12 000,00 EUR", 'title="BT-112"',
                     "Prestation de services (S1)", "Indemnité forfaitaire de recouvrement", "Virement (30)",
                     "NOUS AUSSI"):
        assert expected in html, expected


def test_values_carry_xml_line(facturx_path):
    doc = load(facturx_path)
    inv = invoice_of(doc)
    html = render_invoice(doc)
    assert f'title="BT-1" data-line="{inv.number.line}"' in html
    assert f'title="BT-112" data-line="{inv.totals.lines_of["BT-112"]}"' in html
    assert f'<tr data-line="{inv.lines[0].line}">' in html  # repli : clic hors valeur
    first = inv.lines[0]
    assert f'title="BT-153" data-line="{first.lines_of["BT-153"]}"' in html  # cellule → valeur, pas la ligne
    assert first.lines_of["BT-153"] != first.line
    assert f'title="BT-117" data-line="{inv.vat_breakdown[0].lines_of["BT-117"]}"' in html
    assert "<script" not in html  # l'export reste statique


def test_interactive_rendering_adds_click_script(facturx_path):
    html = render_invoice(load(facturx_path), interactive=True)
    assert "<script" in html and LINE_MESSAGE in html


def test_viewer_page_forwards_line_clicks(qtbot):
    pytest.importorskip("PySide6.QtWebEngineCore")
    from PySide6.QtWidgets import QWidget

    host = QWidget()
    qtbot.addWidget(host)
    received: list[int] = []
    page = _viewer_page(host, received.append)
    page.javaScriptConsoleMessage(page.JavaScriptConsoleMessageLevel.InfoMessageLevel, f"{LINE_MESSAGE}42", 1, "")
    page.javaScriptConsoleMessage(page.JavaScriptConsoleMessageLevel.InfoMessageLevel, "autre message", 1, "")
    assert received == [42]


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*/*.xml")), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_all_official_examples_render(path):
    html = render_invoice(load(path))
    assert "<table>" in html and "Net à payer" in html
