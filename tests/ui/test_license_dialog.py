"""Acceptation de la licence avant toute utilisation."""
import pytest
from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QDialog

from fchecker.ui import license_dialog as L


@pytest.fixture(autouse=True)
def reglages_vierges(qtbot):
    QCoreApplication.setOrganizationName("Fchecker")
    QCoreApplication.setApplicationName("Fchecker")
    QSettings().remove("licence")
    yield
    QSettings().remove("licence")


def test_not_accepted_at_first_launch():
    assert not L.licence_acceptee()


def test_acceptance_is_recorded_with_date():
    L.enregistrer_acceptation()
    assert L.licence_acceptee()
    assert QSettings().value("licence/version", type=int) == L.LICENCE_VERSION
    assert QSettings().value("licence/date")


def test_asked_again_when_terms_change(monkeypatch):
    L.enregistrer_acceptation()
    monkeypatch.setattr(L, "LICENCE_VERSION", L.LICENCE_VERSION + 1)
    assert not L.licence_acceptee()


def test_accept_button_requires_the_checkbox(qtbot):
    dlg = L.LicenseDialog()
    qtbot.addWidget(dlg)
    assert not dlg.accepter.isEnabled()
    dlg.case.setChecked(True)
    assert dlg.accepter.isEnabled()
    dlg.case.setChecked(False)
    assert not dlg.accepter.isEnabled()


def test_text_contains_liability_and_as_is(qtbot):
    dlg = L.LicenseDialog()
    qtbot.addWidget(dlg)
    texte = dlg.texte.toPlainText()
    assert L.RESPONSABILITE in " ".join(texte.split())
    assert L.MENTION_CEN in " ".join(texte.split())
    assert 'distributed under the License is distributed on an "AS IS" BASIS' in texte


def test_closing_without_choice_is_a_refusal(qtbot, monkeypatch):
    monkeypatch.setattr(L.LicenseDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    assert not L.demander_licence()
    assert not L.licence_acceptee()


def test_close_button_rejects(qtbot):
    dlg = L.LicenseDialog()
    qtbot.addWidget(dlg)
    dlg.show()
    dlg.close()
    assert dlg.result() == QDialog.DialogCode.Rejected


def test_acceptance_recorded_and_not_asked_twice(qtbot, monkeypatch):
    appels = []

    def accepte(self):
        appels.append(1)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(L.LicenseDialog, "exec", accepte)
    assert L.demander_licence() and L.demander_licence()
    assert len(appels) == 1
