"""Éditeur XML en lecture seule : numéros de ligne, coloration, repli des éléments, surlignage."""
from __future__ import annotations

import re
from bisect import bisect_left

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from fchecker.ui import theme
from fchecker.ui.widgets.xml_outline import Outline, XmlNode, is_compact, line_map, map_line, reindent

FOLD_WIDTH = 14  # colonne des marqueurs ▸ / ▾ dans la gouttière
MAX_HIGHLIGHT_CHARS = 5_000_000  # au-delà, pas de coloration (ouverture trop lente)
MAX_FIND_SELECTIONS = 2000  # occurrences surlignées ; le compteur, lui, reste exact

_NAME = re.compile(r"</?[^\s/>!?]*")
_ATTR = re.compile(r"""([^\s=/>"']+)(?:\s*=\s*("[^"]*"?|'[^']*'?))?""")
_ENTITY = re.compile(r"&[#\w.:-]+;")
_ASTRAL = re.compile("[\U00010000-\U0010ffff]")


class _XmlHighlighter(QSyntaxHighlighter):
    """Coloration XML ; l'état de bloc suit commentaires, CDATA et balises sur plusieurs lignes."""

    NORMAL, COMMENT, CDATA, TAG = 0, 1, 2, 3

    def __init__(self, document) -> None:
        super().__init__(document)
        self.refresh_colors()

    def refresh_colors(self) -> None:
        p = theme.palette()

        def fmt(color: str, italic: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            f.setFontItalic(italic)
            return f

        self._tag, self._attr, self._value = fmt(p.syn_tag), fmt(p.syn_attr), fmt(p.syn_value)
        self._comment, self._decl = fmt(p.syn_comment, italic=True), fmt(p.syn_decl)

    def highlightBlock(self, text: str) -> None:
        state = max(self.previousBlockState(), self.NORMAL)
        i, n = 0, len(text)
        while i < n:
            if state in (self.COMMENT, self.CDATA):
                mark, f = ("-->", self._comment) if state == self.COMMENT else ("]]>", self._decl)
                j = text.find(mark, i)
                if j < 0:
                    self.setFormat(i, n - i, f)
                    break
                self.setFormat(i, j + 3 - i, f)
                i, state = j + 3, self.NORMAL
            elif state == self.TAG:
                if text[i].isspace():
                    i += 1
                elif text.startswith(("/>", "?>"), i):
                    self.setFormat(i, 2, self._tag)
                    i, state = i + 2, self.NORMAL
                elif text[i] == ">":
                    self.setFormat(i, 1, self._tag)
                    i, state = i + 1, self.NORMAL
                elif m := _ATTR.match(text, i):
                    self.setFormat(m.start(1), len(m.group(1)), self._attr)
                    if m.group(2):
                        self.setFormat(m.start(2), len(m.group(2)), self._value)
                    i = m.end()
                else:
                    i += 1
            else:
                j = text.find("<", i)
                self._entities(text, i, n if j < 0 else j)
                if j < 0:
                    break
                i = j
                if text.startswith("<!--", i):
                    self.setFormat(i, 4, self._comment)
                    i, state = i + 4, self.COMMENT
                elif text.startswith("<![CDATA[", i):
                    self.setFormat(i, 9, self._decl)
                    i, state = i + 9, self.CDATA
                elif text.startswith(("<?", "<!"), i):
                    j = text.find(">", i)
                    j = n - 1 if j < 0 else j
                    self.setFormat(i, j + 1 - i, self._decl)
                    i = j + 1
                else:
                    m = _NAME.match(text, i)
                    self.setFormat(i, m.end() - i, self._tag)
                    i, state = m.end(), self.TAG
        self.setCurrentBlockState(state)

    def _entities(self, text: str, start: int, end: int) -> None:
        for m in _ENTITY.finditer(text, start, end):
            self.setFormat(m.start(), len(m.group()), self._decl)


class _Gutter(QWidget):
    def __init__(self, editor: CodeView) -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.paint_gutter(event)

    def mousePressEvent(self, event) -> None:
        self.editor.gutter_clicked(event.position().toPoint())


class CodeView(QPlainTextEdit):
    """Source XML. Un XML compacté est réindenté pour l'affichage (``reindented``) ;
    ``goto_line`` reçoit toujours les lignes du fichier d'origine (``sourceline`` des constats).
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Cascadia Mono")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(9)
        self.setFont(font)
        self._gutter = _Gutter(self)
        self.blockCountChanged.connect(lambda _: self.setViewportMargins(self.gutter_width(), 0, 0, 0))
        self.updateRequest.connect(self._on_update_request)

        # Fins de ligne normalisées comme libxml2 (CRLF / CR → LF) : les n° de ligne restent alignés sur lxml.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        raw = Outline(text)
        self.reindented = is_compact(raw)
        if self.reindented:
            self.outline = Outline(reindent(text))
            self._line_map = line_map(raw, self.outline)
        else:
            self.outline, self._line_map = raw, {}
        self.setPlainText(self.outline.text)
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)
        # Qt compte en UTF-16, Python en points de code : décalage après chaque caractère hors BMP.
        astral = [m.start() for m in _ASTRAL.finditer(self.outline.text)]
        self._astral, self._astral_qt = astral, [i + k for k, i in enumerate(astral)]

        self.highlighted = len(self.outline.text) <= MAX_HIGHLIGHT_CHARS
        self._highlighter = _XmlHighlighter(self.document()) if self.highlighted else None

        # Repli : un seul élément repliable par ligne (le plus externe qui y commence).
        self._fold_at: dict[int, XmlNode] = {}
        for node in self.outline.nodes:
            if node.foldable:
                self._fold_at.setdefault(node.start_line, node)
        self._folded: set[XmlNode] = set()
        self._hidden = bytearray(self.blockCount())  # 1 = ligne masquée (index 0-based)
        self._fold_marks: list[tuple[QRectF, XmlNode]] = []

        self._line_selection: list[QTextEdit.ExtraSelection] = []
        self._matches: list[tuple[int, int]] = []
        self._current_match = -1

    # --- Gouttière ---------------------------------------------------------------
    def gutter_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits + FOLD_WIDTH

    def _on_update_request(self, rect: QRect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def paint_gutter(self, event) -> None:
        p = theme.palette()
        painter = QPainter(self._gutter)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(event.rect(), QColor(p.surface_alt))
        muted = QColor(p.text_muted)
        numbers_width = self._gutter.width() - FOLD_WIDTH - 2
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible():
                painter.setPen(muted)
                painter.drawText(0, top, numbers_width, height,
                                 Qt.AlignmentFlag.AlignRight, str(block.blockNumber() + 1))
                node = self._fold_at.get(block.blockNumber() + 1)
                if node is not None:
                    self._paint_fold_marker(painter, numbers_width + 2, top, height, node in self._folded, muted)
            top += round(self.blockBoundingRect(block).height())
            block = self._next_visible(block)
        painter.end()

    @staticmethod
    def _paint_fold_marker(painter: QPainter, x: int, top: int, height: int, folded: bool, color: QColor) -> None:
        cx, cy, r = x + FOLD_WIDTH / 2, top + height / 2, 3.5
        path = QPainterPath()
        if folded:  # ▸
            path.moveTo(cx - r / 2, cy - r)
            path.lineTo(cx + r / 2 + 1, cy)
            path.lineTo(cx - r / 2, cy + r)
        else:  # ▾
            path.moveTo(cx - r, cy - r / 2)
            path.lineTo(cx + r, cy - r / 2)
            path.lineTo(cx, cy + r / 2 + 1)
        path.closeSubpath()
        painter.fillPath(path, color)

    def gutter_clicked(self, pos: QPoint) -> None:
        if pos.x() < self._gutter.width() - FOLD_WIDTH - 2:
            return
        block = self.cursorForPosition(QPoint(0, pos.y())).block()
        node = self._fold_at.get(block.blockNumber() + 1)
        if node is not None:
            self.toggle_fold(node)

    # --- Repli -------------------------------------------------------------------
    @property
    def foldable_nodes(self) -> list[XmlNode]:
        return list(self._fold_at.values())

    def is_folded(self, node: XmlNode) -> bool:
        return node in self._folded

    def toggle_fold(self, node: XmlNode) -> None:
        self._folded.symmetric_difference_update({node})
        self._apply_folding()

    def expand_all(self) -> None:
        self._folded.clear()
        self._apply_folding()

    def collapse_all(self) -> None:
        """Tout replier sauf la racine : ses enfants directs restent lisibles."""
        self._folded = {n for n in self._fold_at.values() if n.depth > 0}
        self._apply_folding()

    def focus_node(self, node: XmlNode) -> None:
        """Déplie ``node`` (et sa descendance) et le chemin qui y mène ; replie tout le reste."""
        keep = {*node.path(), *self.outline.descendants(node)}
        self._folded = {n for n in self._fold_at.values() if n not in keep}
        self._apply_folding()
        cursor = self.textCursor()
        cursor.setPosition(self.to_qt(node.start))
        self.setTextCursor(cursor)
        block = self.document().findBlockByNumber(node.start_line - 1)
        self.verticalScrollBar().setValue(block.firstLineNumber())
        self._highlight_lines(node.start_line, node.end_line)

    def reveal_line(self, line: int) -> None:
        """Déplie les éléments qui masquent la ligne affichée ``line`` (1-based)."""
        hiding = {n for n in self._folded if n.start_line < line <= n.end_line}
        if hiding:
            self._folded -= hiding
            self._apply_folding()

    def _next_visible(self, block):
        """Bloc visible suivant : saute d'un coup les lignes repliées (sinon peindre parcourt tout)."""
        n = block.blockNumber() + 1
        i = self._hidden.find(0, n)
        if i == n:
            return block.next()
        return self.document().findBlockByNumber(i) if i >= 0 else self.document().findBlockByNumber(-1)

    def _apply_folding(self) -> None:
        hidden = bytearray(self.blockCount())
        covered = 0
        for node in sorted(self._folded, key=lambda n: n.start_line):
            if node.start_line <= covered:  # déjà masqué par un ancêtre replié
                continue
            hidden[node.start_line:node.end_line] = b"\x01" * (node.end_line - node.start_line)
            covered = node.end_line
        self._hidden = hidden
        doc = self.document()
        block, changed = doc.begin(), False
        while block.isValid():
            visible = not hidden[block.blockNumber()]
            if block.isVisible() != visible:
                block.setVisible(visible)
                changed = True
            block = block.next()
        if changed:
            doc.markContentsDirty(0, doc.characterCount())
            cursor = self.textCursor()
            if not cursor.block().isVisible():  # curseur ramené sur la ligne repliée
                block = cursor.block()
                while block.isValid() and not block.isVisible():
                    block = block.previous()
                cursor.setPosition(block.position() if block.isValid() else 0)
                self.setTextCursor(cursor)
        self.viewport().update()
        self._gutter.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        self._fold_marks = []
        if not self._folded:
            return
        p = theme.palette()
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fm = self.fontMetrics()
        offset = self.contentOffset()
        block = self.firstVisibleBlock()
        while block.isValid():
            geo = self.blockBoundingGeometry(block).translated(offset)
            if geo.top() > event.rect().bottom():
                break
            node = self._fold_at.get(block.blockNumber() + 1)
            if block.isVisible() and node in self._folded:
                end = QTextCursor(block)
                end.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                x = self.cursorRect(end).right() + 6
                rect = QRectF(x, geo.top() + 1, fm.horizontalAdvance("⋯") + 12, fm.height() - 1)
                painter.setPen(QColor(p.border))
                painter.setBrush(QColor(p.surface_alt))
                painter.drawRoundedRect(rect, 3, 3)
                painter.setPen(QColor(p.text_muted))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "⋯")
                self._fold_marks.append((rect, node))
            block = self._next_visible(block)
        painter.end()

    def mousePressEvent(self, event) -> None:
        pos = QPointF(event.position())
        for rect, node in self._fold_marks:
            if rect.contains(pos):
                self.toggle_fold(node)
                return
        super().mousePressEvent(event)

    # --- Navigation et surlignage ----------------------------------------------------
    def to_qt(self, offset: int) -> int:
        """Position Python (``outline``) → position du document Qt."""
        return offset + bisect_left(self._astral, offset) if self._astral else offset

    def cursor_offset(self) -> int:
        """Position du curseur dans le texte de ``outline``."""
        pos = self.textCursor().position()
        return pos - bisect_left(self._astral_qt, pos) if self._astral else pos

    def display_line(self, line: int) -> int:
        """Ligne affichée correspondant à une ligne du fichier d'origine."""
        return map_line(self._line_map, line) if self._line_map else line

    def goto_line(self, line: int) -> None:
        """Place le curseur sur la ligne (1-based, fichier d'origine), la déplie et la surligne."""
        line = self.display_line(line)
        block = self.document().findBlockByNumber(max(0, line - 1))
        if not block.isValid():
            return
        self.reveal_line(block.blockNumber() + 1)
        self.setTextCursor(QTextCursor(block))
        self.centerCursor()
        self._highlight_lines(line, line)

    def clear_line_highlight(self) -> None:
        """Retire le surlignage de ligne ou de bloc (``goto_line``, ``focus_node``)."""
        if self._line_selection:
            self._line_selection = []
            self._update_selections()

    def _highlight_lines(self, first: int, last: int) -> None:
        """Surligne les lignes ``first`` à ``last`` (1-based) sur toute la largeur (même bleu
        que la sélection du panneau Problèmes)."""
        doc = self.document()
        last_block = doc.findBlockByNumber(last - 1)
        cursors = [QTextCursor(last_block)]  # curseur replié : pleine largeur sur une ligne
        if first < last:  # lignes précédentes : la sélection franchit leur fin → pleine largeur
            cursor = QTextCursor(doc.findBlockByNumber(first - 1))
            cursor.setPosition(last_block.position(), QTextCursor.MoveMode.KeepAnchor)
            cursors.append(cursor)
        self._line_selection = []
        for cursor in cursors:
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor(theme.palette().selection))
            sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            sel.cursor = cursor
            self._line_selection.append(sel)
        self._update_selections()

    def set_matches(self, matches: list[tuple[int, int]], current: int = -1) -> None:
        """Occurrences de recherche (position, longueur) ; ``current`` est mise en évidence."""
        self._matches, self._current_match = matches, current
        self._update_selections()

    def show_match(self, index: int) -> None:
        """Rend visible l'occurrence ``index`` (dépliage compris) et y place le curseur."""
        self._current_match = index
        start = self._matches[index][0]
        self.reveal_line(self.outline.line_of(start))
        cursor = self.textCursor()
        cursor.setPosition(self.to_qt(start))
        self.setTextCursor(cursor)
        self.centerCursor()
        self._update_selections()

    def _update_selections(self) -> None:
        p = theme.palette()
        doc = self.document()

        def selection(start: int, length: int, color: str) -> QTextEdit.ExtraSelection:
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor(color))
            cursor = QTextCursor(doc)
            cursor.setPosition(self.to_qt(start))
            cursor.setPosition(self.to_qt(start + length), QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = cursor
            return sel

        selections = list(self._line_selection)
        selections += [selection(s, n, p.find_match) for s, n in self._matches[:MAX_FIND_SELECTIONS]]
        if 0 <= self._current_match < len(self._matches):
            selections.append(selection(*self._matches[self._current_match], p.find_current))
        self.setExtraSelections(selections)

    def refresh_theme(self) -> None:
        if self._highlighter is not None:
            self._highlighter.refresh_colors()
            self._highlighter.rehighlight()
        for sel in self._line_selection:
            sel.format.setBackground(QColor(theme.palette().selection))
        self._update_selections()
        self._gutter.update()
