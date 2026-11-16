import json

from fchecker.core.export import render_html, render_json
from fchecker.core.findings import Severity
from fchecker.core.loader import load
from fchecker.core.plugin import RunContext
from fchecker.core.registry import Registry


def reports_for(doc):
    reg = Registry()
    reg.discover()
    return {s.id: reg.get_tool(s.id).run(doc, RunContext()) for s in reg.specs if s.runnable}


def test_html_and_json(facturx_path):
    doc = load(facturx_path)
    reports = reports_for(doc)
    html = render_html(doc, reports)
    assert "F202500003" in html and "Conforme avec avertissements" in html
    assert "Mentions obligatoires" in html and "Cohérence PDF" in html
    data = json.loads(render_json(doc, reports))
    assert data["document"]["format"] == "Factur-X" and len(data["document"]["sha256"]) == 64
    assert data["counts"]["ERROR"] == 0 and data["counts"]["WARNING"] >= 1
    assert "ID-BIC" in {f["rule_id"] for f in data["findings"]}  # BIC fictif de l'exemple officiel
    # l'export JSON ne doit pas altérer les rapports (réexport HTML possible)
    assert isinstance(next(iter(reports["validator"].meta["checks"][0]["counts"])), Severity)
    assert "F202500003" in render_html(doc, reports)
