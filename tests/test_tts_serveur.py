import json
import sys

import pytest
from fastapi.testclient import TestClient

from services.tts.serveur import (
    TAILLE_MORCEAU,
    MoteurPiper,
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

    def verifier(self, voix: str) -> None:
        pass


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


def test_une_voix_absente_est_une_erreur_500_qui_nomme_le_fichier(tmp_path):
    app.dependency_overrides[obtenir_moteur] = lambda: MoteurPiper(dossier_modeles=str(tmp_path))
    try:
        r = TestClient(app).post("/synthesize", json={"text": "Bonjour.", "voice": "inexistante"})
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 500
    assert str(tmp_path / "inexistante.onnx") in r.json()["detail"]


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


class MoteurSansFin(MoteurPiper):
    """Piper de test qui n'atteint jamais EOF, pour exercer l'abandon du générateur."""

    def _commande(self, modele: str) -> list[str]:
        return [
            sys.executable,
            "-c",
            "import sys\nwhile True:\n sys.stdout.buffer.write(b'\\x00' * 1024)\n"
            " sys.stdout.flush()",
        ]

    def _frequence(self, modele: str) -> int:
        return 22050


def test_abandonner_le_generateur_termine_le_sous_processus():
    moteur = MoteurSansFin()
    generateur = moteur.synthetiser("peu importe", "fr")
    next(generateur)
    next(generateur)
    proc = moteur._dernier_processus

    generateur.close()

    try:
        proc.wait(timeout=5)
    finally:
        # Filet de sécurité pour ne pas laisser le processus tourner si le test échoue.
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
    assert proc.poll() is not None


class MoteurUneSeconde(MoteurPiper):
    """Piper de test : rend exactement une seconde de silence à la fréquence de sa voix."""

    def __init__(self, dossier, frequence: int) -> None:
        super().__init__(dossier_modeles=str(dossier))
        self._octets = frequence * 2

    def _commande(self, modele: str) -> list[str]:
        return [
            sys.executable,
            "-c",
            f"import sys\nsys.stdin.read()\nsys.stdout.buffer.write(b'\\x00' * {self._octets})",
        ]


def _creer_voix(dossier, nom: str, frequence: int) -> None:
    (dossier / f"{nom}.onnx").write_bytes(b"")
    (dossier / f"{nom}.onnx.json").write_text(json.dumps({"audio": {"sample_rate": frequence}}))


@pytest.mark.parametrize("frequence", [22050, 44100, 16000])
def test_une_seconde_de_voix_donne_une_seconde_a_16_khz(tmp_path, frequence):
    # Chaque voix Piper a sa propre fréquence (Siwis 22 050 Hz, Tom 44 100 Hz) :
    # la supposer fixe ralentit ou accélère la parole.
    _creer_voix(tmp_path, "voix", frequence)
    moteur = MoteurUneSeconde(tmp_path, frequence)

    total = sum(len(bloc) for bloc in moteur.synthetiser("peu importe", "voix"))

    assert abs(total - 16000 * 2) <= 2 * TAILLE_MORCEAU


def test_une_configuration_de_voix_absente_est_une_erreur_500(tmp_path):
    (tmp_path / "voix.onnx").write_bytes(b"")
    app.dependency_overrides[obtenir_moteur] = lambda: MoteurPiper(dossier_modeles=str(tmp_path))
    try:
        r = TestClient(app).post("/synthesize", json={"text": "Bonjour.", "voice": "voix"})
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 500
    assert "voix.onnx.json" in r.json()["detail"]
