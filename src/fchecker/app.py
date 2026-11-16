"""Démarrage de l'application."""
from __future__ import annotations

import logging
import sys
import time

_T0 = time.perf_counter()
log = logging.getLogger("fchecker")


def create_window(argv: list[str] | None = None):
    """Construit QApplication (si besoin) + fenêtre principale. Utilisé aussi par les tests."""
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication

    from fchecker.core.registry import Registry
    from fchecker.ui import theme
    from fchecker.ui.main_window import MainWindow

    from PySide6.QtCore import Qt

    QCoreApplication.setOrganizationName("Fchecker")
    QCoreApplication.setApplicationName("Fchecker")
    # Requis AVANT la création de QApplication pour charger QtWebEngine plus tard (visionneuse).
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setStyle("Fusion")

    from PySide6.QtCore import QSettings

    _migrate_qsettings(QSettings())
    mode =theme.ThemeMode(QSettings().value("ui/theme", theme.ThemeMode.SYSTEM.value))
    theme.apply(app, mode)

    registry = Registry()
    registry.discover()
    window = MainWindow(registry)
    return app, window


def _migrate_qsettings(current) -> None:
    """Reprend les préférences d'interface de Factotum (ancien nom) si Fchecker n'en a pas encore."""
    from PySide6.QtCore import QSettings

    if current.allKeys():
        return
    legacy = QSettings("Factotum", "Factotum")
    keys = legacy.allKeys()
    for key in keys:
        current.setValue(key, legacy.value(key))
    if keys:
        current.sync()
        log.info("Préférences d'interface reprises de Factotum (%d clés)", len(keys))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    argv = sys.argv if argv is None else argv
    if len(argv) == 3 and argv[1] == "--self-test":  # sans interface, utilisé par tools/build_release.py
        from fchecker.selftest import run

        return run(argv[2])
    app, window = create_window(argv)

    from fchecker.ui.license_dialog import demander_licence

    if not demander_licence():
        return 0
    window.show()
    for path in argv[1:]:
        window.open_path(path)
    log.info("Fenêtre affichée en %.0f ms", (time.perf_counter() - _T0) * 1000)

    from PySide6.QtCore import QTimer

    QTimer.singleShot(0, _warm_up)
    try:
        return app.exec()
    finally:
        from fchecker.core.schematron import SchematronEngine
        from fchecker.ui import workers

        workers.shutdown()
        SchematronEngine.shutdown()


def _warm_up() -> None:
    """Précompile les schematrons les plus courants en tâche de fond (la 1re validation est alors immédiate)."""
    from fchecker.core.profiles import warm_up_paths
    from fchecker.core.schematron import SchematronEngine

    t0 = time.perf_counter()
    future = SchematronEngine.instance().warm_up(warm_up_paths())
    future.add_done_callback(
        lambda f: log.info("Schematrons précompilés (%s) en %.1f s", f.result() if not f.exception() else f.exception(),
                           time.perf_counter() - t0)
    )
