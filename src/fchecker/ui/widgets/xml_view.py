"""Onglet XML du volet contextuel : barre d'outils (recherche, repli), fil d'Ariane, source colorée."""
from __future__ import annotations

import re
from bisect import bisect_left

from PySide6.QtCore import QEvent, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from fchecker.ui import theme
from fchecker.ui.widgets.code_view import CodeView
from fchecker.ui.widgets.xml_outline import XmlNode

_BREADCRUMB_KEY = "ui/xmlBreadcrumb"


class XmlBreadcrumb(QScrollArea):
    """Chemin de l'élément sous le curseur ; un clic affiche cet élément déplié, le reste replié."""

    node_clicked = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("xmlBreadcrumb")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget(objectName="xmlBreadcrumbInner")
        self._layout = QHBoxLayout(inner)
        self._layout.setContentsMargins(6, 2, 6, 2)
        self._layout.setSpacing(0)
        self.setWidget(inner)
        self.setFixedHeight(28)
        self.path: list[XmlNode] = []
        self.buttons: list[QToolButton] = []

    def set_path(self, path: list[XmlNode]) -> None:
        if path == self.path and self.buttons:
            return
        self.path = path
        while self._layout.count():
            w = self._layout.takeAt(0).widget()
            if w is not None:
                w.hide()  # deleteLater est différé : sans hide, l'ancien chemin reste peint dessous
                w.deleteLater()
        self.buttons = []
        for i, node in enumerate(path):
            if i:
                self._layout.addWidget(QLabel("›", objectName="crumbSep"))
            b = QToolButton(objectName="crumb", text=node.name, autoRaise=True)
            b.setToolTip(f"Afficher <{node.name}> déplié et replier le reste (ligne {node.start_line})")
            b.setProperty("current", i == len(path) - 1)
            b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)  # défile au lieu d'élider
            b.clicked.connect(lambda _=False, n=node: self.node_clicked.emit(n))
            self._layout.addWidget(b)
            self.buttons.append(b)
        self._layout.addStretch(1)
        # Le QScrollArea compresserait le chemin à la largeur visible : il doit défiler.
        # (``layout.minimumSize()`` n'est pas encore recalculé ici : somme des éléments.)
        margins = self._layout.contentsMargins()
        widgets = [self._layout.itemAt(i).widget() for i in range(self._layout.count())]
        for w in widgets:
            if w is not None:
                w.ensurePolished()
        width = margins.left() + margins.right() + sum(w.sizeHint().width() for w in widgets if w is not None)
        self.widget().setMinimumWidth(width)
        # Chemin long : on garde visible l'élément courant (la fin du chemin).
        QTimer.singleShot(0, lambda: self.horizontalScrollBar().setValue(self.horizontalScrollBar().maximum()))

    def wheelEvent(self, event) -> None:
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - event.angleDelta().y())


