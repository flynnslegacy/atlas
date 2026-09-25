"""Le daemon audio du M5.

Trois tâches par connexion au Core (voir `connexion.py`) : l'une lit le micro et parle
au Core, une autre reçoit du Core, et la dernière joue le son à son rythme, sans jamais
prendre plus de quelques secondes d'avance. Le client ne décide de rien d'autre que du
barge-in — il le décide localement parce que 200 ms d'aller-retour réseau rendraient
l'interruption molle — et de la relance : une fois la réponse d'Atlas jouée, il rouvre
l'écoute un moment sans mot de réveil, pour que la conversation continue. Si le Core
disparaît, le client se reconnecte seul.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import os
import time
from collections import deque
from collections.abc import Awaitable, Callable
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
from .connexion import PeripheriqueEnPanne, boucle_de_connexion, servir_connexion
from .reveilleur import PredicteurOpenWakeWord, ReveilleurMotCle, ReveilleurTouche
from .vad import DetecteurVoix, Endpointeur, FenetreEnergie

_journal = logging.getLogger(__name__)

URL_CORE = os.environ.get("ATLAS_CORE_URL", "ws://127.0.0.1:8080/ws/audio")

DUREE_BLOC_S = DUREE_BLOC_MS / 1000  # 0,020 s joués par trame
MARGE_SORTIE_S = 0.15  # latence de sortie du haut-parleur, à régler au banc
# Au plus ce son d'avance confié au haut-parleur (le binaire Swift en accepterait 30 s
# avant de freiner) : un vidage reste immédiat, et l'horloge de lecture reste juste.
AVANCE_MAX_S = 5.0
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


def lire_cle_audio() -> str:
    """La clé que le client présente au Core dans son `Bonjour` : la même des deux côtés."""
    cle = os.environ.get("ATLAS_AUDIO_CLE", "").strip()
    if not cle:
        raise ValueError(
            "ATLAS_AUDIO_CLE manquante : mets dans le .env du client la même clé que dans "
            "celui du Core"
        )
    return cle


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


async def _frontiere_peripherique(appel: Awaitable):
    """Enveloppe un appel au périphérique audio (`lire_bloc`, `jouer`, `vider`) : toute
    panne à cette frontière devient `PeripheriqueEnPanne`. C'est la CAUSE qui distingue
    une panne du périphérique d'une coupure réseau, pas la tâche qui l'a levée — la même
    tâche de capture fait à la fois de la lecture micro (le périphérique) et des envois au
    Core (le réseau) ; un `ws.send` qui échoue parce que le Core est parti n'est jamais
    une panne du périphérique, et ne doit pas empêcher la reconnexion."""
    try:
        return await appel
    except asyncio.CancelledError:
        raise
    except Exception as e:
        raise PeripheriqueEnPanne("le périphérique audio est mort") from e


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
        attendre: Callable[[float], Awaitable[None]] | None = None,
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
        self._attendre = attendre or asyncio.sleep
        # Écho résiduel d'Atlas pendant que l'annulateur d'écho converge (spike S2) :
        # une parole détectée pendant la lecture ne compte pour le barge-in que si son
        # niveau sur 300 ms dépasse ce seuil. Ne s'applique qu'à la surveillance du
        # barge-in ; jamais à la capture normale ni à la fin de phrase.
        self._seuil_bargein_dbfs = seuil_bargein_dbfs
        self._fenetre_energie = FenetreEnergie()
        # Échéance, sur notre propre horloge, de la fin de l'audio déjà confié au
        # haut-parleur. Le Core finit d'ENVOYER bien avant que le son finisse de jouer.
        self._fin_lecture = 0.0
        # Le Core dit une réponse à voix haute : un « Dire » est arrivé, et aucun état
        # autre que « parole » ne l'a encore suivi. Le barge-in reste armé même dans un
        # blanc entre deux phrases, quand plus aucun son ne joue.
        self._core_parle = False
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
        # Une échéance expire d'elle-même, et tout état autre que « parole » désarme le
        # Core : le micro ne peut jamais rester sourd.
        return self._core_parle or self._horloge() < self._fin_lecture + MARGE_SORTIE_S

    # --- micro vers Core --------------------------------------------------

    async def boucle_capture(self) -> None:
        # Une annulation (extérieure, ou levée par un faux périphérique de test à court de
        # blocs) termine la capture sans bruit. Une vraie panne du périphérique — le
        # binaire Swift qui meurt lève `IncompleteReadError` — doit au contraire remonter,
        # via `_frontiere_peripherique`, en `PeripheriqueEnPanne` : `connexion.py` arrête
        # alors la connexion plutôt que de laisser le client tourner sourd indéfiniment.
        # Les envois à `_traiter_bloc` (le Core), eux, restent une coupure réseau ordinaire.
        with contextlib.suppress(asyncio.CancelledError):
            while True:
                bloc = await _frontiere_peripherique(self._peripherique.lire_bloc())
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
        # Le Core d'abord : il arrête la synthèse et Claude pendant que le son se vide.
        await self._transport.envoyer_json(Interruption(horodatage=time.time()))
        await _frontiere_peripherique(self._peripherique.vider())
        self._ouvrir_capture()
        # Le pré-roulement est capturé comme le reste : envoyé, et compté par
        # l'endpointeur, qui sait ainsi que la parole a déjà commencé.
        for bloc_passe, parle_passe in pre_roulement:
            if not self._capture:
                break
            await self._capturer(bloc_passe, parle_passe)

    def _couper(self, id_enonce: int = 0) -> None:
        """Marque l'énoncé courant (et `id_enonce`, si plus grand) comme coupé ; son audio
        vient d'être vidé. `id_enonce` couvre un `StopAudio` en avance sur un `Dire` (et
        ses trames) du même énoncé encore dans la file de `connexion.py` : sans lui, ce
        `Dire` en retard relèverait `_id_courant` et ferait rejouer une réponse déjà coupée."""
        self._id_coupe = max(self._id_coupe, self._id_courant, id_enonce)
        self._id_courant = 0
        self._fin_lecture = 0.0
        self._core_parle = False
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
            self._core_parle = True
            if msg.id_enonce != self._id_courant:
                # Nouvel énoncé seulement : remettre le compteur à zéro à chaque
                # phrase effacerait la parole que l'utilisateur a déjà accumulée.
                self._id_courant = msg.id_enonce
                self._reponse_jouee = True
                self._bargein.reinitialiser()
                self._pre_roulement.clear()
                self._fenetre_energie.reinitialiser()
        elif isinstance(msg, StopAudio):
            self._couper(msg.id_enonce)
            await _frontiere_peripherique(self._peripherique.vider())
        elif isinstance(msg, Erreur):
            _journal.warning("erreur signalée par le Core [%s] : %s", msg.code, msg.message)
        elif isinstance(msg, Etat):
            # « repos » dit que le Core a fini d'ENVOYER, pas que le son est joué : le
            # barge-in reste armé tant que l'horloge de lecture court. Mais tout état autre
            # que « parole » (repos, réflexion d'une recherche web…) dit que le Core ne
            # parle plus : le blanc qui suit n'est plus gardé. « repos » arme aussi la
            # relance, qui attendra que le son se taise ; sans ce signal, un blanc entre
            # deux phrases relancerait l'écoute en pleine réponse.
            if msg.valeur != "parole":
                self._core_parle = False
            self._relance_due = (
                msg.valeur == "repos" and self._reponse_jouee and self._relance_s > 0
            )
            if msg.valeur == "repos":
                self._reponse_jouee = False

    async def sur_trame(self, trame: bytes) -> None:
        """Joue une trame, sans jamais dépasser `AVANCE_MAX_S` d'avance : au-delà, on
        attend que le haut-parleur en ait joué une partie. Une coupure pendant l'attente
        ou pendant l'écriture jette la trame."""
        identifiant, pcm = decoder_audio_sortant(trame)
        while True:
            if not self._a_jouer(identifiant):
                return  # trame d'un énoncé interrompu : on la jette
            # L'avance qu'aurait le haut-parleur une fois cette trame écrite ; la
            # demi-trame de marge absorbe les arrondis de l'horloge.
            avance = self._fin_lecture - self._horloge() + DUREE_BLOC_S
            if avance <= AVANCE_MAX_S + DUREE_BLOC_S / 2:
                break
            await self._attendre(avance - AVANCE_MAX_S)
        await _frontiere_peripherique(self._peripherique.jouer(pcm))
        if self._a_jouer(identifiant):
            # Sinon, coupée pendant l'écriture : le vidage l'a suivie, l'horloge n'avance pas.
            self._fin_lecture = max(self._horloge(), self._fin_lecture) + DUREE_BLOC_S

    def _a_jouer(self, identifiant: int) -> bool:
        return identifiant > self._id_coupe and identifiant == self._id_courant

    async def arreter(self) -> None:
        """La connexion au Core est perdue : ce qui restait à jouer se tait."""
        self._couper()
        with contextlib.suppress(Exception):  # le binaire Swift a pu mourir avec elle
            await self._peripherique.vider()


