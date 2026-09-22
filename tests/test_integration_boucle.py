"""Test d'intégration de la boucle vocale : le vrai client audio branché au vrai Core.

Les revues de tâche ne voyaient chaque composant qu'avec des faux de l'autre côté.
Ce test câble un `ClientAudio` réel à une `Session` réelle par des transports en
mémoire, avec un périphérique dont `jouer` rend la main instantanément — comme le
vrai chemin Swift, qui lit stdin sans freiner — et une horloge qu'on avance à la main.
"""

import asyncio
from collections.abc import AsyncIterator

from pydantic import TypeAdapter

from atlas_audio.client import ClientAudio
from atlas_audio.vad import Endpointeur
from atlas_core.protocole import (
    DUREE_BLOC_MS,
    Etat,
    Interruption,
    MessageCore,
    decoder_audio_entrant,
    decoder_message,
)
from atlas_core.session import Session

SILENCE = b"\x00" * 640
PAROLE = b"\x01" * 640
BLOCS_PAR_PHRASE = 50  # une seconde d'audio par phrase

_adaptateur_core = TypeAdapter(MessageCore)


class FausseHorloge:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def avancer(self, secondes: float) -> None:
        self.t += secondes


class PeripheriqueInstantane:
    """Joue sans attendre ; chaque bloc lu au micro fait avancer l'horloge de 20 ms."""

    def __init__(self, horloge: FausseHorloge) -> None:
        self._horloge = horloge
        self._blocs: list[bytes] = []
        self.joues = 0
        self.vidages = 0

    def ajouter(self, blocs: list[bytes]) -> None:
        self._blocs.extend(blocs)

    async def lire_bloc(self) -> bytes:
        if not self._blocs:
            raise asyncio.CancelledError
        self._horloge.avancer(DUREE_BLOC_MS / 1000)
        return self._blocs.pop(0)

    async def jouer(self, pcm: bytes) -> None:
        self.joues += 1

    async def vider(self) -> None:
        self.vidages += 1

    async def fermer(self) -> None:
        pass


class DetecteurParContenu:
    def parle(self, bloc: bytes) -> bool:
        return bloc != SILENCE


class ReveilleurPremierBloc:
    """Se déclenche sur le tout premier bloc examiné, puis plus jamais."""

    def __init__(self) -> None:
        self._n = 0

    def examiner(self, bloc: bytes) -> bool:
        self._n += 1
        return self._n == 1


class FausseTranscription:
    async def transcrire(self, pcm: bytes) -> str:
        return "Raconte-moi quelque chose."


class FausseSynthese:
    async def synthetiser(self, texte: str) -> AsyncIterator[bytes]:
        for _ in range(BLOCS_PAR_PHRASE):
            yield SILENCE


class CerveauBavard:
    async def repondre(self, texte: str) -> AsyncIterator[str]:
        for mot in "Voici une phrase. En voici une autre. Et une troisième.".split(" "):
            yield mot + " "
            await asyncio.sleep(0)


class ClientVersCore:
    """Ce que le client envoie arrive, décodé, dans la session."""

    def __init__(self) -> None:
        self.session: Session | None = None
        self.envoyes: list = []

    async def envoyer_json(self, msg) -> None:
        self.envoyes.append(msg)
        await self.session.sur_message(decoder_message(msg.model_dump_json()))

    async def envoyer_binaire(self, trame: bytes) -> None:
        await self.session.sur_audio(decoder_audio_entrant(trame))


def _boucle():
    horloge = FausseHorloge()
    peripherique = PeripheriqueInstantane(horloge)
    vers_core = ClientVersCore()
    client = ClientAudio(
        transport=vers_core,
        peripherique=peripherique,
        detecteur=DetecteurParContenu(),
        endpointeur=Endpointeur(silence_ms=400, parole_min_ms=200),
        reveilleur=ReveilleurPremierBloc(),
        bargein=Endpointeur(silence_ms=400, parole_min_ms=300),
        horloge=horloge,
    )
    recus: list = []

    async def vers_client_json(msg) -> None:
        recu = _adaptateur_core.validate_json(msg.model_dump_json())
        recus.append(recu)
        await client.sur_message(recu)

    session = Session(
        envoyer_json=vers_client_json,
        envoyer_binaire=client.sur_trame,
        transcription=FausseTranscription(),
        synthese=FausseSynthese(),
        cerveau=CerveauBavard(),
    )
    vers_core.session = session
    return horloge, peripherique, vers_core, client, session, recus


def _etats(recus: list) -> list[str]:
    return [m.valeur for m in recus if isinstance(m, Etat)]


async def _attendre_repos(recus: list) -> None:
    for _ in range(1000):
        if _etats(recus)[-1:] == ["repos"]:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"le Core n'est jamais revenu au repos : {_etats(recus)}")


async def test_le_bargein_reste_arme_tant_que_la_reponse_est_jouee():
    horloge, peripherique, vers_core, client, session, recus = _boucle()

    # Réveil, une demi-seconde de parole, puis le silence qui clôt l'énoncé.
    peripherique.ajouter([SILENCE] + [PAROLE] * 25 + [SILENCE] * 25)
    await client.boucle_capture()
    await _attendre_repos(recus)

    # Le Core a tout envoyé en quelques millisecondes et se dit au repos...
    assert _etats(recus) == ["ecoute", "reflexion", "parole", "repos"]
    assert peripherique.joues == 3 * BLOCS_PAR_PHRASE
    # ... alors que trois secondes d'audio restent à jouer. Une demi-seconde passe.
    horloge.avancer(0.5)

    # L'utilisateur coupe la parole à Atlas pendant 400 ms.
    peripherique.ajouter([PAROLE] * 20)
    await client.boucle_capture()

    assert any(isinstance(m, Interruption) for m in vers_core.envoyes), (
        "la parole de l'utilisateur pendant la lecture n'a pas interrompu Atlas"
    )
    assert peripherique.vidages >= 1
    assert _etats(recus)[-1] == "ecoute"
    await session.fermer()
