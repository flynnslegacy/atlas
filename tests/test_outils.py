"""Les niveaux d'autorisation : la règle que le Core applique autour de chaque outil, vérifiée
avec des outils factices, appelés comme Claude les appelle (leur gestionnaire)."""

import asyncio

import pytest
from claude_agent_sdk import AssistantMessage, ToolUseBlock

from atlas_core.cerveau import Confirmation, Note
from atlas_core.confirmation import Confirmations, Suppression
from atlas_core.memoire import ErreurMemoire
from atlas_core.outils import (
    DEJA_EN_ATTENTE,
    ECHEC,
    EN_ATTENTE,
    PENDANT_LE_RESUME,
    Fait,
    Niveau,
    Outil,
    ServeurAtlas,
)


class Banc:
    """Trois outils factices, un par niveau, qui notent leurs appels."""

    def __init__(self) -> None:
        self.appels: list[str] = []
        self.executions: list[str] = []

    async def lire(self, arguments: dict) -> str:
        self.appels.append("lire")
        return f"contenu de {arguments['chemin']}"

    async def ecrire(self, arguments: dict) -> Fait:
        self.appels.append("ecrire")
        if arguments["texte"] == "pareil":
            return Fait("Rien n'a changé.")
        return Fait("C'est écrit.", annonce="J'ai écrit la fiche Paul Durand.")

    async def supprimer(self, arguments: dict) -> Suppression:
        self.appels.append("supprimer")
        chemin = arguments["chemin"]
        return Suppression(chemin, "Paul Durand", lambda: self.executions.append(chemin))

    def outils(self) -> list[Outil]:
        return [
            Outil("lire", "Lit.", {"chemin": str}, Niveau.N1, self.lire),
            Outil("ecrire", "Écrit.", {"texte": str}, Niveau.N2, self.ecrire),
            Outil("supprimer", "Supprime.", {"chemin": str}, Niveau.N3, self.supprimer),
        ]


@pytest.fixture
def banc() -> Banc:
    return Banc()


@pytest.fixture
def serveur(banc) -> ServeurAtlas:
    return ServeurAtlas(banc.outils(), Confirmations())


async def appeler(serveur: ServeurAtlas, nom: str, **arguments) -> tuple[str, bool]:
    outil = next(o for o in serveur.outils if o.name == nom)
    resultat = await outil.handler(arguments)
    return resultat["content"][0]["text"], resultat.get("is_error", False)


def test_claude_voit_les_outils_sous_le_serveur_atlas(serveur):
    assert serveur.noms == ["mcp__atlas__lire", "mcp__atlas__ecrire", "mcp__atlas__supprimer"]
    assert (serveur.serveur()["type"], serveur.serveur()["name"]) == ("sdk", "atlas")
    ecrire = next(o for o in serveur.outils if o.name == "ecrire")
    assert (ecrire.description, ecrire.input_schema) == ("Écrit.", {"texte": str})


def test_un_outil_se_declare_toujours_avec_son_niveau(serveur):
    with pytest.raises(TypeError):
        Outil("lire", "Lit.", {"chemin": str}, gestionnaire=Banc().lire)  # type: ignore[call-arg]
    assert [(o.nom, o.niveau) for o in serveur.declarations] == [
        ("lire", Niveau.N1),
        ("ecrire", Niveau.N2),
        ("supprimer", Niveau.N3),
    ]


async def test_n1_rend_son_resultat_sans_rien_annoncer(serveur):
    assert await appeler(serveur, "lire", chemin="profil.md") == ("contenu de profil.md", False)
    assert serveur.prendre_les_annonces() == []


async def test_n2_fait_annoncer_ce_qui_a_change_et_seulement_ca(serveur):
    assert await appeler(serveur, "ecrire", texte="neuf") == ("C'est écrit.", False)
    assert await appeler(serveur, "ecrire", texte="pareil") == ("Rien n'a changé.", False)
    assert serveur.prendre_les_annonces() == [Note("J'ai écrit la fiche Paul Durand.")]
    assert serveur.prendre_les_annonces() == []


async def test_n3_ne_fait_rien_et_met_l_action_en_attente(serveur, banc):
    assert await appeler(serveur, "supprimer", chemin="personnes/paul-durand.md") == (
        EN_ATTENTE,
        False,
    )
    assert banc.executions == []
    assert serveur.confirmations.en_attente
    assert serveur.prendre_les_annonces() == []  # la question, c'est le cerveau qui la pose
    assert "N'ajoute rien" in EN_ATTENTE and "ne dis pas que c'est fait" in EN_ATTENTE


