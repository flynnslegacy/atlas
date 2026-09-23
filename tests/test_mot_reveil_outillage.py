import re
import subprocess
from pathlib import Path

DOSSIER = Path("scripts/mot_reveil")


def test_les_scripts_shell_sont_syntaxiquement_valides():
    for script in ("telecharger_donnees.sh", "entrainer.sh"):
        assert subprocess.run(["bash", "-n", str(DOSSIER / script)]).returncode == 0


def test_le_dockerfile_fige_la_pile_verifiee():
    texte = (DOSSIER / "Dockerfile").read_text()
    for attendu in (
        "FROM python:3.10-slim",
        "torch==1.13.1+cu117",
        "checkout 368c037",
        "piper-tts==1.3.0",
        "tensorflow-cpu==2.8.1",
        '"pyarrow<15"',
        '"fsspec<2024.1.0"',
        "/opt/psg/generate_samples.py",
    ):
        assert attendu in texte


def test_la_procedure_ne_publie_aucune_adresse():
    for fichier in (DOSSIER / "LISEZMOI.md", DOSSIER / "Dockerfile"):
        assert not re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", fichier.read_text())


def test_l_ancienne_procedure_a_disparu():
    assert not Path("scripts/entrainer_mot_reveil.md").exists()
