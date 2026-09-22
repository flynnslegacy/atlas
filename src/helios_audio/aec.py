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
        if self._proc:
            self._proc.terminate()
            await self._proc.wait()
            self._proc = None


class PeripheriqueSounddevice:
    """Repli sans annulation d'écho : ne convient qu'au casque."""

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
        # donc une deque bornée protégée par un verrou classique, touchée à
        # la fois par ce callback et par `jouer`/`vider`.
        self._file_lecture: deque[bytes] = deque(maxlen=200)
        self._verrou_lecture = threading.Lock()
        self._boucle = asyncio.get_running_loop()

        def sur_entree(donnees, cadres, temps, etat) -> None:
            self._boucle.call_soon_threadsafe(self._file_capture.put_nowait, bytes(donnees))

        def sur_sortie(sortie, cadres, temps, etat) -> None:
            with self._verrou_lecture:
                bloc = self._file_lecture.popleft() if self._file_lecture else None
            sortie[:] = bloc if bloc is not None else b"\x00" * len(sortie)

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
        with self._verrou_lecture:
            self._file_lecture.append(pcm)

    async def vider(self) -> None:
        with self._verrou_lecture:
            self._file_lecture.clear()

    async def fermer(self) -> None:
        self._entree.stop()
        self._sortie.stop()


async def ouvrir_peripherique() -> PeripheriqueAudio:
    if os.environ.get("HELIOS_AUDIO_PERIPHERIQUE", "aec") == "sounddevice":
        return PeripheriqueSounddevice()
    peripherique = PeripheriqueAec()
    await peripherique.demarrer()
    return peripherique
