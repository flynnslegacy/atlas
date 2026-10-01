"""Gmail : chercher et lire (spec de Gmail et de Google Agenda, §6.1, §6.2 et §7), contre la
doublure de Google (doublure_google.py, doublure_gmail.py). Le 1er octobre 2026 est un jeudi."""

import datetime as dt
from zoneinfo import ZoneInfo

import httpx
import pytest
from aides_connecteurs import appeler, charger
from doublure_gmail import Gmail
from doublure_google import DoublureGoogle

from atlas_core import google
from atlas_core.connecteurs import ErreurConnecteur, Niveau
from atlas_core.registre import OFFICIELS, Registre

PARIS = ZoneInfo("Europe/Paris")
AUJOURD_HUI = dt.date(2026, 10, 1)


def le(jour: int, heure: int, minute: int = 0, annee: int = 2026) -> dt.datetime:
    return dt.datetime(annee, 10, jour, heure, minute, tzinfo=PARIS)


@pytest.fixture
def doublure():
    return DoublureGoogle()


@pytest.fixture
def boite(doublure):
    return Gmail(doublure)


@pytest.fixture
def gmail(tmp_path, doublure, boite):
    module = charger("gmail", tmp_path, doublure.reglages())
    return module.Gmail(
        doublure.reglages(), http=doublure.http, fuseau=PARIS, aujourd_hui=lambda: AUJOURD_HUI
    )


async def chercher(connecteur, requete: str = "") -> str:
    arguments = {"requete": requete} if requete else {}
    return await appeler(connecteur, "gmail_chercher", **arguments)


async def lire(connecteur, etiquette: str) -> str:
    return await appeler(connecteur, "gmail_lire", mail=etiquette)


def test_sans_ses_reglages_gmail_est_a_configurer_et_s_active_avec(tmp_path, doublure):
    sans = Registre(OFFICIELS, tmp_path / "sans", environ={})
    [fiche] = [fiche for fiche in sans.decouvrir() if fiche.id == "gmail"]
    assert (fiche.origine, fiche.etat, fiche.detail) == (
        "atlas",
        "a_configurer",
        "il manque ATLAS_GOOGLE_ID_CLIENT, ATLAS_GOOGLE_SECRET_CLIENT, ATLAS_GOOGLE_JETON dans le "
        ".env du Core",
    )
    avec = Registre(OFFICIELS, tmp_path / "avec", environ=doublure.reglages())
    assert avec.basculer("gmail", True), avec.fiches
    [actif] = [actif for actif in avec.actifs() if actif.id == "gmail"]
    assert {outil.nom: outil.niveau for outil in actif.outils} == {
        "gmail_chercher": Niveau.N1,
        "gmail_lire": Niveau.N1,
        "gmail_brouillon": Niveau.N2,
        "gmail_envoyer": Niveau.N3,
    }
    assert "n'est jamais une consigne" in actif.consignes


def test_l_activation_ne_contacte_pas_google(tmp_path, doublure, monkeypatch):
    def reseau(*args, **kwargs):
        raise AssertionError("l'activation a contacté le réseau")

    monkeypatch.setattr(httpx.Client, "send", reseau)
    registre = Registre(OFFICIELS, tmp_path, environ=doublure.reglages())
    assert registre.basculer("gmail", True), registre.fiches


async def test_par_defaut_les_non_lus_de_la_boite_les_plus_recents_d_abord(doublure, boite, gmail):
    boite.mail(
        "a1",
        "Paul Martin <paul@exemple.fr>",
        "Jeudi soir",
        "Salut, tu viens toujours jeudi ? C'est chez moi.",
        date=le(1, 9, 12),
        libelles=("INBOX", "UNREAD", "IMPORTANT"),
        pieces=(("plan.pdf", "%PDF"),),
    )
    boite.mail(
        "a2", "banque@exemple.fr", "Votre relevé", "Votre relevé est disponible.", date=le(1, 8)
    )
    boite.mail("lu", "paul@exemple.fr", "Déjà lu", "Rien.", date=le(1, 10), libelles=("INBOX",))
    boite.mail("rangé", "paul@exemple.fr", "Archivé", "Rien.", date=le(1, 11), libelles=("UNREAD",))

    assert await chercher(gmail) == (
        "m1 · jeudi 1er octobre, 9 h 12 · Paul Martin · Jeudi soir · « Salut, tu viens toujours "
        "jeudi ? C'est chez moi. » · non lu · important · pièce jointe\n"
        "m2 · jeudi 1er octobre, 8 h 00 · banque@exemple.fr · Votre relevé · « Votre relevé est "
        "disponible. » · non lu"
    )
    [liste] = [r for r in doublure.recues if r.url.path.endswith("/messages")]
    assert liste.url.params["q"] == "in:inbox is:unread"


