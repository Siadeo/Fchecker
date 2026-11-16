import pytest

from fchecker.core.findings import Finding, Severity, Source
from fchecker.core.rules_catalog import catalog, normalize_key, translate_pattern


def test_normalize_key():
    assert normalize_key("BR-01") == normalize_key("br-1") == "BR-1"
    assert normalize_key("BR-FR-05") == "BR-FR-5"
    assert normalize_key("G1.03") == "G1.3"


def test_en_rule_uses_home_translation():
    # Traduction maison (en16931_fr.yaml) du message anglais des artefacts CEN.
    f = catalog().enrich(Finding("BR-CO-15", Severity.ERROR, Source.SCHEMATRON_EN,
                                 "[BR-CO-15]-Invoice total amount with VAT (BT-112) = ..."))
    assert f.translated
    assert f.title.startswith("Total TTC de la facture (BT-112)")
    assert "centime" in f.explanation           # texte pédagogique (toolkit.yaml)
    assert f.example and f.bt == "BT-112, BT-109, BT-110"
    e = catalog().entry("BR-CO-15")
    assert e["original"].startswith("Invoice total amount with VAT") and "CEN" in e["source"]


def test_translation_wins_over_generic_pattern():
    # « Each … shall contain … » serait traduit par motif ; la traduction de la règle prime.
    f = catalog().enrich(Finding("BR-54", Severity.ERROR, Source.SCHEMATRON_EN,
                                 "[BR-54]-Each Item attribute (BG-32) shall contain an Item attribute name (BT-160) "
                                 "and an Item attribute value (BT-161)."))
    assert f.title == "Chaque attribut d'article (BG-32) doit avoir un nom (BT-160) et une valeur (BT-161)."


def test_profile_variant_uses_base_translation():
    f = catalog().enrich(Finding("BR-FXEXT-S-08", Severity.ERROR, Source.SCHEMATRON_EN, "[BR-FXEXT-S-08]-For each…"))
    assert f.title.startswith("Pour chaque taux (BT-119) de la catégorie « taux normal » (S)")


def test_syntax_rule_translated_in_catalog():
    e = catalog().entry("UBL-CR-001")
    assert e["original"].startswith("A UBL invoice should not include")
    assert e["title"].startswith("La facture UBL ne doit pas contenir")


def test_br_fr_keeps_actual_message():
    msg = "BR-FR-05/BT-22 : La mention relative aux pénalités de retard (code PMD) est absente."
    f = catalog().enrich(Finding("BR-FR-05", Severity.ERROR, Source.SCHEMATRON_FR, msg, bt="BT-22"))
    assert f.title == "La mention relative aux pénalités de retard (code PMD) est absente."
    assert "PMT" in f.explanation and "PMD" in f.explanation


@pytest.mark.parametrize("message, expected", [
    ("[CII-SR-237] - ChannelCode should not be present", "« ChannelCode » ne doit pas être présent"),
    ("[UBL-CR-490]-A UBL invoice should not include the TaxExchangeRate", "ne doit pas contenir « TaxExchangeRate »"),
    ("[UBL-SR-45]-Due Date shall occur maximum once", "« Due Date » ne doit apparaître qu'une fois"),
    ("Element 'ram:TypeCode' must occur exactly 1 times.", "« ram:TypeCode » doit être présent exactement 1 fois"),
    ("Element 'ram:TaxPointDate' is marked as not used in the given context.", "n'est pas utilisé dans ce profil"),
    ("Element '{urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100}Bidon': "
     "This element is not expected. Expected is ( "
     "{urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100}IssueDateTime ).",
     "« ram:Bidon » n'est pas attendu à cet endroit. Attendu : ram:IssueDateTime"),
])
def test_pattern_translations(message, expected):
    assert expected in translate_pattern(message)


def test_untranslatable_is_flagged():
    f = catalog().enrich(Finding("ZZ-99", Severity.ERROR, Source.SCHEMATRON_EN, "Something odd"))
    assert not f.translated and f.display_message == "Something odd"


def test_lookup():
    hits = catalog().lookup("BR-CO-1")
    assert any(k == "BR-CO-15" for k, _ in hits)
    assert catalog().lookup("pénalités")


def test_lookup_empty_returns_all_rules():
    keys = {k for k, _ in catalog().lookup("")}
    assert len(keys) > 200
    assert {"BR-CO-15", "FR-PROFIL-1"} <= keys  # clés normalisées (FR-PROFIL-01 ≡ FR-PROFIL-1)
