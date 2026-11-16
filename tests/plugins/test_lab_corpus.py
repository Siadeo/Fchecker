"""Non-régression sur le corpus ezfacture Lab (`tests/fixtures/lab/`, voir SOURCE.txt) : XML CII et Factur-X.

Chaque cas du manifeste déclare l'intention de Lab : les règles qui doivent être levées (`must`),
celles qui sont tolérées (`may`) et la gravité maximale de tout autre constat (`max_severity`).
Les factures valides de la matrice (`must: []`, `max_severity: info`) vérifient l'absence de faux
positifs ; les factures pièges, la détection de la règle visée.
"""
from pathlib import Path

import pytest
import yaml

from fchecker.core.findings import Severity
from fchecker.core.loader import load
from fchecker.core.plugin import RunContext
from fchecker.core.registry import Registry

ROOT = Path(__file__).parents[1] / "fixtures" / "lab"
MANIFEST = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
CASES = MANIFEST["cases"]


@pytest.fixture(scope="module")
def tools():
    reg = Registry()
    reg.discover()
    return [reg.get_tool(t) for t in ("validator", "mentions", "consistency")]


def test_manifest():
    assert MANIFEST["lab_version"] == 1
    assert sum(c["level"] == "valid" for c in CASES) >= 20
    assert sum(c["level"] != "valid" for c in CASES) >= 10
    assert len({c["id"] for c in CASES}) == len(CASES)
    # Factur-X rendus par Excel : valides (facturx/) et pièges de niveau C (cohérence PDF/XML, PDF/A)
    assert any(c.get("format") == "facturx" and c["level"] == "valid" for c in CASES)
    assert any(c["level"] == "C" for c in CASES)
    # aucun fichier orphelin : tout ce qui est dans cii/, traps/ et facturx/ est décrit par le manifeste
    files = {p.relative_to(ROOT).as_posix() for d in ("cii", "traps", "facturx")
             for p in (ROOT / d).glob("*") if p.suffix in (".xml", ".pdf")}
    assert files == {c["file"] for c in CASES}


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_lab_case(tools, case):
    doc = load(ROOT / case["file"])
    findings = []
    for tool in tools:
        if tool.accepts(doc):
            findings += tool.run(doc, RunContext()).findings
    found = {f.rule_id for f in findings}
    expect = case["expect"]
    tolerated = Severity[expect["max_severity"].upper()]

    missing = set(expect["must"]) - found
    unexpected = sorted(f"{f.rule_id} ({f.severity.name})" for f in findings
                        if f.rule_id not in expect["must"] and f.rule_id not in expect["may"]
                        and f.severity < tolerated)
    assert not missing, f"règles attendues absentes : {sorted(missing)}"
    assert not unexpected, f"constats plus graves que {expect['max_severity']} : {unexpected}"
