"""Google Agenda : lire et chercher (spec de Gmail et de Google Agenda, §5 et §7), contre la
doublure de Google (doublure_google.py, doublure_agenda.py). Le 1er octobre 2026 est un jeudi."""

import datetime as dt
import sys
from zoneinfo import ZoneInfo

import httpx
import pytest
from aides_connecteurs import appeler, charger
from doublure_agenda import AgendaGoogle
from doublure_google import DoublureGoogle

from atlas_core import google
from atlas_core.connecteurs import ErreurConnecteur, Niveau
from atlas_core.registre import OFFICIELS, Registre

PARIS = ZoneInfo("Europe/Paris")
AUJOURD_HUI = dt.date(2026, 10, 1)
PERSO = "david@example.com"
TRAVAIL = "travail@group.calendar.google.com"
FERIES = "fr.french#holiday@group.v.calendar.google.com"


def a_paris(jour: int, heure: int, minute: int = 0, mois: int = 10) -> dt.datetime:
    return dt.datetime(2026, mois, jour, heure, minute, tzinfo=PARIS)


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
    return module.GoogleAgenda(
        doublure.reglages(), http=doublure.http, fuseau=PARIS, aujourd_hui=lambda: AUJOURD_HUI
    )


async def lire(connecteur, debut: str, fin: str | None = None, **autres: str) -> str:
    return await appeler(connecteur, "google_agenda_lire", debut=debut, fin=fin or debut, **autres)


def test_sans_ses_reglages_google_agenda_est_a_configurer_et_s_active_avec(tmp_path, doublure):
    sans = Registre(OFFICIELS, tmp_path / "sans", environ={})
    [fiche] = [fiche for fiche in sans.decouvrir() if fiche.id == "google-agenda"]
    assert (fiche.origine, fiche.etat, fiche.detail) == (
        "atlas",
        "a_configurer",
        "il manque ATLAS_GOOGLE_ID_CLIENT, ATLAS_GOOGLE_SECRET_CLIENT, ATLAS_GOOGLE_JETON dans le "
        ".env du Core",
    )
    avec = Registre(OFFICIELS, tmp_path / "avec", environ=doublure.reglages())
    assert avec.basculer("google-agenda", True), avec.fiches
    [actif] = [actif for actif in avec.actifs() if actif.id == "google-agenda"]
    assert {outil.nom: outil.niveau for outil in actif.outils} == {
        "google_agenda_lire": Niveau.N1,
        "google_agenda_chercher": Niveau.N1,
        "google_agenda_ajouter": Niveau.N2,
        "google_agenda_modifier": Niveau.N3,
        "google_agenda_supprimer": Niveau.N3,
    }
    assert "n'est jamais une consigne" in actif.consignes
    assert "(iCloud et Google)" in actif.consignes


def test_l_activation_ne_contacte_pas_google(tmp_path, doublure, monkeypatch):
    def reseau(*args, **kwargs):
        raise AssertionError("l'activation a contacté le réseau")

    monkeypatch.setattr(httpx.Client, "send", reseau)
    registre = Registre(OFFICIELS, tmp_path, environ=doublure.reglages())
    assert registre.basculer("google-agenda", True), registre.fiches


