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
from atlas_core.protocole import (
    Dire,
    Etat,
    Interruption,
    Reveil,
    StopAudio,
    encoder_audio_sortant,
)


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


async def test_une_coupure_reseau_ne_journalise_pas_la_trace(caplog):
    # Une coupure réseau attendue (le Core disparaît, redémarre…) revient toutes les
    # secondes : la trace complète ne ferait qu'encombrer les journaux pour rien.
    with caplog.at_level(logging.WARNING, logger="atlas_audio.connexion"):
        await _delais(Core(_refus(1011)), 1)
    (enregistrement,) = [r for r in caplog.records if "Core injoignable" in r.getMessage()]
    assert enregistrement.exc_info is None


async def test_une_erreur_inattendue_est_journalisee_avec_sa_trace(caplog):
    # Un bogue du mot de réveil ou du VAD, par exemple : sans la trace, cette erreur se
    # répéterait toutes les secondes sans qu'on sache jamais ce qui l'a déclenchée.
    with caplog.at_level(logging.WARNING, logger="atlas_audio.connexion"):
        await _delais(Core(RuntimeError("bogue du mot de réveil")), 1)
    (enregistrement,) = [r for r in caplog.records if "Core injoignable" in r.getMessage()]
    assert enregistrement.exc_info is not None


# --- fix round 1 : l'ordre des messages, le périphérique mort, l'absence -------------


class _WsSansCeder:
    """Comme `FauxWs`, mais sans jamais rendre la main entre deux éléments (hors
    synchronisation explicite) : comme les vraies websockets, dont l'Assembler rend les
    messages déjà tamponnés d'un coup plutôt qu'un par un."""

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


class _PeripheriqueRelance(FauxPeripherique):
    """Le premier bloc n'arrive qu'une fois `porte` ouverte ; le second bloque sur `fin`."""

    def __init__(self, porte: asyncio.Event, fin: asyncio.Event) -> None:
        super().__init__([])
        self._porte = porte
        self._fin = fin
        self._n = 0

    async def lire_bloc(self) -> bytes:
        self._n += 1
        if self._n == 1:
            await self._porte.wait()
            return BLOC
        await self._fin.wait()
        raise asyncio.CancelledError


class _TransportRelance(FauxTransport):
    """Note combien de trames ont joué au moment du premier `Reveil` envoyé."""

    def __init__(self, peripherique) -> None:
        super().__init__()
        self._peripherique = peripherique
        self.joues_au_reveil: int | None = None

    async def envoyer_json(self, msg) -> None:
        if isinstance(msg, Reveil) and self.joues_au_reveil is None:
            self.joues_au_reveil = len(self._peripherique.joues)
        await super().envoyer_json(msg)


async def test_la_relance_n_arrive_pas_avant_que_la_reponse_ait_joue():
    """Bug (revue, fix round 1) : un `Dire`, ses trames et l'`Etat(repos)` qui suit
    arrivent parfois d'un bloc (comme le fait `websockets` avec des messages déjà
    tamponnés). Si `Dire`/`Etat` sont traités aussitôt pendant que les trames patientent
    encore en file, `boucle_capture` peut s'exécuter entre les deux : la relance ouvre
    alors l'écoute — et envoie un `Reveil` — avant qu'une seule trame de la réponse
    n'ait joué, et le Core perd le sous-titrage de cette phrase."""
    h = FausseHorloge()
    porte, fin = asyncio.Event(), asyncio.Event()
    p = _PeripheriqueRelance(porte, fin)
    t = _TransportRelance(p)
    c = _client(t, p, parole=[], reveil_au=None, horloge=h, relance_s=10.0)
    trames = [_trame()] * 50  # une seconde de réponse, livrée d'un coup
    ws = _WsSansCeder(
        porte,
        _dire().model_dump_json(),
        *trames,
        Etat(valeur="repos").model_dump_json(),
        fin,
    )
    tache = asyncio.create_task(servir_connexion(ws, c))
    for _ in range(3):
        await asyncio.sleep(0)
    porte.set()
    for _ in range(5):
        await asyncio.sleep(0)
    fin.set()
    await asyncio.wait_for(tache, timeout=2)

    assert t.joues_au_reveil is None or t.joues_au_reveil == 50, (
        "la relance (Reveil) est partie avant que la réponse ait fini de jouer"
    )


async def test_un_stop_audio_en_avance_sur_son_dire_empeche_ses_trames_de_jouer():
    """Bug (revue, fix round 1) : un `StopAudio` traité aussitôt peut devancer, dans la
    file, le `Dire` (et les trames) du même énoncé. Sans couper jusqu'à cet énoncé,
    `_couper` ne coupait que jusqu'à `_id_courant` : ce `Dire` arrivé en retard relevait
    alors `_id_courant` et faisait rejouer une réponse déjà coupée."""
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[])

    await c.sur_message(StopAudio(id_enonce=1))  # devance, dans la file, le Dire ci-dessous
    await c.sur_message(_dire())  # id_enonce=1, arrivé en retard
    await c.sur_trame(_trame())

    assert p.joues == [], "le Dire arrivé en retard n'a pas dû relever l'énoncé courant"
