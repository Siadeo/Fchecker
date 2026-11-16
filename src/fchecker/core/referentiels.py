"""Référentiels de Fchecker : liste unique des normes, règles et textes utilisés, et contrôle de leur fraîcheur.

Où et comment ils sont utilisés dans le code
--------------------------------------------
- Schematrons et XSD (FNFE, CEN, Factur-X) : embarqués dans ``resources/rules/fnfe/`` ; choisis par
  ``core/profiles.py``, exécutés par ``core/schematron.py`` et ``core/xsd.py``, appelés depuis
  ``plugins/validator/checks/`` (profile, xsd_check, schematron_check).
- Messages des règles : ``core/catalog/official.yaml`` (généré par ``tools/build_catalog.py`` depuis les
  artefacts CEN, l'annexe 7 DGFiP et les schematrons FNFE) et ``core/catalog/en16931_fr.yaml`` (traduction
  maison, contrôlée par ``tools/check_translations.py``) ; appliqués par ``core/rules_catalog.py``.
- Règles de gestion G de la DGFiP et textes légaux : ``plugins/mentions/``
  (``predicates.py``, ``rules.yaml``) et fiches de ``core/catalog/toolkit.yaml``.
- Mise à jour des packs (SHA-256 figés) : ``tools/fetch_rules.py``.
- Affichage pour l'utilisateur : tableau de ``ui/settings_dialog.py``, qui ne lit que ``REFERENTIELS``.

Contrôle de fraîcheur (développeurs uniquement)
-----------------------------------------------
    venv\\Scripts\\python -m fchecker.core.referentiels

Ce contrôle interroge Internet. Il n'est lancé que par cette commande, jamais par l'application : ``httpx``
n'est importé que dans ``verifier_tous``. Code de sortie 1 si un référentiel maître a une version plus récente.

États : À JOUR ; EN ATTENTE (version plus récente, mais ``suit`` désigne le référentiel qui commande la mise à
jour) ; MANUEL (relecture humaine, à dater dans ``verifie_le``) ; À METTRE À JOUR ; INCONNU (page inaccessible
ou format changé : jamais compté comme à jour).

Pourquoi « suit » : le pack FNFE est la référence française. Il assemble les artefacts CEN, Factur-X et les XSD.
On n'intègre pas une version CEN seule : on attend que la FNFE la reprenne, pour rester aligné sur ce que
contrôlent les plateformes.

Source unique des versions : les constantes ci-dessous. ``tools/fetch_rules.py``, ``tools/build_catalog.py`` et
``core/profiles.py`` les lisent. Pour une mise à jour : changer la constante ici, puis l'URL et le SHA-256 dans
``tools/fetch_rules.py``, et les versions de NOTICE et LICENSE.md (un test les compare) ; relancer ``fetch_rules``,
``build_catalog``, ``check_translations``, les tests et cette commande.
"""
from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import Enum

FNFE_VERSION = "1.4.0.04"
CEN_VERSION = "1.3.16"
FACTURX_VERSION = "1.09.2"
FACTURX_DOSSIER = f"Factur-X_{FACTURX_VERSION}.fixFR04"   # dossier du pack FNFE
DGFIP_VERSION = "3.2"
ANNEXE7_VERSION = "1.9"
CODES_DATE = "15/05/2026"                                 # listes de codes EN 16931

A_CONFIRMER = "à confirmer"
RELECTURE_JOURS = 90
_VERIFIE = date(2026, 11, 5)   # dernière relecture des pages officielles
_TAG_GITHUB = r'"tag_name"\s*:\s*"[^"\d]*(\d[\d.]*)"'
_LEGIFRANCE = "https://www.legifrance.gouv.fr/codes/article_lc/"
_FNFE_RESSOURCES = "https://fnfe-mpe.org/ressources/"


@dataclass(frozen=True)
class Controle:
    """Page officielle et motif dont le groupe 1 donne une version (la plus haute trouvée est retenue)."""
    url: str
    motif: str


@dataclass(frozen=True)
class Referentiel:
    id: str
    nom: str
    categorie: str
    version: str
    publication: str               # texte affiché dans Paramètres ; A_CONFIRMER si aucune source officielle lue
    editeur: str
    url: str
    usage: str
    suit: str | None = None        # id du référentiel qui commande sa mise à jour
    note: str = ""
    controle: Controle | None = None
    verifie_le: date | None = None  # relecture humaine du texte officiel ; None = jamais faite


