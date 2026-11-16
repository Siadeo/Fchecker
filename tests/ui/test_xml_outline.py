from lxml import etree

from fchecker.ui.widgets.xml_outline import Outline, is_compact, line_map, map_line, reindent

XML = """<?xml version="1.0"?>
<!-- <Faux> commentaire -->
<Invoice xmlns:cbc="urn:x"
         xmlns:cac="urn:y">
  <cbc:ID>F1</cbc:ID>
  <cac:Party attr="a>b">
    <cbc:Name><![CDATA[<pas un élément>]]></cbc:Name>
    <cbc:Empty/>
  </cac:Party>
</Invoice>
"""


def _elements(xml: str):
    return [e for e in etree.fromstring(xml.encode()).iter() if isinstance(e.tag, str)]


def test_parse_outline_structure():
    ol = Outline(XML)
    assert [n.name for n in ol.nodes] == ["Invoice", "cbc:ID", "cac:Party", "cbc:Name", "cbc:Empty"]
    root, ident, party, name, empty = ol.nodes
    assert (root.start_line, root.tag_line, root.end_line) == (3, 4, 10)
    assert (party.start_line, party.end_line) == (6, 9)
    assert party.parent is root and party.children == [name, empty]
    assert name.path() == [root, party, name] and name.depth == 2
    assert not ident.foldable and party.foldable
    assert XML[empty.start:empty.end] == "<cbc:Empty/>"
    assert ol.descendants(party) == [name, empty]


def test_tag_line_matches_lxml_sourceline(sample_xml):
    ol = Outline(sample_xml)
    assert [n.tag_line for n in ol.nodes] == [e.sourceline for e in _elements(sample_xml)]


def test_node_at():
    ol = Outline(XML)
    assert ol.node_at(XML.index("F1")).name == "cbc:ID"
    assert ol.node_at(XML.index("pas un")).name == "cbc:Name"
    assert ol.node_at(XML.index("  </cac:Party>")).name == "cac:Party"
    assert ol.node_at(0) is None  # prologue


def test_unbalanced_xml_is_tolerated():
    ol = Outline("<a><b></c></b>")
    assert [n.name for n in ol.nodes] == ["a", "b"]
    assert ol.nodes[0].end == len("<a><b></c></b>")


def test_reindent_compact_xml(sample_xml):
    compact = etree.tostring(etree.fromstring(sample_xml.encode(), etree.XMLParser(remove_blank_text=True)),
                             encoding="unicode")
    raw = Outline(compact)
    assert is_compact(raw) and not is_compact(Outline(sample_xml))
    shown = Outline(reindent(compact))
    assert shown.line_count > 100
    assert len(shown.nodes) == len(raw.nodes)
    before, after = _elements(compact), _elements(shown.text)
    assert [e.text for e in before if len(e) == 0] == [e.text for e in after if len(e) == 0]
    assert line_map(raw, shown) == {1: 1}


def test_reindent_keeps_leaf_values():
    assert reindent("<a><b> </b><c>x<d/>y</c></a>") == "<a>\n  <b> </b>\n  <c>x<d/>y</c>\n</a>\n"


def test_map_line():
    mapping = {1: 1, 5: 12, 9: 30}
    assert map_line(mapping, 5) == 12
    assert map_line(mapping, 7) == 12
    assert map_line({}, 7) == 7
