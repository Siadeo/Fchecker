"""Export du rapport de contrôle : HTML, JSON (noyau) ou PDF (impression HTML via QtWebEngine)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QUrl
from PySide6.QtGui import QPageLayout, QPageSize
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from fchecker.core import export
from fchecker.core.document import InvoiceDocument
from fchecker.core.report import Report

FILTERS = {"Rapport PDF (*.pdf)": "pdf", "Rapport HTML (*.html)": "html", "Données JSON (*.json)": "json"}

_pending: list = []  # garde en vie les pages d'impression jusqu'à la fin de l'export


def export_report(parent: QWidget, doc: InvoiceDocument, reports: dict[str, Report]) -> None:
    default = str(Path(doc.path).with_name(f"{Path(doc.path).stem}_rapport.pdf"))
    path, chosen = QFileDialog.getSaveFileName(parent, "Exporter le rapport", default, ";;".join(FILTERS))
    if not path:
        return
    kind = FILTERS.get(chosen) or Path(path).suffix.lstrip(".").lower() or "pdf"
    target = Path(path)
    if target.suffix.lower() != f".{kind}":
        target = target.with_suffix(f".{kind}")
    try:
        if kind == "json":
            target.write_text(export.render_json(doc, reports), encoding="utf-8")
        elif kind == "html":
            target.write_text(export.render_html(doc, reports), encoding="utf-8")
        else:
            _print_pdf(parent, export.render_html(doc, reports), target)
            return
    except OSError as exc:
        QMessageBox.warning(parent, "Exporter le rapport", f"Écriture impossible : {exc}")
        return
    _done(parent, target)


def _print_pdf(parent: QWidget, html: str, target: Path) -> None:
    from PySide6.QtWebEngineCore import QWebEnginePage

    page = QWebEnginePage(parent)
    _pending.append(page)

    def loaded(ok: bool) -> None:
        if not ok:
            _finish(False)
            return
        layout = QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                             QMarginsF(0, 0, 0, 0))
        page.printToPdf(str(target), layout)

    def _finish(ok: bool, *_) -> None:
        if page in _pending:
            _pending.remove(page)
        page.deleteLater()
        if ok:
            _done(parent, target)
        else:
            QMessageBox.warning(parent, "Exporter le rapport", "La génération du PDF a échoué.")

    page.loadFinished.connect(loaded)
    page.pdfPrintingFinished.connect(lambda _path, ok: _finish(ok))
    page.setHtml(html, QUrl("about:blank"))


def _done(parent: QWidget, target: Path) -> None:
    window = parent.window()
    if hasattr(window, "statusBar"):
        window.statusBar().showMessage(f"Rapport exporté : {target}", 8000)
