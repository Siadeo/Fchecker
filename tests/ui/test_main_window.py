import pytest

from fchecker.core.findings import Finding, Severity, Source


@pytest.fixture
def window(qtbot):
    from fchecker.app import create_window

    _app, win = create_window([])
    qtbot.addWidget(win)
    win.show()
    return win


def test_window_starts_on_welcome(window):
    assert window.pages.currentWidget() is window.welcome
    assert len(window.activity.buttons()) == 5
    assert not window.act_run.isEnabled()


def test_open_sample_invoice(window, qtbot, facturx_path):
    window.open_path(str(facturx_path))
    qtbot.waitUntil(lambda: window.tabs.count() == 1, timeout=5000)
    assert window.pages.currentWidget() is window.tabs
    assert window.status.doc_label.text() == "Factur-X · EN 16931 · PDF/A-3B"
    assert window.act_run.isEnabled()

    # Ré-ouvrir le même fichier ne crée pas de second onglet
    window.open_path(str(facturx_path))
    qtbot.wait(200)
    assert window.tabs.count() == 1


def test_switch_tools_and_run(window, qtbot, facturx_path):
    window.open_path(str(facturx_path))
    qtbot.waitUntil(lambda: window.tabs.count() == 1, timeout=5000)
    tab = window.current_tab()
    for spec in window.registry.specs:
        window.select_tool(spec.id)
        assert tab.current_tool == spec.id
    with qtbot.waitSignal(window.runner.finished, timeout=30000):
        window.run_all()
    assert window.status.time_label.text().startswith("validé en")


def test_settings_dialog_saves(qtbot):
    from fchecker.core import settings
    from fchecker.ui.settings_dialog import SettingsDialog

    before = settings.get()
    dlg = SettingsDialog()
    qtbot.addWidget(dlg)
    dlg.timeout.setValue(9)
    dlg.accept()
    assert settings.get().peppol_timeout == 9
    settings.save(before)


def test_about_text():
    from fchecker.core.referentiels import ORGANISMES
    from fchecker.ui.license_dialog import MENTION_CEN, RESPONSABILITE
    from fchecker.ui.main_window import about_text

    texte = about_text().replace("&#x27;", "'")
    licence = texte.index("Licence : Apache-2.0")
    responsabilite = texte.index(RESPONSABILITE)
    mention_cen = texte.index(MENTION_CEN)  # condition de l'accord Commission / CEN
    organismes = texte.index("Fchecker s'appuie sur les référentiels publiés par ces organismes")
    assert licence < responsabilite < mention_cen < organismes
    assert all(o in texte[organismes:] for o in ORGANISMES)
    assert "Ces organismes ne sont pas associés à cette application." in texte[organismes:]


def test_settings_dialog_lists_all_referentials(qtbot):
    from fchecker.core.referentiels import CATEGORIES, REFERENTIELS
    from fchecker.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog()
    qtbot.addWidget(dlg)
    table = dlg.referentiels
    assert table.rowCount() == len(REFERENTIELS) + len(CATEGORIES)
    noms = {table.item(row, 0).text() for row in range(table.rowCount())}
    assert {r.nom for r in REFERENTIELS} | set(CATEGORIES) == noms
    row = next(i for i in range(table.rowCount()) if table.item(i, 0).text().startswith("EN 16931-1"))
    assert table.item(row, 1).text() == "2017 + A1"


def test_dashboard_summary(window, qtbot, facturx_path):
    window.open_path(str(facturx_path))
    qtbot.waitUntil(lambda: window.tabs.count() == 1, timeout=5000)
    window.select_tool("dashboard")
    with qtbot.waitSignal(window.runner.finished, timeout=30000):
        window.run_all()
    view = window.current_tab()._views["dashboard"]
    assert "avertissement" in view.verdict.text()
    assert "0 erreur" in view._rows["validator"][1].text()


def test_rule_lookup_dialog(qtbot):
    from PySide6.QtCore import Qt

    from fchecker.ui.rule_lookup_dialog import RuleLookupDialog

    full = RuleLookupDialog()
    qtbot.addWidget(full)
    assert full.results.count() > 200  # toutes les règles dès l'ouverture
    assert full.detail.toPlainText()

    dlg = RuleLookupDialog(initial="BR-CO-15")
    qtbot.addWidget(dlg)
    assert dlg.results.count() == full.results.count()  # liste complète, règle du constat sélectionnée
    assert dlg.results.currentItem().data(Qt.ItemDataRole.UserRole)[0] == "BR-CO-15"
    assert "BT-112" in dlg.detail.toPlainText()
    dlg.search.setText("pénalités")
    qtbot.waitUntil(lambda: 0 < dlg.results.count() < full.results.count(), timeout=2000)


def test_problems_panel_filters(window, qtbot, facturx_path):
    window.open_path(str(facturx_path))
    qtbot.waitUntil(lambda: window.tabs.count() == 1, timeout=5000)
    model = window.current_tab().findings
    model.append([
        Finding("BR-CO-15", Severity.ERROR, Source.SCHEMATRON_EN, "Total TTC incohérent", bt="BT-112", line=3),
        Finding("INFO-1", Severity.INFO, Source.PEPPOL, "Annuaire injoignable"),
    ])
    proxy = window.problems.proxy
    assert proxy.rowCount() == 2
    window.problems._filters[Severity.INFO].setChecked(False)
    assert proxy.rowCount() == 1
    proxy.set_text("annuaire")
    assert proxy.rowCount() == 0
    error_filter = window.problems._filters[Severity.ERROR]
    assert error_filter.text() == "1"
    assert not error_filter.icon().isNull()
    window.current_tab().reveal(model.findings()[0])  # navigation XML sans erreur
    tab = window.current_tab()
    tab.reveal(Finding("COH-03", Severity.ERROR, Source.CONSISTENCY, "écart", pdf_hint="31/07/2025"))
    assert tab.context.tabText(tab.context.currentIndex()) == "PDF"
    qtbot.waitUntil(lambda: tab.pdf_match_count() > 0, timeout=5000)


def test_viewer_click_reveals_xml_line(window, qtbot, facturx_path):
    """Clic sur une valeur de la visionneuse → onglet XML affiché et ligne surlignée."""
    window.open_path(str(facturx_path))
    qtbot.waitUntil(lambda: window.tabs.count() == 1, timeout=5000)
    window.select_tool("viewer")
    tab = window.current_tab()
    view = tab.stack.currentWidget()
    view.xml_line_requested.emit(16)  # BT-1 de la facture de référence
    assert tab.context.tabText(tab.context.currentIndex()) == "XML"
    editor = tab._xml_view.editor
    assert editor.textCursor().block().blockNumber() + 1 == editor.display_line(16)
    assert editor._line_selection


def test_close_tab_detaches_pdf(window, qtbot, facturx_path):
    """Régression : QPdfDocument détruit après QPdfView → crash natif à la fermeture d'un onglet."""
    window.open_path(str(facturx_path))
    qtbot.waitUntil(lambda: window.tabs.count() == 1, timeout=5000)
    tab = window.current_tab()
    tab.reveal(Finding("COH-03", Severity.ERROR, Source.CONSISTENCY, "écart", pdf_hint="31/07/2025"))
    view = tab._pdf_view
    assert view is not None and view.document().parent() is tab
    with qtbot.waitSignal(tab.destroyed, timeout=2000):  # onglet réellement détruit, sans crash
        window.close_current()
        assert view.document() is None and view.searchModel() is None
    assert window.pages.currentWidget() is window.welcome
