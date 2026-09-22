"""Accès au périphérique audio du M5.

Deux implémentations derrière le même protocole : le binaire Swift avec
annulation d'écho, et un repli sounddevice pour l'usage au casque.
"""

from __future__ import annotations

import asyncio
import os
import struct
import threading
from collections import deque
from typing import Protocol

from helios_core.protocole import FREQUENCE_HZ as FREQUENCE
from helios_core.protocole import TAILLE_BLOC_OCTETS as TAILLE_BLOC

_TYPE_LECTURE = 0x01
_TYPE_VIDAGE = 0x02

CHEMIN_BINAIRE = os.environ.get("HELIOS_AEC_BINAIRE", "src/helios_aec/.build/release/helios-aec")


def trame_lecture(pcm: bytes) -> bytes:
    if len(pcm) != TAILLE_BLOC:
        raise ValueError(f"bloc de {len(pcm)} octets, attendu {TAILLE_BLOC}")
    return bytes([_TYPE_LECTURE]) + struct.pack(">I", len(pcm)) + pcm


def trame_vidage() -> bytes:
    return bytes([_TYPE_VIDAGE]) + struct.pack(">I", 0)


class PeripheriqueAudio(Protocol):
    async def lire_bloc(self) -> bytes: ...
    async def jouer(self, pcm: bytes) -> None: ...
    async def vider(self) -> None: ...
    async def fermer(self) -> None: ...


class PeripheriqueAec:
    """Pilote le binaire Swift. À utiliser dès que le son sort sur des enceintes."""

    def __init__(self, chemin: str = CHEMIN_BINAIRE) -> None:
        self._chemin = chemin
        self._proc: asyncio.subprocess.Process | None = None

    async def demarrer(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            self._chemin,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )

    async def lire_bloc(self) -> bytes:
        assert self._proc and self._proc.stdout
        return await self._proc.stdout.readexactly(TAILLE_BLOC)

    async def jouer(self, pcm: bytes) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(trame_lecture(pcm))
        await self._proc.stdin.drain()

    async def vider(self) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(trame_vidage())
        await self._proc.stdin.drain()

    async def fermer(self) -> None:
        if self._proc is None:
            return
        proc, self._proc = self._proc, None
        try:
            if proc.returncode is None:
                proc.terminate()
        except ProcessLookupError:
            # Le binaire est déjà mort (micro refusé, périphérique parti) :
            # `terminate()` sur un processus déjà récolté lève cette
            # exception. `self._proc` est déjà remis à None ci-dessus, donc
            # `fermer()` ne reste jamais bloqué dans un état non atteignable.
            pass
        finally:
            # Attendu même si `terminate()` a levé : sinon l'enfant n'est
            # jamais recueilli et le transport asyncio jamais nettoyé.
            await proc.wait()


def _resoudre_si_pendante(attente: asyncio.Future[None]) -> None:
    """Résout un futur d'attente sans lever si un autre chemin l'a déjà fait.

    Appelé depuis `call_soon_threadsafe` (fil audio) ou directement depuis la
    boucle (`vider`, `fermer`) : dans les deux cas, un même futur peut être
    résolu par plus d'un chemin (place libérée ET fermeture, par exemple).
    """
    if not attente.done():
        attente.set_result(None)


