import pytest

from atlas_core.mise_en_voix import est_hallucination, nettoyer


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [
        ("Il fait **beau** à Paris.", "Il fait beau à Paris."),
        ("C'est *vraiment* simple.", "C'est vraiment simple."),
        ("## Le résumé\nTout va bien.", "Le résumé Tout va bien."),
        ("Deux idées :\n- aller au parc ;\n- lire.", "Deux idées : aller au parc ; lire."),
        ("Voici :\n1. Aller au parc.", "Voici : Aller au parc."),
        ("• Premier point.", "Premier point."),
        ("Tape `make test` pour voir.", "Tape make test pour voir."),
        ("Regarde https://meteo.fr/paris demain.", "Regarde un lien demain."),
        ("Va sur www.example.org pour ça.", "Va sur un lien pour ça."),
        ("Tout est sur https://x.fr.", "Tout est sur un lien."),
        (
            "D'après [Météo-France](https://meteofrance.com), il pleut.",
            "D'après Météo-France, il pleut.",
        ),
        ("Une   phrase\n\ttrop  espacée. ", "Une phrase trop espacée."),
        ("Il fait 3,5 degrés, soit -2 de moins.", "Il fait 3,5 degrés, soit -2 de moins."),
    ],
)
def test_nettoyer_rend_un_texte_prononcable(brut, attendu):
    assert nettoyer(brut) == attendu


def test_un_texte_deja_propre_ne_change_pas():
    phrase = "Bonjour David, il est midi dix. Tu déjeunes ?"
    assert nettoyer(phrase) == phrase


def test_une_phrase_faite_de_mise_en_forme_devient_vide():
    assert nettoyer("**") == ""
    assert nettoyer("- ") == ""


@pytest.mark.parametrize(
    "fantome",
    [
        "Merci.",
        " merci ! ",
        "Merci beaucoup.",
        "Sous-titres réalisés par la communauté d'Amara.org",
        "Sous-titrage ST' 501",
        "Merci d'avoir regardé cette vidéo !",
        "Abonnez-vous à la chaîne !",
        "[Musique]",
        "♪",
        "...",
        "",
    ],
)
def test_les_phrases_fantomes_de_whisper_sont_reconnues(fantome):
    assert est_hallucination(fantome)


@pytest.mark.parametrize(
    "vraie",
    [
        "Quelle heure est-il ?",
        "Merci pour la météo, et demain ?",
        "Musique classique, tu connais ?",
        "Bonjour Atlas.",
    ],
)
def test_une_vraie_question_n_est_pas_un_fantome(vraie):
    assert not est_hallucination(vraie)
