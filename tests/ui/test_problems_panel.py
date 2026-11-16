from fchecker.core.findings import Finding, Severity, Source
from fchecker.ui.problems_panel import finding_html


def test_details_under_title_and_listing_at_bottom():
    f = Finding("PEP-OK", Severity.INFO, Source.PEPPOL, "Adresse inscrite", title="Adresse inscrite dans annuaire Peppol",
                details="SMP : smp.exemple.fr. 2 types de documents acceptés : voir tous les types de documents ci-dessous.",
                listing_title="Types de documents acceptés par le SMP", listing=("Invoice <UBL>", "CII"))
    html = finding_html(f)
    title, details = html.index("Adresse inscrite dans annuaire Peppol"), html.index("SMP : smp.exemple.fr")
    table, listing = html.index("<table"), html.index("Types de documents acceptés par le SMP")
    assert title < details < table < listing
    assert "<li>Invoice &lt;UBL&gt;</li><li>CII</li>" in html


def test_no_listing_without_items():
    html = finding_html(Finding("PEP-01", Severity.WARNING, Source.PEPPOL, "Absente"))
    assert "<ul>" not in html
