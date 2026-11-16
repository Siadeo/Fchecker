import pytest

from fchecker.core.findings import Source
from fchecker.core.loader import load
from fchecker.core.referentiels import FNFE_VERSION
from fchecker.core.profiles import Profile, chain_for, detect_profile, pack


@pytest.mark.parametrize("urn, profile", [
    ("urn:cen.eu:en16931:2017", Profile.EN16931),
    ("urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0", Profile.EN16931),
    ("urn:factur-x.eu:1p0:minimum", Profile.MINIMUM),
    ("urn:factur-x.eu:1p0:basicwl", Profile.BASIC_WL),
    ("urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic", Profile.BASIC),
    ("urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended", Profile.EXTENDED),
    ("urn:cen.eu:en16931:2017#conformant#urn.cpro.gouv.fr:1p0:extended-ctc-fr", Profile.EXTENDED_CTC_FR),
    ("urn:autre:chose", Profile.UNKNOWN),
    (None, Profile.UNKNOWN),
])
def test_detect_profile(urn, profile):
    assert detect_profile(urn) is profile


def test_pack_installed():
    p = pack()
    assert p is not None and p.version == FNFE_VERSION


def test_chain_facturx_en16931(facturx_path):
    chain = chain_for(load(facturx_path))
    assert chain.profile is Profile.EN16931
    assert chain.xsd.endswith("Factur-X_EN16931.xsd")
    # schematron de profil Factur-X (inclut EN 16931) + règles FR, sans doublon EN16931-CII
    assert [s.id for s in chain.schematrons] == ["facturx-en16931", "br-fr-cii"]
    assert all(pack().has(s.rel_path) for s in chain.schematrons)
    assert pack().has(chain.xsd)


def test_chain_ubl():
    from pathlib import Path

    ubl = next((Path(__file__).parents[1] / "fixtures" / "en16931" / "ubl").glob("ubl-tc434-example1.xml"))
    chain = chain_for(load(ubl))
    assert chain.xsd.endswith("UBL-Invoice-2.1.xsd")
    assert [s.source for s in chain.schematrons] == [Source.SCHEMATRON_EN, Source.SCHEMATRON_FR]


def test_chain_cii_minimum_has_note(sample_xml, cii_file):
    xml = sample_xml.replace("urn:cen.eu:en16931:2017", "urn:factur-x.eu:1p0:minimum")
    doc = load(cii_file(xml))
    chain = chain_for(doc)
    assert chain.profile is Profile.MINIMUM
    assert chain.xsd.endswith("CrossIndustryInvoice_100pD22B.xsd")
