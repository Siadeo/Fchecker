from fchecker.core.loader import load
from fchecker.core.xpath_locator import locate, to_xpath1

RSM = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"


def test_star_namespace_location(facturx_path):
    root = load(facturx_path).root
    loc = (f"/*:CrossIndustryInvoice[namespace-uri()='{RSM}'][1]"
           f"/*:ExchangedDocument[namespace-uri()='{RSM}'][1]"
           f"/*:ID[namespace-uri()='{RAM}'][1]")
    assert locate(root, loc) == root.xpath("//*[local-name()='ExchangedDocument']/*[local-name()='ID']")[0].sourceline


def test_qname_location_and_attribute_fallback(facturx_path):
    root = load(facturx_path).root
    loc = f"/Q{{{RSM}}}CrossIndustryInvoice[1]/Q{{{RSM}}}ExchangedDocument[1]/@languageID"
    line = locate(root, loc)  # l'attribut n'existe pas : on remonte à l'élément parent
    assert line == root.xpath("//*[local-name()='ExchangedDocument']")[0].sourceline


def test_unresolvable():
    assert locate(None, None) is None
    assert "local-name()='A'" in to_xpath1("/*:A[namespace-uri()='x'][1]")
