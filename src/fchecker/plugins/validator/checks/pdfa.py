"""PDF/A-3 et Factur-X : contrôles STRUCTURELS en Python (pikepdf).

Ce n'est pas une validation PDF/A certifiante (veraPDF) : on vérifie les points qui font
échouer le plus souvent les Factur-X — en-tête, XMP, OutputIntent, polices, actions,
pièce jointe et métadonnées Factur-X.
"""
from __future__ import annotations

import io
import re

from lxml import etree

from fchecker.core.document import secure_parser
from fchecker.core.findings import Finding, Severity, Source

from . import Check

NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NS_PDFAID = "http://www.aiim.org/pdfa/ns/id/"
NS_FX = "urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#"
NS_PDFA_SCHEMA = "http://www.aiim.org/pdfa/ns/schema#"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_PDF = "http://ns.adobe.com/pdf/1.3/"

FACTURX_NAME = "factur-x.xml"
LEGACY_NAMES = ("zugferd-invoice.xml", "xrechnung.xml", "ZUGFeRD-invoice.xml")
RELATIONSHIPS = {"Data", "Source", "Alternative"}
MAX_FONT_REPORTS = 10


def _f(rule, sev, msg, suggestion=None):
    return Finding(rule, sev, Source.PDFA, msg, suggestion=suggestion)


def _xmp_values(xmp: etree._Element | None, ns: str, name: str) -> list[str]:
    """Valeurs d'une propriété XMP, en attribut ou en élément (y compris rdf:Alt / rdf:Seq)."""
    if xmp is None:
        return []
    out = []
    for desc in xmp.iter(f"{{{NS_RDF}}}Description"):
        if (v := desc.get(f"{{{ns}}}{name}")) is not None:
            out.append(v.strip())
        for el in desc.findall(f"{{{ns}}}{name}"):
            texts = [t.strip() for t in el.itertext() if t.strip()]
            out.append(" ".join(texts))
    return out


