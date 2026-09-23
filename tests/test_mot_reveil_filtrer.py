import json

import httpx
import numpy as np

from scripts.mot_reveil.audio import ecrire_wav
from scripts.mot_reveil.filtrer import filtrer

# nom -> (sorte, durée en échantillons à 16 kHz, transcription rendue par le faux Whisper)
EXTRAITS = {
    "bon": ("positifs", 12000, None),  # 0,75 s
    "long": ("positifs", 48000, None),  # 3 s : du charabia
    "nbon": ("negatifs", 12000, "Hélas."),
    "nrate": ("negatifs", 12000, "Hey Atlas !"),
}


def _clips(racine):
    """Écrit les extraits (contenu distinct par nom) et rend {contenu: transcription}."""
    par_contenu = {}
    for k, (nom, (sorte, taille, texte)) in enumerate(EXTRAITS.items()):
        audio = np.full(taille, 0.1 + 0.05 * k, dtype=np.float32)
        for source in ("piper", "qwen"):
            chemin = racine / source / sorte / f"{nom}.wav"
            ecrire_wav(chemin, audio)
            par_contenu[chemin.read_bytes()] = texte
    return par_contenu


async def test_filtrer_garde_les_bons_et_reprend(tmp_path):
    clips, retenus = tmp_path / "clips", tmp_path / "retenus"
    par_contenu = _clips(clips)
    appels = []

    def repondre(requete):
        appels.append(requete)
        texte = par_contenu[requete.content]
        assert texte is not None, "un positif ne doit jamais partir chez Whisper"
        return httpx.Response(200, json={"text": texte})

    async with httpx.AsyncClient(transport=httpx.MockTransport(repondre)) as http:
        bilan = await filtrer(http, "http://stt", clips, retenus)
    assert bilan["piper"] == {"positifs": 1, "negatifs": 1}
    assert len(appels) == 4  # seulement les négatifs, deux par source
    assert sorted(p.name for p in (retenus / "positifs").glob("*.wav")) == [
        "piper_bon.wav",
        "qwen_bon.wav",
    ]
    assert sorted(p.name for p in (retenus / "negatifs").glob("*.wav")) == [
        "piper_nbon.wav",
        "qwen_nbon.wav",
    ]
    journal = json.loads((retenus / "filtrage.json").read_text())
    assert journal["piper/positifs/long.wav"] == {"duree_s": 3.0, "garde": False}
    assert journal["piper/negatifs/nrate.wav"] == {
        "texte": "Hey Atlas !",
        "duree_s": 0.75,
        "garde": False,
    }
    n = len(appels)
    async with httpx.AsyncClient(transport=httpx.MockTransport(repondre)) as http:
        await filtrer(http, "http://stt", clips, retenus)
    assert len(appels) == n  # tout était déjà tranché : aucune nouvelle requête


async def test_filtrer_ignore_les_dossiers_d_essai(tmp_path):
    """L'essai s'écrit dans <source>/essai/ : ses extraits ne doivent pas entrer."""
    clips, retenus = tmp_path / "clips", tmp_path / "retenus"
    ecrire_wav(clips / "piper" / "essai" / "positifs" / "e1.wav", np.full(12000, 0.2, np.float32))
    ecrire_wav(clips / "piper" / "positifs" / "p1.wav", np.full(12000, 0.3, np.float32))
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: None)) as http:
        bilan = await filtrer(http, "http://stt", clips, retenus)
    assert bilan == {"piper": {"positifs": 1, "negatifs": 0}}
    assert [p.name for p in (retenus / "positifs").glob("*.wav")] == ["piper_p1.wav"]


async def test_filtrer_sauvegarde_le_journal_avant_la_fin(tmp_path):
    """Un docker stop (SIGTERM) ou un crash pendant le filtrage ne doit pas tout perdre."""
    clips, retenus = tmp_path / "clips", tmp_path / "retenus"
    chemin_journal = retenus / "filtrage.json"
    for k, nom in enumerate(("p1", "p2")):
        ecrire_wav(
            clips / "src" / "positifs" / f"{nom}.wav", np.full(12000, 0.1 + 0.05 * k, np.float32)
        )
    ecrire_wav(clips / "src" / "negatifs" / "n1.wav", np.full(12000, 0.9, np.float32))

    verifie = []

    def repondre(requete):
        # Les deux positifs sont déjà tranchés : sauvegarde_tous=2 a dû sauvegarder
        # le journal avant même que la requête du négatif ne parte.
        verifie.append(chemin_journal.exists())
        if chemin_journal.exists():
            verifie.append(len(json.loads(chemin_journal.read_text())))
        return httpx.Response(200, json={"text": "Hélas."})

    async with httpx.AsyncClient(transport=httpx.MockTransport(repondre)) as http:
        await filtrer(http, "http://stt", clips, retenus, paralleles=1, sauvegarde_tous=2)
    assert verifie == [True, 2]
