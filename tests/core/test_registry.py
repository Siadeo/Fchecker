import sys

from fchecker.core.registry import Registry

EXPECTED = ["dashboard", "validator", "mentions", "viewer", "consistency"]


def test_discover_order():
    reg = Registry()
    assert [s.id for s in reg.discover()] == EXPECTED


def test_tools_are_lazy():
    reg = Registry()
    reg.discover()
    assert not any(reg.is_loaded(t) for t in EXPECTED)
    # discover() ne doit pas avoir importé l'implémentation d'un outil
    for mod in list(sys.modules):
        if mod.startswith("fchecker.plugins.") and mod.endswith(".tool"):
            del sys.modules[mod]
    reg.discover()
    assert "fchecker.plugins.validator.tool" not in sys.modules
    tool = reg.get_tool("validator")
    assert "fchecker.plugins.validator.tool" in sys.modules
    assert reg.get_tool("validator") is tool


def test_runnable_tools_accept_sample(facturx_path):
    from fchecker.core.findings import Severity
    from fchecker.core.loader import load
    from fchecker.core.plugin import RunContext

    reg = Registry()
    reg.discover()
    doc = load(facturx_path)
    for spec in reg.specs:
        if spec.runnable:
            report = reg.get_tool(spec.id).run(doc, RunContext())
            assert report.tool_id == spec.id
            assert not [f for f in report.findings if f.severity <= Severity.ERROR], spec.id
