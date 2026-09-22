"""Route /synthesize : validation à la frontière et erreurs rendues avant le flux."""

import pytest
from fastapi.testclient import TestClient

from services.tts.serveur import TAILLE_MORCEAU, app, obtenir_moteur


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
