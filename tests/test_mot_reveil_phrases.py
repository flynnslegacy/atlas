import re

import pytest

from scripts.mot_reveil.phrases import (
    NEGATIVES,
    NEGATIVES_QWEN,
    POSITIVES,
    POSITIVES_QWEN,
    entend_hey_atlas,
    garder_negatif,
    garder_positif,
)
from scripts.mot_reveil.repartition import est_test, noms_copies, repartir


@pytest.mark.parametrize(
    "texte",
    [
        "Hey Atlas.",
        "Eh, Atlas !",
        "Hé Atlas",
        "hey atlasse",
        "Alors, hey Atlas, tu m'entends ?",
        # « Hé » et « Et » se prononcent pareil : Whisper écrit souvent « Et Atlas ».
        "Et Atlas.",
        "et atlas",
    ],
)
def test_entend_hey_atlas(texte):
    assert entend_hey_atlas(texte)


@pytest.mark.parametrize(
    "texte",
    ["Atlas.", "Le projet Atlas avance.", "Hélas", "Hey Nicolas", "J'ai l'atlas", "Et là", ""],
)
def test_n_entend_pas_hey_atlas(texte):
    assert not entend_hey_atlas(texte)


def test_les_textes_synthetises_suivent_l_orthographe_phonetique():
    assert all("Atlasse" in p and p.startswith("Eille") for p in POSITIVES)
    assert "Atlasse" in NEGATIVES  # « Atlas » seul est un négatif


def test_qwen_recoit_les_memes_phrases_en_orthographe_usuelle():
    assert POSITIVES_QWEN == ["Hey Atlas", "Hey Atlas !", "Hey, Atlas.", "Hey Atlas ?"]
    assert len(NEGATIVES_QWEN) == len(NEGATIVES)
    assert {"Atlas", "Le projet Atlas avance bien.", "Hey Nicolas", "Dallas"} <= set(NEGATIVES_QWEN)
    assert not any(re.search(r"Eille|asse\b", t) for t in POSITIVES_QWEN + NEGATIVES_QWEN)


def test_un_positif_se_juge_a_sa_duree_seulement():
    # Whisper ne reconnaît pas deux mots isolés (29 % des prises de David) ; les voix
    # qui déraillent, elles, produisent 3 à 9 s de charabia.
    assert garder_positif(0.9) and garder_positif(0.4) and garder_positif(2.0)
    assert not garder_positif(0.3)  # un claquement, pas deux mots
    assert not garder_positif(2.9)  # le charabia de gilles commence à 2,9 s


def test_un_negatif_refuse_ce_qui_sonne_comme_le_mot():
    assert garder_negatif("Atlas.", duree_s=0.8)
    assert not garder_negatif("Hey Atlas", duree_s=1.0)
    assert not garder_negatif("Et Atlas.", duree_s=1.0)
    assert not garder_negatif("Hélas", duree_s=4.0)


def test_est_test_est_stable_et_proche_de_la_proportion():
    noms = [f"extrait_{i:05d}.wav" for i in range(3000)]
    part = sum(est_test(n, 3) for n in noms) / len(noms)
    assert 0.28 < part < 0.38
    assert [est_test(n, 3) for n in noms] == [est_test(n, 3) for n in noms]


def test_repartir_est_complet_et_disjoint():
    noms = [f"n{i}.wav" for i in range(100)]
    entrainement, test = repartir(noms, 10)
    assert set(entrainement).isdisjoint(test)
    assert sorted(entrainement + test) == sorted(noms)
    assert entrainement == sorted(entrainement)


def test_noms_copies():
    copies = noms_copies("david_bureau_001.wav", 3)
    assert copies == [
        "david_bureau_001__c00.wav",
        "david_bureau_001__c01.wav",
        "david_bureau_001__c02.wav",
    ]
