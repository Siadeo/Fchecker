"""Annuaire Peppol : l'adresse électronique du DESTINATAIRE y est-elle inscrite, pour ce format de facture ?

Tous les schémas d'adresse sont interrogeables (0225, 0009, 0002, 9957…). Destinataire : l'acheteur (BT-49), ou le vendeur
(BT-34) pour une autofacture.

L'annuaire Peppol est public et facultatif : une absence n'est qu'un avertissement.
Le SMP de l'adresse et les types de documents qu'il publie complètent la fiche (``details``, ``listing``).
Contrôle *concurrent* : données extraites dans ``prepare``, appel réseau en parallèle des autres contrôles.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from fchecker.core.document import DocFormat
from fchecker.core.findings import Finding, Severity, Source
from fchecker.core.invoice import Value, invoice_of
from fchecker.core.services.peppol import (
    LookupStatus,
    PeppolClient,
    PeppolResult,
    SmpClient,
    SmpResult,
    accepts,
    short_doc_type,
)

from . import Check


@dataclass(frozen=True)
class PeppolData:
    role: str                 # acheteur | vendeur
    address: Value | None
    bt_addr: str              # BT-49 (acheteur) / BT-34 (vendeur)
    line: int | None          # ligne du BG-7 / BG-4
    format: DocFormat

    @property
    def of_role(self) -> str:
        return "de l'acheteur" if self.role == "acheteur" else f"du {self.role}"


class PeppolCheck(Check):
    id = "peppol"
    label = "Annuaire Peppol"
    order = 41
    concurrent = True

    def __init__(self, client_factory=PeppolClient.from_settings, smp_factory=SmpClient.from_settings) -> None:
        self.client_factory = client_factory
        self.smp_factory = smp_factory

    def prepare(self, doc) -> PeppolData:
        inv = invoice_of(doc)
        if inv.self_billed:  # autofacture : facture destinée au vendeur
            return PeppolData("vendeur", inv.seller.electronic_address, "BT-34", inv.lines_of.get("BG-4"), doc.format)
        return PeppolData("acheteur", inv.buyer.electronic_address, "BT-49", inv.lines_of.get("BG-7"), doc.format)

    def run(self, data: PeppolData, ctx):
        client = self.client_factory()
        if client is None:
            yield Finding("PEP-06", Severity.INFO, Source.PEPPOL,
                          "Vérification dans l'annuaire Peppol désactivée (Paramètres).")
            return
        addr, bt = data.address, data.bt_addr
        if addr is None or not addr.scheme or not addr.text:
            yield Finding("PEP-00", Severity.INFO, Source.PEPPOL,
                          f"Annuaire Peppol non interrogé : adresse électronique {data.of_role} ({bt}) "
                          "absente ou sans schéma.", bt=bt, line=addr.line if addr else data.line)
            return

        result: PeppolResult = client.lookup(addr.scheme, addr.text)
        label = result.participant
        if result.status is LookupStatus.REJECTED:
            yield Finding("PEP-03", Severity.WARNING, Source.PEPPOL,
                          f"Adresse {data.of_role} « {label} » refusée par l'annuaire Peppol ({result.error}) : "
                          "adresse mal formée ou inexistante.", bt=bt, line=addr.line)
            return
        if result.status is not LookupStatus.OK:
            yield Finding("PEP-06", Severity.INFO, Source.PEPPOL,
                          f"Annuaire Peppol injoignable ({result.error}) : adresse {data.of_role} « {label} » "
                          "non vérifiée.", bt=bt, line=addr.line)
            return

        cache = " (cache)" if result.from_cache else ""
        if not result.matches:
            finding = Finding("PEP-01", Severity.WARNING, Source.PEPPOL,
                              f"Adresse électronique {data.of_role} « {label} » absente de l'annuaire Peppol{cache}.",
                              bt=bt, line=addr.line)
        elif not accepts(result.doc_types, data.format):
            announced = ", ".join(dict.fromkeys(short_doc_type(d) for d in result.doc_types)) or "aucun"
            finding = Finding("PEP-02", Severity.WARNING, Source.PEPPOL,
                              f"Adresse {data.of_role} « {label} » inscrite dans l'annuaire Peppol{cache}, mais sans "
                              f"type de document {data.format.value} annoncé.", bt=bt, line=addr.line,
                              suggestion=f"Types de documents annoncés : {announced}")
        else:
            finding = Finding("PEP-OK", Severity.INFO, Source.PEPPOL,
                              f"Adresse {data.of_role} « {label} » inscrite dans l'annuaire Peppol pour le format "
                              f"{data.format.value}{cache}.", bt=bt, line=addr.line)
        yield self._with_smp(finding, addr)

    def _with_smp(self, finding: Finding, addr: Value) -> Finding:
        """Complète la fiche avec le SMP de l'adresse et les types de documents qu'il publie (information)."""
        client = self.smp_factory()
        if client is None:
            return finding
        smp: SmpResult = client.lookup(addr.scheme, addr.text)
        if smp.status is not LookupStatus.OK:
            return replace(finding, details=f"SMP non déterminé ({smp.error}).")
        if not smp.exists:
            return replace(finding, details="Aucun SMP enregistré pour cette adresse sur le réseau Peppol.")
        n = len(smp.doc_types)
        count = (f"{n} types de documents acceptés (voir ci-dessous)." if n > 1 else
                 "1 type de document accepté : voir le type de document ci-dessous." if n else
                 "Aucun type de document publié.")
        return replace(finding, details=f"SMP : {smp.host or 'non indiqué'}. {count}",
                       listing_title="Types de documents acceptés par le SMP" if n else None,
                       listing=tuple(d.name + (" (obsolète)" if d.deprecated else "") for d in smp.doc_types))


CHECK = PeppolCheck()
