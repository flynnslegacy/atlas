"""Route /synthesize : validation à la frontière et erreurs rendues avant le flux."""

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from services.tts.serveur import TAILLE_MORCEAU, MoteurPiper, MoteurQwen3, app, obtenir_moteur


class MoteurEspion:
    nom = "espion"
    voix_defaut = "voix_du_moteur"

    def __init__(self) -> None:
        self.appels: list[tuple[str, str]] = []

    def verifier(self, voix: str) -> None:
        self.appels.append(("verifier", voix))

    def synthetiser(self, texte: str, voix: str):
        self.appels.append(("synthetiser", voix))
        return iter([b"\x00" * TAILLE_MORCEAU])


def poster(moteur, voix: str):
    app.dependency_overrides[obtenir_moteur] = lambda: moteur
    try:
        return TestClient(app).post("/synthesize", json={"text": "Bonjour.", "voice": voix})
    finally:
        app.dependency_overrides.clear()


# Le nom de voix devient un chemin de fichier : il ne doit jamais sortir du dossier des voix.


@pytest.mark.parametrize("voix", ["../x", "a/b", "x.y", "..\\x", "/etc/passwd", "voix\n", "a" * 65])
def test_un_nom_de_voix_qui_pourrait_sortir_du_dossier_est_refuse_en_422(voix):
    espion = MoteurEspion()

    r = poster(espion, voix)

    assert r.status_code == 422
    assert espion.appels == []


@pytest.mark.parametrize(
    "voix", ["", "atlas_reference", "fr_FR-siwis-medium", "fr_FR-tom-medium", "a" * 64]
)
def test_les_noms_de_voix_legitimes_sont_acceptes(voix):
    espion = MoteurEspion()

    r = poster(espion, voix)

    assert r.status_code == 200
    assert espion.appels[0] == ("verifier", voix or "voix_du_moteur")


# Un moteur qui échoue doit le dire par un code d'erreur, pas par un 200 sans son.


@pytest.fixture
def dossier_voix(tmp_path):
    sf.write(tmp_path / "atlas_reference.wav", np.zeros(2400, np.float32), 24000)
    (tmp_path / "atlas_reference.txt").write_text("Bonjour.", encoding="utf-8")
    return tmp_path


def chargeur_sans_memoire(nom_modele: str):
    raise RuntimeError("CUDA out of memory")


class ModeleQuiRefuse:
    def create_voice_clone_prompt(self, **kwargs):
        return object()

    def generate_voice_clone(self, **kwargs):
        raise TypeError("unexpected keyword argument 'max_new_tokens'")


def test_un_chargement_en_echec_rend_503_sans_audio(dossier_voix):
    moteur = MoteurQwen3(dossier_voix=str(dossier_voix), charger=chargeur_sans_memoire)

    r = poster(moteur, "atlas_reference")

    assert r.status_code == 503
    assert not r.content.startswith(b"RIFF")
    assert r.json()["detail"].startswith("moteur de voix indisponible : ")
    assert "CUDA out of memory" in r.json()["detail"]


def test_une_generation_en_echec_rend_503_sans_audio(dossier_voix):
    moteur = MoteurQwen3(dossier_voix=str(dossier_voix), charger=lambda nom: ModeleQuiRefuse())

    r = poster(moteur, "atlas_reference")

    assert r.status_code == 503
    assert not r.content.startswith(b"RIFF")
    assert "max_new_tokens" in r.json()["detail"]


def test_appeler_piper_ne_lance_rien_avant_la_lecture_du_flux(tmp_path):
    # La route appelle synthetiser avant de répondre : pour Piper, fonction génératrice,
    # cet appel ne doit encore rien exécuter.
    moteur = MoteurPiper(dossier_modeles=str(tmp_path))

    moteur.synthetiser("Bonjour.", "absente")

    assert moteur._dernier_processus is None
