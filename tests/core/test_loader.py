import pytest

from fchecker.core.document import NS_CII, DocFormat
from fchecker.core.loader import LoadError, load

UBL_MINI = b"""<?xml version="1.0"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:CustomizationID>urn:cen.eu:en16931:2017</cbc:CustomizationID>
  <cbc:ID>F1</cbc:ID>
</Invoice>"""


def test_facturx_pdf(facturx_path):
    doc = load(facturx_path)
    assert doc.format is DocFormat.FACTURX
    assert doc.is_pdf
    assert doc.profile == "urn:cen.eu:en16931:2017"
    assert doc.root.tag == f"{{{NS_CII}}}CrossIndustryInvoice"
    info = doc.pdf_info
    assert info.pdfa_label == "PDF/A-3B"
    assert info.attachment_name == "factur-x.xml"
    assert info.af_relationship == "Source"
    assert info.fx_conformance_level == "EN 16931"


def test_xml_line_numbers_preserved(facturx_path):
    doc = load(facturx_path)
    number = doc.root.xpath("//*[local-name()='ExchangedDocument']/*[local-name()='ID']")[0]
    assert number.text == "F202500003" and number.sourceline == 16


def test_bom_is_tolerated(facturx_path):
    """Le XML des exemples officiels commence par un BOM UTF-8."""
    doc = load(facturx_path)
    assert doc.xml_bytes.startswith(b"\xef\xbb\xbf")
    assert not doc.xml_text.startswith("﻿")


def test_cii_xml_alone(tmp_path, facturx_path):
    xml = load(facturx_path).xml_bytes
    p = tmp_path / "facture.xml"
    p.write_bytes(xml)
    doc = load(p)
    assert doc.format is DocFormat.CII
    assert not doc.is_pdf


def test_ubl(tmp_path):
    p = tmp_path / "ubl.xml"
    p.write_bytes(UBL_MINI)
    doc = load(p)
    assert doc.format is DocFormat.UBL
    assert doc.profile == "urn:cen.eu:en16931:2017"


@pytest.mark.parametrize(
    "content, message",
    [
        (b"<pas-du-xml", "mal formé"),
        (b"<root xmlns='urn:autre'/>", "non reconnue"),
    ],
)
def test_invalid_xml(tmp_path, content, message):
    p = tmp_path / "x.xml"
    p.write_bytes(content)
    with pytest.raises(LoadError, match=message):
        load(p)


def test_xxe_not_resolved(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET")
    p = tmp_path / "xxe.xml"
    p.write_text(
        f'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///{secret.as_posix()}">]>'
        f'<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">&x;</Invoice>'
    )
    doc = load(p)
    assert "SECRET" not in (doc.root.text or "")


def test_missing_file(tmp_path):
    with pytest.raises(LoadError):
        load(tmp_path / "absent.pdf")
