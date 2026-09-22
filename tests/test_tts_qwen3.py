"""Moteur Qwen3-TTS : clonage de la voix d'Atlas, avec un faux modèle (ni GPU, ni qwen_tts)."""

import logging
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from atlas_core.config import Config
from services.tts import serveur
from services.tts.serveur import (
    TAILLE_MORCEAU,
    MoteurPiper,
    MoteurQwen3,
    app,
    nom_moteur_choisi,
    obtenir_moteur,
    voix_par_defaut,
)

FREQUENCE_QWEN = 24000
TEXTE_REFERENCE = "Bonjour, je m'appelle Atlas. Je suis là pour t'aider."
VOIX_DU_DEPOT = Path(__file__).parent.parent / "services" / "tts" / "voix"


def plafond_attendu(texte: str) -> float:
    """Plafond fixé par le verdict du spike S1 : 2,5 fois 0,06 s par caractère."""
    return max(4.0, len(texte) * 0.06 * 2.5)


def parole(duree_s: float) -> np.ndarray:
    """Un son continu non nul, qui tient lieu de parole."""
    t = np.arange(int(duree_s * FREQUENCE_QWEN)) / FREQUENCE_QWEN
    return (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


class FauxModele:
    """Imite Qwen3TTSModel : enregistre ses appels et rend l'audio qu'on lui confie."""

    def __init__(self, audio: np.ndarray | None = None) -> None:
        self.audio = parole(1.0) if audio is None else audio
        self.empreinte = object()
        self.appels_empreinte = 0
        self.ref_text: str | None = None
        self.ref_audio = None
        self.x_vector_only_mode = None
        self.generations: list[dict] = []
        self.en_cours = 0
        self.chevauchement_max = 0
        self.duree_generation_s = 0.0

    def create_voice_clone_prompt(self, ref_audio, ref_text, x_vector_only_mode):
        self.appels_empreinte += 1
        self.ref_audio = ref_audio
        self.ref_text = ref_text
        self.x_vector_only_mode = x_vector_only_mode
        return self.empreinte

    def generate_voice_clone(self, **kwargs):
        self.en_cours += 1
        self.chevauchement_max = max(self.chevauchement_max, self.en_cours)
        time.sleep(self.duree_generation_s)
        self.generations.append(kwargs)
        self.en_cours -= 1
        return [self.audio.copy()], FREQUENCE_QWEN


class FauxChargeur:
    def __init__(self, modele: FauxModele, lenteur_s: float = 0.0) -> None:
        self.modele = modele
        self.lenteur_s = lenteur_s
        self.appels: list[str] = []

    def __call__(self, nom_modele: str) -> FauxModele:
        self.appels.append(nom_modele)
        time.sleep(self.lenteur_s)
        return self.modele


@pytest.fixture
def dossier_voix(tmp_path):
    sf.write(tmp_path / "atlas_reference.wav", parole(0.5), FREQUENCE_QWEN)
    # Des blancs autour, comme un éditeur les laisse : le texte doit en être débarrassé.
    (tmp_path / "atlas_reference.txt").write_text(f"  {TEXTE_REFERENCE}\n", encoding="utf-8")
    return tmp_path


def moteur_avec(dossier, modele: FauxModele, lenteur_s: float = 0.0):
    chargeur = FauxChargeur(modele, lenteur_s)
    return MoteurQwen3(dossier_voix=str(dossier), charger=chargeur), chargeur


def tout_synthetiser(moteur: MoteurQwen3, texte: str = "Bonjour David.") -> list[bytes]:
    return list(moteur.synthetiser(texte, "atlas_reference"))


# 1. verifier


def test_verifier_nomme_le_wav_absent(dossier_voix):
    (dossier_voix / "atlas_reference.wav").unlink()
    moteur, _ = moteur_avec(dossier_voix, FauxModele())

    with pytest.raises(FileNotFoundError, match="atlas_reference.wav"):
        moteur.verifier("atlas_reference")


def test_verifier_nomme_le_texte_absent(dossier_voix):
    (dossier_voix / "atlas_reference.txt").unlink()
    moteur, _ = moteur_avec(dossier_voix, FauxModele())

    with pytest.raises(FileNotFoundError, match="atlas_reference.txt"):
        moteur.verifier("atlas_reference")


def test_verifier_une_voix_complete_ne_charge_pas_le_modele(dossier_voix):
    moteur, chargeur = moteur_avec(dossier_voix, FauxModele())

    moteur.verifier("atlas_reference")

    assert chargeur.appels == []


# 2. chargement paresseux, une seule fois


def test_la_construction_ne_charge_pas_le_modele(dossier_voix):
    _, chargeur = moteur_avec(dossier_voix, FauxModele())

    assert chargeur.appels == []


def test_deux_syntheses_chargent_le_modele_une_seule_fois(dossier_voix):
    moteur, chargeur = moteur_avec(dossier_voix, FauxModele())

    tout_synthetiser(moteur)
    assert chargeur.appels == ["Qwen/Qwen3-TTS-12Hz-1.7B-Base"]
    tout_synthetiser(moteur)
    assert chargeur.appels == ["Qwen/Qwen3-TTS-12Hz-1.7B-Base"]


def test_des_syntheses_simultanees_chargent_une_fois_et_ne_generent_jamais_en_parallele(
    dossier_voix,
):
    modele = FauxModele()
    modele.duree_generation_s = 0.02
    moteur, chargeur = moteur_avec(dossier_voix, modele, lenteur_s=0.05)

    fils = [threading.Thread(target=tout_synthetiser, args=(moteur,)) for _ in range(4)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join(timeout=5)

    assert not any(fil.is_alive() for fil in fils)
    assert len(chargeur.appels) == 1
    assert modele.appels_empreinte == 1
    assert len(modele.generations) == 4
    assert modele.chevauchement_max == 1


def test_la_synthese_travaille_des_l_appel_avant_toute_lecture(dossier_voix):
    # Tout se fait avant que la route ne réponde : un échec y devient un 503.
    modele = FauxModele()
    moteur, chargeur = moteur_avec(dossier_voix, modele)

    moteur.synthetiser("Bonjour David.", "atlas_reference")

    assert len(chargeur.appels) == 1
    assert len(modele.generations) == 1


def test_le_moteur_est_libre_des_que_la_synthese_est_rendue(dossier_voix):
    # Le client HTTP se déconnecte en pleine phrase : les blocs restants sont abandonnés
    # sans être lus. Le verrou, lui, a été rendu avant le premier bloc.
    moteur, _ = moteur_avec(dossier_voix, FauxModele())
    blocs = moteur.synthetiser("Bonjour David.", "atlas_reference")
    next(blocs)

    suivante = threading.Thread(target=tout_synthetiser, args=(moteur,), daemon=True)
    suivante.start()
    suivante.join(timeout=5)

    assert not suivante.is_alive()


# 3. empreinte de la voix : une fois, avec le texte exact


def test_l_empreinte_est_calculee_une_fois_avec_le_texte_exact_de_la_reference(dossier_voix):
    # Régression du spike S1 : si le texte en dit plus que l'audio, chaque phrase générée
    # commence par les mots manquants.
    modele = FauxModele()
    moteur, _ = moteur_avec(dossier_voix, modele)

    for _ in range(3):
        tout_synthetiser(moteur)

    assert modele.appels_empreinte == 1
    assert modele.ref_text == TEXTE_REFERENCE
    assert modele.x_vector_only_mode is False
    audio, frequence = modele.ref_audio
    attendu, _ = sf.read(dossier_voix / "atlas_reference.wav", dtype="float32")
    assert frequence == FREQUENCE_QWEN
    assert audio.dtype == np.float32
    np.testing.assert_array_equal(audio, attendu)


def test_le_prechauffage_charge_le_modele_et_l_empreinte_d_avance(dossier_voix):
    modele = FauxModele()
    moteur, chargeur = moteur_avec(dossier_voix, modele)

    moteur.prechauffer("atlas_reference")
    assert len(chargeur.appels) == 1 and modele.appels_empreinte == 1
    assert modele.generations == []

    tout_synthetiser(moteur)
    assert len(chargeur.appels) == 1 and modele.appels_empreinte == 1


# 4. appel de génération


@pytest.mark.parametrize(
    "texte",
    [
        "Bonjour David.",
        "Le workflow « Veille concurrence » a échoué à 3 heures du matin. "
        "Erreur d'authentification sur l'API. Tu veux que je relance la tâche maintenant ?",
    ],
)
def test_la_generation_recoit_le_francais_l_empreinte_et_un_plafond_de_jetons_large(
    dossier_voix, texte
):
    modele = FauxModele()
    moteur, _ = moteur_avec(dossier_voix, modele)

    list(moteur.synthetiser(texte, "atlas_reference"))

    (appel,) = modele.generations
    assert appel["text"] == texte
    assert appel["language"] == "French"
    assert appel["voice_clone_prompt"] is modele.empreinte
    # 12 jetons/s : la cadence nominale du codec. Le plafond doit rester au-dessus même
    # de cette lecture pessimiste, pour ne jamais couper une phrase normale.
    assert appel["max_new_tokens"] >= plafond_attendu(texte) * 12


# 5. rééchantillonnage et blocs


def test_une_seconde_a_24_khz_donne_une_seconde_a_16_khz_en_blocs_exacts(dossier_voix):
    moteur, _ = moteur_avec(dossier_voix, FauxModele(parole(1.0)))

    blocs = tout_synthetiser(moteur)

    assert all(len(bloc) == TAILLE_MORCEAU for bloc in blocs)
    assert abs(sum(len(bloc) for bloc in blocs) - 16000 * 2) <= TAILLE_MORCEAU


def test_un_bloc_final_incomplet_est_complete_au_silence(dossier_voix):
    # 1,01 s : 16 160 échantillons à 16 kHz, soit 50 blocs et un reste de 320 octets.
    moteur, _ = moteur_avec(dossier_voix, FauxModele(parole(1.01)))

    blocs = tout_synthetiser(moteur)

    assert all(len(bloc) == TAILLE_MORCEAU for bloc in blocs)
    assert len(blocs) == 51
    assert blocs[-1][320:] == b"\x00" * 320


# 6. seul garde-fou : le plafond de durée


def test_une_generation_qui_boucle_est_coupee_au_plafond_avec_un_avertissement(
    dossier_voix, caplog
):
    texte = "Bonjour David."
    moteur, _ = moteur_avec(dossier_voix, FauxModele(parole(60.0)))

    with caplog.at_level(logging.WARNING, logger=serveur._journal.name):
        blocs = tout_synthetiser(moteur, texte)

    total = sum(len(bloc) for bloc in blocs)
    assert abs(total - plafond_attendu(texte) * 16000 * 2) <= TAILLE_MORCEAU
    avertissements = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(avertissements) == 1


# 7. jamais de coupe sur un silence


def test_un_silence_au_milieu_de_la_phrase_ne_coupe_rien(dossier_voix):
    # Régression du spike S1 : la coupe au premier long silence a amputé de vraie parole
    # 3 fois sur 11. Parole, 1 s de silence, parole : tout doit ressortir.
    audio = np.concatenate([parole(1.0), np.zeros(FREQUENCE_QWEN, np.float32), parole(1.0)])
    moteur, _ = moteur_avec(dossier_voix, FauxModele(audio))

    blocs = tout_synthetiser(moteur)

    pcm = np.frombuffer(b"".join(blocs), dtype="<i2")
    assert abs(len(pcm) - 3 * 16000) <= TAILLE_MORCEAU // 2
    # La parole d'après le silence est bien là.
    assert np.abs(pcm[int(2.2 * 16000) : int(2.8 * 16000)]).max() > 1000


# 8. voix par défaut propre à chaque moteur


def test_sans_voix_imposee_qwen3_prend_la_voix_d_atlas():
    assert voix_par_defaut(MoteurQwen3(), {}) == "atlas_reference"


def test_sans_voix_imposee_piper_prend_siwis():
    assert voix_par_defaut(MoteurPiper(), {}) == "fr_FR-siwis-medium"


def test_une_voix_imposee_vide_laisse_le_moteur_choisir():
    assert voix_par_defaut(MoteurQwen3(), {"ATLAS_TTS_VOIX": ""}) == "atlas_reference"


def test_la_voix_imposee_par_l_environnement_l_emporte_sur_celle_du_moteur():
    environ = {"ATLAS_TTS_VOIX": "autre_voix"}
    assert voix_par_defaut(MoteurQwen3(), environ) == "autre_voix"
    assert voix_par_defaut(MoteurPiper(), environ) == "autre_voix"


def test_le_moteur_par_defaut_est_qwen3_et_il_est_enregistre():
    assert nom_moteur_choisi({}) == "qwen3"
    assert nom_moteur_choisi({"ATLAS_TTS_MOTEUR": "piper"}) == "piper"
    assert isinstance(serveur._moteurs["qwen3"], MoteurQwen3)
    assert isinstance(serveur._moteurs["piper"], MoteurPiper)


def test_piper_sans_voix_demandee_prend_sa_propre_voix(monkeypatch, tmp_path):
    monkeypatch.delenv("ATLAS_TTS_VOIX", raising=False)

    with pytest.raises(FileNotFoundError, match="fr_FR-siwis-medium.onnx"):
        MoteurPiper(dossier_modeles=str(tmp_path)).verifier("")


class MoteurEspion:
    nom = "espion"
    voix_defaut = "voix_du_moteur"

    def __init__(self) -> None:
        self.voix_verifiees: list[str] = []

    def verifier(self, voix: str) -> None:
        self.voix_verifiees.append(voix)

    def synthetiser(self, texte: str, voix: str):
        yield b"\x00" * TAILLE_MORCEAU


@pytest.mark.parametrize(
    ("demandee", "imposee", "attendue"),
    [
        ("explicite", "imposee", "explicite"),
        ("explicite", None, "explicite"),
        ("", "imposee", "imposee"),
        ("", None, "voix_du_moteur"),
    ],
)
def test_la_route_choisit_la_voix_demandee_puis_imposee_puis_celle_du_moteur(
    monkeypatch, demandee, imposee, attendue
):
    if imposee is None:
        monkeypatch.delenv("ATLAS_TTS_VOIX", raising=False)
    else:
        monkeypatch.setenv("ATLAS_TTS_VOIX", imposee)
    espion = MoteurEspion()
    app.dependency_overrides[obtenir_moteur] = lambda: espion
    try:
        r = TestClient(app).post("/synthesize", json={"text": "Bonjour.", "voice": demandee})
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    assert espion.voix_verifiees == [attendue]


def test_le_core_n_impose_plus_de_voix_par_defaut(monkeypatch):
    monkeypatch.delenv("ATLAS_TTS_VOIX", raising=False)

    assert Config.depuis_environnement().tts_voix == ""


# 9. route : une voix absente est une erreur 500 avant le flux


def test_la_route_rend_500_en_nommant_le_fichier_de_voix_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("ATLAS_TTS_VOIX", raising=False)
    chargeur = FauxChargeur(FauxModele())
    app.dependency_overrides[obtenir_moteur] = lambda: MoteurQwen3(
        dossier_voix=str(tmp_path), charger=chargeur
    )
    try:
        r = TestClient(app).post("/synthesize", json={"text": "Bonjour.", "voice": ""})
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 500
    assert str(tmp_path / "atlas_reference.wav") in r.json()["detail"]
    assert chargeur.appels == []


# 10. la voix d'Atlas versionnée


def test_la_voix_d_atlas_est_versionnee_et_complete():
    wav = VOIX_DU_DEPOT / "atlas_reference.wav"
    txt = VOIX_DU_DEPOT / "atlas_reference.txt"
    assert wav.is_file() and txt.is_file()

    info = sf.info(wav)
    assert info.channels == 1
    assert info.samplerate == FREQUENCE_QWEN
    texte = txt.read_text(encoding="utf-8").strip()
    assert texte
    assert "\n" not in texte
