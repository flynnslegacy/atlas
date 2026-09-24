"""Tests pour le découpage en phrases françaises."""

import pytest

from atlas_core.phrases import LIMITE, DecoupeurPhrases


def _mot_par_mot(texte: str) -> list[str]:
    """Nourrit le découpeur comme le fait Claude : un mot (et son espace) à la fois."""
    d = DecoupeurPhrases()
    sorties: list[str] = []
    for mot in texte.split(" "):
        sorties.extend(d.ajouter(mot + " "))
    sorties.extend(d.vider())
    return sorties


def test_une_phrase_complete_sort_des_que_le_caractere_suivant_arrive():
    d = DecoupeurPhrases()
    assert d.ajouter("Bonjour David.") == [], "« David. » pourrait encore devenir « David.fr »"
    assert d.ajouter(" ") == ["Bonjour David."]


def test_une_phrase_incomplete_est_retenue():
    d = DecoupeurPhrases()
    assert d.ajouter("Bonjour ") == []
    assert d.ajouter("David. ") == ["Bonjour David."]


def test_vider_rend_la_derniere_phrase_ponctuee():
    d = DecoupeurPhrases()
    assert d.ajouter("Bonjour David.") == []
    assert d.vider() == ["Bonjour David."]


def test_deux_phrases_dans_un_fragment():
    d = DecoupeurPhrases()
    assert d.ajouter("Il est midi. Tu déjeunes ? ") == ["Il est midi.", "Tu déjeunes ?"]


def test_une_abreviation_ne_coupe_pas():
    d = DecoupeurPhrases()
    assert d.ajouter("M. Durand est arrivé. ") == ["M. Durand est arrivé."]


def test_une_decimale_ne_coupe_pas():
    d = DecoupeurPhrases()
    assert d.ajouter("Il fait 3.5 degrés dehors. ") == ["Il fait 3.5 degrés dehors."]


def test_un_nombre_coupe_en_deux_fragments_reste_entier():
    d = DecoupeurPhrases()
    assert d.ajouter("Ça coûte 3.") == []
    assert d.ajouter("5 euros. ") == ["Ça coûte 3.5 euros."]


def test_une_abreviation_coupee_en_deux_fragments_ne_coupe_pas():
    d = DecoupeurPhrases()
    assert d.ajouter("Demande à M.") == []
    assert d.ajouter(" Dupont. ") == ["Demande à M. Dupont."]


def test_un_nom_de_site_ne_coupe_pas():
    d = DecoupeurPhrases()
    assert d.ajouter("Selon meteo.") == []
    assert d.ajouter("fr il pleut. ") == ["Selon meteo.fr il pleut."]


def test_les_points_de_suspension_ne_coupent_pas_trois_fois():
    d = DecoupeurPhrases()
    assert d.ajouter("Attends... je réfléchis. ") == ["Attends... je réfléchis."]


def test_des_points_de_suspension_en_fin_de_texte_attendent_la_suite():
    d = DecoupeurPhrases()
    assert d.ajouter("Attends... ") == []
    assert d.ajouter("Voilà. ") == ["Attends...", "Voilà."]


def test_le_caractere_points_de_suspension_est_une_serie():
    d = DecoupeurPhrases()
    assert d.ajouter("Bon… je vois. Oui… Et toi ? ") == ["Bon… je vois.", "Oui…", "Et toi ?"]


def test_un_numero_de_liste_ne_coupe_pas():
    d = DecoupeurPhrases()
    phrases = d.ajouter("Deux idées :\n1. Aller au parc.\n2. Lire un livre.\n")
    assert phrases == ["Deux idées :\n1. Aller au parc.", "2. Lire un livre."]


def test_une_annee_en_fin_de_phrase_coupe():
    d = DecoupeurPhrases()
    assert d.ajouter("C'était en 2026. Puis ") == ["C'était en 2026."]


def test_le_flux_caractere_par_caractere_donne_le_meme_resultat():
    d = DecoupeurPhrases()
    sorties = []
    for c in "Il est midi. Tu déjeunes ?":
        sorties.extend(d.ajouter(c))
    sorties.extend(d.vider())
    assert sorties == ["Il est midi.", "Tu déjeunes ?"]


def test_le_flux_mot_par_mot_garde_nombres_et_abreviations():
    texte = "Il fait 3.5 degrés. M. Dupont dit 3,5. Pas mal !"
    assert _mot_par_mot(texte) == ["Il fait 3.5 degrés.", "M. Dupont dit 3,5.", "Pas mal !"]


def test_vider_rend_une_phrase_sans_ponctuation_finale():
    d = DecoupeurPhrases()
    d.ajouter("Bon, on verra")
    assert d.vider() == ["Bon, on verra"]


def test_vider_deux_fois_ne_repete_rien():
    d = DecoupeurPhrases()
    d.ajouter("Bon")
    assert d.vider() == ["Bon"]
    assert d.vider() == []


def test_une_phrase_trop_longue_est_coupee_sur_la_derniere_virgule():
    d = DecoupeurPhrases()
    phrases = d.ajouter("a" * 200 + ", puis " + "b" * 30 + ", enfin " + "c" * 30 + " fin. ")
    assert phrases == ["a" * 200 + ", puis " + "b" * 30 + ",", "enfin " + "c" * 30 + " fin."]


def test_une_phrase_trop_longue_sans_virgule_est_coupee_sur_un_espace():
    d = DecoupeurPhrases()
    phrases = d.ajouter("mot " * 80)  # 320 caractères, aucune ponctuation
    assert phrases == [" ".join(["mot"] * 62)], "au-delà de la limite, on n'attend plus"
    assert len(phrases[0]) <= LIMITE


def test_la_coupe_forcee_ne_separe_pas_les_chiffres_d_une_decimale():
    texte = "x" * 240 + " 3,5 " + "y" * 20
    d = DecoupeurPhrases()
    phrases = d.ajouter(texte)
    assert phrases == ["x" * 240 + " 3,5"]


def test_un_mot_sans_espace_plus_long_que_la_limite_est_coupe_net():
    d = DecoupeurPhrases()
    assert d.ajouter("z" * (LIMITE + 10)) == ["z" * LIMITE]
    assert d.vider() == ["z" * 10]


@pytest.mark.parametrize("longueur", [LIMITE - 1, LIMITE])
def test_une_phrase_a_la_limite_n_est_pas_coupee(longueur):
    phrase = "a" * (longueur - 1) + "."
    d = DecoupeurPhrases()
    assert d.ajouter(phrase + " ") == [phrase]