class PeripheriqueSounddevice:
    """Repli sans annulation d'écho : ne convient qu'au casque."""

    _CAPACITE_LECTURE = 200  # ~4 s à 20 ms/bloc, comme la asyncio.Queue du brief

    def __init__(self) -> None:
        import sounddevice as sd

        # Capture : le callback tourne sur le thread audio de PortAudio et ne
        # touche `_file_capture` qu'à travers `call_soon_threadsafe`, donc
        # toutes les opérations sur cette asyncio.Queue restent sur la boucle.
        self._file_capture: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        # Lecture : le callback de sortie, lui, doit lire un bloc *depuis* le
        # thread audio sans repasser par la boucle (pas d'`await` possible
        # dans un callback temps réel). Une asyncio.Queue n'est pas conçue
        # pour être lue depuis un thread étranger à sa boucle ; on utilise
        # donc une deque protégée par un verrou classique, touchée à la fois
        # par ce callback et par `jouer`/`vider`. Sa taille est bornée à la
        # main (pas de `maxlen`) : `maxlen` évincerait silencieusement le
        # bloc le plus ANCIEN — celui sur le point d'être joué — alors que
        # `PeripheriqueAec.jouer` freine le producteur via `drain()`. On veut
        # la même contre-pression des deux côtés du protocole.
        #
        # La contre-pression elle-même n'utilise PAS un `asyncio.Event`
        # partagé : `Event.wait()` rend la main immédiatement, SANS point de
        # suspension, quand le drapeau est déjà posé. Comme `sur_sortie` pose
        # l'évènement à chaque rappel où il reste de la place (cinquante fois
        # par seconde, y compris quand personne n'attend), un `jouer` qui
        # attend pile au mauvais moment tournerait en boucle chaude sur la
        # boucle d'évènements — celle-là même qui draine la capture du micro
        # via `call_soon_threadsafe`. Un `Future` neuf par attente n'a pas ce
        # problème : il n'est jamais déjà résolu, `await` suspend donc
        # toujours réellement, et on ne le résout que lorsqu'une place vient
        # effectivement de se libérer ET qu'un producteur attend.
        self._file_lecture: deque[bytes] = deque()
        self._verrou_lecture = threading.Lock()
        self._attentes_place: list[asyncio.Future[None]] = []
        self._ferme = False
        self._boucle = asyncio.get_running_loop()

        def sur_entree(donnees, cadres, temps, etat) -> None:
            self._boucle.call_soon_threadsafe(self._file_capture.put_nowait, bytes(donnees))

        def sur_sortie(sortie, cadres, temps, etat) -> None:
            with self._verrou_lecture:
                bloc = self._file_lecture.popleft() if self._file_lecture else None
                reveil = None
                if len(self._file_lecture) < self._CAPACITE_LECTURE and self._attentes_place:
                    reveil = self._attentes_place.pop(0)
            # Un bloc de mauvaise taille ne doit jamais lever ici : l'affectation
            # de tranche sur `sortie` exigerait une longueur exacte et une
            # exception dans ce callback tue le flux de sortie (paAbort côté
            # PortAudio) sans jamais remonter à l'appelant fautif. `jouer`
            # valide déjà la taille ; ce contrôle est une seconde ligne de
            # défense, pas le chemin normal.
            if bloc is not None and len(bloc) == len(sortie):
                sortie[:] = bloc
            else:
                sortie[:] = b"\x00" * len(sortie)
            if reveil is not None:
                self._boucle.call_soon_threadsafe(_resoudre_si_pendante, reveil)

        self._entree = sd.RawInputStream(
            samplerate=FREQUENCE,
            channels=1,
            dtype="int16",
            blocksize=TAILLE_BLOC // 2,
            callback=sur_entree,
        )
        self._sortie = sd.RawOutputStream(
            samplerate=FREQUENCE,
            channels=1,
            dtype="int16",
            blocksize=TAILLE_BLOC // 2,
            callback=sur_sortie,
        )
        self._entree.start()
        self._sortie.start()

    async def lire_bloc(self) -> bytes:
        return await self._file_capture.get()

    async def jouer(self, pcm: bytes) -> None:
        if len(pcm) != TAILLE_BLOC:
            raise ValueError(f"bloc de {len(pcm)} octets, attendu {TAILLE_BLOC}")
        while True:
            with self._verrou_lecture:
                if self._ferme:
                    raise RuntimeError("le périphérique audio est fermé")
                if len(self._file_lecture) < self._CAPACITE_LECTURE:
                    self._file_lecture.append(pcm)
                    return
                attente: asyncio.Future[None] = self._boucle.create_future()
                self._attentes_place.append(attente)
            try:
                await attente
            except asyncio.CancelledError:
                with self._verrou_lecture:
                    if attente in self._attentes_place:
                        self._attentes_place.remove(attente)
                raise
            # Bouclé : soit une place s'est libérée, soit `fermer()` a réveillé
            # tout le monde — le contrôle de `self._ferme` en tête de boucle
            # tranche entre les deux avant d'écrire dans un périphérique fermé.

    async def vider(self) -> None:
        with self._verrou_lecture:
            self._file_lecture.clear()
            attentes, self._attentes_place = self._attentes_place, []
        for attente in attentes:
            _resoudre_si_pendante(attente)

    async def fermer(self) -> None:
        with self._verrou_lecture:
            self._ferme = True
            attentes, self._attentes_place = self._attentes_place, []
        for attente in attentes:
            _resoudre_si_pendante(attente)
        self._entree.stop()
        self._sortie.stop()


async def ouvrir_peripherique() -> PeripheriqueAudio:
    if os.environ.get("HELIOS_AUDIO_PERIPHERIQUE", "aec") == "sounddevice":
        return PeripheriqueSounddevice()
    peripherique = PeripheriqueAec()
    await peripherique.demarrer()
    return peripherique
