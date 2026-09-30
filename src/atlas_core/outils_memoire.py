"""Les outils de la mémoire, que Claude appelle : lire, chercher, écrire une fiche, annuler,
supprimer — ceux des documents (outils_documents.py), et ceux des connecteurs actifs.

Chacun déclare son niveau, et le serveur « atlas » (outils.py) applique la règle : lire et
chercher sont N1, écrire et annuler N2 (faits, puis annoncés), supprimer N3 (le « oui » de
David d'abord). Chaque écriture passe par `Memoire`, qui la vérifie et la commite.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from .confirmation import Confirmations, Suppression
from .memoire import DOSSIER_DOCUMENTS, Defait, Memoire
from .missions import Missions
from .outils import Fait, Niveau, Outil, ServeurAtlas
from .outils_documents import outils_des_documents
from .registre import ConnecteurActif, Registre
from .reglages import ReglageRefuse, changements_permis, ecrire_env, secretes

_journal = logging.getLogger(__name__)

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
    """Le serveur « atlas » : le socle (la mémoire et les documents), et les outils des
    connecteurs actifs du `registre`. `sur_documents` prévient les pages quand un document
    change, `sur_connecteurs` quand des bascules ont pris effet ; `confirmations` tient
    l'action qui attend le « oui » ; `missions`, la mission en cours sur le Mac ;
    `fichier_env`, le .env où s'écrivent les réglages des connecteurs saisis dans la page."""

    def __init__(
        self,
        memoire: Memoire,
        confirmations: Confirmations | None = None,
        sur_documents: Callable[[], None] | None = None,
        missions: Missions | None = None,
        registre: Registre | None = None,
        sur_connecteurs: Callable[[], None] | None = None,
        fichier_env: Path | None = None,
    ) -> None:
        self.memoire = memoire
        self.fichier_env = fichier_env
        self.sur_documents = sur_documents or (lambda: None)
        self.sur_connecteurs = sur_connecteurs or (lambda: None)
        self.missions = missions or Missions()
        self.registre = registre
        self._socle = [
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
        ]
        self.connecteurs: list[ConnecteurActif] = []
        if registre is not None:
            registre.reserver(o.nom for o in self._socle)
            registre.demarrer()
            self.connecteurs = registre.actifs()
        super().__init__(self._tous(), confirmations or Confirmations())

    def _tous(self) -> list[Outil]:
        return [*self._socle, *(o for c in self.connecteurs for o in c.outils)]

    @property
    def consignes_des_connecteurs(self) -> list[str]:
        return [c.consignes for c in self.connecteurs if c.consignes.strip()]

    def basculer(self, id_: str, actif: bool) -> bool:
        """Active ou coupe un connecteur ; rend vrai si les connecteurs actifs ont changé.
        Les outils changent aussitôt ici, mais Claude ne les voit qu'à la conversation
        neuve : celle en cours garde les siens jusqu'à sa clôture."""
        if self.registre is None or not self.registre.basculer(id_, actif):
            return False
        self.connecteurs = self.registre.actifs()
        self._installer(self._tous())
        return True

    def regler(self, id_: str, valeurs: Mapping[str, str], effacer: Iterable[str]) -> bool:
        """Écrit des réglages d'un connecteur dans le .env et les applique aussitôt : un
        connecteur actif se recharge avec eux, comme après deux bascules, et de même tout
        autre connecteur actif qui déclare un réglage changé (un mot de passe partagé) ; rend
        vrai : la conversation se renouvelle. `ReglageRefuse` si rien ne convient : rien n'a
        changé."""
        if self.registre is None or self.fichier_env is None:
            raise ReglageRefuse("Les réglages ne s'écrivent pas ici.")
        fiches = self.registre.decouvrir()
        fiche = next((f for f in fiches if f.id == id_), None)
        if fiche is None or fiche.manifeste is None:
            raise ReglageRefuse("Ce connecteur n'a pas de réglages.")
        changements = changements_permis(fiche.manifeste, valeurs, effacer)
        ecrire_env(self.fichier_env, changements)
        environ = self.registre.environ
        for variable, valeur in changements.items():
            if valeur is None:
                environ.pop(variable, None)
            else:
                environ[variable] = valeur
        secrets = secretes(f.manifeste for f in fiches)
        self.memoire.ajouter_secrets(v for k, v in changements.items() if v and k in secrets)
        concernes = [
            f
            for f in fiches
            if f.manifeste is not None
            and any(r.variable in changements for r in f.manifeste.reglages)
        ]
        for concerne in concernes:  # « en erreur » à cause d'un réglage : il réessaiera
            self.registre.oublier_l_echec(concerne.id)
        actifs = [concerne.id for concerne in concernes if concerne.etat == "actif"]
        if not actifs:
            return False
        for actif in actifs:
            self.registre.basculer(actif, False)
            self.registre.basculer(actif, True)  # s'il ne se recharge pas : « en erreur »
        self.connecteurs = self.registre.actifs()
        self._installer(self._tous())
        return True

    def fin_du_tour(self, arretee: bool = False) -> None:
        """La réponse est finie : une mission ne lui survit pas. `arretee` : la réponse a été
        coupée (David a parlé, ou touché « Stop »)."""
        self.missions.fermer("Mission arrêtée." if arretee else "Mission terminée.")
        self._prevenir("fin_du_tour", arretee)

    def nouvelle_phrase(self) -> None:
        """David parle : la mission en cours s'arrête net."""
        self.missions.fermer("Mission arrêtée.")
        self._prevenir("nouvelle_phrase")

    def nouvelle_conversation(self) -> None:
        super().nouvelle_conversation()
        self.missions.fermer("Mission arrêtée.")
        if self.registre is not None and self.registre.actifs() != self.connecteurs:
            self.connecteurs = self.registre.actifs()  # un connecteur retiré du disque
            self._installer(self._tous())
        self._prevenir("nouvelle_conversation")

    def conversation_commencee(self) -> None:
        """La première question d'une conversation neuve est partie, avec les outils des
        connecteurs actifs : les bascules ont pris effet, et les pages le voient."""
        if self.registre is not None and self.registre.appliquer():
            self.sur_connecteurs()

    def _prevenir(self, reaction: str, *arguments: object) -> None:
        """Préviens les connecteurs actifs ; celui qui plante ne gêne ni Atlas ni les autres."""
        for actif in self.connecteurs:
            try:
                getattr(actif.connecteur, reaction)(*arguments)
            except (Exception, SystemExit):  # un sys.exit non plus
                _journal.exception("le connecteur %s a échoué (%s)", actif.id, reaction)

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
