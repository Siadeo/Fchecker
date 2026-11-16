from datetime import date
from decimal import Decimal

import pikepdf
import pytest

from fchecker.core.findings import Severity
from fchecker.core.loader import load
from fchecker.core.plugin import RunContext
from fchecker.core.registry import Registry
from fchecker.plugins.consistency import matchers


@pytest.fixture(scope="module")
def tool():
    reg = Registry()
    reg.discover()
    return reg.get_tool("consistency")


@pytest.fixture
def with_xml(tmp_path, facturx_path, sample_xml):
    """PDF d'exemple dont le XML embarqué est remplacé (le visuel reste inchangé)."""
    def make(transform):
        out = tmp_path / "alt.pdf"
        with pikepdf.open(facturx_path) as pdf:
            spec = pdf.attachments["factur-x.xml"]
            spec.obj.EF.F.write(transform(sample_xml).encode("utf-8"))
            pdf.save(out)
        return out
    return make


def run(tool, path):
    report = tool.run(load(path), RunContext())
    return {r["rule"]: r for r in report.meta["fields"]}, {f.rule_id: f for f in report.findings}


def test_sample_fully_consistent(tool, facturx_path):
    rows, findings = run(tool, facturx_path)
    assert findings == {}
    assert {r["status"] for r in rows.values()} <= {"trouvé", "sans objet"}


def test_total_and_number_mismatch(tool, with_xml):
    def alter(xml):
        return (xml.replace("<ram:GrandTotalAmount>12000.00", "<ram:GrandTotalAmount>12000.01")
                   .replace("<ram:ID>F202500003</ram:ID>", "<ram:ID>F202500099</ram:ID>", 1)
                   .replace('<udt:DateTimeString format="102">20250731', '<udt:DateTimeString format="102">20250801', 1))
    rows, findings = run(tool, with_xml(alter))
    assert rows["COH-06"]["status"] == "divergent" and rows["COH-06"]["pdf"] == "12 000,00"
    assert findings["COH-06"].severity is Severity.ERROR
    assert rows["COH-01"]["status"] == "absent"
    # « Date d'échéance : 31/07/2025 » sur le PDF, 01/08/2025 dans le XML
    assert rows["COH-03"]["status"] == "divergent" and rows["COH-03"]["pdf"] == "31/07/2025"
    assert findings["COH-03"].pdf_hint == "31/07/2025" and findings["COH-03"].translated
    assert rows["COH-04"]["status"] == "trouvé"


def test_scanned_pdf(tool, tmp_path, sample_xml):
    pdf = pikepdf.new()
    pdf.add_blank_page()
    pdf.attachments["factur-x.xml"] = pikepdf.AttachedFileSpec(pdf, sample_xml.encode(), filename="factur-x.xml")
    path = tmp_path / "scan.pdf"
    pdf.save(path)
    _, findings = run(tool, path)
    assert set(findings) == {"COH-10"}


def test_not_applicable_to_xml(tool, cii_file, sample_xml):
    assert not tool.accepts(load(cii_file(sample_xml)))


@pytest.mark.parametrize("text, value", [
    ("Total : 1 234,56 €", "1234.56"), ("1.234,56", "1234.56"), ("1,234.56", "1234.56"),
    ("1234.5", "1234.5"), ("TTC 1 007,33", "1007.33"), ("-12,50", "-12.50"), ("12'345.60", "12345.60"),
])
def test_amount_formats(text, value):
    assert Decimal(value) in {t.value for t in matchers.amounts(text)}


@pytest.mark.parametrize("text", ["24/09/2026", "24/09/26", "24-09-2026", "24.09.2026", "2026-09-24", "20260924",
                                  "24 septembre 2026", "24 sept. 2026", "le 24 Septembre 2026"])
def test_date_formats(text):
    assert date(2026, 9, 24) in {t.value for t in matchers.dates(text)}


def test_siren_variants():
    assert matchers.find_siren("SIRET 300 000 007 00015", "300000007")
    assert matchers.find_siren("TVA FR83300000007", "300000007")
    assert matchers.find_siren("RCS LYON 300.000.007", "300000007")
    assert not matchers.find_siren("n° 1300000007", "300000007")


def test_divergence_ignores_non_monetary_numbers():
    text = "Montant TVA\nINDEMNITE FORFAITAIRE DE 40€"
    assert matchers.labelled_values(text, "BT-110", "amount") == []
