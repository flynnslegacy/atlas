import json

import httpx
import numpy as np

from scripts.mot_reveil.audio import ecrire_wav
from scripts.mot_reveil.filtrer import filtrer

TRANSCRIPTIONS = {"bon": "Hey Atlas.", "rate": "Et là.", "nbon": "Hélas.", "nrate": "Hey Atlas !"}
SORTE = {"bon": "positifs", "rate": "positifs", "nbon": "negatifs", "nrate": "negatifs"}


def _clips(racine):
    """Écrit les extraits (contenu distinct par nom) et rend {contenu: transcription}."""
    par_contenu = {}
    for k, (nom, texte) in enumerate(TRANSCRIPTIONS.items()):
        audio = np.full(12000, 0.1 + 0.05 * k, dtype=np.float32)
        for source in ("piper", "qwen"):
            chemin = racine / source / SORTE[nom] / f"{nom}.wav"
            ecrire_wav(chemin, audio)
            par_contenu[chemin.read_bytes()] = texte
    return par_contenu


async def test_filtrer_garde_les_bons_et_reprend(tmp_path):
    clips, retenus = tmp_path / "clips", tmp_path / "retenus"
    par_contenu = _clips(clips)
    appels = []

    def repondre(requete):
        appels.append(requete)
        return httpx.Response(200, json={"text": par_contenu[requete.content]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(repondre)) as http:
        bilan = await filtrer(http, "http://stt", clips, retenus)
    assert bilan["piper"] == {"positifs": 1, "negatifs": 1}
    assert sorted(p.name for p in (retenus / "positifs").glob("*.wav")) == [
        "piper_bon.wav",
        "qwen_bon.wav",
    ]
    assert sorted(p.name for p in (retenus / "negatifs").glob("*.wav")) == [
        "piper_nbon.wav",
        "qwen_nbon.wav",
    ]
    journal = json.loads((retenus / "filtrage.json").read_text())
    assert journal["piper/positifs/rate.wav"] == {"texte": "Et là.", "garde": False}
    n = len(appels)
    async with httpx.AsyncClient(transport=httpx.MockTransport(repondre)) as http:
        await filtrer(http, "http://stt", clips, retenus)
    assert len(appels) == n  # tout était déjà tranché : aucune nouvelle requête


async def test_filtrer_sauvegarde_le_journal_avant_la_fin(tmp_path):
    """Un docker stop (SIGTERM) ou un crash pendant le filtrage ne doit pas tout perdre."""
    clips, retenus = tmp_path / "clips", tmp_path / "retenus"
    chemin_journal = retenus / "filtrage.json"
    texte_par_contenu = {}
    for k, nom in enumerate(("p1", "p2")):
        audio = np.full(12000, 0.1 + 0.05 * k, dtype=np.float32)
        chemin = clips / "src" / "positifs" / f"{nom}.wav"
        ecrire_wav(chemin, audio)
        texte_par_contenu[chemin.read_bytes()] = "Hey Atlas."
    audio = np.full(12000, 0.9, dtype=np.float32)
    chemin = clips / "src" / "negatifs" / "n1.wav"
    ecrire_wav(chemin, audio)
    texte_par_contenu[chemin.read_bytes()] = "Hélas."

    appels = []
    verifie = []

    def repondre(requete):
        appels.append(requete)
        if len(appels) == 3:
            # Les deux positifs sont déjà tranchés : sauvegarde_tous=2 a dû sauvegarder
            # le journal avant même que ce 3e appel (un négatif) ne parte.
            verifie.append(chemin_journal.exists())
            if chemin_journal.exists():
                verifie.append(len(json.loads(chemin_journal.read_text())))
        return httpx.Response(200, json={"text": texte_par_contenu[requete.content]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(repondre)) as http:
        await filtrer(http, "http://stt", clips, retenus, paralleles=1, sauvegarde_tous=2)
    assert verifie == [True, 2]
