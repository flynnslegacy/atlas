"""La voix d'une page, côté Core : ses pièces, puis le vrai client audio branché à une
vraie session, la page étant remplacée par deux listes (ce qu'elle envoie, ce qu'elle
reçoit) et le temps par une horloge qu'on avance à la main."""

import asyncio
import contextlib
import struct
from collections.abc import AsyncIterator
from dataclasses import replace

import pytest

from atlas_audio.client import Reglages
from atlas_core import voix
from atlas_core.diffuseur import Diffuseur
from atlas_core.protocole import Etat, Interruption, Reveil, encoder_audio_entrant
from atlas_core.protocole_voix import Vider
from atlas_core.regie import Regie
from atlas_core.session import Session
from atlas_core.voix import (
    FILE_MAX_BLOCS,
    FluxSession,
    PeripheriqueNavigateur,
    ReveilleurPage,
    TransportSession,
    charger_modeles,
    monter_page,
)

SILENCE = b"\x00" * 640
PAROLE = struct.pack("<h", 8000) * 320  # -12 dBFS : bien au-dessus de la porte de -40 dBFS
REGLAGES = Reglages(
    seuil_reveil=0.5, silence_ms=400, bargein_ms=300, bargein_dbfs=-40.0, relance_s=0.0
)
QUESTION = [PAROLE] * 25 + [SILENCE] * 25  # une demi-seconde de parole, puis le silence


async def _laisser_tourner(tours: int = 30) -> None:
    for _ in range(tours):
        await asyncio.sleep(0)


async def _attendre(condition, message: str) -> None:
    for _ in range(50_000):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError(message)


# --- les pièces -----------------------------------------------------------


class Envois:
    def __init__(self) -> None:
        self.recus: list = []

    async def json(self, msg) -> None:
        self.recus.append(msg)

    async def binaire(self, pcm: bytes) -> None:
        self.recus.append(pcm)


async def test_le_peripherique_rend_les_blocs_de_la_page_dans_l_ordre():
    envois = Envois()
    peripherique = PeripheriqueNavigateur(envois.json, envois.binaire)
    lecture = asyncio.create_task(peripherique.lire_bloc())
    await _laisser_tourner()
    assert not lecture.done()  # rien reçu : il attend
    peripherique.recevoir(b"\x01" * 640)
    peripherique.recevoir(b"\x02" * 640)
    assert await lecture == b"\x01" * 640
    assert await peripherique.lire_bloc() == b"\x02" * 640


async def test_si_le_core_prend_du_retard_les_plus_vieux_blocs_se_perdent():
    peripherique = PeripheriqueNavigateur(Envois().json, Envois().binaire)
    for i in range(FILE_MAX_BLOCS + 10):
        peripherique.recevoir(struct.pack("<h", i) * 320)
    assert await peripherique.lire_bloc() == struct.pack("<h", 10) * 320


async def test_le_peripherique_joue_et_vide_par_la_page():
    envois = Envois()
    peripherique = PeripheriqueNavigateur(envois.json, envois.binaire)
    await peripherique.jouer(b"\x07" * 640)
    await peripherique.vider()
    assert envois.recus == [b"\x07" * 640, Vider()]


class MotCleEspion:
    """Se déclenche au premier bloc examiné, puis plus jamais."""

    def __init__(self) -> None:
        self.examens = 0

    def examiner(self, bloc: bytes) -> bool:
        self.examens += 1
        return self.examens == 1


def test_interrupteur_eteint_le_mot_de_reveil_n_est_meme_pas_consulte():
    mot_cle = MotCleEspion()
    reveilleur = ReveilleurPage(mot_cle, actif=False)
    assert reveilleur.examiner(SILENCE) is False and mot_cle.examens == 0
    reveilleur.actif = True
    assert reveilleur.examiner(SILENCE) is True and mot_cle.examens == 1


class SessionEspionne:
    def __init__(self) -> None:
        self.messages: list = []
        self.audio: list[bytes] = []

    async def sur_message(self, msg) -> None:
        self.messages.append(msg)

    async def sur_audio(self, pcm: bytes) -> None:
        self.audio.append(pcm)


async def test_le_client_de_la_page_parle_directement_a_sa_session():
    session = SessionEspionne()
    transport = TransportSession(session)
    reveil = Reveil(confiance=1.0, horodatage=0.0)
    await transport.envoyer_json(reveil)
    await transport.envoyer_binaire(encoder_audio_entrant(PAROLE))
    assert session.messages == [reveil] and session.audio == [PAROLE]


