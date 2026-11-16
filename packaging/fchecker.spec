# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller de Fchecker (mode dossier « onedir », distribué en ZIP portable).

Ne pas lancer directement : passer par ``venv\\Scripts\\python tools\\build_release.py``, qui génère le
fichier de version Windows, ajoute les licences et produit le ZIP.

- ``collect_submodules("fchecker")`` : les outils (``plugins/``) et les sous-contrôles du validateur
  (``plugins/validator/checks/``) sont découverts par ``pkgutil.iter_modules`` puis importés
  dynamiquement ; l'analyse statique ne les voit pas. Un nouveau plugin est embarqué sans toucher au spec.
- ``collect_data_files("fchecker")`` : packs officiels, catalogues YAML, gabarits, icônes. Ils restent de
  vrais fichiers sur disque (``core/rulepacks.py`` les adresse par chemin).
- saxonche (module natif unique, DLL Saxon à côté) est trouvé par l'analyse des imports de
  ``core/saxon_worker.py`` ; il n'est importé que dans le processus Saxon (multiprocessing spawn,
  ``freeze_support()`` dans ``main.py``).
- Rien n'est collecté depuis la racine du dépôt : ni ``settings.json`` de développement, ni facture.
"""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
CONSOLE = os.environ.get("FCHECKER_CONSOLE") == "1"
VERSION_FILE = os.environ.get("FCHECKER_VERSION_FILE")
ICON = ROOT / "packaging" / "fchecker.ico"

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(SRC)],
    datas=collect_data_files("fchecker"),
    hiddenimports=collect_submodules("fchecker"),
    excludes=["tkinter", "pytest", "pytestqt", "openpyxl", "pypdfium2"],
    noarchive=False,
)


def _unused(dest: str) -> bool:
    """Fichiers Qt inutiles à Fchecker (~150 Mo) : DevTools de QtWebEngine, traductions autres que le
    français, modules QML (l'interface est en widgets ; QtWebEngine n'en a pas besoin).
    L'auto-test de build_release.py (impression PDF QtWebEngine) vérifie que rien d'utile n'est retiré."""
    d = dest.replace("\\", "/")
    name = d.rsplit("/", 1)[-1]
    if d.startswith("PySide6/resources/qtwebengine_devtools_resources"):
        return True
    if d.startswith("PySide6/translations/"):
        if "/qtwebengine_locales/" in d:
            return name not in ("fr.pak", "en-US.pak")
        return not name.endswith("_fr.qm")
    if d.startswith("PySide6/qml/"):
        return True
    return any(part in name for part in (
        "Quick3D", "QuickControls2", "QuickTemplates2", "QuickDialogs2", "QuickParticles", "QuickTimeline",
        "QuickEffects", "QuickShapes", "QuickVectorImage", "ShaderTools", "Qt6Labs", "Qt6Graphs",
    ))


a.datas = [entry for entry in a.datas if not _unused(entry[0])]
a.binaries = [entry for entry in a.binaries if not _unused(entry[0])]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Fchecker",
    console=CONSOLE,
    upx=False,
    version=VERSION_FILE if VERSION_FILE and Path(VERSION_FILE).is_file() else None,
    icon=str(ICON) if ICON.is_file() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Fchecker", upx=False)