# Organismes qui publient les référentiels (boîte « À propos »).
ORGANISMES = ("CEN", "DGFiP", "FNFE-MPE", "FeRD", "UN/CEFACT", "OASIS")

CATEGORIES = ("Règles exécutées", "Normes", "Administration", "Textes légaux", "Doctrine fiscale")

REFERENTIELS: tuple[Referentiel, ...] = (
    # --- Règles exécutées ----------------------------------------------------------------------------
    Referentiel("fnfe", "Schematrons FNFE-MPE (BR-FR, EXTENDED-CTC-FR)", "Règles exécutées", FNFE_VERSION,
                "04/09/2026", "FNFE-MPE", _FNFE_RESSOURCES, "Contrôle des factures (validateur)",
                controle=Controle("https://api.github.com/repos/fnfempe/France_RFE/releases/latest", _TAG_GITHUB)),
    Referentiel("en16931", "Artefacts de validation EN 16931", "Règles exécutées", CEN_VERSION, "10/04/2026",
                "CEN/TC 434", "https://github.com/ConnectingEurope/eInvoicing-EN16931",
                "Contrôle des règles BR, BR-CO, BR-CL et de syntaxe ; textes anglais des fiches", suit="fnfe",
                note="La 1.3.17 (octobre 2026) corrige BR-AF-05, BR-AG-05, BR-CO-09, CII-SR-036 à 038 et les listes "
                     "de codes, mais la FNFE ne l'a pas intégrée : attendre sa prochaine version.",
                controle=Controle("https://api.github.com/repos/ConnectingEurope/eInvoicing-EN16931/releases/latest",
                                  _TAG_GITHUB)),
    Referentiel("codes", "Listes de codes EN 16931", "Règles exécutées", CODES_DATE, CODES_DATE, "CEN/TC 434",
                _FNFE_RESSOURCES, "Contrôle des valeurs codées", suit="fnfe"),
    Referentiel("facturx", "Factur-X / ZUGFeRD", "Règles exécutées", FACTURX_VERSION, "04/08/2026 (effet 01/09/2026)",
                "FNFE-MPE et FeRD", "https://fnfe-mpe.org/factur-x/", "Contrôle des factures Factur-X", suit="fnfe",
                controle=Controle("https://fnfe-mpe.org/factur-x/", r"Factur-X\W+(1\.\d+(?:\.\d+)?)")),
    Referentiel("xsd-cii", "Schémas XSD CII", "Règles exécutées", "D22B", A_CONFIRMER, "UN/CEFACT",
                _FNFE_RESSOURCES, "Contrôle de structure CII", suit="fnfe"),
    Referentiel("xsd-ubl", "Schémas XSD UBL", "Règles exécutées", "2.1", "04/11/2013", "OASIS",
                "https://docs.oasis-open.org/ubl/UBL-2.1.html", "Contrôle de structure UBL", suit="fnfe",
                verifie_le=_VERIFIE),
    Referentiel("traduction", "Traduction française des règles EN 16931", "Règles exécutées",
                f"artefacts {CEN_VERSION}",
                "04/11/2026", "Fchecker", "https://github.com/ConnectingEurope/eInvoicing-EN16931",
                "Textes français de l'écran Règles et des constats", suit="en16931",
                note="À retraduire si les messages anglais changent : tools/check_translations.py."),
    # --- Normes --------------------------------------------------------------------------------------
    Referentiel("en16931-1", "EN 16931-1 (modèle sémantique)", "Normes", "2017 + A1", A_CONFIRMER, "CEN",
                "https://ec.europa.eu/digital-building-blocks/sites/display/DIGITAL/"
                "Obtaining+a+copy+of+the+European+standard+on+eInvoicing",
                "Fondement des règles BR", suit="fnfe",
                note="Édition 2026 publiée en mai 2026. La version 2017 est retirée mais reste conforme pendant la "
                     "migration, sans date de fin publiée. À réévaluer quand le socle français l'adoptera.",
                verifie_le=_VERIFIE),
    # --- Administration ------------------------------------------------------------------------------
    Referentiel("dgfip", "Spécifications externes de la facturation électronique", "Administration", DGFIP_VERSION,
                "30/04/2026", "DGFiP", "https://www.impots.gouv.fr/node/14441", "Cadre de la réforme",
                controle=Controle("https://www.impots.gouv.fr/node/14441",
                                  r"Version\s+(\d+\.\d+)\s+des\s+sp\S+cifications\s+externes")),
    Referentiel("dgfip-annexe7", "Annexe 7, règles de gestion G", "Administration", ANNEXE7_VERSION, "30/04/2026", "DGFiP",
                "https://www.impots.gouv.fr/node/14441", "Fiches des règles G de l'écran Règles", suit="dgfip"),
    # --- Textes légaux -------------------------------------------------------------------------------
    Referentiel("cgi-289bis", "CGI, art. 289 bis", "Textes légaux", "Loi n° 2026-103", "21/02/2026", "État français",
                _LEGIFRANCE + "LEGIARTI000046195635", "Obligation de facturation électronique", verifie_le=_VERIFIE),
    Referentiel("arrete-2026", "Arrêté du 27 juillet 2026 (généralisation)", "Textes légaux", "Texte initial",
                "27/07/2026", "État français", "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000054499535",
                "Application de l'art. 289 bis"),
    Referentiel("cgi-242", "CGI, annexe II, art. 242 nonies A", "Textes légaux", "Décret n° 2024-1195", "01/01/2025",
                "État français", _LEGIFRANCE + "LEGIARTI000050811276", "Mentions obligatoires", verifie_le=_VERIFIE),
    Referentiel("cgi-293b", "CGI, art. 293 B", "Textes légaux", "Loi n° 2025-1044", "01/03/2025", "État français",
                _LEGIFRANCE + "LEGIARTI000045035275", "Franchise en base", verifie_le=_VERIFIE,
                note="Remplacé par le CIBS, art. L. 233-3, au 01/01/2027."),
    Referentiel("cibs-233-3", "CIBS, art. L. 233-3", "Textes légaux", "Ordonnance n° 2026-671",
                "à venir, 01/01/2027", "État français", _LEGIFRANCE + "LEGIARTI000054524584/2027-01-01",
                "Mention de franchise en base à compter du 01/01/2027", verifie_le=_VERIFIE),
    Referentiel("cc-l441-9", "Code de commerce, art. L441-9", "Textes légaux", "Ordonnance n° 2019-359", "26/04/2019",
                "État français", _LEGIFRANCE + "LEGIARTI000038414397",
                "Paiement, pénalités, escompte, bon de commande", verifie_le=_VERIFIE),
    Referentiel("cc-d441-5", "Code de commerce, art. D441-5", "Textes légaux", "Décret n° 2021-211", "27/02/2021",
                "État français", _LEGIFRANCE + "LEGIARTI000043197457", "Indemnité de recouvrement de 40 €",
                verifie_le=_VERIFIE),
    Referentiel("cc-r123-237", "Code de commerce, art. R123-237", "Textes légaux", "Décret n° 2022-725", "15/05/2022",
                "État français", _LEGIFRANCE + "LEGIARTI000045710304", "Identité du vendeur (RCS)",
                verifie_le=_VERIFIE),
    Referentiel("cc-r123-238", "Code de commerce, art. R123-238", "Textes légaux", "Sans modification", "27/03/2007",
                "État français", _LEGIFRANCE + "LEGIARTI000006259054", "Forme juridique et capital social",
                verifie_le=_VERIFIE),
    # --- Doctrine ------------------------------------------------------------------------------------
    Referentiel("boi-res-253", "BOI-RES-TVA-000253", "Doctrine fiscale", "18/02/2026", "18/02/2026", "DGFiP (BOFiP)",
                "https://bofip.impots.gouv.fr/bofip/14901-PGP.html/identifiant%3DBOI-RES-TVA-000253-20260218",
                "Renvois au CGI admis jusqu'au 31/12/2027", verifie_le=_VERIFIE),
    Referentiel("boi-decla", "BOI-TVA-DECLA-30-20-10-30", "Doctrine fiscale", "29/06/2022", "29/06/2022",
                "DGFiP (BOFiP)",
                "https://bofip.impots.gouv.fr/bofip/13244-PGP.html/identifiant=BOI-TVA-DECLA-30-20-10-30-20220629",
                "Facture établie par un mandataire", note="Vérifier qu'il n'existe pas de version plus récente."),
)


