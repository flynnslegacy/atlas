from bench.bench import normaliser, taux_erreur_mots


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