class PdfaCheck(Check):
    id = "pdfa"
    label = "PDF/A-3 et Factur-X (structure)"
    order = 25

    def applies(self, doc):
        return doc.is_pdf

    def run(self, doc, ctx):
        import pikepdf

        data = doc.pdf_bytes or b""

        # PDFA-01 : en-tête et commentaire binaire
        head = data[:1024]
        if not re.match(rb"%PDF-1\.[0-7]", head):
            yield _f("PDFA-01", Severity.ERROR, "En-tête « %PDF-1.x » absent en début de fichier.")
        else:
            second = head.split(b"\n", 2)[1] if head.count(b"\n") >= 1 else b""
            second = second.lstrip(b"\r")
            if not (second.startswith(b"%") and sum(1 for b in second[1:5] if b > 127) >= 4):
                yield _f("PDFA-01", Severity.ERROR,
                         "Commentaire binaire (4 octets > 127) absent sur la 2e ligne du fichier.")

        try:
            pdf = pikepdf.open(io.BytesIO(data))
        except pikepdf.PasswordError:
            yield _f("PDFA-03", Severity.FATAL, "PDF chiffré : interdit en PDF/A.")
            return
        with pdf:
            if pdf.is_encrypted:
                yield _f("PDFA-03", Severity.FATAL, "PDF chiffré : interdit en PDF/A.")
            yield from self._trailer(pdf)
            xmp = self._xmp(pdf)
            yield from self._pdfa_id(xmp)
            yield from self._output_intent(pdf)
            yield from self._fonts(pdf)
            yield from self._actions(pdf)
            name = yield from self._attachment(pdf, doc)
            yield from self._facturx_xmp(xmp, name)
            yield from self._info_vs_xmp(pdf, xmp)

    # ------------------------------------------------------------------------------------------
    @staticmethod
    def _xmp(pdf) -> etree._Element | None:
        stream = pdf.Root.get("/Metadata")
        if stream is None:
            return None
        try:
            return etree.fromstring(stream.read_bytes(), parser=secure_parser())
        except Exception:
            return None

    @staticmethod
    def _trailer(pdf):
        if "/ID" not in pdf.trailer:
            yield _f("PDFA-07", Severity.ERROR, "Identifiant de fichier (/ID) absent du trailer.")

    @staticmethod
    def _pdfa_id(xmp):
        if xmp is None:
            yield _f("PDFA-02", Severity.ERROR, "Métadonnées XMP absentes ou illisibles : PDF/A non déclaré.")
            return
        part = next(iter(_xmp_values(xmp, NS_PDFAID, "part")), None)
        conf = next(iter(_xmp_values(xmp, NS_PDFAID, "conformance")), None)
        if part != "3":
            yield _f("PDFA-02", Severity.ERROR,
                     f"PDF/A-3 requis pour embarquer le XML : pdfaid:part = « {part or 'absent'} ».")
        if (conf or "").upper() not in {"A", "B", "U"}:
            yield _f("PDFA-02", Severity.ERROR, f"Niveau de conformité PDF/A invalide : « {conf or 'absent'} ».")

    @staticmethod
    def _output_intent(pdf):
        intents = pdf.Root.get("/OutputIntents")
        ok = False
        for oi in intents or []:
            if str(oi.get("/S")) == "/GTS_PDFA1" and oi.get("/DestOutputProfile") is not None:
                ok = True
        if not ok:
            yield _f("PDFA-04", Severity.ERROR,
                     "OutputIntent PDF/A (GTS_PDFA1) avec profil ICC absent : les couleurs ne sont pas définies.")

    @staticmethod
    def _fonts(pdf):
        """Polices servant à afficher du texte visible sans programme de police embarqué.

        ISO 19005-3 § 6.2.11.4.1 : l'obligation d'embarquement ne vaut que pour les polices utilisées
        pour le rendu ; une police déclarée mais inutilisée, ou servant exclusivement au texte invisible
        (mode de rendu 3, ex. couche de texte OCR), en est dispensée. On suit donc les opérateurs du
        flux de contenu (Tf, Tr, q/Q, Do) plutôt que les seules ressources.
        """
        import pikepdf

        missing: dict[str, int] = {}
        checked: set = set()
        visited: set = set()

        def font_embedded(font) -> bool:
            subtype = str(font.get("/Subtype"))
            if subtype == "/Type3":
                return True
            if subtype == "/Type0":
                desc = font.get("/DescendantFonts")
                font = desc[0] if desc else font
            fd = font.get("/FontDescriptor")
            return fd is not None and any(k in fd for k in ("/FontFile", "/FontFile2", "/FontFile3"))

        def check_font(font) -> None:
            key = font.objgen if font.is_indirect else id(font)
            if key in checked:
                return
            checked.add(key)
            if not font_embedded(font):
                name = str(font.get("/BaseFont", "?")).lstrip("/")
                missing[name] = missing.get(name, 0) + 1

        def check_all(resources) -> None:
            """Flux illisible : repli prudent sur toutes les polices déclarées."""
            fonts = resources.get("/Font") if resources is not None else None
            for _, font in (fonts.items() if fonts is not None else []):
                check_font(font)

        def walk(owner, resources, tr: int, depth: int = 0) -> None:
            key = (owner.objgen if owner.is_indirect else id(owner), tr)
            if resources is None or depth > 8 or key in visited:
                return
            visited.add(key)
            fonts = resources.get("/Font")
            xobjects = resources.get("/XObject")
            stack, font = [], None
            try:
                ops = pikepdf.parse_content_stream(owner)
            except Exception:
                check_all(resources)
                return
            for operands, op in ops:
                op = str(op)
                if op == "q":
                    stack.append(tr)
                elif op == "Q":
                    tr = stack.pop() if stack else tr
                elif op == "Tr" and operands:
                    tr = int(operands[0])
                elif op == "Tf" and operands:
                    font = fonts.get(str(operands[0])) if fonts is not None else None
                elif op in ("Tj", "TJ", "'", '"') and tr != 3 and font is not None:
                    check_font(font)
                elif op == "Do" and operands and xobjects is not None:
                    xo = xobjects.get(str(operands[0]))
                    if isinstance(xo, pikepdf.Stream) and str(xo.get("/Subtype")) == "/Form":
                        walk(xo, xo.get("/Resources") or resources, tr, depth + 1)

        for page in pdf.pages:
            walk(page.obj, page.obj.get("/Resources"), 0)
        for name in list(missing)[:MAX_FONT_REPORTS]:
            yield _f("PDFA-05", Severity.ERROR, f"Police non embarquée : {name}.")

    @staticmethod
    def _actions(pdf):
        bad: list[str] = []
        names = pdf.Root.get("/Names")
        if names is not None and "/JavaScript" in names:
            bad.append("JavaScript de document (/Names /JavaScript)")
        if "/AA" in pdf.Root:
            bad.append("actions automatiques du document (/AA)")
        open_action = pdf.Root.get("/OpenAction")
        if open_action is not None and hasattr(open_action, "get") and str(open_action.get("/S")) in (
                "/JavaScript", "/Launch"):
            bad.append(f"action d'ouverture {open_action.get('/S')}")
        for i, page in enumerate(pdf.pages, start=1):
            for annot in page.obj.get("/Annots") or []:
                action = annot.get("/A")
                if action is not None and str(action.get("/S")) in ("/JavaScript", "/Launch"):
                    bad.append(f"annotation page {i} ({action.get('/S')})")
        for what in bad[:10]:
            yield _f("PDFA-06", Severity.ERROR, f"Élément interdit en PDF/A : {what}.")

    @staticmethod
    def _attachment(pdf, doc):
        """Contrôle la pièce jointe XML ; renvoie son nom (ou None) au générateur appelant."""
        attachments = dict(pdf.attachments.items())
        name = doc.pdf_info.attachment_name if doc.pdf_info else None
        if name is None or name not in attachments:
            yield _f("PDFA-08", Severity.FATAL, "Aucune pièce jointe XML de facture dans le PDF.")
            return None
        if name in LEGACY_NAMES:
            yield _f("PDFA-08", Severity.WARNING, f"Pièce jointe nommée « {name} » : le nom attendu est "
                                                   f"« {FACTURX_NAME} ».", f"Renommer en {FACTURX_NAME}")
        elif name != FACTURX_NAME:
            yield _f("PDFA-08", Severity.ERROR, f"Pièce jointe « {name} » : le nom doit être « {FACTURX_NAME} ».",
                     f"Renommer en {FACTURX_NAME}")
        spec = attachments[name]
        rel = spec.obj.get("/AFRelationship")
        rel_name = str(rel).lstrip("/") if rel is not None else None
        if rel_name not in RELATIONSHIPS:
            yield _f("PDFA-08", Severity.ERROR,
                     f"AFRelationship de la pièce jointe = « {rel_name or 'absent'} » (attendu : Data, Source "
                     "ou Alternative).", "Pour Factur-X : /AFRelationship /Alternative (profils EN 16931 et plus)")
        af = pdf.Root.get("/AF")
        if af is None or not any(item.objgen == spec.obj.objgen for item in af if item.is_indirect):
            yield _f("PDFA-08", Severity.ERROR,
                     "La pièce jointe n'est pas référencée dans le tableau /AF du catalogue (fichier associé).")
        ef = spec.obj.get("/EF")
        stream = ef.get("/F") if ef is not None else None
        if stream is not None:
            subtype = str(stream.get("/Subtype", ""))
            if subtype not in ("/text#2Fxml", "/text/xml", "/application#2Fxml", "/application/xml"):
                yield _f("PDFA-08", Severity.WARNING,
                         f"Type MIME de la pièce jointe = « {subtype.lstrip('/') or 'absent'} » (attendu text/xml).")
            params = stream.get("/Params")
            if params is None or "/ModDate" not in params:
                yield _f("PDFA-08", Severity.WARNING,
                         "Date de modification (/Params /ModDate) absente sur la pièce jointe.")
        return name

    @staticmethod
    def _facturx_xmp(xmp, attachment_name):
        if xmp is None:
            return
        schemas = xmp.findall(f".//{{{NS_PDFA_SCHEMA}}}namespaceURI")
        schema_texts = {(s.text or "").strip() for s in schemas}
        schema_texts |= {v for v in _xmp_values(xmp, NS_PDFA_SCHEMA, "namespaceURI")}
        if NS_FX not in schema_texts:
            yield _f("PDFA-09", Severity.ERROR,
                     "Schéma d'extension XMP Factur-X (fx) non déclaré dans pdfaExtension:schemas.")
        file_name = next(iter(_xmp_values(xmp, NS_FX, "DocumentFileName")), None)
        doc_type = next(iter(_xmp_values(xmp, NS_FX, "DocumentType")), None)
        level = next(iter(_xmp_values(xmp, NS_FX, "ConformanceLevel")), None)
        if not level:
            yield _f("PDFA-09", Severity.ERROR, "fx:ConformanceLevel absent des métadonnées XMP.")
        if attachment_name and file_name != attachment_name:
            yield _f("PDFA-09", Severity.ERROR,
                     f"fx:DocumentFileName = « {file_name or 'absent'} » au lieu de « {attachment_name} ».")
        if (doc_type or "").upper() != "INVOICE":
            yield _f("PDFA-09", Severity.ERROR, f"fx:DocumentType = « {doc_type or 'absent'} » (attendu INVOICE).")

    @staticmethod
    def _info_vs_xmp(pdf, xmp):
        info = pdf.trailer.get("/Info")
        if info is None or xmp is None:
            return
        pairs = (("/Title", NS_DC, "title", "titre"), ("/Producer", NS_PDF, "Producer", "producteur"))
        for key, ns, name, label in pairs:
            if key not in info:
                continue
            value = str(info.get(key)).strip()
            xmp_vals = _xmp_values(xmp, ns, name)
            if value and value not in xmp_vals:
                yield _f("PDFA-10", Severity.WARNING,
                         f"Le {label} du dictionnaire Info (« {value[:60]} ») est absent ou différent dans le XMP.")


CHECK = PdfaCheck()