class Etat(str, Enum):
    A_JOUR = "À JOUR"
    EN_ATTENTE = "EN ATTENTE"
    MANUEL = "MANUEL"
    A_METTRE_A_JOUR = "À METTRE À JOUR"
    INCONNU = "INCONNU"


@dataclass(frozen=True)
class Resultat:
    referentiel: Referentiel
    etat: Etat
    detail: str


def _numeros(version: str) -> tuple[int, ...]:
    """« 1.4.0.04 » → (1, 4, 0, 4), sans zéros de fin : 1.4 ≡ 1.4.0."""
    m = re.search(r"\d+(?:\.\d+)*", version)
    numeros = [int(n) for n in m.group().split(".")] if m else []
    while numeros and numeros[-1] == 0:
        numeros.pop()
    return tuple(numeros)


def verifier(ref: Referentiel, lire: Callable[[str], str], aujourdhui: date | None = None) -> Resultat:
    """État d'un référentiel. ``lire`` renvoie le texte d'une URL (exception si inaccessible)."""
    if ref.controle is None:
        if ref.verifie_le is None:
            if ref.suit:
                return Resultat(ref, Etat.MANUEL, f"Suit {ref.suit} : à revoir avec sa mise à jour.")
            return Resultat(ref, Etat.MANUEL, f"Jamais relu : {ref.url}")
        age = ((aujourdhui or date.today()) - ref.verifie_le).days
        conseil = "à relire" if age > RELECTURE_JOURS else "relu"
        return Resultat(ref, Etat.MANUEL, f"{conseil}, dernière relecture le {ref.verifie_le:%d/%m/%Y} : {ref.url}")
    try:
        trouvees = re.findall(ref.controle.motif, lire(ref.controle.url))
    except Exception as exc:  # réseau, HTTP, décodage : ne jamais conclure « à jour »
        return Resultat(ref, Etat.INCONNU, f"Page inaccessible ({type(exc).__name__}) : {ref.controle.url}")
    if not trouvees:
        return Resultat(ref, Etat.INCONNU, f"Version introuvable, format changé ? {ref.controle.url}")
    publiee = max(trouvees, key=_numeros)
    if _numeros(publiee) <= _numeros(ref.version):
        return Resultat(ref, Etat.A_JOUR, f"{ref.version} (publiée : {publiee})")
    if ref.suit:
        return Resultat(ref, Etat.EN_ATTENTE, f"{publiee} publiée, embarquée {ref.version} : à intégrer via {ref.suit}.")
    return Resultat(ref, Etat.A_METTRE_A_JOUR, f"{publiee} publiée, embarquée {ref.version} : {ref.url}")


