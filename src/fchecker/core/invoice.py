"""Modèle métier normalisé (termes BT de l'EN 16931), indépendant de la syntaxe CII / UBL.

Chaque valeur garde la ligne XML d'où elle provient (``Value.line``), pour localiser les constats.
Le modèle est extrait une fois par document (:func:`invoice_of`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from lxml import etree

from .document import NS_UBL_CREDIT_NOTE, DocFormat, InvoiceDocument

NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


# Codes type d'autofacture : 389, 501, 500, 471, 473, 261, 502.
SELF_BILLING_TYPES = frozenset({"389", "501", "500", "471", "473", "261", "502"})


@dataclass(frozen=True, slots=True)
class Value:
    text: str
    line: int | None = None
    scheme: str | None = None

    def __str__(self) -> str:
        return self.text


@dataclass(slots=True)
class Address:
    lines: list[str] = field(default_factory=list)
    city: str | None = None
    postcode: str | None = None
    country: str | None = None
    line: int | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.lines or self.city or self.postcode or self.country)

    def one_line(self) -> str:
        return ", ".join(filter(None, [*self.lines, " ".join(filter(None, (self.postcode, self.city))), self.country]))


@dataclass(slots=True)
class Party:
    name: Value | None = None
    ids: list[Value] = field(default_factory=list)          # BT-29 / BT-46 (avec schéma)
    legal_id: Value | None = None                            # BT-30 / BT-47
    vat_id: Value | None = None                              # BT-31 / BT-48
    tax_registration: Value | None = None                    # BT-32 (vendeur : identifiant fiscal hors TVA)
    electronic_address: Value | None = None                  # BT-34 / BT-49
    legal_info: Value | None = None                          # BT-33
    address: Address = field(default_factory=Address)

    @property
    def siren(self) -> str | None:
        if self.legal_id and (self.legal_id.scheme in (None, "0002")) and re.fullmatch(r"\d{9}", self.legal_id.text):
            return self.legal_id.text
        return None

    @property
    def sirets(self) -> list[Value]:
        return [v for v in self.ids if v.scheme == "0009"]


@dataclass(slots=True)
class Note:
    code: str | None
    content: str
    line: int | None = None


@dataclass(slots=True)
class VatBreakdown:
    category: str | None
    rate: Decimal | None
    basis: Decimal | None
    amount: Decimal | None
    exemption_reason: str | None = None
    exemption_code: str | None = None
    line: int | None = None
    lines_of: dict[str, int | None] = field(default_factory=dict)  # BT → ligne XML de la valeur


@dataclass(slots=True)
class InvoiceLine:
    id: str | None
    name: str | None
    quantity: Decimal | None
    unit: str | None
    net_price: Decimal | None
    net_amount: Decimal | None
    vat_category: str | None
    vat_rate: Decimal | None
    line: int | None = None
    lines_of: dict[str, int | None] = field(default_factory=dict)  # BT → ligne XML de la valeur


@dataclass(slots=True)
class AllowanceCharge:
    is_charge: bool
    amount: Decimal | None
    reason: str | None
    vat_category: str | None
    vat_rate: Decimal | None
    line: int | None = None


@dataclass(slots=True)
class Totals:
    lines: Decimal | None = None           # BT-106
    allowances: Decimal | None = None      # BT-107
    charges: Decimal | None = None         # BT-108
    without_vat: Decimal | None = None     # BT-109
    vat: Decimal | None = None             # BT-110
    with_vat: Decimal | None = None        # BT-112
    prepaid: Decimal | None = None         # BT-113
    rounding: Decimal | None = None        # BT-114
    due: Decimal | None = None             # BT-115
    lines_of: dict[str, int | None] = field(default_factory=dict)


@dataclass(slots=True)
class Invoice:
    number: Value | None = None            # BT-1
    issue_date: date | None = None         # BT-2
    type_code: str | None = None           # BT-3
    currency: str | None = None            # BT-5
    vat_point_code: str | None = None      # BT-8
    due_date: date | None = None           # BT-9
    payment_terms: str | None = None       # BT-20
    business_process: str | None = None    # BT-23
    profile: str | None = None             # BT-24
    notes: list[Note] = field(default_factory=list)
    seller: Party = field(default_factory=Party)
    buyer: Party = field(default_factory=Party)
    invoicer: Party | None = None          # EXT-FR-FE-BG-05 Tiers Facturant (mandataire, EXTENDED-CTC-FR)
    deliver_to_name: str | None = None     # BT-70
    deliver_to: Address = field(default_factory=Address)  # BG-15
    delivery_date: date | None = None      # BT-72
    period_start: date | None = None       # BT-73 (BG-26)
    period_end: date | None = None         # BT-74 (BG-26)
    buyer_reference: str | None = None     # BT-10
    order_reference: str | None = None     # BT-13
    contract_reference: str | None = None  # BT-12
    payment_means_code: str | None = None  # BT-81
    allowances_charges: list[AllowanceCharge] = field(default_factory=list)  # BG-20 / BG-21
    ibans: list[Value] = field(default_factory=list)       # BT-84
    bics: list[Value] = field(default_factory=list)        # BT-86
    totals: Totals = field(default_factory=Totals)
    vat_breakdown: list[VatBreakdown] = field(default_factory=list)
    lines: list[InvoiceLine] = field(default_factory=list)
    lines_of: dict[str, int | None] = field(default_factory=dict)  # BT → ligne XML

    def notes_with(self, code: str) -> list[Note]:
        return [n for n in self.notes if (n.code or "").upper() == code.upper()]

    @property
    def self_billed(self) -> bool:
        """Autofacture : émise par l'ACHETEUR, destinataire = VENDEUR."""
        return (self.type_code or "") in SELF_BILLING_TYPES

    @property
    def issued_by_mandatary(self) -> bool:
        """Facture émise par un tiers sous mandat de facturation."""
        return self.invoicer is not None or bool(self.notes_with("DCL"))

    @property
    def vat_categories(self) -> set[str]:
        cats = {v.category for v in self.vat_breakdown if v.category}
        cats |= {ln.vat_category for ln in self.lines if ln.vat_category}
        return cats


