"""Client de l'annuaire Peppol (API REST publique « Peppol Directory »), avec cache SQLite.

``GET {url}?participant=iso6523-actorid-upis::0225:100000009_FOURNISSEUR`` →
``{"matches": [{"participantID": {"value": "0225:…"}, "docTypes": [{"value": "…"}], "entities": [...]}]}``

L'annuaire Peppol est public et facultatif (les cartes de visite y sont publiées par les points d'accès) :
l'absence d'un participant ne prouve pas qu'il est injoignable. Limite d'usage : environ 2 requêtes par seconde.

SMP du participant (API REST de peppol.helger.com, ``SmpClient``) :
``GET {url}/ppidexistence/peppolprod/{participant}`` → ``{"exists": true, "smpHostURI": "http://…"}``, puis
``GET {url}/smpquery/peppolprod/{participant}`` → ``{"urls": [{"documentTypeID": "…", "niceName": "…",
"isDeprecated": false}]}`` : les types de documents publiés par le SMP (source de référence du routage).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import quote

import httpx

from fchecker.core import settings as app_settings
from fchecker.core.document import DocFormat

log = logging.getLogger(__name__)

SCHEME = "iso6523-actorid-upis"
SML = "peppolprod"           # réseau Peppol de production
MIN_INTERVAL = 0.5           # secondes entre deux requêtes (limite de l'API)

# Marqueurs des identifiants de types de documents acceptant chaque format de facture
_DOC_TYPE_MARKERS = {
    DocFormat.FACTURX: ("urn:peppol:doctype:pdf+xml", "CrossIndustryInvoice:100::CrossIndustryInvoice"),
    DocFormat.CII: ("CrossIndustryInvoice:100::CrossIndustryInvoice",),
    DocFormat.UBL: ("Invoice-2::Invoice##", "CreditNote-2::CreditNote##"),
}

_throttle_lock = threading.Lock()
_last_request = 0.0


class LookupStatus(str, Enum):
    OK = "ok"                # réponse exploitable (éventuellement vide)
    DISABLED = "désactivé"
    REJECTED = "refusée"     # l'annuaire a répondu : c'est l'adresse qu'il refuse (HTTP 400)
    ERROR = "erreur"


class LookupCache:
    """Cache SQLite (une connexion par appel : utilisable depuis n'importe quel thread)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS entries (siren TEXT PRIMARY KEY, fetched REAL, payload TEXT)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def get(self, key: str, max_age: float) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT fetched, payload FROM entries WHERE siren = ?", (key,)).fetchone()
        if row and time.time() - row[0] <= max_age:
            return json.loads(row[1])
        return None

    def put(self, key: str, payload: dict) -> None:
        with self._connect() as db:
            db.execute("REPLACE INTO entries VALUES (?, ?, ?)", (key, time.time(), json.dumps(payload)))

    def clear(self) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM entries")


@dataclass(frozen=True, slots=True)
class PeppolParticipant:
    identifier: str                      # ex. 0225:100000009_FOURNISSEUR
    doc_types: tuple[str, ...] = ()
    names: tuple[str, ...] = ()


@dataclass(slots=True)
class PeppolResult:
    participant: str
    status: LookupStatus
    matches: list[PeppolParticipant] = field(default_factory=list)
    from_cache: bool = False
    error: str | None = None

    @property
    def doc_types(self) -> list[str]:
        return [d for m in self.matches for d in m.doc_types]


def parse_matches(payload: dict) -> list[PeppolParticipant]:
    out = []
    for item in payload.get("matches") or []:
        names = tuple(n.get("name", "") for e in item.get("entities") or [] for n in e.get("name") or [])
        out.append(PeppolParticipant(
            identifier=str((item.get("participantID") or {}).get("value", "")),
            doc_types=tuple(str(d.get("value", "")) for d in item.get("docTypes") or []),
            names=tuple(n for n in names if n),
        ))
    return out


def accepts(doc_types: list[str] | tuple[str, ...], fmt: DocFormat) -> bool:
    """Le participant annonce-t-il un type de document compatible avec le format de la facture ?"""
    markers = _DOC_TYPE_MARKERS.get(fmt, ())
    return any(m in d for d in doc_types for m in markers)


def short_doc_type(doc_type: str) -> str:
    """``urn:…:Invoice-2::Invoice##urn:…:peppol:france:billing:cius:1.0::2.1`` → ``Invoice (…cius:1.0)``."""
    root, _, rest = doc_type.partition("##")
    name = root.rsplit("::", 1)[-1] if "::" in root else root.rsplit(":", 1)[-1]
    custom = rest.rsplit("#", 1)[-1].split("::", 1)[0] if rest else ""
    return f"{name} ({custom})" if custom else name


def _throttle() -> None:
    global _last_request
    with _throttle_lock:
        wait = _last_request + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


class PeppolClient:
    def __init__(self, url: str, timeout: float = 5.0, cache: LookupCache | None = None,
                 cache_seconds: float = 86400, transport: httpx.BaseTransport | None = None) -> None:
        self.url = url
        self.timeout = timeout
        self.cache = cache
        self.cache_seconds = cache_seconds
        self._transport = transport  # tests : httpx.MockTransport

    @classmethod
    def from_settings(cls) -> PeppolClient | None:
        s = app_settings.get()
        if not s.peppol_enabled:
            return None
        cache = LookupCache(app_settings.cache_dir() / "peppol.sqlite")
        return cls(s.peppol_url, s.peppol_timeout, cache, s.peppol_cache_hours * 3600)

    def lookup(self, scheme: str, value: str) -> PeppolResult:
        participant = f"{scheme}:{value}"
        key = participant.lower()  # identifiants Peppol insensibles à la casse
        if self.cache is not None:
            cached = self.cache.get(key, self.cache_seconds)
            if cached is not None:
                return PeppolResult(participant, LookupStatus.OK, parse_matches(cached), from_cache=True)
        try:
            if self._transport is None:
                _throttle()
            with httpx.Client(timeout=self.timeout, transport=self._transport,
                              headers={"User-Agent": "fchecker"}) as client:
                r = client.get(self.url, params={"participant": f"{SCHEME}::{participant}"})
            if r.status_code == 400:
                return PeppolResult(participant, LookupStatus.REJECTED, error="HTTP 400")
            if r.status_code != 200:
                return PeppolResult(participant, LookupStatus.ERROR, error=f"HTTP {r.status_code}")
            payload = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.info("Annuaire Peppol injoignable pour %s : %s", participant, exc)
            return PeppolResult(participant, LookupStatus.ERROR, error=type(exc).__name__)
        if self.cache is not None:
            self.cache.put(key, payload)
        return PeppolResult(participant, LookupStatus.OK, parse_matches(payload))


@dataclass(frozen=True, slots=True)
class SmpDocType:
    identifier: str
    name: str                            # libellé lisible (niceName), à défaut forme courte de l'identifiant
    deprecated: bool = False


@dataclass(slots=True)
class SmpResult:
    participant: str
    status: LookupStatus
    exists: bool = False                 # enregistré dans le SML (réseau Peppol)
    host: str | None = None              # ex. smp.helger.com
    doc_types: tuple[SmpDocType, ...] = ()
    from_cache: bool = False
    error: str | None = None


def parse_smp(payload: dict) -> tuple[bool, str | None, tuple[SmpDocType, ...]]:
    existence = payload.get("existence") or {}
    host = (existence.get("smpHostURI") or "").split("://", 1)[-1].rstrip("/") or None
    doc_types = tuple(
        SmpDocType(str(u.get("documentTypeID", "")),
                   u.get("niceName") or short_doc_type(str(u.get("documentTypeID", ""))),
                   bool(u.get("isDeprecated")))
        for u in (payload.get("smpquery") or {}).get("urls") or [])
    return bool(existence.get("exists")), host, doc_types


class SmpClient:
    def __init__(self, url: str, timeout: float = 5.0, cache: LookupCache | None = None,
                 cache_seconds: float = 86400, transport: httpx.BaseTransport | None = None) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.cache = cache
        self.cache_seconds = cache_seconds
        self._transport = transport  # tests : httpx.MockTransport

    @classmethod
    def from_settings(cls) -> SmpClient | None:
        s = app_settings.get()
        if not s.peppol_enabled or not s.smp_url.strip():
            return None
        cache = LookupCache(app_settings.cache_dir() / "smp.sqlite")
        return cls(s.smp_url.strip(), s.peppol_timeout, cache, s.peppol_cache_hours * 3600)

    def lookup(self, scheme: str, value: str) -> SmpResult:
        participant = f"{scheme}:{value}"
        key = participant.lower()
        if self.cache is not None:
            cached = self.cache.get(key, self.cache_seconds)
            if cached is not None:
                return SmpResult(participant, LookupStatus.OK, *parse_smp(cached), from_cache=True)
        pid = quote(f"{SCHEME}::{participant}", safe="")
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport,
                              headers={"User-Agent": "fchecker", "Accept": "application/json"}) as client:
                payload = {"existence": self._get(client, f"{self.url}/ppidexistence/{SML}/{pid}")}
                if payload["existence"].get("exists"):
                    payload["smpquery"] = self._get(client, f"{self.url}/smpquery/{SML}/{pid}")
        except _HttpStatus as exc:
            return SmpResult(participant, LookupStatus.ERROR, error=f"HTTP {exc.code}")
        except (httpx.HTTPError, ValueError) as exc:
            log.info("SMP non déterminé pour %s : %s", participant, exc)
            return SmpResult(participant, LookupStatus.ERROR, error=type(exc).__name__)
        if self.cache is not None:
            self.cache.put(key, payload)
        return SmpResult(participant, LookupStatus.OK, *parse_smp(payload))

    @staticmethod
    def _get(client: httpx.Client, url: str) -> dict:
        r = client.get(url)
        if r.status_code != 200:
            raise _HttpStatus(r.status_code)
        return r.json()


class _HttpStatus(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code