def verifier_tous(lire: Callable[[str], str] | None = None, aujourdhui: date | None = None) -> list[Resultat]:
    if lire is not None:
        return [verifier(r, lire, aujourdhui) for r in REFERENTIELS]
    import httpx

    pages: dict[str, str] = {}
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "fchecker"}) as client:
        def lire_page(url: str) -> str:
            if url not in pages:
                response = client.get(url)
                response.raise_for_status()
                pages[url] = response.text
            return pages[url]

        return [verifier(r, lire_page, aujourdhui) for r in REFERENTIELS]


def ecarts_embarques() -> list[str]:
    """Écarts entre cette liste et les fichiers réellement embarqués (sans réseau)."""
    from .rulepacks import get_pack

    pack = get_pack("fnfe")
    if pack is None:
        return ["Pack FNFE absent."]
    ecarts = []
    if pack.version != FNFE_VERSION:
        ecarts.append(f"FNFE : pack.yaml {pack.version}, liste {FNFE_VERSION}")
    entete = pack.path("CII/EN16931/2xslt/EN16931-CII-validation.xslt").read_text(encoding="utf-8", errors="ignore")[:2000]
    m = re.search(r"Schematron version ([\d.]+)", entete)
    if not m or m.group(1) != CEN_VERSION:
        ecarts.append(f"CEN : XSLT {m.group(1) if m else '?'}, liste {CEN_VERSION}")
    if not pack.has(f"{FACTURX_DOSSIER}/EN16931/2xslt/FACTUR-X_EN16931.xslt"):
        ecarts.append(f"Factur-X : dossier {FACTURX_DOSSIER} absent")
    return ecarts


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    resultats = verifier_tous()
    for r in resultats:
        print(f"{r.etat.value:<16} {r.referentiel.nom} — {r.detail}")
        if r.etat is Etat.EN_ATTENTE and r.referentiel.note:
            print(f"{'':<16} {r.referentiel.note}")
    ecarts = ecarts_embarques()
    for ecart in ecarts:
        print(f"INCOHÉRENT       {ecart}")
    return 1 if ecarts or any(r.etat is Etat.A_METTRE_A_JOUR for r in resultats) else 0


if __name__ == "__main__":
    raise SystemExit(main())
