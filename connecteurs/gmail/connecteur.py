"""La boîte Gmail de David, en connecteur (spec de Gmail et de Google Agenda, §6) : chercher et
lire (N1).

Chaque mail trouvé reçoit une étiquette (`m1`, `m2`…), que Claude rend pour désigner un mail.
Les étiquettes valent pour la conversation : la suivante les oublie.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Callable
from typing import Any

import httpx

from atlas_core.connecteurs import Connecteur, Contexte, ErreurConnecteur, Niveau, Outil
from atlas_core.consignes import heure_en_chiffres
from atlas_core.google import Autorisation
from atlas_core.rendez_vous import jour_court, jour_long

from .boite import Boite
from .mails import Mail, Resume, taille

PAR_DEFAUT = "in:inbox is:unread"
CHERCHER = (
    "Cherche des mails dans la boîte Gmail de David (requete : la syntaxe de recherche de "
    "Gmail, par exemple from:paul is:unread newer_than:7d ; par défaut, les non-lus de la "
    "boîte de réception). 20 mails au plus, les plus récents d'abord, chacun avec une étiquette "
    "(m1, m2…) qui le désigne pour le lire."
)
LIRE = (
    "Lit un mail de David, désigné par son étiquette (mail : m1, m2…, donnée par "
    "gmail_chercher) : ses en-têtes, son texte, et ses pièces jointes, nommées mais jamais "
    "ouvertes."
)


class Gmail(Connecteur):
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
        self._boite = Boite(autorisation, fuseau=fuseau)
        self._aujourd_hui = aujourd_hui or (lambda: dt.datetime.now(self._boite.fuseau).date())
        self._mails: dict[str, str] = {}
        self._par_id: dict[str, str] = {}
        self._outils = [
            Outil(
                "gmail_chercher",
                CHERCHER,
                {"type": "object", "properties": {"requete": {"type": "string"}}},
                Niveau.N1,
                self._chercher,
            ),
            Outil("gmail_lire", LIRE, {"mail": str}, Niveau.N1, self._lire),
        ]

    def outils(self) -> list[Outil]:
        return self._outils

    def nouvelle_conversation(self) -> None:
        self._mails.clear()
        self._par_id.clear()

    async def _chercher(self, arguments: dict[str, Any]) -> str:
        requete = str(arguments.get("requete") or "").strip() or PAR_DEFAUT
        resumes, encore = await asyncio.to_thread(self._boite.chercher, requete)
        if not resumes:
            return f"Aucun mail pour « {requete} »."
        lignes = [self._ligne(resume) for resume in resumes]
        if encore:
            lignes.append("… et d'autres : précise ta recherche.")
        return "\n".join(lignes)

    async def _lire(self, arguments: dict[str, Any]) -> str:
        mail = await asyncio.to_thread(self._boite.lire, self._designe(arguments.get("mail")))
        return self._presenter(mail)

    def _designe(self, etiquette: object) -> str:
        etiquette = str(etiquette or "").strip()
        if etiquette not in self._mails:
            raise ErreurConnecteur(f"Je ne connais pas « {etiquette} » : cherche d'abord.")
        return self._mails[etiquette]

    def _etiqueter(self, id_: str) -> str:
        etiquette = self._par_id.get(id_)
        if etiquette is None:
            etiquette = f"m{len(self._par_id) + 1}"
            self._par_id[id_] = etiquette
            self._mails[etiquette] = id_
        return etiquette

    def _quand(self, moment: dt.datetime) -> str:
        """« jeudi 1er octobre, 9 h 12 », avec l'année si ce n'est pas celle en cours."""
        jour = moment.date()
        dit = jour_court(jour) if jour.year == self._aujourd_hui().year else jour_long(jour)
        return f"{dit}, {heure_en_chiffres(moment)}"

    def _ligne(self, resume: Resume) -> str:
        morceaux = [
            self._etiqueter(resume.id),
            self._quand(resume.date),
            resume.expediteur,
            resume.objet,
        ]
        if resume.extrait:
            morceaux.append(f"« {resume.extrait} »")
        for vrai, marque in [
            (resume.non_lu, "non lu"),
            (resume.important, "important"),
            (resume.piece_jointe, "pièce jointe"),
        ]:
            if vrai:
                morceaux.append(marque)
        return " · ".join(morceaux)

    def _presenter(self, mail: Mail) -> str:
        entetes = [("De", mail.de), ("À", mail.a), ("Copie", mail.copie)]
        lignes = [f"{nom} : {valeur}" for nom, valeur in entetes if valeur]
        lignes += [f"Date : {self._quand(mail.date)}", f"Objet : {mail.objet}", ""]
        lignes.append(mail.texte or "(pas de texte)")
        if mail.pieces:
            pieces = ", ".join(f"{nom} ({taille(octets)})" for nom, octets in mail.pieces)
            lignes += ["", f"Pièces jointes : {pieces}"]
        return "\n".join(lignes)


def creer(contexte: Contexte) -> Gmail:
    return Gmail(contexte.reglages)
