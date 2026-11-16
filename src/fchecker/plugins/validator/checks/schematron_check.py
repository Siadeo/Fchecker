"""Règles de gestion : schematrons EN 16931 / profil et règles FR (BR-FR), via SaxonC."""
from __future__ import annotations

from fchecker.core.findings import Finding, Severity, Source
from fchecker.core.profiles import chain_for, pack
from fchecker.core.schematron import SchematronEngine
from fchecker.core.xpath_locator import locate

from . import Check

_FLAG = {
    "fatal": Severity.ERROR,
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "information": Severity.INFO,
    "info": Severity.INFO,
}


class SchematronCheck(Check):
    id = "schematron"
    label = "Règles de gestion (schematrons)"
    order = 20

    def run(self, doc, ctx):
        p = pack()
        engine = SchematronEngine.instance()
        for spec in chain_for(doc).schematrons:
            ctx.check_cancelled()
            if p is None or not p.has(spec.rel_path):
                yield Finding("PACK-MISSING", Severity.INFO, spec.source, f"Schematron introuvable : {spec.label}")
                continue
            ctx.progress(0, spec.label)
            try:
                results = engine.validate(p.path(spec.rel_path), doc.xml_text)
            except Exception as exc:
                # Erreur (et non avertissement) : les règles n'ont PAS été vérifiées, la facture ne
                # doit pas pouvoir apparaître conforme.
                yield Finding("SCH-ERROR", Severity.ERROR, spec.source,
                              f"{spec.label} : règles non vérifiées (erreur technique : {exc})")
                continue
            seen: set[tuple] = set()
            for r in results:
                line = locate(doc.root, r.location)
                key = (r.rule_id, line, r.text)
                if key in seen:
                    continue
                seen.add(key)
                yield Finding(
                    rule_id=r.rule_id,
                    severity=_FLAG.get((r.flag or "").lower(), Severity.ERROR),
                    source=spec.source,
                    message=r.text,
                    bt=r.bts[0] if r.bts else None,
                    xpath=r.location,
                    line=line,
                )

    def packs(self):
        p = pack()
        return {"Schematrons FNFE (EN 16931, BR-FR, Factur-X)": p.version} if p else {}


CHECK = SchematronCheck()