# --- Utilitaires de lecture ---------------------------------------------------------------

def _first(node, xpath: str) -> etree._Element | None:
    found = node.xpath(xpath, namespaces=NS) if node is not None else []
    return found[0] if found else None


def _text(node, xpath: str) -> str | None:
    el = _first(node, xpath)
    if el is None:
        return None
    text = el if isinstance(el, str) else el.text
    return text.strip() if text and text.strip() else None


def _value(node, xpath: str, scheme_attr: str = "schemeID") -> Value | None:
    el = _first(node, xpath)
    if el is None or not (el.text or "").strip():
        return None
    return Value(el.text.strip(), el.sourceline, el.get(scheme_attr))


def _values(node, xpath: str, scheme_attr: str = "schemeID") -> list[Value]:
    if node is None:
        return []
    return [Value(e.text.strip(), e.sourceline, e.get(scheme_attr))
            for e in node.xpath(xpath, namespaces=NS) if (e.text or "").strip()]


def _line(node, xpath: str) -> int | None:
    el = _first(node, xpath)
    return el.sourceline if isinstance(el, etree._Element) else None


def _lines(node, xpaths: dict[str, str]) -> dict[str, int | None]:
    """Ligne XML de chaque BT (``{BT: XPath relatif à node}``)."""
    return {bt: _line(node, xp) for bt, xp in xpaths.items()}


def to_decimal(text: str | None) -> Decimal | None:
    if text is None:
        return None
    try:
        return Decimal(text.strip())
    except (InvalidOperation, AttributeError):
        return None


def parse_date(text: str | None) -> date | None:
    if not text:
        return None
    t = text.strip()
    m = re.fullmatch(r"(\d{4})-?(\d{2})-?(\d{2})", t[:10] if "-" in t else t[:8])
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


# --- CII ----------------------------------------------------------------------------------

