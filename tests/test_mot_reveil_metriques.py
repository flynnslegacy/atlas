import numpy as np

from scripts.mot_reveil.audio import ecrire_wav
from scripts.mot_reveil.evaluer import charger
from scripts.mot_reveil.metriques import (
    assembler,
    detectes,
    par_heure,
    reveils,
    seuil_conseille,
)
from scripts.mot_reveil.repartition import est_test


def test_reveils_suit_la_periode_refractaire_du_client():
    scores = [0.0] * 200
    for i in (2, 3, 4, 60, 152):
        scores[i] = 0.9
    # 2 s de réfractaire = 100 blocs : le pic à 60 est ignoré, celui à 152 compte.
    assert reveils(scores, 0.5) == [2, 152]


def test_reveils_respecte_le_seuil():
    assert reveils([0.4, 0.45, 0.2], 0.5) == []


def test_assembler_separe_les_extraits_de_deux_secondes():
    un = np.ones(16000, dtype=np.float32) * 0.1
    audio, segments = assembler({"b": un, "a": un})
    assert audio.size == 16000 * 8  # 2 s + 1 s + 2 s + 1 s + 2 s
    assert [(s.nom, s.debut, s.fin) for s in segments] == [("a", 100, 150), ("b", 250, 300)]


def test_detectes_accepte_un_reveil_jusqu_a_une_seconde_apres():
    _, segments = assembler({"a": np.zeros(16000, np.float32), "b": np.zeros(16000, np.float32)})
    assert detectes([120], segments) == {"a"}
    assert detectes([180], segments) == {"a"}
    assert detectes([210], segments) == set()
    assert detectes([260, 120], segments) == {"a", "b"}


def test_par_heure():
    assert par_heure(1, 180000) == 1.0
    assert par_heure(0, 0) == 0.0


def test_seuil_conseille_prend_le_plus_bas_sans_faux_reveil():
    lignes = [
        {"seuil": 0.3, "atlas_seul": 1, "faux": 0},
        {"seuil": 0.5, "atlas_seul": 0, "faux": 0},
        {"seuil": 0.7, "atlas_seul": 0, "faux": 0},
    ]
    assert seuil_conseille(lignes) == 0.5
    assert seuil_conseille([{"seuil": 0.9, "atlas_seul": 1, "faux": 0}]) is None


def test_charger_ne_rend_que_la_part_reservee_au_test(tmp_path):
    noms = [f"bureau_{i:03d}.wav" for i in range(30)]
    for n in noms:
        ecrire_wav(tmp_path / n, np.full(8000, 0.2, dtype=np.float32))
    extraits = charger(tmp_path, 3, couper=True)
    assert set(extraits) == {n for n in noms if est_test(n, 3)}
