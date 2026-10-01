"""L'agenda iCloud de David, en connecteur (spec de l'agenda et des contacts, §5) : le moteur
d'agenda d'Atlas (`atlas_core/agendas.py`), branché sur le client CalDAV d'iCloud. Ses outils
s'appellent `agenda_…`, ses étiquettes `e1`, `e2`…, et il ajoute dans l'agenda de ses réglages.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from atlas_core.agendas import ConnecteurAgenda
from atlas_core.connecteurs import Contexte

from .agenda import ADRESSE, DELAI_S, Calendrier


class AgendaIcloud(ConnecteurAgenda):
    """`adresse` : la racine CalDAV, celle d'iCloud ; les tests passent celle de leur serveur,
    et le jour qu'il est (`aujourd_hui`)."""

    def __init__(
        self,
        reglages: dict[str, str],
        *,
        adresse: str = ADRESSE,
        fuseau: dt.tzinfo | None = None,
        delai_s: float = DELAI_S,
        aujourd_hui: Callable[[], dt.date] | None = None,
    ) -> None:
        calendrier = Calendrier(
            reglages["ATLAS_ICLOUD_IDENTIFIANT"],
            reglages["ATLAS_ICLOUD_MOT_DE_PASSE"],
            adresse=adresse,
            fuseau=fuseau,
            delai_s=delai_s,
        )
        super().__init__(
            calendrier,
            service="iCloud",
            prefixe="agenda",
            lettre="e",
            application="Calendrier",
            defaut=reglages["ATLAS_ICLOUD_AGENDA"],
            aujourd_hui=aujourd_hui,
        )


def creer(contexte: Contexte) -> AgendaIcloud:
    return AgendaIcloud(contexte.reglages)
