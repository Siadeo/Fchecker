import json
from pathlib import Path

import httpx
import pytest

from fchecker.core import settings
from fchecker.core.document import DocFormat
from fchecker.core.findings import Severity
from fchecker.core.loader import load
from fchecker.core.plugin import RunContext
from fchecker.core.services.peppol import LookupCache, LookupStatus, PeppolClient, SmpClient, accepts, short_doc_type
from fchecker.plugins.validator.checks.peppol_check import PeppolCheck

UBL = Path(__file__).parents[1] / "fixtures" / "france_rfe" / "UBL" / "EN16931"

CII = ("urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100::CrossIndustryInvoice##urn:cen.eu:en16931:2017"
       "#compliant#urn:peppol:france:billing:cius:1.0::D22B")
FACTURX = "urn:peppol:doctype:pdf+xml##urn:cen.eu:en16931:2017#conformant#urn:peppol:france:billing:Factur-X:1.0::D22B"
UBL_INVOICE = ("urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017"
               "#compliant#urn:peppol:france:billing:cius:1.0::2.1")
STATUS = ("urn:un:unece:uncefact:data:standard:CrossDomainAcknowledgementAndResponse:100::"
          "CrossDomainAcknowledgementAndResponse##urn:peppol:france:billing:cdv:1.0::D22B")

# Réponse au format de directory.peppol.eu, données fictives (adresse de statuts uniquement)
STATUS_ONLY = {"version": "1.0", "total-result-count": 1, "matches": [
    {"participantID": {"scheme": "iso6523-actorid-upis", "value": "0225:300000007_client"},
     "docTypes": [{"scheme": "busdox-docid-qns", "value": STATUS}],
     "entities": [{"name": [{"name": "Le client"}], "countryCode": "FR"}]}]}

# Facture de référence (UC1) : acheteur BT-49 = 0225:200000008
BUYER = "0225:200000008"


def match(identifier, *doc_types):
    return {"matches": [{"participantID": {"scheme": "iso6523-actorid-upis", "value": identifier},
                         "docTypes": [{"value": d} for d in doc_types],
                         "entities": [{"name": [{"name": "LE CLIENT"}], "countryCode": "FR"}]}]}


def make_client(responses: dict, calls: list | None = None, cache=None):
    def handler(request: httpx.Request) -> httpx.Response:
        participant = request.url.params["participant"]
        if calls is not None:
            calls.append(participant)
        return httpx.Response(200, json=responses.get(participant.split("::", 1)[1], {"matches": []}))
    return PeppolClient("https://peppol.test/search", cache=cache, transport=httpx.MockTransport(handler))


def run(doc, responses, **kw):
    check = PeppolCheck(client_factory=lambda: make_client(responses, **kw))
    return {f.rule_id: f for f in check.run(check.prepare(doc), RunContext())}


def test_client_parses_real_response():
    result = make_client({"0225:300000007_client": STATUS_ONLY}).lookup("0225", "300000007_client")
    assert result.status is LookupStatus.OK
    assert result.matches[0].identifier == "0225:300000007_client"
    assert result.matches[0].names == ("Le client",)
    assert not accepts(result.doc_types, DocFormat.FACTURX)


def test_participant_parameter(facturx_path):
    calls: list = []
    run(load(facturx_path), {}, calls=calls)
    assert calls == [f"iso6523-actorid-upis::{BUYER}"]


def test_registered_for_facturx(facturx_path):
    rules = run(load(facturx_path), {BUYER: match(BUYER, FACTURX, STATUS)})
    assert set(rules) == {"PEP-OK"} and rules["PEP-OK"].bt == "BT-49"


def test_absent_is_warning(facturx_path):
    rules = run(load(facturx_path), {})
    assert set(rules) == {"PEP-01"} and rules["PEP-01"].severity is Severity.WARNING


def test_status_only_address_is_warning(facturx_path):
    rules = run(load(facturx_path), {BUYER: match(BUYER, STATUS)})
    assert rules["PEP-02"].severity is Severity.WARNING
    assert "CrossDomainAcknowledgementAndResponse" in rules["PEP-02"].suggestion


