"""Le daemon audio du M5.

Deux boucles concurrentes : l'une lit le micro et parle au Core, l'autre reçoit
du Core et joue le son. Le client ne décide de rien d'autre que du barge-in —
il le décide localement parce que 200 ms d'aller-retour réseau rendraient
l'interruption molle — et de la relance : une fois la réponse d'Atlas jouée, il
rouvre l'écoute un moment sans mot de réveil, pour que la conversation continue.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import os
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from atlas_core.protocole import (
    DUREE_BLOC_MS,
    Abandon,
    Bonjour,
    Dire,
    Erreur,
    Etat,
    FinEnonce,
    Interruption,
    Reveil,
    StopAudio,
    decoder_audio_sortant,
    encoder_audio_entrant,
)

from .aec import ouvrir_peripherique
from .reveilleur import PredicteurOpenWakeWord, ReveilleurMotCle, ReveilleurTouche
from .vad import DetecteurVoix, Endpointeur, FenetreEnergie

_journal = logging.getLogger(__name__)

URL_CORE = os.environ.get("ATLAS_CORE_URL", "ws://127.0.0.1:8080/ws/audio")

DUREE_BLOC_S = DUREE_BLOC_MS / 1000  # 0,020 s joués par trame
MARGE_SORTIE_S = 0.15  # latence de sortie du haut-parleur, à régler au banc
# Seuil de barge-in par défaut (spike S2) : une seule source de vérité pour
# _lire_bargein_dbfs() et ClientAudio, plutôt que la même valeur écrite deux fois.
_SEUIL_BARGEIN_DBFS_DEFAUT = -40.0

# Garde-fous de la capture : sans eux, un faux réveil ou un « Stop ! » isolé
# laisserait le micro ouvert vers le Core indéfiniment.
DELAI_SANS_PAROLE_S = 5.0
DUREE_MAX_ENONCE_S = 30.0
# Le temps de capture se compte en blocs, pas à l'horloge murale.
_BLOCS_PAR_S = 1000 // DUREE_BLOC_MS
_BLOCS_SANS_PAROLE = round(DELAI_SANS_PAROLE_S * _BLOCS_PAR_S)
_BLOCS_MAX_ENONCE = round(DUREE_MAX_ENONCE_S * _BLOCS_PAR_S)


@dataclass(frozen=True)
class Reglages:
    """Les seuils que le banc de mesure (tâche 14) et le spike S2 servent à choisir."""

    seuil_reveil: float
    silence_ms: int
    bargein_ms: int
    bargein_dbfs: float
    relance_s: float  # écoute rouverte après une réponse jouée ; 0 la désactive


def lire_reglages() -> Reglages:
    """Lit les réglages dans l'environnement, sinon les valeurs par défaut actuelles."""
    return Reglages(
        seuil_reveil=float(os.environ.get("ATLAS_REVEIL_SEUIL", "0.5")),
        silence_ms=int(os.environ.get("ATLAS_SILENCE_MS", "400")),
        bargein_ms=int(os.environ.get("ATLAS_BARGEIN_MS", "300")),
        bargein_dbfs=_lire_bargein_dbfs(),
        relance_s=_lire_relance_s(),
    )


def _lire_bargein_dbfs() -> float:
    brute = os.environ.get("ATLAS_BARGEIN_DBFS", str(_SEUIL_BARGEIN_DBFS_DEFAUT))
    try:
        valeur = float(brute)
    except ValueError as erreur:
        raise ValueError(f"ATLAS_BARGEIN_DBFS invalide : {brute!r} n'est pas un nombre") from erreur
    if not math.isfinite(valeur) or not (-120.0 <= valeur <= 0.0):
        raise ValueError(
            f"ATLAS_BARGEIN_DBFS invalide : {brute!r} doit être un nombre fini entre -120 et 0"
        )
    return valeur


