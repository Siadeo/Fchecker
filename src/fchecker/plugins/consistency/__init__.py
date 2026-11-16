from fchecker.core.plugin import ToolSpec

SPEC = ToolSpec(
    id="consistency",
    name="Cohérence PDF ↔ XML",
    label="PDF <-> XML",
    icon="consistency",
    order=50,
    factory="fchecker.plugins.consistency.tool:ConsistencyTool",
    description="Compare le PDF visuel et le XML : n° de facture, dates, totaux HT/TVA/TTC, SIREN.",
)