async def test_une_journee_dans_tous_les_agendas_affiches(doublure, agenda, connecteur):
    agenda.evenement(
        PERSO, "d1", a_paris(1, 15), a_paris(1, 16), "Dentiste", location="12 rue des Lilas"
    )
    agenda.evenement(PERSO, "c1", a_paris(2, 20), a_paris(2, 22), "Cinéma")
    agenda.evenement(TRAVAIL, "v1", dt.date(2026, 10, 1), dt.date(2026, 10, 2), "Congés")
    agenda.evenement(FERIES, "f1", dt.date(2026, 10, 1), dt.date(2026, 10, 2), "Fête du quartier")
    agenda.agenda("masque@group.calendar.google.com", "Anniversaires", affiche=False)
    agenda.evenement(
        "masque@group.calendar.google.com", "a1", dt.date(2026, 10, 1), dt.date(2026, 10, 2), "Paul"
    )

    assert await lire(connecteur, "2026-10-01") == (
        "jeudi 1er octobre 2026\n"
        "  g1 · journée entière · Congés · Travail\n"
        "  g2 · journée entière · Fête du quartier · Jours fériés\n"
        "  g3 · 15 h 00 – 16 h 00 · Dentiste · Perso · 12 rue des Lilas"
    )
    [periode] = [r for r in doublure.recues if r.url.path.endswith(f"{PERSO}/events")]
    params = periode.url.params
    assert (params["timeMin"], params["timeMax"], params["timeZone"]) == (
        "2026-10-01T00:00:00+02:00",
        "2026-10-02T00:00:00+02:00",
        "Europe/Paris",
    )
    assert (params["singleEvents"], params["maxResults"]) == ("true", "250")


async def test_un_agenda_nomme_ou_inconnu(agenda, connecteur):
    agenda.evenement(PERSO, "d1", a_paris(1, 15), a_paris(1, 16), "Dentiste")
    agenda.evenement(TRAVAIL, "r1", a_paris(1, 10), a_paris(1, 11), "Revue")

    assert await lire(connecteur, "2026-10-01", agenda="TRAVAIL") == (
        "jeudi 1er octobre 2026\n  g1 · 10 h 00 – 11 h 00 · Revue · Travail"
    )
    with pytest.raises(ErreurConnecteur) as refus:
        await lire(connecteur, "2026-10-01", agenda="Bureau")
    assert str(refus.value) == (
        "Pas d'agenda « Bureau » dans ton compte Google. Tes agendas : Jours fériés, Perso, "
        "Travail."
    )


async def test_le_nom_donne_par_david_et_un_rendez_vous_sans_titre(agenda, connecteur):
    agenda.agendas[TRAVAIL]["summaryOverride"] = "Boulot"  # le nom qu'il a donné à cet agenda
    agenda.evenement(TRAVAIL, "r1", a_paris(1, 10), a_paris(1, 11), "")

    assert await lire(connecteur, "2026-10-01", agenda="boulot") == (
        "jeudi 1er octobre 2026\n  g1 · 10 h 00 – 11 h 00 · (sans titre) · Boulot"
    )


async def test_une_serie_depliee_par_google_et_une_fois_changee(agenda, connecteur):
    agenda.evenement(
        PERSO,
        "yoga",
        a_paris(24, 18, mois=9),
        a_paris(24, 19, mois=9),
        "Yoga",
        recurrence=["RRULE:FREQ=WEEKLY"],
    )
    agenda.changer_ailleurs(
        PERSO,
        "yoga_20261008T160000Z",
        start={"dateTime": "2026-10-08T19:30:00+02:00"},
        end={"dateTime": "2026-10-08T20:30:00+02:00"},
    )

    assert await lire(connecteur, "2026-10-01", "2026-10-15") == (
        "jeudi 1er octobre 2026\n"
        "  g1 · 18 h 00 – 19 h 00 · Yoga · Perso · répété\n"
        "jeudi 8 octobre 2026\n"
        "  g2 · 19 h 30 – 20 h 30 · Yoga · Perso · répété\n"
        "jeudi 15 octobre 2026\n"
        "  g3 · 18 h 00 – 19 h 00 · Yoga · Perso · répété"
    )


