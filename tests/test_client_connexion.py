"""Le client audio face aux longues réponses et aux coupures : lecture cadencée, connexion
servie, reconnexion."""

import asyncio
import logging

import pytest
from test_client_audio import (
    BLOC,
    BLOC_FORT,
    FausseHorloge,
    FauxPeripherique,
    FauxTransport,
    _client,
)
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from atlas_audio.client import AVANCE_MAX_S, DUREE_BLOC_S
from atlas_audio.connexion import boucle_de_connexion, servir_connexion
from atlas_core.protocole import Dire, Interruption, Reveil, StopAudio, encoder_audio_sortant


def _dire(id_enonce: int = 1) -> Dire:
    return Dire(id_enonce=id_enonce, rang=1, texte="Une longue réponse.")


def _trame(id_enonce: int = 1) -> bytes:
    return encoder_audio_sortant(id_enonce, BLOC)


class PeripheriqueDate(FauxPeripherique):
    """Note l'heure de chaque écriture vers le haut-parleur."""

    def __init__(self, horloge: FausseHorloge) -> None:
        super().__init__([])
        self.horloge = horloge
        self.instants: list[float] = []

    async def jouer(self, pcm: bytes) -> None:
        await super().jouer(pcm)
        self.instants.append(self.horloge.t)


# --- la lecture cadencée ----------------------------------------------------------


async def test_la_lecture_ne_prend_jamais_plus_de_cinq_secondes_d_avance():
    h = FausseHorloge()
    depart = h.t
    attentes: list[float] = []

    async def attendre(secondes: float) -> None:
        attentes.append(secondes)
        h.avancer(secondes)

    t, p = FauxTransport(), PeripheriqueDate(h)
    c = _client(t, p, parole=[], horloge=h, attendre=attendre)
    await c.sur_message(_dire())
    for _ in range(400):  # huit secondes de réponse, livrées d'un coup
        await c.sur_trame(_trame())

    assert len(p.joues) == 400
    assert attentes, "au-delà de cinq secondes d'avance, la lecture attend"
    for rang, instant in enumerate(p.instants):
        # La trame n° rang commence à jouer à depart + rang × 20 ms : elle ne part pas
        # plus de cinq secondes avant.
        assert instant >= depart + rang * DUREE_BLOC_S - AVANCE_MAX_S - 1e-9


async def test_une_coupure_pendant_l_attente_jette_la_trame():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([])

    async def attendre(secondes: float) -> None:
        await c.sur_message(StopAudio(id_enonce=1))  # arrivé pendant l'attente
        h.avancer(secondes)

    c = _client(t, p, parole=[], horloge=h, attendre=attendre)
    await c.sur_message(_dire())
    for _ in range(251):
        await c.sur_trame(_trame())

    assert len(p.joues) == 250, "la trame qui attendait n'est jamais jouée"
    assert p.vidages == 1


class PeripheriqueCoupeEnEcrivant(FauxPeripherique):
    """Le Core coupe la réponse pendant que la première trame s'écrit."""

    client = None

    async def jouer(self, pcm: bytes) -> None:
        await super().jouer(pcm)
        await self.client.sur_message(StopAudio(id_enonce=1))


async def test_une_coupure_pendant_l_ecriture_n_arme_pas_le_bargein():
    h = FausseHorloge()
    t, p = FauxTransport(), PeripheriqueCoupeEnEcrivant([BLOC_FORT] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=0, horloge=h)
    p.client = c
    await c.sur_message(_dire())
    await c.sur_trame(_trame())

    await c.boucle_capture()

    assert not any(isinstance(m, Interruption) for m in t.json)
    assert isinstance(t.json[0], Reveil), "l'horloge de lecture n'a pas avancé pour rien"


# --- la connexion servie ---------------------------------------------------------------


class FauxWs:
    """Rejoue ce que le Core envoie ; un `asyncio.Event` dans la suite fait attendre."""

    def __init__(self, *etapes) -> None:
        self.etapes = etapes

    def __aiter__(self):
        return self._flux()

    async def _flux(self):
        for etape in self.etapes:
            if isinstance(etape, asyncio.Event):
                await etape.wait()
                continue
            yield etape
            await asyncio.sleep(0)


