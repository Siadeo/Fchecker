"""Mentions obligatoires, sur la facture de référence UC1 (exemple officiel FNFE) :
prestation de services (S1), BT-8 = 72, notes REG / ABL / PMD / PMT / AAB, BT-33 renseigné,
période de facturation (BG-26), adresse de livraison différente de celle de l'acheteur, pas de mandataire.
"""
import pytest

from fchecker.core.findings import Severity
from fchecker.core.loader import load
from fchecker.core.plugin import RunContext
from fchecker.core.registry import Registry
from fchecker.plugins.mentions.predicates import Status

PMT = "Indemnité forfaitaire pour frais de recouvrement en cas de retard de paiement : 40 €."
PMD = "calculée sur la base de trois fois le taux d'intérêt légal."


@pytest.fixture(scope="module")
def tool():
    reg = Registry()
    reg.discover()
    return reg.get_tool("mentions")


def run(tool, doc):
    report = tool.run(doc, RunContext())
    return {m["id"]: m for m in report.meta["mentions"]}, {f.rule_id: f for f in report.findings}


def add_note(xml: str, code: str, content: str) -> str:
    note = f"<ram:IncludedNote><ram:Content>{content}</ram:Content><ram:SubjectCode>{code}</ram:SubjectCode></ram:IncludedNote>"
    return xml.replace("<ram:IncludedNote>", note + "<ram:IncludedNote>", 1)


def test_sample_checklist(tool, facturx_path):
    checklist, findings = run(tool, load(facturx_path))
    assert len(checklist) == 15
    for rid in ("MEN-01", "MEN-02", "MEN-05", "MEN-06", "MEN-07", "MEN-08", "MEN-12", "MEN-14"):
        assert checklist[rid]["status"] is Status.OK, rid
    assert checklist["MEN-06"]["detail"] == "40,00 €."
    assert checklist["MEN-14"]["detail"] == "Période de facturation du 01/06/2025 au 30/06/2025 (BG-26)."
    assert checklist["MEN-03"]["status"] is Status.NA          # G6.16 : pas pour les services
    assert checklist["MEN-04"]["detail"] == "BT-8 = 72 (autre date d'exigibilité)."
    for rid in ("MEN-09", "MEN-10", "MEN-11", "MEN-13"):
        assert checklist[rid]["status"] is Status.NA, rid
    assert findings == {}  # exemple officiel conforme


def test_covered_mentions_do_not_duplicate_br_fr(tool, sample_xml, cii_file):
    xml = sample_xml.replace("<ram:SubjectCode>PMT</ram:SubjectCode>", "<ram:SubjectCode>AAI</ram:SubjectCode>")
    checklist, findings = run(tool, load(cii_file(xml)))
    assert checklist["MEN-06"]["status"] is Status.MISSING
    assert checklist["MEN-06"]["covered_by"] == ["BR-FR-05"]
    assert "MEN-06" not in findings  # c'est BR-FR-05 (validateur) qui le signale


@pytest.mark.parametrize("old, new, rule, severity", [
    (PMT, "Indemnité forfaitaire pour frais de recouvrement : 15 €.", "MEN-06", Severity.ERROR),
    (PMT, "Indemnité forfaitaire pour frais de recouvrement selon la loi.", "MEN-06", Severity.WARNING),
    (PMD, "calculée selon nos conditions générales.", "MEN-05", Severity.WARNING),
])
def test_content_rules(tool, sample_xml, cii_file, old, new, rule, severity):
    assert old in sample_xml
    _, findings = run(tool, load(cii_file(sample_xml.replace(old, new, 1))))
    assert findings[rule].severity is severity


def test_mandate_note(tool, sample_xml, cii_file):
    """Mandataire : la mention DCL doit citer le vendeur (« LE VENDEUR »)."""
    ok = add_note(sample_xml, "DCL", "Facture établie par MANDATAIRE SAS au nom et pour le compte de LE VENDEUR")
    checklist, findings = run(tool, load(cii_file(ok)))
    assert checklist["MEN-13"]["status"] is Status.OK and "MEN-13" not in findings
    ko = add_note(sample_xml, "DCL", "Facture établie par MANDATAIRE SAS au nom et pour le compte d'un tiers")
    _, findings = run(tool, load(cii_file(ko)))
    assert findings["MEN-13"].severity is Severity.WARNING


