"""Exécution hors thread UI.

Les traitements tournent dans un ``ThreadPoolExecutor`` **Python** et non dans ``QThreadPool`` :
lxml/libxml2 n'est pas fiable dans des threads natifs créés hors de Python (crash constaté).
Les résultats remontent par signaux Qt, automatiquement mis en file vers le thread UI.
"""
from __future__ import annotations

import logging
import os
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from PySide6.QtCore import QObject, Signal

from fchecker.core.plugin import RunContext

log = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None


def executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=min(8, (os.cpu_count() or 2)), thread_name_prefix="fe-worker")
    return _executor


def shutdown() -> None:
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None


class WorkerSignals(QObject):
    finished = Signal(object)   # résultat
    failed = Signal(object)     # exception
    progress = Signal(int, str)
    finding = Signal(object)    # Finding publié au fil de l'eau


class Worker:
    """Exécute ``fn(ctx)`` hors thread UI. ``fn`` ne doit jamais toucher aux widgets.

    Connecter les signaux **avant** ``start()`` : un traitement rapide pourrait sinon les perdre.

    ``WorkerSignals`` a un parent Qt et n'est détruit que par ``deleteLater()`` dans le thread UI :
    sans cela, le ramasse-miettes Python peut le libérer depuis un thread de travail (crash natif).
    """

    def __init__(self, fn: Callable[[RunContext], Any], parent: QObject) -> None:
        self.fn = fn
        self.signals = WorkerSignals(parent)
        self.ctx = RunContext(
            on_progress=self.signals.progress.emit,
            on_finding=self.signals.finding.emit,
        )

    def cancel(self) -> None:
        self.ctx.cancel_event.set()

    def start(self) -> Worker:
        # Connecté en dernier : la destruction est postée après les slots de l'appelant.
        self.signals.finished.connect(self.signals.deleteLater)
        self.signals.failed.connect(self.signals.deleteLater)
        executor().submit(self._run)
        return self

    def _run(self) -> None:
        try:
            result = self.fn(self.ctx)
        except Exception as exc:
            log.error("Échec du traitement : %s\n%s", exc, traceback.format_exc())
            self.signals.failed.emit(exc)
        else:
            self.signals.finished.emit(result)
