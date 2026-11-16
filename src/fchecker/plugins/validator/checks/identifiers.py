"""Contrôles algorithmiques d'identifiants : Luhn SIREN/SIRET, clé TVA FR, IBAN, BIC.

Les contrôles de format déjà faits par les règles BR-FR (9/14 chiffres, SIRET commençant
par le SIREN) ne sont pas répétés ici.
"""
from __future__ import annotations

import re

from fchecker.core import ids
from fchecker.core.findings import Finding, Severity, Source
from fchecker.core.invoice import invoice_of

from . import Check

_BIC = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")
_ROLES = (("seller", "du vendeur", "BT-30", "BT-31", "BT-29"), ("buyer", "de l'acheteur", "BT-47", "BT-48", "BT-46"))


def _f(rule, sev, msg, bt, line, suggestion=None):
    return Finding(rule, sev, Source.IDENTIFIERS, msg, bt=bt, line=line, suggestion=suggestion)


class IdentifiersCheck(Check):
    id = "identifiers"
    label = "Identifiants (SIREN, SIRET, TVA, IBAN)"
    order = 30

    def run(self, doc, ctx):
        inv = invoice_of(doc)
        for attr, of_role, bt_siren, bt_vat, bt_ids in _ROLES:
            party = getattr(inv, attr)
            siren = party.legal_id
            if siren and siren.scheme in (None, "0002") and re.fullmatch(r"\d{9}", siren.text) \
                    and not ids.is_valid_siren(siren.text):
                yield _f("ID-SIREN", Severity.ERROR, f"SIREN {of_role} « {siren.text} » invalide (clé de Luhn).",
                         bt_siren, siren.line)
            for siret in party.sirets:
                if re.fullmatch(r"\d{14}", siret.text) and not ids.is_valid_siret(siret.text):
                    yield _f("ID-SIRET", Severity.ERROR, f"SIRET {of_role} « {siret.text} » invalide (clé de Luhn).",
                             bt_ids, siret.line)
            vat = party.vat_id
            if vat and vat.text.upper().startswith("FR"):
                if not ids.is_valid_fr_vat(vat.text):
                    embedded = ids.siren_from_fr_vat(vat.text)
                    if embedded is None:
                        yield _f("ID-TVA-CLE", Severity.ERROR,
                                 f"Numéro de TVA {of_role} « {vat.text} » mal formé : attendu FR + clé (2 caractères) "
                                 "+ SIREN (9 chiffres), soit 13 caractères.", bt_vat, vat.line,
                                 f"TVA attendue : {ids.fr_vat_from_siren(siren.text)}"
                                 if siren and re.fullmatch(r"\d{9}", siren.text) else None)
                    else:
                        yield _f("ID-TVA-CLE", Severity.ERROR,
                                 f"Numéro de TVA {of_role} « {vat.text} » invalide (clé incorrecte).", bt_vat,
                                 vat.line, f"Numéro attendu pour ce SIREN : {ids.fr_vat_from_siren(embedded)}")
                else:
                    embedded = ids.siren_from_fr_vat(vat.text)
                    if embedded and siren and re.fullmatch(r"\d{9}", siren.text) and embedded != siren.text:
                        yield _f("ID-TVA-SIREN", Severity.ERROR,
                                 f"Le numéro de TVA {of_role} ({vat.text}) ne correspond pas à son SIREN ({siren.text}).",
                                 bt_vat, vat.line, f"TVA attendue : {ids.fr_vat_from_siren(siren.text)}")

        buyer = inv.buyer
        addr = buyer.electronic_address
        if addr and addr.scheme == "0225" and buyer.siren:
            addr_siren = addr.text.split("_", 1)[0]
            if re.fullmatch(r"\d{9}", addr_siren) and addr_siren != buyer.siren:
                yield _f("ID-ADR-SIREN", Severity.WARNING,
                         f"L'adresse électronique de l'acheteur « {addr.text} » ne commence pas par son SIREN "
                         f"({buyer.siren}).", "BT-49", addr.line)

        for iban in inv.ibans:
            if not ids.is_valid_iban(iban.text):
                yield _f("ID-IBAN", Severity.ERROR, f"IBAN « {iban.text} » invalide (longueur ou clé mod 97).",
                         "BT-84", iban.line)
        for bic in inv.bics:
            if not _BIC.match(bic.text.replace(" ", "").upper()):
                yield _f("ID-BIC", Severity.WARNING, f"BIC « {bic.text} » mal formé (8 ou 11 caractères ISO 9362).",
                         "BT-86", bic.line)


CHECK = IdentifiersCheck()
