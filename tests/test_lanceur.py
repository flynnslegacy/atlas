"""`make run-core`, lancé pour de vrai avec un faux Core : il le relance, par un make neuf qui
relit le .env, tant que le Core laisse la marque `donnees/redemarrer`, et s'arrête avec lui
sinon."""

import os
import shutil
import signal
import subprocess
import sys
import time
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
if "attendre" in sys.argv:
    # Comme uvicorn : il attend un signal, puis s'arrête proprement, sans se presser.
    import signal, time
    def arreter(numero, _):
        with journal.open("a") as f:
            f.write(f"{signal.Signals(numero).name}\\n")
        time.sleep(0.3)
        with journal.open("a") as f:
            f.write("arrêt propre\\n")
        sys.exit(0)
    signal.signal(signal.SIGTERM, arreter)
    signal.signal(signal.SIGINT, arreter)
    pathlib.Path("pret").write_text(str(os.getpid()))
    while True:
        time.sleep(0.05)
sys.exit(int(sys.argv[1]))
"""

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make absent")


def preparer(dossier: Path, *arguments: str) -> tuple[list[str], dict[str, str]]:
    # Un Makefile qui ignorerait COMMANDE_CORE lancerait le vrai Core : jamais dans un test.
    makefile = (DEPOT / "Makefile").read_text(encoding="utf-8")
    assert "$(COMMANDE_CORE)" in makefile, "run-core ne sait pas encore lancer un autre Core"
    shutil.copy(DEPOT / "Makefile", dossier / "Makefile")
    (dossier / "faux_core.py").write_text(FAUX_CORE)
    environ = {
        k: v for k, v in os.environ.items() if not k.startswith(("ATLAS_", "MAKE", "MFLAGS"))
    }
    commande = f"COMMANDE_CORE={sys.executable} faux_core.py {' '.join(arguments)}"
    return ["make", "-s", "run-core", commande], environ


def lancer(dossier: Path, *arguments: str) -> subprocess.CompletedProcess:
    commande, environ = preparer(dossier, *arguments)
    return subprocess.run(
        commande, cwd=dossier, env=environ, capture_output=True, text=True, timeout=60
    )


def demarrer(dossier: Path) -> tuple[subprocess.Popen, int]:
    """`make run-core` avec un faux Core qui attend un signal ; rend make, et le pid du Core."""
    commande, environ = preparer(dossier, "0", "attendre")
    make = subprocess.Popen(
        commande,
        cwd=dossier,
        env=environ,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # son propre groupe, comme dans un Terminal ou sous launchd
    )
    for _ in range(200):
        if (dossier / "pret").exists() and (dossier / "pret").read_text():
            return make, int((dossier / "pret").read_text())
        time.sleep(0.05)
    make.kill()
    raise AssertionError("le faux Core n'a pas démarré")


def vivant(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


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


def test_launchd_qui_arrete_make_arrete_le_core_proprement(tmp_path):
    # launchd envoie SIGTERM au seul make qu'il a lancé (kickstart -k, bootout, réinstallation).
    (tmp_path / ".env").write_text("ATLAS_ESSAI=1\n")
    make, core = demarrer(tmp_path)
    try:
        os.kill(make.pid, signal.SIGTERM)
        make.wait(timeout=10)
        journal = (tmp_path / "journal").read_text().splitlines()
        assert journal == ["1 -", "SIGTERM", "arrêt propre"], "make a attendu son arrêt propre"
        assert not vivant(core), "aucun Core orphelin"
    finally:
        if vivant(core):
            os.kill(core, signal.SIGKILL)


def test_un_ctrl_c_n_envoie_qu_un_signal_au_core(tmp_path):
    # Le Terminal envoie SIGINT à tout le groupe : un second signal ferait sauter à uvicorn
    # son arrêt propre (le résumé de la conversation).
    (tmp_path / ".env").write_text("ATLAS_ESSAI=1\n")
    make, core = demarrer(tmp_path)
    try:
        os.killpg(make.pid, signal.SIGINT)
        make.wait(timeout=10)
        journal = (tmp_path / "journal").read_text().splitlines()
        assert journal == ["1 -", "SIGINT", "arrêt propre"]
        assert not vivant(core)
    finally:
        if vivant(core):
            os.kill(core, signal.SIGKILL)