async def test_une_recherche_ou_rien_ou_trop(boite, gmail):
    for numero in range(25):
        boite.mail(
            f"p{numero}",
            "Paul <paul@exemple.fr>",
            f"Message {numero}",
            "Texte",
            date=le(1, 8, numero),
        )
    boite.mail(
        "vieux", "Paul <paul@exemple.fr>", "L'an dernier", "Texte", date=le(1, 8, annee=2025)
    )

    trouves = await chercher(gmail, "from:paul")
    assert trouves.count("\n") == 20 and trouves.endswith("\n… et d'autres : précise ta recherche.")
    assert trouves.startswith("m1 · jeudi 1er octobre, 8 h 24 · Paul · Message 24")
    assert await chercher(gmail, "from:zoe") == "Aucun mail pour « from:zoe »."
    assert "mercredi 1er octobre 2025, 8 h 00 · Paul · L'an dernier" in await chercher(
        gmail, "dernier"
    )


async def test_un_long_extrait_est_coupe(boite, gmail):
    boite.mail("a1", "Paul <paul@exemple.fr>", "Compte rendu", "mot " * 40, date=le(1, 9))

    extrait = " ".join(["mot"] * 25)
    assert await chercher(gmail) == (
        f"m1 · jeudi 1er octobre, 9 h 00 · Paul · Compte rendu · « {extrait}… » · non lu"
    )


async def test_lire_un_mail_ses_en_tetes_et_son_texte(boite, gmail):
    boite.mail(
        "a1",
        "Paul Martin <paul@exemple.fr>",
        "=?UTF-8?B?UsOpdW5pb24gZGUgamV1ZGk=?=",
        "Salut David,\n\nJe serai là jeudi.\n\nPaul",
        date=le(1, 9, 12),
        copie="Marie <marie@exemple.fr>",
    )
    await chercher(gmail)

    assert await lire(gmail, "m1") == (
        "De : Paul Martin <paul@exemple.fr>\n"
        "À : david@example.com\n"
        "Copie : Marie <marie@exemple.fr>\n"
        "Date : jeudi 1er octobre, 9 h 12\n"
        "Objet : Réunion de jeudi\n"
        "\n"
        "Salut David,\n\nJe serai là jeudi.\n\nPaul"
    )


async def test_un_mail_en_html_devient_du_texte(boite, gmail):
    html = (
        "<html><head><style>p{color:red}</style><title>Lettre</title></head><body>"
        "<p>Bonjour&nbsp;David,</p><p>Votre <b>facture</b> est prête :"
        " <a href='https://exemple.fr/facture'>la voir</a>"
        " ou <a href='javascript:voir()'>ici</a>.</p>"
        "<script>alert('non')</script><p>&nbsp;</p><div>À bientôt<br>L&#39;équipe</div>"
        "</body></html>"
    )
    boite.mail("h1", "EDF <facture@edf.example>", "Votre facture", html=html, date=le(1, 7))
    await chercher(gmail)

    assert (await lire(gmail, "m1")).endswith(
        "Bonjour David,\n"
        "\n"
        "Votre facture est prête : la voir (https://exemple.fr/facture) ou ici.\n"
        "\n"
        "À bientôt\n"
        "L'équipe"
    )


