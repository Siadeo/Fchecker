"""Profil de la facture au regard de la réforme et cohérence XMP ↔ XML."""
from __future__ import annotations

from fchecker.core.document import DocFormat
from fchecker.core.findings import Finding, Severity, Source
from fchecker.core.profiles import Profile, chain_for, detect_profile

from . import Check

_XMP_LEVELS = {
    "MINIMUM": {Profile.MINIMUM},
    "BASIC WL": {Profile.BASIC_WL},
    "BASIC": {Profile.BASIC},
    "EN 16931": {Profile.EN16931},
    "EXTENDED": {Profile.EXTENDED, Profile.EXTENDED_CTC_FR},
}
# Correction propre à chaque profil écarté : MINIMUM manque de données, BASIC est un sous-ensemble d'EN 16931.
_NON_RETENUS = {
    Profile.MINIMUM: "Générer la facture au profil EN 16931 (ou EXTENDED si des données étendues sont nécessaires).",
    Profile.BASIC: "Déclarer la facture en EN 16931 : BT-24 = urn:cen.eu:en16931:2017 et, pour un Factur-X, niveau de "
                   "conformité EN 16931 dans le PDF.",
}


class ProfileCheck(Check):
    id = "profile"
    label = "Profil"
    order = 0

    def run(self, doc, ctx):
        profile = detect_profile(doc.profile)
        bt24 = doc.profile or "(absent)"
        if profile in (Profile.MINIMUM, Profile.BASIC):
            yield Finding("FR-PROFIL-01", Severity.ERROR, Source.PROFILE,
                          f"Profil {profile.value} ({bt24}) non retenu par la réforme.", bt="BT-24",
                          suggestion=_NON_RETENUS[profile])
        elif profile is Profile.BASIC_WL:
            yield Finding("FR-PROFIL-03", Severity.WARNING, Source.PROFILE,
                          f"Profil BASIC WL ({bt24}) toléré uniquement jusqu'au 01/09/2027 (date à confirmer).",
                          bt="BT-24")
        elif profile is Profile.UNKNOWN:
            yield Finding("FR-PROFIL-04", Severity.WARNING, Source.PROFILE,
                          f"Identifiant de profil non reconnu : {bt24}.", bt="BT-24")

        if doc.format is DocFormat.FACTURX and doc.pdf_info and doc.pdf_info.fx_conformance_level:
            level = doc.pdf_info.fx_conformance_level.strip().upper()
            expected = _XMP_LEVELS.get(level)
            if expected is None or profile not in expected:
                yield Finding("FR-PROFIL-02", Severity.ERROR, Source.PROFILE,
                              f"Niveau XMP « {doc.pdf_info.fx_conformance_level} » incohérent avec le profil "
                              f"du XML ({profile.value}).", bt="BT-24")

        for note in chain_for(doc).notes:
            yield Finding("FR-PROFIL-05", Severity.INFO, Source.PROFILE, note, bt="BT-24")


CHECK = ProfileCheck()
