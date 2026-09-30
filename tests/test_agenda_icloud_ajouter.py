"""L'agenda iCloud : ajouter un rendez-vous (spec de l'agenda et des contacts, §5.4, §7), contre un
vrai serveur CalDAV (Radicale, voir serveur_dav.py). Le 1er octobre 2026 est un jeudi."""

from zoneinfo import ZoneInfo

import pytest
from serveur_dav import appeler, charger, reglages, serveur_dav

from atlas_core.connecteurs import ErreurConnecteur, Fait

PARIS = ZoneInfo("Europe/Paris")


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


async def lire(connecteur, debut: str, fin: str | None = None) -> str:
    return await appeler(connecteur, "agenda_lire", debut=debut, fin=fin or debut)


async def ajouter(connecteur, **arguments: object) -> Fait:
    return await appeler(connecteur, "agenda_ajouter", **arguments)


async def test_ajouter_a_l_heure_dans_l_agenda_des_reglages(serveur, agenda):
    fait = await ajouter(
        agenda, titre="Dentiste", debut="2026-10-01T15:00", lieu="12 rue des Lilas"
    )

    assert fait == Fait(
        "C'est ajouté à l'agenda « Domicile ».", "C'est noté : Dentiste, jeudi 1er octobre à 15 h."
    )
    assert await lire(agenda, "2026-10-01") == (
        "jeudi 1er octobre 2026\n  e1 · 15 h 00 – 16 h 00 · Dentiste · Domicile · 12 rue des Lilas"
    )
    [garde] = serveur.contenus(serveur.domicile)
    assert "DTSTART;TZID=Europe/Paris:20261001T150000" in garde
    assert "ATTENDEE" not in garde and "ORGANIZER" not in garde
    assert serveur.contenus(serveur.travail) == []
    [(methode, _, conditions, envoye)] = serveur.ecrits
    assert (methode, conditions["If-None-Match"]) == ("PUT", "*"), "un ajout ne remplace rien"
    assert "BEGIN:VTIMEZONE" in envoye and "TZID:Europe/Paris" in envoye


async def test_ajouter_une_journee_entiere_ou_plusieurs(agenda):
    une = await ajouter(agenda, titre="Congés", debut="2026-10-05")
    plusieurs = await ajouter(agenda, titre="Salon", debut="2026-10-07", fin="2026-10-09")

    assert une.annonce == "C'est noté : Congés, lundi 5 octobre."
    assert plusieurs.annonce == "C'est noté : Salon, du mercredi 7 octobre au vendredi 9 octobre."
    assert await lire(agenda, "2026-10-05", "2026-10-09") == (
        "lundi 5 octobre 2026\n"
        "  e1 · journée entière · Congés · Domicile\n"
        "mercredi 7 octobre 2026\n"
        "  e2 · journée entière, jusqu'au vendredi 9 octobre · Salon · Domicile"
    )


async def test_ajouter_avec_une_fin_des_notes_et_une_alerte(serveur, agenda):
    fait = await ajouter(
        agenda,
        titre="Appeler le garage",
        debut="2026-10-02T09:30",
        fin="2026-10-02T09:45",
        notes="Pour le contrôle technique",
        alerte=30,
    )

    assert fait.annonce == "C'est noté : Appeler le garage, vendredi 2 octobre à 9 h 30."
    assert "9 h 30 – 9 h 45 · Appeler le garage" in await lire(agenda, "2026-10-02")
    [garde] = serveur.contenus(serveur.domicile)
    assert "DESCRIPTION:Pour le contrôle technique" in garde
    assert "BEGIN:VALARM" in garde and "TRIGGER:-PT30M" in garde


