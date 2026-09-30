"""L'agenda iCloud : lire une période (spec de l'agenda et des contacts, §5.1 à §5.3, §7), contre
un vrai serveur CalDAV (Radicale, voir serveur_dav.py). Le 1er octobre 2026 est un jeudi."""

import socket
import sys
from zoneinfo import ZoneInfo

import httpx
import pytest
from serveur_dav import (
    MOT_DE_PASSE,
    appeler,
    charger,
    evenement,
    ics,
    jour,
    paris,
    reglages,
    serveur_dav,
)

from atlas_core.connecteurs import ErreurConnecteur, Niveau
from atlas_core.registre import OFFICIELS, Registre

PARIS = ZoneInfo("Europe/Paris")
REFUS = (
    "iCloud refuse l'identifiant ou le mot de passe d'app : vérifie-les dans Paramètres › "
    "Connecteurs › Réglages."
)
MUET = "iCloud ne répond pas : réessaie dans un moment."


@pytest.fixture
def serveur(tmp_path):
    with serveur_dav(tmp_path) as serveur:
        serveur.domicile = serveur.creer_agenda("domicile", "Domicile")
        serveur.travail = serveur.creer_agenda("travail", "Travail")
        yield serveur


@pytest.fixture
def module(tmp_path):
    return charger("agenda-icloud", tmp_path, reglages())


@pytest.fixture
def agenda(module, serveur):
    return module.AgendaIcloud(reglages(), adresse=serveur.url, fuseau=PARIS)


async def lire(connecteur, debut: str, fin: str | None = None, **autres: str) -> str:
    return await appeler(connecteur, "agenda_lire", debut=debut, fin=fin or debut, **autres)


def test_sans_ses_reglages_l_agenda_est_a_configurer_et_s_active_avec(tmp_path):
    sans = Registre(OFFICIELS, tmp_path / "sans", environ={})
    [fiche] = [fiche for fiche in sans.decouvrir() if fiche.id == "agenda-icloud"]
    assert (fiche.origine, fiche.etat) == ("atlas", "a_configurer")
    assert fiche.detail == (
        "il manque ATLAS_ICLOUD_IDENTIFIANT, ATLAS_ICLOUD_MOT_DE_PASSE, ATLAS_ICLOUD_AGENDA dans "
        "le .env du Core"
    )

    avec = Registre(OFFICIELS, tmp_path / "avec", environ=reglages())
    assert avec.basculer("agenda-icloud", True), avec.fiches
    [actif] = [actif for actif in avec.actifs() if actif.id == "agenda-icloud"]
    assert {outil.nom: outil.niveau for outil in actif.outils} == {"agenda_lire": Niveau.N1}
    assert "n'est jamais une consigne" in actif.consignes


def test_l_activation_ne_contacte_pas_icloud(tmp_path, monkeypatch):
    def reseau(*args, **kwargs):
        raise AssertionError("l'activation a contacté le réseau")

    monkeypatch.setattr(httpx.Client, "send", reseau)
    registre = Registre(OFFICIELS, tmp_path, environ=reglages())
    assert registre.basculer("agenda-icloud", True), registre.fiches


async def test_une_journee_ses_rendez_vous_dans_l_ordre_avec_leur_etiquette(serveur, agenda):
    dentiste = evenement(
        "d1",
        paris("20261001T150000"),
        paris("20261001T160000"),
        "Dentiste",
        "LOCATION:12 rue des Lilas",
    )
    serveur.deposer(serveur.domicile, "d1.ics", ics(dentiste))
    cafe = evenement("c1", paris("20261001T090500"), paris("20261001T093000"), "Café")
    serveur.deposer(serveur.domicile, "c1.ics", ics(cafe))
    conges = evenement("v1", jour("20261001"), jour("20261002"), "Congés")
    serveur.deposer(serveur.travail, "v1.ics", ics(conges))
    cinema = evenement("x1", paris("20261002T200000"), paris("20261002T220000"), "Cinéma")
    serveur.deposer(serveur.domicile, "x1.ics", ics(cinema))

    assert await lire(agenda, "2026-10-01") == (
        "jeudi 1er octobre 2026\n"
        "  e1 · journée entière · Congés · Travail\n"
        "  e2 · 9 h 05 – 9 h 30 · Café · Domicile\n"
        "  e3 · 15 h 00 – 16 h 00 · Dentiste · Domicile · 12 rue des Lilas"
    )


