"""L'action qui attend le « oui » de David (spec 2c §6).

Un outil N3 ne fait rien lui-même : il décrit son action, que le Core met ici en attente.
Atlas pose la question ; la phrase suivante de David, d'où qu'elle vienne, est lue ici avant
Claude. « Oui » : l'action s'exécute. « Non », autre chose, ou trente secondes de silence :
elle est abandonnée. Claude apprend le résultat par une ligne au début de sa question
suivante ; les pages voient la question, puis comment l'attente s'est finie.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .cerveau import Confirmation

_journal = logging.getLogger(__name__)

DELAI_S = 30.0
RIEN_SUPPRIME = "Rien n'a été supprimé."
_OUI = (
    "oui",
    "ouais",
    "oui oui",
    "vas-y",
    "oui vas-y",
    "je confirme",
    "oui je confirme",
    "confirme",
    "d'accord",
    "oui d'accord",
    "ok",
    "oui ok",
    "c'est bon",
    "oui c'est bon",
    "supprime",
    "oui supprime",
    "supprime-le",
    "supprime-la",
    "exactement",
    "tout à fait",
)
_NON = (
    "non",
    "non non",
    "non merci",
    "annule",
    "non annule",
    "laisse tomber",
    "non laisse tomber",
    "stop",
    "arrête",
    "surtout pas",
    "pas du tout",
    "ne supprime pas",
    "ne supprime rien",
)


def _normaliser(texte: str) -> str:
    """Sans majuscules, accents ni ponctuation ; un « Atlas » au début ou à la fin ignoré."""
    plie = unicodedata.normalize("NFD", texte.casefold())
    sans_accents = "".join(c for c in plie if not unicodedata.combining(c))
    mots = re.sub(r"[^a-z0-9]+", " ", sans_accents).split()
    if mots and mots[0] == "atlas":
        mots = mots[1:]
    if mots and mots[-1] == "atlas":
        mots = mots[:-1]
    return " ".join(mots)


OUI = frozenset(map(_normaliser, _OUI))
NON = frozenset(map(_normaliser, _NON))


def lire_reponse(texte: str) -> str:
    """« oui », « non », ou « autre » : seule une de ces phrases, exactement, vaut oui ou non.
    Dans le doute, ce n'est pas oui."""
    normal = _normaliser(texte)
    if normal in OUI:
        return "oui"
    if normal in NON:
        return "non"
    return "autre"


def _rien() -> None:
    pass


@dataclass(frozen=True)
class Suppression:
    """Une suppression résolue — ce qu'elle retire — et la façon de la dire. `executer`
    tourne hors de la boucle du Core, seulement après le « oui » ; `apres`, dans la boucle,
    une fois l'exécution réussie (prévenir les pages, par exemple)."""

    chemin: str
    titre: str
    executer: Callable[[], object]
    apres: Callable[[], None] = _rien

    @property
    def _nature(self) -> str:
        if self.chemin == "profil.md":
            return "profil"
        return "document" if self.chemin.startswith("documents/") else "fiche"

    @property
    def voix(self) -> str:
        return {
            "profil": "ton profil",
            "document": f"le document {self.titre}",
            "fiche": f"la fiche {self.titre}",
        }[self._nature]

    @property
    def _supprime(self) -> str:
        return "supprimée" if self._nature == "fiche" else "supprimé"

    @property
    def question(self) -> str:
        return f"Je supprime {self.voix}. Tu confirmes ?"

    @property
    def faite(self) -> str:
        return f"C'est fait : {self.voix} est {self._supprime}."

    @property
    def ratee(self) -> str:
        return f"Je n'ai pas pu supprimer {self.voix}."

    @property
    def objet(self) -> str:
        """Pour Claude : « la suppression du document « X » »."""
        return {
            "profil": "la suppression du profil",
            "document": f"la suppression du document « {self.titre} »",
            "fiche": f"la suppression de la fiche « {self.titre} »",
        }[self._nature]

    @property
    def bilan(self) -> str:
        """Pour Claude, après le oui : « le document « X » est supprimé »."""
        return {
            "profil": "le profil est supprimé",
            "document": f"le document « {self.titre} » est supprimé",
            "fiche": f"la fiche « {self.titre} » est supprimée",
        }[self._nature]

    @property
    def page_faite(self) -> str:
        return f"Supprimé : {self.voix}."


