"""Le cerveau et la confirmation (N3) : la question posée à sa place dans la réponse, la
réponse de David lue avant Claude, la ligne qui dit le résultat à Claude, et l'abandon quand
la question n'a pas été entendue ou que la conversation se termine. Avec la doublure du SDK
et une vraie mémoire sur un dépôt temporaire."""

import asyncio

import pytest
from test_cerveau_claude import (
    BLOQUE,
    MOMENT,
    Fabrique,
    FauxClientClaude,
    Temps,
    debut_texte,
    delta,
    fin,
    reponse,
)
from test_cerveau_journal import Minuterie, resume

from atlas_core.cerveau import Confirmation
from atlas_core.cerveau_claude import CerveauClaude
from atlas_core.confirmation import Confirmations
from atlas_core.consignes import DEMANDE_RESUME
from atlas_core.memoire import Memoire
from atlas_core.outils_memoire import OutilsMemoire

DATE = "[jeudi 24 septembre 2026, 21 h 50]"
OFFRE = "# Offre de lancement\n\nTrois formules pour les premiers clients.\n"
QUESTION = "Je supprime le document Offre de lancement. Tu confirmes ?"
CHEMIN = "documents/offre-de-lancement.md"


async def _jamais(delai: float) -> None:
    await asyncio.Event().wait()  # les trente secondes ne sonnent jamais ici


class Pages:
    def __init__(self) -> None:
        self.fins: list[str] = []


@pytest.fixture
def pages() -> Pages:
    return Pages()


@pytest.fixture
def outils(tmp_path, pages) -> OutilsMemoire:
    memoire = Memoire.ouvrir(tmp_path / "memoire")
    memoire.ecrire_document("offre-de-lancement", OFFRE)
    return OutilsMemoire(memoire, Confirmations(attendre=_jamais, sur_fin=pages.fins.append))


class Supprimer:
    """Claude appelle memoire_supprimer au milieu d'un tour : le SDK exécute son gestionnaire."""

    def __init__(self, outils: OutilsMemoire, chemin: str = CHEMIN) -> None:
        self._outil = next(o for o in outils.outils if o.name == "memoire_supprimer")
        self._chemin = chemin

    async def __call__(self) -> None:
        await self._outil.handler({"chemin": self._chemin})


def _cerveau(outils, *clients, minuterie=None) -> CerveauClaude:
    return CerveauClaude(
        Fabrique(*clients),
        oubli_s=30 * 60,
        horloge=Temps(),
        maintenant=lambda: MOMENT,
        outils=outils,
        attendre=minuterie or _jamais,
    )


async def _tout(cerveau: CerveauClaude, texte: str) -> list:
    async def lire() -> list:
        return [f async for f in cerveau.repondre(texte)]

    fragments = await asyncio.wait_for(lire(), timeout=2)
    for _ in range(5):
        await asyncio.sleep(0)  # l'échéance programmée par la réponse se met à attendre
    return fragments


async def _jusqu_a(condition, message: str) -> None:
    for _ in range(200):  # deux secondes au plus
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(message)


def _demande(outils) -> list:
    return [debut_texte(), delta("D'accord."), Supprimer(outils), fin()]


async def test_la_question_se_pose_a_sa_place_dans_la_reponse(outils):
    client = FauxClientClaude(_demande(outils))
    fragments = await _tout(_cerveau(outils, client), "Supprime l'offre de lancement.")
    assert fragments == ["D'accord.", Confirmation(QUESTION)]
    assert outils.memoire.lire(CHEMIN) == OFFRE  # rien n'est encore supprimé


async def test_oui_supprime_sans_passer_par_claude_puis_claude_l_apprend(outils, pages):
    client = FauxClientClaude(_demande(outils), reponse("Très bien."))
    cerveau = _cerveau(outils, client)
    await _tout(cerveau, "Supprime l'offre de lancement.")
    assert await _tout(cerveau, "Oui.") == [
        "C'est fait : le document Offre de lancement est supprimé."
    ]
    assert len(client.questions) == 1
    assert outils.memoire.documents() == []
    assert pages.fins == ["Supprimé : le document Offre de lancement."]
    await _tout(cerveau, "Et maintenant ?")
    assert client.questions[-1] == (
        "[Confirmé par David : le document « Offre de lancement » est supprimé.]\n"
        f"{DATE}\nEt maintenant ?"
    )


