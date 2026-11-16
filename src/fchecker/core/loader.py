"""Chargement d'une facture : détection du format et extraction du XML."""
from __future__ import annotations

from pathlib import Path

from lxml import etree

from .document import (
    NS_CII,
    NS_UBL_CREDIT_NOTE,
    NS_UBL_INVOICE,
    DocFormat,
    InvoiceDocument,
    PdfInfo,
    secure_parser,
)

# Noms de pièce jointe reconnus, par ordre de préférence.
EMBEDDED_XML_NAMES = ("factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml")

_NS_PDFAID = "http://www.aiim.org/pdfa/ns/id/"
_NS_FX = "urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#"


class LoadError(Exception):
    """Fichier illisible ou non reconnu comme facture électronique."""


def load(path: str | Path) -> InvoiceDocument:
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise LoadError(f"Impossible de lire le fichier : {exc}") from exc

    if data[:5] == b"%PDF-" or data.lstrip()[:5] == b"%PDF-":
        return _load_pdf(path, data)
    return _load_xml(path, data)


def _load_xml(path: Path, data: bytes, *, pdf: bytes | None = None, pdf_info: PdfInfo | None = None) -> InvoiceDocument:
    try:
        root = etree.fromstring(data, parser=secure_parser())
    except etree.XMLSyntaxError as exc:
        raise LoadError(f"XML mal formé : {exc}") from exc

    ns = etree.QName(root).namespace
    if ns == NS_CII:
        fmt = DocFormat.FACTURX if pdf is not None else DocFormat.CII
        profile = _first_text(
            root,
            "rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID",
            {"rsm": NS_CII, "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"},
        )
    elif ns in (NS_UBL_INVOICE, NS_UBL_CREDIT_NOTE):
        if pdf is not None:
            raise LoadError("PDF contenant du UBL : format hybride non pris en charge.")
        fmt = DocFormat.UBL
        profile = _first_text(
            root,
            "cbc:CustomizationID",
            {"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"},
        )
    else:
        raise LoadError(f"Racine XML non reconnue ({root.tag}) : ni CII ni UBL.")

    doc = InvoiceDocument(path=path, format=fmt, xml_bytes=data, profile=profile, pdf_bytes=pdf, pdf_info=pdf_info)
    doc._tree = etree.ElementTree(root)
    return doc


def _load_pdf(path: Path, data: bytes) -> InvoiceDocument:
    import pikepdf  # import différé : coûteux et inutile pour un XML seul

    try:
        pdf = pikepdf.open(path)
    except pikepdf.PdfError as exc:
        raise LoadError(f"PDF illisible : {exc}") from exc

    with pdf:
        attachments = dict(pdf.attachments.items())
        name = next((n for n in EMBEDDED_XML_NAMES if n in attachments), None)
        if name is None:
            xml_names = [n for n in attachments if n.lower().endswith(".xml")]
            name = xml_names[0] if len(xml_names) == 1 else None
        if name is None:
            raise LoadError("PDF sans XML de facture embarqué (pas de pièce jointe factur-x.xml).")

        spec = attachments[name]
        xml = spec.get_file().read_bytes()
        rel = spec.obj.get("/AFRelationship")

        xmp = _read_xmp(pdf)
        part = _xmp_value(xmp, _NS_PDFAID, "part")
        conformance = _xmp_value(xmp, _NS_PDFAID, "conformance")
        fx_level = _xmp_value(xmp, _NS_FX, "ConformanceLevel")

        info = PdfInfo(
            pdf_version=str(pdf.pdf_version),
            page_count=len(pdf.pages),
            pdfa_part=part,
            pdfa_conformance=conformance,
            attachment_name=name,
            af_relationship=str(rel).lstrip("/") if rel is not None else None,
            fx_conformance_level=fx_level,
        )

    return _load_xml(path, xml, pdf=data, pdf_info=info)


def _read_xmp(pdf) -> etree._Element | None:
    """Lecture seule du flux XMP (``open_metadata`` de pikepdf réécrit le XMP en sortie)."""
    stream = pdf.Root.get("/Metadata")
    if stream is None:
        return None
    try:
        return etree.fromstring(stream.read_bytes(), parser=secure_parser())
    except Exception:  # XMP corrompu : signalé plus tard par le contrôle PDF/A
        return None


def _xmp_value(xmp: etree._Element | None, ns: str, name: str) -> str | None:
    """Valeur XMP, sous forme d'attribut (rdf:Description ns:x="…") ou d'élément (<ns:x>…</ns:x>)."""
    if xmp is None:
        return None
    for desc in xmp.iter("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description"):
        if (value := desc.get(f"{{{ns}}}{name}")) is not None:
            return value.strip()
        if (el := desc.find(f"{{{ns}}}{name}")) is not None and el.text:
            return el.text.strip()
    return None


def _first_text(root: etree._Element, xpath: str, ns: dict[str, str]) -> str | None:
    found = root.xpath(f"{xpath}/text()", namespaces=ns)
    return str(found[0]).strip() if found else None
