"""Préchauffage du moteur au démarrage du service, et journaux visibles sous uvicorn."""

import logging
import threading

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
from uvicorn.config import LOGGING_CONFIG

from services.tts import serveur
from services.tts.serveur import MoteurPiper, MoteurQwen3, app, demarrer_prechauffage


class MoteurPrechauffable:
    nom = "prechauffable"
    voix_defaut = "voix_du_moteur"

    def __init__(self, echec: bool = False) -> None:
        self.echec = echec
        self.voix_prechauffees: list[str] = []
        self.fini = threading.Event()

    def prechauffer(self, voix: str) -> None:
        try:
            self.voix_prechauffees.append(voix)
            if self.echec:
                raise RuntimeError("pas de GPU")
        finally:
            self.fini.set()


def test_le_prechauffage_tourne_dans_un_fil_demon(monkeypatch):
    monkeypatch.delenv("ATLAS_TTS_VOIX", raising=False)
    moteur = MoteurPrechauffable()

    fil = demarrer_prechauffage(moteur)

    assert fil is not None and fil.daemon
    fil.join(timeout=5)
    assert moteur.voix_prechauffees == ["voix_du_moteur"]


def test_un_prechauffage_en_echec_est_journalise_sans_planter(monkeypatch, caplog):
    monkeypatch.delenv("ATLAS_TTS_VOIX", raising=False)
    moteur = MoteurPrechauffable(echec=True)

    with caplog.at_level(logging.ERROR, logger=serveur._journal.name):
        fil = demarrer_prechauffage(moteur)
        assert fil is not None
        fil.join(timeout=5)

    assert [r for r in caplog.records if r.levelno == logging.ERROR]
    assert "pas de GPU" in caplog.text


def test_un_moteur_sans_prechauffage_ne_lance_aucun_fil():
    assert demarrer_prechauffage(MoteurPiper()) is None


def test_le_demarrage_du_service_lance_le_prechauffage_du_moteur_choisi(monkeypatch):
    monkeypatch.delenv("ATLAS_TTS_VOIX", raising=False)
    moteur = MoteurPrechauffable()
    monkeypatch.setitem(serveur._moteurs, serveur.MOTEUR, moteur)

    with TestClient(app) as client:
        assert client.get("/sante").status_code == 200
        assert moteur.fini.wait(timeout=5)

    assert moteur.voix_prechauffees == ["voix_du_moteur"]


class ModeleMuet:
    def create_voice_clone_prompt(self, **kwargs):
        return object()


def test_le_proprietaire_voit_le_prechauffage_dans_les_journaux_d_uvicorn(monkeypatch, tmp_path):
    # uvicorn ne configure que ses propres journaux (« uvicorn », niveau INFO, sans
    # propagation) : un message qui n'y passe pas est perdu, et le propriétaire ne saurait
    # pas si le modèle s'est chargé. On reproduit sa configuration le temps du test.
    monkeypatch.delenv("ATLAS_TTS_VOIX", raising=False)
    sf.write(tmp_path / "atlas_reference.wav", np.zeros(2400, np.float32), 24000)
    (tmp_path / "atlas_reference.txt").write_text("Bonjour.", encoding="utf-8")
    moteur = MoteurQwen3(dossier_voix=str(tmp_path), charger=lambda nom: ModeleMuet())
    recus: list[str] = []

    class Collecteur(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            recus.append(record.getMessage())

    journal_uvicorn = logging.getLogger("uvicorn")
    configuration = LOGGING_CONFIG["loggers"]["uvicorn"]
    collecteur = Collecteur()
    monkeypatch.setattr(journal_uvicorn, "propagate", configuration["propagate"])
    journal_uvicorn.addHandler(collecteur)
    niveau = journal_uvicorn.level
    journal_uvicorn.setLevel(configuration["level"])
    try:
        fil = demarrer_prechauffage(moteur)
        assert fil is not None
        fil.join(timeout=5)
    finally:
        journal_uvicorn.removeHandler(collecteur)
        journal_uvicorn.setLevel(niveau)

    assert any("chargement du modèle" in message for message in recus)
    assert any("préchauffé" in message for message in recus)
