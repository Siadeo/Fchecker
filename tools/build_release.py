"""Construction de la release Windows portable : ``dist/Fchecker-<version>-win64.zip``.

    venv\\Scripts\\python -m pip install -e .[release]     (une fois)
    venv\\Scripts\\python tools\\build_release.py --tests

1. (``--tests``) lance la suite de tests et s'arrête si elle échoue ;
2. gèle l'application avec PyInstaller (``packaging/fchecker.spec``, mode dossier) ;
3. ajoute LICENSE, LICENSE.md, NOTICE (obligations Apache / EUPL / mention CEN) et LISEZMOI.txt ;
4. contrôle le contenu (packs officiels, catalogues, QtWebEngine, saxonche ; ni réglages ni facture) ;
5. lance l'auto-test de l'exécutable gelé (``--self-test``) sur la facture de référence des tests ;
6. zippe le dossier et affiche la taille et le SHA-256 de l'archive.

Options : ``--console`` (exécutable avec console, pour diagnostiquer un démarrage raté),
``--force`` (construire malgré des modifications non commitées).
Code de sortie 1 si une étape échoue.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "fchecker.spec"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
APP = DIST / "Fchecker"
LICENCES = ("LICENSE", "LICENSE.md", "NOTICE")
REFERENCE = ROOT / "tests" / "fixtures" / "france_rfe" / "FX" / "EN16931" / "UC1_F202500003_00-INV_20250701_EN16931_FX.pdf"

LISEZMOI = """\
Fchecker {version} - contrôle de factures électroniques (Factur-X, CII, UBL)
==========================================================================

Lancement : double-cliquer sur Fchecker.exe. Aucune installation ni Python requis (Windows 10/11, 64 bits).

- Décompresser l'archive dans un dossier où vous avez le droit d'écrire (Documents, Bureau...) :
  les réglages sont enregistrés dans settings.json, à côté de Fchecker.exe.
- Tous les contrôles fonctionnent hors ligne, sauf l'annuaire Peppol (désactivable dans les Paramètres).
- Une facture peut être passée en argument : Fchecker.exe facture.pdf

Licence : Apache 2.0 (LICENSE). Composants et référentiels tiers : LICENSE.md et NOTICE.
"""


def fail(message: str) -> None:
    print(f"ÉCHEC : {message}", file=sys.stderr)
    raise SystemExit(1)


def read_version() -> str:
    text = (ROOT / "src" / "fchecker" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M)
    if not match:
        fail("__version__ introuvable dans src/fchecker/__init__.py")
    return match.group(1)


def check_git_clean(force: bool) -> None:
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        print("Avertissement : état git inconnu.")
        return
    if out.strip():
        if not force:
            fail("modifications non commitées (relancer avec --force pour construire quand même)")
        print("Avertissement : modifications non commitées, la release ne correspond à aucun commit.")


def run_tests() -> None:
    print("== Tests")
    if subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT).returncode:
        fail("tests en échec")


def write_version_file(version: str) -> Path:
    """Ressource de version Windows (propriétés du .exe), au format VSVersionInfo de PyInstaller."""
    nums = [int(n) for n in re.findall(r"\d+", version)[:4]]
    nums += [0] * (4 - len(nums))
    tup = tuple(nums)
    path = BUILD / "version_info.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    strings = {
        "CompanyName": "Fchecker",
        "FileDescription": "Fchecker - contrôle de factures électroniques",
        "FileVersion": version,
        "InternalName": "Fchecker",
        "LegalCopyright": "Licence Apache 2.0",
        "OriginalFilename": "Fchecker.exe",
        "ProductName": "Fchecker",
        "ProductVersion": version,
    }
    entries = ",\n          ".join(f"StringStruct({k!r}, {v!r})" for k, v in strings.items())
    path.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tup}, prodvers={tup}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040C04B0', [
          {entries}])]),
    VarFileInfo([VarStruct('Translation', [0x040C, 1200])])
  ]
)
""", encoding="utf-8")
    return path


