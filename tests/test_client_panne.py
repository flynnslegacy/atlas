"""Le client audio face à un périphérique mort, à une connexion annulée, et à l'absence
du Core : ce qui doit arrêter le programme, ce qui doit juste se reconnecter."""

import asyncio

import pytest
from test_client_audio import BLOC, FauxPeripherique, FauxTransport, _client
from test_client_connexion import FauxWs, Fin, Ouverture, PeripheriqueSilencieux, _dire, _trame
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.frames import Close

from atlas_audio.client import _vider_le_micro
from atlas_audio.connexion import PeripheriqueEnPanne, boucle_de_connexion, servir_connexion
from atlas_core.protocole import StopAudio

# --- une vraie panne du périphérique --------------------------------------------------


class _PeripheriqueMort(FauxPeripherique):
    """Le binaire Swift est mort : la capture et/ou la lecture lèvent une vraie panne."""

    def __init__(self, panne_capture=None, panne_lecture=None) -> None:
        super().__init__([])
        self._panne_capture = panne_capture
        self._panne_lecture = panne_lecture

    async def lire_bloc(self) -> bytes:
        if self._panne_capture is not None:
            raise self._panne_capture
        await asyncio.Event().wait()  # jamais réveillé : seule la panne doit y mettre fin
        return b""

    async def jouer(self, pcm: bytes) -> None:
        if self._panne_lecture is not None:
            raise self._panne_lecture
        await super().jouer(pcm)


def _armer_trace_arreter(c):
    """Note chaque appel à `c.arreter()`, en gardant son vrai comportement."""
    appels: list[int] = []
    original = c.arreter

    async def arreter():
        appels.append(1)
        await original()

    c.arreter = arreter
    return appels


async def test_une_capture_morte_arrete_la_connexion_avec_une_panne():
    t = FauxTransport()
    p = _PeripheriqueMort(panne_capture=asyncio.IncompleteReadError(b"", 640))
    c = _client(t, p, parole=[])
    appels = _armer_trace_arreter(c)
    ws = FauxWs(_dire().model_dump_json(), asyncio.Event())  # ne finit jamais seul

    with pytest.raises(PeripheriqueEnPanne):
        await asyncio.wait_for(servir_connexion(ws, c), timeout=2)

    assert appels, "arreter() doit être appelé même quand le périphérique meurt"


async def test_une_lecture_morte_arrete_la_connexion_avec_une_panne():
    t = FauxTransport()
    p = _PeripheriqueMort(panne_lecture=ConnectionResetError("son perdu"))
    c = _client(t, p, parole=[])
    appels = _armer_trace_arreter(c)
    ws = FauxWs(_dire().model_dump_json(), _trame(), asyncio.Event())  # ne finit jamais seul

    with pytest.raises(PeripheriqueEnPanne):
        await asyncio.wait_for(servir_connexion(ws, c), timeout=2)

    assert appels, "arreter() doit être appelé même quand le périphérique meurt"


async def test_deux_pannes_a_la_fois_ne_se_masquent_pas_l_une_l_autre():
    """Bug (revue, fix round 1) : l'ancien nettoyage réattendait chaque tâche dans son
    `finally` sans intercepter l'exception qu'elle relevait ; avec deux pannes à la fois,
    la seconde tâche réveillée pouvait remplacer l'erreur déjà en train de se propager,
    et sauter `arreter()` au passage. Une seule panne du périphérique doit sortir,
    quelle que soit la tâche qui l'a levée en premier."""
    t = FauxTransport()
    p = _PeripheriqueMort(
        panne_capture=asyncio.IncompleteReadError(b"", 640),
        panne_lecture=ConnectionResetError("son perdu"),
    )
    c = _client(t, p, parole=[])
    appels = _armer_trace_arreter(c)
    ws = FauxWs(_dire().model_dump_json(), _trame(), asyncio.Event())  # ne finit jamais seul

    with pytest.raises(PeripheriqueEnPanne):
        await asyncio.wait_for(servir_connexion(ws, c), timeout=2)

    assert appels, "arreter() doit être appelé même avec deux pannes à la fois"


async def test_annuler_servir_connexion_pendant_qu_elle_patiente_leve_juste_l_annulation():
    """Une connexion sans panne, annulée pendant qu'elle patiente (Ctrl-C ordinaire),
    relève l'annulation telle quelle et arrête quand même le client proprement."""
    t, p = FauxTransport(), PeripheriqueSilencieux([])
    c = _client(t, p, parole=[])
    appels = _armer_trace_arreter(c)
    ws = FauxWs(_dire().model_dump_json(), asyncio.Event())  # ne finit jamais seul

    tache = asyncio.create_task(servir_connexion(ws, c))
    for _ in range(5):
        await asyncio.sleep(0)
    tache.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tache

    assert appels, "arreter() doit être appelé même si la connexion est annulée"


async def test_une_panne_du_peripherique_arrete_la_boucle_sans_retenter():
    tentatives: list[int] = []

    def ouvrir():
        tentatives.append(1)
        return Ouverture("ws")

    async def servir(ws) -> None:
        raise PeripheriqueEnPanne("le périphérique audio est mort")

    async def attendre_jamais(_secondes: float) -> None:
        raise AssertionError("ne doit jamais retenter après une panne du périphérique")

    with pytest.raises(PeripheriqueEnPanne):
        await boucle_de_connexion(ouvrir, servir, attendre=attendre_jamais)

    assert tentatives == [1], "une seule tentative : pas de reconnexion après la panne"


# --- une panne du périphérique n'est pas une coupure réseau, et réciproquement -------


