import pytest

from fchecker.core import ids
from fchecker.core.loader import load


@pytest.mark.parametrize("value, ok", [
    ("123456782", True),
    ("123 456 782", True),
    ("123456789", False),
    ("12345678", False),
    ("12345678A", False),
])
def test_siren(value, ok):
    assert ids.is_valid_siren(value) is ok


def test_siret():
    assert ids.is_valid_siret("12345678200007") is ids.luhn_valid("12345678200007")
    assert not ids.is_valid_siret("1234567820000")


def test_fr_vat_key():
    # 123456782 mod 97 = 32 → (12 + 96) mod 97 = 11
    assert ids.fr_vat_key("123456782") == "11"
    assert ids.fr_vat_from_siren("123456782") == "FR11123456782"
    assert ids.is_valid_fr_vat("FR 11 123456782")
    assert not ids.is_valid_fr_vat("FR12123456782")
    assert ids.siren_from_fr_vat("FR11123456782") == "123456782"


@pytest.mark.parametrize("value, ok", [
    ("FR7630006000011234567890189", True),
    ("FR76 3000 6000 0112 3456 7890 189", True),
    ("FR7630006000011234567890188", False),
    ("FR763000600001123456789018", False),   # longueur FR incorrecte
    ("DE89370400440532013000", True),
])
def test_iban(value, ok):
    assert ids.is_valid_iban(value) is ok


def test_sample_invoice_identifiers(facturx_path):
    """Les identifiants de la facture d'exemple doivent passer les contrôles."""
    root = load(facturx_path).root
    ns = {"ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"}
    sirens = root.xpath("//ram:SpecifiedLegalOrganization/ram:ID[@schemeID='0002']/text()", namespaces=ns)
    vats = root.xpath("//ram:SpecifiedTaxRegistration/ram:ID[@schemeID='VA']/text()", namespaces=ns)
    ibans = root.xpath("//ram:PayeePartyCreditorFinancialAccount/ram:IBANID/text()", namespaces=ns)
    assert sirens, "SIREN attendu dans la facture d'exemple"
    for s in sirens:
        assert ids.is_valid_siren(s), s
    for v in vats:
        if v.startswith("FR"):
            assert ids.is_valid_fr_vat(v), v
    for i in ibans:
        assert ids.is_valid_iban(i), i