def freeze(version_file: Path, console: bool) -> None:
    print("== PyInstaller")
    env = dict(os.environ, FCHECKER_VERSION_FILE=str(version_file))
    if console:
        env["FCHECKER_CONSOLE"] = "1"
    cmd = [sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm", "--clean",
           "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller")]
    if subprocess.run(cmd, cwd=ROOT, env=env).returncode:
        fail("PyInstaller")


def add_documents(version: str) -> None:
    for name in LICENCES:
        shutil.copy2(ROOT / name, APP / name)
    (APP / "LISEZMOI.txt").write_text(LISEZMOI.format(version=version), encoding="utf-8-sig")


def check_content() -> None:
    print("== Contrôle du contenu")
    internal = APP / "_internal"
    expected = {
        "exécutable": APP / "Fchecker.exe",
        "packs officiels": internal / "fchecker" / "resources" / "rules",
        "catalogue officiel": internal / "fchecker" / "core" / "catalog" / "official.yaml",
        "traductions EN 16931": internal / "fchecker" / "core" / "catalog" / "en16931_fr.yaml",
        "règles des mentions": internal / "fchecker" / "plugins" / "mentions" / "rules.yaml",
        "thème": internal / "fchecker" / "ui" / "theme" / "app.qss.tmpl",
        **{name: APP / name for name in LICENCES},
    }
    missing = [label for label, path in expected.items() if not path.exists()]
    for label, pattern in (("saxonche", "saxonche*.pyd"), ("DLL Saxon", "saxonc-core-he*.dll")):
        if not any(internal.glob(pattern)):
            missing.append(label)
    if not any(internal.rglob("QtWebEngineProcess.exe")):
        missing.append("QtWebEngineProcess.exe")
    if not any((internal / "fchecker" / "resources" / "rules").rglob("*.xslt")):
        missing.append("schematrons compilés (.xslt)")
    if missing:
        fail("absent de la distribution : " + ", ".join(missing))
    forbidden = [p for p in APP.rglob("*") if p.name == "settings.json" or p.name.startswith("Facture_")]
    if forbidden:
        fail("fichiers à ne pas distribuer : " + ", ".join(str(p.relative_to(APP)) for p in forbidden))


def self_test() -> None:
    """Exécute l'exécutable gelé sans interface : plugins, packs embarqués et processus Saxon (spawn)."""
    print("== Auto-test de l'exécutable")
    try:
        code = subprocess.run([str(APP / "Fchecker.exe"), "--self-test", str(REFERENCE)],
                              cwd=DIST, timeout=600).returncode
    except subprocess.TimeoutExpired:
        fail("auto-test : délai dépassé")
    if code:
        fail(f"auto-test : code {code} (relancer avec --console pour voir le détail)")
    if (APP / "settings.json").exists():
        fail("l'auto-test a créé settings.json dans la distribution")
    print("Auto-test réussi.")


def make_zip(version: str) -> Path:
    archive = DIST / f"Fchecker-{version}-win64.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(APP.rglob("*")):
            if path.is_file():
                zf.write(path, Path("Fchecker") / path.relative_to(APP))
    return archive


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tests", action="store_true", help="lancer les tests avant le build")
    parser.add_argument("--console", action="store_true", help="exécutable avec console (diagnostic)")
    parser.add_argument("--force", action="store_true", help="ignorer les modifications non commitées")
    args = parser.parse_args()

    version = read_version()
    print(f"Fchecker {version}")
    check_git_clean(args.force)
    if args.tests:
        run_tests()
    freeze(write_version_file(version), args.console)
    add_documents(version)
    check_content()
    self_test()
    archive = make_zip(version)
    print(f"\nArchive : {archive}")
    print(f"Taille  : {archive.stat().st_size / 1e6:.1f} Mo")
    print(f"SHA-256 : {sha256(archive)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