class _TransportCoupureReseau(FauxTransport):
    """Un envoi échoue comme le ferait un vrai websocket dont le Core est parti — pas
    comme une panne du périphérique."""

    def __init__(self, exception: BaseException) -> None:
        super().__init__()
        self._exception = exception

    async def envoyer_json(self, msg) -> None:
        raise self._exception

    async def envoyer_binaire(self, trame: bytes) -> None:
        raise self._exception


@pytest.mark.parametrize(
    "exception",
    [
        ConnectionClosedOK(Close(1000, ""), None),
        ConnectionClosedError(Close(1012, ""), None),
    ],
    ids=["fermeture_propre", "fermeture_en_erreur"],
)
async def test_une_fermeture_reseau_pendant_la_capture_reconnecte_sans_panne(exception):
    """Bug (revue, fix round 2) : un envoi au Core qui échoue parce qu'il est parti
    (`ConnectionClosed`) partait du même endroit — la tâche de capture — qu'une vraie
    panne du périphérique. L'ancien code confondait les deux sur la seule tâche fautive
    et arrêtait le programme au lieu de se reconnecter (reproduit avec un vrai `websockets`
    dans le scratchpad de la revue : jusqu'à 40/40 essais terminaient en `PeripheriqueEnPanne`
    selon le code de fermeture)."""
    t = _TransportCoupureReseau(exception)
    p = FauxPeripherique([BLOC] * 3)
    c = _client(t, p, parole=[], reveil_au=0)  # le premier bloc capturé déclenche l'envoi
    ws = FauxWs(asyncio.Event())  # ne finit jamais seul : seule la capture doit échouer

    tentatives: list[int] = []

    def ouvrir():
        tentatives.append(1)
        return Ouverture(ws)

    async def attendre(_secondes: float) -> None:
        raise Fin  # une tentative suffit : elle prouve qu'on a bien tenté de reconnecter

    with pytest.raises(Fin):
        await boucle_de_connexion(ouvrir, lambda w: servir_connexion(w, c), attendre=attendre)

    assert tentatives == [1], "la reconnexion a bien été retentée (pas de PeripheriqueEnPanne)"


class _PeripheriqueViderMort(FauxPeripherique):
    async def vider(self) -> None:
        raise ConnectionResetError("son perdu")


async def test_un_stop_audio_qui_vide_un_peripherique_mort_reste_une_panne():
    """Bug (revue, fix round 2), mislabel réciproque : `StopAudio` est traité par la
    tâche du flux (ni la capture, ni la lecture) ; sa panne de `vider()` doit rester une
    `PeripheriqueEnPanne` comme celle des deux autres tâches, pas une coupure réseau."""
    t, p = FauxTransport(), _PeripheriqueViderMort([])
    c = _client(t, p, parole=[])
    ws = FauxWs(
        _dire().model_dump_json(),
        StopAudio(id_enonce=1).model_dump_json(),
        asyncio.Event(),  # ne finit jamais seul
    )

    with pytest.raises(PeripheriqueEnPanne):
        await asyncio.wait_for(servir_connexion(ws, c), timeout=2)


class _ReveilleurCasse:
    """Un bug dans le mot de réveil, sans rapport avec le périphérique."""

    def examiner(self, bloc: bytes) -> bool:
        raise RuntimeError("bug du mot de réveil")


async def test_un_bug_du_reveilleur_n_est_pas_signale_comme_une_panne_du_peripherique():
    """Bug (revue, fix round 2), second mislabel : une exception du réveilleur (ou de la
    détection de voix) n'a rien à voir avec le périphérique audio ; elle ne doit pas être
    maquillée en `PeripheriqueEnPanne`."""
    t, p = FauxTransport(), FauxPeripherique([BLOC])
    c = _client(t, p, parole=[True])
    c._reveilleur = _ReveilleurCasse()
    ws = FauxWs(asyncio.Event())  # ne finit jamais seul

    with pytest.raises(RuntimeError, match="bug du mot de réveil"):
        await asyncio.wait_for(servir_connexion(ws, c), timeout=2)


# --- l'absence : le micro tourne dans le vide entre deux connexions ------------------


class _OuvertureLente:
    """Cède la main une fois avant de rendre le faux websocket, comme le ferait une
    vraie connexion réseau — assez pour laisser une tâche de fond démarrer avant elle."""

    def __init__(self, ws) -> None:
        self._ws = ws

    async def __aenter__(self):
        await asyncio.sleep(0)
        return self._ws

    async def __aexit__(self, *exc) -> bool:
        return False


async def test_pendant_l_absence_le_micro_est_vide_puis_arrete_avant_le_service():
    lectures = 0

    async def pendant_l_absence() -> None:
        nonlocal lectures
        while True:
            lectures += 1
            await asyncio.sleep(0)

    releves: list[int] = []

    def ouvrir():
        return _OuvertureLente("ws")

    async def servir(ws) -> None:
        releves.append(lectures)
        await asyncio.sleep(0)
        releves.append(lectures)

    async def attendre(_secondes: float) -> None:
        raise Fin  # une seule connexion servie suffit au test

    with pytest.raises(Fin):
        await boucle_de_connexion(
            ouvrir, servir, attendre=attendre, pendant_l_absence=pendant_l_absence
        )

    assert lectures > 0, "l'absence doit lire (et jeter) le micro dès le départ"
    assert releves[0] == releves[1], "aucune lecture n'arrive pendant que la connexion est servie"


async def test_vider_le_micro_lit_et_jette_les_blocs():
    """`_vider_le_micro` (passé comme `pendant_l_absence` par `principal()`) ne fait que
    lire le micro : rien n'est rejoué, rien n'est renvoyé à un client."""
    p = FauxPeripherique([BLOC] * 5)

    with pytest.raises(asyncio.CancelledError):
        await _vider_le_micro(p)  # `FauxPeripherique` lève une fois les blocs épuisés

    assert p.joues == [] and p.vidages == 0
