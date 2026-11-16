"""Emplacement de settings.json et reprise des anciens réglages (profil utilisateur)."""
import json
import sys
from pathlib import Path

from fchecker.core import settings

ANCIEN = {"directory_enabled": True, "directory_url": "https://exemple.test", "check_seller_directory": True,
          "directory_timeout": 9.0, "peppol_enabled": False}


def _anciens_reglages(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "user_config_path", lambda app, appauthor=False: tmp_path / app)
    ancien = tmp_path / settings.LEGACY_APP / "settings.json"
    ancien.parent.mkdir(parents=True)
    ancien.write_text(json.dumps(ANCIEN), encoding="utf-8")
    return tmp_path / "projet" / "settings.json"


def test_project_root_in_development():
    assert settings.app_dir() == Path(__file__).parents[2]


def test_next_to_exe_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Fchecker.exe"))
    assert settings.app_dir() == tmp_path


def test_old_settings_are_cleaned(monkeypatch, tmp_path):
    nouveau = _anciens_reglages(monkeypatch, tmp_path)
    settings._migrate_legacy(nouveau)
    data = json.loads(nouveau.read_text(encoding="utf-8"))
    assert not [k for k in data if k.startswith("directory") or k == "check_seller_directory"]
    assert data["peppol_enabled"] is False and data["peppol_timeout"] == 9.0  # valeur renommée reprise
    assert data["smp_url"] == settings.Settings().smp_url


def test_fchecker_profile_wins_over_factotum(monkeypatch, tmp_path):
    nouveau = _anciens_reglages(monkeypatch, tmp_path)
    fchecker = tmp_path / settings.APP / "settings.json"
    fchecker.parent.mkdir()
    fchecker.write_text('{"peppol_timeout": 3.0}', encoding="utf-8")
    settings._migrate_legacy(nouveau)
    assert json.loads(nouveau.read_text(encoding="utf-8"))["peppol_timeout"] == 3.0


def test_existing_settings_are_not_overwritten(monkeypatch, tmp_path):
    nouveau = _anciens_reglages(monkeypatch, tmp_path)
    nouveau.parent.mkdir()
    nouveau.write_text("{}", encoding="utf-8")
    settings._migrate_legacy(nouveau)
    assert nouveau.read_text(encoding="utf-8") == "{}"
