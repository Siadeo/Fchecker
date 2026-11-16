import pytest
from lxml import etree
from PySide6.QtCore import QSettings

from fchecker.ui.widgets.xml_view import XmlView


@pytest.fixture
def make_view(qtbot):
    def make(text: str) -> XmlView:
        view = XmlView(text)
        qtbot.addWidget(view)
        view.resize(700, 500)
        view.show()
        return view
    return make


@pytest.fixture
def view(make_view, sample_xml):
    return make_view(sample_xml)


def _visible_lines(editor) -> list[int]:
    lines, block = [], editor.document().begin()
    while block.isValid():
        if block.isVisible():
            lines.append(block.blockNumber() + 1)
        block = block.next()
    return lines


def _node(view, name: str):
    return next(n for n in view.editor.outline.nodes if n.name == name)


def test_syntax_highlighting(view):
    block = view.editor.document().findBlockByNumber(_node(view, "ram:ID").start_line - 1)
    assert block.layout().formats()  # balises et valeurs colorées


def test_collapse_and_expand_all(view):
    ed = view.editor
    total = ed.blockCount()
    view.btn_collapse.click()
    visible = _visible_lines(ed)
    assert len(visible) < 20
    # La racine et ses enfants directs restent visibles
    assert all(n.start_line in visible for n in ed.outline.nodes if n.depth <= 1)
    view.btn_expand.click()
    assert len(_visible_lines(ed)) == total


def test_toggle_fold_from_gutter(view, qtbot):
    ed = view.editor
    party = _node(view, "ram:SellerTradeParty")
    ed.toggle_fold(party)
    assert ed.is_folded(party)
    assert party.start_line in _visible_lines(ed) and party.start_line + 1 not in _visible_lines(ed)
    ed.toggle_fold(party)
    assert party.start_line + 1 in _visible_lines(ed)


def test_focus_node_expands_it_and_folds_the_rest(view):
    ed = view.editor
    seller, buyer = _node(view, "ram:SellerTradeParty"), _node(view, "ram:BuyerTradeParty")
    ed.focus_node(seller)
    visible = set(_visible_lines(ed))
    assert set(range(seller.start_line, seller.end_line + 1)) <= visible
    assert ed.is_folded(buyer) and buyer.start_line + 1 not in visible
    assert ed.outline.node_at(ed.cursor_offset()) is seller


def test_search_highlights_and_reveals(view):
    ed = view.editor
    view.btn_collapse.click()
    view.search.setText("sellertradeparty")  # insensible à la casse
    view.find_next()  # recherche différée lancée immédiatement
    assert view.match_count >= 2  # balise ouvrante + fermante
    assert view.count_label.text() == f"1 / {view.match_count}"
    assert ed.textCursor().block().isVisible()
    first = ed.textCursor().position()
    view.find_next()
    assert ed.textCursor().position() > first and ed.textCursor().block().isVisible()
    assert view.count_label.text() == f"2 / {view.match_count}"
    view.find_previous()
    assert ed.textCursor().position() == first
    assert len(ed.extraSelections()) >= view.match_count

    view.search.setText("introuvable-xyz")
    view.find_next()
    assert view.match_count == 0 and view.count_label.text() == "Aucun résultat"


def test_search_matches_attributes_and_values(view):
    view.search.setText('schemeID="0225"')
    view.find_next()
    assert view.match_count >= 1


def test_breadcrumb_follows_cursor_and_focuses(view):
    ed = view.editor
    seller = _node(view, "ram:SellerTradeParty")
    name = next(n for n in seller.children if n.name == "ram:Name")
    cursor = ed.textCursor()
    cursor.setPosition(ed.to_qt(name.start) + 3)
    ed.setTextCursor(cursor)
    assert view.breadcrumb.path == name.path()
    assert [b.text() for b in view.breadcrumb.buttons][-2:] == ["ram:SellerTradeParty", "ram:Name"]

    view.breadcrumb.buttons[-2].click()  # clic sur SellerTradeParty
    assert ed.textCursor().block().blockNumber() + 1 == seller.start_line
    assert ed.is_folded(_node(view, "ram:BuyerTradeParty"))
    assert not ed.is_folded(seller)
    # Bloc entier surligné, du début à la fin de l'élément
    doc = ed.document()
    covered = {(s.cursor.selectionStart(), s.cursor.selectionEnd()) for s in ed.extraSelections()}
    first, last = (doc.findBlockByNumber(n - 1).position() for n in (seller.start_line, seller.end_line))
    assert {(first, last), (last, last)} <= covered


def test_breadcrumb_can_be_hidden_and_is_remembered(view, make_view, sample_xml):
    try:
        view.breadcrumb.set_path([_node(view, "ram:SellerTradeParty")])
        view.breadcrumb.buttons[0].click()
        assert view.editor.extraSelections()  # bloc surligné
        view.btn_breadcrumb.click()
        assert not view.breadcrumb.isVisible()
        assert not view.editor.extraSelections()  # surlignage retiré avec le fil d'Ariane
        assert QSettings().value("ui/xmlBreadcrumb", True, type=bool) is False
        assert not make_view(sample_xml).breadcrumb.isVisibleTo(view)
    finally:
        QSettings().setValue("ui/xmlBreadcrumb", True)


def test_goto_line_unfolds_target(view):
    ed = view.editor
    target = _node(view, "ram:BuyerTradeParty").children[0]
    view.btn_collapse.click()
    assert target.tag_line not in _visible_lines(ed)
    view.goto_line(target.tag_line)
    assert target.tag_line in _visible_lines(ed)
    assert ed.textCursor().block().blockNumber() + 1 == target.tag_line


def test_compact_xml_is_reindented(make_view, sample_xml):
    compact = etree.tostring(etree.fromstring(sample_xml.encode(), etree.XMLParser(remove_blank_text=True)),
                             encoding="unicode")
    view = make_view(compact)
    assert view.editor.reindented and view.editor.blockCount() > 100
    view.btn_collapse.click()
    assert len(_visible_lines(view.editor)) < 20
    view.goto_line(1)


def test_positions_after_non_bmp_characters(make_view):
    view = make_view("<a>\n  <b>😀 texte</b>\n  <c>cible</c>\n</a>\n")
    view.search.setText("cible")
    view.find_next()
    ed = view.editor
    assert ed.outline.text[ed.cursor_offset():].startswith("cible")
    assert view.breadcrumb.path[-1].name == "c"
