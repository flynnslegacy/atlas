"""Le déploiement sur le néo : le modèle du service launchd, son installateur, son guide."""

import plistlib
import re
import subprocess
from pathlib import Path

import pytest

NEO = Path(__file__).resolve().parent.parent / "scripts" / "neo"


def _service() -> dict:
    modele = (NEO / "fr.atlas.core.plist").read_text()
    rempli = (
        modele.replace("__DOSSIER__", "/Users/atlas/atlas")
        .replace("__MAISON__", "/Users/atlas")
        .replace("__UTILISATEUR__", "atlas")
    )
    return plistlib.loads(rempli.encode())


def test_le_service_lance_le_core_et_le_relance_s_il_tombe():
    service = _service()
    assert service["Label"] == "fr.atlas.core"
    assert service["ProgramArguments"] == ["/usr/bin/make", "run-core"]
    assert service["WorkingDirectory"] == "/Users/atlas/atlas"
    assert service["UserName"] == "atlas", "jamais root : Claude tourne sous l'utilisateur"
    assert service["RunAtLoad"] is True and service["KeepAlive"] is True


def test_le_service_trouve_uv_et_claude():
    environnement = _service()["EnvironmentVariables"]
    assert environnement["HOME"] == "/Users/atlas"
    assert environnement["PATH"].split(":")[0] == "/Users/atlas/.local/bin"


def test_le_journal_du_service_va_dans_donnees():
    service = _service()
    assert service["StandardOutPath"] == "/Users/atlas/atlas/donnees/logs/core.log"
    assert service["StandardErrorPath"] == service["StandardOutPath"]


def test_l_installateur_est_un_script_bash_valide():
    script = NEO / "installer_service.sh"
    assert script.stat().st_mode & 0o111, "le script doit être exécutable"
    subprocess.run(["bash", "-n", str(script)], check=True)


def test_l_apercu_de_l_installateur_remplit_le_modele():
    script = NEO / "installer_service.sh"
    sortie = subprocess.run(
        ["bash", str(script), "--apercu"], check=True, capture_output=True, text=True
    ).stdout
    assert "__" not in sortie, "tous les repères sont remplacés"
    service = plistlib.loads(sortie.encode())
    assert service["WorkingDirectory"] == str(NEO.parent.parent)
    assert service["UserName"] and service["EnvironmentVariables"]["HOME"]


@pytest.mark.parametrize(
    ("contenu", "manque"),
    [
        (None, ".env"),
        (
            "ATLAS_WEB_CLE=a\nATLAS_AUDIO_CLE=b\n# CLAUDE_CODE_OAUTH_TOKEN=\n",
            "CLAUDE_CODE_OAUTH_TOKEN",
        ),
        ("ATLAS_WEB_CLE=a\nATLAS_AUDIO_CLE=\nCLAUDE_CODE_OAUTH_TOKEN=c\n", "ATLAS_AUDIO_CLE"),
    ],
)
def test_l_installateur_refuse_un_env_incomplet(tmp_path, contenu, manque):
    # Une copie du dépôt réduite au script et au modèle : il s'arrête avant tout sudo.
    (tmp_path / "scripts" / "neo").mkdir(parents=True)
    for nom in ("installer_service.sh", "fr.atlas.core.plist"):
        (tmp_path / "scripts" / "neo" / nom).write_bytes((NEO / nom).read_bytes())
    if contenu is not None:
        (tmp_path / ".env").write_text(contenu)

    resultat = subprocess.run(
        ["bash", str(tmp_path / "scripts" / "neo" / "installer_service.sh")],
        capture_output=True,
        text=True,
    )

    assert resultat.returncode == 1
    assert manque in resultat.stderr


@pytest.mark.parametrize("fichier", sorted(p.name for p in NEO.iterdir()))
def test_rien_de_prive_dans_le_deploiement(fichier):
    texte = (NEO / fichier).read_text()
    assert not re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", texte), "aucune adresse IP"
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", texte), "aucune adresse e-mail"
    assert not re.search(r"sk-ant-\w", texte), "aucun jeton"
