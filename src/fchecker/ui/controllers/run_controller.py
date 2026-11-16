from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal

from fchecker.core.registry import Registry
from fchecker.core.report import Report
from fchecker.ui.document_tab import DocumentTab
from fchecker.ui.workers import Worker


class RunController(QObject):
    """Lance les outils exécutables sur un document ; les constats arrivent au fil de l'eau."""

    started = Signal(object)                # DocumentTab
    finished = Signal(object, float)        # DocumentTab, durée totale (s)
    tool_failed = Signal(str, str)          # tool_id, message

    def __init__(self, registry: Registry, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.registry = registry
        self._running: dict[DocumentTab, set[Worker]] = {}

    def is_running(self, tab: DocumentTab) -> bool:
        return bool(self._running.get(tab))

    def run_all(self, tab: DocumentTab) -> None:
        if self.is_running(tab):
            return
        doc = tab.doc
        tool_ids = [s.id for s in self.registry.specs if s.runnable]
        tab.findings.clear()
        tab.reports.clear()
        workers: set[Worker] = set()
        self._running[tab] = workers
        t0 = time.perf_counter()
        self.started.emit(tab)

        for tool_id in tool_ids:
            tool = self.registry.get_tool(tool_id)
            if not tool.accepts(doc):
                continue
            worker = Worker(lambda ctx, t=tool: t.run(doc, ctx), self)
            workers.add(worker)
            worker.signals.finding.connect(lambda f: tab.findings.append([f]))
            worker.signals.finished.connect(lambda rep, w=worker: self._done(tab, w, rep, t0))
            worker.signals.failed.connect(lambda exc, w=worker, tid=tool_id: self._fail(tab, w, tid, exc, t0))

        if not workers:
            self._finish(tab, t0)
            return
        # Démarrage après enregistrement de tous les workers : un outil qui termine
        # immédiatement ne peut pas déclencher _finish() avant que les suivants soient lancés.
        for worker in list(workers):
            worker.start()

    def cancel(self, tab: DocumentTab) -> None:
        for w in self._running.get(tab, ()):
            w.cancel()

    def _done(self, tab: DocumentTab, worker: Worker, report: Report, t0: float) -> None:
        tab.set_report(report)
        self._release(tab, worker, t0)

    def _fail(self, tab: DocumentTab, worker: Worker, tool_id: str, exc: Exception, t0: float) -> None:
        self.tool_failed.emit(tool_id, str(exc) or type(exc).__name__)
        self._release(tab, worker, t0)

    def _release(self, tab: DocumentTab, worker: Worker, t0: float) -> None:
        workers = self._running.get(tab)
        if workers is None:
            return
        workers.discard(worker)
        if not workers:
            self._finish(tab, t0)

    def _finish(self, tab: DocumentTab, t0: float) -> None:
        self._running.pop(tab, None)
        self.finished.emit(tab, time.perf_counter() - t0)
