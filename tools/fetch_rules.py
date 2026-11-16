"""Télécharge et embarque les packs de règles officiels (script de développement).

    venv\\Scripts\\python tools\\fetch_rules.py

- FNFE-MPE « Schematrons FR CTC » : XSD + XSLT précompilées (EN 16931, BR-FR, EXTENDED-CTC-FR,
  Factur-X) → src/fchecker/resources/rules/fnfe/
- ConnectingEurope EN 16931 : exemples officiels CII / UBL → tests/fixtures/en16931/
- DGFiP spécifications externes : annexes (catalogue de traduction) → tools/.cache/ (non embarqué)

Chaque archive est vérifiée par SHA-256 : une nouvelle version impose de mettre à jour SOURCES.
"""
from __future__ import annotations

import hashlib
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fchecker.core.referentiels import (  # noqa: E402
    CEN_VERSION,
    DGFIP_VERSION,
    FACTURX_DOSSIER,
    FNFE_VERSION,
)

CACHE = ROOT / "tools" / ".cache"
RULES_DIR = ROOT / "src" / "fchecker" / "resources" / "rules"
FIXTURES = ROOT / "tests" / "fixtures"


@dataclass(frozen=True)
class Source:
    id: str
    version: str
    url: str
    sha256: str
    filename: str


FNFE = Source(
    id="fnfe",
    version=FNFE_VERSION,
    url="https://fnfe-mpe.org/wp-content/uploads/2026/09/2026_09_04_FNFE_SCHEMATRONS_FR_CTC_V1.4.0.04.zip",
    sha256="9fddfbbb081ec969374dcefd24615fb1d736fdd974155890fc24a413afd0c01e",
    filename=f"fnfe_fr_ctc_{FNFE_VERSION}.zip",
)
EN16931 = Source(
    id="en16931",
    version=CEN_VERSION,
    url="https://github.com/ConnectingEurope/eInvoicing-EN16931/archive/refs/tags/validation-1.3.16.zip",
    sha256="161c136b7edbeeaa1f1397ee67da017c85062fb52b315ea63a681606a8bb666b",
    filename=f"en16931_validation_{CEN_VERSION}.zip",
)
DGFIP = Source(
    id="dgfip",
    version=DGFIP_VERSION,
    url=("https://www.impots.gouv.fr/sites/default/files/media/1_metier/2_professionnel/EV/2_gestion/"
         "290_facturation_electronique/specification_externes_b2b/specifications-externes-v3.2.zip"),
    sha256="cd8f6e817e37f329e6f62a35aa131b78a51379bec953445b774fa8adbaaa3862",
    filename=f"dgfip_specifications_externes_{DGFIP_VERSION}.zip",
)

# Sous-arborescences du pack FNFE à embarquer (chemins relatifs à la racine de l'archive).
FNFE_KEEP = (
    "CII/1xsd-CII_D22B_uncoupled/",
    "CII/EN16931/2xslt/EN16931-CII-validation.xslt",
    "CII/EN16931/2xslt/BR-FR-Flux2-Schematron-CII.xslt",
    "CII/EXTENDED-CTC-FR/2xslt/EXTENDED-CTC-FR-CII.xslt",
    f"{FACTURX_DOSSIER}/BASICWL/1xsd/",
    f"{FACTURX_DOSSIER}/BASICWL/2xslt/FACTUR-X_BASIC-WL",
    f"{FACTURX_DOSSIER}/EN16931/1xsd/",
    f"{FACTURX_DOSSIER}/EN16931/2xslt/FACTUR-X_EN16931",
    f"{FACTURX_DOSSIER}/EXTENDED/1xsd/",
    f"{FACTURX_DOSSIER}/EXTENDED/2xslt/FACTUR-X_EXTENDED",
    "UBL/1xsd_UBL2.1/common/",
    "UBL/1xsd_UBL2.1/maindoc/UBL-Invoice-2.1.xsd",
    "UBL/1xsd_UBL2.1/maindoc/UBL-CreditNote-2.1.xsd",
    "UBL/EN16931/2xslt/EN16931-UBL-validation.xslt",
    "UBL/EN16931/2xslt/BR-FR-Flux2-Schematron-UBL.xslt",
    "UBL/EXTENDED-CTC-FR/2xslt/EXTENDED-CTC-FR-UBL.xslt",
)

EN_EXAMPLES = ("cii/examples/", "ubl/examples/")


def download(src: Source) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / src.filename
    if not dest.exists():
        print(f"Téléchargement {src.id} {src.version}…")
        with httpx.Client(follow_redirects=True, timeout=180, headers={"User-Agent": "fchecker"}) as client:
            r = client.get(src.url)
            r.raise_for_status()
            dest.write_bytes(r.content)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    if digest != src.sha256:
        dest.unlink()
        sys.exit(f"SHA-256 inattendu pour {src.id} : {digest} (attendu {src.sha256}). Mettre à jour SOURCES.")
    return dest


def _members(zf: zipfile.ZipFile) -> list[tuple[str, zipfile.ZipInfo]]:
    """(chemin relatif sans le dossier racine, info), hors métadonnées macOS."""
    out = []
    for info in zf.infolist():
        name = info.filename
        if info.is_dir() or "__MACOSX" in name or name.endswith(".DS_Store"):
            continue
        out.append((name.split("/", 1)[1] if "/" in name else name, info))
    return out


def _lf(data: bytes) -> bytes:
    """Fins de ligne LF, imposées par .gitattributes (les archives contiennent du CRLF)."""
    return data.replace(b"\r\n", b"\n")


def install_fnfe() -> None:
    archive = download(FNFE)
    target = RULES_DIR / FNFE.id
    if target.exists():
        shutil.rmtree(target)
    count = 0
    with zipfile.ZipFile(archive) as zf:
        for rel, info in _members(zf):
            if not rel.startswith(FNFE_KEEP):
                continue
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(_lf(zf.read(info)))
            count += 1
    manifest = {
        "id": FNFE.id,
        "version": FNFE.version,
        "source": FNFE.url,
        "sha256": FNFE.sha256,
    }
    (target / "pack.yaml").write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
                                      encoding="utf-8", newline="\n")
    print(f"FNFE {FNFE.version} : {count} fichiers → {target.relative_to(ROOT)}")


def install_en_examples() -> None:
    archive = download(EN16931)
    target = FIXTURES / "en16931"
    if target.exists():
        shutil.rmtree(target)
    count = 0
    with zipfile.ZipFile(archive) as zf:
        for rel, info in _members(zf):
            if rel.startswith(EN_EXAMPLES) and rel.endswith(".xml"):
                out = target / rel.split("/", 1)[0] / Path(rel).name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(_lf(zf.read(info)))
                count += 1
    print(f"Exemples EN 16931 {EN16931.version} : {count} fichiers → {target.relative_to(ROOT)}")


def main() -> None:
    install_fnfe()
    install_en_examples()
    download(DGFIP)
    print(f"DGFiP {DGFIP.version} en cache → {CACHE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
