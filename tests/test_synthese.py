import httpx
import pytest

from helios_core.synthese import ClientSynthese

_ENTETE = b"RIFF" + b"\xff" * 4 + b"WAVE" + b"fmt " + b"\x00" * 20 + b"data" + b"\xff" * 4


async def _collecter(client: ClientSynthese, texte: str) -> list[bytes]:
    return [bloc async for bloc in client.synthetiser(texte)]


async def test_les_blocs_sortent_sans_l_entete():
    corps = _ENTETE + b"\x01\x02" * 320 * 3

    def repondre(requete: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=corps)

    async with httpx.AsyncClient(transport=httpx.MockTransport(repondre)) as http:
        blocs = await _collecter(ClientSynthese("http://tts", "fr", http), "Bonjour.")
    assert len(blocs) == 3
    assert all(len(b) == 640 for b in blocs)
    assert b"RIFF" not in b"".join(blocs)


async def test_un_reste_partiel_est_complete_par_du_silence():
    corps = _ENTETE + b"\x01\x02" * 400  # 800 octets : un bloc plein + 160 octets
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=corps))
    ) as http:
        blocs = await _collecter(ClientSynthese("http://tts", "fr", http), "Bonjour.")
    assert len(blocs) == 2
    assert all(len(b) == 640 for b in blocs)
    assert blocs[1].endswith(b"\x00" * 480)


async def test_une_erreur_du_service_remonte_une_exception():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(503, text="occupé"))
    ) as http:
        with pytest.raises(RuntimeError, match="synthèse"):
            await _collecter(ClientSynthese("http://tts", "fr", http), "Bonjour.")
