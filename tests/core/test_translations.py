"""Traductions maison des règles EN 16931 (en16931_fr.yaml) : couverture, fraîcheur, non-recopie."""
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import check_translations as ct  # noqa: E402


@pytest.fixture(scope="module")
def data():
    import yaml

    from fchecker.core.rules_catalog import normalize_key

    official = {normalize_key(k): v for k, v in
                yaml.safe_load((ct.CATALOG / "official.yaml").read_text(encoding="utf-8")).items()}
    french = yaml.safe_load((ct.CATALOG / "en16931_fr.yaml").read_text(encoding="utf-8"))
    rules = {normalize_key(k): v for k, v in french["rules"].items()}
    cen = {k: v for k, v in official.items() if "CEN" in str(v.get("source"))}
    return cen, rules, french["glossary"]


def test_every_semantic_rule_is_translated(data):
    cen, rules, _ = data
    assert sorted(k for k in cen if k.startswith("BR") and k not in rules) == []


def test_translations_match_current_english(data):
    cen, rules, _ = data
    stale = [k for k, v in rules.items() if v["en_sha"] != ct.en_sha(cen[k]["title"])]
    assert stale == [], "message anglais modifié : retraduire puis mettre à jour en_sha"


def test_every_syntax_rule_is_translated(data):
    from fchecker.core.rules_catalog import translate_pattern

    cen, rules, _ = data
    rest = [k for k in cen if not k.startswith("BR") and k not in rules and not translate_pattern(cen[k]["title"])]
    assert rest == []


def test_glossary_covers_cited_terms(data):
    import re

    _, rules, glossary = data
    cited = {bt for v in rules.values() for bt in re.findall(r"\b(B[TG]-\d+)\b", v["title"])}
    assert cited - set(glossary) == set()


def test_no_sequence_copied_from_dgfip_annex(data):
    annex = ct.annex_french_grams()
    if annex is None:
        pytest.skip("cache DGFiP absent (tools/fetch_rules.py)")
    _, rules, _ = data
    assert {k: ct.grams(v["title"]) & annex for k, v in rules.items() if ct.grams(v["title"]) & annex} == {}