async def test_une_seconde_action_n3_est_refusee_tant_que_la_premiere_attend(serveur, banc):
    await appeler(serveur, "supprimer", chemin="personnes/paul-durand.md")
    assert await appeler(serveur, "supprimer", chemin="projets/site-web.md") == (
        DEJA_EN_ATTENTE,
        True,
    )
    serveur.confirmations.poser()
    assert await serveur.confirmations.trancher("oui") == (
        "C'est fait : la fiche Paul Durand est supprimée.",
        False,
    )
    await asyncio.sleep(0)
    assert banc.executions == ["personnes/paul-durand.md"]


async def test_pendant_le_resume_n2_et_n3_refusent_sans_s_executer_mais_n1_lit(serveur, banc):
    serveur.ecriture_permise = False
    assert await appeler(serveur, "ecrire", texte="neuf") == (PENDANT_LE_RESUME, True)
    assert await appeler(serveur, "supprimer", chemin="profil.md") == (PENDANT_LE_RESUME, True)
    assert await appeler(serveur, "lire", chemin="profil.md") == ("contenu de profil.md", False)
    assert banc.appels == ["lire"]
    assert not serveur.confirmations.en_attente


async def test_un_refus_revient_a_claude_et_une_panne_se_note(serveur, banc, caplog):
    async def refuser(arguments: dict) -> Fait:
        raise ErreurMemoire("Refusé : un secret.")

    async def tomber(arguments: dict) -> Fait:
        raise OSError("disque plein")

    banc.ecrire = refuser
    refus = ServeurAtlas(banc.outils(), Confirmations())
    assert await appeler(refus, "ecrire", texte="x") == ("Refusé : un secret.", True)
    banc.ecrire = tomber
    panne = ServeurAtlas(banc.outils(), Confirmations())
    assert await appeler(panne, "ecrire", texte="x") == (ECHEC, True)
    assert "l'outil ecrire a échoué" in caplog.text
    assert refus.prendre_les_annonces() == [] and panne.prendre_les_annonces() == []


def _appel(nom: str, parent: str | None = None) -> AssistantMessage:
    bloc = ToolUseBlock(id="a1", name=f"mcp__atlas__{nom}", input={})
    return AssistantMessage(content=[bloc], model="claude-sonnet-5", parent_tool_use_id=parent)


async def test_une_annonce_attend_que_le_cerveau_ait_lu_l_appel_de_son_outil(serveur):
    await appeler(serveur, "lire", chemin="profil.md")
    await appeler(serveur, "ecrire", texte="neuf")
    assert serveur.prendre_les_annonces(toutes=False) == []
    serveur.marquer_vus(_appel("lire"))
    recherche = ToolUseBlock(id="w1", name="WebSearch", input={})
    serveur.marquer_vus(AssistantMessage(content=[recherche], model="claude-sonnet-5"))
    serveur.marquer_vus(_appel("ecrire", parent="t9"))  # un sous-agent : pas la réponse d'Atlas
    assert serveur.prendre_les_annonces(toutes=False) == []
    serveur.marquer_vus(_appel("ecrire"))
    assert serveur.prendre_les_annonces(toutes=False) == [Note("J'ai écrit la fiche Paul Durand.")]


async def test_la_question_attend_aussi_que_le_cerveau_ait_lu_l_appel(serveur):
    await appeler(serveur, "supprimer", chemin="personnes/paul-durand.md")
    assert serveur.poser_la_question() is None
    serveur.marquer_vus(_appel("supprimer"))
    assert serveur.poser_la_question() == Confirmation(
        "Je supprime la fiche Paul Durand. Tu confirmes ?"
    )
    assert serveur.poser_la_question() is None


async def test_une_nouvelle_conversation_abandonne_et_recompte_les_appels(serveur):
    await appeler(serveur, "ecrire", texte="neuf")
    await appeler(serveur, "supprimer", chemin="personnes/paul-durand.md")
    serveur.nouvelle_conversation()
    assert not serveur.confirmations.en_attente
    # Ce qui attendait d'être dit le sera, au début de la réponse suivante.
    assert serveur.prendre_les_annonces(toutes=False) == [Note("J'ai écrit la fiche Paul Durand.")]
    await appeler(serveur, "ecrire", texte="encore")
    assert serveur.prendre_les_annonces(toutes=False) == []
    serveur.marquer_vus(_appel("ecrire"))
    assert serveur.prendre_les_annonces(toutes=False) == [Note("J'ai écrit la fiche Paul Durand.")]