_CII_SETTLE = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeSettlement"
_CII_AGREE = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeAgreement"
_CII_SUM = f"{_CII_SETTLE}/ram:SpecifiedTradeSettlementHeaderMonetarySummation"
_CII_LINE_TAX = "ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax"
_CII_LINE_XP = {  # relatif à IncludedSupplyChainTradeLineItem
    "BT-126": "ram:AssociatedDocumentLineDocument/ram:LineID",
    "BT-153": "ram:SpecifiedTradeProduct/ram:Name",
    "BT-129": "ram:SpecifiedLineTradeDelivery/ram:BilledQuantity",
    "BT-146": "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount",
    "BT-151": f"{_CII_LINE_TAX}/ram:CategoryCode",
    "BT-152": f"{_CII_LINE_TAX}/ram:RateApplicablePercent",
    "BT-131": "ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount",
}
_CII_VAT_XP = {  # relatif à ApplicableTradeTax (en-tête)
    "BT-116": "ram:BasisAmount", "BT-117": "ram:CalculatedAmount", "BT-118": "ram:CategoryCode",
    "BT-119": "ram:RateApplicablePercent", "BT-120": "ram:ExemptionReason",
}


def _cii_address(node) -> Address:
    a = _first(node, "ram:PostalTradeAddress")
    if a is None:
        return Address()
    lines = [t for t in (_text(a, "ram:LineOne"), _text(a, "ram:LineTwo"), _text(a, "ram:LineThree")) if t]
    return Address(lines, _text(a, "ram:CityName"), _text(a, "ram:PostcodeCode"), _text(a, "ram:CountryID"),
                   a.sourceline)


def _cii_party(node) -> Party:
    if node is None:
        return Party()
    return Party(
        name=_value(node, "ram:Name"),
        ids=_values(node, "ram:ID | ram:GlobalID"),
        legal_id=_value(node, "ram:SpecifiedLegalOrganization/ram:ID"),
        vat_id=_value(node, "ram:SpecifiedTaxRegistration/ram:ID[@schemeID='VA']"),
        tax_registration=_value(node, "ram:SpecifiedTaxRegistration/ram:ID[@schemeID='FC']"),
        electronic_address=_value(node, "ram:URIUniversalCommunication/ram:URIID"),
        legal_info=_value(node, "ram:Description"),
        address=_cii_address(node),
    )


