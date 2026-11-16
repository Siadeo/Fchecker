"""Logique des mentions obligatoires. Chaque fonction ``men_xx(inv, doc)`` renvoie un :class:`Outcome`.

Une mention couverte par une règle officielle (``covered_by``) est évaluée pour la check-list,
mais ses constats de *présence* ne sont pas émis (le validateur les porte déjà).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

from fchecker.core.document import DocFormat, InvoiceDocument
from fchecker.core.findings import Finding, Severity, Source
from fchecker.core.invoice import Invoice


class Status(str, Enum):
    OK = "Présente"
    MISSING = "Absente"
    CHECK = "À vérifier"
    NA = "Sans objet"
    INFO = "Information"


@dataclass
class Outcome:
    status: Status
    detail: str
    findings: list[Finding] = field(default_factory=list)
    presence_only: bool = False  # True : le constat ne porte que sur la présence (donc couvert si covered_by)


def _fold(text: str | None) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def _finding(rule: str, sev: Severity, msg: str, bt: str | None, line: int | None, suggestion: str | None = None):
    return Finding(rule, sev, Source.MENTIONS, msg, bt=bt, line=line, suggestion=suggestion)


BT23_CODES = {"B1", "S1", "M1", "B2", "S2", "M2", "S3", "B4", "S4", "M4", "S5", "S6", "B7", "S7",
              "B8", "S8", "M8", "B9", "S9", "M9"}


def _kind(inv: Invoice) -> str | None:
    """B (biens), S (services), M (mixte) d'après BT-23."""
    code = (inv.business_process or "").strip().upper()
    return code[:1] if code[:1] in ("B", "S", "M") else None