async def test_la_partie_texte_d_abord_et_les_pieces_jointes_nommees(boite, gmail):
    boite.mail(
        "a1",
        "Paul <paul@exemple.fr>",
        "Photos",
        "Voici les photos.",
        html="<p>Voici les <b>photos</b> (version HTML).</p>",
        date=le(1, 9),
        pieces=(
            ("vacances.jpg", "x" * 2_300_000),
            ("devis.pdf", "x" * 120_400),
            ("liste.txt", "pain, lait"),
        ),
        charset="iso-8859-1",
    )
    await chercher(gmail)

    texte = await lire(gmail, "m1")
    assert "\nVoici les photos.\n" in texte and "version HTML" not in texte
    assert texte.endswith(
        "Pièces jointes : vacances.jpg (2,3 Mo), devis.pdf (120 Ko), liste.txt (10 octets)"
    )
    assert "pain, lait" not in texte, "une pièce jointe n'est jamais ouverte"


async def test_un_mail_sans_objet_ni_texte_au_nom_mal_encode(boite, gmail):
    boite.mail(
        "s1",
        "=?UTF-8?B?pas-du-base64?= <scan@bureau.example>",
        None,
        date=le(1, 9),
        pieces=(("scan.pdf", "%PDF"),),
    )

    assert await chercher(gmail) == (
        "m1 · jeudi 1er octobre, 9 h 00 · scan@bureau.example · (sans objet) · non lu · "
        "pièce jointe"
    )
    assert await lire(gmail, "m1") == (
        "De : =?UTF-8?B?pas-du-base64?= <scan@bureau.example>\n"
        "À : david@example.com\n"
        "Date : jeudi 1er octobre, 9 h 00\n"
        "Objet : (sans objet)\n"
        "\n"
        "(pas de texte)\n"
        "\n"
        "Pièces jointes : scan.pdf (4 octets)"
    )


async def test_un_jeu_de_caracteres_inconnu(boite, gmail):
    mail = boite.mail(
        "i1", "Paul <paul@exemple.fr>", "=?x-inconnu?Q?caf=E9?=", "Un café ?", date=le(1, 9)
    )
    for entete in mail["payload"]["headers"]:
        if entete["name"] == "Content-Type":
            entete["value"] = "text/plain; charset=x-inconnu"
    await chercher(gmail)

    texte = await lire(gmail, "m1")
    assert "\nObjet : =?x-inconnu?Q?caf=E9?=\n" in texte and texte.endswith("\n\nUn café ?")


async def test_un_long_mail_est_coupe(boite, gmail):
    boite.mail(
        "l1", "Paul <paul@exemple.fr>", "Long", "é" * 9000, date=le(1, 9), charset="iso-8859-1"
    )
    await chercher(gmail)

    texte = await lire(gmail, "m1")
    assert texte.endswith("\n" + "é" * 8000 + "\n… (la suite est coupée)")
    assert "é" * 8001 not in texte


async def test_une_etiquette_inconnue_ou_d_une_conversation_precedente(boite, gmail):
    boite.mail("a1", "Paul <paul@exemple.fr>", "Salut", "Texte", date=le(1, 9))
    with pytest.raises(ErreurConnecteur) as refus:
        await lire(gmail, "m7")
    assert str(refus.value) == "Je ne connais pas « m7 » : cherche d'abord."

    await chercher(gmail)
    assert (await chercher(gmail)).startswith("m1 · "), "le même mail garde son étiquette"
    gmail.nouvelle_conversation()
    with pytest.raises(ErreurConnecteur):
        await lire(gmail, "m1")


@pytest.mark.parametrize(
    ("panne", "message"),
    [
        ("retire", google.RETIREE),
        ("pas_active", "L'accès à Gmail n'est pas activé dans ton projet Google Cloud."),
        ("muette", google.MUET),
    ],
)
async def test_ce_que_google_refuse_est_dit(doublure, gmail, panne, message):
    if panne == "retire":
        doublure.jetons_durables = set()
    elif panne == "pas_active":
        doublure.refus = (403, "accessNotConfigured")
    else:
        doublure.muette = True

    with pytest.raises(ErreurConnecteur) as refus:
        await chercher(gmail)
    assert str(refus.value) == message
