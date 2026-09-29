"""Une bascule de connecteur, vue du cerveau : la conversation se clôt comme à l'oubli
(résumé au journal), une réponse en cours d'abord finie, et la question suivante ouvre une
conversation neuve, avec les outils et les consignes des connecteurs actifs."""

import asyncio

import pytest
from test_cerveau_claude import FauxClientClaude, debut_texte, delta, fin, reponse
from test_cerveau_journal import JOURNAL, Attente, _cerveau, _jusqu_a, _tout, resume
from test_registre import deposer

from atlas_core.confirmation import Suppression
from atlas_core.consignes import DEMANDE_RESUME
from atlas_core.memoire import Memoire
from atlas_core.options_claude import options_cerveau
from atlas_core.outils_memoire import OutilsMemoire
from atlas_core.registre import Registre


@pytest.fixture
def annonces() -> list[str]:
    return []


@pytest.fixture
def outils(tmp_path, annonces) -> OutilsMemoire:
    deposer(tmp_path / "connecteurs", "salut")
    registre = Registre(tmp_path / "officiels", tmp_path / "connecteurs", environ={})
    return OutilsMemoire(
        Memoire.ouvrir(tmp_path / "memoire"),
        registre=registre,
        sur_connecteurs=lambda: annonces.append("liste"),
    )


async def test_une_bascule_clot_la_conversation_et_la_suivante_part_neuve(
    outils, annonces, tmp_path
):
    ancien = FauxClientClaude(reponse("Midi."), resume("On a parlé de l'heure."))
    neuf = FauxClientClaude(reponse("Bonjour David."))
    cerveau = _cerveau(outils, ancien, neuf)
    await _tout(cerveau, "Quelle heure est-il ?")
    assert outils.basculer("salut", True)
    cerveau.renouveler()
    await _jusqu_a(lambda: ancien.deconnexions == 1, "la conversation ne s'est pas close")
    assert ancien.questions[-1] == DEMANDE_RESUME
    assert "On a parlé de l'heure." in outils.memoire.lire(JOURNAL)
    assert annonces == [], "la bascule prend effet à la question suivante, pas avant"
    assert await _tout(cerveau, "Dis bonjour.") == ["Bonjour David."]
    assert annonces == ["liste"], "les pages voient que la bascule a pris effet"
    assert neuf.questions[0].startswith("[Mémoire d'Atlas]")
    options = options_cerveau("claude-sonnet-5", tmp_path, outils)
    assert "mcp__atlas__salut_dire" in options.allowed_tools
    assert "Dis bonjour quand David te le demande." in options.system_prompt


async def test_une_reponse_en_cours_se_finit_avant_la_cloture(outils):
    attente = Attente()
    ancien = FauxClientClaude(
        [debut_texte(), delta("Il est "), attente, delta("midi."), fin()],
        resume("On a parlé de l'heure."),
    )
    cerveau = _cerveau(outils, ancien)
    question = asyncio.create_task(_tout(cerveau, "Quelle heure est-il ?"))
    await _jusqu_a(lambda: ancien.questions, "la question n'est pas partie")
    outils.basculer("salut", True)
    cerveau.renouveler()
    for _ in range(20):
        await asyncio.sleep(0)
    assert DEMANDE_RESUME not in ancien.questions and ancien.interruptions == 0
    attente.liberer()
    assert await question == ["Il est ", "midi."]
    await _jusqu_a(lambda: ancien.deconnexions == 1, "la conversation ne s'est pas close")
    assert ancien.questions[-1] == DEMANDE_RESUME


async def test_une_question_juste_apres_la_bascule_part_dans_la_conversation_neuve(outils):
    ancien = FauxClientClaude(reponse("Midi."), resume("On a parlé de l'heure."))
    neuf = FauxClientClaude(reponse("Bonjour."))
    cerveau = _cerveau(outils, ancien, neuf)
    await _tout(cerveau, "Quelle heure est-il ?")
    outils.basculer("salut", True)
    cerveau.renouveler()
    assert await _tout(cerveau, "Dis bonjour.") == ["Bonjour."]
    assert ancien.questions[-1] == DEMANDE_RESUME and ancien.deconnexions == 1
    assert neuf.questions[-1].endswith("Dis bonjour.")


async def test_sans_conversation_la_bascule_ne_demande_aucun_resume(outils, annonces):
    client = FauxClientClaude(reponse("Bonjour."))
    cerveau = _cerveau(outils, client)
    outils.basculer("salut", True)
    cerveau.renouveler()
    for _ in range(20):
        await asyncio.sleep(0)
    assert client.questions == [] and annonces == []
    assert [f.en_attente for f in outils.registre.fiches] == [True], "jusqu'à la question"
    assert await _tout(cerveau, "Bonjour ?") == ["Bonjour."]
    assert annonces == ["liste"] and [f.en_attente for f in outils.registre.fiches] == [False]
    await cerveau.fermer()


async def test_a_l_arret_du_core_un_renouvellement_finit_son_resume(outils):
    attente = Attente()
    client = FauxClientClaude(
        reponse("Midi."), [debut_texte(), delta("On a parlé de l'heure."), attente, fin()]
    )
    cerveau = _cerveau(outils, client)
    await _tout(cerveau, "Quelle heure est-il ?")
    outils.basculer("salut", True)
    cerveau.renouveler()
    await _jusqu_a(lambda: DEMANDE_RESUME in client.questions, "le résumé n'est pas demandé")
    arret = asyncio.create_task(cerveau.fermer())
    for _ in range(20):
        await asyncio.sleep(0)
    attente.liberer()
    await asyncio.wait_for(arret, timeout=2)
    assert "On a parlé de l'heure." in outils.memoire.lire(JOURNAL)


async def test_une_bascule_pendant_une_suppression_en_attente_l_abandonne(outils, tmp_path):
    fins: list[str] = []
    outils.confirmations.sur_fin = fins.append
    supprimees: list[str] = []
    ancien = FauxClientClaude(reponse("Midi."), resume("RIEN."))
    cerveau = _cerveau(outils, ancien)
    await _tout(cerveau, "Quelle heure est-il ?")
    action = Suppression("profil.md", "ton profil", lambda: supprimees.append("profil.md"))
    outils.confirmations.mettre_en_attente(action)
    outils.confirmations.poser()
    outils.basculer("salut", True)
    cerveau.renouveler()
    await _jusqu_a(lambda: ancien.deconnexions == 1, "la conversation ne s'est pas close")
    assert fins == ["Rien n'a été supprimé."] and supprimees == []
    assert not outils.confirmations.en_attente