async def test_non_ne_supprime_rien_et_claude_l_apprend(outils):
    client = FauxClientClaude(_demande(outils), reponse("Entendu."))
    cerveau = _cerveau(outils, client)
    await _tout(cerveau, "Supprime l'offre de lancement.")
    assert await _tout(cerveau, "Non, laisse tomber.") == ["D'accord, je ne supprime rien."]
    assert outils.memoire.lire(CHEMIN) == OFFRE
    await _tout(cerveau, "Merci.")
    assert client.questions[-1] == f"[Refusé par David : rien n'a été supprimé.]\n{DATE}\nMerci."


async def test_autre_chose_abandonne_puis_part_a_claude_dans_la_meme_reponse(outils):
    client = FauxClientClaude(_demande(outils), reponse("Elle propose trois formules."))
    cerveau = _cerveau(outils, client)
    await _tout(cerveau, "Supprime l'offre de lancement.")
    assert await _tout(cerveau, "Attends, lis-la-moi d'abord.") == [
        "Je ne supprime rien. ",
        "Elle propose trois formules.",
    ]
    assert outils.memoire.lire(CHEMIN) == OFFRE
    assert client.questions[-1] == (
        "[David a répondu autre chose : la suppression du document « Offre de lancement » est "
        f"abandonnée.]\n{DATE}\nAttends, lis-la-moi d'abord."
    )


async def test_un_oui_qui_coupe_la_fin_de_la_reponse_compte(outils):
    client = FauxClientClaude(
        [debut_texte(), delta("D'accord."), Supprimer(outils), delta(" Je"), BLOQUE, fin()],
        reponse("Oui ?"),
    )
    cerveau = _cerveau(outils, client)
    premiere: list = []

    async def lire_la_premiere() -> None:
        async for fragment in cerveau.repondre("Supprime l'offre."):
            premiere.append(fragment)

    tache = asyncio.create_task(lire_la_premiere())
    await _jusqu_a(lambda: Confirmation(QUESTION) in premiere, "la question n'est pas posée")
    assert await _tout(cerveau, "Oui.") == [
        "C'est fait : le document Offre de lancement est supprimé."
    ]
    await tache
    assert outils.memoire.documents() == []
    assert len(client.questions) == 1


async def test_une_question_coupee_avant_d_etre_posee_est_abandonnee(outils, pages):
    client = FauxClientClaude(
        [debut_texte(), delta("Je regarde. "), Supprimer(outils), BLOQUE, delta("x"), fin()],
        reponse("Oui ?"),
    )
    cerveau = _cerveau(outils, client)
    premiere: list = []

    async def lire_la_premiere() -> None:
        async for fragment in cerveau.repondre("Supprime l'offre."):
            premiere.append(fragment)

    tache = asyncio.create_task(lire_la_premiere())
    await _jusqu_a(lambda: outils.confirmations.en_attente, "la suppression n'attend pas")
    assert await _tout(cerveau, "Oui.") == ["Oui ?"]  # pas une réponse : la question n'est pas dite
    await tache
    assert premiere == ["Je regarde. "]
    assert outils.memoire.lire(CHEMIN) == OFFRE and pages.fins == []
    assert client.questions[-1] == (
        "[David a parlé avant la question : la suppression du document « Offre de lancement » "
        f"est abandonnée.]\n{DATE}\nOui."
    )


async def test_la_fin_de_la_conversation_abandonne_l_action_en_attente(outils, pages):
    client = FauxClientClaude(_demande(outils), resume("RIEN"))
    cerveau = _cerveau(outils, client)
    await _tout(cerveau, "Supprime l'offre de lancement.")
    await cerveau.fermer()
    assert not outils.confirmations.en_attente
    assert outils.memoire.lire(CHEMIN) == OFFRE
    assert pages.fins == ["Rien n'a été supprimé."]


async def test_le_resume_apprend_ce_que_david_a_confirme_juste_avant(outils):
    minuterie = Minuterie()
    client = FauxClientClaude(_demande(outils), resume("On a supprimé l'offre."))
    cerveau = _cerveau(outils, client, minuterie=minuterie)
    await _tout(cerveau, "Supprime l'offre de lancement.")
    await _tout(cerveau, "Oui.")
    minuterie.sonner()
    await _jusqu_a(lambda: client.deconnexions, "la conversation ne s'est pas fermée")
    assert client.questions[-1] == (
        "[Confirmé par David : le document « Offre de lancement » est supprimé.]\n" + DEMANDE_RESUME
    )
    assert outils.confirmations.prendre_les_lignes() == []
