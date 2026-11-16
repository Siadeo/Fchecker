import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


# Facture de référence : exemple officiel FNFE (cas UC1), Factur-X EN 16931, entièrement
# conforme (seul son BIC fictif « BIC_MONCOMPTE » donne un avertissement). Données fictives.
SAMPLE = FIXTURES / "france_rfe" / "FX" / "EN16931" / "UC1_F202500003_00-INV_20250701_EN16931_FX.pdf"


@pytest.fixture
def facturx_path() -> Path:
    return SAMPLE


@pytest.fixture
def sample_xml(facturx_path) -> str:
    from fchecker.core.loader import load

    return load(facturx_path).xml_bytes.decode("utf-8")


@pytest.fixture
def cii_file(tmp_path):
    """Fabrique : écrit un XML CII (éventuellement modifié) et renvoie son chemin."""
    def make(xml: str, name: str = "facture.xml") -> Path:
        p = tmp_path / name
        p.write_text(xml, encoding="utf-8")
        return p
    return make


def corrupt(xml: str, **changes: bool) -> str:
    """Variantes corrompues de la facture d'exemple, utilisées par plusieurs tests."""
    if changes.get("total"):
        xml = re.sub(r"<ram:GrandTotalAmount>[\d.]+<", "<ram:GrandTotalAmount>9999.99<", xml, count=1)
    if changes.get("pmt"):
        xml = xml.replace("<ram:SubjectCode>PMT</ram:SubjectCode>", "<ram:SubjectCode>AAI</ram:SubjectCode>")
    if changes.get("structure"):
        xml = xml.replace("<ram:TypeCode>380</ram:TypeCode>", "<ram:TypeCode>380</ram:TypeCode><ram:Bidon/>", 1)
    return xml


@pytest.fixture(autouse=True, scope="session")
def _isolated_settings(tmp_path_factory):
    """Réglages du noyau isolés ; annuaires désactivés par défaut (pas de réseau dans les tests)."""
    from fchecker.core import settings

    path = tmp_path_factory.mktemp("settings") / "settings.json"
    settings.use_path(path)
    settings.save(settings.Settings(peppol_enabled=False))
    yield
    settings.use_path(None)


@pytest.fixture(autouse=True, scope="session")
def _isolated_qsettings(tmp_path_factory):
    """Les tests ne doivent jamais écrire dans les réglages réels de l'utilisateur."""
    from PySide6.QtCore import QSettings

    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      str(tmp_path_factory.mktemp("qsettings")))
