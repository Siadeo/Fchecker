from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum


class Severity(IntEnum):
    """Ordonné du plus grave au moins grave (tri naturel)."""

    FATAL = 0
    ERROR = 1
    WARNING = 2
    INFO = 3

    @property
    def label(self) -> str:
        return _SEVERITY_LABELS[self]


_SEVERITY_LABELS = {
    Severity.FATAL: "Bloquant",
    Severity.ERROR: "Erreur",
    Severity.WARNING: "Avertissement",
    Severity.INFO: "Information",
}


class Source(str, Enum):
    LOADER = "chargement"
    PROFILE = "profil"
    XSD = "xsd"
    SCHEMATRON_EN = "schematron EN 16931"
    SCHEMATRON_FR = "règles FR"
    PDFA = "pdf/a-3"
    IDENTIFIERS = "identifiants"
    PEPPOL = "annuaire Peppol"
    MENTIONS = "mentions"
    CONSISTENCY = "cohérence"


@dataclass(frozen=True, slots=True)
class Finding:
    """Constat. ``message`` est le texte d'origine (schematron, contrôle) ; ``title``,
    ``explanation`` et ``example`` sont ajoutés par le catalogue de traduction."""

    rule_id: str
    severity: Severity
    source: Source
    message: str
    bt: str | None = None
    xpath: str | None = None
    line: int | None = None
    suggestion: str | None = None
    title: str | None = None
    explanation: str | None = None
    example: str | None = None
    translated: bool = False
    pdf_hint: str | None = None  # texte à surligner dans le PDF (contrôle de cohérence)
    details: str | None = None   # complément affiché sous le titre dans la fiche du constat
    listing_title: str | None = None
    listing: tuple[str, ...] = ()  # liste affichée en bas de la fiche (ex. types de documents du SMP)

    @property
    def display_message(self) -> str:
        return self.title or self.message
