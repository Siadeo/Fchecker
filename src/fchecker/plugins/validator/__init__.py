from fchecker.core.plugin import ToolSpec

SPEC = ToolSpec(
    id="validator",
    name="Validateur",
    label="VALIDATEUR",
    icon="validator",
    order=10,
    factory="fchecker.plugins.validator.tool:ValidatorTool",
    description="Profil, XSD, schematrons EN 16931 / Factur-X, règles FR, PDF/A-3, identifiants "
                "(SIREN/SIRET, TVA, IBAN) et annuaire Peppol. Chaque erreur est expliquée en français.",
)
