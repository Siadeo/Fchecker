"""Catalogue de traduction des règles : chaque constat est enrichi (titre FR, explication, exemple).

Ordre de résolution :
1. ``catalog/toolkit.yaml`` — textes pédagogiques rédigés à la main (priorité) ;
2. ``catalog/en16931_fr.yaml`` — traduction maison des règles EN 16931 (EUPL-1.2), faite depuis l'anglais ;
3. ``catalog/official.yaml`` — textes officiels générés (messages anglais des artefacts CEN EN 16931,
   règles de gestion G de la DGFiP, messages BR-FR) ;
4. traduction par motifs des messages stéréotypés (syntaxe CII/UBL, Factur-X, XSD).

Le texte anglais d'origine reste disponible dans ``original`` quand une traduction le remplace.
"""
from __future__ import annotations

import dataclasses
import re
import threading
from importlib import resources

import yaml

from .findings import Finding, Source


def normalize_key(rule_id: str) -> str:
    """``BR-01`` ≡ ``BR-1`` ; ``br-co-15`` ≡ ``BR-CO-15``."""
    return re.sub(r"(?<=[-.])0+(?=\d)", "", rule_id.strip().upper())


_NS_PREFIX = {
    "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100": "ram",
    "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100": "rsm",
    "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100": "udt",
    "urn:un:unece:uncefact:data:standard:QualifiedDataType:100": "qdt",
    "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2": "cac",
    "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2": "cbc",
    "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2": "",
    "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2": "",
}


def _qname(text: str) -> str:
    """``{urn:…:100}Foo`` → ``ram:Foo``."""
    def repl(m: re.Match) -> str:
        prefix = _NS_PREFIX.get(m[1])
        return f"{prefix}:{m[2]}" if prefix else m[2]
    return re.sub(r"\{([^}]*)\}([\w.\-]+)", repl, text)


