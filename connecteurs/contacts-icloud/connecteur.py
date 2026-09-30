"""Les contacts iCloud de David, en connecteur (spec de l'agenda et des contacts, §6) : les
chercher (N1), en lecture seule."""

from __future__ import annotations

import asyncio
import datetime as dt
import re
import time
from collections.abc import Callable
from typing import Any

from atlas_core.connecteurs import Connecteur, Contexte, ErreurConnecteur, Niveau, Outil
from atlas_core.consignes import date_en_lettres

from .carnet import ADRESSE, DELAI_S, Anniversaire, Carnet, Fiche, normaliser

MAX_FICHES = 10

CHERCHER = (
    "Cherche dans les contacts iCloud de David les fiches dont le nom, le prénom, le surnom, "
    "l'entreprise, un numéro ou une adresse mail contient un texte (texte, deux caractères au "
    "moins), sans tenir compte des accents ni des majuscules : 10 fiches au plus, avec leurs "
    "téléphones, leurs adresses mail et postales, et leur anniversaire."
)
_SEPARATEURS = re.compile(r"[\s.()-]")


def chiffres(numero: str) -> str:
    """Un numéro sans ses espaces ni ses points ; +33 et 0033 deviennent 0."""
    nu = _SEPARATEURS.sub("", numero)
    for indicatif in ("+33", "0033"):
        if nu.startswith(indicatif):
            return "0" + nu[len(indicatif) :]
    return nu


def correspond(fiche: Fiche, cherche: str) -> bool:
    """Le texte est-il dans le nom, le surnom, l'entreprise ou un mail de la fiche ; ou, pour
    un bout de numéro, dans l'un de ses téléphones (sans espaces ni points, +33 comme 0) ?"""
    texte = normaliser(cherche)
    champs = (fiche.nom, fiche.surnom, fiche.entreprise, *(mail.valeur for mail in fiche.mails))
    if any(texte in normaliser(champ) for champ in champs):
        return True
    numero = chiffres(cherche)
    return len(numero) >= 2 and any(numero in chiffres(tel.valeur) for tel in fiche.telephones)


def date_d_anniversaire(anniversaire: Anniversaire) -> str:
    """« 12 mai 1990 », ou « 12 mai » sans l'année."""
    jour = dt.date(anniversaire.annee or 2000, anniversaire.mois, anniversaire.jour)
    texte = date_en_lettres(jour)
    return texte if anniversaire.annee else texte.removesuffix(f" {jour.year}")


def presenter(fiche: Fiche) -> str:
    """Le nom, le surnom et l'entreprise, puis une ligne par coordonnée, et l'anniversaire."""
    entete = fiche.nom + (f" ({fiche.surnom})" if fiche.surnom else "")
    if fiche.entreprise and fiche.entreprise != fiche.nom:
        entete += f" · {fiche.entreprise}"
    lignes = [entete]
    for genre, coordonnees in [
        ("téléphone", fiche.telephones),
        ("mail", fiche.mails),
        ("adresse", fiche.adresses),
    ]:
        for coordonnee in coordonnees:
            libelle = f"{genre} {coordonnee.libelle}" if coordonnee.libelle else genre
            lignes.append(f"  {libelle} : {coordonnee.valeur}")
    if fiche.anniversaire is not None:
        lignes.append(f"  anniversaire : {date_d_anniversaire(fiche.anniversaire)}")
    return "\n".join(lignes)


class ContactsIcloud(Connecteur):
    """`adresse` : la racine CardDAV, celle d'iCloud ; les tests passent celle de leur serveur,
    et leur horloge."""

    def __init__(
        self,
        reglages: dict[str, str],
        *,
        adresse: str = ADRESSE,
        delai_s: float = DELAI_S,
        horloge: Callable[[], float] = time.monotonic,
    ) -> None:
        self._carnet = Carnet(
            reglages["ATLAS_ICLOUD_IDENTIFIANT"],
            reglages["ATLAS_ICLOUD_MOT_DE_PASSE"],
            adresse=adresse,
            delai_s=delai_s,
            horloge=horloge,
        )
        self._outils = [
            Outil("contacts_chercher", CHERCHER, {"texte": str}, Niveau.N1, self._chercher)
        ]

    def outils(self) -> list[Outil]:
        return self._outils

    async def _chercher(self, arguments: dict[str, Any]) -> str:
        cherche = str(arguments.get("texte") or "").strip()
        if len(cherche) < 2:
            raise ErreurConnecteur("Cherche au moins deux lettres.")
        fiches = await asyncio.to_thread(self._carnet.fiches)
        trouvees = [fiche for fiche in fiches if correspond(fiche, cherche)]
        if not trouvees:
            return f"Aucun contact ne correspond à « {cherche} »."
        lignes = [presenter(fiche) for fiche in trouvees[:MAX_FICHES]]
        if len(trouvees) > MAX_FICHES:
            lignes.append(f"… et {len(trouvees) - MAX_FICHES} autres : précise ta recherche.")
        return "\n".join(lignes)


def creer(contexte: Contexte) -> ContactsIcloud:
    return ContactsIcloud(contexte.reglages)
