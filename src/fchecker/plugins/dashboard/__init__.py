from fchecker.core.plugin import ToolSpec

SPEC = ToolSpec(
    id="dashboard",
    name="Tableau de bord",
    label="DASHBOARD",
    icon="dashboard",
    order=0,
    factory="fchecker.plugins.dashboard.tool:DashboardTool",
    description="Synthèse du document et état de chaque contrôle.",
    runnable=False,
)
