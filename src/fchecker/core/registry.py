"""Découverte et instanciation paresseuse des outils."""
from __future__ import annotations

import importlib
import logging
import pkgutil
import threading
from importlib.metadata import entry_points

from .plugin import Tool, ToolSpec

log = logging.getLogger(__name__)

PLUGIN_PACKAGE = "fchecker.plugins"
ENTRY_POINT_GROUP = "fchecker.tools"


class Registry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._tools: dict[str, Tool] = {}
        self._lock = threading.Lock()

    def discover(self) -> list[ToolSpec]:
        """Lit uniquement les ``SPEC`` des plugins (sans importer leur implémentation)."""
        specs: dict[str, ToolSpec] = {}
        package = importlib.import_module(PLUGIN_PACKAGE)
        for info in pkgutil.iter_modules(package.__path__, prefix=f"{PLUGIN_PACKAGE}."):
            if not info.ispkg:
                continue
            self._add(specs, info.name, lambda name=info.name: importlib.import_module(name).SPEC)
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            self._add(specs, ep.name, ep.load)
        self._specs = dict(sorted(specs.items(), key=lambda kv: (kv[1].order, kv[1].name)))
        return list(self._specs.values())

    @staticmethod
    def _add(specs: dict[str, ToolSpec], origin: str, loader) -> None:
        try:
            spec = loader()
        except Exception:
            log.exception("Plugin ignoré (%s)", origin)
            return
        if not isinstance(spec, ToolSpec):
            log.warning("Plugin ignoré (%s) : SPEC absent ou invalide", origin)
            return
        if spec.id in specs:
            log.warning("Plugin en double ignoré : %s (%s)", spec.id, origin)
            return
        specs[spec.id] = spec

    @property
    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def spec(self, tool_id: str) -> ToolSpec:
        return self._specs[tool_id]

    def get_tool(self, tool_id: str) -> Tool:
        """Instancie l'outil au premier appel (thread-safe), puis le réutilise."""
        with self._lock:
            tool = self._tools.get(tool_id)
            if tool is None:
                spec = self._specs[tool_id]
                module_name, _, class_name = spec.factory.partition(":")
                cls = getattr(importlib.import_module(module_name), class_name)
                tool = self._tools[tool_id] = cls(spec)
            return tool

    def is_loaded(self, tool_id: str) -> bool:
        return tool_id in self._tools
