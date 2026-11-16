from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from fchecker.core.findings import Finding, Severity, Source
from fchecker.core.plugin import CancelledError, Tool
from fchecker.core.report import Report

log = logging.getLogger(__name__)


class ValidatorTool(Tool):
    """Orchestre les sous-contrôles (``checks/``) et note leur bilan dans ``report.meta['checks']``."""

    def __init__(self, spec) -> None:
        super().__init__(spec)
        from .checks import discover

        self.checks = discover()

    def rule_packs(self):
        packs: dict[str, str] = {}
        for c in self.checks:
            packs.update(c.packs())
        return packs

    def run(self, doc, ctx) -> Report:
        start = time.perf_counter()
        report = Report(tool_id=self.spec.id, rule_packs=self.rule_packs())
        summary: list[dict] = []
        applicable = [c for c in self.checks if c.applies(doc)]

        # Les contrôles concurrents (réseau) démarrent d'abord, sur des données déjà extraites ;
        # leurs résultats sont publiés après les contrôles séquentiels.
        concurrent = [c for c in applicable if c.concurrent]
        pool = ThreadPoolExecutor(max_workers=len(concurrent), thread_name_prefix="fe-check") if concurrent else None
        futures = {c.id: pool.submit(self._timed, c, c.prepare(doc), ctx) for c in concurrent}
        try:
            for c in applicable:
                if c.concurrent:
                    continue
                t0 = time.perf_counter()
                findings = self._safe(c, lambda c=c: c.run(doc, ctx), report, ctx)
                summary.append(self._summary(c, findings, time.perf_counter() - t0))
            for c in concurrent:
                holder: dict = {}
                findings = self._safe(c, lambda c=c: self._unwrap(futures[c.id], holder), report, ctx)
                summary.append(self._summary(c, findings, holder.get("duration", 0.0)))
        finally:
            if pool is not None:
                pool.shutdown(wait=False, cancel_futures=True)

        order = {c.id: c.order for c in self.checks}
        report.meta["checks"] = sorted(summary, key=lambda s: order.get(s["id"], 0))
        report.duration = time.perf_counter() - start
        return report

    @staticmethod
    def _timed(check, data, ctx) -> tuple[float, list[Finding]]:
        t0 = time.perf_counter()
        findings = list(check.run(data, ctx))
        return time.perf_counter() - t0, findings

    @staticmethod
    def _unwrap(future, holder: dict) -> list[Finding]:
        holder["duration"], findings = future.result()
        return findings

    def _safe(self, check, produce, report, ctx) -> list[Finding]:
        published: list[Finding] = []
        try:
            for f in produce():
                ctx.check_cancelled()
                published.append(self.publish(f, report, ctx))
        except CancelledError:
            raise
        except Exception as exc:
            log.exception("Contrôle %s en échec", check.id)
            published.append(self.publish(Finding("SCH-ERROR", Severity.ERROR, Source.LOADER,
                                                  f"{check.label} : contrôle non effectué, erreur technique "
                                                  f"({exc})"), report, ctx))
        return published

    @staticmethod
    def _summary(check, findings: list[Finding], duration: float) -> dict:
        counts = {s: 0 for s in Severity}
        for f in findings:
            counts[f.severity] += 1
        return {"id": check.id, "label": check.label, "duration": duration, "counts": counts}

    def create_view(self, parent, doc):
        from .view import ValidatorView

        return ValidatorView(self.spec, parent)
