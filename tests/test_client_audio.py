import asyncio

from helios_audio.client import ClientAudio
from helios_core.protocole import (
    Dire,
    Etat,
    FinEnonce,
    Interruption,
    StopAudio,
    decoder_audio_entrant,
    encoder_audio_sortant,
)

BLOC = b"\x00" * 640


class FauxTransport:
    def __init__(self) -> None:
        self.json: list = []
        self.binaire: list[bytes] = []

    async def envoyer_json(self, msg) -> None:
        self.json.append(msg)

    async def envoyer_binaire(self, trame: bytes) -> None:
        self.binaire.append(trame)

    def types(self) -> list[str]:
        return [m.type for m in self.json]


class FauxPeripherique:
    def __init__(self, blocs: list[bytes]) -> None:
        self._blocs = list(blocs)
        self.joues: list[bytes] = []
        self.vidages = 0

    async def lire_bloc(self) -> bytes:
        if not self._blocs:
            raise asyncio.CancelledError
        return self._blocs.pop(0)

    async def jouer(self, pcm: bytes) -> None:
        self.joues.append(pcm)

    async def vider(self) -> None:
        self.vidages += 1

    async def fermer(self) -> None:
        pass


class DetecteurScript:
    """Rend les valeurs d'une liste, puis False."""

    def __init__(self, suite: list[bool]) -> None:
        self._suite = list(suite)

    def parle(self, bloc: bytes) -> bool:
        return self._suite.pop(0) if self._suite else False


class ReveilleurScript:
    def __init__(self, a_declencher_au_bloc: int | None = 0) -> None:
        self._cible = a_declencher_au_bloc
        self._n = -1

    def examiner(self, bloc: bytes) -> bool:
        self._n += 1
        return self._n == self._cible


def _client(transport, peripherique, parole: list[bool], reveil_au=0):
    from helios_audio.vad import Endpointeur

    return ClientAudio(
        transport=transport,
        peripherique=peripherique,
        detecteur=DetecteurScript(parole),
        endpointeur=Endpointeur(silence_ms=60, parole_min_ms=40),
        reveilleur=ReveilleurScript(reveil_au),
        bargein=Endpointeur(silence_ms=60, parole_min_ms=40),
    )


async def test_le_reveil_est_annonce_puis_l_audio_part():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 6)
    c = _client(t, p, parole=[True] * 6)
    await c.boucle_capture()

    assert t.types()[0] == "reveil"
    assert len(t.binaire) == 5, "le bloc du réveil n'est pas envoyé, les suivants oui"
    assert decoder_audio_entrant(t.binaire[0]) == BLOC


async def test_le_silence_declenche_la_fin_d_enonce():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 10)
    c = _client(t, p, parole=[True] * 4 + [False] * 6)
    await c.boucle_capture()

    assert any(isinstance(m, FinEnonce) for m in t.json)


async def test_avant_le_reveil_rien_ne_part():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 4)
    c = _client(t, p, parole=[True] * 4, reveil_au=None)
    await c.boucle_capture()

    assert t.json == [] and t.binaire == []


async def test_l_audio_recu_est_joue():
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[])
    await c.sur_message(Dire(id_enonce=1, rang=1, texte="Bonjour."))
    await c.sur_trame(encoder_audio_sortant(1, BLOC))
    assert p.joues == [BLOC]


async def test_un_stop_audio_vide_le_peripherique():
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[])
    await c.sur_message(StopAudio(id_enonce=1))
    assert p.vidages == 1


async def test_une_trame_perimee_n_est_pas_jouee():
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[])
    await c.sur_message(Dire(id_enonce=2, rang=1, texte="Deux."))
    await c.sur_trame(encoder_audio_sortant(1, BLOC))  # énoncé précédent
    assert p.joues == []


async def test_parler_pendant_la_parole_declenche_l_interruption():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=None)
    await c.sur_message(Etat(valeur="parole"))
    await c.boucle_capture()

    assert any(isinstance(m, Interruption) for m in t.json)
    assert p.vidages >= 1
