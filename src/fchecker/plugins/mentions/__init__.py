from fchecker.core.plugin import ToolSpec

SPEC = ToolSpec(
    id="mentions",
    name="Mentions obligatoires",
    label="MENTIONS",
    icon="mentions",
    order=30,
    factory="fchecker.plugins.mentions.tool:MentionsTool",
    description="Mentions obligatoires de la réforme non couvertes par les schematrons.",
)