def test_services_without_bt8(tool, sample_xml, cii_file):
    xml = sample_xml.replace("<ram:DueDateTypeCode>72</ram:DueDateTypeCode>", "")
    checklist, findings = run(tool, load(cii_file(xml)))
    # G1.67 : non contrôlable applicativement → simple information
    assert checklist["MEN-04"]["status"] is Status.CHECK and findings["MEN-04"].severity is Severity.INFO


@pytest.mark.parametrize("code", ["5", "29"])
def test_debit_option_codes(tool, sample_xml, cii_file, code):
    """Option débits : 5 (date de facture) ou 29 (date de livraison) = option débits en CII."""
    xml = sample_xml.replace("<ram:DueDateTypeCode>72</ram:DueDateTypeCode>",
                             f"<ram:DueDateTypeCode>{code}</ram:DueDateTypeCode>")
    checklist, _ = run(tool, load(cii_file(xml)))
    assert checklist["MEN-04"]["status"] is Status.OK


@pytest.mark.parametrize("issue_date, severity", [("20260924", Severity.INFO), ("20270915", Severity.WARNING)])
def test_delivery_address_rule_applies_from_2027(tool, sample_xml, cii_file, issue_date, severity):
    """G6.16 : adresse de livraison différente et incomplète → obligatoire à partir du 01/09/2027 (biens)."""
    xml = sample_xml.replace("<ram:ID>S1</ram:ID>", "<ram:ID>B1</ram:ID>").replace("20250701", issue_date, 1)
    ship_start, ship_end = xml.index("<ram:ShipToTradeParty>"), xml.index("</ram:ShipToTradeParty>")
    ship = xml[ship_start:ship_end].replace("<ram:PostcodeCode>06000</ram:PostcodeCode>", "")
    xml = xml[:ship_start] + ship + xml[ship_end:]
    checklist, findings = run(tool, load(cii_file(xml)))
    assert checklist["MEN-03"]["status"] is Status.MISSING and findings["MEN-03"].severity is severity
    assert "code postal (BT-78)" in findings["MEN-03"].message


def test_delivery_address_complete_is_ok_for_goods(tool, sample_xml, cii_file):
    xml = sample_xml.replace("<ram:ID>S1</ram:ID>", "<ram:ID>B1</ram:ID>")
    checklist, _ = run(tool, load(cii_file(xml)))
    assert checklist["MEN-03"]["status"] is Status.OK


def _header_vat(xml: str, extra: str) -> str:
    """Passe la ventilation TVA d'en-tête (BG-23) en catégorie E avec ``extra``."""
    start = xml.index("<ram:ApplicableHeaderTradeSettlement>")
    head, tail = xml[:start], xml[start:]
    return head + tail.replace("<ram:CategoryCode>S</ram:CategoryCode>",
                               f"<ram:CategoryCode>E</ram:CategoryCode>{extra}", 1)


def test_franchise_en_base(tool, sample_xml, cii_file):
    """Franchise en base : E + VATEX-FR-FRANCHISE ; sans n° de TVA, SIREN répété en BT-32."""
    xml = sample_xml.replace('<ram:ID schemeID="VA">FR88100000009</ram:ID>', "")  # plus de TVA vendeur
    xml = _header_vat(xml, "<ram:ExemptionReasonCode>VATEX-FR-FRANCHISE</ram:ExemptionReasonCode>")
    _, findings = run(tool, load(cii_file(xml)))
    assert findings["MEN-10"].severity is Severity.WARNING and findings["MEN-10"].bt == "BT-32"


@pytest.mark.parametrize("text", ["TVA non applicable, art. 293 B du CGI",
                                  "TVA non applicable, article L. 233-3 du CIBS",
                                  "TVA non applicable, art. L233-3 du CIBS"])
def test_franchise_text_without_code(tool, sample_xml, cii_file, text):
    xml = _header_vat(sample_xml, f"<ram:ExemptionReason>{text}</ram:ExemptionReason>")
    _, findings = run(tool, load(cii_file(xml)))
    assert findings["MEN-10"].severity is Severity.WARNING and findings["MEN-10"].bt == "BT-121"