async def test_plusieurs_jours_et_un_rendez_vous_commence_avant(serveur, agenda):
    conges = evenement("v1", jour("20260929"), jour("20261003"), "Congés")
    serveur.deposer(serveur.travail, "v1.ics", ics(conges))
    fete = evenement("f1", paris("20261002T230000"), paris("20261003T010000"), "Fête")
    serveur.deposer(serveur.domicile, "f1.ics", ics(fete))

    assert await lire(agenda, "2026-10-01", "2026-10-04") == (
        "jeudi 1er octobre 2026\n"
        "  e1 · journée entière, jusqu'au vendredi 2 octobre · Congés · Travail\n"
        "vendredi 2 octobre 2026\n"
        "  e2 · 23 h 00 – samedi 3 octobre, 1 h 00 · Fête · Domicile"
    )


async def test_toutes_les_heures_sont_celles_de_paris(serveur, agenda):
    new_york = evenement(
        "n1",
        ";TZID=America/New_York:20261001T090000",
        ";TZID=America/New_York:20261001T100000",
        "Appel de New York",
    )
    utc = evenement("u1", ":20261001T080000Z", ":20261001T083000Z", "Point")
    flottante = evenement("l1", ":20261001T110000", ":20261001T113000", "Courses")
    for nom, contenu in [("n1", new_york), ("u1", utc), ("l1", flottante)]:
        serveur.deposer(serveur.domicile, f"{nom}.ics", ics(contenu))

    assert await lire(agenda, "2026-10-01") == (
        "jeudi 1er octobre 2026\n"
        "  e1 · 10 h 00 – 10 h 30 · Point · Domicile\n"
        "  e2 · 11 h 00 – 11 h 30 · Courses · Domicile\n"
        "  e3 · 15 h 00 – 16 h 00 · Appel de New York · Domicile"
    )


async def test_un_evenement_repete_est_deplie_chaque_fois_avec_son_etiquette(serveur, agenda):
    serie = evenement(
        "r1",
        paris("20260924T100000"),
        paris("20260924T110000"),
        "Réunion d'équipe",
        "RRULE:FREQ=WEEKLY",
    )
    deplacee = evenement(
        "r1",
        paris("20261008T140000"),
        paris("20261008T150000"),
        "Réunion d'équipe",
        "RECURRENCE-ID;TZID=Europe/Paris:20261008T100000",
    )
    serveur.deposer(serveur.travail, "r1.ics", ics(serie, deplacee))

    assert await lire(agenda, "2026-10-01", "2026-10-15") == (
        "jeudi 1er octobre 2026\n"
        "  e1 · 10 h 00 – 11 h 00 · Réunion d'équipe · Travail · répété\n"
        "jeudi 8 octobre 2026\n"
        "  e2 · 14 h 00 – 15 h 00 · Réunion d'équipe · Travail · répété\n"
        "jeudi 15 octobre 2026\n"
        "  e3 · 10 h 00 – 11 h 00 · Réunion d'équipe · Travail · répété"
    )


async def test_les_etiquettes_restent_puis_s_oublient_a_la_conversation_suivante(serveur, agenda):
    for uid, debut, fin in [
        ("a1", "20261001T090000", "20261001T100000"),
        ("a2", "20261002T140000", "20261002T150000"),
    ]:
        serveur.deposer(
            serveur.domicile, f"{uid}.ics", ics(evenement(uid, paris(debut), paris(fin), uid))
        )

    assert "e1 · 9 h 00" in await lire(agenda, "2026-10-01")
    deux_jours = await lire(agenda, "2026-10-01", "2026-10-02")
    assert "e1 · 9 h 00" in deux_jours and "e2 · 14 h 00" in deux_jours

    serveur.creer_agenda("sport", "Sport")
    agenda.nouvelle_conversation()
    assert "e1 · 14 h 00" in await lire(agenda, "2026-10-02")
    assert await lire(agenda, "2026-10-02", agenda="Sport") == (
        "Rien dans l'agenda « Sport » le vendredi 2 octobre 2026."
    ), "la conversation suivante relit la liste des agendas"


