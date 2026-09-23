# Entraînement du mot de réveil « Hey Atlas »

Ce document est la procédure réelle, celle que tu suis vraiment pour entraîner
`hey_atlas.onnx` : ta voix, ton Unraid, tes commandes. Il remplace l'ancien
`scripts/entrainer_mot_reveil.md`, écrit avant que le code existe — ses
commandes ne correspondaient à rien de réel. Claude te guide étape par étape ;
ce fichier sert de référence à relire entre deux étapes.

## Avant de commencer

- **« Atlas » dit seul est un négatif.** Le modèle ne doit réagir qu'à « Hey
  Atlas » (prononcé à la française, « eille atlasse »), jamais au seul mot
  « Atlas », que tu prononceras souvent en parlant du projet.
- **Tes enregistrements ne se commitent jamais.** `donnees/` et `models/` sont
  dans `.gitignore` ; ne force jamais leur ajout (`git add -f`). Il en va de
  même côté Unraid : rien sous `<dossier-travail-unraid>` n'a sa place dans
  Git.
- **Les traits négatifs précalculés (ACAV100M) sont sous licence
  CC-BY-NC-SA-4.0, non commerciale.** Ça convient à ton assistant personnel ;
  un modèle destiné à des clients devrait être réentraîné sans eux.

Le GPU (12 Go) est partagé avec `atlas-stt`, `atlas-tts` et ComfyUI : les
étapes lourdes se passent l'une après l'autre, jamais en même temps — d'où
les `docker stop atlas-tts` / `docker start atlas-tts` autour de l'étape
Qwen.

## Vue d'ensemble

1. Enregistrer ta voix (Mac)
2. Copier tes enregistrements vers l'Unraid
3. Construire l'image `atlas-mot-reveil`
4. Télécharger les données (~20 Go)
5. Générer les extraits Piper
6. Générer les extraits Qwen
7. Filtrer les extraits par Whisper
8. Essai à blanc (préparation + entraînement)
9. Vrai entraînement
10. Rapatrier le modèle sur le Mac et l'évaluer
11. Une journée de veille
12. Boucler jusqu'aux critères d'arrêt

Placeholders utilisés partout ci-dessous : `<dossier-travail-unraid>` (le
dossier monté dans le conteneur en `/travail`), `<clone-du-depot>` (le dépôt
Atlas cloné sur l'Unraid, celui qui sert déjà à bâtir `atlas-stt` et
`atlas-tts`), `<cache-huggingface-hote>` (le cache Hugging Face de l'hôte, à
réutiliser pour ne pas retélécharger Qwen3-TTS) et `<ton-mac>` (l'alias SSH ou
le nom de ta machine).

---

## 1. Enregistrer ta voix (Mac, environ 30 minutes)

Depuis la racine du dépôt, sur ton Mac :

```bash
uv run python -m scripts.mot_reveil.enregistrer
```

C'est une séance guidée : chaque prise affiche sa consigne, tu appuies sur
Entrée puis tu parles. Elle reprend là où elle s'était arrêtée — une prise
déjà enregistrée n'est pas refaite. Le résultat va dans
`donnees/mot_reveil/david/` (positifs, « Atlas » seul, parole, bruits de
bureau).

## 2. Copier vers l'Unraid

