"""La boîte Gmail de David, en connecteur (spec de Gmail et de Google Agenda, §6) : chercher et
lire (N1), préparer un brouillon (N2), envoyer après son « oui » (N3).

Chaque mail trouvé reçoit une étiquette (`m1`, `m2`…), chaque brouillon préparé la sienne (`b1`,
`b2`…), que Claude rend pour les désigner. Les étiquettes valent pour la conversation : la
suivante les oublie.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Callable
from typing import Any

import httpx

from atlas_core.connecteurs import Connecteur, Contexte, ErreurConnecteur, Fait, Niveau, Outil
from atlas_core.consignes import heure_en_chiffres
from atlas_core.google import Autorisation
from atlas_core.rendez_vous import jour_court, jour_long

from .boite import Boite
from .envoi import Envoi
from .mails import Brouillon, Mail, Resume, en_reponse, nom_ou_adresse, taille, verifier_adresses

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
BROUILLON = (
    "Prépare un brouillon dans Gmail quand David veut relire avant d'envoyer : un nouveau mail "
    "(a : ses adresses, copie, objet, texte), ou une réponse (repondre : l'étiquette du mail, "
    "et texte ; a et objet au besoin). Il reste dans ses brouillons ; Atlas l'annonce. Du texte "
    "simple, sans copie cachée ni pièce jointe."
)
ENVOYER = (
    "Envoie un mail quand David le demande : un nouveau mail (a, copie, objet, texte), une "
    "réponse (repondre et texte), ou un brouillon déjà prêt (brouillon : b1, b2…). Atlas lit à "
    "David les adresses, l'objet et le texte, et attend son « oui » : n'ajoute rien après "
    "l'appel. Du texte simple, sans copie cachée ni pièce jointe."
)
_ECRIRE = {
    "a": "string",
    "copie": "string",
    "objet": "string",
    "texte": "string",
    "repondre": "string",
}


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
        self._brouillons: dict[str, tuple[str, Brouillon]] = {}
        self._numero_de_brouillon = 0
        self._outils = [
            Outil(
                "gmail_chercher",
                CHERCHER,
                {"type": "object", "properties": {"requete": {"type": "string"}}},
                Niveau.N1,
                self._chercher,
            ),
            Outil("gmail_lire", LIRE, {"mail": str}, Niveau.N1, self._lire),
            Outil(
                "gmail_brouillon",
                BROUILLON,
                {"type": "object", "properties": {c: {"type": t} for c, t in _ECRIRE.items()}},
                Niveau.N2,
                self._brouillon,
            ),
            Outil(
                "gmail_envoyer",
                ENVOYER,
                {
                    "type": "object",
                    "properties": {
                        **{c: {"type": t} for c, t in _ECRIRE.items()},
                        "brouillon": {"type": "string"},
                    },
                },
                Niveau.N3,
                self._envoyer,
            ),
        ]

    def outils(self) -> list[Outil]:
        return self._outils

    def nouvelle_conversation(self) -> None:
        self._mails.clear()
        self._par_id.clear()
        self._brouillons.clear()

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

    async def _brouillon(self, arguments: dict[str, Any]) -> Fait:
        brouillon, pour = await self._preparer(arguments)
        id_ = await asyncio.to_thread(self._boite.brouillon, brouillon)
        self._numero_de_brouillon += 1
        etiquette = f"b{self._numero_de_brouillon}"
        self._brouillons[etiquette] = (id_, brouillon)
        return Fait(
            f"Le brouillon {etiquette} est dans Gmail : David peut le relire, ou te demander de "
            "l'envoyer.",
            f"Brouillon prêt pour {pour} : « {brouillon.objet} ».",
        )

    async def _envoyer(self, arguments: dict[str, Any]) -> Envoi:
        etiquette = str(arguments.get("brouillon") or "").strip()
        if not etiquette:
            brouillon, _ = await self._preparer(arguments)
            return Envoi(brouillon, faire=lambda: self._boite.envoyer(brouillon))
        if etiquette not in self._brouillons:
            raise ErreurConnecteur(
                f"Je ne connais pas « {etiquette} » : prépare d'abord le brouillon."
            )
        id_, brouillon = self._brouillons[etiquette]
        return Envoi(
            brouillon,
            faire=lambda: self._boite.envoyer_le_brouillon(id_),
            apres=lambda: self._brouillons.pop(etiquette, None),
        )

    async def _preparer(self, arguments: dict[str, Any]) -> tuple[Brouillon, str]:
        """Le mail que Claude décrit, vérifié, et à qui il va, pour l'annonce."""
        texte = str(arguments.get("texte") or "").strip()
        if not texte:
            raise ErreurConnecteur("Écris le texte du mail (texte).")
        a = verifier_adresses(arguments.get("a"), "a")
        copie = verifier_adresses(arguments.get("copie"), "copie")
        objet = str(arguments.get("objet") or "").strip()
        if arguments.get("repondre"):
            mail = await asyncio.to_thread(self._boite.lire, self._designe(arguments["repondre"]))
            reponse = en_reponse(mail)
            brouillon = Brouillon(
                a=a or reponse.a,
                objet=objet or reponse.objet,
                texte=texte,
                copie=copie,
                fil=reponse.fil,
                en_reponse_a=reponse.en_reponse_a,
                references=reponse.references,
            )
            a_l_expediteur = not a and reponse.a == verifier_adresses(mail.de, "a")
            pour = nom_ou_adresse(mail.de) if a_l_expediteur else ", ".join(brouillon.a)
            return brouillon, pour
        if not a:
            raise ErreurConnecteur("À qui ? Donne son adresse mail (a).")
        if not objet:
            raise ErreurConnecteur("Donne un objet au mail (objet).")
        return Brouillon(a=a, objet=objet, texte=texte, copie=copie), ", ".join(a)

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
