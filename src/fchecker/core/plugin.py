"""Contrat des outils (plugins).

Un plugin est un sous-paquet de ``fchecker.plugins`` dont le ``__init__.py`` ne déclare
que ``SPEC = ToolSpec(...)``. La classe ``Tool`` (et sa vue Qt) n'est importée qu'au
premier usage, ce qui garde le démarrage rapide.
"""
from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .findings import Finding
from .report import Report

if TYPE_CHECKING:
    from .document import InvoiceDocument


@dataclass(frozen=True, slots=True)
class ToolSpec:
    id: str
    name: str
    icon: str
    order: int
    factory: str  # "module.path:ClassName"
    description: str = ""
    runnable: bool = True  # participe à « Tout valider » (F5)
    label: str = ""  # libellé court sous l'icône de la barre d'activité (défaut : name en majuscules)

    @property
    def short_label(self) -> str:
        return self.label or self.name.upper()


class CancelledError(Exception):
    pass


@dataclass(slots=True)
class RunContext:
    cancel_event: threading.Event = field(default_factory=threading.Event)
    on_progress: Callable[[int, str], None] | None = None
    on_finding: Callable[[Finding], None] | None = None

    def progress(self, pct: int, message: str = "") -> None:
        if self.on_progress:
            self.on_progress(pct, message)

    def emit(self, finding: Finding) -> None:
        if self.on_finding:
            self.on_finding(finding)

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise CancelledError


class Tool(ABC):
    spec: ToolSpec

    def __init__(self, spec: ToolSpec) -> None:
        self.spec = spec

    def accepts(self, doc: InvoiceDocument) -> bool:
        return True

    def run(self, doc: InvoiceDocument, ctx: RunContext) -> Report:
        """Traitement pur Python, exécuté hors du thread UI. Doit être thread-safe.

        Chaque constat est traduit par le catalogue avant publication : un outil n'a pas à s'en soucier.
        """
        start = time.perf_counter()
        report = Report(tool_id=self.spec.id, rule_packs=self.rule_packs())
        for finding in self.check(doc, ctx):
            ctx.check_cancelled()
            self.publish(finding, report, ctx)
        report.duration = time.perf_counter() - start
        return report

    @staticmethod
    def publish(finding: Finding, report: Report, ctx: RunContext) -> Finding:
        """Traduit le constat, l'ajoute au rapport et le publie au fil de l'eau."""
        from .rules_catalog import catalog

        finding = catalog().enrich(finding)
        report.findings.append(finding)
        ctx.emit(finding)
        return finding

    def rule_packs(self) -> dict[str, str]:
        """Versions des packs de règles utilisés (pour le rapport)."""
        return {}

    def check(self, doc: InvoiceDocument, ctx: RunContext):
        """Générateur de findings ; à surcharger par les outils de contrôle."""
        return iter(())

    @abstractmethod
    def create_view(self, parent: Any, doc: InvoiceDocument) -> Any:
        """Retourne le QWidget de l'outil pour ce document (import Qt local à l'implémentation).

        Si la vue expose ``show_report(report)``, elle reçoit le résultat de chaque exécution.
        """
