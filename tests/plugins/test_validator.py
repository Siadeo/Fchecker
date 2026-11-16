import dataclasses
from pathlib import Path

import pytest
from conftest import corrupt

from fchecker.core.findings import Severity, Source
from fchecker.core.loader import load
from fchecker.core.plugin import RunContext
from fchecker.core.registry import Registry

EXAMPLES = Path(__file__).parents[1] / "fixtures" / "en16931"


@pytest.fixture(scope="module")
def validator():
    reg = Registry()
    reg.discover()
    return reg.get_tool("validator")


def run(validator, doc):
    return validator.run(doc, RunContext())


def blocking(report):
    return [f for f in report.findings if f.severity <= Severity.ERROR]


def test_sample_invoice_is_valid(validator, facturx_path):
    report = run(validator, load(facturx_path))
    assert blocking(report) == []
    assert [c["id"] for c in report.meta["checks"]][:3] == ["profile", "xsd", "schematron"]
    assert "Schematrons FNFE (EN 16931, BR-FR, Factur-X)" in report.rule_packs


def test_corrupted_invoice(validator, sample_xml, cii_file):
    doc = load(cii_file(corrupt(sample_xml, total=True, pmt=True, structure=True)))
    report = run(validator, doc)
    ids = {f.rule_id for f in blocking(report)}
    assert {"XSD", "BR-CO-15", "BR-FR-05"} <= ids
    xsd = next(f for f in report.findings if f.rule_id == "XSD")
    assert xsd.line and "ram:Bidon" in xsd.title
    assert all(f.translated for f in report.findings)
    br15 = next(f for f in report.findings if f.rule_id == "BR-CO-15")
    assert br15.line is not None and br15.bt.startswith("BT-112")
    assert br15.title.startswith("Total TTC de la facture (BT-112)")  # traduction maison (en16931_fr.yaml)


def test_utf8_bom_is_accepted(validator, sample_xml, tmp_path):
    """Les exemples officiels France_RFE commencent par un BOM UTF-8 : les schematrons doivent s'exécuter."""
    path = tmp_path / "bom.xml"
    path.write_bytes(b"\xef\xbb\xbf" + sample_xml.lstrip("﻿").encode("utf-8"))
    report = run(validator, load(path))
    assert not [f for f in report.findings if f.rule_id == "SCH-ERROR"]
    assert blocking(report) == []


def test_technical_failure_is_blocking(validator, facturx_path, monkeypatch):
    """Un schematron non exécuté ne doit jamais laisser croire que la facture est conforme."""
    from fchecker.core.schematron import SchematronEngine

    def boom(*_a, **_k):
        raise RuntimeError("panne simulée")

    monkeypatch.setattr(SchematronEngine, "validate", boom)
    report = run(validator, load(facturx_path))
    assert any(f.rule_id == "SCH-ERROR" and f.severity is Severity.ERROR for f in report.findings)


def test_profile_rules(validator, sample_xml, cii_file, facturx_path):
    minimum = load(cii_file(sample_xml.replace("urn:cen.eu:en16931:2017", "urn:factur-x.eu:1p0:minimum")))
    assert "FR-PROFIL-01" in {f.rule_id for f in run(validator, minimum).findings}

    doc = load(facturx_path)
    doc.pdf_info = dataclasses.replace(doc.pdf_info, fx_conformance_level="BASIC")
    assert "FR-PROFIL-02" in {f.rule_id for f in blocking(run(validator, doc))}


@pytest.mark.parametrize("urn, attendu", [("urn:factur-x.eu:1p0:minimum", "Générer la facture"),
                                          ("urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic",
                                           "BT-24 = urn:cen.eu:en16931:2017")])
def test_rejected_profiles_have_their_own_correction(validator, sample_xml, cii_file, urn, attendu):
    doc = load(cii_file(sample_xml.replace("urn:cen.eu:en16931:2017", urn, 1)))
    f = next(f for f in run(validator, doc).findings if f.rule_id == "FR-PROFIL-01")
    assert f.severity is Severity.ERROR and attendu in f.suggestion
    assert "rejettera" not in f.explanation and "sous-ensemble" in f.explanation


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*/*.xml")), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_official_examples_structure(validator, path):
    """Les exemples officiels EN 16931 doivent passer le XSD et le schematron EN 16931
    (ils ne sont pas conformes aux règles FR, ce qui est attendu)."""
    report = run(validator, load(path))
    en_errors = [f for f in blocking(report) if f.source in (Source.XSD, Source.SCHEMATRON_EN)]
    assert en_errors == [], [(f.rule_id, f.display_message) for f in en_errors[:5]]