def men_01(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    code = (inv.business_process or "").strip().upper()
    if not code:
        return Outcome(Status.MISSING, "Cadre de facturation (BT-23) absent.", presence_only=True)
    if code not in BT23_CODES:
        return Outcome(Status.MISSING, f"Code « {code} » hors liste de la réforme.", presence_only=True)
    label = {"B": "livraison de biens", "S": "prestation de services", "M": "facture mixte"}[code[0]]
    return Outcome(Status.OK, f"{code} — {label}.")


def men_02(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    buyer = inv.buyer
    if buyer.siren:
        return Outcome(Status.OK, f"SIREN {buyer.siren}.")
    b2b_note = any(n.code == "BAR" and "B2B" in n.content.upper() for n in inv.notes)
    french = (buyer.address.country or "").upper() == "FR" or (buyer.vat_id and buyer.vat_id.text.upper().startswith("FR"))
    if b2b_note:  # BR-FR-11 s'applique : pas de doublon
        return Outcome(Status.MISSING, "SIREN absent (signalé par BR-FR-11).", presence_only=True)
    if french:
        return Outcome(Status.MISSING, "SIREN du client français absent.", [
            _finding("MEN-02", Severity.WARNING, "SIREN du client (BT-47) absent alors que le client est établi en "
                     "France (mention obligatoire pour une opération B2B domestique).", "BT-47",
                     inv.lines_of.get("BG-7"))])
    return Outcome(Status.NA, "Client non établi en France.")


DELIVERY_ADDRESS_FROM = date(2027, 9, 1)  # G6.16 : obligation à partir du 01/09/2027


def _same_address(a, b) -> bool:
    def key(x):
        return (_fold(" ".join(x.lines)), _fold(x.city), (x.postcode or "").replace(" ", ""), (x.country or "").upper())
    return key(a) == key(b)


def men_03(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    """G6.16 (DGFiP) : si l'adresse de livraison diffère de celle de l'acheteur (BG-8), BT-75, BT-77,
    BT-78 et BT-80 sont obligatoires — à partir du 01/09/2027, pas pour les services ; règle impossible à
    vérifier automatiquement (on ne sait pas si les adresses désignent le même lieu)."""
    kind = _kind(inv)
    if kind == "S":
        return Outcome(Status.NA, "Prestation de services : non concernée (G6.16).")
    d = inv.deliver_to
    in_force = inv.issue_date is not None and inv.issue_date >= DELIVERY_ADDRESS_FROM
    when = "" if in_force else " (obligatoire à partir du 01/09/2027)"
    if not d.is_empty:
        if _same_address(d, inv.buyer.address):
            return Outcome(Status.OK, "Identique à l'adresse de l'acheteur.")
        missing = [label for label, v in (("ligne 1 (BT-75)", d.lines[0] if d.lines else None),
                                          ("localité (BT-77)", d.city), ("code postal (BT-78)", d.postcode),
                                          ("pays (BT-80)", d.country)) if not v]
        if missing:
            return Outcome(Status.MISSING, f"Adresse de livraison incomplète{when}.", [
                _finding("MEN-03", Severity.WARNING if in_force else Severity.INFO,
                         f"Adresse de livraison (BG-15) différente de celle de l'acheteur mais incomplète : "
                         f"{', '.join(missing)} manquant(s){when}.", "BG-15", d.line or inv.lines_of.get("BG-13"))])
        return Outcome(Status.OK, d.one_line())
    if kind in ("B", "M"):
        return Outcome(Status.CHECK, f"Absente : à fournir si les biens sont livrés ailleurs qu'à l'adresse de "
                                     f"l'acheteur{when}.", [
            _finding("MEN-03", Severity.INFO, "Adresse de livraison (BG-15) absente sur une facture de biens : "
                     f"elle doit figurer si elle diffère de l'adresse de l'acheteur{when} (G6.16, règle non "
                     "contrôlable automatiquement).", "BG-15", inv.lines_of.get("BG-7"))])
    return Outcome(Status.NA, "Catégorie d'opération inconnue.")


def men_04(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    code = (inv.vat_point_code or "").strip()
    ubl = doc.format is DocFormat.UBL
    debit_code = "3" if ubl else "5"
    # G1.43, G1.44 : option débits = BT-8 à 5 (CII) / 3 (UBL) ; 29 (CII) / 35 (UBL) acceptés aussi.
    debit_codes = {"3", "35"} if ubl else {"5", "29"}
    kind = _kind(inv)
    if code in debit_codes:
        # Les exemples officiels FNFE (UC12, UC13) portent aussi BT-8 = 5/3 sur des factures B1 :
        # aucune remarque dans ce cas.
        return Outcome(Status.OK, f"Option débits déclarée (BT-8 = {code}).")
    if kind in ("S", "M") and not code:
        # G1.67 : « règle métier, non contrôlable applicativement » → simple information.
        return Outcome(Status.CHECK, "Non déclarée : obligatoire seulement si l'option a été exercée.", [
            _finding("MEN-04", Severity.INFO, "Prestation de services sans BT-8 : si l'entreprise a opté pour la "
                     "TVA sur les débits, la facture doit l'indiquer (BT-8 = " + debit_code + ").", "BT-8",
                     inv.lines_of.get("BT-8"))])
    return Outcome(Status.NA, "Non concernée." if not code else f"BT-8 = {code} (autre date d'exigibilité).")


_RATE = re.compile(r"\d+(?:[.,]\d+)?\s*%|taux\s+(?:d.int[eé]r[eê]t\s+)?(?:l[eé]gal|directeur|de la bce|refi)|bce", re.I)


def men_05(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    notes = inv.notes_with("PMD")
    if not notes:
        return Outcome(Status.MISSING, "Note PMD absente (signalée par BR-FR-05).", presence_only=True)
    text = " ".join(n.content for n in notes)
    if not _RATE.search(text):
        return Outcome(Status.CHECK, "Taux non identifiable.", [
            _finding("MEN-05", Severity.WARNING, f"La mention des pénalités de retard ne précise pas de taux : "
                     f"« {text[:120]} ».", "BT-22", notes[0].line,
                     "Indiquer le taux (ex. « 3 fois le taux d'intérêt légal » ou un pourcentage).")])
    return Outcome(Status.OK, text[:120])


_AMOUNT = re.compile(r"(\d{1,6}(?:[.,]\d{1,2})?)\s*(?:€|eur|euros?)|(?:€|eur)\s*(\d{1,6}(?:[.,]\d{1,2})?)", re.I)


def men_06(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    notes = inv.notes_with("PMT")
    if not notes:
        return Outcome(Status.MISSING, "Note PMT absente (signalée par BR-FR-05).", presence_only=True)
    text = " ".join(n.content for n in notes)
    amounts = [Decimal((a or b).replace(",", ".")) for a, b in _AMOUNT.findall(text)]
    if not amounts:
        return Outcome(Status.CHECK, "Montant non identifiable.", [
            _finding("MEN-06", Severity.WARNING, f"La mention de l'indemnité forfaitaire ne précise pas son montant : "
                     f"« {text[:120]} ».", "BT-22", notes[0].line, "Indiquer « 40 € ».")])
    amount = f"{max(amounts):.2f}".replace(".", ",")
    if max(amounts) < 40:
        return Outcome(Status.MISSING, f"Montant {amount} € inférieur à 40 €.", [
            _finding("MEN-06", Severity.ERROR, f"Indemnité forfaitaire de {amount} € : le minimum légal est "
                     "de 40 € (art. D441-5 du Code de commerce).", "BT-22", notes[0].line)])
    return Outcome(Status.OK, f"{amount} €.")


def men_07(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    notes = inv.notes_with("AAB")
    if not notes:
        return Outcome(Status.MISSING, "Note AAB absente (signalée par BR-FR-05).", presence_only=True)
    return Outcome(Status.OK, notes[0].content[:120])


def men_08(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    if inv.due_date:
        return Outcome(Status.OK, f"Échéance le {inv.due_date:%d/%m/%Y}.")
    if inv.payment_terms:
        return Outcome(Status.OK, inv.payment_terms[:120])
    if inv.totals.due is not None and inv.totals.due <= 0:
        return Outcome(Status.NA, "Rien à payer.")
    return Outcome(Status.MISSING, "Ni échéance (BT-9) ni conditions de paiement (BT-20) — voir BR-CO-25.",
                   presence_only=True)


def men_09(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    ae = [v for v in inv.vat_breakdown if (v.category or "").upper() == "AE"]
    if not ae and "AE" not in inv.vat_categories:
        return Outcome(Status.NA, "Pas d'autoliquidation.")
    texts = " ".join(_fold(v.exemption_reason) for v in ae) + " " + " ".join(_fold(n.content) for n in inv.notes)
    if "autoliquidation" in texts:
        return Outcome(Status.OK, "Mention « Autoliquidation » présente.")
    has_code = any((v.exemption_code or "").upper() == "VATEX-EU-AE" for v in ae)
    line = ae[0].line if ae else None
    if has_code:
        return Outcome(Status.CHECK, "Code VATEX-EU-AE sans le texte « Autoliquidation ».", [
            _finding("MEN-09", Severity.WARNING, "Autoliquidation codée (VATEX-EU-AE) sans le texte « Autoliquidation » "
                     "exigé par la loi.", "BT-120", line, "Motif d'exonération (BT-120) : « Autoliquidation »")])
    return Outcome(Status.MISSING, "Mention « Autoliquidation » absente.", [
        _finding("MEN-09", Severity.ERROR, "Opération en autoliquidation (catégorie AE) sans la mention "
                 "« Autoliquidation ».", "BT-120", line, "Motif d'exonération (BT-120) : « Autoliquidation »")])


FRANCHISE_CODE = "VATEX-FR-FRANCHISE"


# Mention de franchise en base. Recodification de la TVA dans le CIBS (ordonnance n° 2025-1247) :
# L. 233-3 du CIBS à compter du 01/01/2027 (impots.gouv.fr) ; renvois au CGI admis jusqu'au 31/12/2027
# (BOI-RES-TVA-000253).
CIBS_FROM = date(2027, 1, 1)
_FRANCHISE_REF = re.compile(r"293\s*b\b|l\.?\s*233-3")


def franchise_mention(today: date | None = None) -> str:
    if (today or date.today()) >= CIBS_FROM:
        return "TVA non applicable, article L. 233-3 du CIBS"
    return "TVA non applicable, art. 293 B du CGI"


def men_10(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    """Franchise en base = détail TVA avec BT-118 = « E » ET BT-121 = « VATEX-FR-FRANCHISE » ; un vendeur sans
    n° de TVA reporte son SIREN en BT-32. (Absent des schematrons FNFE : contrôlé ici.)
    Avertissement seulement : obligation incertaine, la règle G1.47 de la DGFiP évoque le code « Z » pour la franchise."""
    exempt = [v for v in inv.vat_breakdown if (v.category or "").upper() == "E"]
    seller = inv.seller
    franchise = [v for v in exempt if (v.exemption_code or "").upper() == FRANCHISE_CODE]
    if franchise:
        if seller.vat_id is None:
            siren = seller.siren
            bt32 = seller.tax_registration.text.replace(" ", "") if seller.tax_registration else None
            if not bt32:
                return Outcome(Status.MISSING, "SIREN non répété en BT-32.", [
                    _finding("MEN-10", Severity.WARNING, "Franchise en base : un vendeur sans n° de TVA (BT-31) "
                             "reporte son SIREN en BT-32.", "BT-32",
                             inv.lines_of.get("BG-4"),
                             f"BT-32 (schéma FC) : {siren}" if siren else "BT-32 (schéma FC) : SIREN du vendeur")])
            if siren and bt32 != siren:
                return Outcome(Status.CHECK, f"BT-32 « {bt32} » différent du SIREN {siren}.", [
                    _finding("MEN-10", Severity.WARNING, f"Franchise en base : BT-32 « {bt32} » devrait reprendre le "
                             f"SIREN du vendeur ({siren}).", "BT-32", seller.tax_registration.line)])
        return Outcome(Status.OK, f"Franchise en base codée ({FRANCHISE_CODE}).")
    if not exempt:
        return Outcome(Status.NA, "Non concernée.")
    texts = " ".join(_fold(v.exemption_reason) for v in exempt)
    if _FRANCHISE_REF.search(texts):
        return Outcome(Status.MISSING, f"Référence à la franchise en base sans le code {FRANCHISE_CODE}.", [
            _finding("MEN-10", Severity.WARNING, "Franchise en base citée en texte (293 B du CGI ou L. 233-3 du "
                     "CIBS) sans le code "
                     f"d'exonération {FRANCHISE_CODE} en BT-121, prévu pour la franchise en base.", "BT-121", exempt[0].line,
                     f"BT-121 : {FRANCHISE_CODE}")])
    if seller.vat_id is None and (seller.address.country or "").upper() == "FR":
        return Outcome(Status.CHECK, "Vendeur sans n° de TVA, exonération non codée en franchise.", [
            _finding("MEN-10", Severity.WARNING, "Vendeur français sans n° de TVA et opération exonérée (catégorie E) : "
                     f"s'il relève de la franchise en base, le code {FRANCHISE_CODE} (BT-121) et la répétition du "
                     "SIREN en BT-32 sont attendus.", "BT-121", exempt[0].line,
                     f"BT-121 : {FRANCHISE_CODE} ; BT-120 : « {franchise_mention()} »")])
    return Outcome(Status.NA, "Exonération autre que la franchise en base.")


def men_11(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    if not inv.self_billed:
        return Outcome(Status.NA, "Pas une autofacture.")
    # Exemples officiels FNFE (UC13) : l'autofacturation est portée par le code type BT-3, sans note ;
    # la mention « Autofacturation » apparaît dans la représentation lisible.
    label = "note présente" if any("autofactur" in _fold(n.content) for n in inv.notes) else "code type"
    return Outcome(Status.OK, f"Autofacture signalée par BT-3 = {inv.type_code} ({label}).")


def men_12(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    info = inv.seller.legal_info
    # Exemples officiels FNFE : BT-33, ou notes REG (capital, forme) et ABL (RCS).
    notes = inv.notes_with("REG") + inv.notes_with("ABL")
    if info is not None and re.search(r"[A-Za-z]{2,}", info.text):
        return Outcome(Status.OK, info.text[:120])
    if notes:
        return Outcome(Status.OK, " · ".join(n.content for n in notes)[:120])
    shown = f"« {info.text} »" if info else "absentes"
    return Outcome(Status.CHECK, f"Informations juridiques {shown}.", [
        _finding("MEN-12", Severity.WARNING, f"Informations juridiques du vendeur {shown} (ni BT-33 exploitable, ni "
                 "note REG / ABL) : forme juridique, capital social et RCS doivent figurer sur la facture d'une "
                 "société.", "BT-33", info.line if info else inv.lines_of.get("BG-4"),
                 "BT-33 ou notes REG / ABL, ex. « SAS au capital de 10 000 € » (REG) et « RCS Paris 100 000 009 » (ABL)")])


def _core_name(name) -> str:
    return re.sub(r"\b(sas|sasu|sarl|sa|eurl|snc|sci)\b", "", _fold(name.text if name else "")).strip()


def men_13(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    """Facturation par un mandataire : il peut se déclarer en Tiers Facturant
    (EXT-FR-FE-BG-05) ; le BOI-TVA-DECLA-30-20-10-30 § 210 RECOMMANDE la mention « facture établie par A
    au nom et pour le compte de B », portée en note DCL (BT-21) / BT-22."""
    notes = inv.notes_with("DCL")
    if not inv.issued_by_mandatary:
        return Outcome(Status.NA, "Pas de mandat de facturation déclaré.")
    if not notes:
        name = inv.invoicer.name.text if inv.invoicer and inv.invoicer.name else "déclaré"
        return Outcome(Status.CHECK, f"Tiers Facturant {name} sans mention de mandat.", [
            _finding("MEN-13", Severity.INFO, f"Facture émise par un Tiers Facturant ({name}) sans la mention "
                     "« facture établie par A au nom et pour le compte de B », recommandée par la doctrine fiscale.",
                     "BG-1", inv.lines_of.get("BG-1"),
                     "Note DCL (BT-21) : « Facture établie par <mandataire> au nom et pour le compte de <vendeur> »")])
    text = _fold(" ".join(n.content for n in notes))
    seller = _core_name(inv.seller.name)
    if seller and seller not in text:
        return Outcome(Status.CHECK, "Le vendeur n'est pas cité dans la mention de mandat.", [
            _finding("MEN-13", Severity.WARNING, "La mention de mandat (note DCL) ne cite pas le vendeur (BG-4) : "
                     "la facture est établie « au nom et pour le compte » du vendeur, qui doit y être nommé.",
                     "BG-1", notes[0].line)])
    invoicer = _core_name(inv.invoicer.name) if inv.invoicer else ""
    if invoicer and invoicer not in text:
        return Outcome(Status.CHECK, "Le Tiers Facturant n'est pas cité dans la mention de mandat.", [
            _finding("MEN-13", Severity.INFO, "La mention de mandat (note DCL) ne cite pas le Tiers Facturant déclaré "
                     "(EXT-FR-FE-BG-05) comme auteur de la facture.", "BG-1", notes[0].line)])
    return Outcome(Status.OK, notes[0].content[:120])


def men_14(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    """G1.39 : date de livraison / de fin d'exécution (BT-72), date de livraison à la ligne ou période de
    facturation (BG-26), « dans la mesure où elle est déterminée et différente de la date d'émission »
    (CGI art. 242 nonies A, 10°). Règle non contrôlable applicativement : simple rappel."""
    if inv.delivery_date:
        return Outcome(Status.OK, f"Livraison / exécution le {inv.delivery_date:%d/%m/%Y} (BT-72).")
    if inv.period_start or inv.period_end:
        start = f"{inv.period_start:%d/%m/%Y}" if inv.period_start else "…"
        end = f"{inv.period_end:%d/%m/%Y}" if inv.period_end else "…"
        return Outcome(Status.OK, f"Période de facturation du {start} au {end} (BG-26).")
    return Outcome(Status.CHECK, "Ni date de livraison (BT-72) ni période (BG-26).", [
        _finding("MEN-14", Severity.INFO, "Ni date de livraison / d'exécution (BT-72) ni période de facturation "
                 "(BG-26) : à fournir si elle est déterminée et différente de la date d'émission (G1.39).",
                 "BT-72", inv.lines_of.get("BG-13") or inv.lines_of.get("BT-2"))])


def men_15(inv: Invoice, doc: InvoiceDocument) -> Outcome:
    """Code de commerce art. L441-9 : la facture mentionne le numéro du bon de commande « lorsqu'il a été
    préalablement établi par l'acheteur ». L'outil ne peut pas savoir s'il existe : simple rappel."""
    if inv.order_reference:
        return Outcome(Status.OK, f"Bon de commande {inv.order_reference} (BT-13).")
    return Outcome(Status.CHECK, "Pas de numéro de bon de commande (BT-13).", [
        _finding("MEN-15", Severity.INFO, "Pas de numéro de bon de commande (BT-13) : à indiquer si l'acheteur a "
                 "établi un bon de commande (art. L441-9 du Code de commerce).", "BT-13", inv.lines_of.get("BT-2"))])


PREDICATES = {f"MEN-{i:02d}": fn for i, fn in enumerate(
    (men_01, men_02, men_03, men_04, men_05, men_06, men_07, men_08, men_09, men_10, men_11, men_12, men_13,
     men_14, men_15), start=1)}
