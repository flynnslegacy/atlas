"""Ce que l'agenda dit (spec de l'agenda et des contacts, §5.2 et §5.4) : les lignes que Claude
lit, et ce qu'Atlas dit à David."""

from __future__ import annotations

import datetime as dt

from atlas_core.consignes import date_en_lettres, heure_en_chiffres

from .agenda import RendezVous, jour_de

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def jour_long(jour: dt.date) -> str:
    """« jeudi 2 octobre 2026 »."""
    return f"{JOURS[jour.weekday()]} {date_en_lettres(jour)}"


def jour_court(jour: dt.date) -> str:
    """« jeudi 2 octobre »."""
    return jour_long(jour).removesuffix(f" {jour.year}")


def periode(debut: dt.date, fin: dt.date) -> str:
    """« le jeudi 2 octobre 2026 », « du jeudi 2 octobre 2026 au samedi 4 octobre 2026 »."""
    if debut == fin:
        return f"le {jour_long(debut)}"
    return f"du {jour_long(debut)} au {jour_long(fin)}"


def horaire(rendezvous: RendezVous) -> str:
    """« 15 h 00 – 16 h 00 », « 15 h 00 » (sans fin), « journée entière », « journée entière,
    jusqu'au lundi 6 octobre »."""
    debut, fin = rendezvous.debut, rendezvous.fin
    if rendezvous.journee:
        dernier = fin - dt.timedelta(days=1)
        return (
            "journée entière"
            if dernier <= debut
            else f"journée entière, jusqu'au {jour_court(dernier)}"
        )
    assert isinstance(debut, dt.datetime) and isinstance(fin, dt.datetime)
    if fin == debut:
        return heure_en_chiffres(debut)
    if jour_de(fin) == jour_de(debut):
        return f"{heure_en_chiffres(debut)} – {heure_en_chiffres(fin)}"
    return f"{heure_en_chiffres(debut)} – {jour_court(jour_de(fin))}, {heure_en_chiffres(fin)}"


def ligne(etiquette: str, rendezvous: RendezVous) -> str:
    """« e3 · 15 h 00 – 16 h 00 · Dentiste · Domicile · 12 rue des Lilas »."""
    morceaux = [etiquette, horaire(rendezvous), rendezvous.titre, rendezvous.agenda.nom]
    if rendezvous.lieu:
        morceaux.append(rendezvous.lieu)
    if rendezvous.annule:
        morceaux.append("annulé")
    if rendezvous.repete:
        morceaux.append("répété")
    if rendezvous.invites:
        morceaux.append("avec invités")
    return "  " + " · ".join(morceaux)


def heure_dite(moment: dt.datetime) -> str:
    """« 15 h », « 9 h 05 » : pour la voix."""
    return f"{moment.hour} h" if moment.minute == 0 else heure_en_chiffres(moment)


def quand(debut: dt.date, fin: dt.date) -> str:
    """« jeudi 1er octobre à 15 h », « lundi 5 octobre », « du lundi 5 octobre au vendredi 9
    octobre » (une journée entière a sa `fin` exclue)."""
    if isinstance(debut, dt.datetime):
        return f"{jour_court(debut.date())} à {heure_dite(debut)}"
    dernier = fin - dt.timedelta(days=1)
    if dernier <= debut:
        return jour_court(debut)
    return f"du {jour_court(debut)} au {jour_court(dernier)}"
