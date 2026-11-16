"""Non-régression sur les exemples officiels FNFE-MPE (socle minimum de la réforme).

Tous les exemples doivent passer XSD, schematrons, PDF/A, mentions et cohérence PDF ↔ XML.
Seules exceptions : des identifiants FICTIFS présents dans les exemples eux-mêmes, que l'outil
a raison de signaler (vérifiés manuellement) :
- UC13_F202600037 : n° de TVA vendeur « FR37288100000008 » (14 chiffres au lieu de 11) ;
- BASICWL F20260023 / F20260024 : SIREN acheteur « 987654321 » (clé de Luhn fausse).
Le BIC fictif « BIC_MONCOMPTE » ne donne qu'un avertissement.
"""
from pathlib import Path

import pytest

from fchecker.core.findings import Severity
from fchecker.core.loader import load
from fchecker.core.plugin import RunContext
from fchecker.core.registry import Registry

ROOT = Path(__file__).parents[1] / "fixtures" / "france_rfe"
FILES = sorted(p for p in ROOT.rglob("*") if p.suffix.lower() in (".xml", ".pdf"))
KNOWN = {"UC13_F202600037": {"ID-TVA-CLE"}, "F20260023": {"ID-SIREN"}, "F20260024": {"ID-SIREN"}}


@pytest.fixture(scope="module")
def tools():
    reg = Registry()
    reg.discover()
    return [reg.get_tool(t) for t in ("validator", "mentions", "consistency")]


def test_examples_present():
    assert len(FILES) == 56


@pytest.mark.parametrize("path", FILES, ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}/{p.name[:40]}")
def test_official_example(tools, path):
    doc = load(path)
    errors = set()
    for tool in tools:
        if tool.accepts(doc):
            errors |= {f.rule_id for f in tool.run(doc, RunContext()).findings if f.severity <= Severity.ERROR}
    expected = next((ids for key, ids in KNOWN.items() if key in path.name), set())
    assert errors == expected
