"""L'action qui attend le « oui » de David : la lecture de sa réponse, les phrases, le délai.
Une minuterie qu'on fait sonner à la main remplace les trente secondes."""

import asyncio
import threading

import pytest

from atlas_core.cerveau import Confirmation, Note
from atlas_core.confirmation import DELAI_S, Confirmations, Suppression, lire_reponse
from atlas_core.memoire import ErreurMemoire


class Minuterie:
    def __init__(self) -> None:
        self.delais: list[float] = []
        self._sonnerie = asyncio.Event()

    async def __call__(self, delai: float) -> None:
        self.delais.append(delai)
        await self._sonnerie.wait()

    def sonner(self) -> None:
        self._sonnerie.set()


class Temoin:
    """Ce que les pages reçoivent, et les exécutions de l'action."""

    def __init__(self) -> None:
        self.questions: list[str] = []
        self.fins: list[str] = []
        self.executions: list[int] = []

    def executer(self) -> None:
        self.executions.append(threading.get_ident())


def _document(temoin: Temoin) -> Suppression:
    return Suppression("documents/offre-de-lancement.md", "Offre de lancement", temoin.executer)


@pytest.fixture
def temoin() -> Temoin:
    return Temoin()


@pytest.fixture
def minuterie() -> Minuterie:
    return Minuterie()


@pytest.fixture
def confirmations(temoin, minuterie) -> Confirmations:
    return Confirmations(
        attendre=minuterie, sur_question=temoin.questions.append, sur_fin=temoin.fins.append
    )


async def _laisser_tourner() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


# --- la réponse de David ---------------------------------------------------------------


@pytest.mark.parametrize(
    "texte",
    [
        "Oui.",
        "OUI !",
        "ouais",
        "Oui oui",
        "Oui, vas-y.",
        "Vas-y !",
        "Je confirme.",
        "Oui, je confirme.",
        "Confirme",
        "D'accord",
        "D’accord.",
        "Oui, d'accord.",
        "OK",
        "Oui, ok.",
        "C'est bon.",
        "Oui, c'est bon.",
        "Supprime.",
        "Oui, supprime.",
        "Supprime-le.",
        "Supprime-la.",
        "Exactement.",
        "Tout à fait.",
        "Atlas, oui.",
        "Oui, Atlas.",
    ],
)
def test_ces_phrases_valent_oui(texte):
    assert lire_reponse(texte) == "oui"


@pytest.mark.parametrize(
    "texte",
    [
        "Non.",
        "Non non",
        "Non merci.",
        "Annule !",
        "Non, annule.",
        "Laisse tomber.",
        "Non, laisse tomber.",
        "Stop",
        "Arrête.",
        "Surtout pas !",
        "Pas du tout.",
        "Ne supprime pas.",
        "Ne supprime rien.",
        "Atlas, non.",
    ],
)
def test_ces_phrases_valent_non(texte):
    assert lire_reponse(texte) == "non"


@pytest.mark.parametrize(
    "texte",
    [
        "Oui, mais lis-le-moi d'abord.",
        "Qu'est-ce qu'il contient ?",
        "Oui non",
        "Supprime aussi la fiche de Paul.",
        "Atlas",
        "",
    ],
)
def test_tout_le_reste_vaut_autre_chose(texte):
    assert lire_reponse(texte) == "autre"


# --- les phrases d'une suppression ------------------------------------------------------


def test_une_suppression_se_dit_selon_ce_qu_elle_retire(temoin):
    document = _document(temoin)
    fiche = Suppression("personnes/paul-durand.md", "Paul Durand", temoin.executer)
    profil = Suppression("profil.md", "Profil", temoin.executer)
    assert document.question == "Je supprime le document Offre de lancement. Tu confirmes ?"
    assert fiche.question == "Je supprime la fiche Paul Durand. Tu confirmes ?"
    assert profil.question == "Je supprime ton profil. Tu confirmes ?"
    assert document.faite == "C'est fait : le document Offre de lancement est supprimé."
    assert fiche.faite == "C'est fait : la fiche Paul Durand est supprimée."
    assert profil.faite == "C'est fait : ton profil est supprimé."
    assert fiche.ratee == "Je n'ai pas pu supprimer la fiche Paul Durand."
    assert document.objet == "la suppression du document « Offre de lancement »"
    assert fiche.objet == "la suppression de la fiche « Paul Durand »"
    assert profil.objet == "la suppression du profil"
    assert fiche.page_faite == "Supprimé : la fiche Paul Durand."


# --- l'attente -----------------------------------------------------------------------


async def test_une_seule_action_attend_a_la_fois(confirmations, temoin):
    assert confirmations.mettre_en_attente(_document(temoin)) is True
    assert confirmations.mettre_en_attente(_document(temoin)) is False
    assert confirmations.en_attente


async def test_la_question_se_pose_une_fois_et_s_affiche_dans_les_pages(confirmations, temoin):
    assert confirmations.poser() is None  # rien n'attend
    confirmations.mettre_en_attente(_document(temoin))
    question = confirmations.poser()
    assert question == Confirmation("Je supprime le document Offre de lancement. Tu confirmes ?")
    assert isinstance(question, Note)  # la session la dit comme une annonce
    assert confirmations.poser() is None
    assert temoin.questions == [question.annonce]


