"""Contrôles algorithmiques d'identifiants (SIREN, SIRET, TVA FR, IBAN)."""
from __future__ import annotations

import re

_LA_POSTE_SIREN = "356000000"

# Longueurs IBAN des pays les plus courants ; les autres pays ne sont contrôlés que par le mod-97.
IBAN_LENGTHS = {
    "FR": 27, "MC": 27, "DE": 22, "BE": 16, "LU": 20, "ES": 24, "IT": 27, "NL": 18,
    "CH": 21, "GB": 22, "PT": 25, "AT": 20, "IE": 22,
}


def _compact(value: str) -> str:
    return re.sub(r"[\s.\-]", "", value or "")


def luhn_valid(digits: str) -> bool:
    if not digits.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def is_valid_siren(value: str) -> bool:
    siren = _compact(value)
    return len(siren) == 9 and siren.isdigit() and luhn_valid(siren)


def is_valid_siret(value: str) -> bool:
    siret = _compact(value)
    if len(siret) != 14 or not siret.isdigit():
        return False
    if luhn_valid(siret):
        return True
    # Établissements La Poste : dérogation, la somme des chiffres doit être un multiple de 5.
    return siret.startswith(_LA_POSTE_SIREN) and sum(map(int, siret)) % 5 == 0


def fr_vat_key(siren: str) -> str:
    """Clé TVA intracommunautaire FR : (12 + 3 × (SIREN mod 97)) mod 97."""
    siren = _compact(siren)
    if len(siren) != 9 or not siren.isdigit():
        raise ValueError("SIREN attendu sur 9 chiffres")
    return f"{(12 + 3 * (int(siren) % 97)) % 97:02d}"


def fr_vat_from_siren(siren: str) -> str:
    siren = _compact(siren)
    return f"FR{fr_vat_key(siren)}{siren}"


def is_valid_fr_vat(value: str) -> bool:
    """Contrôle les numéros FR à clé numérique ; les anciennes clés alphanumériques ne sont pas vérifiables."""
    vat = _compact(value).upper()
    m = re.fullmatch(r"FR([0-9A-Z]{2})(\d{9})", vat)
    if not m:
        return False
    key, siren = m.groups()
    if not key.isdigit():
        return True
    return key == fr_vat_key(siren)


def siren_from_fr_vat(value: str) -> str | None:
    m = re.fullmatch(r"FR[0-9A-Z]{2}(\d{9})", _compact(value).upper())
    return m.group(1) if m else None


def is_valid_iban(value: str) -> bool:
    iban = _compact(value).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", iban):
        return False
    expected = IBAN_LENGTHS.get(iban[:2])
    if expected is not None and len(iban) != expected:
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(numeric) % 97 == 1
