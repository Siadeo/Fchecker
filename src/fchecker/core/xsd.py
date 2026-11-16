"""Validation XSD (lxml), schémas compilés une fois et mis en cache."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

_cache: dict[Path, etree.XMLSchema] = {}
_lock = threading.Lock()


@dataclass(frozen=True, slots=True)
class XsdError:
    line: int | None
    message: str
    path: str | None


def schema(path: Path) -> etree.XMLSchema:
    with _lock:
        s = _cache.get(path)
        if s is None:
            s = _cache[path] = etree.XMLSchema(etree.parse(str(path)))
        return s


def validate(path: Path, tree: etree._ElementTree) -> list[XsdError]:
    s = schema(path)
    with _lock:  # error_log est porté par l'objet schéma partagé
        if s.validate(tree):
            return []
        return [XsdError(e.line or None, e.message, e.path) for e in s.error_log]
