"""La voix d'une page : le Core écoute pour elle.

Une page qui allume son micro n'est qu'un terminal audio : elle envoie ses blocs de micro
par /ws/voix et joue le son qui lui revient. Le Core fait tourner pour elle le client
audio du Mac (`ClientAudio`) — mot de réveil, détection de voix, fin de phrase, coupure de
parole, relance —, branché en mémoire à sa propre `Session`. Le client reçoit la session
exactement comme il reçoit le Core sur le Mac, par `servir_connexion`.
"""

from __future__ import annotations

import asyncio
import os
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from atlas_audio.client import ClientAudio, Reglages
from atlas_audio.connexion import servir_connexion
from atlas_audio.reveilleur import PredicteurOpenWakeWord, Reveilleur, ReveilleurMotCle
from atlas_audio.vad import CHEMIN_MODELE, DetecteurVoix, Endpointeur

from .protocole import decoder_audio_entrant
from .protocole_voix import Vider

# Spike S4 : l'annuleur d'écho d'un navigateur laisse passer l'écho le temps de
# s'installer (0,7 s sur iOS, 7 à 10 s dans Chrome sur macOS).
AMORCAGE_S = 10.0
# Au plus 5 s de micro en attente : si le Core prend du retard, les plus vieux blocs se
# perdent plutôt que de s'accumuler.
FILE_MAX_BLOCS = 250


def charger_modeles(seuil_reveil: float) -> tuple[DetecteurVoix, ReveilleurMotCle]:
    """Silero et « Hey Atlas », propres à une page (ils gardent un état). Près d'une
    seconde la première fois : le Core les charge hors de sa boucle."""
    if not os.path.isfile(CHEMIN_MODELE):
        raise FileNotFoundError(
            f"Modèle Silero introuvable sur la machine du Core : {CHEMIN_MODELE} "
            "(voir scripts/neo/LISEZMOI.md)."
        )
    mot_cle = ReveilleurMotCle(PredicteurOpenWakeWord(), seuil=seuil_reveil)
    return DetecteurVoix(chemin=CHEMIN_MODELE), mot_cle


class PeripheriqueNavigateur:
    """Le périphérique audio du client, quand c'est une page : le micro arrive par
    /ws/voix (`recevoir`), le son y repart (`jouer`, `vider`)."""

    def __init__(
        self,
        envoyer_json: Callable[[object], Awaitable[None]],
        envoyer_binaire: Callable[[bytes], Awaitable[None]],
    ) -> None:
        self._envoyer_json = envoyer_json
        self._envoyer_binaire = envoyer_binaire
        self._blocs: deque[bytes] = deque(maxlen=FILE_MAX_BLOCS)
        self._arrivee = asyncio.Event()

    def recevoir(self, bloc: bytes) -> None:
        self._blocs.append(bloc)
        self._arrivee.set()

    async def lire_bloc(self) -> bytes:
        while not self._blocs:
            self._arrivee.clear()
            await self._arrivee.wait()
        return self._blocs.popleft()

    async def jouer(self, pcm: bytes) -> None:
        await self._envoyer_binaire(pcm)

    async def vider(self) -> None:
        await self._envoyer_json(Vider())


class ReveilleurPage:
    """« Hey Atlas » pour une page, si son interrupteur est allumé. Toucher l'orbe ne
    passe pas par ici, mais par `ClientAudio.demander_la_parole`."""

    def __init__(self, mot_cle: Reveilleur, actif: bool) -> None:
        self._mot_cle = mot_cle
        self.actif = actif

    def examiner(self, bloc: bytes) -> bool:
        return self.actif and self._mot_cle.examiner(bloc)


class TransportSession:
    """Ce que le client de la page envoie « au Core » arrive directement dans sa session."""

    def __init__(self, session) -> None:
        self._session = session

    async def envoyer_json(self, msg) -> None:
        await self._session.sur_message(msg)

    async def envoyer_binaire(self, trame: bytes) -> None:
        await self._session.sur_audio(decoder_audio_entrant(trame))


class FluxSession:
    """Ce que la session envoie à son client, en file, lu comme le flux d'une WebSocket :
    `servir_connexion` en garde l'ordre, et fait passer `StopAudio` devant."""

    def __init__(self) -> None:
        self._file: asyncio.Queue[str | bytes] = asyncio.Queue()

    async def envoyer_json(self, msg) -> None:
        self._file.put_nowait(msg.model_dump_json())

    async def envoyer_binaire(self, trame: bytes) -> None:
        self._file.put_nowait(trame)

    def __aiter__(self) -> FluxSession:
        return self

    async def __anext__(self) -> str | bytes:
        return await self._file.get()


@dataclass
class PageVoix:
    peripherique: PeripheriqueNavigateur
    reveilleur: ReveilleurPage
    client: ClientAudio
    session: object
    flux: FluxSession

    async def servir(self) -> None:
        """Fait tourner le client de la page jusqu'à ce qu'on l'annule."""
        await servir_connexion(self.flux, self.client)


def monter_page(
    envoyer_json: Callable[[object], Awaitable[None]],
    envoyer_binaire: Callable[[bytes], Awaitable[None]],
    fabrique_session: Callable[..., object],
    modeles: tuple[object, Reveilleur],
    reglages: Reglages,
    marge_sortie_s: float,
    hey_atlas: bool,
    horloge: Callable[[], float] | None = None,
    attendre: Callable[[float], Awaitable[None]] | None = None,
) -> PageVoix:
    """Le client audio d'une page et sa session. `envoyer_json` et `envoyer_binaire`
    parlent à la page ; `fabrique_session` reçoit les deux fonctions par lesquelles la
    session parle à son client."""
    detecteur, mot_cle = modeles
    flux = FluxSession()
    session = fabrique_session(flux.envoyer_json, flux.envoyer_binaire)
    peripherique = PeripheriqueNavigateur(envoyer_json, envoyer_binaire)
    reveilleur = ReveilleurPage(mot_cle, hey_atlas)
    client = ClientAudio(
        transport=TransportSession(session),
        peripherique=peripherique,
        detecteur=detecteur,
        endpointeur=Endpointeur(silence_ms=reglages.silence_ms),
        reveilleur=reveilleur,
        bargein=Endpointeur(parole_min_ms=reglages.bargein_ms),
        horloge=horloge,
        seuil_bargein_dbfs=reglages.bargein_dbfs,
        relance_s=reglages.relance_s,
        attendre=attendre,
        marge_sortie_s=marge_sortie_s,
        amorcage_s=AMORCAGE_S,
    )
    return PageVoix(peripherique, reveilleur, client, session, flux)