async def test_la_session_parle_a_son_client_comme_une_websocket():
    flux = FluxSession()
    await flux.envoyer_json(Etat(valeur="ecoute"))
    await flux.envoyer_binaire(b"\x02trame")
    assert await anext(flux) == Etat(valeur="ecoute").model_dump_json()
    assert await anext(flux) == b"\x02trame"


def test_sans_silero_sur_la_machine_du_core_le_message_le_dit(monkeypatch, tmp_path):
    monkeypatch.setattr(voix, "CHEMIN_MODELE", str(tmp_path / "absent.onnx"))
    with pytest.raises(FileNotFoundError, match="absent.onnx"):
        charger_modeles(0.5)


# --- la page branchée à une vraie session ---------------------------------


class FausseHorloge:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def avancer(self, secondes: float) -> None:
        self.t += secondes


class DetecteurParContenu:
    def parle(self, bloc: bytes) -> bool:
        return bloc != SILENCE


class FausseTranscription:
    def __init__(self) -> None:
        self.appels = 0

    async def transcrire(self, pcm: bytes) -> str:
        self.appels += 1
        return "Raconte-moi quelque chose."


class FausseSynthese:
    def __init__(self, trames_par_phrase: int) -> None:
        self._n = trames_par_phrase

    async def synthetiser(self, texte: str) -> AsyncIterator[bytes]:
        for _ in range(self._n):
            yield SILENCE


class CerveauBavard:
    async def repondre(self, texte: str) -> AsyncIterator[str]:
        for mot in "Voici une phrase. En voici une autre. Et une troisième.".split(" "):
            yield mot + " "
            await asyncio.sleep(0)


class DiffuseurEspion(Diffuseur):
    def __init__(self) -> None:
        super().__init__()
        self.etats: list[str] = []

    def publier(self, msg) -> None:
        if isinstance(msg, Etat):
            self.etats.append(msg.valeur)
        super().publier(msg)


class Banc:
    def __init__(
        self, hey_atlas: bool, trames_par_phrase: int, porte_dbfs: float, relance_s: float
    ) -> None:
        self.horloge = FausseHorloge()
        self.page_recoit = Envois()
        self.mot_cle = MotCleEspion()
        self.transcription = FausseTranscription()
        self.diffuseur = DiffuseurEspion()
        self.interruptions = 0

        def fabrique(envoyer_json, envoyer_binaire) -> Session:
            self.session = Session(
                envoyer_json=envoyer_json,
                envoyer_binaire=envoyer_binaire,
                transcription=self.transcription,
                synthese=FausseSynthese(trames_par_phrase),
                cerveau=CerveauBavard(),
                diffuseur=self.diffuseur,
            )
            sur_message = self.session.sur_message

            async def compter(msg) -> None:
                self.interruptions += isinstance(msg, Interruption)
                await sur_message(msg)

            self.session.sur_message = compter
            return self.session

        async def attendre(secondes: float) -> None:
            self.horloge.avancer(secondes)  # le haut-parleur joue pendant qu'on attend
            await asyncio.sleep(0)

        self.page = monter_page(
            self.page_recoit.json,
            self.page_recoit.binaire,
            fabrique,
            (DetecteurParContenu(), self.mot_cle),
            replace(REGLAGES, bargein_dbfs=porte_dbfs, relance_s=relance_s),
            marge_sortie_s=0.2,
            hey_atlas=hey_atlas,
            horloge=self.horloge,
            attendre=attendre,
        )

    @property
    def trames(self) -> list[bytes]:
        return [m for m in self.page_recoit.recus if isinstance(m, bytes)]

    @property
    def vidages(self) -> int:
        return sum(isinstance(m, Vider) for m in self.page_recoit.recus)

    async def dire(self, blocs: list[bytes]) -> None:
        for bloc in blocs:
            self.page.peripherique.recevoir(bloc)
            self.horloge.avancer(0.02)
            await _laisser_tourner()

    async def attendre_la_reponse(self, trames: int) -> None:
        await _attendre(
            lambda: len(self.trames) == trames,
            f"la page a reçu {len(self.trames)} trames sur {trames}",
        )


@contextlib.asynccontextmanager
async def _banc(
    hey_atlas: bool = False,
    trames_par_phrase: int = 50,
    porte_dbfs: float = -40.0,
    relance_s: float = 0.0,
):
    banc = Banc(hey_atlas, trames_par_phrase, porte_dbfs, relance_s)
    service = asyncio.create_task(banc.page.servir())
    try:
        yield banc
    finally:
        service.cancel()
        await asyncio.wait([service])
        await banc.session.fermer()