def test_ubl_needs_ubl_doc_type():
    doc = load(UBL / "UC1_F202500003_00-INV_20250701_EN16931_UBL_Commentee.xml")
    assert set(run(doc, {BUYER: match(BUYER, CII)})) == {"PEP-02"}
    assert set(run(doc, {BUYER: match(BUYER, UBL_INVOICE)})) == {"PEP-OK"}


def test_self_billing_checks_seller():
    calls: list = []
    rules = run(load(UBL / "UC13_AUTOF202600028_EN16931_UBL_Commentee.xml"), {}, calls=calls)
    assert calls == ["iso6523-actorid-upis::0225:100000009_AUTOFACT"]
    assert rules["PEP-01"].bt == "BT-34"


def test_missing_address_not_queried(sample_xml, cii_file):
    xml = sample_xml.replace('<ram:URIID schemeID="0225">200000008</ram:URIID>', "", 1)
    assert xml != sample_xml
    calls: list = []
    rules = run(load(cii_file(xml)), {}, calls=calls)
    assert calls == [] and set(rules) == {"PEP-00"}


@pytest.mark.parametrize("factory", [
    lambda: None,
    lambda: PeppolClient("https://peppol.test/search", transport=httpx.MockTransport(
        lambda r: (_ for _ in ()).throw(httpx.ConnectError("réseau coupé")))),
    lambda: PeppolClient("https://peppol.test/search", transport=httpx.MockTransport(lambda r: httpx.Response(429))),
])
def test_disabled_or_unreachable_is_info(facturx_path, factory):
    check = PeppolCheck(client_factory=factory)
    rules = {f.rule_id: f for f in check.run(check.prepare(load(facturx_path)), RunContext())}
    assert set(rules) == {"PEP-06"} and rules["PEP-06"].severity is Severity.INFO


def test_http_400_is_a_rejected_address(facturx_path, tmp_path):
    """L'annuaire répond : ce n'est pas une panne, c'est l'adresse qui est refusée."""
    cache = LookupCache(tmp_path / "p.sqlite")
    calls = []
    client = PeppolClient("https://peppol.test/search", cache=cache,
                          transport=httpx.MockTransport(lambda r: httpx.Response(400)))
    check = PeppolCheck(client_factory=lambda: client, smp_factory=lambda: make_smp(calls=calls))
    rules = {f.rule_id: f for f in check.run(check.prepare(load(facturx_path)), RunContext())}
    assert set(rules) == {"PEP-03"}
    f = rules["PEP-03"]
    assert f.severity is Severity.WARNING and f.bt == "BT-49" and "HTTP 400" in f.message
    assert calls == []                                    # pas de requête SMP pour une adresse refusée
    assert cache.get("0225:200000008", 3600) is None      # réponse non mise en cache


