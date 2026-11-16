"""Réglages applicatifs du noyau (sans Qt) : ``settings.json``, au même niveau que le .exe une fois packagé,
à la racine du projet en développement.

Les préférences purement visuelles (thème, géométrie des fenêtres) restent dans ``QSettings`` côté UI.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from platformdirs import user_cache_path, user_config_path

log = logging.getLogger(__name__)
APP = "fchecker"
LEGACY_APP = "factotum"  # ancien nom du logiciel
VERSION = 3
# Versions ≤ 2 : délai et cache étaient communs à l'annuaire de facturation électronique (retiré) et à Peppol.
_RENAMED = {"directory_timeout": "peppol_timeout", "directory_cache_hours": "peppol_cache_hours"}


@dataclass
class Settings:
    version: int = VERSION
    peppol_enabled: bool = True
    peppol_url: str = "https://directory.peppol.eu/search/1.0/json"
    peppol_timeout: float = 5.0
    peppol_cache_hours: float = 1.0
    smp_url: str = "https://peppol.helger.com/api"   # recherche du SMP (ppidexistence, smpquery)


_lock = threading.Lock()
_current: Settings | None = None
_path_override: Path | None = None


def app_dir() -> Path:
    """Dossier du .exe une fois packagé (PyInstaller, Nuitka), sinon racine du projet."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    if "__compiled__" in globals():
        return Path(sys.argv[0]).resolve().parent
    return Path(__file__).resolve().parents[3]


def config_path() -> Path:
    return _path_override or app_dir() / "settings.json"


def cache_dir() -> Path:
    path = user_cache_path(APP, appauthor=False)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get() -> Settings:
    global _current
    with _lock:
        if _current is None:
            _current = _load()
        return _current


def save(settings: Settings) -> None:
    global _current
    with _lock:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _write(path, settings)
        _current = settings


def use_path(path: Path | None) -> None:
    """Tests : rediriger le fichier de réglages."""
    global _path_override, _current
    with _lock:
        _path_override, _current = path, None


def _write(path: Path, settings: Settings) -> None:
    path.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False), encoding="utf-8")


def _read(path: Path) -> Settings:
    data = json.loads(path.read_text(encoding="utf-8"))
    for old, new in _RENAMED.items():
        if old in data:
            data.setdefault(new, data[old])
    known = {f.name for f in fields(Settings)}
    return Settings(**{k: v for k, v in data.items() if k in known and k != "version"})


def _migrate_legacy(path: Path) -> None:
    """Reprend les réglages de l'ancien emplacement (profil utilisateur) s'il n'y a pas encore de fichier.

    Le fichier est réécrit : les clés périmées (annuaire de facturation électronique) disparaissent."""
    if path.is_file():
        return
    for app in (APP, LEGACY_APP):
        legacy = user_config_path(app, appauthor=False) / "settings.json"
        if legacy.is_file():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                _write(path, _read(legacy))
                log.info("Réglages repris de %s", legacy)
            except (OSError, ValueError, TypeError):
                log.warning("Impossible de reprendre les réglages de %s", legacy)
            return


def _load() -> Settings:
    path = config_path()
    if _path_override is None:
        _migrate_legacy(path)
    if not path.is_file():
        return Settings()
    try:
        return _read(path)
    except Exception:
        log.warning("Réglages illisibles (%s) : valeurs par défaut utilisées", path)
        return Settings()
