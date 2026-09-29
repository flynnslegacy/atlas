"""`make run-core`, lancé pour de vrai avec un faux Core : il le relance, par un make neuf qui
relit le .env, tant que le Core laisse la marque `donnees/redemarrer`, et s'arrête avec lui
sinon."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DEPOT = Path(__file__).resolve().parents[1]
# Il note ce qu'il voit du .env ; la première fois, il change le .env et demande à revenir.
FAUX_CORE = """
import os, pathlib, sys
journal = pathlib.Path("journal")
with journal.open("a") as f:
    f.write(f"{os.environ.get('ATLAS_ESSAI')} {os.environ.get('ATLAS_RETIRE', '-')}\\n")
if len(journal.read_text().splitlines()) == 1 and "revenir" in sys.argv:
    pathlib.Path(".env").write_text("ATLAS_ESSAI=2\\n")
    pathlib.Path("donnees").mkdir(exist_ok=True)
    pathlib.Path("donnees/redemarrer").touch()
sys.exit(int(sys.argv[1]))
"""

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make absent")


def lancer(dossier: Path, *arguments: str) -> subprocess.CompletedProcess:
    # Un Makefile qui ignorerait COMMANDE_CORE lancerait le vrai Core : jamais dans un test.
    makefile = (DEPOT / "Makefile").read_text(encoding="utf-8")
    assert "$(COMMANDE_CORE)" in makefile, "run-core ne sait pas encore lancer un autre Core"
    shutil.copy(DEPOT / "Makefile", dossier / "Makefile")
    (dossier / "faux_core.py").write_text(FAUX_CORE)
    environ = {
        k: v for k, v in os.environ.items() if not k.startswith(("ATLAS_", "MAKE", "MFLAGS"))
    }
    commande = f"COMMANDE_CORE={sys.executable} faux_core.py {' '.join(arguments)}"
    return subprocess.run(
        ["make", "-s", "run-core", commande],
        cwd=dossier,
        env=environ,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_le_core_qui_le_demande_revient_avec_le_env_relu(tmp_path):
    (tmp_path / ".env").write_text("ATLAS_ESSAI=1\nexport ATLAS_RETIRE = oui\n")
    r = lancer(tmp_path, "0", "revenir")
    assert r.returncode == 0, r.stderr
    # Relancé une fois, avec la nouvelle valeur ; la variable retirée n'a pas survécu.
    assert (tmp_path / "journal").read_text().splitlines() == ["1 oui", "2 -"]
    assert not (tmp_path / "donnees" / "redemarrer").exists()


def test_sans_marque_la_boucle_s_arrete_avec_le_core(tmp_path):
    (tmp_path / ".env").write_text("ATLAS_ESSAI=1\n")
    r = lancer(tmp_path, "3")
    assert r.returncode != 0, "le Core est tombé : make le dit (launchd le relance)"
    assert (tmp_path / "journal").read_text().splitlines() == ["1 -"]


def test_une_marque_restee_la_ne_relance_rien(tmp_path):
    (tmp_path / "donnees").mkdir()
    (tmp_path / "donnees" / "redemarrer").touch()  # un Core tué juste après l'avoir laissée
    r = lancer(tmp_path, "0")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "journal").read_text().splitlines() == ["None -"]
