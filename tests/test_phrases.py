"""Tests pour le découpage en phrases françaises."""

from helios_core.phrases import DecoupeurPhrases


def test_une_phrase_complete_sort_immediatement():
    d = DecoupeurPhrases()
    assert d.ajouter("Bonjour David.") == ["Bonjour David."]


def test_une_phrase_incomplete_est_retenue():
    d = DecoupeurPhrases()
    assert d.ajouter("Bonjour ") == []
    assert d.ajouter("David.") == ["Bonjour David."]


def test_deux_phrases_dans_un_fragment():
    d = DecoupeurPhrases()
    assert d.ajouter("Il est midi. Tu déjeunes ?") == ["Il est midi.", "Tu déjeunes ?"]


def test_une_abreviation_ne_coupe_pas():
    d = DecoupeurPhrases()
    assert d.ajouter("M. Durand est arrivé.") == ["M. Durand est arrivé."]


def test_une_decimale_ne_coupe_pas():
    d = DecoupeurPhrases()
    assert d.ajouter("Il fait 3.5 degrés dehors.") == ["Il fait 3.5 degrés dehors."]


def test_les_points_de_suspension_ne_coupent_pas_trois_fois():
    d = DecoupeurPhrases()
    assert d.ajouter("Attends... je réfléchis.") == ["Attends... je réfléchis."]


def test_le_flux_caractere_par_caractere_donne_le_meme_resultat():
    d = DecoupeurPhrases()
    sorties = []
    for c in "Il est midi. Tu déjeunes ?":
        sorties.extend(d.ajouter(c))
    sorties.extend(d.vider())
    assert sorties == ["Il est midi.", "Tu déjeunes ?"]


def test_vider_rend_une_phrase_sans_ponctuation_finale():
    d = DecoupeurPhrases()
    d.ajouter("Bon, on verra")
    assert d.vider() == ["Bon, on verra"]


def test_vider_deux_fois_ne_repete_rien():
    d = DecoupeurPhrases()
    d.ajouter("Bon")
    assert d.vider() == ["Bon"]
    assert d.vider() == []