def _lire_relance_s() -> float:
    brute = os.environ.get("ATLAS_RELANCE_S", "10")
    try:
        valeur = float(brute)
    except ValueError as erreur:
        raise ValueError(f"ATLAS_RELANCE_S invalide : {brute!r} n'est pas un nombre") from erreur
    if not math.isfinite(valeur) or not (0.0 <= valeur <= 60.0):
        raise ValueError(
            f"ATLAS_RELANCE_S invalide : {brute!r} doit être un nombre de secondes entre 0 et 60"
        )
    return valeur


class Transport(Protocol):
    async def envoyer_json(self, msg) -> None: ...
    async def envoyer_binaire(self, trame: bytes) -> None: ...


class ClientAudio:
    def __init__(
        self,
        transport,
        peripherique,
        detecteur,
        endpointeur,
        reveilleur,
        bargein=None,
        horloge: Callable[[], float] | None = None,
        seuil_bargein_dbfs: float = _SEUIL_BARGEIN_DBFS_DEFAUT,
        relance_s: float = 0.0,
    ) -> None:
        self._transport = transport
        self._peripherique = peripherique
        self._detecteur = detecteur
        self._endpointeur = endpointeur
        self._reveilleur = reveilleur
        self._capture = False
        self._id_courant = 0
        # Plus grand identifiant d'énoncé coupé : ni ses phrases encore en vol ni
        # ses trames ne doivent plus jamais sonner, ni ré-armer le barge-in.
        self._id_coupe = 0
        self._bargein = bargein or Endpointeur(silence_ms=400, parole_min_ms=300)
        self._horloge = horloge or time.monotonic
        # Écho résiduel d'Atlas pendant que l'annulateur d'écho converge (spike S2) :
        # une parole détectée pendant la lecture ne compte pour le barge-in que si son
        # niveau sur 300 ms dépasse ce seuil. Ne s'applique qu'à la surveillance du
        # barge-in ; jamais à la capture normale ni à la fin de phrase.
        self._seuil_bargein_dbfs = seuil_bargein_dbfs
        self._fenetre_energie = FenetreEnergie()
        # Échéance, sur notre propre horloge, de la fin de l'audio déjà confié au
        # haut-parleur. Le Core finit d'ENVOYER bien avant que le son finisse de jouer.
        self._fin_lecture = 0.0
        # Derniers blocs entendus pendant la surveillance du barge-in, avec leur
        # verdict de voix : la parole qui déclenche l'interruption (« Non, attends… »)
        # doit partir vers le Core, sinon Whisper perd le premier mot. La porte
        # d'énergie retarde encore ce moment le temps que la fenêtre de 300 ms monte
        # en régime (jusqu'à sa taille en blocs) : sans en tenir compte, les tout
        # premiers blocs d'une parole calme sortiraient du pré-roulement avant même
        # que l'interruption ne se déclenche.
        seuil_blocs = self._bargein.blocs_parole_min  # seuil de l'endpointeur de barge-in
        self._pre_roulement: deque[tuple[bytes, bool]] = deque(
            maxlen=seuil_blocs + self._fenetre_energie.taille + 10
        )
        self._blocs_captures = 0
        self._parole_vue = False
        self._blocs_sans_parole = _BLOCS_SANS_PAROLE
        # La relance : une réponse a été entendue jusqu'au bout (ni coupée, ni muette),
        # et le Core a fini son tour. L'écoute se rouvre quand le son s'est tu.
        self._relance_s = relance_s
        self._reponse_jouee = False
        self._relance_due = False

    def _atlas_parle_encore(self) -> bool:
        # Une échéance expire d'elle-même : le micro ne peut jamais rester sourd.
        return self._horloge() < self._fin_lecture + MARGE_SORTIE_S

    # --- micro vers Core --------------------------------------------------

    async def boucle_capture(self) -> None:
        with contextlib.suppress(asyncio.CancelledError, asyncio.IncompleteReadError):
            while True:
                bloc = await self._peripherique.lire_bloc()
                await self._traiter_bloc(bloc)

    async def _traiter_bloc(self, bloc: bytes) -> None:
        if self._atlas_parle_encore():
            await self._surveiller_bargein(bloc)
            return

        if not self._capture:
            if not self._relance_due:
                # Pas de pré-roulement ici : envoyer « Hey Atlas » à Whisper
                # polluerait la transcription.
                if self._reveilleur.examiner(bloc):
                    self._ouvrir_capture()
                    await self._annoncer_ecoute()
                return
            # Atlas vient de finir de parler : il écoute encore un moment, sans mot de
            # réveil. Ce bloc-ci est déjà capturé, pour ne perdre aucun premier mot.
            self._relance_due = False
            self._ouvrir_capture(self._relance_s)
            await self._annoncer_ecoute()

        await self._capturer(bloc, self._detecteur.parle(bloc))

    def _ouvrir_capture(self, delai_sans_parole_s: float = DELAI_SANS_PAROLE_S) -> None:
        self._capture = True
        self._endpointeur.reinitialiser()
        self._blocs_captures = 0
        self._parole_vue = False
        self._blocs_sans_parole = round(delai_sans_parole_s * _BLOCS_PAR_S)

    async def _annoncer_ecoute(self) -> None:
        await self._transport.envoyer_json(Reveil(confiance=1.0, horodatage=time.time()))

    async def _capturer(self, bloc: bytes, parle: bool) -> None:
        """Envoie un bloc capturé au Core et décide si l'énoncé est terminé."""
        await self._transport.envoyer_binaire(encoder_audio_entrant(bloc))
        self._blocs_captures += 1
        decision = self._endpointeur.ajouter(parle)
        if decision == "debut":
            self._parole_vue = True

        if decision == "fin":
            await self._clore_capture()
        elif self._blocs_captures >= _BLOCS_MAX_ENONCE:
            _journal.info("capture close : durée maximale d'un énoncé atteinte")
            await self._clore_capture()
        elif not self._parole_vue and self._blocs_captures >= self._blocs_sans_parole:
            _journal.info("capture close : aucune parole entendue")
            await self._abandonner_capture()

    async def _clore_capture(self) -> None:
        self._capture = False
        await self._transport.envoyer_json(FinEnonce(duree_ms=0))

    async def _abandonner_capture(self) -> None:
        # Rien n'a été dit : envoyer ce silence à Whisper l'inviterait à inventer une
        # phrase. Le Core revient au repos sans transcrire.
        self._capture = False
        await self._transport.envoyer_json(Abandon())

    async def _surveiller_bargein(self, bloc: bytes) -> None:
        parle = self._detecteur.parle(bloc)
        # Le pré-roulement garde le verdict BRUT : une fois l'interruption détectée,
        # la capture qui rejoue ces blocs doit voir la vraie parole, pas ce que la
        # porte d'énergie en a laissé passer.
        self._pre_roulement.append((bloc, parle))
        niveau = self._fenetre_energie.ajouter(bloc)
        if self._bargein.ajouter(parle and niveau > self._seuil_bargein_dbfs) != "debut":
            return
        _journal.info("interruption détectée (%.1f dBFS sur 300 ms)", niveau)
        pre_roulement = list(self._pre_roulement)
        self._couper()
        await self._peripherique.vider()
        await self._transport.envoyer_json(Interruption(horodatage=time.time()))
        self._ouvrir_capture()
        # Le pré-roulement est capturé comme le reste : envoyé, et compté par
        # l'endpointeur, qui sait ainsi que la parole a déjà commencé.
        for bloc_passe, parle_passe in pre_roulement:
            if not self._capture:
                break
            await self._capturer(bloc_passe, parle_passe)

    def _couper(self) -> None:
        """Marque l'énoncé courant comme coupé ; son audio vient d'être vidé."""
        self._id_coupe = max(self._id_coupe, self._id_courant)
        self._id_courant = 0
        self._fin_lecture = 0.0
        self._pre_roulement.clear()
        self._fenetre_energie.reinitialiser()
        # Une réponse coupée n'est pas une réponse entendue : l'écoute est déjà
        # ouverte (interruption) ou une question tapée a pris la main.
        self._reponse_jouee = False
        self._relance_due = False

    # --- Core vers haut-parleur -------------------------------------------

    async def sur_message(self, msg) -> None:
        if isinstance(msg, Dire):
            if msg.id_enonce <= self._id_coupe:
                return  # phrase en vol d'une réponse coupée : on l'ignore
            if msg.id_enonce != self._id_courant:
                # Nouvel énoncé seulement : remettre le compteur à zéro à chaque
                # phrase effacerait la parole que l'utilisateur a déjà accumulée.
                self._id_courant = msg.id_enonce
                self._reponse_jouee = True
                self._bargein.reinitialiser()
                self._pre_roulement.clear()
                self._fenetre_energie.reinitialiser()
        elif isinstance(msg, StopAudio):
            self._couper()
            await self._peripherique.vider()
        elif isinstance(msg, Erreur):
            _journal.warning("erreur signalée par le Core [%s] : %s", msg.code, msg.message)
        elif isinstance(msg, Etat):
            # « repos » dit que le Core a fini d'ENVOYER, pas que le son est joué : il
            # n'arme ni ne désarme le barge-in, que seule l'horloge de lecture tranche.
            # Il arme en revanche la relance, qui attendra que le son se taise. Sans ce
            # signal, un blanc entre deux phrases relancerait l'écoute en pleine réponse.
            self._relance_due = (
                msg.valeur == "repos" and self._reponse_jouee and self._relance_s > 0
            )
            if msg.valeur == "repos":
                self._reponse_jouee = False

    async def sur_trame(self, trame: bytes) -> None:
        identifiant, pcm = decoder_audio_sortant(trame)
        if identifiant <= self._id_coupe or identifiant != self._id_courant:
            return  # trame d'un énoncé interrompu : on la jette
        await self._peripherique.jouer(pcm)
        self._fin_lecture = max(self._horloge(), self._fin_lecture) + DUREE_BLOC_S


