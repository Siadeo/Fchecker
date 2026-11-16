from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QWidget,
)

from fchecker import __version__
from fchecker.core.document import InvoiceDocument
from fchecker.core.referentiels import ORGANISMES
from fchecker.core.registry import Registry
from fchecker.ui import theme
from fchecker.ui.activity_bar import ActivityBar
from fchecker.ui.controllers.document_controller import DocumentController
from fchecker.ui.controllers.run_controller import RunController
from fchecker.ui.document_tab import DocumentTab
from fchecker.ui.license_dialog import MENTION_CEN, RESPONSABILITE
from fchecker.ui.models.findings_model import FindingRole
from fchecker.ui.problems_panel import ProblemsPanel
from fchecker.ui.status_bar import StatusBar
from fchecker.ui.welcome_page import WelcomePage

FILE_FILTER = "Factures (*.pdf *.xml);;PDF Factur-X (*.pdf);;XML CII / UBL (*.xml);;Tous les fichiers (*)"
DEFAULT_TOOL = "dashboard"


def about_text() -> str:
    organismes = ", ".join(ORGANISMES[:-1]) + f" et {ORGANISMES[-1]}"
    return (
        f"<b>Fchecker</b> {__version__}<br>Boîte à outils facturation électronique "
        f"(Factur-X, CII, UBL).<br><br>Licence : Apache-2.0<br><br>"
        f"{escape(RESPONSABILITE)}<br><br>"
        f"{escape(MENTION_CEN)}<br><br>"
        f"Fchecker s'appuie sur les référentiels publiés par ces organismes : {organismes}. "
        f"Ces organismes ne sont pas associés à cette application. "
        f"Les règles EN 16931 (CEN/TC 434) sont vérifiées à l'aide des artefacts de validation officiels "
        f"(EUPL-1.2). Traduction française des règles réalisée pour Fchecker (EUPL-1.2)."
    )


