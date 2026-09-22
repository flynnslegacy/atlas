import io
import time
import wave

import pytest
from fastapi.testclient import TestClient

from services.stt.serveur import MoteurWhisper, app, obtenir_transcripteur


class FauxTranscripteur:
    def __init__(self) -> None:
        self.appels: list[bytes] = []

    def transcrire(self, wav: bytes) -> tuple[str, str, int]:
        self.appels.append(wav)
        return ("il est quatorze heures", "fr", 1500)


def _wav_silencieux(ms: int = 1000) -> bytes:
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\x00\x00" * (16 * ms))
    return tampon.getvalue()


@pytest.fixture
def client():
    faux = FauxTranscripteur()
    app.dependency_overrides[obtenir_transcripteur] = lambda: faux
    yield TestClient(app), faux
    app.dependency_overrides.clear()


def test_transcrire_rend_le_texte(client):
    c, _ = client
    r = c.post("/transcribe", content=_wav_silencieux(), headers={"Content-Type": "audio/wav"})
    assert r.status_code == 200
    assert r.json() == {"text": "il est quatorze heures", "language": "fr", "duration_ms": 1500}


def test_un_corps_qui_n_est_pas_un_wav_est_refuse(client):
    c, _ = client
    r = c.post(
        "/transcribe", content=b"ceci n'est pas un wav", headers={"Content-Type": "audio/wav"}
    )
    assert r.status_code == 400


def test_un_corps_vide_est_refuse(client):
    c, _ = client
    r = c.post("/transcribe", content=b"", headers={"Content-Type": "audio/wav"})
    assert r.status_code == 400


def test_la_route_de_sante_repond(client):
    c, _ = client
    r = c.get("/sante")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_le_moteur_se_decharge_apres_inactivite():
    m = MoteurWhisper("x", dechargement_s=0)
    m._modele = object()
    m._dernier_usage = time.monotonic() - 1
    m.decharger_si_inactif()
    assert m.charge is False


def test_le_moteur_ne_se_decharge_pas_pendant_une_transcription():
    m = MoteurWhisper("x", dechargement_s=0)
    m._modele = object()
    m._dernier_usage = time.monotonic() - 1
    m._en_cours = 1
    m.decharger_si_inactif()
    assert m.charge is True


def test_le_moteur_reste_charge_avant_le_delai():
    m = MoteurWhisper("x", dechargement_s=300)
    m._modele = object()
    m._dernier_usage = time.monotonic()
    m.decharger_si_inactif()
    assert m.charge is True
