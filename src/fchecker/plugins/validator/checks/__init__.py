"""Sous-contrôles du validateur.

Chaque module du paquet expose ``CHECK = MaClasse()`` (sous-classe de :class:`Check`) ;
ils sont découverts automatiquement et exécutés par ordre croissant de ``order``.

Les contrôles qui lisent l'arbre XML s'exécutent séquentiellement (lxml : pas d'accès
concurrent au même document). Un contrôle ``concurrent`` (ex. appel réseau) extrait
d'abord ses données via :meth:`Check.prepare` puis s'exécute en parallèle.
"""
from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from typing import Any

from fchecker.core.document import InvoiceDocument
from fchecker.core.findings import Finding
from fchecker.core.plugin import RunContext


class Check:
    id: str = ""
    label: str = ""
    order: int = 100
    concurrent: bool = False

    def applies(self, doc: InvoiceDocument) -> bool:
        return True

    def prepare(self, doc: InvoiceDocument) -> Any:
        """Extraction (séquentielle) des données utiles à un contrôle concurrent."""
        return doc

    def run(self, data: Any, ctx: RunContext) -> Iterable[Finding]:
        raise NotImplementedError

    def packs(self) -> dict[str, str]:
        return {}


def discover() -> list[Check]:
    checks: list[Check] = []
    for info in pkgutil.iter_modules(__path__, prefix=f"{__name__}."):
        module = importlib.import_module(info.name)
        check = getattr(module, "CHECK", None)
        if isinstance(check, Check):
            checks.append(check)
    return sorted(checks, key=lambda c: c.order)