class MainWindow(QMainWindow):
    def __init__(self, registry: Registry) -> None:
        super().__init__()
        self.registry = registry
        self.settings = QSettings()
        self.current_tool = DEFAULT_TOOL
        self.setWindowTitle("Fchecker par Siadeo")
        self.setAcceptDrops(True)
        self.resize(1360, 860)

        self.documents = DocumentController(self)
        self.runner = RunController(registry, self)

        self._build_central()
        self.problems = ProblemsPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.problems)
        self.status = StatusBar(self)
        self.setStatusBar(self.status)
        self._build_actions()
        self._build_menus_and_toolbar()
        self._wire()

        self.welcome.set_recent(self.documents.recent())
        self._on_tab_changed(-1)
        self._restore_geometry()

    # --- Construction ----------------------------------------------------------
    def _build_central(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.activity = ActivityBar(self.registry.specs, central)
        layout.addWidget(self.activity)

        self.pages = QStackedWidget(objectName="documentArea")
        self.welcome = WelcomePage()
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.pages.addWidget(self.welcome)
        self.pages.addWidget(self.tabs)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)

    def _action(self, text: str, slot, shortcut=None, icon: str | None = None, tip: str | None = None) -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if icon:
            a.setIcon(theme.icon(icon))
        if tip:
            a.setToolTip(tip)
        a.triggered.connect(slot)
        return a

    def _build_actions(self) -> None:
        self.act_open = self._action("&Ouvrir…", self.open_dialog, QKeySequence.StandardKey.Open, "open",
                                     "Ouvrir une facture (Ctrl+O)")
        self.act_close = self._action("&Fermer l'onglet", self.close_current, QKeySequence.StandardKey.Close)
        self.act_quit = self._action("&Quitter", self.close, QKeySequence.StandardKey.Quit)
        self.act_settings = self._action("&Paramètres…", self.open_settings, "Ctrl+,")
        self.act_run = self._action("Tout &valider", self.run_all, "F5", "run", "Exécuter tous les contrôles (F5)")
        self.act_export = self._action("&Exporter le rapport…", self.export_report, "Ctrl+E", "export",
                                       "Exporter le rapport (Ctrl+E)")
        self.act_lookup = self._action("&Règles…", self.lookup_rule, "Ctrl+Shift+R", None,
                                       "Consulter toutes les règles de contrôle et leur explication")
        self.act_problems = self.problems.toggleViewAction()
        self.act_problems.setText("Panneau &Problèmes")
        self.act_problems.setShortcut(QKeySequence("Ctrl+J"))
        self.act_context = self._action("&Volet PDF / XML", self._toggle_context, "Ctrl+K")
        self.act_context.setCheckable(True)
        self.act_context.setChecked(self.settings.value("ui/contextVisible", True, type=bool))

        self.tool_actions: list[QAction] = []
        for i, spec in enumerate(self.registry.specs):
            a = self._action(spec.name, lambda _=False, tid=spec.id: self.select_tool(tid),
                             f"Ctrl+{i + 1}" if i < 9 else None, spec.icon)
            self.tool_actions.append(a)

        self.theme_group = QActionGroup(self)
        self.theme_actions: dict[theme.ThemeMode, QAction] = {}
        saved = theme.ThemeMode(self.settings.value("ui/theme", theme.ThemeMode.SYSTEM.value))
        for mode, label in ((theme.ThemeMode.SYSTEM, "Selon le système"), (theme.ThemeMode.LIGHT, "Clair"),
                            (theme.ThemeMode.DARK, "Sombre")):
            a = self._action(label, lambda _=False, m=mode: self.set_theme(m))
            a.setCheckable(True)
            a.setChecked(mode is saved)
            self.theme_group.addAction(a)
            self.theme_actions[mode] = a

    def _build_menus_and_toolbar(self) -> None:
        mb = self.menuBar()
        m_file = mb.addMenu("&Fichier")
        m_file.addAction(self.act_open)
        self.m_recent = m_file.addMenu("Fichiers &récents")
        self._fill_recent_menu(self.documents.recent())
        m_file.addAction(self.act_close)
        m_file.addSeparator()
        m_file.addAction(self.act_export)
        m_file.addSeparator()
        m_file.addAction(self.act_settings)
        m_file.addAction(self.act_quit)

        m_tools = mb.addMenu("&Outils")
        m_tools.addAction(self.act_run)
        m_tools.addAction(self.act_lookup)
        m_tools.addSeparator()
        m_tools.addActions(self.tool_actions)

        m_view = mb.addMenu("&Affichage")
        m_view.addAction(self.act_problems)
        m_view.addAction(self.act_context)
        m_theme = m_view.addMenu("&Thème")
        m_theme.addActions(list(self.theme_actions.values()))

        m_help = mb.addMenu("A&ide")
        m_help.addAction(self._action("À &propos", self.about))

        tb = QToolBar("Principale", self, objectName="mainToolbar")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb.addActions([self.act_open, self.act_run, self.act_export])
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        self.toolbar = tb

    def _wire(self) -> None:
        self.activity.tool_selected.connect(self.select_tool)
        self.activity.settings_requested.connect(self.open_settings)
        self.welcome.open_requested.connect(self.open_dialog)
        self.welcome.recent_requested.connect(self.open_path)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.documents.loaded.connect(self._on_loaded)
        self.documents.failed.connect(
            lambda path, msg: QMessageBox.warning(self, "Ouverture impossible", f"{Path(path).name}\n\n{msg}")
        )
        self.documents.recent_changed.connect(self.welcome.set_recent)
        self.documents.recent_changed.connect(self._fill_recent_menu)
        self.problems.finding_activated.connect(
            lambda f: (tab := self.current_tab()) and tab.reveal(f)
        )
        self.runner.started.connect(lambda tab: self._set_running(tab, True))
        self.runner.finished.connect(self._on_run_finished)
        self.runner.tool_failed.connect(
            lambda tid, msg: self.status.showMessage(f"Échec de l'outil {tid} : {msg}", 8000)
        )

    # --- Documents -------------------------------------------------------------
    def open_dialog(self) -> None:
        start = self.settings.value("ui/lastDir", str(Path.home()))
        paths, _ = QFileDialog.getOpenFileNames(self, "Ouvrir une facture", start, FILE_FILTER)
        for p in paths:
            self.open_path(p)
        if paths:
            self.settings.setValue("ui/lastDir", str(Path(paths[0]).parent))

    def open_path(self, path: str) -> None:
        resolved = Path(path).resolve()
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if isinstance(tab, DocumentTab) and tab.doc.path.resolve() == resolved:
                self.tabs.setCurrentIndex(i)
                return
        self.status.showMessage(f"Chargement de {resolved.name}…")
        self.documents.open(resolved)

    def _on_loaded(self, doc: InvoiceDocument) -> None:
        self.status.clearMessage()
        tab = DocumentTab(doc, self.registry)
        tab.set_context_visible(self.act_context.isChecked())
        index = self.tabs.addTab(tab, doc.display_name)
        self.tabs.setTabToolTip(index, str(doc.path))
        self.tabs.setCurrentIndex(index)

    def current_tab(self) -> DocumentTab | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, DocumentTab) else None

    def close_current(self) -> None:
        if self.tabs.count():
            self._close_tab(self.tabs.currentIndex())

    def _close_tab(self, index: int) -> None:
        tab = self.tabs.widget(index)
        if isinstance(tab, DocumentTab):
            self.runner.cancel(tab)
            tab.dispose()
        self.tabs.removeTab(index)
        tab.deleteLater()

    def _on_tab_changed(self, _index: int) -> None:
        tab = self.current_tab()
        has_doc = tab is not None
        self.pages.setCurrentWidget(self.tabs if has_doc else self.welcome)
        self.activity.set_enabled_tools({s.id for s in self.registry.specs} if has_doc else None)
        for a in (self.act_run, self.act_export, self.act_close, *self.tool_actions):
            a.setEnabled(has_doc)
        self.problems.set_model(tab.findings if tab else None)
        self.status.show_document(tab.doc if tab else None)
        self.status.show_duration(None)
        self.status.show_directory(tab.findings.findings() if tab else [])
        if tab:
            tab.set_context_visible(self.act_context.isChecked())
            tab.show_tool(self.current_tool)
            self.activity.set_current(self.current_tool)
            self._set_running(tab, self.runner.is_running(tab))

    def _fill_recent_menu(self, paths: list[str]) -> None:
        self.m_recent.clear()
        existing = [p for p in paths if Path(p).exists()]
        for p in existing:
            self.m_recent.addAction(p, lambda path=p: self.open_path(path))
        self.m_recent.setEnabled(bool(existing))

    # --- Outils ----------------------------------------------------------------
    def select_tool(self, tool_id: str) -> None:
        self.current_tool = tool_id
        self.activity.set_current(tool_id)
        if tab := self.current_tab():
            tab.show_tool(tool_id)

    def run_all(self) -> None:
        if tab := self.current_tab():
            self.runner.run_all(tab)

    def _set_running(self, tab: DocumentTab, running: bool) -> None:
        if tab is self.current_tab():
            self.act_run.setEnabled(not running)
            if running:
                self.status.show_duration(None)
                self.status.showMessage("Contrôles en cours…")

    def _on_run_finished(self, tab: DocumentTab, seconds: float) -> None:
        if tab is self.current_tab():
            self.act_run.setEnabled(True)
            self.status.clearMessage()
            self.status.show_duration(seconds)
            self.status.show_directory(tab.findings.findings())

    def open_settings(self) -> None:
        from fchecker.ui.settings_dialog import SettingsDialog

        SettingsDialog(self).exec()

    def lookup_rule(self, initial: str = "") -> None:
        from fchecker.ui.rule_lookup_dialog import RuleLookupDialog

        tab = self.current_tab()
        if not initial and tab is not None:  # pré-remplit avec le constat sélectionné
            idx = self.problems.table.currentIndex()
            f = idx.data(FindingRole) if idx.isValid() else None
            initial = f.rule_id if f else ""
        RuleLookupDialog(self, initial if isinstance(initial, str) else "").exec()

    def export_report(self) -> None:
        tab = self.current_tab()
        if tab is None:
            return
        if not tab.reports:
            QMessageBox.information(self, "Exporter le rapport",
                                    "Lancez d'abord les contrôles (F5) : le rapport reprend leurs résultats.")
            return
        from fchecker.ui.report_export import export_report

        export_report(self, tab.doc, dict(tab.reports))

    # --- Affichage -------------------------------------------------------------
    def _toggle_context(self, checked: bool) -> None:
        self.settings.setValue("ui/contextVisible", checked)
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if isinstance(tab, DocumentTab):
                tab.set_context_visible(checked)

    def set_theme(self, mode: theme.ThemeMode) -> None:
        self.settings.setValue("ui/theme", mode.value)
        theme.apply(QApplication.instance(), mode)
        self.activity.refresh_theme()
        for a, name in ((self.act_open, "open"), (self.act_run, "run"), (self.act_export, "export")):
            a.setIcon(theme.icon(name))
        for a, spec in zip(self.tool_actions, self.registry.specs):
            a.setIcon(theme.icon(spec.icon))
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if isinstance(tab, DocumentTab):
                tab.refresh_theme()

    def about(self) -> None:
        QMessageBox.about(self, "À propos", about_text())

    # --- Glisser-déposer ---------------------------------------------------------
    def dragEnterEvent(self, event) -> None:
        if any(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()
            self.welcome.set_drag_active(True)

    def dragLeaveEvent(self, event) -> None:
        self.welcome.set_drag_active(False)

    def dropEvent(self, event) -> None:
        self.welcome.set_drag_active(False)
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.open_path(url.toLocalFile())
        event.acceptProposedAction()

    # --- Persistance -------------------------------------------------------------
    def _restore_geometry(self) -> None:
        if geo := self.settings.value("ui/geometry"):
            self.restoreGeometry(geo)
        if state := self.settings.value("ui/state"):
            self.restoreState(state)

    def closeEvent(self, event) -> None:
        self.settings.setValue("ui/geometry", self.saveGeometry())
        self.settings.setValue("ui/state", self.saveState())
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if isinstance(tab, DocumentTab):
                self.runner.cancel(tab)
                tab.dispose()
        super().closeEvent(event)
