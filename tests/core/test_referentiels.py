"""Référentiels : cohérence avec les fichiers embarqués et états du contrôle de fraîcheur (sans réseau)."""
import subprocess
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from fchecker.core import referentiels as R

TOOLS = Path(__file__).parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import fetch_rules  # noqa: E402

PAR_ID = {r.id: r for r in R.REFERENTIELS}


def test_list_matches_embedded_files():
    assert R.ecarts_embarques() == []


def test_download_urls_match_versions():
    assert R.FNFE_VERSION in fetch_rules.FNFE.url
    assert R.CEN_VERSION in fetch_rules.EN16931.url
    assert R.DGFIP_VERSION in fetch_rules.DGFIP.url


@pytest.mark.parametrize("fichier", ["NOTICE", "LICENSE.md"])
def test_attribution_files_match_versions(fichier):
    texte = (Path(__file__).parents[2] / fichier).read_text(encoding="utf-8")
    for valeur in (R.FNFE_VERSION, R.CEN_VERSION, R.FACTURX_VERSION, R.ANNEXE7_VERSION, R.CODES_DATE):
        assert valeur in texte, valeur


def test_ids_categories_and_dependencies_are_consistent():
    assert len(PAR_ID) == len(R.REFERENTIELS)
    assert {r.categorie for r in R.REFERENTIELS} == set(R.CATEGORIES)
    assert all(r.suit in PAR_ID for r in R.REFERENTIELS if r.suit)


def test_every_publisher_is_listed_in_organisations():
    for ref in R.REFERENTIELS:
        if ref.editeur not in ("État français", "Fchecker"):
            assert any(o in ref.editeur for o in R.ORGANISMES), ref.editeur


def lecteur(version: str):
    return lambda url: f'{{"tag_name": "validation-{version}"}}'


def test_up_to_date():
    ref = replace(PAR_ID["en16931"], version="1.0.0")
    assert R.verifier(ref, lecteur("1.0.0")).etat is R.Etat.A_JOUR


def test_cen_newer_version_waits_for_fnfe():
    resultat = R.verifier(replace(PAR_ID["en16931"], version="1.0.0"), lecteur("1.0.1"))
    assert resultat.etat is R.Etat.EN_ATTENTE and "fnfe" in resultat.detail


def test_new_fnfe_must_be_integrated():
    assert R.verifier(replace(PAR_ID["fnfe"], version="1.0.0"), lecteur("1.0.1")).etat is R.Etat.A_METTRE_A_JOUR


def test_version_comparison_is_numeric():
    assert R._numeros("1.10") > R._numeros("1.09.2")
    assert R._numeros("1.4") == R._numeros("1.4.0")


def test_highest_version_found_is_kept():
    pages = "Version 3.1 des spécifications externes ; Version 3.3 des spécifications externes ; Version 3.2 des spécifications externes"
    ref = replace(PAR_ID["dgfip"], version="3.2")
    assert R.verifier(ref, lambda url: pages).etat is R.Etat.A_METTRE_A_JOUR


def test_network_failure_is_never_up_to_date():
    def echec(url):
        raise OSError("réseau")

    assert R.verifier(PAR_ID["fnfe"], echec).etat is R.Etat.INCONNU


def test_changed_page_format_is_unknown():
    assert R.verifier(PAR_ID["fnfe"], lambda url: "<html></html>").etat is R.Etat.INCONNU


def test_manual_review_expires():
    ref = replace(PAR_ID["cgi-242"], verifie_le=date(2026, 1, 1))
    assert "à relire" in R.verifier(ref, lecteur("0"), date(2026, 11, 5)).detail
    assert "relu" in R.verifier(ref, lecteur("0"), date(2026, 2, 1)).detail


def test_exit_code_is_one_only_for_master_update(monkeypatch):
    monkeypatch.setattr(R, "verifier_tous", lambda: [R.Resultat(PAR_ID["en16931"], R.Etat.EN_ATTENTE, "x")])
    assert R.main() == 0
    monkeypatch.setattr(R, "verifier_tous", lambda: [R.Resultat(PAR_ID["fnfe"], R.Etat.A_METTRE_A_JOUR, "x")])
    assert R.main() == 1


def test_import_loads_neither_network_nor_qt():
    code = ("import sys, fchecker.core.referentiels;"
            "assert 'httpx' not in sys.modules and 'PySide6' not in sys.modules")
    subprocess.run([sys.executable, "-c", code], check=True)


@pytest.mark.parametrize("ref", R.REFERENTIELS, ids=lambda r: r.id)
def test_entries_are_complete(ref):
    assert ref.nom and ref.version and ref.publication and ref.editeur and ref.url and ref.usage
