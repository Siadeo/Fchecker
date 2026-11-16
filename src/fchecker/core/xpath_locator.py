"""Convertit les ``location`` SVRL (XPath 2/3) en XPath 1.0 évaluable par lxml → n° de ligne."""
from __future__ import annotations

import re

from lxml import etree

# /*:Nom[namespace-uri()='urn:…'][1]
_STAR_NS = re.compile(r"\*:([\w.\-]+)\[namespace-uri\(\)='([^']*)'\]")
# /Q{urn:…}Nom[1]
_QNAME = re.compile(r"Q\{([^}]*)\}([\w.\-]+)")
# /prefixe:Nom (location « lisible » de certains moteurs) : on ignore le préfixe
_PREFIXED = re.compile(r"(?<=/)(?!\*)([\w.\-]+):([\w.\-]+)")


def to_xpath1(location: str) -> str:
    xp = _STAR_NS.sub(lambda m: f"*[local-name()='{m[1]}' and namespace-uri()='{m[2]}']", location)
    xp = _QNAME.sub(lambda m: f"*[local-name()='{m[2]}' and namespace-uri()='{m[1]}']", xp)
    xp = _PREFIXED.sub(lambda m: f"*[local-name()='{m[2]}']", xp)
    return xp


def locate(root: etree._Element, location: str | None) -> int | None:
    """Ligne de l'élément désigné (ou de son plus proche ancêtre résolu)."""
    if not location:
        return None
    steps = to_xpath1(location).split("/")
    # On retire les étapes finales non résolues (attribut, text(), étape inconnue).
    for end in range(len(steps), 1, -1):
        xp = "/".join(steps[:end])
        try:
            found = root.xpath(xp)
        except etree.XPathError:
            continue
        for node in found if isinstance(found, list) else ():
            if isinstance(node, etree._Element):
                return node.sourceline
            parent = getattr(node, "getparent", lambda: None)()
            if parent is not None:
                return parent.sourceline
    return None