async def test_ajouter_dans_un_autre_agenda_ou_un_agenda_inconnu(module, serveur, agenda):
    fait = await ajouter(agenda, titre="Revue", debut="2026-10-01T10:00", agenda="travail")

    assert fait.annonce == "C'est noté dans Travail : Revue, jeudi 1er octobre à 10 h."
    assert len(serveur.contenus(serveur.travail)) == 1
    with pytest.raises(ErreurConnecteur) as refus:
        await ajouter(agenda, titre="Revue", debut="2026-10-01T10:00", agenda="Bureau")
    assert str(refus.value) == (
        "Pas d'agenda « Bureau » dans ton iCloud. Tes agendas : Domicile, Travail."
    )
    mal_regle = module.AgendaIcloud(
        reglages(ATLAS_ICLOUD_AGENDA="Maison"), adresse=serveur.url, fuseau=PARIS
    )
    with pytest.raises(ErreurConnecteur) as refus:
        await ajouter(mal_regle, titre="Revue", debut="2026-10-01T10:00")
    assert str(refus.value) == (
        "Pas d'agenda « Maison » dans ton iCloud. Tes agendas : Domicile, Travail."
    )


async def test_un_agenda_en_lecture_seule_refuse_l_ajout(serveur, agenda):
    serveur.interdire(serveur.travail)

    with pytest.raises(ErreurConnecteur) as refus:
        await ajouter(agenda, titre="Revue", debut="2026-10-01T10:00", agenda="Travail")
    assert str(refus.value) == "L'agenda « Travail » ne se modifie pas d'ici."


async def test_un_titre_et_des_notes_reviennent_tels_quels(serveur, agenda):
    titre = "Déjeuner ; Paul, Marie"
    await ajouter(agenda, titre=titre, debut="2026-10-25T12:30", notes="Menu : 1, 2 ; 3\nRéserver")

    assert await lire(agenda, "2026-10-25") == (
        f"dimanche 25 octobre 2026\n  e1 · 12 h 30 – 13 h 30 · {titre} · Domicile"
    )
    [garde] = serveur.contenus(serveur.domicile)
    assert "DTSTART;TZID=Europe/Paris:20261025T123000" in garde
    assert "DESCRIPTION:Menu : 1\\, 2 \\; 3\\nRéserver" in garde
    trouve = await appeler(
        agenda, "agenda_chercher", texte="1, 2 ; 3", debut="2026-10-25", fin="2026-10-25"
    )
    assert f"· {titre} ·" in trouve


MAL_FORME = (
    "debut : AAAA-MM-JJTHH:MM pour une heure, par exemple 2026-10-02T15:00, ou AAAA-MM-JJ pour "
    "une journée entière."
)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"titre": " ", "debut": "2026-10-01T10:00"}, "Donne un titre au rendez-vous."),
        ({"titre": "Revue"}, "debut : le jour du rendez-vous, et son heure s'il en a une."),
        ({"titre": "Revue", "debut": "demain à 10 h"}, MAL_FORME),
        ({"titre": "Revue", "debut": "2026-10-01T25:00"}, MAL_FORME),
        (
            {"titre": "Revue", "debut": "2026-10-01T10:00", "fin": "2026-10-01T09:00"},
            "La fin vient avant le début.",
        ),
        (
            {"titre": "Revue", "debut": "2026-10-03", "fin": "2026-10-02"},
            "La fin vient avant le début.",
        ),
        (
            {"titre": "Revue", "debut": "2026-10-01", "fin": "2026-10-01T09:00"},
            "debut et fin : deux dates avec heure, ou deux dates pour une journée entière.",
        ),
        (
            {"titre": "Revue", "debut": "2026-10-01T10:00", "alerte": "bientôt"},
            "alerte : un nombre de minutes avant le début, par exemple 30.",
        ),
        (
            {"titre": "Revue", "debut": "2026-10-01T10:00", "alerte": -5},
            "alerte : un nombre de minutes avant le début, par exemple 30.",
        ),
    ],
)
async def test_un_ajout_mal_demande_est_refuse_sans_rien_ecrire(
    serveur, agenda, arguments, message
):
    with pytest.raises(ErreurConnecteur) as refus:
        await ajouter(agenda, **arguments)
    assert str(refus.value) == message
    assert serveur.contenus(serveur.domicile) == []