# (motif sur le message sans préfixe « [ID]- », gabarit FR)
_PATTERNS: list[tuple[re.Pattern, str]] = [(re.compile(p, re.I), t) for p, t in (
    (r"^A UBL invoice (?:should|shall) not include extensions\.?$",
     "La facture UBL ne doit pas contenir d'extensions (UBLExtensions)."),
    (r"^A UBL invoice (?:should|shall) not include the (.+?)\.?$",
     "La facture UBL ne doit pas contenir « {1} » : donnée hors du modèle EN 16931."),
    (r"^Each (.+?) (?:shall|should|must) contain (?:a |an |the |one )?(.+?)\.?$",
     "Chaque « {1} » doit contenir : {2}."),
    (r"^(.+?) (?:should|shall|must) exist maximum once\.?$", "« {1} » ne doit apparaître qu'une fois au maximum."),
    (r"^(.+?) shall occur maximum twice in (.+?)\.?$", "« {1} » ne peut apparaître que deux fois dans « {2} »."),
    (r"^An address can only have one (\w+) line\.?$", "Une adresse ne peut comporter qu'une seule ligne « {1} »."),
    (r"^(.+?) must be stated when providing (.+?)\.?$", "« {1} » doit être renseigné lorsque « {2} » est présent."),
    (r"^Binary object elements shall contain the (.+?) attribute\.?$",
     "Les pièces jointes binaires doivent porter l'attribut « {1} »."),
    (r"^Date time string with format attribute 102 shall be YYYYMMDD\.?$",
     "Une date au format 102 doit s'écrire AAAAMMJJ (ex. 20260924)."),
    (r"^(\w+) shall be '(.+?)'\.?$", "« {1} » doit valoir « {2} »."),
    (r"^Document MUST not contain empty elements.*$", "Le document ne doit pas contenir d'éléments vides."),
    (r"^(.+?) shall only be used for (.+?)$", "« {1} » ne doit être utilisé que pour {2}."),
    (r"^Only one (.+?) (?:element )?is allowed(?: on an invoice)?\.?$", "Un seul élément « {1} » est autorisé."),
    (r"^Only one (.+?) is allowed with (.+?)\.?$", "Un seul « {1} » est autorisé avec {2}."),
    (r"^An Invoice shall contain maximum one (.+?)\.?$", "La facture ne peut contenir qu'un seul « {1} »."),
    (r"^All (.+?) shall have the same value across all (.+?)\.?$",
     "Tous les « {1} » doivent avoir la même valeur dans l'ensemble des « {2} »."),
    (r"^A UBL invoice (?:should|shall) not include an? (.+?)\.?$",
     "La facture UBL ne doit pas contenir « {1} » : donnée hors du modèle EN 16931."),
    (r"^(.+?) (?:should not be present|shall not be used)\.?$",
     "« {1} » ne doit pas être présent : donnée hors du périmètre du profil."),
    (r"^(.+?) shall occur (?:maximum|at most) once in (.+?)\.?$",
     "« {1} » ne doit apparaître qu'une fois au maximum dans « {2} »."),
    (r"^(.+?) shall occur (?:maximum|at most) once\.?$",
     "« {1} » ne doit apparaître qu'une fois au maximum."),
    (r"^(.+?) must exist exactly once\.?$", "« {1} » doit être présent exactement une fois."),
    (r"^Element (?:variant )?'(.+?)' must occur exactly (\d+) times\.?$",
     "L'élément « {1} » doit être présent exactement {2} fois."),
    (r"^Element (?:variant )?'(.+?)' must occur at least (\d+) times\.?$",
     "L'élément « {1} » doit être présent au moins {2} fois."),
    (r"^Element (?:variant )?'(.+?)' may occur at maximum (\d+) times\.?$",
     "L'élément « {1} » ne peut apparaître que {2} fois au maximum."),
    (r"^Value of '(.+?)' is not allowed\.?$",
     "La valeur de « {1} » n'est pas autorisée (hors liste de codes du profil)."),
    (r"^Attribute '?(@[\w:\-]+)'? is required in this context\.?$", "L'attribut « {1} » est obligatoire ici."),
    (r"^(?:Element|Attribute) '?(.+?)'? (?:is )?marked as not used in the given context\.?$",
     "« {1} » n'est pas utilisé dans ce profil et ne doit pas être présent."),
    (r"^Amounts shall be decimal up to two fraction digits\.?$",
     "Les montants doivent comporter au plus deux décimales."),
    # --- Erreurs XSD (libxml2) ---
    (r"^Element '(.+?)': This element is not expected\. Expected is(?: one of)? \( (.+?) \)\.?$",
     "L'élément « {1} » n'est pas attendu à cet endroit. Attendu : {2}."),
    (r"^Element '(.+?)': This element is not expected\.?$",
     "L'élément « {1} » n'est pas attendu à cet endroit (nom ou ordre incorrect)."),
    (r"^Element '(.+?)': Missing child element\(s\)\. Expected is(?: one of)? \( (.+?) \)\.?$",
     "L'élément « {1} » est incomplet : il manque {2}."),
    (r"^Element '(.+?)', attribute '(.+?)': The attribute '.+?' is not allowed\.?$",
     "L'attribut « {2} » n'est pas autorisé sur « {1} »."),
    (r"^Element '(.+?)': The attribute '(.+?)' is required but missing\.?$",
     "L'attribut obligatoire « {2} » est absent de « {1} »."),
    (r"^Element '(.+?)'(?:, attribute '(.+?)')?: \[facet 'enumeration'\] The value '(.*?)' is not an element of the set .*$",
     "La valeur « {3} » de « {1} » n'appartient pas à la liste autorisée."),
    (r"^Element '(.+?)'(?:, attribute '(.+?)')?: \[facet '(?:pattern|length|minLength|maxLength)'\] The value '(.*?)'.*$",
     "La valeur « {3} » de « {1} » ne respecte pas le format attendu."),
    (r"^Element '(.+?)'(?:, attribute '(.+?)')?: '(.*?)' is not a valid value of the (?:atomic|local atomic|union) type '(.+?)'\.?$",
     "La valeur « {3} » de « {1} » est invalide (type attendu : {4})."),
    (r"^Element '(.+?)': (?:\[facet .*?\] )?The value '(.*?)' .*$",
     "La valeur « {2} » de « {1} » est invalide."),
)]

