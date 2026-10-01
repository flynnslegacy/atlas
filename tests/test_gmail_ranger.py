"""Gmail : ranger (spec de Gmail et de Google Agenda, §6.4), contre la doublure de Google. Le
rangement se fait puis se dit, corbeille comprise (elle se rattrape pendant 30 jours) ; jamais
d'effacement définitif."""

import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest
from aides_connecteurs import appeler, charger
from doublure_gmail import Gmail
from doublure_google import DoublureGoogle

from atlas_core.connecteurs import ErreurConnecteur, Fait

PARIS = ZoneInfo("Europe/Paris")


@pytest.fixture
def doublure():
    return DoublureGoogle()


@pytest.fixture
def boite(doublure):
    boite = Gmail(doublure)
    for numero in range(1, 4):
        boite.mail(
            f"a{numero}",
            "Paul <paul@exemple.fr>",
            f"Message {numero}",
            "Texte",
            date=dt.datetime(2026, 10, 1, 9, numero, tzinfo=PARIS),
        )
    boite.libelle("Factures")
    boite.libelle("Élèves")
    return boite


@pytest.fixture
async def gmail(tmp_path, doublure, boite):
    module = charger("gmail", tmp_path, doublure.reglages())
    connecteur = module.Gmail(doublure.reglages(), http=doublure.http, fuseau=PARIS)
    await appeler(connecteur, "gmail_chercher")  # m1 : a3, m2 : a2, m3 : a1
    return connecteur


async def ranger(connecteur, mails: str, action: str, **autres: str) -> Fait:
    return await appeler(connecteur, "gmail_ranger", mails=mails, action=action, **autres)


def changements(doublure):
    return [json.loads(r.content) for r in doublure.recues if r.url.path.endswith("batchModify")]


async def test_marquer_comme_lu_ou_non_lu(doublure, boite, gmail):
    fait = await ranger(gmail, "m1, m2", "lu")

    assert fait == Fait("C'est fait.", "C'est rangé : 2 mails marqués comme lus.")
    assert changements(doublure) == [
        {"ids": ["a3", "a2"], "addLabelIds": [], "removeLabelIds": ["UNREAD"]}
    ]
    assert "UNREAD" not in boite.mails["a3"]["labelIds"]
    fait = await ranger(gmail, "m1", "non_lu")
    assert fait.annonce == "C'est rangé : 1 mail marqué comme non lu."
    assert "UNREAD" in boite.mails["a3"]["labelIds"]


async def test_archiver_retire_de_la_boite_de_reception(boite, gmail):
    fait = await ranger(gmail, "m1 m2 m3", "archiver")

    assert fait.annonce == "C'est rangé : 3 mails archivés."
    assert all("INBOX" not in mail["labelIds"] for mail in boite.mails.values())


async def test_un_libelle_qui_existe_sans_tenir_compte_des_accents(doublure, boite, gmail):
    fait = await ranger(gmail, "m3", "libelle", libelle="eleves")

    assert fait.annonce == "C'est rangé : 1 mail sous « Élèves »."
    [changement] = changements(doublure)
    assert changement["addLabelIds"] == ["Label_10"] and boite.libelles["Label_10"] == "Élèves"
    with pytest.raises(ErreurConnecteur) as refus:
        await ranger(gmail, "m3", "libelle", libelle="Impôts")
    assert str(refus.value) == (
        "Pas de libellé « Impôts » dans ta boîte Gmail. Tes libellés : Élèves, Factures."
    )


async def test_la_corbeille_jamais_l_effacement(doublure, boite, gmail):
    fait = await ranger(gmail, "m2", "corbeille")

    assert fait.annonce == "C'est rangé : 1 mail mis à la corbeille."
    assert boite.mails["a2"]["labelIds"] == ["UNREAD", "TRASH"]
    assert [r.method for r in doublure.recues if "a2" in r.url.path and r.method != "GET"] == [
        "POST"
    ], "jamais de DELETE"


@pytest.mark.parametrize(
    ("mails", "action", "autres", "message"),
    [
        ("m9", "lu", {}, "Je ne connais pas « m9 » : cherche d'abord."),
        ("", "lu", {}, "Dis quels mails ranger (mails : m1, m2…)."),
        ("m1", "effacer", {}, "action : lu, non_lu, archiver, libelle ou corbeille."),
        ("m1", "libelle", {}, "Donne le nom du libellé (libelle)."),
    ],
)
async def test_un_rangement_mal_demande_est_refuse_sans_rien_changer(
    doublure, gmail, mails, action, autres, message
):
    with pytest.raises(ErreurConnecteur) as refus:
        await ranger(gmail, mails, action, **autres)
    assert str(refus.value) == message
    assert changements(doublure) == []