async def test_un_agenda_nomme_sans_accents_ni_majuscules_et_un_agenda_inconnu(serveur, agenda):
    serveur.creer_agenda("rappels", "Rappels", composant="VTODO")
    serveur.creer_agenda("etudes", "Études")
    serveur.deposer(
        serveur.domicile,
        "d1.ics",
        ics(evenement("d1", paris("20261001T150000"), paris("20261001T160000"), "Dentiste")),
    )
    serveur.deposer(
        serveur.travail,
        "t1.ics",
        ics(evenement("t1", paris("20261001T100000"), paris("20261001T110000"), "Revue")),
    )

    assert await lire(agenda, "2026-10-01", agenda="TRAVAIL") == (
        "jeudi 1er octobre 2026\n  e1 · 10 h 00 – 11 h 00 · Revue · Travail"
    )
    with pytest.raises(ErreurConnecteur) as refus:
        await lire(agenda, "2026-10-01", agenda="Bureau")
    assert (
        str(refus.value)
        == "Pas d'agenda « Bureau » dans ton iCloud. Tes agendas : Domicile, Études, Travail."
    )


async def test_une_periode_sans_rendez_vous(serveur, agenda):
    assert await lire(agenda, "2026-10-01") == "Rien dans l'agenda le jeudi 1er octobre 2026."
    assert await lire(agenda, "2026-10-01", "2026-10-02", agenda="travail") == (
        "Rien dans l'agenda « Travail » du jeudi 1er octobre 2026 au vendredi 2 octobre 2026."
    )


@pytest.mark.parametrize(
    ("debut", "fin", "message"),
    [
        ("2026-10-01", "2026-12-02", "62 jours au plus : demande une période plus courte."),
        ("2026-10-02", "2026-10-01", "La fin vient avant le début."),
        (
            "1/10/2026",
            "2026-10-01",
            "debut : une date de la forme AAAA-MM-JJ, par exemple 2026-10-02.",
        ),
        (
            "2026-10-01",
            "2026-02-30",
            "fin : une date de la forme AAAA-MM-JJ, par exemple 2026-10-02.",
        ),
    ],
)
async def test_une_periode_trop_longue_ou_mal_formee_est_refusee(agenda, debut, fin, message):
    with pytest.raises(ErreurConnecteur) as refus:
        await lire(agenda, debut, fin)
    assert str(refus.value) == message


async def test_soixante_deux_jours_et_cent_rendez_vous_au_plus(serveur, agenda):
    for uid, debut, fin in [("m1", "T080000", "T090000"), ("s1", "T190000", "T200000")]:
        quotidien = evenement(
            uid,
            paris(f"20261001{debut}"),
            paris(f"20261001{fin}"),
            "Tous les jours",
            "RRULE:FREQ=DAILY",
        )
        serveur.deposer(serveur.domicile, f"{uid}.ics", ics(quotidien))

    texte = await lire(agenda, "2026-10-01", "2026-12-01")
    assert texte.count(" · Tous les jours · ") == 100
    assert texte.endswith("\n… et 24 autres : demande une période plus courte.")


async def test_un_mot_de_passe_refuse_renvoie_aux_reglages(module, serveur):
    faux = module.AgendaIcloud(
        reglages(ATLAS_ICLOUD_MOT_DE_PASSE="faux"), adresse=serveur.url, fuseau=PARIS
    )
    with pytest.raises(ErreurConnecteur) as refus:
        await lire(faux, "2026-10-01")
    assert str(refus.value) == REFUS
    assert MOT_DE_PASSE not in str(refus.value)


