"""Le cerveau et la mission : elle ne vit que le temps de la réponse qui suit le « oui », et
la moindre phrase de David l'arrête. Avec la doublure du SDK, un faux poste et une vraie
mémoire sur un dépôt temporaire."""

import asyncio
import contextlib

import pytest
from test_cerveau_claude import (
    BLOQUE,
    MOMENT,
    Fabrique,
    FauxClientClaude,
    Temps,
    debut_texte,
    delta,
    erreur_assistant,
    fin,
    reponse,
)
from test_cerveau_memoire import AppelOutil
from test_outils_poste import FauxPoste

from atlas_core.cerveau import Confirmation, ErreurCerveau
from atlas_core.cerveau_claude import CerveauClaude, options_cerveau
from atlas_core.confirmation import Confirmations
from atlas_core.consignes import CONSIGNES_AVEC_MEMOIRE, CONSIGNES_AVEC_POSTE
from atlas_core.memoire import Memoire
from atlas_core.outils_memoire import OutilsMemoire
from atlas_core.outils_poste import Missions
from atlas_core.protocole_poste import Cliquer

NOTE = "écrire bonjour dans une nouvelle note"
QUESTION = "Je vais écrire bonjour dans une nouvelle note. Tu confirmes ?"


async def _jamais(delai: float) -> None:
    await asyncio.Event().wait()


class Pages:
    def __init__(self) -> None:
        self.debuts: list[str] = []
        self.fins: list[str] = []


@pytest.fixture
def pages() -> Pages:
    return Pages()


@pytest.fixture
def poste() -> FauxPoste:
    return FauxPoste()


@pytest.fixture
def outils(tmp_path, poste, pages) -> OutilsMemoire:
    missions = Missions(attendre=_jamais, sur_debut=pages.debuts.append, sur_fin=pages.fins.append)
    return OutilsMemoire(
        Memoire.ouvrir(tmp_path / "memoire"),
        Confirmations(attendre=_jamais),
        poste=poste,
        missions=missions,
    )


def _cerveau(outils, *clients) -> CerveauClaude:
    return CerveauClaude(
        Fabrique(*clients),
        oubli_s=30 * 60,
        horloge=Temps(),
        maintenant=lambda: MOMENT,
        outils=outils,
        attendre=_jamais,
    )


async def _tout(cerveau: CerveauClaude, texte: str) -> list:
    async def lire() -> list:
        return [f async for f in cerveau.repondre(texte)]

    return await asyncio.wait_for(lire(), timeout=2)


def _demande(outils) -> list:
    return [
        debut_texte(),
        delta("D'accord."),
        AppelOutil(outils, "mac_mission", mission=NOTE),
        fin(),
    ]


async def test_la_mission_vit_le_temps_de_la_reponse_qui_suit_le_oui(outils, poste, pages):
    pilotage = [
        AppelOutil(outils, "mac_cliquer", x=640, y=400),
        debut_texte(),
        delta("C'est écrit."),
        fin(),
    ]
    client = FauxClientClaude(_demande(outils), pilotage)
    cerveau = _cerveau(outils, client)
    assert await _tout(cerveau, "Écris bonjour dans une note.") == [
        "D'accord.",
        Confirmation(QUESTION),
    ]
    assert await _tout(cerveau, "Oui.") == ["C'est parti. ", "C'est écrit."]
    assert poste.gestes == [Cliquer(x=640, y=400)]
    assert pages.debuts == ["Mission en cours : écrire bonjour dans une nouvelle note"]
    assert pages.fins == ["Mission terminée."]  # la réponse finie, la mission avec
    assert outils.missions.en_cours is None


async def test_la_moindre_phrase_de_david_arrete_la_mission(outils, pages):
    pilotage = [AppelOutil(outils, "mac_capture"), BLOQUE, delta("jamais"), fin()]
    client = FauxClientClaude(_demande(outils), pilotage, reponse("D'accord, j'arrête."))
    cerveau = _cerveau(outils, client)
    await _tout(cerveau, "Écris bonjour dans une note.")
    en_route = asyncio.create_task(_tout(cerveau, "Oui."))
    for _ in range(200):
        if outils.missions.en_cours is not None:
            break
        await asyncio.sleep(0.01)
    assert outils.missions.en_cours == NOTE
    assert await _tout(cerveau, "Stop.") == ["D'accord, j'arrête."]
    await en_route
    assert pages.fins == ["Mission arrêtée."]
    assert client.questions[-1].endswith("Stop.")


async def test_une_reponse_coupee_par_sa_session_arrete_la_mission(outils, pages):
    # « Hey Atlas », une coupure à la voix, ou le bouton « Stop » d'une page au micro allumé :
    # la session annule sa réponse avant même que la phrase suivante n'arrive.
    pilotage = [AppelOutil(outils, "mac_capture"), BLOQUE, delta("jamais"), fin()]
    client = FauxClientClaude(_demande(outils), pilotage, reponse("D'accord, j'arrête."))
    cerveau = _cerveau(outils, client)
    await _tout(cerveau, "Écris bonjour dans une note.")

    async def lire() -> None:
        async with contextlib.aclosing(cerveau.repondre("Oui.")) as fragments:
            async for _ in fragments:
                pass

    en_route = asyncio.create_task(lire())
    for _ in range(200):
        if outils.missions.en_cours is not None:
            break
        await asyncio.sleep(0.01)
    assert outils.missions.en_cours == NOTE
    en_route.cancel()
    with pytest.raises(asyncio.CancelledError):
        await en_route
    assert pages.fins == ["Mission arrêtée."]
    assert await _tout(cerveau, "Stop.") == ["D'accord, j'arrête."]
    assert pages.fins == ["Mission arrêtée."]


async def test_une_panne_de_claude_en_pleine_mission_la_ferme(outils, pages):
    pilotage = [AppelOutil(outils, "mac_capture"), erreur_assistant("rate_limit"), fin()]
    cerveau = _cerveau(outils, FauxClientClaude(_demande(outils), pilotage))
    await _tout(cerveau, "Écris bonjour dans une note.")
    with pytest.raises(ErreurCerveau):
        await _tout(cerveau, "Oui.")
    assert pages.fins == ["Mission terminée."]
    assert outils.missions.en_cours is None


def test_avec_le_poste_claude_recoit_les_consignes_du_mac(outils, tmp_path):
    options = options_cerveau("claude-sonnet-5", tmp_path, outils)
    assert options.system_prompt == CONSIGNES_AVEC_POSTE
    assert "mcp__atlas__mac_mission" in options.allowed_tools
    sans = OutilsMemoire(Memoire.ouvrir(tmp_path / "autre"))
    assert (
        options_cerveau("claude-sonnet-5", tmp_path, sans).system_prompt == CONSIGNES_AVEC_MEMOIRE
    )
