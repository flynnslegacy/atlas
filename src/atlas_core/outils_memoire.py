"""Les outils de la mémoire, que Claude appelle : lire, chercher, écrire une fiche, annuler,
supprimer — et ceux des documents (outils_documents.py).

Chacun déclare son niveau, et le serveur « atlas » (outils.py) applique la règle : lire et
chercher sont N1, écrire et annuler N2 (faits, puis annoncés), supprimer N3 (le « oui » de
David d'abord). Chaque écriture passe par `Memoire`, qui la vérifie et la commite.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from .confirmation import Confirmations, Suppression
from .memoire import DOSSIER_DOCUMENTS, Defait, Memoire
from .outils import Fait, Niveau, Outil, ServeurAtlas
from .outils_documents import outils_des_documents

ANNONCE_PROFIL = "Je le note dans ton profil."
ANNONCE_RETRAIT = "J'ai retiré ma dernière note."

LIRE = (
    "Lit un fichier de ta mémoire : profil.md, une fiche (entreprise/, projets/ ou "
    "personnes/ suivi du nom), un document (documents/ suivi du nom) ou un jour du journal "
    "(journal/AAAA-MM-JJ.md). Lis une fiche ou un document avant de le modifier."
)
CHERCHER = (
    "Cherche un mot ou un nom dans tes fiches, tes documents et ton journal, sans tenir "
    "compte des majuscules ni des accents. Rend au plus vingt lignes, chacune avec son fichier."
)
ECRIRE = (
    "Crée ou remplace une fiche entière de ta mémoire : profil.md, ou entreprise/<nom>.md, "
    "projets/<nom>.md, personnes/<nom>.md, le nom en minuscules, chiffres et tirets. Le "
    "contenu commence par « # Titre », une ligne vide, puis une phrase de résumé ; le reste "
    "est libre. Atlas annonce l'écriture à David : ne l'annonce pas toi-même."
)
ANNULER = (
    "Défait ta dernière note encore en place — une fiche écrite, un document écrit ou "
    "retouché, une suppression —, quand David dit « annule », « oublie ça » ou « ne note pas "
    "ça ». Rappeler cet outil remonte d'une note. Atlas le dit à David."
)
SUPPRIMER = (
    "Supprime une fiche (profil.md, entreprise/, projets/ ou personnes/) ou un document "
    "(documents/), quand David le demande. Rien n'est supprimé tout de suite : Atlas demande "
    "à David de confirmer. N'ajoute rien après l'appel, et ne dis jamais que c'est fait."
)


def annonce_de(chemin: str, titre: str) -> str:
    return ANNONCE_PROFIL if chemin == "profil.md" else f"Je le note dans la fiche {titre}."


def _est_un_document(chemin: str) -> bool:
    return chemin.startswith(f"{DOSSIER_DOCUMENTS}/")


def annonce_du_retrait(defait: Defait) -> str:
    """Ce qu'Atlas dit après « annule », selon ce que la note avait fait."""
    if defait.nature == "suppression":
        if defait.chemin == "profil.md":
            return "J'ai remis ton profil."
        quoi = "le document" if _est_un_document(defait.chemin) else "la fiche"
        return f"J'ai remis {quoi} {defait.titre}."
    if _est_un_document(defait.chemin):
        if defait.nature == "creation":
            return f"J'ai retiré le document {defait.titre}."
        return f"Le document {defait.titre} revient à sa version précédente."
    return ANNONCE_RETRAIT


class OutilsMemoire(ServeurAtlas):
    """Le serveur « atlas » et les outils de la mémoire. `sur_documents` prévient les pages
    quand un document change ; `confirmations` tient l'action qui attend le « oui »."""

    def __init__(
        self,
        memoire: Memoire,
        confirmations: Confirmations | None = None,
        sur_documents: Callable[[], None] | None = None,
    ) -> None:
        self.memoire = memoire
        self.sur_documents = sur_documents or (lambda: None)
        super().__init__(
            [
                Outil("memoire_lire", LIRE, {"chemin": str}, Niveau.N1, self._lire),
                Outil("memoire_chercher", CHERCHER, {"texte": str}, Niveau.N1, self._chercher),
                Outil(
                    "memoire_ecrire",
                    ECRIRE,
                    {"chemin": str, "contenu": str},
                    Niveau.N2,
                    self._ecrire,
                ),
                *outils_des_documents(memoire, lambda: self.sur_documents()),
                Outil("memoire_annuler", ANNULER, {}, Niveau.N2, self._annuler),
                Outil("memoire_supprimer", SUPPRIMER, {"chemin": str}, Niveau.N3, self._supprimer),
            ],
            confirmations or Confirmations(),
        )

    async def _lire(self, arguments: dict[str, Any]) -> str:
        return await asyncio.to_thread(self.memoire.lire, arguments["chemin"])

    async def _chercher(self, arguments: dict[str, Any]) -> str:
        lignes = await asyncio.to_thread(self.memoire.chercher, arguments["texte"])
        return "\n".join(lignes) if lignes else "Rien trouvé."

    async def _ecrire(self, arguments: dict[str, Any]) -> Fait:
        chemin = arguments["chemin"]
        titre = await asyncio.to_thread(self.memoire.ecrire, chemin, arguments["contenu"])
        if titre is None:
            return Fait("La fiche était déjà ainsi : rien n'a changé.")
        return Fait(f"C'est noté dans {chemin}.", annonce_de(chemin, titre))

    async def _annuler(self, arguments: dict[str, Any]) -> Fait:
        defait = await asyncio.to_thread(self.memoire.annuler)
        annonce = annonce_du_retrait(defait)
        if _est_un_document(defait.chemin):
            self.sur_documents()
        if annonce == ANNONCE_RETRAIT:
            return Fait(f"La note « {defait.titre} » est retirée.", annonce)
        return Fait(annonce, annonce)

    async def _supprimer(self, arguments: dict[str, Any]) -> Suppression:
        chemin = arguments["chemin"]
        titre = await asyncio.to_thread(self.memoire.titre_de, chemin)
        apres = (lambda: self.sur_documents()) if _est_un_document(chemin) else (lambda: None)
        return Suppression(chemin, titre, lambda: self.memoire.supprimer(chemin), apres)
