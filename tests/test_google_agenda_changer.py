"""Google Agenda : ajouter, modifier et supprimer (spec de Gmail et de Google Agenda, §5), contre
la doublure de Google. Ce qu'Atlas envoie compte autant que ce qu'il dit : jamais de
notification aux invités (`sendUpdates=none`), et `If-Match` sur chaque modification. Le 1er
octobre 2026 est un jeudi."""

import datetime as dt
import json
import sys
from zoneinfo import ZoneInfo

import pytest
from aides_connecteurs import appeler, charger
from doublure_agenda import AgendaGoogle
from doublure_google import DoublureGoogle

from atlas_core.connecteurs import Action, ErreurConnecteur

PARIS = ZoneInfo("Europe/Paris")
PERSO = "david@example.com"
TRAVAIL = "travail@group.calendar.google.com"
FERIES = "fr.french#holiday@group.v.calendar.google.com"


def a_paris(jour: int, heure: int, mois: int = 10) -> dt.datetime:
    return dt.datetime(2026, mois, jour, heure, tzinfo=PARIS)


@pytest.fixture
def doublure():
    return DoublureGoogle()


@pytest.fixture
def agenda(doublure):
    agenda = AgendaGoogle(doublure)
    agenda.agenda(PERSO, "Perso", principal=True)
    agenda.agenda(TRAVAIL, "Travail")
    agenda.agenda(FERIES, "Jours fériés", role="reader")
    return agenda


@pytest.fixture
def connecteur(tmp_path, doublure, agenda):
    module = charger("google-agenda", tmp_path, doublure.reglages())
    return module.GoogleAgenda(doublure.reglages(), http=doublure.http, fuseau=PARIS)


@pytest.fixture
def diner(agenda):
    agenda.evenement(PERSO, "diner", a_paris(1, 19), a_paris(1, 21), "Dîner chez Paul")


def ecritures(doublure):
    return [
        r
        for r in doublure.recues
        if r.method in {"POST", "PATCH", "DELETE"} and "calendar" in r.url.path
    ]


def change():
    return sys.modules["atlas_core.rendez_vous"].Change


async def lire(connecteur, debut: str, fin: str | None = None) -> str:
    return await appeler(connecteur, "google_agenda_lire", debut=debut, fin=fin or debut)


async def test_ajouter_va_dans_l_agenda_principal_sans_prevenir_personne(
    doublure, agenda, connecteur
):
    fait = await appeler(
        connecteur, "google_agenda_ajouter", titre="Dentiste", debut="2026-10-01T15:00", alerte=30
    )

    assert fait.annonce == "C'est noté : Dentiste, jeudi 1er octobre à 15 h."
    [envoi] = ecritures(doublure)
    assert (envoi.url.path, envoi.url.params["sendUpdates"]) == (
        f"/calendar/v3/calendars/{PERSO}/events",
        "none",
    )
    assert json.loads(envoi.content) == {
        "summary": "Dentiste",
        "start": {"dateTime": "2026-10-01T15:00:00+02:00", "timeZone": "Europe/Paris"},
        "end": {"dateTime": "2026-10-01T16:00:00+02:00", "timeZone": "Europe/Paris"},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]},
    }
    assert "15 h 00 – 16 h 00 · Dentiste · Perso" in await lire(connecteur, "2026-10-01")


async def test_ajouter_une_journee_ou_dans_un_autre_agenda(doublure, agenda, connecteur):
    fait = await appeler(
        connecteur,
        "google_agenda_ajouter",
        titre="Salon",
        debut="2026-10-07",
        fin="2026-10-09",
        agenda="travail",
        lieu="Paris Expo",
        notes="Stand B12",
    )

    assert (
        fait.annonce
        == "C'est noté dans Travail : Salon, du mercredi 7 octobre au vendredi 9 octobre."
    )
    [envoi] = ecritures(doublure)
    assert "travail%40group.calendar.google.com" in str(envoi.url)
    corps = json.loads(envoi.content)
    assert (corps["end"], corps["location"], corps["description"]) == (
        {"date": "2026-10-10"},
        "Paris Expo",
        "Stand B12",
    )


async def test_l_agenda_principal_masque_recoit_quand_meme_les_ajouts(agenda, connecteur):
    agenda.agendas[PERSO]["selected"] = False  # David le masque dans Google Agenda

    fait = await appeler(
        connecteur, "google_agenda_ajouter", titre="Dentiste", debut="2026-10-01T15:00"
    )
    assert fait.annonce == "C'est noté : Dentiste, jeudi 1er octobre à 15 h."


