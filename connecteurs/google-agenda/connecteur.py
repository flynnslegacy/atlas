"""L'agenda Google de David, en connecteur (spec de Gmail et de Google Agenda, §5) : le moteur
d'agenda d'Atlas (`atlas_core/agendas.py`), branché sur le client de l'API Google Agenda. Ses
outils s'appellent `google_agenda_…`, ses étiquettes `g1`, `g2`…, et il ajoute dans l'agenda
principal de David, sauf s'il en nomme un autre.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import httpx

from atlas_core.agendas import ConnecteurAgenda
from atlas_core.connecteurs import Contexte
from atlas_core.google import Autorisation

from .agenda import Calendrier


class GoogleAgenda(ConnecteurAgenda):
    """`http` : le client vers Google (les tests passent leur doublure) ; `aujourd_hui` : le
    jour qu'il est (les tests le fixent)."""

    def __init__(
        self,
        reglages: dict[str, str],
        *,
        http: httpx.Client | None = None,
        fuseau: dt.tzinfo | None = None,
        aujourd_hui: Callable[[], dt.date] | None = None,
    ) -> None:
        autorisation = Autorisation(
            reglages["ATLAS_GOOGLE_ID_CLIENT"],
            reglages["ATLAS_GOOGLE_SECRET_CLIENT"],
            reglages["ATLAS_GOOGLE_JETON"],
            http=http,
        )
        super().__init__(
            Calendrier(autorisation, fuseau=fuseau),
            service="Google",
            prefixe="google_agenda",
            lettre="g",
            application="Google Agenda",
            compte="compte Google",
            aujourd_hui=aujourd_hui,
        )


def creer(contexte: Contexte) -> GoogleAgenda:
    return GoogleAgenda(contexte.reglages)
