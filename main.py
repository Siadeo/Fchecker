"""Point d'entrée : python main.py"""
import multiprocessing
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fchecker.app import main  # noqa: E402

if __name__ == "__main__":
    multiprocessing.freeze_support()  # processus Saxon dans un exécutable figé (PyInstaller)
    raise SystemExit(main())
