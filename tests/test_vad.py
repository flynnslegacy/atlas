from pathlib import Path

import numpy as np
import pytest

from atlas_audio.vad import DetecteurVoix, Endpointeur, verifier_bloc

BLOC_MS = 20
_VOIX_ATLAS = Path("services/tts/voix/atlas_reference.wav")
_sans_modele = pytest.mark.skipif(
    not Path("models/silero_vad.onnx").exists(),
    reason="modèle Silero absent de models/ : voir bench/LISEZMOI.md",
)


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


def _blocs_de_la_voix_atlas() -> list[bytes]:
    """La phrase de référence d'Atlas, en blocs de 20 ms à 16 kHz, comme le micro."""
    import soundfile as sf
    import soxr

    audio, sr = sf.read(_VOIX_ATLAS, dtype="float32")
    audio = soxr.resample(audio, sr, 16000)
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    return [pcm[i : i + 640] for i in range(0, len(pcm) - 639, 640)]


@_sans_modele
def test_le_detecteur_reconnait_de_la_vraie_parole():
    # Régression : sans les 64 échantillons de contexte qu'attend Silero v5, le
    # modèle rendait des probabilités proches de zéro, et la parole n'était jamais
    # reconnue — ni la fin des phrases, ni les interruptions.
    detecteur = DetecteurVoix()
    verdicts = [detecteur.parle(bloc) for bloc in _blocs_de_la_voix_atlas()]
    assert sum(verdicts) / len(verdicts) > 0.5


@_sans_modele
def test_la_parole_tient_assez_longtemps_pour_declencher_une_interruption():
    # La coupure exige 300 ms de voix continue, soit 15 blocs de 20 ms.
    detecteur = DetecteurVoix()
    course = plus_longue = 0
    for bloc in _blocs_de_la_voix_atlas():
        course = course + 1 if detecteur.parle(bloc) else 0
        plus_longue = max(plus_longue, course)
    assert plus_longue >= 15


@_sans_modele
def test_le_detecteur_reste_muet_sur_le_silence():
    detecteur = DetecteurVoix()
    assert not any(detecteur.parle(b"\x00" * 640) for _ in range(100))