class XmlView(QWidget):
    """Source XML navigable. API utilisée par l'onglet : ``goto_line``, ``refresh_theme``."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.editor = CodeView(text)
        self._matches: list[tuple[int, int]] = []
        self._current = -1
        self._query = ""

        toolbar = QWidget(objectName="xmlToolbar")
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(6, 4, 6, 4)
        tl.setSpacing(2)
        self.search = QLineEdit(placeholderText="Rechercher dans le XML (Ctrl+F)", clearButtonEnabled=True)
        self.search.setMinimumWidth(140)
        self.search.setMaximumWidth(280)
        self.search.installEventFilter(self)
        tl.addWidget(self.search, 1)
        self.count_label = QLabel(objectName="xmlFindCount")
        tl.addWidget(self.count_label)
        self._buttons: list[tuple[QToolButton, str]] = []
        self.btn_prev = self._button(tl, "chevron-up", "Occurrence précédente (Maj+Entrée, Maj+F3)", self.find_previous)
        self.btn_next = self._button(tl, "chevron-down", "Occurrence suivante (Entrée, F3)", self.find_next)
        self._separator(tl)
        self.btn_expand = self._button(tl, "expand-all", "Tout déplier", self.editor.expand_all)
        self.btn_collapse = self._button(tl, "collapse-all", "Tout replier", self.editor.collapse_all)
        self._separator(tl)
        self.btn_breadcrumb = self._button(tl, "breadcrumb", "Afficher / masquer le fil d'Ariane", None)
        self.btn_breadcrumb.setCheckable(True)
        tl.addStretch(1)
        notes = []
        if self.editor.reindented:
            notes.append(("Affichage réindenté", "Le XML d'origine est compacté : il a été réindenté pour "
                          "l'affichage. Les numéros de ligne ne sont donc pas ceux du fichier."))
        if not self.editor.highlighted:
            notes.append(("Coloration désactivée", "Fichier trop volumineux pour la coloration syntaxique."))
        for label, tip in notes:
            note = QLabel(label, objectName="xmlNote", toolTip=tip)
            tl.addWidget(note)

        self.breadcrumb = XmlBreadcrumb()
        self.breadcrumb.node_clicked.connect(self._focus_node)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(toolbar)
        root.addWidget(self.breadcrumb)
        root.addWidget(self.editor, 1)

        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(self._run_search)
        self.search.textChanged.connect(lambda _: self._timer.start())
        self.editor.cursorPositionChanged.connect(self._update_breadcrumb)

        visible = QSettings().value(_BREADCRUMB_KEY, True, type=bool)
        self.btn_breadcrumb.setChecked(visible)
        self.breadcrumb.setVisible(visible)
        self.btn_breadcrumb.toggled.connect(self._set_breadcrumb_visible)
        self._update_breadcrumb()

        for keys, slot in ((QKeySequence.StandardKey.Find, self.focus_search),
                           (QKeySequence("F3"), self.find_next), (QKeySequence("Shift+F3"), self.find_previous)):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

    @staticmethod
    def _separator(layout: QHBoxLayout) -> None:
        """Filet vertical entre deux groupes de boutons."""
        sep = QFrame(objectName="xmlToolbarSep")
        sep.setFixedSize(1, 18)
        layout.addSpacing(4)
        layout.addWidget(sep)
        layout.addSpacing(4)

    def _button(self, layout: QHBoxLayout, icon: str, tip: str, slot) -> QToolButton:
        b = QToolButton(objectName="xmlTool", autoRaise=True, toolTip=tip)
        b.setIcon(theme.icon(icon))
        b.setIconSize(QSize(16, 16))
        if slot is not None:
            b.clicked.connect(slot)
        layout.addWidget(b)
        self._buttons.append((b, icon))
        return b

    # --- Recherche ---------------------------------------------------------------
    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                shift = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                self.find_previous() if shift else self.find_next()
                return True
            if key == Qt.Key.Key_Escape:
                self.search.clear()
                self.editor.setFocus()
                return True
        return super().eventFilter(obj, event)

    @property
    def match_count(self) -> int:
        return len(self._matches)

    def find_next(self) -> None:
        self._step(1)

    def find_previous(self) -> None:
        self._step(-1)

    def _step(self, delta: int) -> None:
        if self._timer.isActive() or self._query != self.search.text():
            self._run_search()  # se place déjà sur l'occurrence la plus proche du curseur
            return
        if self._matches:
            self._current = (self._current + delta) % len(self._matches)
            self.editor.show_match(self._current)
            self._update_count()

    def _run_search(self) -> None:
        """Recherche intégrale (texte simple, sans casse) : balises, attributs, valeurs, commentaires."""
        self._timer.stop()
        self._query = query = self.search.text()
        if query:
            rx = re.compile(re.escape(query), re.IGNORECASE)
            self._matches = [(m.start(), m.end() - m.start()) for m in rx.finditer(self.editor.outline.text)]
        else:
            self._matches = []
        self.editor.set_matches(self._matches)
        self._current = -1
        if self._matches:  # première occurrence à partir du curseur, en rebouclant
            pos = self.editor.cursor_offset()
            self._current = bisect_left([s for s, _ in self._matches], pos) % len(self._matches)
            self.editor.show_match(self._current)
        self._update_count()

    def _update_count(self) -> None:
        if not self._query:
            text, empty = "", False
        elif not self._matches:
            text, empty = "Aucun résultat", True
        else:
            text, empty = f"{self._current + 1} / {len(self._matches)}", False
        self.count_label.setText(text)
        if self.count_label.property("empty") != empty:
            self.count_label.setProperty("empty", empty)
            self.count_label.style().unpolish(self.count_label)
            self.count_label.style().polish(self.count_label)

    # --- Fil d'Ariane --------------------------------------------------------------
    def _set_breadcrumb_visible(self, visible: bool) -> None:
        QSettings().setValue(_BREADCRUMB_KEY, visible)
        self.breadcrumb.setVisible(visible)
        if not visible:  # le bloc surligné par un clic dans le fil d'Ariane n'a plus de raison d'être
            self.editor.clear_line_highlight()
        self._update_breadcrumb()

    def _update_breadcrumb(self) -> None:
        if not self.breadcrumb.isVisibleTo(self):
            return
        outline = self.editor.outline
        node = outline.node_at(self.editor.cursor_offset())
        if node is None and outline.nodes:  # avant la racine (prologue) : la racine
            node = outline.nodes[0]
        self.breadcrumb.set_path(node.path() if node is not None else [])

    def _focus_node(self, node: XmlNode) -> None:
        self.editor.focus_node(node)
        self.editor.setFocus()

    # --- API de l'onglet -------------------------------------------------------------
    def goto_line(self, line: int) -> None:
        self.editor.goto_line(line)

    def refresh_theme(self) -> None:
        self.editor.refresh_theme()
        for b, icon in self._buttons:
            b.setIcon(theme.icon(icon))
