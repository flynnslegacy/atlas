"""La fin d'une conversation : le résumé au journal à l'échéance de l'oubli, et à l'arrêt du
Core. La doublure du SDK de `test_cerveau_claude.py`, une vraie mémoire sur un dépôt
temporaire, et une minuterie qu'on fait sonner à la main."""

import asyncio
import datetime as dt

import pytest
from test_cerveau_claude import (
    BLOQUE,
    Fabrique,
    FauxClientClaude,
    Temps,
    debut_recherche,
    debut_texte,
    delta,
    fin,
    reponse,
)
from test_cerveau_memoire import AppelOutil

from atlas_core import cerveau_claude
from atlas_core.cerveau import Note
from atlas_core.cerveau_claude import PHRASE_FIL_PERDU, CerveauClaude
from atlas_core.consignes import DEMANDE_RESUME
from atlas_core.memoire import Memoire
from atlas_core.outils_memoire import ANNONCE_PROFIL, OutilsMemoire

JOURNAL = "journal/2026-09-24.md"


class Moment:
    def __init__(self) -> None:
        self.t = dt.datetime(2026, 9, 24, 21, 50)

    def __call__(self) -> dt.datetime:
        return self.t


class Minuterie:
    """Les attentes du cerveau : chacune ne finit que quand le test la fait sonner."""

    def __init__(self) -> None:
        self.delais: list[float] = []
        self._sonneries: list[asyncio.Event] = []

    async def __call__(self, delai: float) -> None:
        self.delais.append(delai)
        sonnerie = asyncio.Event()
        self._sonneries.append(sonnerie)
        await sonnerie.wait()

    def sonner(self, rang: int = -1) -> None:
        self._sonneries[rang].set()


class Attente:
    """Claude met du temps à écrire : le tour reprend quand le test le libère."""

    def __init__(self) -> None:
        self._libre = asyncio.Event()

    async def __call__(self) -> None:
        await self._libre.wait()

    def liberer(self) -> None:
        self._libre.set()


def resume(texte: str) -> list:
    return [debut_texte(), delta(texte), fin()]


@pytest.fixture
def outils(tmp_path) -> OutilsMemoire:
    return OutilsMemoire(Memoire.ouvrir(tmp_path / "memoire"))