class TransportWebSocket:
    def __init__(self, ws) -> None:
        self._ws = ws

    async def envoyer_json(self, msg) -> None:
        await self._ws.send(msg.model_dump_json())

    async def envoyer_binaire(self, trame: bytes) -> None:
        await self._ws.send(trame)


async def principal() -> None:
    import json

    import websockets
    from pydantic import TypeAdapter

    from atlas_core.protocole import MessageCore

    adaptateur = TypeAdapter(MessageCore)
    logging.basicConfig(level=logging.INFO)
    # Réglages et réveilleur d'abord : une variable mal formée ou un modèle absent
    # doit échouer avant que le périphérique audio soit ouvert.
    reglages = lire_reglages()
    if os.environ.get("ATLAS_REVEILLEUR", "touche") == "motcle":
        reveilleur = ReveilleurMotCle(PredicteurOpenWakeWord(), seuil=reglages.seuil_reveil)
    else:
        reveilleur = ReveilleurTouche()
    peripherique = await ouvrir_peripherique()

    async with websockets.connect(URL_CORE) as ws:
        transport = TransportWebSocket(ws)
        client = ClientAudio(
            transport=transport,
            peripherique=peripherique,
            detecteur=DetecteurVoix(),
            endpointeur=Endpointeur(silence_ms=reglages.silence_ms),
            reveilleur=reveilleur,
            bargein=Endpointeur(parole_min_ms=reglages.bargein_ms),
            seuil_bargein_dbfs=reglages.bargein_dbfs,
            relance_s=reglages.relance_s,
        )
        await transport.envoyer_json(Bonjour(client="m5", capacites=["aec", "vad"]))
        capture = asyncio.create_task(client.boucle_capture())
        try:
            async for recu in ws:
                if isinstance(recu, bytes):
                    await client.sur_trame(recu)
                else:
                    await client.sur_message(adaptateur.validate_python(json.loads(recu)))
        finally:
            capture.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await capture
            await peripherique.fermer()


if __name__ == "__main__":
    asyncio.run(principal())
