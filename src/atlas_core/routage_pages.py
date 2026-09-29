"""Ce que le Core fait d'un message d'une page authentifiée, sur /ws/web : une question tapée,
le mode muet, les documents, les boutons des barres, les connecteurs et leurs réglages, et
l'entretien du Core (sa version, le redémarrage, la mise à jour)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .pages import lire_document, liste_connecteurs, liste_documents
from .protocole_web import (
    ActiverConnecteur,
    Arreter,
    Confirmer,
    DemandeConnecteurs,
    DemandeCore,
    DemandeDocuments,
    LireDocument,
    MessagePage,
    MettreAJourCore,
    Muet,
    RedemarrerCore,
    ReglerConnecteur,
    ResultatReglage,
    Saisie,
)
from .reglages import ReglageRefuse

if TYPE_CHECKING:
    from .cerveau import Cerveau
    from .diffuseur import Abonnement
    from .entretien import Entretien
    from .outils_memoire import OutilsMemoire
    from .regie import Regie

ENREGISTRE = "Enregistré."
SANS_MEMOIRE = "La mémoire n'est pas disponible : pas de connecteurs."


@dataclass
class Contexte:
    """Ce dont un message a besoin : la régie, la mémoire et ses outils (None sans elle), le
    cerveau, la page qui l'a envoyé (son abonnement, son identifiant), et l'entretien."""

    regie: Regie
    outils: OutilsMemoire | None
    cerveau: Cerveau | None
    abonnement: Abonnement
    page: str | None
    entretien: Entretien | None = None


async def traiter(msg: MessagePage, ctx: Contexte) -> None:
    outils = ctx.outils
    if isinstance(msg, Saisie):
        await ctx.regie.saisie(msg.texte, ctx.page)
    elif isinstance(msg, Muet):
        await ctx.regie.basculer_muet(msg.actif)
    elif isinstance(msg, DemandeDocuments):
        ctx.abonnement.envoyer_prive(await liste_documents(outils))
    elif isinstance(msg, LireDocument):
        ctx.abonnement.envoyer_prive(await lire_document(outils, msg.chemin))
    elif isinstance(msg, Confirmer):
        # Comme taper « oui » ou « non » depuis cette page ; trop tard, rien.
        if outils is not None and outils.confirmations.en_attente:
            await ctx.regie.saisie("oui" if msg.oui else "non", ctx.page)
    elif isinstance(msg, Arreter):
        # Comme taper « stop » depuis cette page ; la mission déjà finie, rien.
        if outils is not None and outils.missions.en_cours is not None:
            await ctx.regie.saisie("stop", ctx.page)
    elif isinstance(msg, DemandeConnecteurs):
        ctx.abonnement.envoyer_prive(liste_connecteurs(outils))
    elif isinstance(msg, ActiverConnecteur):
        # La conversation se clôt ; la suivante porte les connecteurs actifs.
        if outils is not None and outils.basculer(msg.id, msg.actif):
            ctx.cerveau.renouveler()
        ctx.regie.diffuseur.publier(liste_connecteurs(outils))  # toutes les pages
    elif isinstance(msg, ReglerConnecteur):
        _regler(msg, ctx)
    elif ctx.entretien is not None:
        await _entretenir(msg, ctx.entretien, ctx.abonnement)


async def _entretenir(msg: MessagePage, entretien: Entretien, abonnement: Abonnement) -> None:
    """La version pour la page qui la demande ; un refus aussi ; les étapes, à toutes."""
    if isinstance(msg, DemandeCore):
        abonnement.envoyer_prive(await entretien.etat())
    elif isinstance(msg, RedemarrerCore):
        if (refus := entretien.demander_redemarrage()) is not None:
            abonnement.envoyer_prive(refus)
    elif isinstance(msg, MettreAJourCore):
        if (refus := await entretien.demander_mise_a_jour()) is not None:
            abonnement.envoyer_prive(refus)


def _regler(msg: ReglerConnecteur, ctx: Contexte) -> None:
    """Écrit les réglages ; le résultat va à la page qui les a saisis, la liste à toutes."""
    try:
        if ctx.outils is None:
            raise ReglageRefuse(SANS_MEMOIRE)
        change = ctx.outils.regler(msg.id, msg.valeurs, msg.effacer)
    except ReglageRefuse as e:
        ctx.abonnement.envoyer_prive(ResultatReglage(id=msg.id, ok=False, message=str(e)))
        return
    if change:
        ctx.cerveau.renouveler()  # un connecteur actif rechargé : comme une bascule
    ctx.abonnement.envoyer_prive(ResultatReglage(id=msg.id, ok=True, message=ENREGISTRE))
    ctx.regie.diffuseur.publier(liste_connecteurs(ctx.outils))
