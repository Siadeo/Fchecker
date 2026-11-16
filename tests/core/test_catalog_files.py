"""Les fichiers de catalogue et de règles doivent rester du YAML valide (erreur de saisie fréquente)."""
from pathlib import Path

import pytest
import yaml

SRC = Path(__file__).parents[2] / "src" / "fchecker"


@pytest.mark.parametrize("path", sorted(SRC.rglob("*.yaml")), ids=lambda p: p.name)
def test_yaml_is_valid(path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and data