async def test_un_stop_audio_passe_devant_le_son_en_attente():
    h = FausseHorloge()
    en_attente, jamais = asyncio.Event(), asyncio.Event()

    async def attendre(_secondes: float) -> None:
        en_attente.set()
        await jamais.wait()  # le haut-parleur a cinq secondes d'avance : on patiente

    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[], horloge=h, attendre=attendre)
    ws = FauxWs(
        _dire().model_dump_json(),
        *[_trame()] * 300,
        en_attente,
        StopAudio(id_enonce=1).model_dump_json(),
    )

    await asyncio.wait_for(servir_connexion(ws, c), timeout=2)

    assert len(p.joues) == 250
    assert p.vidages >= 1, "le StopAudio a été traité sans attendre la lecture"


async def test_un_message_illisible_du_core_ne_coupe_pas_la_connexion():
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[])
    ws = FauxWs("pas du json", '{"type":"inconnu"}', _dire().model_dump_json(), _trame())

    await asyncio.wait_for(servir_connexion(ws, c), timeout=2)

    assert p.joues == [BLOC]


class PeripheriqueSilencieux(FauxPeripherique):
    """Un micro qui ne livre jamais rien : la capture reste en attente."""

    async def lire_bloc(self) -> bytes:
        await asyncio.Event().wait()
        return b""


async def test_la_fin_de_la_connexion_arrete_le_son_et_ses_taches():
    t, p = FauxTransport(), PeripheriqueSilencieux([])
    c = _client(t, p, parole=[])

    await asyncio.wait_for(servir_connexion(FauxWs(_dire().model_dump_json()), c), timeout=2)

    assert p.vidages == 1, "le son d'une connexion perdue se tait"
    autres = [x for x in asyncio.all_tasks() if x is not asyncio.current_task()]
    assert all(x.done() for x in autres), "capture et lecture sont arrêtées"


# --- la reconnexion ------------------------------------------------------------------


class Fin(Exception):
    """Arrête la boucle de connexion, qui sinon tourne toujours."""


def _refus(code: int) -> ConnectionClosedError:
    return ConnectionClosedError(Close(code, ""), None)


class Ouverture:
    def __init__(self, scenario) -> None:
        self.scenario = scenario

    async def __aenter__(self):
        if isinstance(self.scenario, OSError):
            raise self.scenario  # le Core ne répond pas
        return self.scenario

    async def __aexit__(self, *exc) -> bool:
        return False


class Core:
    """Chaque ouverture rejoue le scénario suivant : `OSError` à la connexion, ou une
    connexion acceptée que `servir` perd (normalement, ou sur un code de fermeture)."""

    def __init__(self, *scenarios) -> None:
        self.scenarios = list(scenarios)
        self.servies: list = []

    def ouvrir(self) -> Ouverture:
        return Ouverture(self.scenarios.pop(0))

    async def servir(self, ws) -> None:
        self.servies.append(ws)
        if isinstance(ws, Exception):
            raise ws


async def _delais(core: Core, tentatives: int) -> list[float]:
    delais: list[float] = []

    async def attendre(secondes: float) -> None:
        delais.append(secondes)
        if len(delais) == tentatives:
            raise Fin

    with pytest.raises(Fin):
        await boucle_de_connexion(core.ouvrir, core.servir, attendre=attendre)
    return delais


async def test_les_tentatives_s_espacent_jusqu_a_trente_secondes():
    core = Core(*[OSError("refusé")] * 8)
    assert await _delais(core, 8) == [1, 2, 4, 8, 16, 30, 30, 30]


async def test_une_connexion_acceptee_remet_le_compte_a_zero():
    core = Core(OSError(), OSError(), "connexion perdue", OSError())
    assert await _delais(core, 4) == [1, 2, 1, 2]
    assert core.servies == ["connexion perdue"]


async def test_une_cle_refusee_ne_remet_pas_le_compte_a_zero(caplog):
    core = Core(OSError(), _refus(4401), _refus(4401))
    with caplog.at_level(logging.ERROR, logger="atlas_audio.connexion"):
        assert await _delais(core, 3) == [1, 2, 4]
    assert "ATLAS_AUDIO_CLE" in caplog.text


async def test_un_core_sans_cle_est_signale(caplog):
    with caplog.at_level(logging.ERROR, logger="atlas_audio.connexion"):
        await _delais(Core(_refus(4000)), 1)
    assert "ATLAS_AUDIO_CLE" in caplog.text and "son .env" in caplog.text


async def test_une_connexion_perdue_en_route_est_retentee():
    core = Core(_refus(1011), "de nouveau là")
    assert await _delais(core, 2) == [1, 1]
    assert len(core.servies) == 2
