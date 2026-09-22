import pytest

from atlas_audio.vad import Endpointeur, verifier_bloc

BLOC_MS = 20


def _jouer(e: Endpointeur, motif: list[tuple[bool, int]]) -> list[str]:
    """Joue une suite de (parle, durée_ms) et rend les événements non vides."""
    evenements = []
    for parle, duree in motif:
        for _ in range(duree // BLOC_MS):
            ev = e.ajouter(parle)
            if ev != "rien":
                evenements.append(ev)
    return evenements


def test_un_silence_continu_ne_produit_rien():
    assert _jouer(Endpointeur(), [(False, 2000)]) == []


def test_une_parole_assez_longue_produit_un_debut():
    assert _jouer(Endpointeur(), [(True, 300)]) == ["debut"]


def test_une_parole_trop_courte_est_ignoree():
    assert _jouer(Endpointeur(parole_min_ms=200), [(True, 100), (False, 1000)]) == []


def test_un_silence_apres_la_parole_produit_une_fin():
    assert _jouer(Endpointeur(), [(True, 300), (False, 500)]) == ["debut", "fin"]


def test_un_silence_trop_court_ne_coupe_pas():
    motif = [(True, 300), (False, 200), (True, 300), (False, 500)]
    assert _jouer(Endpointeur(silence_ms=400), motif) == ["debut", "fin"]


def test_deux_phrases_separees_produisent_deux_cycles():
    motif = [(True, 300), (False, 500), (True, 300), (False, 500)]
    assert _jouer(Endpointeur(), motif) == ["debut", "fin", "debut", "fin"]


def test_reinitialiser_oublie_l_etat():
    e = Endpointeur()
    _jouer(e, [(True, 300)])
    e.reinitialiser()
    assert _jouer(e, [(False, 1000)]) == []


def test_verifier_bloc_accepte_640_octets():
    bloc_correct = b"\x00" * 640
    verifier_bloc(bloc_correct)  # Ne doit pas lever


def test_verifier_bloc_refuse_100_octets():
    bloc_mauvais = b"\x00" * 100
    with pytest.raises(ValueError):
        verifier_bloc(bloc_mauvais)
