from fchecker.core.plugin import ToolSpec

SPEC = ToolSpec(
    id="viewer",
    name="Visionneuse",
    label="VISIONNEUSE",
    icon="viewer",
    order=40,
    factory="fchecker.plugins.viewer.tool:ViewerTool",
    description="Rendu lisible d'un XML CII ou UBL (HTML, export PDF).",
    runnable=False,
)
