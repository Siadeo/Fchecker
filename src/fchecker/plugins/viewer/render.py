"""Rendu HTML lisible d'une facture (CII ou UBL) à partir du modèle normalisé. Sans Qt."""
from __future__ import annotations

from functools import cache

from jinja2 import Environment, PackageLoader, select_autoescape
from markupsafe import Markup

from fchecker.core import labels
from fchecker.core.document import InvoiceDocument, profile_label
from fchecker.core.invoice import invoice_of


@cache
def _env() -> Environment:
    env = Environment(loader=PackageLoader("fchecker.plugins.viewer", "templates"),
                      autoescape=select_autoescape(["html", "j2"]), trim_blocks=True, lstrip_blocks=True)
    env.filters.update(money=labels.money, number=labels.number, day=labels.day)
    env.globals.update(label=labels.label, L=labels, src=src)
    return env


def src(x) -> Markup | str:
    """Attribut ``data-line`` : ligne XML d'origine d'une valeur (``int``, ou objet doté de ``.line``)."""
    line = x if isinstance(x, int) else getattr(x, "line", None)
    return Markup(f' data-line="{line}"') if isinstance(line, int) and line > 0 else ""


def render_invoice(doc: InvoiceDocument, interactive: bool = False) -> str:
    """``interactive`` : ajoute le script de la visionneuse (clic → ligne XML). Jamais dans l'export."""
    inv = invoice_of(doc)
    return _env().get_template("invoice.html.j2").render(
        inv=inv, doc=doc, currency=inv.currency or "", interactive=interactive,
        profile=profile_label(doc.profile) if doc.profile else "",
    )
