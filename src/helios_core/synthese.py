"""Client du service helios-tts, en flux."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from .protocole import TAILLE_BLOC_OCTETS

_TAILLE_ENTETE_WAV = 44


class ClientSynthese:
    def __init__(self, base_url: str, voix: str, http: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/")
        self._voix = voix
        self._http = http

    async def synthetiser(self, texte: str) -> AsyncIterator[bytes]:
        """Rend des blocs de 20 ms, en-tête WAV retiré, dernier bloc complété au silence."""
        a_sauter = _TAILLE_ENTETE_WAV
        reste = b""
        async with self._http.stream(
            "POST",
            f"{self._base}/synthesize",
            json={"text": texte, "voice": self._voix},
            timeout=60.0,
        ) as reponse:
            if reponse.status_code != 200:
                corps = await reponse.aread()
                raise RuntimeError(f"synthèse en échec ({reponse.status_code}) : {corps[:200]!r}")
            async for morceau in reponse.aiter_bytes():
                if a_sauter:
                    saut = min(a_sauter, len(morceau))
                    morceau = morceau[saut:]
                    a_sauter -= saut
                    if not morceau:
                        continue
                reste += morceau
                while len(reste) >= TAILLE_BLOC_OCTETS:
                    yield reste[:TAILLE_BLOC_OCTETS]
                    reste = reste[TAILLE_BLOC_OCTETS:]
        if reste:
            yield reste + b"\x00" * (TAILLE_BLOC_OCTETS - len(reste))
