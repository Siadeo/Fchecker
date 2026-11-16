"""Couverture du catalogue de traduction sur l'ensemble des règles embarquées."""
from pathlib import Path

import yaml
from lxml import etree

from fchecker.core.findings import Finding, Severity, Source
from fchecker.core.rulepacks import get_pack
from fchecker.core.rules_catalog import catalog, candidate_keys
from fchecker.core.schematron import normalize_rule_id

SVRL = "http://purl.oclc.org/dsdl/svrl"
TOOLKIT = Path(__file__).parents[2] / "src" / "fchecker" / "core" / "catalog" / "toolkit.yaml"


def all_rules():
    for xslt in get_pack("fnfe").root.rglob("*.xslt"):
        source = Source.SCHEMATRON_FR if "BR-FR" in xslt.name else Source.SCHEMATRON_EN
        for el in etree.parse(str(xslt)).iter(f"{{{SVRL}}}failed-assert", f"{{{SVRL}}}successful-report"):
            node = el.find(f"{{{SVRL}}}text")
            text = " ".join("".join(node.itertext()).split()) if node is not None else ""
            yield normalize_rule_id(el.get("id"), text), source, text


def test_at_least_98_percent_translated():
    cat = catalog()
    rules = list(all_rules())
    translated = sum(cat.enrich(Finding(r, Severity.ERROR, s, t)).translated for r, s, t in rules)
    assert len(rules) > 5000
    assert translated / len(rules) >= 0.98, f"{translated}/{len(rules)}"


def test_every_toolkit_rule_documented():
    """Chaque règle propre à l'outil a une fiche rédigée (explication)."""
    manual = yaml.safe_load(TOOLKIT.read_text(encoding="utf-8"))
    own_prefixes = ("FR-PROFIL-", "PACK-", "XSD", "SCH-", "ID-", "PEP-", "PDFA-")
    own = [k for k in manual if k.startswith(own_prefixes)]
    assert all(manual[k].get("explanation") or manual[k].get("title") for k in own)


def test_variant_resolution():
    assert "BR-AE-8" in candidate_keys("BR-FXEXT-AE-08b")
    assert "BR-23" in candidate_keys("BR-FXEXT-BR-23")
    assert "BR-54" in candidate_keys("BR-54-1")
    f = catalog().enrich(Finding("BR-FREXT-AE-08rev", Severity.WARNING, Source.SCHEMATRON_EN, "[BR-FREXT-AE-08rev] - x"))
    assert f.translated and "Variante de la règle" in f.explanation