class TransportWebSocket:
    def __init__(self, ws) -> None:
        self._ws = ws

    async def envoyer_json(self, msg) -> None:
        await self._ws.send(msg.model_dump_json())

    async def envoyer_binaire(self, trame: bytes) -> None:
        await self._ws.send(trame)


async def _vider_le_micro(peripherique) -> None:
    """Pendant que le Core est injoignable, personne d'autre ne lit le micro : sans cette
    tâche, l'audio s'accumule (le binaire Swift en rejoue de vieilles secondes au
    rebranchement ; sounddevice sature sa file et son rappel crie `QueueFull` en boucle)
    jusqu'à ce que la connexion revienne."""
    while True:
        await _frontiere_peripherique(peripherique.lire_bloc())


async def principal() -> None:
    import websockets

    logging.basicConfig(level=logging.INFO)
    # Réglages, clé et réveilleur d'abord : une variable mal formée ou un modèle absent
    # doit échouer avant que le périphérique audio soit ouvert.
    reglages = lire_reglages()
    cle = lire_cle_audio()
    if os.environ.get("ATLAS_REVEILLEUR", "touche") == "motcle":
        reveilleur = ReveilleurMotCle(PredicteurOpenWakeWord(), seuil=reglages.seuil_reveil)
    else:
        reveilleur = ReveilleurTouche()
    detecteur = DetecteurVoix()
    peripherique = await ouvrir_peripherique()

    async def servir(ws) -> None:
        transport = TransportWebSocket(ws)
        # Un client neuf à chaque connexion : le Core ouvre une session neuve, dont les
        # énoncés repartent de 1 ; les repères de l'ancien client les jetteraient tous.
        client = ClientAudio(
            transport=transport,
            peripherique=peripherique,
            detecteur=detecteur,
            endpointeur=Endpointeur(silence_ms=reglages.silence_ms),
            reveilleur=reveilleur,
            bargein=Endpointeur(parole_min_ms=reglages.bargein_ms),
            seuil_bargein_dbfs=reglages.bargein_dbfs,
            relance_s=reglages.relance_s,
        )
        await transport.envoyer_json(Bonjour(client="m5", capacites=["aec", "vad"], cle=cle))
        _journal.info("connecté au Core")
        await servir_connexion(ws, client)

    try:
        await boucle_de_connexion(
            lambda: websockets.connect(URL_CORE),
            servir,
            pendant_l_absence=lambda: _vider_le_micro(peripherique),
        )
    finally:
        await peripherique.fermer()


if __name__ == "__main__":
    asyncio.run(principal())