def _cerveau(outils, *clients, minuterie=None, moment=None, temps=None) -> CerveauClaude:
    return CerveauClaude(
        Fabrique(*clients),
        oubli_s=30 * 60,
        horloge=temps or Temps(),
        maintenant=moment or Moment(),
        outils=outils,
        attendre=minuterie or Minuterie(),
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


# --- à l'échéance --------------------------------------------------------------------


async def test_a_l_echeance_la_conversation_se_resume_au_journal_puis_se_ferme(outils):
    moment, minuterie = Moment(), Minuterie()
    client = FauxClientClaude(reponse("Midi."), reponse("Oui."), resume("On a parlé du site."))
    cerveau = _cerveau(outils, client, minuterie=minuterie, moment=moment)
    await _tout(cerveau, "Quelle heure est-il ?")
    moment.t += dt.timedelta(minutes=12)
    await _tout(cerveau, "Et le site ?")
    assert minuterie.delais == [30 * 60, 30 * 60]
    minuterie.sonner()
    await _jusqu_a(lambda: client.deconnexions == 1, "la conversation ne s'est pas fermée")
    assert client.questions[-1] == DEMANDE_RESUME
    assert outils.memoire.lire(JOURNAL) == (
        "# Journal du 24 septembre 2026\n\n## 21 h 50 – 22 h 02\n\nOn a parlé du site.\n"
    )


async def test_rien_a_garder_rien_n_est_ecrit(outils):
    minuterie = Minuterie()
    client = FauxClientClaude(reponse("Midi."), resume("RIEN."))
    cerveau = _cerveau(outils, client, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: client.deconnexions == 1, "la conversation ne s'est pas fermée")
    assert not (outils.memoire.racine / "journal").exists()


async def test_la_conversation_suivante_part_du_journal(outils):
    minuterie = Minuterie()
    ancien = FauxClientClaude(reponse("Midi."), resume("On a parlé de l'heure."))
    neuf = FauxClientClaude(reponse("Oui."))
    cerveau = _cerveau(outils, ancien, neuf, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: ancien.deconnexions == 1, "la conversation ne s'est pas fermée")
    await _tout(cerveau, "De quoi on a parlé ?")
    assert neuf.questions[0].startswith("[Mémoire d'Atlas]")
    assert "On a parlé de l'heure." in neuf.questions[0]


async def test_une_question_avant_l_echeance_la_repousse(outils):
    minuterie = Minuterie()
    client = FauxClientClaude(reponse("Un."), reponse("Deux."), resume("Deux questions."))
    cerveau = _cerveau(outils, client, minuterie=minuterie)
    await _tout(cerveau, "un")
    await _tout(cerveau, "deux")
    minuterie.sonner(0)  # la première échéance, annulée par la deuxième question
    for _ in range(50):
        await asyncio.sleep(0)
    assert DEMANDE_RESUME not in client.questions
    minuterie.sonner(1)
    await _jusqu_a(lambda: client.deconnexions == 1, "la conversation ne s'est pas fermée")


async def test_une_question_pendant_le_resume_l_attend_sans_le_couper(outils):
    minuterie, attente = Minuterie(), Attente()
    ancien = FauxClientClaude(
        reponse("Midi."), [debut_texte(), delta("On a parlé de l'heure."), attente, fin()]
    )
    neuf = FauxClientClaude(reponse("Deux."))
    cerveau = _cerveau(outils, ancien, neuf, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: DEMANDE_RESUME in ancien.questions, "le résumé n'est pas demandé")
    question = asyncio.create_task(_tout(cerveau, "deux"))
    for _ in range(50):
        await asyncio.sleep(0)
    assert not question.done() and ancien.interruptions == 0
    attente.liberer()
    assert await question == ["Deux."]
    assert "On a parlé de l'heure." in outils.memoire.lire(JOURNAL)


async def test_pendant_le_resume_claude_ne_peut_rien_ecrire(outils):
    minuterie = Minuterie()
    ecriture = AppelOutil(outils, "memoire_ecrire", chemin="profil.md", contenu="# P\n\nD.\n")
    client = FauxClientClaude(reponse("Midi."), [ecriture, debut_texte(), delta("L'heure."), fin()])
    cerveau = _cerveau(outils, client, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: client.deconnexions == 1, "la conversation ne s'est pas fermée")
    assert not (outils.memoire.racine / "profil.md").exists()
    assert outils.ecriture_permise is True


async def test_une_note_en_attente_n_est_pas_mangee_par_le_resume(outils):
    minuterie = Minuterie()
    ecriture = AppelOutil(outils, "memoire_ecrire", chemin="profil.md", contenu="# P\n\nD.\n")
    ancien = FauxClientClaude(
        [debut_texte(), delta("Je le note, "), ecriture, BLOQUE, delta("x"), fin()],
        resume("Le profil."),
    )
    neuf = FauxClientClaude(reponse("Oui."))
    cerveau = _cerveau(outils, ancien, neuf, minuterie=minuterie)
    flux = cerveau.repondre("Note ça.")
    assert await anext(flux) == "Je le note, "
    await flux.aclose()  # réponse lâchée : son annonce attend la suivante
    await _jusqu_a(lambda: minuterie.delais, "l'échéance n'est pas programmée")
    minuterie.sonner()
    await _jusqu_a(lambda: ancien.deconnexions == 1, "la conversation ne s'est pas fermée")
    assert await _tout(cerveau, "Tu as noté ?") == [Note(ANNONCE_PROFIL), "Oui."]


async def test_un_resume_trop_long_est_abandonne(outils, monkeypatch, caplog):
    monkeypatch.setattr(cerveau_claude, "DELAI_RESUME_S", 0.05)
    minuterie = Minuterie()
    ancien = FauxClientClaude(reponse("Midi."), [BLOQUE, fin()])
    neuf = FauxClientClaude(reponse("Oui."))
    cerveau = _cerveau(outils, ancien, neuf, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: ancien.deconnexions == 1, "la conversation ne s'est pas fermée")
    assert "résumé de la conversation perdu (TimeoutError)" in caplog.text
    assert not (outils.memoire.racine / "journal").exists()
    assert await _tout(cerveau, "Tu es là ?") == ["Oui."]


async def test_une_panne_de_claude_pendant_le_resume_ne_fait_pas_dire_fil_perdu(outils, caplog):
    minuterie = Minuterie()
    # Le flux se tarit sans message de fin : Claude s'est arrêté en plein résumé.
    ancien = FauxClientClaude(reponse("Midi."), [debut_texte(), delta("On a par")])
    neuf = FauxClientClaude(reponse("Oui."))
    cerveau = _cerveau(outils, ancien, neuf, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: ancien.deconnexions == 1, "la conversation ne s'est pas fermée")
    assert "résumé de la conversation perdu (ErreurCerveau)" in caplog.text
    fragments = await _tout(cerveau, "Tu es là ?")
    assert fragments == ["Oui."] and PHRASE_FIL_PERDU + " " not in fragments


async def test_une_recherche_pendant_le_resume_n_entre_pas_au_journal(outils):
    minuterie = Minuterie()
    client = FauxClientClaude(
        reponse("Midi."), [debut_recherche("t9"), debut_texte(), delta("Le site."), fin()]
    )
    cerveau = _cerveau(outils, client, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: client.deconnexions == 1, "la conversation ne s'est pas fermée")
    assert outils.memoire.lire(JOURNAL).endswith("\n\nLe site.\n")


async def test_chaque_conversation_a_ses_propres_heures_au_journal(outils):
    moment, minuterie = Moment(), Minuterie()
    ancien = FauxClientClaude(reponse("Un."), resume("La première."))
    neuf = FauxClientClaude(reponse("Deux."), resume("La seconde."))
    cerveau = _cerveau(outils, ancien, neuf, minuterie=minuterie, moment=moment)
    await _tout(cerveau, "un")
    minuterie.sonner()
    await _jusqu_a(lambda: ancien.deconnexions == 1, "la première ne s'est pas fermée")
    moment.t += dt.timedelta(hours=1)
    await _tout(cerveau, "deux")
    minuterie.sonner()
    await _jusqu_a(lambda: neuf.deconnexions == 1, "la seconde ne s'est pas fermée")
    assert "## 22 h 50 – 22 h 50\n\nLa seconde." in outils.memoire.lire(JOURNAL)


async def test_le_resume_attend_le_menage_d_une_reponse_abandonnee(outils, monkeypatch):
    monkeypatch.setattr(cerveau_claude, "DELAI_MENAGE_S", 0.2)
    minuterie = Minuterie()
    client = FauxClientClaude(
        [debut_texte(), delta("Une longue "), BLOQUE, delta("x"), fin()], resume("Rien.")
    )
    client.interruption_sans_effet = True  # le ménage ne finira pas : la conversation se perd
    cerveau = _cerveau(outils, client, minuterie=minuterie)
    flux = cerveau.repondre("Raconte.")
    assert await anext(flux) == "Une longue "
    await flux.aclose()
    await _jusqu_a(lambda: minuterie.delais, "l'échéance n'est pas programmée")
    minuterie.sonner()  # le ménage lit encore : le résumé ne doit pas croiser sa lecture
    await _jusqu_a(lambda: client.deconnexions == 1, "la conversation ne s'est pas fermée")
    for _ in range(20):
        await asyncio.sleep(0.01)
    assert DEMANDE_RESUME not in client.questions


async def test_l_oubli_constate_a_la_question_suivante_resume_aussi(outils):
    temps = Temps()
    ancien = FauxClientClaude(reponse("Midi."), resume("On a parlé de l'heure."))
    neuf = FauxClientClaude(reponse("Oui."))
    cerveau = _cerveau(outils, ancien, neuf, temps=temps)  # la minuterie ne sonne jamais
    await _tout(cerveau, "Quelle heure est-il ?")
    temps.t += 30 * 60
    assert await _tout(cerveau, "De quoi on a parlé ?") == ["Oui."]
    assert "On a parlé de l'heure." in outils.memoire.lire(JOURNAL)
    assert "On a parlé de l'heure." in neuf.questions[0]


# --- à l'arrêt du Core ----------------------------------------------------------------


async def test_a_l_arret_du_core_la_conversation_se_resume(outils):
    moment, minuterie = Moment(), Minuterie()
    client = FauxClientClaude(reponse("Midi."), resume("On a parlé de l'heure."))
    cerveau = _cerveau(outils, client, minuterie=minuterie, moment=moment)
    await _tout(cerveau, "Quelle heure est-il ?")
    await cerveau.fermer()
    assert client.questions[-1] == DEMANDE_RESUME and client.deconnexions == 1
    assert "On a parlé de l'heure." in outils.memoire.lire(JOURNAL)


async def test_l_arret_pendant_un_resume_le_laisse_finir(outils):
    minuterie, attente = Minuterie(), Attente()
    client = FauxClientClaude(
        reponse("Midi."), [debut_texte(), delta("On a parlé de l'heure."), attente, fin()]
    )
    cerveau = _cerveau(outils, client, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: DEMANDE_RESUME in client.questions, "le résumé n'est pas demandé")
    arret = asyncio.create_task(cerveau.fermer())
    for _ in range(20):
        await asyncio.sleep(0)
    attente.liberer()
    await arret
    assert "On a parlé de l'heure." in outils.memoire.lire(JOURNAL)
    assert client.questions.count(DEMANDE_RESUME) == 1


async def test_une_conversation_sans_question_ne_se_resume_pas(outils):
    fabrique = Fabrique(FauxClientClaude())
    cerveau = CerveauClaude(fabrique, outils=outils, attendre=Minuterie())
    await cerveau.fermer()
    assert fabrique.creations == 0


async def test_sans_memoire_ni_echeance_ni_resume():
    minuterie = Minuterie()
    client = FauxClientClaude(reponse("Midi."))
    cerveau = CerveauClaude(Fabrique(client), attendre=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    await cerveau.fermer()
    assert minuterie.delais == [] and client.questions == [client.questions[0]]
