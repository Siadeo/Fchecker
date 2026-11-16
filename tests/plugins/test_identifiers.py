from fchecker.core import ids
from fchecker.core.findings import Severity
from fchecker.core.loader import load
from fchecker.core.plugin import RunContext
from fchecker.plugins.validator.checks.identifiers import CHECK

BAD_SIRET = "10000000900010"


def findings(doc):
    return list(CHECK.run(doc, RunContext()))


def test_sample_identifiers_valid(facturx_path):
    # Seul le BIC fictif de l'exemple officiel (« BIC_MONCOMPTE ») est signalé, en avertissement.
    found = findings(load(facturx_path))
    assert [(f.rule_id, f.severity) for f in found] == [("ID-BIC", Severity.WARNING)]


def test_invalid_identifiers(sample_xml, cii_file):
    assert not ids.luhn_valid(BAD_SIRET)
    xml = (sample_xml
           .replace(">200000008<", ">200000007<", 1)            # SIREN acheteur (BT-47) : Luhn faux
           .replace("FR37200000008", "FR12200000008")           # clé TVA acheteur fausse
           .replace("FR88100000009", "FR83300000007")           # TVA valide d'une autre société
           .replace("FR20 1254 2547 2569 8542 5874 698", "FR20 1254 2547 2569 8542 5874 699")  # IBAN altéré
           .replace('<ram:GlobalID schemeID="0088">587451236587</ram:GlobalID>',
                    f'<ram:GlobalID schemeID="0009">{BAD_SIRET}</ram:GlobalID>'))  # SIRET vendeur : Luhn faux
    rules = {f.rule_id: f for f in findings(load(cii_file(xml)))}
    assert {"ID-SIREN", "ID-TVA-CLE", "ID-SIRET", "ID-TVA-SIREN", "ID-IBAN"} <= set(rules)
    assert rules["ID-TVA-CLE"].suggestion == "Numéro attendu pour ce SIREN : FR37200000008"
    assert rules["ID-TVA-SIREN"].suggestion == "TVA attendue : FR88100000009"
    assert rules["ID-SIREN"].line is not None