async def test_le_jour_du_passage_a_l_heure_d_hiver(doublure, agenda, connecteur):
    # Le dimanche 25 octobre 2026 à 3 h, Paris passe de UTC+2 à UTC+1.
    fait = await appeler(
        connecteur, "google_agenda_ajouter", titre="Brunch", debut="2026-10-25T12:30"
    )

    assert fait.annonce == "C'est noté : Brunch, dimanche 25 octobre à 12 h 30."
    [envoi] = ecritures(doublure)
    assert json.loads(envoi.content)["start"]["dateTime"] == "2026-10-25T12:30:00+01:00"
    assert "12 h 30 – 13 h 30 · Brunch · Perso" in await lire(connecteur, "2026-10-25")


async def test_rien_ne_s_ecrit_dans_un_agenda_en_lecture_seule(doublure, agenda, connecteur):
    agenda.evenement(FERIES, "t1", dt.date(2026, 11, 1), dt.date(2026, 11, 2), "Toussaint")
    agenda.agenda("marie@example.com", "Marie", role="freeBusyReader")  # ses disponibilités
    await lire(connecteur, "2026-11-01")

    for nom, arguments in [
        (
            "google_agenda_ajouter",
            {"titre": "Pont", "debut": "2026-11-02", "agenda": "Jours fériés"},
        ),
        ("google_agenda_modifier", {"evenement": "g1", "titre": "Pont"}),
        ("google_agenda_supprimer", {"evenement": "g1"}),
    ]:
        with pytest.raises(ErreurConnecteur) as refus:
            await appeler(connecteur, nom, **arguments)
        assert str(refus.value) == "L'agenda « Jours fériés » ne se modifie pas d'ici."
    with pytest.raises(ErreurConnecteur) as refus:
        await appeler(
            connecteur,
            "google_agenda_ajouter",
            titre="Café",
            debut="2026-11-02T10:00",
            agenda="Marie",
        )
    assert str(refus.value) == "L'agenda « Marie » ne se modifie pas d'ici."
    assert ecritures(doublure) == []


async def test_un_agenda_devenu_en_lecture_seule_refuse_l_ecriture(doublure, agenda, connecteur):
    await lire(connecteur, "2026-10-01")  # Travail se modifie quand Atlas lit la liste…
    agenda.agendas[TRAVAIL]["accessRole"] = "reader"  # … puis son propriétaire le restreint

    with pytest.raises(ErreurConnecteur) as refus:
        await appeler(
            connecteur,
            "google_agenda_ajouter",
            titre="Revue",
            debut="2026-10-02T10:00",
            agenda="Travail",
        )
    assert str(refus.value) == "L'agenda « Travail » ne se modifie pas d'ici."


async def test_deplacer_apres_le_oui_seulement_s_il_n_a_pas_change(
    doublure, agenda, connecteur, diner
):
    await lire(connecteur, "2026-10-01")
    action = await appeler(
        connecteur, "google_agenda_modifier", evenement="g1", debut="2026-10-01T20:00"
    )

    assert isinstance(action, Action)
    assert action.question == "Je déplace « Dîner chez Paul », jeudi 1er octobre, de 19 h à 20 h ?"
    assert ecritures(doublure) == [], "rien avant le « oui »"
    action.executer()
    action.apres()
    [envoi] = ecritures(doublure)
    assert (envoi.method, envoi.headers["if-match"], envoi.url.params["sendUpdates"]) == (
        "PATCH",
        '"1"',
        "none",
    )
    assert envoi.url.path == f"/calendar/v3/calendars/{PERSO}/events/diner"
    assert "20 h 00 – 22 h 00 · Dîner chez Paul" in await lire(connecteur, "2026-10-01")


async def test_une_seule_fois_d_une_serie_change_ou_disparait(doublure, agenda, connecteur):
    agenda.evenement(
        PERSO,
        "yoga",
        a_paris(24, 18, mois=9),
        a_paris(24, 19, mois=9),
        "Yoga",
        recurrence=["RRULE:FREQ=WEEKLY"],
    )
    await lire(connecteur, "2026-10-01", "2026-10-15")

    deplacee = await appeler(
        connecteur, "google_agenda_modifier", evenement="g2", debut="2026-10-08T19:30"
    )
    assert deplacee.question == (
        "Je déplace « Yoga », jeudi 8 octobre, de 18 h à 19 h 30 (cette fois seulement) ?"
    )
    deplacee.executer()
    deplacee.apres()
    with pytest.raises(ErreurConnecteur) as refus:  # les autres fois de la série aussi
        await appeler(connecteur, "google_agenda_supprimer", evenement="g3")
    assert str(refus.value) == "Je ne connais pas « g3 » : relis l'agenda d'abord."
    await lire(connecteur, "2026-10-01", "2026-10-15")
    supprimee = await appeler(connecteur, "google_agenda_supprimer", evenement="g3")
    supprimee.executer()

    assert [r.url.path.rsplit("/", 1)[1] for r in ecritures(doublure)] == [
        "yoga_20261008T160000Z",
        "yoga_20261015T160000Z",
    ]
    lues = await lire(connecteur, "2026-10-01", "2026-10-22")
    assert "19 h 30 – 20 h 30 · Yoga" in lues and "jeudi 15 octobre" not in lues
    assert lues.count(" · Yoga · ") == 3


