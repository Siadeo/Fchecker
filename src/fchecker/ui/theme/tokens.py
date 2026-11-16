"""Tokens de couleur : seule source des couleurs de l'application."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Palette:
    bg: str
    surface: str
    surface_alt: str
    border: str
    text: str
    text_muted: str
    accent: str
    accent_text: str
    selection: str
    fatal: str
    error: str
    warning: str
    info: str
    ok: str
    # Vue XML : coloration syntaxique et recherche
    syn_tag: str
    syn_attr: str
    syn_value: str
    syn_comment: str
    syn_decl: str
    find_match: str
    find_current: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


LIGHT = Palette(
    bg="#f4f5f7",
    surface="#ffffff",
    surface_alt="#eceef2",
    border="#d7dbe2",
    text="#1d2330",
    text_muted="#667085",
    accent="#1f5eff",
    accent_text="#ffffff",
    selection="#dbe5ff",
    fatal="#9f1239",
    error="#d92d20",
    warning="#b54708",
    info="#1f5eff",
    ok="#067647",
    syn_tag="#1d4ed8",
    syn_attr="#9a3412",
    syn_value="#047857",
    syn_comment="#6b7280",
    syn_decl="#7c3aed",
    find_match="#fde68a",
    find_current="#f59e0b",
)

DARK = Palette(
    bg="#16181d",
    surface="#1e2128",
    surface_alt="#262a33",
    border="#343a46",
    text="#e6e8ee",
    text_muted="#98a2b3",
    accent="#5b8cff",
    accent_text="#0b0d12",
    selection="#2a3a66",
    fatal="#fb7185",
    error="#f97066",
    warning="#fdb022",
    info="#84adff",
    ok="#47cd89",
    syn_tag="#7cacf8",
    syn_attr="#f0a36b",
    syn_value="#7ee0b0",
    syn_comment="#7d8696",
    syn_decl="#c4a7ff",
    find_match="#5c4a14",
    find_current="#a16207",
)