def _extract_cii(root) -> Invoice:
    inv = Invoice()
    doc = _first(root, "rsm:ExchangedDocument")
    inv.number = _value(doc, "ram:ID")
    inv.issue_date = parse_date(_text(doc, "ram:IssueDateTime/udt:DateTimeString"))
    inv.type_code = _text(doc, "ram:TypeCode")
    inv.business_process = _text(root, "rsm:ExchangedDocumentContext/ram:BusinessProcessSpecifiedDocumentContextParameter/ram:ID")
    inv.profile = _text(root, "rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID")
    for n in root.xpath("rsm:ExchangedDocument/ram:IncludedNote", namespaces=NS):
        inv.notes.append(Note(_text(n, "ram:SubjectCode"), _text(n, "ram:Content") or "", n.sourceline))

    agree = _first(root, _CII_AGREE)
    inv.seller = _cii_party(_first(agree, "ram:SellerTradeParty"))
    inv.buyer = _cii_party(_first(agree, "ram:BuyerTradeParty"))
    inv.buyer_reference = _text(agree, "ram:BuyerReference")
    inv.order_reference = _text(agree, "ram:BuyerOrderReferencedDocument/ram:IssuerAssignedID")
    inv.contract_reference = _text(agree, "ram:ContractReferencedDocument/ram:IssuerAssignedID")
    delivery = _first(root, "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeDelivery")
    ship = _first(delivery, "ram:ShipToTradeParty")
    if ship is not None:
        inv.deliver_to_name = _text(ship, "ram:Name")
        inv.deliver_to = _cii_address(ship)
    inv.delivery_date = parse_date(_text(delivery, "ram:ActualDeliverySupplyChainEvent/ram:OccurrenceDateTime/udt:DateTimeString"))

    settle = _first(root, _CII_SETTLE)
    invoicer = _first(settle, "ram:InvoicerTradeParty")
    inv.invoicer = _cii_party(invoicer) if invoicer is not None else None
    inv.currency = _text(settle, "ram:InvoiceCurrencyCode")
    inv.vat_point_code = _text(settle, "ram:ApplicableTradeTax/ram:DueDateTypeCode")
    inv.period_start = parse_date(_text(settle, "ram:BillingSpecifiedPeriod/ram:StartDateTime/udt:DateTimeString"))
    inv.period_end = parse_date(_text(settle, "ram:BillingSpecifiedPeriod/ram:EndDateTime/udt:DateTimeString"))
    inv.due_date = parse_date(_text(settle, "ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime/udt:DateTimeString"))
    inv.payment_terms = _text(settle, "ram:SpecifiedTradePaymentTerms/ram:Description")
    inv.payment_means_code = _text(settle, "ram:SpecifiedTradeSettlementPaymentMeans/ram:TypeCode")
    for ac in (settle.xpath("ram:SpecifiedTradeAllowanceCharge", namespaces=NS) if settle is not None else []):
        inv.allowances_charges.append(AllowanceCharge(
            _text(ac, "ram:ChargeIndicator/udt:Indicator") == "true", to_decimal(_text(ac, "ram:ActualAmount")),
            _text(ac, "ram:Reason"), _text(ac, "ram:CategoryTradeTax/ram:CategoryCode"),
            to_decimal(_text(ac, "ram:CategoryTradeTax/ram:RateApplicablePercent")), ac.sourceline))
    inv.ibans = _values(settle, "ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeePartyCreditorFinancialAccount/ram:IBANID")
    inv.bics = _values(settle, "ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeeSpecifiedCreditorFinancialInstitution/ram:BICID")
    for t in (settle.xpath("ram:ApplicableTradeTax", namespaces=NS) if settle is not None else []):
        inv.vat_breakdown.append(VatBreakdown(
            _text(t, "ram:CategoryCode"), to_decimal(_text(t, "ram:RateApplicablePercent")),
            to_decimal(_text(t, "ram:BasisAmount")), to_decimal(_text(t, "ram:CalculatedAmount")),
            _text(t, "ram:ExemptionReason"), _text(t, "ram:ExemptionReasonCode"), t.sourceline,
            _lines(t, _CII_VAT_XP)))

    s = _first(root, _CII_SUM)
    currency = inv.currency
    vat_xpath = f"ram:TaxTotalAmount[@currencyID='{currency}']" if currency else "ram:TaxTotalAmount"
    fields = {"lines": ("BT-106", "ram:LineTotalAmount"), "allowances": ("BT-107", "ram:AllowanceTotalAmount"),
              "charges": ("BT-108", "ram:ChargeTotalAmount"), "without_vat": ("BT-109", "ram:TaxBasisTotalAmount"),
              "vat": ("BT-110", vat_xpath), "with_vat": ("BT-112", "ram:GrandTotalAmount"),
              "prepaid": ("BT-113", "ram:TotalPrepaidAmount"), "rounding": ("BT-114", "ram:RoundingAmount"),
              "due": ("BT-115", "ram:DuePayableAmount")}
    for attr, (bt, xp) in fields.items():
        setattr(inv.totals, attr, to_decimal(_text(s, xp)))
        inv.totals.lines_of[bt] = _line(s, xp)
    if inv.totals.vat is None and currency:  # TaxTotalAmount sans @currencyID
        inv.totals.vat = to_decimal(_text(s, "ram:TaxTotalAmount"))
        inv.totals.lines_of["BT-110"] = _line(s, "ram:TaxTotalAmount")

    for li in root.xpath("rsm:SupplyChainTradeTransaction/ram:IncludedSupplyChainTradeLineItem", namespaces=NS):
        qty = _first(li, "ram:SpecifiedLineTradeDelivery/ram:BilledQuantity")
        inv.lines.append(InvoiceLine(
            _text(li, "ram:AssociatedDocumentLineDocument/ram:LineID"),
            _text(li, "ram:SpecifiedTradeProduct/ram:Name"),
            to_decimal(qty.text) if qty is not None else None,
            qty.get("unitCode") if qty is not None else None,
            to_decimal(_text(li, "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount")),
            to_decimal(_text(li, "ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount")),
            _text(li, "ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/ram:CategoryCode"),
            to_decimal(_text(li, "ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/ram:RateApplicablePercent")),
            li.sourceline, _lines(li, _CII_LINE_XP)))

    inv.lines_of.update({
        "BT-1": inv.number.line if inv.number else None,
        "BT-2": _line(doc, "ram:IssueDateTime"),
        "BT-3": _line(doc, "ram:TypeCode"),
        "BT-5": _line(settle, "ram:InvoiceCurrencyCode"),
        "BT-10": _line(agree, "ram:BuyerReference"),
        "BT-12": _line(agree, "ram:ContractReferencedDocument/ram:IssuerAssignedID"),
        "BT-13": _line(agree, "ram:BuyerOrderReferencedDocument/ram:IssuerAssignedID"),
        "BT-20": _line(settle, "ram:SpecifiedTradePaymentTerms/ram:Description"),
        "BT-70": _line(ship, "ram:Name"),
        "BT-81": _line(settle, "ram:SpecifiedTradeSettlementPaymentMeans/ram:TypeCode"),
        "BT-8": _line(settle, "ram:ApplicableTradeTax/ram:DueDateTypeCode"),
        "BT-9": _line(settle, "ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime"),
        "BT-23": _line(root, "rsm:ExchangedDocumentContext/ram:BusinessProcessSpecifiedDocumentContextParameter"),
        "BG-1": doc.sourceline if doc is not None else None,
        "BG-4": _line(agree, "ram:SellerTradeParty"),
        "BG-7": _line(agree, "ram:BuyerTradeParty"),
        "BG-13": ship.sourceline if ship is not None else None,
        **inv.totals.lines_of,
    })
    return inv


