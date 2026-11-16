"""Saxon dans un processus séparé : l'interface ne gèle plus, et un plantage de Saxon est récupéré."""
import threading
import time

import pytest

from fchecker.core.loader import load
from fchecker.core.profiles import chain_for, pack, warm_up_paths
from fchecker.core.schematron import SchematronEngine


@pytest.fixture
def engine():
    eng = SchematronEngine()  # instance dédiée : n'interfère pas avec le singleton des autres tests
    yield eng
    with eng._lock:
        eng._stop()


def test_compilation_does_not_hold_the_gil(engine):
    """Régression : saxonche en processus principal gelait le thread UI ~1,6 s (GIL).
    Pendant la pré-compilation, un thread Python doit continuer à tourner sans retard notable."""
    future = engine.warm_up(warm_up_paths())
    gaps, last = [], time.perf_counter()
    while not future.done():
        time.sleep(0.01)
        now = time.perf_counter()
        gaps.append(now - last)
        last = now
    assert future.result() == 5
    assert max(gaps) < 0.25, f"gel de {max(gaps):.2f} s"


def test_validation_and_recovery_after_crash(engine, facturx_path):
    doc = load(facturx_path)
    xslt = pack().path(chain_for(doc).schematrons[0].rel_path)
    assert engine.validate(xslt, doc.xml_text) == []
    assert engine.is_compiled(xslt)

    engine._process.kill()  # simulation d'un plantage natif de Saxon
    engine._process.join(5)
    with pytest.raises(RuntimeError):
        # 1re requête après le plantage : relance transparente du processus…
        engine.validate(xslt, "<pas-du-xml")  # …et l'erreur du document est bien remontée
    assert engine.validate(xslt, doc.xml_text) == []


def test_concurrent_requests_are_serialized(engine, facturx_path):
    doc = load(facturx_path)
    xslt = pack().path(chain_for(doc).schematrons[0].rel_path)
    results, errors = [], []

    def run():
        try:
            results.append(engine.validate(xslt, doc.xml_text))
        except Exception as exc:  # pragma: no cover - diagnostic
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not errors and results == [[]] * 4