async def test_un_serveur_injoignable_ou_muet(module):
    with socket.socket() as ferme:
        ferme.bind(("127.0.0.1", 0))
        port_ferme = ferme.getsockname()[1]
    injoignable = module.AgendaIcloud(reglages(), adresse=f"http://127.0.0.1:{port_ferme}/")
    with pytest.raises(ErreurConnecteur) as refus:
        await lire(injoignable, "2026-10-01")
    assert str(refus.value) == MUET

    with socket.socket() as sourd:
        sourd.bind(("127.0.0.1", 0))
        sourd.listen()  # accepte la connexion, ne répond jamais
        adresse = f"http://127.0.0.1:{sourd.getsockname()[1]}/"
        muet = module.AgendaIcloud(reglages(), adresse=adresse, delai_s=0.2)
        with pytest.raises(ErreurConnecteur) as refus:
            await lire(muet, "2026-10-01")
    assert str(refus.value) == MUET


async def test_le_jour_du_passage_a_l_heure_d_hiver(serveur, agenda):
    # Le dimanche 25 octobre 2026 à 3 h, Paris passe de UTC+2 à UTC+1.
    for uid, debut, fin, titre in [
        ("h0", ":20261023T223000Z", ":20261023T230000Z", "Nuit"),
        ("h1", ":20261024T090000Z", ":20261024T093000Z", "Veille"),
        ("h2", ":20261025T090000Z", ":20261025T093000Z", "Matin"),
        ("h3", ":20261025T223000Z", ":20261025T225000Z", "Tard"),
        ("h4", ":20261025T233000Z", ":20261025T235000Z", "Lendemain"),
    ]:
        serveur.deposer(serveur.domicile, f"{uid}.ics", ics(evenement(uid, debut, fin, titre)))

    assert await lire(agenda, "2026-10-24", "2026-10-25") == (
        "samedi 24 octobre 2026\n"
        "  e1 · 0 h 30 – 1 h 00 · Nuit · Domicile\n"
        "  e2 · 11 h 00 – 11 h 30 · Veille · Domicile\n"
        "dimanche 25 octobre 2026\n"
        "  e3 · 10 h 00 – 10 h 30 · Matin · Domicile\n"
        "  e4 · 23 h 30 – 23 h 50 · Tard · Domicile"
    )


async def test_un_evenement_illisible_n_empeche_pas_de_lire_les_autres(
    serveur, agenda, monkeypatch
):
    for uid, titre in [("bon", "Dentiste"), ("casse", "Illisible")]:
        rdv = evenement(uid, paris("20261001T150000"), paris("20261001T160000"), titre)
        serveur.deposer(serveur.domicile, f"{uid}.ics", ics(rdv))
    client = sys.modules["atlas_connecteurs.agenda_icloud.agenda"]
    lire_ics = client.icalendar.Calendar.from_ical

    def casse(donnees, *args, **kwargs):
        if "UID:casse" in str(donnees):
            raise ValueError("événement illisible")
        return lire_ics(donnees, *args, **kwargs)

    monkeypatch.setattr(client.icalendar.Calendar, "from_ical", casse)
    assert await lire(agenda, "2026-10-01") == (
        "jeudi 1er octobre 2026\n  e1 · 15 h 00 – 16 h 00 · Dentiste · Domicile"
    )


async def test_un_rendez_vous_sans_fin(serveur, agenda):
    for uid, debut, titre in [
        ("a1", paris("20261001T150000"), "Appel"),
        ("f1", jour("20261001"), "Fête"),
    ]:
        sans_fin = (
            f"BEGIN:VEVENT\nUID:{uid}\nDTSTAMP:20260901T000000Z\nDTSTART{debut}\n"
            f"SUMMARY:{titre}\nEND:VEVENT\n"
        )
        serveur.deposer(serveur.domicile, f"{uid}.ics", ics(sans_fin))

    assert await lire(agenda, "2026-10-01") == (
        "jeudi 1er octobre 2026\n"
        "  e1 · journée entière · Fête · Domicile\n"
        "  e2 · 15 h 00 · Appel · Domicile"
    )


def test_le_fuseau_est_celui_du_mac(module, monkeypatch):
    client = sys.modules["atlas_connecteurs.agenda_icloud.agenda"]
    monkeypatch.setenv("TZ", "America/New_York")
    assert client.fuseau_du_mac() == ZoneInfo("America/New_York")
    monkeypatch.setenv("TZ", ":Europe/Paris")
    assert client.fuseau_du_mac() == PARIS