def test_franchise_mention_follows_cibs_date():
    from datetime import date

    from fchecker.plugins.mentions.predicates import franchise_mention

    assert "293 B du CGI" in franchise_mention(date(2026, 12, 31))
    assert "L. 233-3 du CIBS" in franchise_mention(date(2027, 1, 1))


def test_purchase_order_reminder(tool, sample_xml, cii_file):
    """Art. L441-9 : invérifiable, donc simple information si BT-13 est absent."""
    import re

    xml = re.sub(r"<ram:BuyerOrderReferencedDocument>.*?</ram:BuyerOrderReferencedDocument>", "", sample_xml, flags=re.S)
    checklist, findings = run(tool, load(cii_file(xml)))
    assert checklist["MEN-15"]["status"] is Status.CHECK and findings["MEN-15"].severity is Severity.INFO


def test_purchase_order_present(tool, sample_xml, cii_file):
    import re

    order = ("<ram:BuyerOrderReferencedDocument><ram:IssuerAssignedID>BC-42</ram:IssuerAssignedID>"
             "</ram:BuyerOrderReferencedDocument>")
    xml = re.sub(r"<ram:BuyerOrderReferencedDocument>.*?</ram:BuyerOrderReferencedDocument>", "", sample_xml, flags=re.S)
    xml = xml.replace("</ram:ApplicableHeaderTradeAgreement>", order + "</ram:ApplicableHeaderTradeAgreement>", 1)
    checklist, findings = run(tool, load(cii_file(xml)))
    assert checklist["MEN-15"]["status"] is Status.OK and "BC-42" in checklist["MEN-15"]["detail"]
    assert "MEN-15" not in findings


def test_self_billing_carried_by_type_code(tool, sample_xml, cii_file):
    """Exemples officiels UC13 : autofacture (389) sans note « Autofacturation »."""
    xml = sample_xml.replace("<ram:TypeCode>380</ram:TypeCode>", "<ram:TypeCode>389</ram:TypeCode>", 1)
    checklist, findings = run(tool, load(cii_file(xml)))
    assert checklist["MEN-11"]["status"] is Status.OK and "MEN-11" not in findings


def test_invoicer_block_without_dcl(tool, sample_xml, cii_file):
    """Tiers Facturant déclaré (EXT-FR-FE-BG-05) sans note DCL : mention recommandée → information."""
    xml = sample_xml.replace("<ram:ApplicableHeaderTradeSettlement>", "<ram:ApplicableHeaderTradeSettlement>"
                             "<ram:InvoicerTradeParty><ram:Name>MANDATAIRE SAS</ram:Name></ram:InvoicerTradeParty>", 1)
    checklist, findings = run(tool, load(cii_file(xml)))
    assert checklist["MEN-13"]["status"] is Status.CHECK and findings["MEN-13"].severity is Severity.INFO


def test_legal_info_in_reg_abl_notes(tool, sample_xml, cii_file):
    """Exemples officiels FNFE : capital en note REG, RCS en note ABL, même sans BT-33."""
    no_bt33 = sample_xml.replace("<ram:Description>SARL AU CAPITAL DE 50 000 EUROS</ram:Description>", "")
    checklist, findings = run(tool, load(cii_file(no_bt33)))
    assert checklist["MEN-12"]["status"] is Status.OK and "MEN-12" not in findings
    nothing = (no_bt33.replace("<ram:SubjectCode>REG</ram:SubjectCode>", "<ram:SubjectCode>AAI</ram:SubjectCode>")
               .replace("<ram:SubjectCode>ABL</ram:SubjectCode>", "<ram:SubjectCode>AAI</ram:SubjectCode>"))
    _, findings = run(tool, load(cii_file(nothing)))
    assert findings["MEN-12"].severity is Severity.WARNING


def test_reverse_charge(tool, sample_xml, cii_file):
    xml = sample_xml.replace("<ram:CategoryCode>S</ram:CategoryCode>", "<ram:CategoryCode>AE</ram:CategoryCode>")
    _, findings = run(tool, load(cii_file(xml)))
    assert findings["MEN-09"].severity is Severity.ERROR
