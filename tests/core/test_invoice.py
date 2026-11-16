from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from fchecker.core.invoice import invoice_of, parse_date
from fchecker.core.loader import load

UBL = Path(__file__).parents[1] / "fixtures" / "en16931" / "ubl" / "ubl-tc434-example1.xml"


def test_sample_cii(facturx_path):
    inv = invoice_of(load(facturx_path))
    assert str(inv.number) == "F202500003" and inv.issue_date == date(2025, 7, 1)
    assert inv.type_code == "380" and inv.currency == "EUR" and inv.business_process == "S1"
    assert inv.vat_point_code == "72" and inv.due_date == date(2025, 7, 31)
    assert inv.payment_terms == "PAIEMENT 30 JOURS NET"
    assert [n.code for n in inv.notes] == ["REG", "ABL", "AAI", "PMD", "PMT", "AAB"]
    assert inv.seller.siren == "100000009" and inv.buyer.siren == "200000008"
    assert str(inv.buyer.vat_id) == "FR37200000008"
    assert (inv.buyer.electronic_address.text, inv.buyer.electronic_address.scheme) == ("200000008", "0225")
    assert (inv.seller.electronic_address.text, inv.seller.electronic_address.scheme) == ("100000009_STATUTS", "0225")
    assert [(v.text, v.scheme) for v in inv.seller.ids] == [("587451236587", "0088")]
    assert inv.seller.legal_info.text == "SARL AU CAPITAL DE 50 000 EUROS"
    assert inv.deliver_to_name == "NOUS AUSSI" and inv.deliver_to.city == "MA VILLE"
    assert (inv.period_start, inv.period_end) == (date(2025, 6, 1), date(2025, 6, 30))
    assert inv.buyer_reference == "BU_2516" and inv.order_reference == "PO202525478"
    assert inv.payment_means_code == "30" and [str(i) for i in inv.ibans] == ["FR20 1254 2547 2569 8542 5874 698"]
    assert inv.invoicer is None and not inv.self_billed and not inv.issued_by_mandatary
    t = inv.totals
    assert (t.without_vat, t.vat, t.with_vat, t.due) == (Decimal("10000.00"), Decimal("2000.00"),
                                                         Decimal("12000.00"), Decimal("12000.00"))
    assert [(v.category, v.rate) for v in inv.vat_breakdown] == [("S", Decimal("20.00"))]
    assert len(inv.lines) == 2 and inv.lines[0].net_amount == Decimal("8000.00")
    assert inv.lines_of["BT-112"] == 239 and inv.lines_of["BT-1"] == inv.number.line == 16


def test_cached_per_document(facturx_path):
    doc = load(facturx_path)
    assert invoice_of(doc) is invoice_of(doc)


def test_ubl():
    inv = invoice_of(load(UBL))
    assert str(inv.number) == "12115118" and inv.issue_date == date(2015, 1, 9)
    assert inv.totals.with_vat == Decimal("250.33") and inv.totals.vat == Decimal("20.73")
    assert len(inv.lines) == 20 and len(inv.ibans) == 2
    assert inv.seller.address.country == "NL"


def _source_line(doc, line: int) -> str:
    return doc.xml_bytes.decode("utf-8").splitlines()[line - 1]


def test_lines_of_point_to_source(facturx_path):
    """Lignes XML utilisées par la visionneuse (clic sur une valeur → ligne surlignée)."""
    doc = load(facturx_path)
    inv = invoice_of(doc)
    for bt, tag in {"BT-3": "ram:TypeCode", "BT-5": "ram:InvoiceCurrencyCode", "BT-10": "ram:BuyerReference",
                    "BT-13": "ram:IssuerAssignedID", "BT-20": "ram:Description", "BT-70": "ram:Name",
                    "BT-81": "ram:TypeCode"}.items():
        assert f"<{tag}" in _source_line(doc, inv.lines_of[bt]), bt


def test_ubl_lines_of_point_to_source():
    doc = load(UBL)
    inv = invoice_of(doc)
    for bt, tag in {"BT-3": "cbc:InvoiceTypeCode", "BT-5": "cbc:DocumentCurrencyCode",
                    "BT-81": "cbc:PaymentMeansCode"}.items():
        assert f"<{tag}" in _source_line(doc, inv.lines_of[bt]), bt


@pytest.mark.parametrize("path, tags", [
    ("facturx", {"BT-153": "ram:Name", "BT-129": "ram:BilledQuantity", "BT-146": "ram:ChargeAmount",
                 "BT-131": "ram:LineTotalAmount", "BT-151": "ram:CategoryCode"}),
    ("ubl", {"BT-153": "cbc:Name", "BT-129": "cbc:InvoicedQuantity", "BT-146": "cbc:PriceAmount",
             "BT-131": "cbc:LineExtensionAmount", "BT-151": "cbc:ID"}),
])
def test_invoice_line_cells_point_to_values(path, tags, facturx_path):
    doc = load(facturx_path if path == "facturx" else UBL)
    line = invoice_of(doc).lines[0]
    for bt, tag in tags.items():
        assert f"<{tag}" in _source_line(doc, line.lines_of[bt]), bt


def test_vat_breakdown_cells_point_to_values(facturx_path):
    doc = load(facturx_path)
    vat = invoice_of(doc).vat_breakdown[0]
    for bt, tag in {"BT-116": "ram:BasisAmount", "BT-117": "ram:CalculatedAmount", "BT-118": "ram:CategoryCode",
                    "BT-119": "ram:RateApplicablePercent"}.items():
        assert f"<{tag}" in _source_line(doc, vat.lines_of[bt]), bt


def test_parse_date():
    assert parse_date("20260924") == date(2026, 9, 24)
    assert parse_date("2026-09-24") == date(2026, 9, 24)
    assert parse_date("2026-02-30") is None and parse_date(None) is None