class Confirmations:
    """L'action en attente — une seule à la fois — et les lignes qui diront à Claude comment
    elle s'est finie. `sur_question` et `sur_fin` préviennent les pages."""

    def __init__(
        self,
        attendre: Callable[[float], Awaitable[None]] = asyncio.sleep,
        sur_question: Callable[[str], None] | None = None,
        sur_fin: Callable[[str], None] | None = None,
    ) -> None:
        self._attendre = attendre
        self.sur_question = sur_question or (lambda texte: None)
        self.sur_fin = sur_fin or (lambda texte: None)
        self._action: Suppression | None = None
        self._posee = False
        self._minuterie: asyncio.Task | None = None
        self._execution: asyncio.Future | None = None  # gardée : une tâche oubliée se perd
        self._lignes: list[str] = []

    @property
    def en_attente(self) -> bool:
        return self._action is not None

    def mettre_en_attente(self, action: Suppression) -> bool:
        """Met l'action de côté ; False si une autre attend déjà la réponse de David."""
        if self._action is not None:
            return False
        self._action, self._posee = action, False
        self._minuterie = asyncio.create_task(self._expirer(action))
        return True

    def poser(self) -> Confirmation | None:
        """La question à dire, une seule fois, quand la réponse d'Atlas en arrive là."""
        if self._action is None or self._posee:
            return None
        self._posee = True
        self.sur_question(self._action.question)
        return Confirmation(self._action.question)

    async def trancher(self, texte: str) -> tuple[str, bool]:
        """Lit la réponse de David à la question posée. Rend la phrase à lui dire, et si sa
        phrase doit encore partir à Claude (« autre chose »)."""
        action = self._action
        assert action is not None, "aucune action n'attend"
        reponse = lire_reponse(texte)
        self._finir()
        if reponse == "non":
            self._conclure("[Refusé par David : rien n'a été supprimé.]", RIEN_SUPPRIME)
            return "D'accord, je ne supprime rien.", False
        if reponse == "autre":
            ligne = f"[David a répondu autre chose : {action.objet} est abandonnée.]"
            self._conclure(ligne, RIEN_SUPPRIME)
            return "Je ne supprime rien.", True
        # L'exécution et sa conclusion vont jusqu'au bout, même si la réponse est annulée
        # entre-temps (une autre question, l'arrêt du Core) : sinon la suppression serait
        # faite sans que les pages, ni Claude, ne l'apprennent.
        self._execution = asyncio.ensure_future(self._executer(action))
        return await asyncio.shield(self._execution)

    async def _executer(self, action: Suppression) -> tuple[str, bool]:
        try:
            await asyncio.to_thread(action.executer)
        except Exception as e:  # noqa: BLE001 — retouché entre-temps, dépôt en panne…
            _journal.warning("%s confirmée n'a pas pu se faire : %s", action.objet, e)
            objet = action.objet[0].upper() + action.objet[1:]
            self._conclure(f"[{objet} a échoué.]", "La suppression a échoué.")
            return action.ratee, False
        action.apres()
        self._conclure(f"[Confirmé par David : {action.bilan}.]", action.page_faite)
        return action.faite, False

    def abandonner_si_non_posee(self) -> None:
        """La réponse d'Atlas s'est arrêtée avant la question : David ne l'a pas entendue,
        sa phrase suivante ne peut pas y répondre."""
        action = self._action
        if action is not None and not self._posee:
            self._finir()
            ligne = f"[David a parlé avant la question : {action.objet} est abandonnée.]"
            self._lignes.append(ligne)

    def abandonner(self) -> None:
        """La conversation se termine : l'action en attente est abandonnée, et les lignes
        pour Claude, qui ne valaient que pour elle, oubliées."""
        posee = self._posee
        if self._action is not None:
            self._finir()
            if posee:
                self.sur_fin(RIEN_SUPPRIME)
        self._lignes.clear()

    def prendre_les_lignes(self) -> list[str]:
        lignes, self._lignes = self._lignes, []
        return lignes

    async def _expirer(self, action: Suppression) -> None:
        await self._attendre(DELAI_S)
        if self._action is action:
            self._minuterie = None  # c'est elle qui sonne : rien à annuler
            posee = self._posee
            self._finir()
            ligne = f"[Sans réponse de David : {action.objet} est abandonnée.]"
            self._conclure(ligne, "Suppression abandonnée : pas de réponse." if posee else None)

    def _finir(self) -> None:
        if self._minuterie is not None:
            self._minuterie.cancel()
        self._action, self._posee, self._minuterie = None, False, None

    def _conclure(self, ligne: str, pour_les_pages: str | None) -> None:
        """La ligne pour Claude ; et pour les pages, si elles ont vu la question."""
        self._lignes.append(ligne)
        if pour_les_pages is not None:
            self.sur_fin(pour_les_pages)
