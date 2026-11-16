from __future__ import annotations

import time
from importlib import resources

import yaml

from fchecker.core.invoice import invoice_of
from fchecker.core.plugin import Tool
from fchecker.core.report import Report


class MentionsTool(Tool):
    """Check-list des mentions obligatoires ; constats émis uniquement hors couverture des schematrons."""

    def __init__(self, spec) -> None:
        super().__init__(spec)
        from .predicates import PREDICATES

        text = resources.files(__package__).joinpath("rules.yaml").read_text(encoding="utf-8")
        self.rules: dict[str, dict] = yaml.safe_load(text)
        self.predicates = PREDICATES
        missing = set(self.rules) ^ set(self.predicates)
        if missing:
            raise RuntimeError(f"Mentions sans métadonnée ou sans logique : {sorted(missing)}")

    def run(self, doc, ctx) -> Report:
        start = time.perf_counter()
        report = Report(tool_id=self.spec.id)
        inv = invoice_of(doc)
        checklist = []
        for rule_id, meta in self.rules.items():
            ctx.check_cancelled()
            outcome = self.predicates[rule_id](inv, doc)
            for finding in outcome.findings:
                self.publish(finding, report, ctx)
            checklist.append({
                "id": rule_id, "label": meta["label"], "legal": meta.get("legal", ""), "bt": meta.get("bt", ""),
                "status": outcome.status, "detail": outcome.detail,
                "covered_by": meta.get("covered_by") if outcome.presence_only else None,
            })
        report.meta["mentions"] = checklist
        report.duration = time.perf_counter() - start
        return report

    def create_view(self, parent, doc):
        from .view import MentionsView

        return MentionsView(self.spec, parent)
