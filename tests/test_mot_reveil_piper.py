import json
from collections import Counter
from types import SimpleNamespace

import numpy as np

from scripts.mot_reveil.audio import lire_wav
from scripts.mot_reveil.generer_piper import Tache, planifier, produire


def test_planifier_est_reproductible_et_couvre_les_locuteurs():
    locuteurs = {"a": 1, "b": 3}
    t1 = planifier(locuteurs, ["x", "y"], 4000, "piper_pos", graine=1)
    assert t1 == planifier(locuteurs, ["x", "y"], 4000, "piper_pos", graine=1)
    assert len(t1) == 4000 and t1[0].nom == "piper_pos_000000"
    paires = Counter((t.voix, t.locuteur) for t in t1)
    assert set(paires) == {("a", None), ("b", 0), ("b", 1), ("b", 2)}
    assert all(800 < n < 1200 for n in paires.values())  # chaque locuteur ~ 1/4
    assert all(0.8 <= t.vitesse <= 1.3 for t in t1)


class FausseVoix:
    config = SimpleNamespace(sample_rate=22050, num_speakers=1)

    def __init__(self, silencieuse=False):
        self.silencieuse = silencieuse

    def synthesize(self, texte, syn_config=None):
        t = np.arange(22050) / 22050
        audio = np.zeros(22050) if self.silencieuse else 0.5 * np.sin(2 * np.pi * 300 * t)
        yield SimpleNamespace(audio_float_array=audio.astype(np.float32), sample_rate=22050)


def _tache(nom, voix="v"):
    return Tache(nom, voix, None, "Eille Atlasse", 1.0, 0.6, 0.8)


def test_produire_ecrit_du_16k_et_saute_l_existant(tmp_path):
    voix = {"v": FausseVoix(), "muette": FausseVoix(silencieuse=True)}
    taches = [_tache("p1"), _tache("p2", voix="muette")]
    config = lambda **k: k  # noqa: E731
    assert produire(taches, voix, tmp_path, fabrique_config=config) == 1  # la muette est jetée
    audio, frequence = lire_wav(tmp_path / "p1.wav")
    assert frequence == 16000 and 15000 < audio.size <= 16000
    assert produire(taches, voix, tmp_path, fabrique_config=config) == 0


def test_produire_ecrit_un_manifeste_et_le_complete_a_la_reprise(tmp_path):
    """Sans lui, David ne peut pas retrouver quels fichiers viennent de la voix mls."""
    voix = {"v": FausseVoix()}
    config = lambda **k: k  # noqa: E731
    taches = [_tache("p1"), _tache("p2")]
    assert produire(taches, voix, tmp_path, fabrique_config=config) == 2
    manifeste = json.loads((tmp_path / "manifeste.json").read_text())
    assert manifeste["p1"] == {
        "voix": "v",
        "locuteur": None,
        "texte": "Eille Atlasse",
        "vitesse": 1.0,
    }
    assert set(manifeste) == {"p1", "p2"}

    # Reprise avec une tâche de plus : le manifeste se complète sans perdre les anciennes.
    taches_reprise = taches + [_tache("p3")]
    assert produire(taches_reprise, voix, tmp_path, fabrique_config=config) == 1
    manifeste_reprise = json.loads((tmp_path / "manifeste.json").read_text())
    assert set(manifeste_reprise) == {"p1", "p2", "p3"}