# --- UBL ----------------------------------------------------------------------------------

def _ubl_address(node) -> Address:
    if node is None:
        return Address()
    lines = [t for t in (_text(node, "cbc:StreetName"), _text(node, "cbc:AdditionalStreetName"),
                         _text(node, "cac:AddressLine/cbc:Line")) if t]
    return Address(lines, _text(node, "cbc:CityName"), _text(node, "cbc:PostalZone"),
                   _text(node, "cac:Country/cbc:IdentificationCode"), node.sourceline)


def _ubl_party(node) -> Party:
    if node is None:
        return Party()
    return Party(
        name=_value(node, "cac:PartyLegalEntity/cbc:RegistrationName") or _value(node, "cac:PartyName/cbc:Name"),
        ids=_values(node, "cac:PartyIdentification/cbc:ID"),
        legal_id=_value(node, "cac:PartyLegalEntity/cbc:CompanyID"),
        vat_id=_value(node, "cac:PartyTaxScheme[cac:TaxScheme/cbc:ID='VAT']/cbc:CompanyID"),
        tax_registration=_value(node, "cac:PartyTaxScheme[not(cac:TaxScheme/cbc:ID='VAT')]/cbc:CompanyID"),
        electronic_address=_value(node, "cbc:EndpointID"),
        legal_info=_value(node, "cac:PartyLegalEntity/cbc:CompanyLegalForm"),
        address=_ubl_address(_first(node, "cac:PostalAddress")),
    )


_UBL_NOTE = re.compile(r"^#([A-Z]{3})#(.*)$", re.S)
_UBL_LINE_XP = {  # relatif à InvoiceLine / CreditNoteLine (BT-129 dépend du type de document)
    "BT-126": "cbc:ID", "BT-153": "cac:Item/cbc:Name", "BT-146": "cac:Price/cbc:PriceAmount",
    "BT-151": "cac:Item/cac:ClassifiedTaxCategory/cbc:ID", "BT-152": "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent",
    "BT-131": "cbc:LineExtensionAmount",
}
_UBL_VAT_XP = {  # relatif à TaxSubtotal
    "BT-116": "cbc:TaxableAmount", "BT-117": "cbc:TaxAmount", "BT-118": "cac:TaxCategory/cbc:ID",
    "BT-119": "cac:TaxCategory/cbc:Percent", "BT-120": "cac:TaxCategory/cbc:TaxExemptionReason",
}