Copie `donnees/mot_reveil/david/` (scp, rsync, ou le partage réseau de
l'Unraid — comme tu préfères) vers `<dossier-travail-unraid>/david/`, en
gardant l'arborescence (`positifs/`, `atlas_seul/`, `parole/`, `bureau/`).

## 3. Construire l'image (Unraid)

Depuis `<clone-du-depot>`, sur l'Unraid. Ces deux variables sont réutilisées
par toutes les commandes du conteneur ci-dessous :

```bash
GPU="--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all"
TRAVAIL="-v <dossier-travail-unraid>:/travail"

docker build -f scripts/mot_reveil/Dockerfile -t atlas-mot-reveil .
```

## 4. Télécharger les données

Environ 20 Go (traits ACAV100M, jeu de validation, réponses impulsionnelles,
ESC-50, voix Piper). Reprend là où le téléchargement s'était arrêté :

```bash
docker run --rm -it $TRAVAIL atlas-mot-reveil bash scripts/mot_reveil/telecharger_donnees.sh
```

## 5. Extraits Piper

D'abord un essai (50 positifs, 50 négatifs) :

```bash
docker run --rm -it $TRAVAIL atlas-mot-reveil \
    /opt/piper/bin/python -m scripts.mot_reveil.generer_piper \
    --voix /travail/voix_piper --sortie /travail/clips/piper --essai
```

**Écoute** quelques extraits de la voix `mls`, dans
`<dossier-travail-unraid>/clips/piper/positifs/` (fichiers `piper_pos_*.wav`).
Si elle déçoit, la vraie génération l'exclut :

```bash
# Voix mls convaincante :
docker run --rm -it $TRAVAIL atlas-mot-reveil \
    /opt/piper/bin/python -m scripts.mot_reveil.generer_piper \
    --voix /travail/voix_piper --sortie /travail/clips/piper

# Voix mls décevante :
docker run --rm -it $TRAVAIL atlas-mot-reveil \
    /opt/piper/bin/python -m scripts.mot_reveil.generer_piper \
    --voix /travail/voix_piper --sortie /travail/clips/piper --exclure fr_FR-mls-medium
```

(La commande sans `--essai` régénère par-dessus l'essai : les fichiers déjà
écrits ne sont pas refaits, seuls les 30 000 positifs et 20 000 négatifs
manquants s'ajoutent.)

## 6. Extraits Qwen

Le service `atlas-tts` tourne sur le même GPU : on l'arrête le temps de cette
étape, pour lui laisser la mémoire vidéo.

```bash
docker stop atlas-tts
docker run --rm -it $GPU $TRAVAIL -v <cache-huggingface-hote>:/root/.cache/huggingface \
    -v <clone-du-depot>/scripts:/app/scripts atlas-tts \
    python -m scripts.mot_reveil.generer_qwen concevoir --sortie /travail/clips/qwen
```

**Écoute** les 15 voix conçues, dans
`<dossier-travail-unraid>/clips/qwen/references/voix_00.wav` à `voix_14.wav`.
Puis clone les phrases sur ces voix, et relance `atlas-tts` :

```bash
docker run --rm -it $GPU $TRAVAIL -v <cache-huggingface-hote>:/root/.cache/huggingface \
    -v <clone-du-depot>/scripts:/app/scripts atlas-tts \
    python -m scripts.mot_reveil.generer_qwen cloner --sortie /travail/clips/qwen
docker start atlas-tts
```

## 7. Filtrer les extraits par Whisper

Garde uniquement les extraits où Whisper entend ce qu'il faut. `--network
host` est nécessaire : le conteneur appelle le service `atlas-stt` sur
`localhost`.

```bash
docker run --rm -it --network host $TRAVAIL atlas-mot-reveil \
    /opt/piper/bin/python -m scripts.mot_reveil.filtrer \
    --clips /travail/clips --retenus /travail/retenus --stt http://localhost:9010
```

## 8. Essai à blanc

Vérifie que toute la chaîne tourne avant de lancer plusieurs heures
d'entraînement pour de vrai (300 extraits, 500 pas) :

```bash
docker run --rm -it $TRAVAIL atlas-mot-reveil python -m scripts.mot_reveil.preparer --travail /travail --essai
docker run --rm -it $GPU --shm-size=32g $TRAVAIL atlas-mot-reveil bash scripts/mot_reveil/entrainer.sh
```

Rapatrie le modèle sur le Mac (voir étape 10) et vérifie seulement qu'`evaluer`
le charge **sans erreur** :

```bash
uv run python -m scripts.mot_reveil.evaluer --modele models/hey_atlas.onnx
```

Les chiffres de cet essai n'ont aucun sens (trop peu d'extraits, trop peu de
pas) : seule l'absence d'erreur compte ici.

## 9. Vrai entraînement

Mêmes commandes, sans `--essai` (toutes les données retenues, 50 000 pas) :

```bash
docker run --rm -it $TRAVAIL atlas-mot-reveil python -m scripts.mot_reveil.preparer --travail /travail
docker run --rm -it $GPU --shm-size=32g $TRAVAIL atlas-mot-reveil bash scripts/mot_reveil/entrainer.sh
```

Ça prend plusieurs heures sur le GPU.

## 10. Rapatrier le modèle et l'évaluer (Mac)

Depuis là où `<dossier-travail-unraid>` est accessible (l'Unraid lui-même, ou
tout autre moyen de copie) :

```bash
scp <dossier-travail-unraid>/modele/hey_atlas.onnx <ton-mac>:models/hey_atlas.onnx  # ou tout autre moyen de copie
```

Puis, depuis la racine du dépôt sur ton Mac (les modèles de traits
d'openWakeWord ne se téléchargent qu'une fois) :

```bash
uv run python -c "import openwakeword.utils as u; u.download_models()"
uv run python -m scripts.mot_reveil.evaluer --modele models/hey_atlas.onnx
```

`evaluer` affiche le taux de détection par distance, les réveils sur « Atlas »
seul, et les faux réveils sur ta parole et ton bureau, pour plusieurs seuils.
Reporte le seuil conseillé dans ton `.env` :

```
ATLAS_REVEILLEUR=motcle
ATLAS_REVEIL_SEUIL=<seuil conseillé par evaluer>
```

## 11. Une journée de veille

```bash
uv run python -m scripts.mot_reveil.veiller --modele models/hey_atlas.onnx
```

Laisse tourner une journée de travail normale. Deux règles pendant la veille :

- **Ne lance jamais `veiller` en même temps que le client Atlas** : les deux
  se disputeraient le micro.
- **Ne dis pas « Hey Atlas » pendant la veille** : tout ce qu'elle garde doit
  être un vrai faux réveil, jamais une détection correcte.

À la fin (Ctrl-C), les alertes sont dans
`donnees/mot_reveil/veille/<horodatage>/`, avec un `journal.json`. Copie
celles marquées **FAUX RÉVEIL** dans le journal (pas les « presque », en
dessous du seuil réel) vers `<dossier-travail-unraid>/david/faux_reveils/` :
`preparer.py` les reprendra comme négatifs précieux au prochain tour.

## 12. Boucler, puis s'arrêter

Reprends à l'étape 9 (`preparer` puis `entrainer.sh`) avec les nouveaux faux
réveils, jusqu'à tenir les trois critères de la spec, mesurés par `evaluer` :

- au moins 90 % des « Hey Atlas » de David détectés (jamais vus à
  l'entraînement), avec le détail par distance ;
- zéro réveil sur « Atlas » dit seul ;
- au plus un faux réveil par journée de travail (mesuré par `veiller`).

**Repli :** si la détection reste sous 85–90 % après deux ou trois tours, on
abandonne openWakeWord pour microWakeWord (runtime `pymicro-wakeword`, qui a
un paquet macOS), avec les mêmes extraits. Il faudra alors un nouveau
`Predicteur` dans le client — hors du périmètre de cette procédure.