def test_http_500_stays_unreachable(facturx_path):
    client = PeppolClient("https://peppol.test/search", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    check = PeppolCheck(client_factory=lambda: client)
    rules = {f.rule_id: f for f in check.run(check.prepare(load(facturx_path)), RunContext())}
    assert set(rules) == {"PEP-06"} and rules["PEP-06"].severity is Severity.INFO


def test_cache_is_case_insensitive(tmp_path):
    calls: list = []
    client = make_client({}, calls, LookupCache(tmp_path / "p.sqlite"))
    assert not client.lookup("0225", "200000008_CLIENT").from_cache
    assert client.lookup("0225", "200000008_client").from_cache
    assert len(calls) == 1


def test_short_doc_type():
    assert short_doc_type(UBL_INVOICE) == "Invoice (urn:peppol:france:billing:cius:1.0)"
    assert short_doc_type(STATUS).startswith("CrossDomainAcknowledgementAndResponse")


def test_settings_v2_timeout_and_cache_kept(tmp_path):
    """Réglages ≤ v2 : délai et cache de l'ancien annuaire, communs avec Peppol, sont repris."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"version": 2, "directory_enabled": True, "directory_url": "https://x.test",
                                "directory_timeout": 9.0, "directory_cache_hours": 12.0}), encoding="utf-8")
    previous = settings.config_path()
    settings.use_path(path)
    try:
        s = settings.get()
        assert (s.peppol_timeout, s.peppol_cache_hours, s.version) == (9.0, 12.0, settings.VERSION)
    finally:
        settings.use_path(previous)


# --- SMP (peppol.helger.com) ---------------------------------------------------------------------
SMP_PID = f"iso6523-actorid-upis::{BUYER}"
SMP_URLS = [
    {"documentTypeID": f"busdox-docid-qns::{UBL_INVOICE}", "niceName": "Peppol BIS Billing UBL Invoice V3",
     "state": "act", "isDeprecated": False},
    {"documentTypeID": f"busdox-docid-qns::{CII}", "niceName": None, "isDeprecated": True},
]


def make_smp(exists=True, urls=SMP_URLS, calls: list | None = None, cache=None, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.raw_path.decode()
        if calls is not None:
            calls.append(path)
        if status != 200:
            return httpx.Response(status)
        if "/ppidexistence/peppolprod/" in path:
            return httpx.Response(200, json={"participantID": SMP_PID, "sml": "peppolprod", "exists": exists,
                                             "smpHostURI": "http://smp.exemple.fr/" if exists else None})
        return httpx.Response(200, json={"smptype": "peppol", "participantID": SMP_PID, "urls": urls})
    return SmpClient("https://smp.test/api", cache=cache, transport=httpx.MockTransport(handler))


def run_smp(doc, responses, smp):
    check = PeppolCheck(client_factory=lambda: make_client(responses), smp_factory=lambda: smp)
    return {f.rule_id: f for f in check.run(check.prepare(doc), RunContext())}


def test_smp_client_parses_responses():
    calls: list = []
    result = make_smp(calls=calls).lookup("0225", "200000008")
    assert result.status is LookupStatus.OK and result.exists and result.host == "smp.exemple.fr"
    assert [d.name for d in result.doc_types] == ["Peppol BIS Billing UBL Invoice V3",
                                                  short_doc_type(f"busdox-docid-qns::{CII}")]
    assert [d.deprecated for d in result.doc_types] == [False, True]
    pid = "iso6523-actorid-upis%3A%3A0225%3A200000008"
    assert calls == [f"/api/ppidexistence/peppolprod/{pid}", f"/api/smpquery/peppolprod/{pid}"]


def test_smp_not_registered_skips_smpquery(tmp_path):
    calls: list = []
    client = make_smp(exists=False, calls=calls, cache=LookupCache(tmp_path / "smp.sqlite"))
    result = client.lookup("0225", "200000008")
    assert not result.exists and result.doc_types == () and len(calls) == 1
    assert client.lookup("0225", "200000008").from_cache and len(calls) == 1


def test_smp_details_on_registered_address(facturx_path):
    rules = run_smp(load(facturx_path), {BUYER: match(BUYER, FACTURX)}, make_smp())
    f = rules["PEP-OK"]
    assert f.details.startswith("SMP : smp.exemple.fr. 2 types de documents acceptés")
    assert "(voir ci-dessous)" in f.details
    assert f.listing_title == "Types de documents acceptés par le SMP"
    assert f.listing[0] == "Peppol BIS Billing UBL Invoice V3" and f.listing[1].endswith("(obsolète)")


def test_smp_details_on_address_absent_from_directory(facturx_path):
    rules = run_smp(load(facturx_path), {}, make_smp())
    assert set(rules) == {"PEP-01"} and rules["PEP-01"].details.startswith("SMP : smp.exemple.fr.")


def test_smp_not_registered_or_error(facturx_path):
    rules = run_smp(load(facturx_path), {}, make_smp(exists=False))
    assert rules["PEP-01"].details == "Aucun SMP enregistré pour cette adresse sur le réseau Peppol."
    assert rules["PEP-01"].listing == ()
    rules = run_smp(load(facturx_path), {}, make_smp(status=500))
    assert set(rules) == {"PEP-01"} and rules["PEP-01"].details == "SMP non déterminé (HTTP 500)."
    assert rules["PEP-01"].severity is Severity.WARNING


def test_smp_disabled_adds_nothing(facturx_path):
    rules = run_smp(load(facturx_path), {BUYER: match(BUYER, FACTURX)}, None)
    assert rules["PEP-OK"].details is None and rules["PEP-OK"].listing == ()
