"""Auto-test sans interface (``--self-test``), exécuté par tools/build_release.py sur l'exécutable gelé."""
from fchecker.app import main


def test_self_test_reference_invoice(facturx_path):
    assert main(["fchecker", "--self-test", str(facturx_path)]) == 0


def test_self_test_missing_file(tmp_path):
    assert main(["fchecker", "--self-test", str(tmp_path / "absente.pdf")]) != 0
