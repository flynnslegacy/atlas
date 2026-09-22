import pytest
from fastapi.testclient import TestClient

from services.tts.serveur import (
    TAILLE_MORCEAU,
    aligner_sur_echantillons,
    app,
    en_blocs,
    obtenir_moteur,
)


class FauxMoteur:
    nom = "faux"

    def synthetiser(self, texte: str, voix: str):
        # trois morceaux de 20 ms, pour vérifier que le streaming passe bien
        for _ in range(3):
            yield b"\x00\x01" * 320


@pytest.fixture
def client():
    app.dependency_overrides[obtenir_moteur] = lambda: FauxMoteur()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_synthetiser_rend_un_wav_avec_les_morceaux(client):
    r = client.post("/synthesize", json={"text": "Bonjour David.", "voice": "fr"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    assert r.content[:4] == b"RIFF"
    assert r.content[8:12] == b"WAVE"
    assert len(r.content) == 44 + 3 * 640


def test_un_texte_vide_est_refuse(client):
    assert client.post("/synthesize", json={"text": "", "voice": "fr"}).status_code == 400


def test_un_texte_uniquement_blanc_est_refuse(client):
    assert client.post("/synthesize", json={"text": "   ", "voice": "fr"}).status_code == 400


def test_la_route_de_sante_repond(client):
    r = client.get("/sante")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_aligner_rend_l_octet_orphelin():
    assert aligner_sur_echantillons(b"\x01\x02\x03") == (b"\x01\x02", b"\x03")


def test_aligner_ne_coupe_rien_quand_c_est_pair():
    assert aligner_sur_echantillons(b"\x01\x02") == (b"\x01\x02", b"")


def test_en_blocs_conserve_le_reste():
    blocs, reste = en_blocs(b"\x00" * (TAILLE_MORCEAU + 100))
    assert len(blocs) == 1 and len(blocs[0]) == TAILLE_MORCEAU
    assert reste == b"\x00" * 100
