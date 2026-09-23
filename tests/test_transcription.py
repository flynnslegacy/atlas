import httpx
import pytest

from atlas_core.protocole import TAILLE_BLOC_OCTETS
from atlas_core.transcription import ClientTranscription, pcm_vers_wav


def test_pcm_vers_wav_produit_un_entete_lisible():
    wav = pcm_vers_wav(b"\x00\x00" * 320)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert len(wav) == 44 + 640


async def test_transcrire_rend_le_texte():
    recus: list[bytes] = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        recus.append(requete.content)
        return httpx.Response(
            200, json={"text": "il est midi", "language": "fr", "duration_ms": 900}
        )

    transport = httpx.MockTransport(repondre)
    async with httpx.AsyncClient(transport=transport) as http:
        client = ClientTranscription("http://stt", http)
        assert await client.transcrire(b"\x00\x00" * 320) == "il est midi"
    assert recus[0][:4] == b"RIFF"


async def test_une_erreur_du_service_remonte_une_exception():
    transport = httpx.MockTransport(lambda r: httpx.Response(500, text="boum"))
    async with httpx.AsyncClient(transport=transport) as http:
        client = ClientTranscription("http://stt", http)
        with pytest.raises(RuntimeError, match="transcription"):
            await client.transcrire(b"\x00\x00" * TAILLE_BLOC_OCTETS)
