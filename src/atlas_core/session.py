"""Orchestration d'un tour de parole, pour une connexion cliente.

Une Session par client audio, et une session sans voix pour les questions tapées
quand aucun client audio n'est connecté. Elle ne connaît ni le réseau ni le
transport : elle reçoit des messages décodés et appelle deux fonctions d'envoi.
Tout ce qui se passe est aussi publié au diffuseur, pour les pages web. C'est ce
qui la rend testable sans WebSocket.
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
        # Sans diffuseur fourni, un diffuseur sans abonné : publier ne coûte presque rien.
        self._diffuseur = diffuseur or Diffuseur()
        self._avec_voix = avec_voix or (lambda: True)
        self._horloge = horloge or time.monotonic
        self._machine = MachineEtat()
        self._tampon: list[bytes] = []
        self._tache: asyncio.Task | None = None
        self._id_enonce = 0
        self._niveaux = CalendrierNiveaux(self._publier_niveau, self._horloge, planifier)
        self._dernier_niveau = float("-inf")
        self._t_fin = 0.0  # fin de la phrase de David, ou envoi de la question tapée
        self._premiere_voix_ms: int | None = None
        self._ecrit_en_cours = False

    # --- entrées ---------------------------------------------------------

    async def sur_message(self, msg: MessageClient) -> None:
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
        await self._annuler_tache()
        if self._machine.valeur != "repos":
            await self._envoyer_json(StopAudio(id_enonce=self._id_enonce))
            self._niveaux.annuler()
            self._tampon.clear()
        if self._machine.valeur == "parole":
            self._machine.aller_vers("ecoute")
        if self._machine.valeur != "reflexion":
            self._machine.aller_vers("reflexion")
        await self._etat("reflexion")
        self._t_fin = self._horloge()
        self._tache = asyncio.create_task(self._tour_texte(texte))

    async def taire(self) -> None:
        """Le mode muet vient d'être activé : la voix se tait, le texte continue."""
        if self._machine.valeur == "parole":
            await self._envoyer_json(StopAudio(id_enonce=self._id_enonce))
            self._niveaux.annuler()

    async def fermer(self) -> None:
        if self._ecrit_en_cours and self._tache is not None and not self._tache.done():
            # Le client audio part pendant une réponse à une question tapée : elle se
            # termine par écrit, pour les pages.
            self._envoyer_json = sans_destinataire
            self._envoyer_binaire = sans_destinataire
            self._avec_voix = lambda: False
            self._niveaux.annuler()
            return
        await self._annuler_tache()
        self._niveaux.annuler()

    # --- transitions -----------------------------------------------------

    async def _reveiller(self) -> None:
        if self._machine.valeur in ("parole", "reflexion"):
            await self._interrompre()
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
        await self._envoyer_json(StopAudio(id_enonce=self._id_enonce))
        self._niveaux.annuler()
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
        if self._tache and not self._tache.done():
            self._tache.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tache
        self._tache = None

    # --- le tour lui-même ------------------------------------------------

    async def _tour(self) -> None:
        try:
            pcm = b"".join(self._tampon)
            self._tampon.clear()
            debut = self._horloge()
            texte = await self._transcription.transcrire(pcm)
            transcription_ms = _ms(self._horloge() - debut)
            await self._envoyer_json(Transcription(texte=texte, finale=True))
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
        self._ecrit_en_cours = True
        try:
            await self._repondre(texte, "clavier", None)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — on ne laisse jamais mourir la session
            await self._echouer(e)
        finally:
            self._ecrit_en_cours = False

    async def _repondre(self, texte: str, source: Source, transcription_ms: int | None) -> None:
        self._diffuseur.publier(Question(texte=texte, source=source))
        self._machine.aller_vers("parole")
        await self._etat("parole")
        self._id_enonce += 1
        identifiant = self._id_enonce
        self._premiere_voix_ms = None
        reflexion_ms: int | None = None
        debut = self._horloge()

        decoupeur = DecoupeurPhrases()
        rang = 0
        async with contextlib.aclosing(self._cerveau.repondre(texte)) as fragments:
            async for fragment in fragments:
                if reflexion_ms is None:
                    reflexion_ms = _ms(self._horloge() - debut)
                for phrase in decoupeur.ajouter(fragment):
                    rang += 1
                    await self._dire(identifiant, rang, phrase)
        for phrase in decoupeur.vider():
            rang += 1
            await self._dire(identifiant, rang, phrase)

        self._diffuseur.publier(
            Latences(
                transcription_ms=transcription_ms,
                reflexion_ms=reflexion_ms,
                premiere_voix_ms=self._premiere_voix_ms,
            )
        )
        self._machine.aller_vers("repos")
        await self._etat("repos")

    async def _echouer(self, e: Exception) -> None:
        _journal.exception("échec du tour de parole")
        # str(e) est vide pour certaines exceptions (httpx.ConnectTimeout…) : le type,
        # au moins, dit ce qui s'est passé.
        erreur = Erreur(
            code="tour", message=f"Je n'ai pas pu répondre : {str(e) or type(e).__name__}"
        )
        await self._envoyer_json(erreur)
        self._diffuseur.publier(erreur)
        if self._machine.peut_aller_vers("repos"):
            self._machine.aller_vers("repos")
            await self._etat("repos")

    async def _dire(self, identifiant: int, rang: int, phrase: str) -> None:
        self._diffuseur.publier(Reponse(texte=phrase))
        if not self._avec_voix():
            return
        await self._envoyer_json(Dire(id_enonce=identifiant, rang=rang, texte=phrase))
        n = 0
        async with contextlib.aclosing(self._synthese.synthetiser(phrase)) as blocs:
            async for bloc in blocs:
                if not self._avec_voix():
                    return  # muet activé en pleine phrase : taire() a déjà coupé le son
                n += 1
                if self._premiere_voix_ms is None:
                    self._premiere_voix_ms = _ms(self._horloge() - self._t_fin)
                await self._envoyer_binaire(encoder_audio_sortant(identifiant, bloc))
                self._niveaux.ajouter(bloc)
        if n == 0 and phrase.strip():
            # Sans cela, une synthèse muette (voix absente…) rend Atlas silencieux
            # sans que rien, nulle part, ne dise pourquoi.
            raise RuntimeError(f"la synthèse n'a produit aucun audio pour « {phrase} »")

    async def _etat(self, valeur: Valeur) -> None:
        etat = Etat(valeur=valeur)
        await self._envoyer_json(etat)
        self._diffuseur.publier(etat)

    def _publier_niveau(self, valeur: float) -> None:
        self._diffuseur.publier(Niveau(valeur=valeur))