async def test_changer_le_lieu_et_les_notes(doublure, agenda, connecteur, diner):
    await lire(connecteur, "2026-10-01")
    action = await appeler(
        connecteur,
        "google_agenda_modifier",
        evenement="g1",
        lieu="Chez Marie",
        notes="Apporter le dessert",
    )
    action.executer()

    [envoi] = ecritures(doublure)
    assert json.loads(envoi.content) == {
        "location": "Chez Marie",
        "description": "Apporter le dessert",
    }


async def test_passer_d_une_heure_a_la_journee_entiere_et_retour(
    doublure, agenda, connecteur, diner
):
    # Google fusionne les objets d'un PATCH : l'ancienne forme du début doit être effacée.
    await lire(connecteur, "2026-10-01")
    journee = await appeler(
        connecteur, "google_agenda_modifier", evenement="g1", debut="2026-10-02"
    )
    journee.executer()
    journee.apres()

    [envoi] = ecritures(doublure)
    assert json.loads(envoi.content)["start"] == {
        "date": "2026-10-02",
        "dateTime": None,
        "timeZone": None,
    }
    assert "g1 · journée entière · Dîner chez Paul" in await lire(connecteur, "2026-10-02")

    a_l_heure = await appeler(
        connecteur, "google_agenda_modifier", evenement="g1", debut="2026-10-02T19:00"
    )
    a_l_heure.executer()
    assert "19 h 00 – 20 h 00 · Dîner chez Paul" in await lire(connecteur, "2026-10-02")


async def test_supprimer_apres_le_oui(doublure, agenda, connecteur, diner):
    await lire(connecteur, "2026-10-01")
    action = await appeler(connecteur, "google_agenda_supprimer", evenement="g1")

    assert action.question == "Je supprime « Dîner chez Paul », jeudi 1er octobre à 19 h ?"
    action.executer()
    [envoi] = ecritures(doublure)
    assert (envoi.method, envoi.headers["if-match"], envoi.url.params["sendUpdates"]) == (
        "DELETE",
        '"1"',
        "none",
    )
    assert await lire(connecteur, "2026-10-01") == "Rien dans l'agenda le jeudi 1er octobre 2026."


async def test_un_rendez_vous_change_ou_supprime_entre_temps_n_est_pas_touche(
    agenda, connecteur, diner
):
    await lire(connecteur, "2026-10-01")
    modification = await appeler(
        connecteur, "google_agenda_modifier", evenement="g1", titre="Dîner"
    )
    agenda.changer_ailleurs(PERSO, "diner", summary="Dîner chez Paul et Marie")

    with pytest.raises(change()):
        modification.executer()
    assert modification.ratee == "« Dîner chez Paul » a changé entre-temps : je n'y ai pas touché."

    await lire(connecteur, "2026-10-01")
    suppression = await appeler(connecteur, "google_agenda_supprimer", evenement="g1")
    del agenda.evenements[PERSO]["diner"]
    with pytest.raises(change()):
        suppression.executer()


async def test_un_rendez_vous_avec_des_invites_est_refuse_avant_toute_question(
    doublure, agenda, connecteur
):
    agenda.evenement(
        PERSO,
        "invit",
        a_paris(1, 12),
        a_paris(1, 13),
        "Déjeuner",
        attendees=[{"email": PERSO, "self": True}, {"email": "marie@example.com"}],
    )
    await lire(connecteur, "2026-10-01")

    with pytest.raises(ErreurConnecteur) as refus:
        await appeler(connecteur, "google_agenda_supprimer", evenement="g1")
    assert str(refus.value) == (
        "Ce rendez-vous a des invités : Atlas ne le change pas, pour ne pas leur écrire en ton "
        "nom. Change-le dans Google Agenda."
    )
    assert ecritures(doublure) == []