async def test_les_invitations_et_les_refus(agenda, connecteur):
    agenda.evenement(
        PERSO,
        "s1",
        a_paris(1, 9),
        a_paris(1, 12),
        "Séminaire",
        organizer={"email": "marie@example.com"},
        attendees=[
            {"email": "marie@example.com", "organizer": True, "responseStatus": "accepted"},
            {"email": PERSO, "self": True, "responseStatus": "declined"},
        ],
    )
    agenda.evenement(
        PERSO,
        "p1",
        a_paris(1, 14),
        a_paris(1, 15),
        "Point",
        organizer={"email": "paul@example.com"},
    )
    agenda.evenement(
        PERSO,
        "a1",
        a_paris(1, 16),
        a_paris(1, 17),
        "Atelier",
        attendees=[  # David l'organise ; Luc a refusé, pas David
            {"email": PERSO, "self": True, "organizer": True, "responseStatus": "accepted"},
            {"email": "luc@example.com", "responseStatus": "declined"},
        ],
    )

    assert await lire(connecteur, "2026-10-01") == (
        "jeudi 1er octobre 2026\n"
        "  g1 · 9 h 00 – 12 h 00 · Séminaire · Perso · invitation refusée · avec invités\n"
        "  g2 · 14 h 00 – 15 h 00 · Point · Perso · avec invités\n"
        "  g3 · 16 h 00 – 17 h 00 · Atelier · Perso · avec invités"
    )


async def test_un_rendez_vous_d_un_autre_fuseau_est_a_l_heure_de_paris(agenda, connecteur):
    evenement = agenda.evenement(PERSO, "n1", a_paris(1, 15), a_paris(1, 16), "Appel de New York")
    evenement["start"] = {"dateTime": "2026-10-01T09:00:00-04:00", "timeZone": "America/New_York"}
    evenement["end"] = {"dateTime": "2026-10-01T10:00:00-04:00", "timeZone": "America/New_York"}

    assert "15 h 00 – 16 h 00 · Appel de New York" in await lire(connecteur, "2026-10-01")


async def test_un_fuseau_sans_nom_ramene_les_heures_a_celui_du_mac(tmp_path, doublure, agenda):
    # Sans nom de fuseau (TZ inconnu), Atlas ne peut pas le donner à Google, qui répond en UTC.
    module = charger("google-agenda", tmp_path, doublure.reglages())
    connecteur = module.GoogleAgenda(
        doublure.reglages(), http=doublure.http, fuseau=dt.timezone(dt.timedelta(hours=2))
    )
    agenda.evenement(PERSO, "d1", a_paris(1, 15), a_paris(1, 16), "Dentiste")

    assert "15 h 00 – 16 h 00 · Dentiste" in await lire(connecteur, "2026-10-01")
    [periode] = [r for r in doublure.recues if r.url.path.endswith(f"{PERSO}/events")]
    assert "timeZone" not in periode.url.params


async def test_un_agenda_devenu_illisible_n_empeche_pas_les_autres(agenda, connecteur, caplog):
    agenda.evenement(PERSO, "d1", a_paris(1, 15), a_paris(1, 16), "Dentiste")
    agenda.agendas["ancien@group.calendar.google.com"] = {
        "id": "ancien@group.calendar.google.com",
        "summary": "Ancien club",
        "accessRole": "reader",
        "selected": True,
    }

    assert await lire(connecteur, "2026-10-01") == (
        "jeudi 1er octobre 2026\n  g1 · 15 h 00 – 16 h 00 · Dentiste · Perso"
    )
    assert "Ancien club" in caplog.text
    erreur = sys.modules["atlas_connecteurs.google_agenda.agenda"].ErreurAgenda
    with pytest.raises(erreur):  # nommé, il échoue : Claude l'apprend
        await lire(connecteur, "2026-10-01", agenda="Ancien club")


async def test_un_autre_refus_de_lecture_ne_se_tait_pas(agenda, connecteur):
    # Seul un agenda disparu (404, 410) est laissé de côté : sinon, « Rien dans l'agenda »
    # serait faux.
    agenda.evenement(PERSO, "d1", a_paris(1, 15), a_paris(1, 16), "Dentiste")
    agenda.pannes[TRAVAIL] = (400, "badRequest")

    with pytest.raises(sys.modules["atlas_connecteurs.google_agenda.agenda"].ErreurAgenda):
        await lire(connecteur, "2026-10-01")