FRENCH_SOURCES = {Source.SCHEMATRON_FR, Source.LOADER, Source.PROFILE, Source.IDENTIFIERS, Source.PEPPOL,
                  Source.PDFA, Source.MENTIONS, Source.CONSISTENCY}

_FOREIGN_VAT = {"AF": "IGIC (îles Canaries)", "AG": "IPSI (Ceuta et Melilla)", "B": "split payment (Italie)",
                "L": "IGIC (îles Canaries)", "M": "IPSI (Ceuta et Melilla)"}


def candidate_keys(rule_id: str) -> list[str]:
    """Clés à essayer : la règle, puis sa règle de base.

    ``BR-FXEXT-AE-08b`` / ``BR-FREXT-AE-08rev`` → ``BR-AE-08`` ; ``BR-54-1`` → ``BR-54`` ;
    ``CII-FREXT-SR-106`` → ``CII-SR-106``.
    """
    keys = [normalize_key(rule_id)]
    base = re.sub(r"^BR-(?:FXEXT|FREXT|EXT)-BR-", "BR-", rule_id)   # BR-FXEXT-BR-23 → BR-23
    base = re.sub(r"-(?:FXEXT|FREXT|EXT)(?=-)", "", base)           # extension de profil
    base = re.sub(r"-([A-Z]{1,2})(\d+)", r"-\1-\2", base)            # BR-S08b → BR-S-08b
    base = re.sub(r"(\d)(?:[a-z]+|ini|rev)$", r"\1", base)           # 08b, 08ini, 08rev
    for candidate in (base, re.sub(r"(-\d+)-\d+$", r"\1", base)):   # BR-54-1 → BR-54
        key = normalize_key(candidate)
        if key not in keys:
            keys.append(key)
    return keys


_FRENCH_HINTS = re.compile(r"[éèêàùç]|\b(?:doit|doivent|être|facture|ligne|montant|lorsque|écart)\b", re.I)


def looks_french(text: str) -> bool:
    """Certains schematrons (EXTENDED-CTC-FR) rédigent leurs messages en français."""
    return len(_FRENCH_HINTS.findall(text)) >= 2


def foreign_vat_title(rule_id: str) -> str | None:
    m = re.match(r"^BR-(?:FXEXT-|FREXT-)?(AF|AG|B|L|M)-\d+", rule_id)
    if not m:
        return None
    return (f"Règle propre à la catégorie de TVA « {m[1]} » — {_FOREIGN_VAT[m[1]]} : "
            "catégorie non utilisée pour une opération imposable en France.")


_PREFIX = re.compile(r"^\s*\[[^\]]+\]\s*-?\s*")
_FR_PREFIX = re.compile(r"^\s*\[?BR-FR[\w/\- ]*?\]?\s*:\s*")


def translate_pattern(message: str) -> str | None:
    text = _qname(_PREFIX.sub("", message).strip())
    for pattern, template in _PATTERNS:
        m = pattern.match(text)
        if m:
            return re.sub(r"\{(\d)\}", lambda g: _qname(m.group(int(g[1])) or ""), template)
    return None


