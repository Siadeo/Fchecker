"""Le projet ne cite ni les normes françaises de facturation électronique ni leur éditeur."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]
# Motif assemblé pour que ce fichier ne contienne pas lui-même les termes recherchés.
INTERDIT = re.compile("|".join(("af" + "nor", r"xp[ _-]?z" + "12", r"\bnf" + " en")), re.I)
EXTENSIONS = {".py", ".yaml", ".md", ".j2", ".toml", ".txt", ".xsd", ".xslt", ".xml", ""}


def test_no_reference_in_tracked_files():
    sortie = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True,
                            encoding="utf-8", check=True).stdout
    trouves = []
    for nom in sortie.splitlines():
        chemin = ROOT / nom
        if chemin.is_file() and chemin.suffix in EXTENSIONS:
            if INTERDIT.search(chemin.read_text(encoding="utf-8", errors="ignore")):
                trouves.append(nom)
    assert trouves == []