async def test_hey_atlas_puis_la_question_la_reponse_sort_de_la_page():
    async with _banc(hey_atlas=True) as banc:
        await banc.dire([SILENCE] + QUESTION)  # le mot de réveil se déclenche au 1er bloc
        await banc.attendre_la_reponse(3 * 50)
        assert banc.transcription.appels == 1
        # La page reçoit du son brut, 20 ms à 16 kHz, sans l'en-tête de /ws/audio.
        assert {len(t) for t in banc.trames} == {640}


async def test_interrupteur_eteint_la_page_ne_se_reveille_jamais_seule():
    async with _banc(hey_atlas=False) as banc:
        await banc.dire([SILENCE] + QUESTION)
        assert banc.mot_cle.examens == 0 and banc.transcription.appels == 0
        assert banc.trames == []


async def test_toucher_l_orbe_au_repos_ouvre_l_ecoute():
    async with _banc(hey_atlas=False) as banc:
        banc.page.client.demander_la_parole()
        await banc.dire(QUESTION)
        await banc.attendre_la_reponse(3 * 50)
        assert banc.transcription.appels == 1


async def test_une_question_tapee_repond_sur_la_page():
    async with _banc() as banc:
        await banc.session.sur_saisie("Raconte-moi quelque chose.")
        await banc.attendre_la_reponse(3 * 50)


async def test_toucher_l_orbe_coupe_atlas_meme_pendant_l_amorcage():
    async with _banc(hey_atlas=True) as banc:
        await banc.dire([SILENCE] + QUESTION)
        await banc.attendre_la_reponse(3 * 50)
        await banc.dire([PAROLE] * 20)  # l'annuleur s'installe : la voix ne coupe pas
        assert banc.vidages == 0 and banc.interruptions == 0
        banc.page.client.demander_la_parole()
        await banc.dire([PAROLE])
        # La page vide son son deux fois, comme le Mac : à la coupure, puis au StopAudio
        # de la session.
        assert banc.vidages >= 1 and banc.interruptions == 1
        assert banc.diffuseur.etats[-1] == "ecoute"


@pytest.mark.parametrize(("porte_dbfs", "coupe"), [(-40.0, True), (-10.0, False)])
async def test_la_voix_coupe_atlas_une_fois_passees_dix_secondes_de_sa_voix(porte_dbfs, coupe):
    # À -10 dBFS, la porte d'énergie de la page arrête une voix à -12 dBFS.
    async with _banc(hey_atlas=True, trames_par_phrase=200, porte_dbfs=porte_dbfs) as banc:
        await banc.dire([SILENCE] + QUESTION)
        # 12 s de voix, confiées à la page avec 5 s d'avance au plus : la dernière trame
        # partie, Atlas en est à 7 s de voix jouée.
        await banc.attendre_la_reponse(3 * 200)
        await banc.dire([PAROLE] * 20)  # à 7,4 s : l'annuleur s'installe encore
        assert banc.vidages == 0 and banc.interruptions == 0
        banc.horloge.avancer(2.8)  # à 10,2 s : Atlas parle toujours, l'amorçage est fini
        await banc.dire([PAROLE] * 20)
        assert banc.interruptions == (1 if coupe else 0)


async def test_apres_sa_reponse_la_page_ecoute_encore_sans_hey_atlas():
    async with _banc(hey_atlas=False, relance_s=10.0) as banc:
        banc.page.client.demander_la_parole()
        await banc.dire(QUESTION)
        await banc.attendre_la_reponse(3 * 50)
        await _laisser_tourner()
        banc.horloge.avancer(3.5)  # la réponse a fini de jouer sur la page
        await banc.dire(QUESTION)  # la question suivante, sans mot de réveil ni toucher
        await _attendre(lambda: banc.transcription.appels == 2, "la relance n'a rien entendu")
        assert banc.mot_cle.examens == 0


async def test_le_muet_d_une_page_coupe_la_voix_d_une_autre():
    async with _banc(hey_atlas=True) as banc:
        regie = Regie(Diffuseur(), lambda: None)
        regie.rattacher(banc.session, page="ipad")
        await banc.dire([SILENCE] + QUESTION)
        await banc.attendre_la_reponse(3 * 50)
        await regie.basculer_muet(True)  # touché sur l'iPhone
        await _laisser_tourner()
        assert banc.vidages == 1