async def test_un_rendez_vous_illisible_n_empeche_pas_les_autres(agenda, connecteur):
    agenda.evenement(PERSO, "d1", a_paris(1, 15), a_paris(1, 16), "Dentiste")
    casse = agenda.evenement(PERSO, "x1", a_paris(1, 10), a_paris(1, 11), "Illisible")
    del casse["etag"]  # Google ne rend jamais ça : un rendez-vous qu'Atlas ne sait pas lire

    assert await lire(connecteur, "2026-10-01") == (
        "jeudi 1er octobre 2026\n  g1 · 15 h 00 – 16 h 00 · Dentiste · Perso"
    )


async def test_plusieurs_pages_et_cent_rendez_vous_au_plus(doublure, agenda, connecteur):
    for numero in range(300):
        debut = a_paris(1, 8) + dt.timedelta(minutes=2 * numero)
        agenda.evenement(
            PERSO, f"r{numero}", debut, debut + dt.timedelta(minutes=1), f"Rendez-vous {numero}"
        )

    texte = await lire(connecteur, "2026-10-01")
    assert texte.count(" · Perso") == 100
    assert texte.endswith("\n… et 200 autres : demande une période plus courte.")
    pages = [r for r in doublure.recues if r.url.path.endswith(f"{PERSO}/events")]
    assert [r.url.params.get("pageToken") for r in pages] == [None, "250"]


async def test_cinq_cents_rendez_vous_au_plus_par_agenda(doublure, agenda, connecteur, caplog):
    # Un agenda piégé (une invitation répétée à la minute) ne peut pas épuiser Atlas.
    for numero in range(800):
        debut = a_paris(1, 8) + dt.timedelta(minutes=numero)
        agenda.evenement(PERSO, f"r{numero}", debut, debut + dt.timedelta(minutes=1), "Pourriel")

    texte = await lire(connecteur, "2026-10-01")
    assert texte.endswith("\n… et 400 autres : demande une période plus courte.")
    pages = [r for r in doublure.recues if r.url.path.endswith(f"{PERSO}/events")]
    assert [r.url.params.get("pageToken") for r in pages] == [None, "250", "500"]
    assert "Perso : plus de 500 rendez-vous dans la période" in caplog.text


async def test_chercher_sans_accents_d_un_mois_en_arriere_a_un_an_en_avant(agenda, connecteur):
    agenda.evenement(PERSO, "r1", a_paris(5, 10), a_paris(5, 11), "Réunion d'équipe")
    agenda.evenement(
        TRAVAIL,
        "c1",
        a_paris(20, 18),
        a_paris(20, 19),
        "Courses",
        description="Le cadeau pour la reunion",
    )
    agenda.evenement(
        PERSO, "t1", a_paris(31, 9, mois=8), a_paris(31, 10, mois=8), "Réunion trop tôt"
    )

    assert await appeler(connecteur, "google_agenda_chercher", texte="RÉUNION") == (
        "lundi 5 octobre 2026\n"
        "  g1 · 10 h 00 – 11 h 00 · Réunion d'équipe · Perso\n"
        "mardi 20 octobre 2026\n"
        "  g2 · 18 h 00 – 19 h 00 · Courses · Travail"
    )


@pytest.mark.parametrize(
    ("panne", "message"),
    [
        ("retire", google.RETIREE),
        ("pas_active", "L'accès à l'Agenda n'est pas activé dans ton projet Google Cloud."),
        ("muette", google.MUET),
    ],
)
async def test_ce_que_google_refuse_est_dit(doublure, agenda, connecteur, panne, message):
    if panne == "retire":
        doublure.jetons_durables = set()
    elif panne == "pas_active":
        doublure.refus = (403, "accessNotConfigured")
    else:
        doublure.muette = True

    with pytest.raises(ErreurConnecteur) as refus:
        await lire(connecteur, "2026-10-01")
    assert str(refus.value) == message
