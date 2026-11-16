"""Exécution des schematrons précompilés (XSLT 2/3) avec SaxonC-HE.

Saxon tourne dans un **processus séparé** (``saxon_worker``) : saxonche garde le GIL pendant ses
calculs et gelait l'interface lorsqu'il tournait dans le processus de l'application. Compilation
~0,1-0,4 s par XSLT (une fois par processus), exécution à chaud en quelques dizaines de ms.
"""
from __future__ import annotations

import atexit
import logging
import multiprocessing
import re
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

log = logging.getLogger(__name__)

NS_SVRL = "http://purl.oclc.org/dsdl/svrl"
COMPILE_TIMEOUT = 120  # s ; la 1re requête inclut le démarrage du processus (~1 s)
_BT = re.compile(r"\b(BT-\d+|BG-\d+|EXT-FR-FE-\d+)\b")


@dataclass(frozen=True, slots=True)
class SvrlResult:
    rule_id: str          # id normalisé (ex. BR-FR-05)
    raw_id: str           # id d'origine (ex. BR-FR-05_BT-22_PMT)
    flag: str | None      # fatal / warning / information / None
    text: str
    location: str | None
    kind: str             # failed-assert | successful-report
    bts: tuple[str, ...]


def normalize_rule_id(raw: str | None, text: str) -> str:
    """``BR-FR-05_BT-22_PMT`` → ``BR-FR-05`` ; ``BR-FR-28-Value`` → ``BR-FR-28`` ;
    sans id, on tente ``[BR-XX]`` en tête du texte."""
    if raw:
        if raw.startswith("BR-FR-"):  # BR-FR-05_BT-22_PMT → BR-FR-05 (les variantes par BT sont regroupées)
            m = re.match(r"(BR-FR-(?:[A-Z]+-)?\d+)", raw)
            return m.group(1) if m else raw
        return raw
    m = re.search(r"\[([A-Z][A-Z0-9]*(?:-[A-Za-z0-9]+)+)(?:/[^\]]*)?\]", text)  # [ID] ou [ID/BT-x] cité
    if m:
        return normalize_rule_id(m.group(1), "") if m.group(1).startswith("BR-FR-") else m.group(1)
    m = re.search(r"\b(BR-FR-(?:[A-Z]+-)?\d+)", text)  # « invoiceID : BR-FR-BD-02/BT-30 : … »
    return m.group(1) if m else "SCH"


def parse_svrl(svrl: bytes) -> list[SvrlResult]:
    root = etree.fromstring(svrl)
    out: list[SvrlResult] = []
    for el in root.iter(f"{{{NS_SVRL}}}failed-assert", f"{{{NS_SVRL}}}successful-report"):
        text = " ".join((el.findtext(f"{{{NS_SVRL}}}text") or "").split())
        raw = el.get("id")
        out.append(SvrlResult(
            rule_id=normalize_rule_id(raw, text),
            raw_id=raw or "",
            flag=(el.get("flag") or None),
            text=text,
            location=el.get("location"),
            kind=etree.QName(el).localname,
            bts=tuple(dict.fromkeys(_BT.findall(text))),
        ))
    return out


class SchematronEngine:
    """Singleton : pilote le processus Saxon (``saxon_worker.serve``) et mémorise les XSLT compilées.

    Appelable depuis n'importe quel thread ; les requêtes sont sérialisées par un verrou. L'attente
    de la réponse (pipe) libère le GIL : l'interface n'est jamais gelée. Si le processus meurt ou ne
    répond plus, il est relancé à la requête suivante et la requête en cours lève ``RuntimeError``.
    """

    _instance: SchematronEngine | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process = None
        self._conn = None
        self._compiled: set[Path] = set()

    @classmethod
    def instance(cls) -> SchematronEngine:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
                atexit.register(cls.shutdown)
            return cls._instance

    @classmethod
    def shutdown(cls) -> None:
        """Arrête proprement le processus Saxon (à la fermeture de l'application)."""
        with cls._instance_lock:
            engine, cls._instance = cls._instance, None
        if engine is not None:
            with engine._lock:
                engine._stop()

    # --- API --------------------------------------------------------------------------
    def warm_up(self, paths: list[Path]) -> Future:
        """Compile en tâche de fond, un fichier à la fois (une validation peut s'intercaler)."""
        future: Future = Future()

        def compile_all() -> None:
            done = 0
            try:
                for p in paths:
                    if p.is_file():
                        self._call(("compile", str(p)), COMPILE_TIMEOUT)
                        self._compiled.add(p)
                        done += 1
            except Exception as exc:
                future.set_exception(exc)
            else:
                future.set_result(done)

        threading.Thread(target=compile_all, name="saxon-warmup", daemon=True).start()
        return future

    def validate(self, xslt: Path, xml: str | bytes, timeout: float | None = 120) -> list[SvrlResult]:
        """``xml`` : de préférence ``InvoiceDocument.xml_text`` (déjà normalisé par lxml)."""
        if isinstance(xml, bytes):
            xml = xml.decode("utf-8-sig")  # retire un éventuel BOM
        svrl = self._call(("transform", str(xslt), xml), timeout)
        self._compiled.add(xslt)
        return parse_svrl(svrl.encode("utf-8"))

    def is_compiled(self, xslt: Path) -> bool:
        return xslt in self._compiled

    # --- Processus fils ------------------------------------------------------------------
    def _call(self, message: tuple, timeout: float | None):
        with self._lock:
            conn = self._ensure_process()
            try:
                conn.send(message)
                if not conn.poll(timeout):
                    self._kill()
                    raise RuntimeError(f"Saxon ne répond pas (délai de {timeout} s dépassé)")
                status, payload = conn.recv()
            except (EOFError, OSError) as exc:
                self._kill()
                raise RuntimeError(f"processus Saxon interrompu ({type(exc).__name__})") from exc
        if status != "ok":
            raise RuntimeError(payload)
        return payload

    def _ensure_process(self):
        if self._process is None or not self._process.is_alive():
            self._kill()
            ctx = multiprocessing.get_context("spawn")
            parent, child = ctx.Pipe()
            from .saxon_worker import serve

            self._process = ctx.Process(target=serve, args=(child,), name="fchecker-saxon", daemon=True)
            self._process.start()
            child.close()
            self._conn = parent
            self._compiled.clear()
            log.info("Processus Saxon démarré (pid %s)", self._process.pid)
        return self._conn

    def _stop(self) -> None:
        if self._conn is not None and self._process is not None and self._process.is_alive():
            try:
                self._conn.send(("stop",))
                if self._conn.poll(5):
                    self._conn.recv()
            except (EOFError, OSError):
                pass
            self._process.join(5)
        self._kill()

    def _kill(self) -> None:
        if self._process is not None and self._process.is_alive():
            self._process.terminate()
            self._process.join(2)
        if self._conn is not None:
            self._conn.close()
        self._process = self._conn = None
        self._compiled.clear()
