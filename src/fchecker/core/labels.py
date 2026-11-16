"""Libellés français des listes de codes courantes (affichage : visionneuse, rapport)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

TYPE_CODES = {
    "380": "Facture", "381": "Avoir", "384": "Facture rectificative", "386": "Facture d'acompte",
    "389": "Autofacture", "393": "Facture affacturée", "261": "Avoir auto-facturé", "396": "Avoir affacturé",
    "500": "Facture d'acompte auto-facturée", "501": "Autofacture affacturée", "502": "Avoir auto-facturé affacturé",
    "503": "Avoir de facture d'acompte", "471": "Facture rectificative auto-facturée",
    "472": "Facture rectificative affacturée", "473": "Facture rectificative auto-facturée affacturée",
    "262": "Avoir remise globale",
}
BUSINESS_PROCESS = {
    "B1": "Livraison de biens", "S1": "Prestation de services", "M1": "Facture double (biens et services)",
    "B2": "Biens — facture déjà payée", "S2": "Services — facture déjà payée", "M2": "Double — déjà payée",
    "S3": "Services — facture de sous-traitance", "B4": "Biens — facture définitive après acompte",
    "S4": "Services — facture définitive après acompte", "M4": "Double — définitive après acompte",
    "S5": "Services — dépôt par un sous-traitant", "S6": "Services — dépôt par un cotraitant",
    "B7": "Biens — déjà soumise à e-reporting", "S7": "Services — déjà soumise à e-reporting",
    "B8": "Biens — facture multi-vendeurs", "S8": "Services — facture multi-vendeurs",
    "M8": "Double — facture multi-vendeurs", "B9": "Biens — facture bidirectionnelle",
    "S9": "Services — facture bidirectionnelle", "M9": "Double — facture bidirectionnelle",
}
VAT_CATEGORIES = {
    "S": "Taux normal", "Z": "Taux zéro", "E": "Exonéré", "AE": "Autoliquidation", "K": "Livraison intracommunautaire",
    "G": "Exportation hors UE", "O": "Hors champ de la TVA", "L": "IGIC (Canaries)", "M": "IPSI (Ceuta, Melilla)",
}
PAYMENT_MEANS = {
    "10": "Espèces", "20": "Chèque", "30": "Virement", "31": "Virement", "42": "Paiement sur compte bancaire",
    "48": "Carte bancaire", "49": "Prélèvement", "57": "Ordre permanent", "58": "Virement SEPA",
    "59": "Prélèvement SEPA", "97": "Compensation", "1": "Non défini",
}
NOTE_SUBJECTS = {
    "PMD": "Pénalités de retard", "PMT": "Indemnité forfaitaire de recouvrement", "AAB": "Escompte",
    "DCL": "Mandat de facturation", "BAR": "Type de traitement", "TXD": "Mention fiscale", "AAI": "Information",
    "REG": "Informations réglementaires", "SUR": "Remarques", "ABL": "Informations légales",
}
VAT_POINT = {"3": "Date de facture (option débits)", "5": "Date de facture (option débits)", "29": "Date de livraison",
             "35": "Date de livraison", "72": "Date de paiement", "432": "Date de paiement"}


def label(table: dict, code: str | None) -> str:
    if not code:
        return ""
    return f"{table[code]} ({code})" if code in table else code


def money(value: Decimal | None, currency: str | None = None) -> str:
    if value is None:
        return ""
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return f"{text} {currency}" if currency else text


def number(value: Decimal | None) -> str:
    if value is None:
        return ""
    text = format(value.normalize(), "f") if value == value.to_integral() else format(value, "f")
    return text.replace(".", ",")


def day(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""