def _extract_ubl(root) -> Invoice:
    inv = Invoice()
    credit = etree.QName(root).namespace == NS_UBL_CREDIT_NOTE
    inv.number = _value(root, "cbc:ID")
    inv.issue_date = parse_date(_text(root, "cbc:IssueDate"))
    inv.type_code = _text(root, "cbc:CreditNoteTypeCode" if credit else "cbc:InvoiceTypeCode")
    inv.currency = _text(root, "cbc:DocumentCurrencyCode")
    inv.vat_point_code = _text(root, "cac:InvoicePeriod/cbc:DescriptionCode")
    inv.due_date = parse_date(_text(root, "cac:PaymentMeans/cbc:PaymentDueDate" if credit else "cbc:DueDate"))
    inv.payment_terms = _text(root, "cac:PaymentTerms/cbc:Note")
    inv.business_process = _text(root, "cbc:ProfileID")
    inv.profile = _text(root, "cbc:CustomizationID")
    for n in root.xpath("cbc:Note", namespaces=NS):
        m = _UBL_NOTE.match((n.text or "").strip())
        inv.notes.append(Note(m[1], m[2].strip(), n.sourceline) if m else Note(None, (n.text or "").strip(), n.sourceline))

    seller = _first(root, "cac:AccountingSupplierParty/cac:Party")
    buyer = _first(root, "cac:AccountingCustomerParty/cac:Party")
    inv.seller, inv.buyer = _ubl_party(seller), _ubl_party(buyer)
    invoicer = _first(seller, "cac:ServiceProviderParty/cac:Party")
    inv.invoicer = _ubl_party(invoicer) if invoicer is not None else None
    delivery = _first(root, "cac:Delivery")
    if delivery is not None:
        inv.deliver_to_name = _text(delivery, "cac:DeliveryParty/cac:PartyName/cbc:Name")
        inv.deliver_to = _ubl_address(_first(delivery, "cac:DeliveryLocation/cac:Address"))
        inv.delivery_date = parse_date(_text(delivery, "cbc:ActualDeliveryDate"))
    inv.period_start = parse_date(_text(root, "cac:InvoicePeriod/cbc:StartDate"))
    inv.period_end = parse_date(_text(root, "cac:InvoicePeriod/cbc:EndDate"))

    inv.buyer_reference = _text(root, "cbc:BuyerReference")
    inv.order_reference = _text(root, "cac:OrderReference/cbc:ID")
    inv.contract_reference = _text(root, "cac:ContractDocumentReference/cbc:ID")
    inv.payment_means_code = _text(root, "cac:PaymentMeans/cbc:PaymentMeansCode")
    for ac in root.xpath("cac:AllowanceCharge", namespaces=NS):
        inv.allowances_charges.append(AllowanceCharge(
            _text(ac, "cbc:ChargeIndicator") == "true", to_decimal(_text(ac, "cbc:Amount")),
            _text(ac, "cbc:AllowanceChargeReason"), _text(ac, "cac:TaxCategory/cbc:ID"),
            to_decimal(_text(ac, "cac:TaxCategory/cbc:Percent")), ac.sourceline))
    inv.ibans = _values(root, "cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID")
    inv.bics = _values(root, "cac:PaymentMeans/cac:PayeeFinancialAccount/cac:FinancialInstitutionBranch/cbc:ID")
    for st in root.xpath("cac:TaxTotal/cac:TaxSubtotal", namespaces=NS):
        inv.vat_breakdown.append(VatBreakdown(
            _text(st, "cac:TaxCategory/cbc:ID"), to_decimal(_text(st, "cac:TaxCategory/cbc:Percent")),
            to_decimal(_text(st, "cbc:TaxableAmount")), to_decimal(_text(st, "cbc:TaxAmount")),
            _text(st, "cac:TaxCategory/cbc:TaxExemptionReason"), _text(st, "cac:TaxCategory/cbc:TaxExemptionReasonCode"),
            st.sourceline, _lines(st, _UBL_VAT_XP)))

    s = _first(root, "cac:LegalMonetaryTotal")
    fields = {"lines": ("BT-106", "cbc:LineExtensionAmount"), "allowances": ("BT-107", "cbc:AllowanceTotalAmount"),
              "charges": ("BT-108", "cbc:ChargeTotalAmount"), "without_vat": ("BT-109", "cbc:TaxExclusiveAmount"),
              "with_vat": ("BT-112", "cbc:TaxInclusiveAmount"), "prepaid": ("BT-113", "cbc:PrepaidAmount"),
              "rounding": ("BT-114", "cbc:PayableRoundingAmount"), "due": ("BT-115", "cbc:PayableAmount")}
    for attr, (bt, xp) in fields.items():
        setattr(inv.totals, attr, to_decimal(_text(s, xp)))
        inv.totals.lines_of[bt] = _line(s, xp)
    vat_xp = f"cac:TaxTotal/cbc:TaxAmount[@currencyID='{inv.currency}']" if inv.currency else "cac:TaxTotal/cbc:TaxAmount"
    inv.totals.vat = to_decimal(_text(root, vat_xp))
    inv.totals.lines_of["BT-110"] = _line(root, vat_xp)

    line_tag, qty_tag = ("cac:CreditNoteLine", "cbc:CreditedQuantity") if credit else ("cac:InvoiceLine", "cbc:InvoicedQuantity")
    for li in root.xpath(line_tag, namespaces=NS):
        qty = _first(li, qty_tag)
        inv.lines.append(InvoiceLine(
            _text(li, "cbc:ID"), _text(li, "cac:Item/cbc:Name"),
            to_decimal(qty.text) if qty is not None else None, qty.get("unitCode") if qty is not None else None,
            to_decimal(_text(li, "cac:Price/cbc:PriceAmount")), to_decimal(_text(li, "cbc:LineExtensionAmount")),
            _text(li, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID"),
            to_decimal(_text(li, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent")), li.sourceline,
            _lines(li, {**_UBL_LINE_XP, "BT-129": qty_tag})))

    inv.lines_of.update({
        "BT-1": inv.number.line if inv.number else None,
        "BT-2": _line(root, "cbc:IssueDate"),
        "BT-3": _line(root, "cbc:CreditNoteTypeCode" if credit else "cbc:InvoiceTypeCode"),
        "BT-5": _line(root, "cbc:DocumentCurrencyCode"),
        "BT-8": _line(root, "cac:InvoicePeriod/cbc:DescriptionCode"),
        "BT-9": _line(root, "cac:PaymentMeans/cbc:PaymentDueDate" if credit else "cbc:DueDate"),
        "BT-10": _line(root, "cbc:BuyerReference"),
        "BT-12": _line(root, "cac:ContractDocumentReference/cbc:ID"),
        "BT-13": _line(root, "cac:OrderReference/cbc:ID"),
        "BT-20": _line(root, "cac:PaymentTerms/cbc:Note"),
        "BT-70": _line(delivery, "cac:DeliveryParty/cac:PartyName/cbc:Name"),
        "BT-81": _line(root, "cac:PaymentMeans/cbc:PaymentMeansCode"),
        "BT-23": _line(root, "cbc:ProfileID"),
        "BG-1": _line(root, "cbc:Note"),
        "BG-4": seller.sourceline if seller is not None else None,
        "BG-7": buyer.sourceline if buyer is not None else None,
        "BG-13": delivery.sourceline if delivery is not None else None,
        **inv.totals.lines_of,
    })
    return inv


def extract(doc: InvoiceDocument) -> Invoice:
    return _extract_ubl(doc.root) if doc.format is DocFormat.UBL else _extract_cii(doc.root)


def invoice_of(doc: InvoiceDocument) -> Invoice:
    """Modèle extrait une seule fois par document (mis en cache sur le document)."""
    inv = doc.__dict__.get("_invoice")
    if inv is None:
        inv = doc.__dict__["_invoice"] = extract(doc)
    return inv
