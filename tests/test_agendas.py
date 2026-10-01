"""Le moteur d'agenda commun (spec de Gmail et de Google Agenda, D10) : ce qu'il apporte en plus
de l'agenda iCloud, pour Google Agenda. L'agenda iCloud, branché dessus, garde ses propres
tests ; ici, un faux calendrier en mémoire. Le 1er octobre 2026 est un jeudi."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from atlas_core.agendas import ConnecteurAgenda
from atlas_core.connecteurs import ErreurConnecteur, Niveau
from atlas_core.rendez_vous import Agenda, RendezVous, jour_de

PARIS = ZoneInfo("Europe/Paris")
PERSO = Agenda("Perso", "perso@example.com", principal=True)
TRAVAIL = Agenda("Travail", "travail@example.com")
FERIES = Agenda("Jours fériés", "feries@example.com", lecture_seule=True)


def a_paris(jour: int, heure: int) -> dt.datetime:
    return dt.datetime(2026, 10, jour, heure, tzinfo=PARIS)


class FauxCalendrier:
    fuseau = PARIS

    def __init__(self, agendas: list[Agenda], rendezvous: list[RendezVous] = ()) -> None:
        self._agendas = agendas
        self.rendezvous = list(rendezvous)
        self.ecrits: list[tuple] = []

    def oublier(self) -> None:
        pass

    def agendas(self) -> list[Agenda]:
        return self._agendas

    def lire(self, debut, fin, agenda=None) -> list[RendezVous]:
        return [
            r
            for r in self.rendezvous
            if (agenda is None or r.agenda == agenda) and debut <= jour_de(r.debut) <= fin
        ]

    def ajouter(self, agenda, titre, debut, fin, **options) -> None:
        self.ecrits.append(("ajouter", agenda.nom, titre))

    def modifier(self, rendezvous, **changements) -> None:
        self.ecrits.append(("modifier", rendezvous.evenement))

    def supprimer(self, rendezvous) -> None:
        self.ecrits.append(("supprimer", rendezvous.evenement))


def google(calendrier: FauxCalendrier) -> ConnecteurAgenda:
    return ConnecteurAgenda(
        calendrier,
        service="Google",
        prefixe="google_agenda",
        lettre="g",
        application="Google Agenda",
        compte="compte Google",
    )


async def appeler(connecteur, nom: str, **arguments):
    [outil] = [outil for outil in connecteur.outils() if outil.nom == nom]
    return await outil.gestionnaire(arguments)


def rendezvous(agenda: Agenda, titre: str, **autres) -> RendezVous:
    return RendezVous(
        agenda=agenda,
        evenement=titre.lower(),
        etag='"1"',
        titre=titre,
        debut=a_paris(1, 10),
        fin=a_paris(1, 11),
        **autres,
    )


async def test_les_outils_prennent_le_prefixe_et_les_etiquettes_la_lettre():
    connecteur = google(FauxCalendrier([PERSO], [rendezvous(PERSO, "Revue")]))

    assert {outil.nom: outil.niveau for outil in connecteur.outils()} == {
        "google_agenda_lire": Niveau.N1,
        "google_agenda_chercher": Niveau.N1,
        "google_agenda_ajouter": Niveau.N2,
        "google_agenda_modifier": Niveau.N3,
        "google_agenda_supprimer": Niveau.N3,
    }
    descriptions = " ".join(outil.description for outil in connecteur.outils())
    assert "l'agenda Google de David" in descriptions and "(g1, g2…)" in descriptions
    assert "sinon son agenda principal" in descriptions
    avec_defaut = ConnecteurAgenda(
        FauxCalendrier([PERSO]),
        service="iCloud",
        prefixe="agenda",
        lettre="e",
        application="Calendrier",
        defaut="Perso",
    )
    assert "sinon celui de ses réglages" in " ".join(o.description for o in avec_defaut.outils())
    assert await appeler(
        connecteur, "google_agenda_lire", debut="2026-10-01", fin="2026-10-01"
    ) == ("jeudi 1er octobre 2026\n  g1 · 10 h 00 – 11 h 00 · Revue · Perso")


async def test_sans_agenda_par_defaut_un_ajout_va_dans_l_agenda_principal():
    calendrier = FauxCalendrier([TRAVAIL, PERSO])
    connecteur = google(calendrier)

    principal = await appeler(
        connecteur, "google_agenda_ajouter", titre="Dentiste", debut="2026-10-01T15:00"
    )
    ailleurs = await appeler(
        connecteur,
        "google_agenda_ajouter",
        titre="Revue",
        debut="2026-10-01T10:00",
        agenda="travail",
    )
    assert principal.annonce == "C'est noté : Dentiste, jeudi 1er octobre à 15 h."
    assert ailleurs.annonce == "C'est noté dans Travail : Revue, jeudi 1er octobre à 10 h."
    assert calendrier.ecrits == [("ajouter", "Perso", "Dentiste"), ("ajouter", "Travail", "Revue")]

    sans_principal = google(FauxCalendrier([TRAVAIL]))
    with pytest.raises(ErreurConnecteur) as refus:
        await appeler(sans_principal, "google_agenda_ajouter", titre="Revue", debut="2026-10-01")
    assert str(refus.value) == "Je ne trouve pas ton agenda principal dans ton compte Google."


async def test_un_agenda_en_lecture_seule_est_refuse_avant_toute_question():
    calendrier = FauxCalendrier([PERSO, FERIES], [rendezvous(FERIES, "Toussaint")])
    connecteur = google(calendrier)
    await appeler(connecteur, "google_agenda_lire", debut="2026-10-01", fin="2026-10-01")

    for nom, arguments in [
        ("google_agenda_modifier", {"evenement": "g1", "titre": "Pont"}),
        ("google_agenda_supprimer", {"evenement": "g1"}),
        (
            "google_agenda_ajouter",
            {"titre": "Pont", "debut": "2026-11-02", "agenda": "Jours fériés"},
        ),
    ]:
        with pytest.raises(ErreurConnecteur) as refus:
            await appeler(connecteur, nom, **arguments)
        assert str(refus.value) == "L'agenda « Jours fériés » ne se modifie pas d'ici."
    assert calendrier.ecrits == []


async def test_une_invitation_refusee_se_dit_et_ne_se_change_pas():
    invitation = rendezvous(PERSO, "Séminaire", invites=True, refuse=True)
    connecteur = google(FauxCalendrier([PERSO], [invitation]))

    assert await appeler(
        connecteur, "google_agenda_lire", debut="2026-10-01", fin="2026-10-01"
    ) == (
        "jeudi 1er octobre 2026\n"
        "  g1 · 10 h 00 – 11 h 00 · Séminaire · Perso · invitation refusée · avec invités"
    )
    with pytest.raises(ErreurConnecteur) as refus:
        await appeler(connecteur, "google_agenda_supprimer", evenement="g1")
    assert str(refus.value) == (
        "Ce rendez-vous a des invités : Atlas ne le change pas, pour ne pas leur écrire en ton "
        "nom. Change-le dans Google Agenda."
    )


async def test_un_agenda_inconnu_nomme_le_compte():
    connecteur = google(FauxCalendrier([PERSO, TRAVAIL]))

    with pytest.raises(ErreurConnecteur) as refus:
        await appeler(
            connecteur, "google_agenda_lire", debut="2026-10-01", fin="2026-10-01", agenda="Bureau"
        )
    assert str(refus.value) == (
        "Pas d'agenda « Bureau » dans ton compte Google. Tes agendas : Perso, Travail."
    )