class RulesCatalog:
    def __init__(self, official: dict[str, dict], manual: dict[str, dict],
                 french: dict[str, dict] | None = None) -> None:
        self.official = {normalize_key(k): v for k, v in official.items()}
        self.manual = {normalize_key(k): v for k, v in manual.items()}
        self.french = {normalize_key(k): v for k, v in (french or {}).items()}

    @classmethod
    def load(cls) -> RulesCatalog:
        def read(name: str) -> dict:
            f = resources.files(__package__).joinpath("catalog", name)
            return (yaml.safe_load(f.read_text(encoding="utf-8")) or {}) if f.is_file() else {}
        return cls(read("official.yaml"), read("toolkit.yaml"), read("en16931_fr.yaml").get("rules"))

    def _official_fr(self, key: str) -> dict:
        """Entrée officielle dont le texte anglais (artefacts CEN) est remplacé par sa traduction."""
        e = self.official.get(key, {})
        title = e.get("title")
        if not title or "CEN" not in str(e.get("source", "")):
            return e
        fr = (self.french.get(key) or {}).get("title") or translate_pattern(title)
        return {**e, "title": fr, "original": title, "source": f"{e['source']}, traduction Fchecker"} if fr else e

    def entry(self, rule_id: str) -> dict:
        """Fusion officiel (traduit) + manuel (le manuel prime) ; à défaut, règle de base d'une variante."""
        for key in candidate_keys(rule_id):
            merged = {**self._official_fr(key), **self.manual.get(key, {})}
            if merged:
                if key != normalize_key(rule_id):
                    merged = {**merged, "variant_of": key}
                return merged
        return {}

    def lookup(self, query: str) -> list[tuple[str, dict]]:
        """Recherche par code (préfixe) ou par texte, pour la fenêtre « Règles ».

        Requête vide : toutes les règles du catalogue, sans limite."""
        q = query.strip()
        keys = sorted(set(self.official) | set(self.manual))
        if not q:
            return [(k, self.entry(k)) for k in keys]
        key = normalize_key(q)
        hits = [k for k in keys if k.startswith(key)]
        if not hits:
            lq = q.casefold()

            def text(k: str) -> str:
                e = self.entry(k)
                fields = ("title", "explanation", "variants", "original")
                return " ".join(str(e.get(f) or "") for f in fields).casefold()

            hits = [k for k in keys if lq in text(k)]
        return [(k, self.entry(k)) for k in hits[:200]]

    def enrich(self, f: Finding) -> Finding:
        if f.translated:
            return f
        e = self.entry(f.rule_id)
        manual = self.manual.get(normalize_key(f.rule_id), {})
        french_source = (f.source in FRENCH_SOURCES or f.rule_id.startswith("BR-FR")
                         or looks_french(f.message))

        # Message déjà en français (BR-FR, contrôles de l'outil) : il porte les valeurs réelles, il
        # sert de titre. Sinon, du plus spécifique au plus générique : traduction par motif (noms
        # d'éléments, valeurs), titre manuel, texte officiel.
        # Règle EN 16931 traduite (en16931_fr.yaml) : message statique, la traduction prime sur le motif.
        translated = next((self.french[k].get("title") for k in candidate_keys(f.rule_id) if k in self.french), None)
        if french_source:
            title = _FR_PREFIX.sub("", f.message).strip() or None
        else:
            title = (manual.get("title") if translated else None) or translated or translate_pattern(f.message) \
                or manual.get("title") or e.get("title") or foreign_vat_title(f.rule_id)

        explanation = e.get("explanation")
        # Pour BR-FR, le titre officiel n'est qu'une variante du message (ex. PMT vs PMD) : pas de reprise.
        if not explanation and not french_source and e.get("title") and e.get("title") != title:
            explanation = e["title"]
        if manual.get("title") and manual["title"] != title:  # ex. XSD : titre générique en tête d'explication
            explanation = f"{manual['title']}. {explanation}" if explanation else manual["title"]
        if e.get("context"):
            explanation = f"{explanation}\n\nContexte : {e['context']}" if explanation else f"Contexte : {e['context']}"
        if e.get("variant_of"):
            note = (f"Variante de la règle {e.get('id', e['variant_of'])} (adaptation au profil étendu) : "
                    "le texte ci-dessus est celui de la règle de base.")
            explanation = f"{explanation}\n\n{note}" if explanation else note

        bts = e.get("bt") or []
        return dataclasses.replace(
            f,
            title=title,
            explanation=explanation,
            example=e.get("example"),
            suggestion=f.suggestion or e.get("correction"),
            bt=f.bt or (", ".join(bts[:3]) if bts else None),
            translated=title is not None,
        )


_catalog: RulesCatalog | None = None
_lock = threading.Lock()


def catalog() -> RulesCatalog:
    global _catalog
    with _lock:
        if _catalog is None:
            _catalog = RulesCatalog.load()
        return _catalog