async def test_oui_execute_hors_de_la_boucle_et_le_dit(confirmations, temoin):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    phrase = await confirmations.trancher("Oui, vas-y.")
    assert phrase == ("C'est fait : le document Offre de lancement est supprimé.", False)
    assert len(temoin.executions) == 1 and temoin.executions[0] != threading.get_ident()
    assert not confirmations.en_attente
    assert temoin.fins == ["Supprimé : le document Offre de lancement."]
    assert confirmations.prendre_les_lignes() == [
        "[Confirmé par David : le document « Offre de lancement » est supprimé.]"
    ]
    assert confirmations.prendre_les_lignes() == []


async def test_non_abandonne_sans_rien_executer(confirmations, temoin):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    assert await confirmations.trancher("Non, laisse tomber.") == (
        "D'accord, je ne supprime rien.",
        False,
    )
    assert temoin.executions == [] and not confirmations.en_attente
    assert temoin.fins == ["Rien n'a été supprimé."]
    assert confirmations.prendre_les_lignes() == ["[Refusé par David : rien n'a été supprimé.]"]


async def test_autre_chose_abandonne_puis_part_a_claude(confirmations, temoin):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    assert await confirmations.trancher("Oui, mais lis-le-moi d'abord.") == (
        "Je ne supprime rien.",
        True,
    )
    assert temoin.executions == [] and temoin.fins == ["Rien n'a été supprimé."]
    assert confirmations.prendre_les_lignes() == [
        "[David a répondu autre chose : la suppression du document « Offre de lancement » est "
        "abandonnée.]"
    ]


async def test_un_echec_apres_le_oui_se_dit_et_se_note(confirmations, caplog):
    def echouer() -> None:
        raise ErreurMemoire("documents/offre-de-lancement.md a été retouché à la main.")

    fins: list[str] = []
    confirmations.sur_fin = fins.append
    confirmations.mettre_en_attente(
        Suppression("documents/offre-de-lancement.md", "Offre de lancement", echouer)
    )
    confirmations.poser()
    assert await confirmations.trancher("oui") == (
        "Je n'ai pas pu supprimer le document Offre de lancement.",
        False,
    )
    assert fins == ["La suppression a échoué."]
    assert confirmations.prendre_les_lignes() == [
        "[La suppression du document « Offre de lancement » a échoué.]"
    ]
    assert "retouché à la main" in caplog.text


async def test_trente_secondes_sans_reponse_abandonnent_en_silence(
    confirmations, temoin, minuterie
):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    await _laisser_tourner()
    assert minuterie.delais == [DELAI_S] and DELAI_S == 30
    minuterie.sonner()
    await _laisser_tourner()
    assert not confirmations.en_attente and temoin.executions == []
    assert temoin.fins == ["Suppression abandonnée : pas de réponse."]
    assert confirmations.prendre_les_lignes() == [
        "[Sans réponse de David : la suppression du document « Offre de lancement » est "
        "abandonnée.]"
    ]


async def test_une_reponse_arrete_la_minuterie(confirmations, temoin, minuterie):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    await _laisser_tourner()
    await confirmations.trancher("non")
    confirmations.prendre_les_lignes()
    minuterie.sonner()
    await _laisser_tourner()
    assert temoin.fins == ["Rien n'a été supprimé."]
    assert confirmations.prendre_les_lignes() == []


async def test_une_question_jamais_posee_s_abandonne_sans_rien_montrer(confirmations, temoin):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.abandonner_si_non_posee()
    assert not confirmations.en_attente and temoin.fins == []
    assert confirmations.prendre_les_lignes() == [
        "[David a parlé avant la question : la suppression du document « Offre de lancement » "
        "est abandonnée.]"
    ]


async def test_une_question_posee_ne_s_abandonne_pas_ainsi(confirmations, temoin):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    confirmations.abandonner_si_non_posee()
    assert confirmations.en_attente


async def test_la_fin_d_une_conversation_ne_montre_rien_d_une_question_jamais_posee(
    confirmations, temoin
):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.abandonner()
    assert not confirmations.en_attente and temoin.fins == []


async def test_la_fin_de_la_conversation_abandonne_et_oublie_les_lignes(confirmations, temoin):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    await confirmations.trancher("non")
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    confirmations.abandonner()
    assert not confirmations.en_attente and temoin.executions == []
    assert temoin.fins == ["Rien n'a été supprimé.", "Rien n'a été supprimé."]
    assert confirmations.prendre_les_lignes() == []


async def test_une_question_jamais_posee_qui_expire_ne_montre_rien_aux_pages(
    confirmations, temoin, minuterie
):
    confirmations.mettre_en_attente(_document(temoin))
    await _laisser_tourner()
    minuterie.sonner()
    await _laisser_tourner()
    assert not confirmations.en_attente and temoin.fins == []
    assert len(confirmations.prendre_les_lignes()) == 1
