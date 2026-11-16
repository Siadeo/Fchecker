"""Accès aux packs de règles embarqués (``resources/rules/<pack>/pack.yaml``)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path

import yaml


@dataclass(frozen=True)
class RulePack:
    id: str
    version: str
    root: Path
    source: str = ""

    def path(self, rel: str) -> Path:
        return self.root / rel

    def has(self, rel: str) -> bool:
        return (self.root / rel).is_file()


def rules_root() -> Path:
    return Path(str(resources.files("fchecker").joinpath("resources", "rules")))


@cache
def load_packs() -> dict[str, RulePack]:
    packs: dict[str, RulePack] = {}
    root = rules_root()
    if not root.is_dir():
        return packs
    for manifest in sorted(root.glob("*/pack.yaml")):
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        pack = RulePack(
            id=data["id"],
            version=str(data["version"]),
            root=manifest.parent,
            source=data.get("source", ""),
        )
        packs[pack.id] = pack
    return packs


def get_pack(pack_id: str) -> RulePack | None:
    return load_packs().get(pack_id)
