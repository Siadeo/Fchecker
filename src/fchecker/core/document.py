from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from lxml import etree

NS_CII = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
NS_UBL_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_UBL_CREDIT_NOTE = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"


class DocFormat(str, Enum):
    FACTURX = "Factur-X"
    CII = "CII"
    UBL = "UBL"

    @property
    def syntax(self) -> str:
        """Syntaxe du XML porté (Factur-X embarque du CII)."""
        return "UBL" if self is DocFormat.UBL else "CII"


@dataclass(frozen=True, slots=True)
class PdfInfo:
    pdf_version: str
    page_count: int
    pdfa_part: str | None
    pdfa_conformance: str | None
    attachment_name: str | None
    af_relationship: str | None
    fx_conformance_level: str | None

    @property
    def pdfa_label(self) -> str | None:
        if not self.pdfa_part:
            return None
        return f"PDF/A-{self.pdfa_part}{(self.pdfa_conformance or '').upper()}"


@dataclass(eq=False)
class InvoiceDocument:
    path: Path
    format: DocFormat
    xml_bytes: bytes
    profile: str | None = None
    pdf_bytes: bytes | None = None
    pdf_info: PdfInfo | None = None
    _tree: etree._ElementTree | None = field(default=None, repr=False)

    @property
    def is_pdf(self) -> bool:
        return self.pdf_bytes is not None

    @property
    def xml_tree(self) -> etree._ElementTree:
        """Arbre XML parsé une seule fois ; conserve les n° de ligne (sourceline)."""
        if self._tree is None:
            self._tree = etree.ElementTree(etree.fromstring(self.xml_bytes, parser=secure_parser()))
        return self._tree

    @property
    def root(self) -> etree._Element:
        return self.xml_tree.getroot()

    @property
    def xml_text(self) -> str:
        """XML re-sérialisé par lxml, sans BOM ni déclaration d'encodage.

        À transmettre aux moteurs tiers (Saxon) : les octets bruts peuvent commencer par un BOM
        UTF-8 ou être dans un autre encodage, ce que ``parse_xml(xml_text=…)`` refuse.
        """
        text = self.__dict__.get("_xml_text")
        if text is None:
            text = self.__dict__["_xml_text"] = etree.tostring(self.xml_tree, encoding="unicode")
        return text

    @property
    def display_name(self) -> str:
        return self.path.name


KNOWN_PROFILES = {
    "urn:factur-x.eu:1p0:minimum": "MINIMUM",
    "urn:factur-x.eu:1p0:basicwl": "BASIC WL",
    "urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic": "BASIC",
    "urn:cen.eu:en16931:2017": "EN 16931",
    "urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended": "EXTENDED",
}


def profile_label(profile: str) -> str:
    """Libellé court d'un profil (GuidelineSpecifiedDocumentContextParameter / CustomizationID)."""
    return KNOWN_PROFILES.get(profile, profile)


def secure_parser() -> etree.XMLParser:
    """Parser sans résolution d'entités ni accès réseau (XXE)."""
    return etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_blank_text=False)
