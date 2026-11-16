"""Structure du XML affiché : éléments, positions et lignes (Python pur, sans Qt ni lxml).

lxml ne donne ni la ligne de fin ni les positions d'un élément, et le document est partagé avec les
workers de contrôle (pas de lxml concurrent) : la vue XML découpe donc son propre texte.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field

_TOKEN = re.compile(
    r"""
    (?P<comment><!--.*?-->)
    |(?P<cdata><!\[CDATA\[.*?\]\]>)
    |(?P<pi><\?.*?\?>)
    |(?P<decl><!(?:[^>\[]|\[.*?\])*>)
    |<(?P<close>/)?(?P<name>[^\s/>!?]+)(?:[^>"']|"[^"]*"|'[^']*')*?(?P<empty>/)?>
    """,
    re.S | re.X,
)


@dataclass(eq=False)
class XmlNode:
    """Un élément : ``start``/``end`` en caractères (fin exclue), lignes 1-based.

    ``tag_line`` est la ligne du ``>`` de la balise ouvrante : c'est le ``sourceline`` de libxml2
    (donc des constats) quand la balise s'étend sur plusieurs lignes (racine et ses ``xmlns``).
    """

    name: str
    start: int
    end: int
    start_line: int
    end_line: int
    tag_line: int
    depth: int
    parent: XmlNode | None = field(default=None, repr=False)
    children: list[XmlNode] = field(default_factory=list, repr=False)

    @property
    def foldable(self) -> bool:
        return self.end_line > self.start_line

    def ancestors(self) -> list[XmlNode]:
        """De la racine au parent."""
        chain: list[XmlNode] = []
        node = self.parent
        while node is not None:
            chain.append(node)
            node = node.parent
        return chain[::-1]

    def path(self) -> list[XmlNode]:
        return [*self.ancestors(), self]

    def contains(self, other: XmlNode) -> bool:
        return self.start <= other.start and other.end <= self.end


class Outline:
    """Éléments du texte, dans l'ordre du document."""

    def __init__(self, text: str) -> None:
        self.text = text
        self._line_starts = [0] + [m.end() for m in re.finditer("\n", text)]
        self.nodes: list[XmlNode] = []
        self._parse()
        self._starts = [n.start for n in self.nodes]

    @property
    def line_count(self) -> int:
        return len(self._line_starts)

    def line_of(self, offset: int) -> int:
        return bisect_right(self._line_starts, offset)

    def _parse(self) -> None:
        stack: list[XmlNode] = []
        for m in _TOKEN.finditer(self.text):
            name = m.group("name")
            if name is None:
                continue
            if m.group("close"):
                if not any(n.name == name for n in stack):
                    continue  # balise fermante orpheline : ignorée
                while stack:
                    node = stack.pop()
                    node.end, node.end_line = m.end(), self.line_of(m.end() - 1)
                    if node.name == name:
                        break
                continue
            parent = stack[-1] if stack else None
            tag_line = self.line_of(m.end() - 1)
            node = XmlNode(name, m.start(), m.end(), self.line_of(m.start()), tag_line, tag_line, len(stack), parent)
            if parent is not None:
                parent.children.append(node)
            self.nodes.append(node)
            if not m.group("empty"):
                stack.append(node)
        for node in stack:  # éléments non fermés : jusqu'à la fin du texte
            node.end, node.end_line = len(self.text), self.line_count

    def node_at(self, offset: int) -> XmlNode | None:
        """Élément le plus profond contenant la position."""
        i = bisect_right(self._starts, offset) - 1
        node = self.nodes[i] if i >= 0 else None
        while node is not None and not node.start <= offset < node.end:
            node = node.parent
        return node

    def descendants(self, node: XmlNode) -> list[XmlNode]:
        i = bisect_right(self._starts, node.start)
        j = bisect_right(self._starts, node.end - 1)
        return self.nodes[i:j]


def is_compact(outline: Outline) -> bool:
    """XML compacté (tout sur quelques lignes) : le repli par ligne y est inutilisable."""
    return len(outline.nodes) > 3 * outline.line_count


def reindent(text: str, indent: str = "  ") -> str:
    """Réindente pour l'affichage : seuls les blancs entre balises sont remplacés.

    Une feuille reste sur une ligne ; le texte, les commentaires et le contenu mixte sont conservés.
    """
    out: list[str] = []
    depth = 0
    last = "start"  # start | open | close | text
    pos = 0

    def newline() -> None:
        if last != "start":
            out.append("\n" + indent * depth)

    for m in _TOKEN.finditer(text):
        between = text[pos:m.start()]
        pos = m.end()
        if between.strip() or (between and last == "open" and m.group("close")):  # « <a> </a> » intact
            out.append(between)
            last = "text"
        token = m.group(0)
        if m.group("cdata"):
            out.append(token)
            last = "text"
        elif m.group("name") is None:  # commentaire, PI, déclaration
            if last != "text":
                newline()
            out.append(token)
            last = "close"
        elif m.group("close"):
            depth = max(0, depth - 1)
            if last not in ("open", "text"):
                newline()
            out.append(token)
            last = "close"
        else:
            if last != "text":
                newline()
            out.append(token)
            if m.group("empty"):
                last = "close"
            else:
                depth += 1
                last = "open"
    tail = text[pos:]
    if tail.strip():
        out.append(tail)
    return "".join(out) + "\n"


def line_map(raw: Outline, shown: Outline) -> dict[int, int]:
    """Ligne du fichier d'origine → ligne affichée (premier élément de chaque ligne d'origine)."""
    if len(raw.nodes) != len(shown.nodes):
        return {}
    mapping: dict[int, int] = {}
    for a, b in zip(raw.nodes, shown.nodes):
        mapping.setdefault(a.tag_line, b.tag_line)
    return mapping


def map_line(mapping: dict[int, int], line: int) -> int:
    """Ligne affichée pour une ligne d'origine (dernier élément commencé à cette ligne ou avant)."""
    if not mapping:
        return line
    keys = sorted(mapping)
    i = bisect_right(keys, line) - 1
    return mapping[keys[i]] if i >= 0 else 1
