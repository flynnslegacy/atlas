import pytest

from bench.bench import normaliser, retard_fin_enonce, taux_erreur_mots, verifier_modele_vad


def test_normaliser_enleve_la_ponctuation_et_la_casse():
    assert normaliser("Il est Midi, non ?") == "il est midi non"


def test_normaliser_ecrase_les_espaces():
    assert normaliser("  il   est   midi  ") == "il est midi"


def test_un_texte_identique_donne_zero():
    assert taux_erreur_mots("il est midi", "Il est midi.") == 0.0


def test_un_mot_faux_sur_trois():
    assert taux_erreur_mots("il est midi", "il est minuit") == 1 / 3


def test_un_mot_manquant_compte():
    assert taux_erreur_mots("il est bien midi", "il est midi") == 1 / 4


def test_un_attendu_vide_donne_zero_si_obtenu_vide():
    assert taux_erreur_mots("", "") == 0.0


PAROLE_400MS = [True] * 20


def test_le_retard_se_compte_depuis_la_derniere_parole():
    parole = PAROLE_400MS + [False] * 25  # 500 ms de silence final
    assert retard_fin_enonce(parole, silence_ms=400) == (400, 1)


def test_une_courte_pause_ne_coupe_pas_la_phrase():
    parole = PAROLE_400MS + [False] * 10 + PAROLE_400MS + [False] * 25  # pause de 200 ms
    assert retard_fin_enonce(parole, silence_ms=400) == (400, 1)


def test_une_longue_pause_coupe_la_phrase_trop_tot():
    parole = PAROLE_400MS + [False] * 25 + PAROLE_400MS + [False] * 25  # pause de 500 ms
    assert retard_fin_enonce(parole, silence_ms=400) == (400, 2)


def test_une_phrase_sans_fin_n_a_pas_de_retard():
    assert retard_fin_enonce(PAROLE_400MS * 3, silence_ms=400) == (None, 0)


def test_sans_modele_silero_le_banc_s_arrete_en_disant_comment_le_telecharger(tmp_path):
    with pytest.raises(SystemExit) as arret:
        verifier_modele_vad(str(tmp_path / "silero_vad.onnx"))
    assert "curl -L -o models/silero_vad.onnx" in str(arret.value)
