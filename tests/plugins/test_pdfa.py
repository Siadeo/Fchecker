import pikepdf
import pytest
from pikepdf import Dictionary, Name

from fchecker.core.findings import Severity
from fchecker.core.loader import load
from fchecker.core.plugin import RunContext
from fchecker.plugins.validator.checks.pdfa import CHECK, NS_FX


def check(path):
    return list(CHECK.run(load(path), RunContext()))


@pytest.fixture
def craft(tmp_path, facturx_path):
    """Applique une mutation à la facture d'exemple et renvoie le chemin du PDF produit."""
    def make(mutate, **save_kw):
        out = tmp_path / "mute.pdf"
        with pikepdf.open(facturx_path) as pdf:
            mutate(pdf)
            pdf.save(out, **save_kw)
        return out
    return make


def rules(findings):
    return {f.rule_id for f in findings}


def test_sample_is_structurally_valid(facturx_path):
    assert check(facturx_path) == []


def test_missing_output_intent(craft):
    def mutate(pdf):
        del pdf.Root.OutputIntents
    assert rules(check(craft(mutate))) == {"PDFA-04"}


def test_javascript_open_action(craft):
    def mutate(pdf):
        pdf.Root.OpenAction = Dictionary(S=Name.JavaScript, JS=pikepdf.String("app.alert(1)"))
    found = check(craft(mutate))
    assert rules(found) == {"PDFA-06"} and "JavaScript" in found[0].message


def add_helvetica(pdf, content: bytes | None):
    """Déclare /F99 (Helvetica non embarquée) et, si fourni, ajoute le flux de contenu qui l'utilise."""
    page = pdf.pages[0]
    page.obj.Resources.Font.F99 = Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica)
    if content is not None:
        page.contents_add(pikepdf.Stream(pdf, content), prepend=False)


def test_non_embedded_font(craft):
    found = check(craft(lambda pdf: add_helvetica(pdf, b"BT /F99 10 Tf 0 0 Td (x) Tj ET")))
    assert rules(found) == {"PDFA-05"} and "Helvetica" in found[0].message


@pytest.mark.parametrize("content", [
    None,                                                     # déclarée, jamais utilisée
    b"BT /F99 10 Tf 3 Tr 0 0 Td (x) Tj ET",                   # texte invisible (couche OCR)
    b"q 3 Tr BT /F99 10 Tf (x) Tj ET Q BT 0 Tr /F99 10 Tf ET",  # visible sélectionnée mais rien affiché
])
def test_font_exempt_when_not_rendered(craft, content):
    """ISO 19005-3 § 6.2.11.4.1 : seules les polices servant au rendu doivent être embarquées."""
    assert check(craft(lambda pdf: add_helvetica(pdf, content))) == []


def test_invisible_mode_restored_by_Q(craft):
    content = b"q 3 Tr Q BT /F99 10 Tf (x) Tj ET"
    assert rules(check(craft(lambda pdf: add_helvetica(pdf, content)))) == {"PDFA-05"}


def test_font_used_in_form_xobject(craft):
    def mutate(pdf):
        font = Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Courier)
        form = pikepdf.Stream(pdf, b"BT /F1 10 Tf (x) Tj ET")
        form.Type, form.Subtype, form.BBox = Name.XObject, Name.Form, [0, 0, 10, 10]
        form.Resources = Dictionary(Font=Dictionary(F1=font))
        page = pdf.pages[0]
        if "/XObject" not in page.obj.Resources:
            page.obj.Resources.XObject = Dictionary()
        page.obj.Resources.XObject.Fm99 = form
        page.contents_add(pikepdf.Stream(pdf, b"q /Fm99 Do Q"), prepend=False)
    found = check(craft(mutate))
    assert rules(found) == {"PDFA-05"} and "Courier" in found[0].message


def test_attachment_relationship_and_af(craft):
    def mutate(pdf):
        pdf.attachments["factur-x.xml"].obj.AFRelationship = Name.Unspecified
        del pdf.Root.AF
    found = [f for f in check(craft(mutate)) if f.rule_id == "PDFA-08"]
    assert len(found) == 2 and all(f.severity is Severity.ERROR for f in found)


def test_renamed_attachment(craft):
    def mutate(pdf):
        data = pdf.attachments["factur-x.xml"].get_file().read_bytes()
        del pdf.attachments["factur-x.xml"]
        pdf.attachments["facture.xml"] = pikepdf.AttachedFileSpec(pdf, data, filename="facture.xml",
                                                                  mime_type="text/xml")
    found = check(craft(mutate))
    assert any(f.rule_id == "PDFA-08" and "doit être « factur-x.xml »" in f.message for f in found)
    assert any(f.rule_id == "PDFA-09" and "DocumentFileName" in f.message for f in found)


def test_facturx_xmp_document_type(craft):
    def mutate(pdf):
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta[f"{{{NS_FX}}}DocumentType"] = "ORDER"
    found = check(craft(mutate))
    assert any(f.rule_id == "PDFA-09" and "ORDER" in f.message for f in found)


def test_encrypted_pdf_is_fatal(craft):
    path = craft(lambda pdf: None, encryption=pikepdf.Encryption(owner="secret", user=""))
    found = check(path)
    assert any(f.rule_id == "PDFA-03" and f.severity is Severity.FATAL for f in found)
