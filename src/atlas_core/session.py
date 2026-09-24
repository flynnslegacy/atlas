"""Orchestration d'un tour de parole, pour une connexion cliente.

Une Session par client audio, et une session sans voix pour les questions tapées
quand aucun client audio n'est connecté. Elle ne connaît ni le réseau ni le
transport : elle reçoit des messages décodés et appelle deux fonctions d'envoi.
Tout ce qui se passe est aussi publié au diffuseur, pour les pages web. C'est ce
qui la rend testable sans WebSocket.

Les entrées (`sur_message`, `sur_saisie`, `taire`, `fermer`) sont sérialisées par un
verrou : avec la régie, elles peuvent arriver en même temps depuis les connexions
des pages et celle du client audio. `sur_audio` n'a pas besoin du verrou : elle ne
fait qu'ajouter au tampon. Les tâches de tour, elles, ne prennent jamais le verrou —
sinon interblocage, puisqu'une entrée peut attendre qu'une tâche annulée se termine
en tenant le verrou.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable

from .cerveau import Cerveau
from .diffuseur import Diffuseur
from .etat import MachineEtat, Valeur
from .niveaux import INTERVALLE_S, CalendrierNiveaux, Planifier, niveau
from .phrases import DecoupeurPhrases
from .protocole import (
    Dire,
    Erreur,
    Etat,
    FinEnonce,
    Interruption,
    MessageClient,
    MessageCore,
    Reveil,
    StopAudio,
    Transcription,
    encoder_audio_sortant,
)
from .protocole_web import Latences, Niveau, Question, Reponse, Source

_journal = logging.getLogger(__name__)

EnvoyerJson = Callable[[MessageCore], Awaitable[None]]
EnvoyerBinaire = Callable[[bytes], Awaitable[None]]


async def sans_destinataire(_message: object) -> None:
    """Envoi vers personne : session sans voix, ou client audio déjà parti."""


def _ms(secondes: float) -> int:
    return round(secondes * 1000)


class Session:
    def __init__(
        self,
        envoyer_json: EnvoyerJson,
        envoyer_binaire: EnvoyerBinaire,
        transcription,
        synthese,
        cerveau: Cerveau,
        diffuseur: Diffuseur | None = None,
        avec_voix: Callable[[], bool] | None = None,
        horloge: Callable[[], float] | None = None,
        planifier: Planifier | None = None,
    ) -> None:
        self._envoyer_json = envoyer_json
        self._envoyer_binaire = envoyer_binaire
        self._transcription = transcription
        self._synthese = synthese
        self._cerveau = cerveau
        self._diffuseur = diffuseur if diffuseur is not None else Diffuseur()
        self._avec_voix = avec_voix or (lambda: True)
        self._horloge = horloge or time.monotonic
        self._machine = MachineEtat()
        self._verrou = asyncio.Lock()
        self._tampon: list[bytes] = []
        self._tache: asyncio.Task | None = None
        self._id_enonce = 0
        self._niveaux = CalendrierNiveaux(self._publier_niveau, self._horloge, planifier)
        self._dernier_niveau = float("-inf")
        self._t_fin = 0.0  # fin de la phrase de David, ou envoi de la question tapée
        self._premiere_voix_ms: int | None = None
        self._ecrit_en_cours = False
        self._etat_pages: Valeur = "repos"  # le dernier état publié aux pages
        self._voix_coupee = False  # le muet, posé jusqu'à la fin du tour même si redésactivé

    # --- entrées ---------------------------------------------------------

    async def sur_message(self, msg: MessageClient) -> None:
        async with self._verrou:
            if isinstance(msg, Reveil):
                await self._reveiller()
            elif isinstance(msg, FinEnonce):
                await self._fin_enonce()
            elif isinstance(msg, Interruption):
                await self._interrompre()

    async def sur_audio(self, pcm: bytes) -> None:
        if self._machine.valeur != "ecoute":
            return
        self._tampon.append(pcm)
        maintenant = self._horloge()
        if maintenant - self._dernier_niveau >= INTERVALLE_S:
            self._dernier_niveau = maintenant
            self._publier_niveau(niveau(pcm))

    async def sur_saisie(self, texte: str) -> None:
        """Une question tapée : elle passe devant tout, comme une coupure à la voix."""
        async with self._verrou:
            await self._annuler_tache()
            # Une lecture peut être encore en cours côté client alors que la machine est
            # déjà « repos » (la synthèse va plus vite que la lecture) : il faut alors
            # couper le son quand même.
            if self._machine.valeur != "repos" or self._niveaux.en_lecture():
                await self._couper_la_voix()
            else:
                self._niveaux.annuler()
            self._tampon.clear()
            if self._machine.valeur == "parole":
                self._machine.aller_vers("ecoute")
            if self._machine.valeur != "reflexion":
                self._machine.aller_vers("reflexion")
            await self._etat("reflexion")
            self._t_fin = self._horloge()
            # Posé ici, pas dans la tâche : entre `create_task` et son premier pas, un
            # `fermer()` doit déjà savoir qu'une réponse tapée est en cours.
            self._ecrit_en_cours = True
            self._tache = asyncio.create_task(self._tour_texte(texte))

    async def taire(self) -> None:
        """Le mode muet vient d'être activé : la voix se tait, le texte continue."""
        async with self._verrou:
            # La machine peut déjà être au repos alors que la lecture, elle, ne l'est
            # pas (la synthèse va plus vite que la lecture) : « activer le muet pendant
            # qu'Atlas parle » couvre aussi cette fin de lecture différée pour les pages.
            if self._machine.valeur == "parole" or self._niveaux.en_lecture():
                # Jusqu'à la fin du tour, même si le muet est redésactivé entre-temps :
                # sinon la synthèse reprendrait à la phrase suivante pour personne.
                self._voix_coupee = True
                await self._couper_la_voix()
                if self._machine.valeur == "repos" and self._etat_pages != "repos":
                    # `_couper_la_voix` vient d'annuler le repos différé des pages (via
                    # `niveaux.annuler()`) : sans ceci, elles resteraient bloquées en
                    # « parole » pour toujours, plus rien ne devant jamais le publier.
                    self._publier_etat("repos")

    async def fermer(self) -> None:
        async with self._verrou:
            if self._ecrit_en_cours and self._tache is not None and not self._tache.done():
                # Le client audio part pendant une réponse à une question tapée : elle
                # se termine par écrit, pour les pages.
                self._oublier_client()
                return
            await self._annuler_tache()
            self._niveaux.annuler()
            if self._etat_pages != "repos":
                # Sans cela, le diffuseur rejoue un état périmé (« parole », « ecoute »)
                # à toute page qui se connecte après la fermeture.
                self._publier_etat("repos")

    # --- transitions -----------------------------------------------------

    async def _reveiller(self) -> None:
        if self._machine.valeur in ("parole", "reflexion"):
            await self._interrompre()
        # Un repos différé ou des niveaux de la réponse précédente ne doivent pas
        # continuer d'arriver pendant la nouvelle écoute.
        self._niveaux.annuler()
        if self._machine.valeur == "repos":
            self._machine.aller_vers("ecoute")
        self._tampon.clear()
        await self._etat("ecoute")

    async def _fin_enonce(self) -> None:
        if self._machine.valeur != "ecoute":
            return
        self._t_fin = self._horloge()
        self._machine.aller_vers("reflexion")
        await self._etat("reflexion")
        self._tache = asyncio.create_task(self._tour())

    async def _interrompre(self) -> None:
        await self._annuler_tache()
        await self._couper_la_voix()
        if self._machine.valeur == "parole":
            self._machine.aller_vers("ecoute")
            self._tampon.clear()
            await self._etat("ecoute")
        elif self._machine.valeur == "reflexion":
            self._machine.aller_vers("repos")
            await self._etat("repos")
        elif self._machine.valeur == "repos":
            # Le tour s'est déjà terminé quand l'interruption arrive (on a coupé
            # juste à la fin de la phrase) : sans cette branche, le Core reste au
            # repos sans écouter, alors que le client, lui, s'est déjà remis à
            # capturer et à envoyer de l'audio.
            self._machine.aller_vers("ecoute")
            self._tampon.clear()
            await self._etat("ecoute")

    async def _annuler_tache(self) -> None:
        tache = self._tache
        if tache and not tache.done():
            tache.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tache
            # Une tâche annulée n'écrit plus rien — même si elle a été coupée avant son
            # premier pas, auquel cas son propre `finally` n'a jamais tourné pour
            # remettre ce drapeau à faux (sinon `fermer()` croit à tort qu'une réponse
            # tapée est encore en cours pour un tour ultérieur, et ne l'annule pas).
            self._ecrit_en_cours = False
        # Une autre entrée a pu créer une nouvelle tâche pendant qu'on attendait
        # celle-ci : ne pas l'écraser.
        if self._tache is tache:
            self._tache = None

    # --- envoi au client, avec garde ---------------------------------------

    async def _au_client(self, msg: MessageCore) -> None:
        try:
            await self._envoyer_json(msg)
        except Exception as e:  # noqa: BLE001 — client audio parti : la suite continue par écrit
            self._oublier_client(e)

    async def _audio_au_client(self, trame: bytes) -> None:
        try:
            await self._envoyer_binaire(trame)
        except Exception as e:  # noqa: BLE001 — idem
            self._oublier_client(e)

    def _oublier_client(self, e: Exception | None = None) -> None:
        """Le client audio est injoignable (parti, ou jamais connecté) : la suite de la
        réponse continue par écrit, pour les pages seulement."""
        self._envoyer_json = sans_destinataire
        self._envoyer_binaire = sans_destinataire
        self._avec_voix = lambda: False
        self._niveaux.annuler()
        # Le type de l'exception, pour qu'un bogue de sérialisation ne passe pas pour un
        # départ du client (auquel cas `e` est `None` : fermeture normale de la session).
        if e is not None:
            _journal.info(
                "client audio injoignable (%s) : la réponse continue par écrit",
                type(e).__name__,
            )
        else:
            _journal.info("client audio parti : la réponse continue par écrit")

    async def _couper_la_voix(self) -> None:
        """`StopAudio` au client, et les niveaux programmés annulés : la voix d'Atlas
        s'arrête net."""
        await self._au_client(StopAudio(id_enonce=self._id_enonce))
        self._niveaux.annuler()

    # --- le tour lui-même ------------------------------------------------

    async def _tour(self) -> None:
        try:
            pcm = b"".join(self._tampon)
            self._tampon.clear()
            debut = self._horloge()
            texte = await self._transcription.transcrire(pcm)
            transcription_ms = _ms(self._horloge() - debut)
            await self._au_client(Transcription(texte=texte, finale=True))
            if not texte.strip():
                self._machine.aller_vers("repos")
                await self._etat("repos")
                return
            await self._repondre(texte, "voix", transcription_ms)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — on ne laisse jamais mourir la session
            await self._echouer(e)

    async def _tour_texte(self, texte: str) -> None:
        try:
            await self._repondre(texte, "clavier", None)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — on ne laisse jamais mourir la session
            await self._echouer(e)
        finally:
            self._ecrit_en_cours = False

    async def _repondre(self, texte: str, source: Source, transcription_ms: int | None) -> None:
        self._voix_coupee = False
        self._diffuseur.publier(Question(texte=texte, source=source))
        self._premiere_voix_ms = None
        reflexion_ms: int | None = None
        debut = self._horloge()
        identifiant = self._id_enonce + 1
        rang = 0

        decoupeur = DecoupeurPhrases()
        async with contextlib.aclosing(self._cerveau.repondre(texte)) as fragments:
            async for fragment in fragments:
                if reflexion_ms is None:
                    reflexion_ms = _ms(self._horloge() - debut)
                for phrase in decoupeur.ajouter(fragment):
                    if rang == 0:
                        await self._entrer_en_parole(identifiant)
                    rang += 1
                    await self._dire(identifiant, rang, phrase)
        for phrase in decoupeur.vider():
            if rang == 0:
                await self._entrer_en_parole(identifiant)
            rang += 1
            await self._dire(identifiant, rang, phrase)

        self._diffuseur.publier(
            Latences(
                transcription_ms=transcription_ms,
                reflexion_ms=reflexion_ms,
                premiere_voix_ms=self._premiere_voix_ms,
            )
        )
        if rang == 0:
            # Le cerveau n'a produit aucune phrase : « reflexion » va droit au repos.
            self._machine.aller_vers("repos")
            await self._etat("repos")
            return
        self._machine.aller_vers("repos")
        await self._au_client(Etat(valeur="repos"))
        # La synthèse va environ deux fois plus vite que la lecture : les pages restent
        # en « parole » tant qu'Atlas parle encore, pas seulement tant qu'on lui envoie.
        self._niveaux.apres_lecture(lambda: self._publier_etat("repos"))

    async def _entrer_en_parole(self, identifiant: int) -> None:
        """La première phrase de la réponse : « reflexion » dure jusque-là, pas au-delà."""
        self._id_enonce = identifiant
        self._machine.aller_vers("parole")
        await self._etat("parole")

    async def _echouer(self, e: Exception) -> None:
        _journal.exception("échec du tour de parole")
        # str(e) est vide pour certaines exceptions (httpx.ConnectTimeout…) : le type,
        # au moins, dit ce qui s'est passé.
        erreur = Erreur(
            code="tour", message=f"Je n'ai pas pu répondre : {str(e) or type(e).__name__}"
        )
        # Aux pages d'abord : un client audio injoignable ne doit pas leur masquer l'erreur.
        self._diffuseur.publier(erreur)
        await self._au_client(erreur)
        # Aucun niveau programmé ne doit plus arriver aux pages après le repos, sur le
        # chemin d'erreur : rien ne l'annulerait sinon (pas de tour normal pour le faire).
        self._niveaux.annuler()
        if self._machine.peut_aller_vers("repos"):
            self._machine.aller_vers("repos")
            await self._etat("repos")

    async def _dire(self, identifiant: int, rang: int, phrase: str) -> None:
        self._diffuseur.publier(Reponse(texte=phrase))
        if not self._avec_voix() or self._voix_coupee:
            return
        await self._au_client(Dire(id_enonce=identifiant, rang=rang, texte=phrase))
        n = 0
        async with contextlib.aclosing(self._synthese.synthetiser(phrase)) as blocs:
            async for bloc in blocs:
                if not self._avec_voix() or self._voix_coupee:
                    return  # muet activé en pleine phrase : taire() a déjà coupé le son
                n += 1
                if self._premiere_voix_ms is None:
                    self._premiere_voix_ms = _ms(self._horloge() - self._t_fin)
                await self._audio_au_client(encoder_audio_sortant(identifiant, bloc))
                if self._avec_voix():
                    self._niveaux.ajouter(bloc)
                # Sinon, muet activé pendant l'envoi de cette trame : elle est déjà
                # partie, mais rien ne doit plus bouger l'orbe en son nom.
        if n == 0 and phrase.strip():
            # Sans cela, une synthèse muette (voix absente…) rend Atlas silencieux
            # sans que rien, nulle part, ne dise pourquoi.
            raise RuntimeError(f"la synthèse n'a produit aucun audio pour « {phrase} »")

    # --- état et niveaux, pour les pages -----------------------------------

    async def _etat(self, valeur: Valeur) -> None:
        # Aux pages d'abord : un client audio injoignable ne doit pas leur masquer l'état.
        self._publier_etat(valeur)
        await self._au_client(Etat(valeur=valeur))

    def _publier_etat(self, valeur: Valeur) -> None:
        """Publie l'état aux pages, et retient le dernier pour que `fermer()` sache s'il
        doit republier « repos » quand la session se termine en plein tour."""
        self._etat_pages = valeur
        self._diffuseur.publier(Etat(valeur=valeur))

    def _publier_niveau(self, valeur: float) -> None:
        self._diffuseur.publier(Niveau(valeur=valeur))
