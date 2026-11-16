from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .findings import Finding, Severity


@dataclass(slots=True)
class Report:
    tool_id: str
    findings: list[Finding] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    duration: float = 0.0
    rule_packs: dict[str, str] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)  # détails propres à l'outil (ex. sous-contrôles)

    def counts(self) -> dict[Severity, int]:
        c = Counter(f.severity for f in self.findings)
        return {s: c.get(s, 0) for s in Severity}

    @property
    def is_blocking(self) -> bool:
        return any(f.severity <= Severity.ERROR for f in self.findings)

    def merge(self, other: Report) -> Report:
        self.findings.extend(other.findings)
        self.duration += other.duration
        self.rule_packs.update(other.rule_packs)
        return self
