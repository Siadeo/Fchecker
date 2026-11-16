from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal

from fchecker.core import loader
from fchecker.core.document import InvoiceDocument
from fchecker.ui.workers import Worker

MAX_RECENT = 8


class DocumentController(QObject):
    """Ouverture des fichiers (chargement hors thread UI) et fichiers récents."""

    loaded = Signal(object)          # InvoiceDocument
    failed = Signal(str, str)        # chemin, message
    recent_changed = Signal(list)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings()
        self._pending: set[Worker] = set()

    def open(self, path: str | Path) -> None:
        path = Path(path)
        worker = Worker(lambda ctx: loader.load(path), self)
        self._pending.add(worker)
        worker.signals.finished.connect(lambda doc, w=worker: self._done(w, doc))
        worker.signals.failed.connect(lambda exc, w=worker: self._fail(w, path, exc))
        worker.start()

    def _done(self, worker: Worker, doc: InvoiceDocument) -> None:
        self._pending.discard(worker)
        self._push_recent(str(doc.path))
        self.loaded.emit(doc)

    def _fail(self, worker: Worker, path: Path, exc: Exception) -> None:
        self._pending.discard(worker)
        self.failed.emit(str(path), str(exc))

    def recent(self) -> list[str]:
        value = self._settings.value("recentFiles", [])
        if isinstance(value, str):  # QSettings renvoie une str pour une liste à 1 élément
            value = [value]
        return list(value or [])

    def _push_recent(self, path: str) -> None:
        items = [p for p in self.recent() if p != path]
        items.insert(0, path)
        self._settings.setValue("recentFiles", items[:MAX_RECENT])
        self.recent_changed.emit(items[:MAX_RECENT])
