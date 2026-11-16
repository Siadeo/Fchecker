"""Auto-test sans interface : ``Fchecker.exe --self-test facture.pdf`` (ou ``main.py --self-test``).

Lance tous les outils exécutables sur une facture, sans réseau (annuaire Peppol coupé), puis imprime le
rapport en PDF avec QtWebEngine, sans fenêtre (plateforme Qt « offscreen »). Code de sortie : 0 si aucun
constat Bloquant ou Erreur et PDF produit, 1 sinon, 2 si l'auto-test plante.
``tools/build_release.py`` l'exécute sur l'exécutable gelé avec la facture de référence des tests : il
vérifie ainsi la découverte des plugins, les packs embarqués, le processus Saxon (spawn) et QtWebEngine
une fois packagé.
Un schematron qui ne s'exécute pas produit SCH-ERROR (Erreur), donc un code 1.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def _say(message: str) -> None:
    if sys.stderr is not None:  # exécutable fenêtré : pas de console
        print(message, file=sys.stderr)


def run(path: str) -> int:
    try:
        from fchecker.core import settings
        from fchecker.core.findings import Severity
        from fchecker.core.loader import load
        from fchecker.core.plugin import RunContext
        from fchecker.core.registry import Registry
        from fchecker.core.schematron import SchematronEngine

        # Réglages par défaut, en mémoire : ni lecture ni migration d'un settings.json (qui serait sinon
        # écrit à côté de l'exécutable et partirait dans le ZIP).
        settings.use_path(Path(tempfile.gettempdir()) / "fchecker-selftest-absent" / "settings.json")
        settings.get().peppol_enabled = False
        doc = load(path)
        registry = Registry()
        specs = [s for s in registry.discover() if s.runnable]
        reports, errors = {}, []
        try:
            for spec in specs:
                reports[spec.id] = report = registry.get_tool(spec.id).run(doc, RunContext())
                errors += [f"{spec.id}: {f.rule_id}" for f in report.findings if f.severity <= Severity.ERROR]
        finally:
            SchematronEngine.shutdown()
        pdf_ok = _print_pdf(doc, reports)
    except Exception as exc:  # noqa: BLE001 - l'auto-test doit toujours rendre un code
        _say(f"Auto-test : échec technique ({type(exc).__name__}: {exc})")
        return 2
    _say(f"Auto-test : {len(specs)} outils, {len(errors)} erreur(s), "
         f"PDF QtWebEngine {'produit' if pdf_ok else 'en échec'}" + "".join(f"\n  {e}" for e in errors))
    return 1 if errors or not pdf_ok else 0


def _print_pdf(doc, reports, timeout_ms: int = 60_000) -> bool:
    """Imprime le rapport HTML en PDF avec QtWebEngine, sans fenêtre ; vrai si un PDF est produit."""
    from fchecker.core.export import render_html

    if QApplication_instance() is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication, QEventLoop, Qt, QTimer, QUrl
    from PySide6.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication([sys.argv[0]])
    from PySide6.QtWebEngineCore import QWebEnginePage

    with tempfile.TemporaryDirectory(prefix="fchecker-selftest-") as tmp:
        target = Path(tmp) / "rapport.pdf"
        page = QWebEnginePage()
        loop = QEventLoop()
        result = {"ok": False}

        def printed(_path: str, ok: bool) -> None:
            result["ok"] = ok
            loop.quit()

        page.loadFinished.connect(lambda ok: page.printToPdf(str(target)) if ok else loop.quit())
        page.pdfPrintingFinished.connect(printed)
        QTimer.singleShot(timeout_ms, loop.quit)
        page.setHtml(render_html(doc, reports), QUrl("about:blank"))
        loop.exec()
        ok = result["ok"] and target.is_file() and target.read_bytes()[:5] == b"%PDF-"
        page.deleteLater()
        app.processEvents()
        return ok


def QApplication_instance():  # noqa: N802 - sans importer Qt si inutile
    if "PySide6.QtWidgets" not in sys.modules:
        return None
    return sys.modules["PySide6.QtWidgets"].QApplication.instance()
