"""Contrôle de structure (XSD de la syntaxe ou du profil Factur-X)."""
from __future__ import annotations

from fchecker.core import xsd
from fchecker.core.findings import Finding, Severity, Source
from fchecker.core.profiles import chain_for, pack

from . import Check

MAX_ERRORS = 200


class XsdCheck(Check):
    id = "xsd"
    label = "Structure (XSD)"
    order = 10

    def run(self, doc, ctx):
        chain = chain_for(doc)
        p = pack()
        if not chain.xsd:
            return
        if p is None or not p.has(chain.xsd):
            yield Finding("PACK-MISSING", Severity.INFO, Source.XSD, f"XSD introuvable : {chain.xsd}")
            return
        errors = xsd.validate(p.path(chain.xsd), doc.xml_tree)
        for err in errors[:MAX_ERRORS]:
            yield Finding("XSD", Severity.ERROR, Source.XSD, err.message, line=err.line, xpath=err.path)
        if len(errors) > MAX_ERRORS:
            yield Finding("XSD", Severity.INFO, Source.XSD,
                          f"{len(errors) - MAX_ERRORS} erreurs XSD supplémentaires non affichées.")

    def packs(self):
        p = pack()
        return {"XSD (FNFE)": p.version} if p else {}


CHECK = XsdCheck()
