"""Reconnaissance des montants, dates et identifiants dans le texte d'un PDF.

Principe : on extrait TOUTES les valeurs candidates du texte (avec leur position), puis on
cherche l'égalité exacte avec la valeur XML. Les formats d'affichage usuels sont acceptés.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True, slots=True)
class Token:
    value: object       # Decimal ou date
    text: str           # texte tel qu'affiché dans le PDF
    start: int


# --- Montants -------------------------------------------------------------------------------

_NUMBER = re.compile(
    r"(?<![\w.,])-?(?:\d{1,3}(?:[ .,']\d{3})+|\d+)(?:[.,]\d{1,4})?(?![\d])"
)


def _interpret(raw: str) -> set[Decimal]:
    s = raw.replace(" ", "").replace("'", "")
    out: set[str] = set()
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        th = "." if dec == "," else ","
        out.add(s.replace(th, "").replace(dec, "."))
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        head, _, tail = s.rpartition(sep)
        if s.count(sep) == 1 and len(tail) in (1, 2, 4):
            out.add(f"{head}.{tail}")                      # séparateur décimal
        elif len(tail) == 3:
            out.add(s.replace(sep, ""))                    # séparateur de milliers
            if s.count(sep) == 1:
                out.add(f"{head}.{tail}")                  # ou décimal à 3 chiffres (quantité)
        else:
            out.add(s.replace(sep, "."))
    else:
        out.add(s)
    values = set()
    for v in out:
        try:
            values.add(Decimal(v))
        except InvalidOperation:
            pass
    return values


def amounts(text: str) -> list[Token]:
    tokens = []
    for m in _NUMBER.finditer(text):
        for value in _interpret(m.group(0)):
            tokens.append(Token(value, m.group(0), m.start()))
    return tokens


def amount_equal(a: Decimal, b: Decimal) -> bool:
    return a == b  # égalité exacte (12.5 == 12.50) : pas de tolérance d'arrondi


# --- Dates -----------------------------------------------------------------------------------

_MONTHS = {
    "janvier": 1, "janv": 1, "fevrier": 2, "fevr": 2, "fev": 2, "mars": 3, "avril": 4, "avr": 4, "mai": 5,
    "juin": 6, "juillet": 7, "juil": 7, "aout": 8, "septembre": 9, "sept": 9, "sep": 9, "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11, "decembre": 12, "dec": 12,
}
_DMY = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})(?!\d)")
_YMD = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_COMPACT = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)")
_LONG = re.compile(r"(?<!\d)(\d{1,2})(?:er)?\s+([a-zéèûô]+)\.?\s+(\d{4})(?!\d)", re.I)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _make(y: int, m: int, d: int) -> date | None:
    if y < 100:
        y += 2000
    try:
        return date(y, m, d)
    except ValueError:
        return None


def dates(text: str) -> list[Token]:
    out = []
    for m in _DMY.finditer(text):
        if (dt := _make(int(m[3]), int(m[2]), int(m[1]))) is not None:
            out.append(Token(dt, m.group(0), m.start()))
    for m in _YMD.finditer(text):
        if (dt := _make(int(m[1]), int(m[2]), int(m[3]))) is not None:
            out.append(Token(dt, m.group(0), m.start()))
    for m in _COMPACT.finditer(text):
        if (dt := _make(int(m[1]), int(m[2]), int(m[3]))) is not None:
            out.append(Token(dt, m.group(0), m.start()))
    for m in _LONG.finditer(text):
        month = _MONTHS.get(_fold(m[2]).rstrip("."))
        if month and (dt := _make(int(m[3]), month, int(m[1]))) is not None:
            out.append(Token(dt, m.group(0), m.start()))
    return sorted(out, key=lambda t: t.start)


# --- Identifiants -----------------------------------------------------------------------------

def compact(text: str) -> str:
    """Supprime espaces et séparateurs : « F 0390-47907 » ≈ « F039047907 »."""
    return re.sub(r"[\s\-_./]", "", text).upper()


def digits_joined(text: str) -> str:
    """Recolle les groupes de chiffres : « 300 000 007 » → « 300000007 »."""
    return re.sub(r"(?<=\d)[ .](?=\d)", "", text)


def has_identifier(text: str, value: str) -> bool:
    """Le numéro figure-t-il dans le texte (comparaison sans espaces ni séparateurs) ?"""
    target = compact(value)
    return bool(target) and target in compact(text)


def find_siren(text: str, siren: str) -> str | None:
    """Le SIREN tel quel, en tête d'un SIRET, dans une TVA FR (FR + clé + SIREN) ou un RCS."""
    joined = digits_joined(text)
    m = re.search(rf"(?<!\d){siren}", joined) or re.search(rf"FR\s?\d{{2}}\s?{siren}", joined, re.I)
    return m.group(0) if m else None


# --- Libellés (détection des valeurs divergentes) ------------------------------------------------

LABELS = {
    "BT-1": r"facture\s*(?:n\s*[°o]|num[ée]ro|:)",
    "BT-2": r"date\s*(?:de\s*(?:la\s*)?)?factur(?:e|ation)|date\s*d.?[ée]mission|factur[ée]e?\s*le",
    "BT-9": r"[ée]ch[ée]ance|date\s*limite\s*de\s*(?:r[èe]glement|paiement)|payable\s*le",
    "BT-109": r"total\s*(?:net\s*)?h\.?\s*t\.?\b|montant\s*h\.?\s*t\.?\b|total\s*hors\s*tax",
    "BT-110": r"total\s*(?:de\s*la\s*)?t\.?\s*v\.?\s*a\.?\b|montant\s*(?:de\s*la\s*|total\s*)?t\.?\s*v\.?\s*a\.?\b",
    "BT-112": r"total\s*t\.?\s*t\.?\s*c\.?\b|montant\s*t\.?\s*t\.?\s*c\.?\b|total\s*toutes\s*taxes",
    "BT-115": r"net\s*[àa]\s*payer|reste\s*[àa]\s*payer|montant\s*d[ûu]|solde\s*d[ûu]",
}


def _values_in(segment: str, kind: str) -> list[Token]:
    if kind == "amount":
        # Seuls les montants « monétaires » (2 décimales) : évite « 40 » d'une mention voisine.
        return [t for t in amounts(segment) if re.search(r"[.,]\d{2}$", t.text)]
    return dates(segment)


def labelled_values(text: str, bt: str, kind: str, window: int = 80) -> list[Token]:
    """Valeur associée à chaque libellé connu du champ ``bt``.

    L'ordre du texte extrait dépend du générateur de PDF : on cherche d'abord sur la même ligne
    (après, puis avant le libellé), puis dans les caractères qui suivent.
    """
    pattern = LABELS.get(bt)
    if not pattern:
        return []
    found = []
    for m in re.finditer(pattern, text, re.I):
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line_end = len(text) if line_end < 0 else line_end
        after = _values_in(text[m.end():line_end], kind)
        before = _values_in(text[line_start:m.start()], kind)
        if after:
            t = after[0]
            found.append(Token(t.value, t.text, m.end() + t.start))
        elif before:
            t = before[-1]
            found.append(Token(t.value, t.text, line_start + t.start))
        else:
            nxt = _values_in(text[m.end(): m.end() + window], kind)
            if nxt:
                t = min(nxt, key=lambda x: x.start)
                found.append(Token(t.value, t.text, m.end() + t.start))
    return found
