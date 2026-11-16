"""Contrôle des traductions maison des règles EN 16931 (``core/catalog/en16931_fr.yaml``).

    venv\\Scripts\\python tools\\check_translations.py     (après tools\\build_catalog.py)

1. Couverture : chaque règle sémantique (BR-…) des artefacts CEN a sa traduction.
2. Fraîcheur : ``en_sha`` correspond au message anglais actuel (sinon, l'anglais a changé : retraduire).
3. Règles de syntaxe : part traduite par motif ou par le fichier, liste des règles restantes.
4. Non-recopie : aucune séquence de 7 mots (hors numéros BT/BG) commune avec les libellés français de
   l'annexe 7 DGFiP, qui dérivent de la version française de la norme (protégée). Nécessite le cache de
   ``tools/fetch_rules.py`` ; ignoré sinon.

Code de sortie 1 si un contrôle échoue.
"""
from __future__ import annotations

import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from fetch_rules import CACHE, DGFIP  # noqa: E402

from fchecker.core.rules_catalog import normalize_key, translate_pattern  # noqa: E402

CATALOG = ROOT / "src" / "fchecker" / "core" / "catalog"
NGRAM = 7


def en_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def words(text: str) -> list[str]:
    """Mots en minuscules, sans les numéros de BT/BG (des faits, pas du texte)."""
    return [w for w in re.findall(r"[\wÀ-ÿ'’]+", text.lower()) if not re.fullmatch(r"b[tg]|\d+", w)]


def grams(text: str) -> set[str]:
    w = words(text)
    return {" ".join(w[i:i + NGRAM]) for i in range(len(w) - NGRAM + 1)}


def annex_french_grams() -> set[str] | None:
    archive = CACHE / DGFIP.filename
    if not archive.is_file():
        return None
    import openpyxl

    with zipfile.ZipFile(archive) as zf:
        name = next(n for n in zf.namelist() if "Annexe 7" in n)
        wb = openpyxl.load_workbook(io.BytesIO(zf.read(name)), read_only=True, data_only=True)
    out: set[str] = set()
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for cell in row:
                if isinstance(cell, str) and len(re.findall(r"\b(?:le|la|les|doit|doivent|du|une|des|de)\b",
                                                            cell.lower())) >= 2:
                    out |= grams(cell)
    return out


def main() -> int:
    official = {normalize_key(k): v for k, v in
                yaml.safe_load((CATALOG / "official.yaml").read_text(encoding="utf-8")).items()}
    french = yaml.safe_load((CATALOG / "en16931_fr.yaml").read_text(encoding="utf-8"))["rules"]
    french = {normalize_key(k): v for k, v in french.items()}
    cen = {k: v for k, v in official.items() if "CEN" in str(v.get("source"))}
    failed = False

    semantic = sorted(k for k in cen if k.startswith("BR"))
    missing = [k for k in semantic if k not in french]
    stale = [k for k, v in french.items() if k in cen and v.get("en_sha") != en_sha(cen[k]["title"])]
    orphans = sorted(k for k in french if k not in cen)
    print(f"Règles sémantiques : {len(semantic) - len(missing)}/{len(semantic)} traduites")
    for label, keys in (("non traduites", missing), ("anglais modifié (retraduire)", stale),
                        ("absentes des artefacts CEN", orphans)):
        if keys:
            failed = True
            print(f"  {label} : {', '.join(keys)}")

    syntax = sorted(k for k in cen if not k.startswith("BR"))
    rest = [k for k in syntax if k not in french and not translate_pattern(cen[k]["title"])]
    print(f"Règles de syntaxe : {len(syntax) - len(rest)}/{len(syntax)} traduites (motifs ou fichier)")
    for k in rest:
        print(f"  à traduire : {k} — {cen[k]['title']}")
    failed |= bool(rest)

    annex = annex_french_grams()
    if annex is None:
        print("Non-recopie : cache DGFiP absent (tools/fetch_rules.py), contrôle ignoré")
    else:
        hits = {k: grams(v["title"]) & annex for k, v in french.items()}
        hits = {k: h for k, h in hits.items() if h}
        print(f"Non-recopie : {len(hits)} traduction(s) avec une séquence de {NGRAM} mots commune avec l'annexe 7")
        for k, h in sorted(hits.items()):
            print(f"  {k} : {' | '.join(sorted(h))}")
        failed |= bool(hits)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
