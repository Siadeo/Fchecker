"""Profils de facture et chaînes de contrôle (XSD + schematrons) associées.

Référence : notice FNFE-MPE « Schematrons FR CTC » V1.4.0, § 1 « Organisation des contrôles ».
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from lxml import etree

from .document import NS_UBL_CREDIT_NOTE, DocFormat, InvoiceDocument
from .findings import Source
from .referentiels import FACTURX_DOSSIER
from .rulepacks import get_pack

PACK_ID = "fnfe"
FX = FACTURX_DOSSIER


class Profile(str, Enum):
    MINIMUM = "MINIMUM"
    BASIC_WL = "BASIC WL"
    BASIC = "BASIC"
    EN16931 = "EN 16931"
    EXTENDED = "EXTENDED"
    EXTENDED_CTC_FR = "EXTENDED-CTC-FR"
    UNKNOWN = "inconnu"


# Profils Factur-X retenus par la réforme ; BASIC WL toléré jusqu'au 01/09/2027 (date à confirmer).
REFORM_PROFILES = {Profile.EN16931, Profile.EXTENDED, Profile.EXTENDED_CTC_FR}
TRANSITIONAL_PROFILES = {Profile.BASIC_WL}


def detect_profile(urn: str | None) -> Profile:
    if not urn:
        return Profile.UNKNOWN
    u = urn.strip().lower()
    if "extended-ctc-fr" in u:
        return Profile.EXTENDED_CTC_FR
    if u.endswith(":extended"):
        return Profile.EXTENDED
    if u.endswith(":basicwl"):
        return Profile.BASIC_WL
    if u.endswith(":basic"):
        return Profile.BASIC
    if u.endswith(":minimum"):
        return Profile.MINIMUM
    if u.startswith("urn:cen.eu:en16931:2017"):
        return Profile.EN16931  # y compris CIUS / extensions « compliant »
    return Profile.UNKNOWN


@dataclass(frozen=True)
class SchematronSpec:
    id: str             # identifiant stable (cache, rapport)
    label: str          # libellé affiché
    rel_path: str       # chemin relatif dans le pack
    source: Source


@dataclass(frozen=True)
class ValidationChain:
    profile: Profile
    xsd: str | None                                   # chemin relatif dans le pack
    schematrons: tuple[SchematronSpec, ...] = ()
    notes: tuple[str, ...] = field(default=())        # informations à publier (ex. XSD absent)


_EN_CII = SchematronSpec("en16931-cii", "EN 16931 (CII)", "CII/EN16931/2xslt/EN16931-CII-validation.xslt",
                         Source.SCHEMATRON_EN)
_EN_UBL = SchematronSpec("en16931-ubl", "EN 16931 (UBL)", "UBL/EN16931/2xslt/EN16931-UBL-validation.xslt",
                         Source.SCHEMATRON_EN)
_EXT_CII = SchematronSpec("extended-ctc-fr-cii", "EXTENDED-CTC-FR (CII)",
                          "CII/EXTENDED-CTC-FR/2xslt/EXTENDED-CTC-FR-CII.xslt", Source.SCHEMATRON_EN)
_EXT_UBL = SchematronSpec("extended-ctc-fr-ubl", "EXTENDED-CTC-FR (UBL)",
                          "UBL/EXTENDED-CTC-FR/2xslt/EXTENDED-CTC-FR-UBL.xslt", Source.SCHEMATRON_EN)
_FR_CII = SchematronSpec("br-fr-cii", "Règles FR (CII)", "CII/EN16931/2xslt/BR-FR-Flux2-Schematron-CII.xslt",
                         Source.SCHEMATRON_FR)
_FR_UBL = SchematronSpec("br-fr-ubl", "Règles FR (UBL)", "UBL/EN16931/2xslt/BR-FR-Flux2-Schematron-UBL.xslt",
                         Source.SCHEMATRON_FR)

_FX = {
    Profile.BASIC_WL: ("BASICWL", "Factur-X_BASICWL.xsd", "FACTUR-X_BASIC-WL.xslt"),
    Profile.EN16931: ("EN16931", "Factur-X_EN16931.xsd", "FACTUR-X_EN16931.xslt"),
    Profile.EXTENDED: ("EXTENDED", "Factur-X_EXTENDED.xsd", "FACTUR-X_EXTENDED.xslt"),
}

CII_XSD = "CII/1xsd-CII_D22B_uncoupled/CrossIndustryInvoice_100pD22B.xsd"
UBL_INVOICE_XSD = "UBL/1xsd_UBL2.1/maindoc/UBL-Invoice-2.1.xsd"
UBL_CREDIT_NOTE_XSD = "UBL/1xsd_UBL2.1/maindoc/UBL-CreditNote-2.1.xsd"


def chain_for(doc: InvoiceDocument) -> ValidationChain:
    """Chaîne XSD + schematrons applicable au document, selon sa syntaxe et son profil."""
    profile = detect_profile(doc.profile)

    if doc.format is DocFormat.UBL:
        is_credit = etree.QName(doc.root).namespace == NS_UBL_CREDIT_NOTE
        xsd = UBL_CREDIT_NOTE_XSD if is_credit else UBL_INVOICE_XSD
        model = _EXT_UBL if profile is Profile.EXTENDED_CTC_FR else _EN_UBL
        return ValidationChain(profile, xsd, (model, _FR_UBL))

    # Profils propres à Factur-X (BASIC WL, EXTENDED) : leurs composants s'appliquent aussi à un CII
    # isolé (notice FNFE § 1 : « il est possible d'utiliser les composants de contrôle de Factur-X pour
    # une facture UN/CEFACT CII »). Le schematron EN 16931 générique exigerait des lignes absentes en BASIC WL.
    facturx_components = doc.format is DocFormat.FACTURX or profile in (Profile.BASIC_WL, Profile.EXTENDED)
    if facturx_components:
        if profile in _FX:
            folder, xsd, xslt = _FX[profile]
            spec = SchematronSpec(f"facturx-{folder.lower()}", f"Factur-X {profile.value}",
                                  f"{FX}/{folder}/2xslt/{xslt}", Source.SCHEMATRON_EN)
            # Le schematron de profil Factur-X intègre déjà les règles EN 16931.
            return ValidationChain(profile, f"{FX}/{folder}/1xsd/{xsd}", (spec, _FR_CII))
        if profile is Profile.EXTENDED_CTC_FR:
            # Factur-X EXTENDED est un sur-ensemble d'EXTENDED-CTC-FR : son XSD s'applique ;
            # le schematron dédié CTC-FR remplace celui du profil (qui refuserait l'URN CTC-FR).
            return ValidationChain(profile, f"{FX}/EXTENDED/1xsd/Factur-X_EXTENDED.xsd", (_EXT_CII, _FR_CII))
        note = (f"Profil Factur-X {profile.value} : aucun XSD ni schematron de profil publié pour la réforme ; "
                "seuls les contrôles EN 16931 et règles FR sont exécutés.")
        return ValidationChain(profile, CII_XSD, (_EN_CII, _FR_CII), (note,))

    # CII seul (EN 16931, EXTENDED-CTC-FR ; MINIMUM / BASIC / inconnu → contrôles EN 16931)
    model = _EXT_CII if profile is Profile.EXTENDED_CTC_FR else _EN_CII
    return ValidationChain(profile, CII_XSD, (model, _FR_CII))


def pack():
    return get_pack(PACK_ID)


def warm_up_paths() -> list:
    """XSLT à précompiler au démarrage, par ordre de probabilité d'usage."""
    p = pack()
    if p is None:
        return []
    specs = (f"{FX}/EN16931/2xslt/FACTUR-X_EN16931.xslt", _FR_CII.rel_path, _EN_CII.rel_path,
             _EN_UBL.rel_path, _FR_UBL.rel_path)
    return [p.path(rel) for rel in specs]
