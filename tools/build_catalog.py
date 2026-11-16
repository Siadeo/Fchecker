"""Génère ``src/fchecker/core/catalog/official.yaml`` à partir des sources officielles.

    venv\\Scripts\\python tools\\build_catalog.py      (après tools\\fetch_rules.py)

Sources :
- Artefacts de validation CEN/TC 434 EN 16931 (EUPL-1.2) : messages ANGLAIS des règles BR / BR-CO / BR-S…
  et des règles de syntaxe (CII-SR, UBL-SR…). La traduction française de la norme est protégée
  par le droit d'auteur : ne pas la reprendre, ni la feuille « Règles de la norme EN16931 » de la DGFiP qui
  en dérive.
- DGFiP spécifications externes, annexe 7, feuille « Règles de gestion » : règles G1.xx (libellé,
  thème), Licence Ouverte 2.0.
- Schematrons FNFE BR-FR (CII) : messages déjà en français, nettoyés des valeurs dynamiques.

Les textes pédagogiques et exemples de correction sont dans ``catalog/toolkit.yaml`` (manuel).
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

import openpyxl
import yaml
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from fetch_rules import DGFIP, EN16931, FNFE, download  # noqa: E402

from fchecker.core.referentiels import ANNEXE7_VERSION  # noqa: E402
from fchecker.core.rules_catalog import normalize_key  # noqa: E402

OUT = ROOT / "src" / "fchecker" / "core" / "catalog" / "official.yaml"
SCH = "http://purl.oclc.org/dsdl/schematron"
_BT = re.compile(r"\b(BT-\d+|BG-\d+)\b")


def clean(text: object) -> str:
    return " ".join(str(text or "").split())


_EN_PREFIX = re.compile(r"^\[[^\]]+\]\s*-?\s*")
_EN_SCHEMATRONS = ("cii/schematron/preprocessed/EN16931-CII-validation-preprocessed.sch",
                   "ubl/schematron/preprocessed/EN16931-UBL-validation-preprocessed.sch")


def en16931_rules_en() -> dict[str, dict]:
    """Règles EN 16931 : messages ANGLAIS des artefacts CEN/TC 434 (EUPL-1.2), CII puis UBL."""
    out: dict[str, dict] = {}
    with zipfile.ZipFile(download(EN16931)) as zf:
        for suffix in _EN_SCHEMATRONS:
            name = next(n for n in zf.namelist() if n.endswith(suffix))
            root = etree.fromstring(zf.read(name))
            for el in root.iter(f"{{{SCH}}}assert", f"{{{SCH}}}report"):
                rid = clean(el.get("id"))
                text = clean(_EN_PREFIX.sub("", clean("".join(el.itertext()))))
                if not rid or not text or normalize_key(rid) in out:
                    continue
                out[normalize_key(rid)] = {
                    "id": rid,
                    "title": text,
                    "bt": list(dict.fromkeys(_BT.findall(text))),
                    "source": f"Artefacts CEN EN 16931 {EN16931.version} (EUPL-1.2)",
                }
    return out


def g_rules(wb) -> dict[str, dict]:
    ws = wb["Règles de gestion"]
    out: dict[str, dict] = {}
    for row in ws.iter_rows(min_row=3, values_only=True):
        theme, rid, label = clean(row[0]), clean(row[1]), clean(row[2])
        if not re.match(r"^G\d+\.\d+$", rid) or not label:
            continue
        out[normalize_key(rid)] = {
            "id": rid,
            "title": theme or rid,
            "explanation": label,
            "bt": list(dict.fromkeys(_BT.findall(label))),
            "source": f"DGFiP annexe 7 v{ANNEXE7_VERSION} ({DGFIP.version})",
        }
    return out


_DYNAMIC = re.compile(r"(Valeur actuelle|Taux fourni|SIRET|SIREN|Nombre de documents trouvés)\s*:\s*\"[^\"]*\"\.?", re.I)


def br_fr_rules() -> dict[str, dict]:
    """Un texte représentatif par règle BR-FR (sans valeurs dynamiques)."""
    archive = download(FNFE)
    with zipfile.ZipFile(archive) as zf:
        name = next(n for n in zf.namelist() if n.endswith("CII/EN16931/schematron/BR-FR-Flux2-Schematron-CII.sch"))
        root = etree.fromstring(zf.read(name))
    out: dict[str, dict] = {}
    for el in root.iter(f"{{{SCH}}}assert", f"{{{SCH}}}report"):
        raw = el.get("id") or ""
        m = re.match(r"(BR-FR-(?:[A-Z]+-)?\d+)", raw)
        if not m:
            continue
        text = clean("".join(el.itertext()))
        text = re.sub(r"^\[?BR-FR[\w/\- ]*?\]?\s*:\s*", "", text)   # préfixe « BR-FR-05/BT-22 : »
        text = clean(_DYNAMIC.sub("", text))
        key = normalize_key(m.group(1))
        entry = out.setdefault(key, {
            "id": m.group(1), "title": text, "bt": [], "variants": [],
            "source": f"Schematron FNFE BR-FR {FNFE.version}",
        })
        entry["bt"] = list(dict.fromkeys(entry["bt"] + _BT.findall(raw + " " + text)))
        if text != entry["title"] and text not in entry["variants"] and len(entry["variants"]) < 6:
            entry["variants"].append(text)
    for entry in out.values():
        if not entry["variants"]:
            del entry["variants"]
    return out


def main() -> None:
    with zipfile.ZipFile(download(DGFIP)) as zf:
        name = next(n for n in zf.namelist() if "Annexe 7" in n)
        wb = openpyxl.load_workbook(io.BytesIO(zf.read(name)), read_only=True, data_only=True)
    catalog: dict[str, dict] = {}
    for part in (en16931_rules_en(), g_rules(wb), br_fr_rules()):
        catalog.update(part)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    header = ("# Généré par tools/build_catalog.py — NE PAS MODIFIER À LA MAIN.\n"
              "# Compléments pédagogiques et exemples : catalog/toolkit.yaml\n")
    OUT.write_text(header + yaml.safe_dump(dict(sorted(catalog.items())), allow_unicode=True,
                                           sort_keys=False, width=120), encoding="utf-8", newline="\n")
    print(f"{len(catalog)} règles → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
