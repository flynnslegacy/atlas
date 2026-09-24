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
**Arrête ComfyUI** pour toute la durée de la procédure : même inactif, il garde
ses modèles en mémoire vidéo, et `atlas-stt` répond alors « Internal Server
Error ».

## Vue d'ensemble

1. Enregistrer ta voix (Mac)
2. Copier tes enregistrements vers l'Unraid
3. Construire l'image `atlas-mot-reveil`
4. Télécharger les données (~20 Go)
5. Générer les extraits Piper
6. Générer les extraits Qwen
7. Filtrer les extraits
8. Essai à blanc (préparation + entraînement)
9. Vrai entraînement
10. Rapatrier le modèle et l'évaluer
11. Une journée de veille
12. Boucler jusqu'aux critères d'arrêt

Placeholders utilisés partout ci-dessous : `<dossier-travail-unraid>` (le
dossier monté dans le conteneur en `/travail`), `<clone-du-depot>` (un vrai
`git clone` du dépôt Atlas sur l'Unraid, mis à jour par `git pull` ; pas
l'archive téléchargée pour bâtir `atlas-stt` et `atlas-tts`, qui n'est pas un
dépôt git), `<unraid>` (l'adresse de l'Unraid, pour `rsync` depuis le Mac),
`<cache-huggingface-hote>` (le cache Hugging Face de l'hôte, à
réutiliser pour ne pas retélécharger Qwen3-TTS), `<ton-mac>` (l'alias SSH ou
le nom de ta machine) et `<depot-sur-le-mac>` (le dépôt Atlas cloné sur ton
Mac, celui depuis lequel tu lances `enregistrer` et `evaluer`).

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

Copie `donnees/mot_reveil/david/` vers `<dossier-travail-unraid>/david/`, en
gardant l'arborescence (`positifs/`, `atlas_seul/`, `parole/`, `bureau/`).
Depuis ton Mac, crée d'abord le dossier : `rsync` ne crée que le dernier niveau
du chemin.

```bash
ssh root@<unraid> mkdir -p <dossier-travail-unraid>/david
rsync -av donnees/mot_reveil/david/ root@<unraid>:<dossier-travail-unraid>/david/
```

## 3. Construire l'image (Unraid)

Depuis `<clone-du-depot>`, sur l'Unraid. La première fois, clone le dépôt :
`git clone https://github.com/flynnslegacy/atlas.git <clone-du-depot>` ; les
fois suivantes, `git pull`. `GPU` et `TRAVAIL` sont de simples
variables shell, pas des variables d'environnement : elles ne survivent pas
d'un terminal à l'autre. **Chaque nouvelle session de terminal doit donc les
redéfinir** — c'est pourquoi les deux lignes ci-dessous réapparaissent dans
chaque bloc de commande qui les utilise, jusqu'à la fin de ce document ;
copie-colle le bloc en entier plutôt que la seule ligne `docker run`.

```bash
GPU="--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all"
TRAVAIL="-v <dossier-travail-unraid>:/travail"

docker build -f scripts/mot_reveil/Dockerfile -t atlas-mot-reveil .
```

**Les scripts sont figés dans l'image au moment du build** (`COPY scripts/`
dans le `Dockerfile`). Après un `git pull` sur l'Unraid, reconstruis l'image
avant de relancer quoi que ce soit : sinon les conteneurs continuent de
tourner avec l'ancien code, sans avertissement.

## 4. Télécharger les données

Environ 20 Go (traits ACAV100M, jeu de validation, réponses impulsionnelles,
ESC-50, voix Piper). Reprend là où le téléchargement s'était arrêté :

```bash
GPU="--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all"
TRAVAIL="-v <dossier-travail-unraid>:/travail"

docker run --rm -it $TRAVAIL atlas-mot-reveil bash scripts/mot_reveil/telecharger_donnees.sh
```

## 5. Extraits Piper

Trois voix seulement : `siwis`, `tom` et `gilles`, les seules qui disent
« Hey Atlas » juste à l'écoute (24 septembre 2026). `mls` et `mls_1840`
produisent 2 à 9 s de charabia pour deux mots, et `upmc` prononce faux.

D'abord un essai (50 positifs, 50 négatifs). Il s'écrit dans
`clips/piper/essai/`, que le filtre ignore : on l'écoute, il n'entre jamais
dans l'entraînement.

```bash
GPU="--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all"
TRAVAIL="-v <dossier-travail-unraid>:/travail"

docker run --rm -it $TRAVAIL atlas-mot-reveil \
    /opt/piper/bin/python -m scripts.mot_reveil.generer_piper \
    --voix /travail/voix_piper --sortie /travail/clips/piper --essai
```

**Écoute-le sur ton Mac.** Unraid n'a pas Python : rapatrie l'essai dans
`donnees/` (jamais commité), puis `ecouter` annonce chaque voix et joue trois
de ses extraits.

```bash
rsync -av root@<unraid>:<dossier-travail-unraid>/clips/piper/essai/ donnees/mot_reveil/essais/piper/
uv run python -m scripts.mot_reveil.ecouter donnees/mot_reveil/essais/piper --par-voix 3
```

Si une voix sonne faux, ajoute `--exclure <voix>` à la vraie génération
(6 000 positifs, 6 000 négatifs) :

```bash
GPU="--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all"
TRAVAIL="-v <dossier-travail-unraid>:/travail"

docker run --rm -it $TRAVAIL atlas-mot-reveil \
    /opt/piper/bin/python -m scripts.mot_reveil.generer_piper \
    --voix /travail/voix_piper --sortie /travail/clips/piper
```

**Un ancien essai** écrit directement dans `clips/piper/positifs/` ou dans un
autre sous-dossier de `clips/` (avant ce correctif) doit être supprimé avant la
vraie génération : le filtre traite chaque sous-dossier de `clips/` comme une
source, et le générateur saute les noms déjà écrits.

## 6. Extraits Qwen

Qwen est la source principale : une quarantaine de voix conçues (âges, accents,
timbres), qui remplacent les 125 locuteurs de `mls`. Il lit les phrases en
orthographe usuelle (« Hey Atlas ») : « Eille Atlasse », écrit pour le
phonétiseur de Piper, le ferait trébucher.

Le service `atlas-tts` tourne sur le même GPU : on l'arrête pendant toute cette
étape, pour lui laisser la mémoire vidéo. Atlas ne parle plus d'ici là.

D'abord, conçois les voix, puis fais dire « Hey Atlas » une fois à chacune
(l'essai, dans `clips/qwen/essai/`) :

```bash
GPU="--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all"
TRAVAIL="-v <dossier-travail-unraid>:/travail"

docker stop atlas-tts
docker run --rm -it $GPU $TRAVAIL -v <cache-huggingface-hote>:/root/.cache/huggingface \
    -v <clone-du-depot>/scripts:/app/scripts atlas-tts \
    python -m scripts.mot_reveil.generer_qwen concevoir --sortie /travail/clips/qwen
docker run --rm -it $GPU $TRAVAIL -v <cache-huggingface-hote>:/root/.cache/huggingface \
    -v <clone-du-depot>/scripts:/app/scripts atlas-tts \
    python -m scripts.mot_reveil.generer_qwen cloner --sortie /travail/clips/qwen --essai
```

**Écoute l'essai sur ton Mac**, une voix après l'autre, avec sa description :

```bash
rsync -av root@<unraid>:<dossier-travail-unraid>/clips/qwen/essai/ donnees/mot_reveil/essais/qwen/
uv run python -m scripts.mot_reveil.ecouter donnees/mot_reveil/essais/qwen
```

Pour écarter une voix qui dit faux, par exemple `voix_07`, sors sa référence
de `references/` : le clonage n'utilise que les références présentes.

```bash
mkdir -p <dossier-travail-unraid>/clips/qwen/references_ecartees
mv <dossier-travail-unraid>/clips/qwen/references/voix_07.* <dossier-travail-unraid>/clips/qwen/references_ecartees/
```

Puis clone les phrases sur les voix gardées (12 000 positifs, 6 000 négatifs :
compte une nuit), et relance `atlas-tts` :

```bash
GPU="--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all"
TRAVAIL="-v <dossier-travail-unraid>:/travail"

docker run --rm -it $GPU $TRAVAIL -v <cache-huggingface-hote>:/root/.cache/huggingface \
    -v <clone-du-depot>/scripts:/app/scripts atlas-tts \
    python -m scripts.mot_reveil.generer_qwen cloner --sortie /travail/clips/qwen
docker start atlas-tts
```

## 7. Filtrer les extraits

- **Positifs : gardés sur leur durée** (0,4 à 2 s), sans Whisper. Whisper ne sait
  pas juger deux mots isolés : il transcrit « Un atlas » ou « Et à tout à
  l'heure » des extraits justes à l'oreille. La durée écarte le charabia, et ton
  écoute des essais garantit la justesse des voix.
- **Négatifs : passés à Whisper,** qui écarte ceux qui sonnent comme « Hey
  Atlas » (« Et Atlas » compris : les deux se prononcent pareil).

`--network host` est nécessaire : le conteneur appelle le service `atlas-stt`
sur `localhost`.

```bash
GPU="--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all"
TRAVAIL="-v <dossier-travail-unraid>:/travail"

docker run --rm -it --network host $TRAVAIL atlas-mot-reveil \
    /opt/piper/bin/python -m scripts.mot_reveil.filtrer \
    --clips /travail/clips --retenus /travail/retenus --stt http://localhost:9010
```

## 8. Essai à blanc

Vérifie que toute la chaîne tourne avant de lancer plusieurs heures
d'entraînement pour de vrai (300 extraits, 500 pas).
L'enrichissement des extraits tourne sur le processeur : sur une carte RTX 40xx,
la FFT de CUDA 11.7 qu'embarque torch 1.13 plante sur le GPU. L'entraînement,
lui, reste sur le GPU.

```bash
GPU="--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all"
TRAVAIL="-v <dossier-travail-unraid>:/travail"

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

Mêmes commandes, sans `--essai` (toutes les données retenues, 50 000 pas).
**C'est aussi le point où tu reviens à chaque tour de la boucle (étape 12),**
parfois plusieurs jours après et dans un terminal tout neuf : les deux lignes
`GPU`/`TRAVAIL` ci-dessous sont à redéfinir à chaque fois, faute de quoi elles
sont vides et `docker run` perd silencieusement le GPU et/ou le montage
`/travail`.

```bash
GPU="--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all"
TRAVAIL="-v <dossier-travail-unraid>:/travail"

docker run --rm -it $TRAVAIL atlas-mot-reveil python -m scripts.mot_reveil.preparer --travail /travail
docker run --rm -it $GPU --shm-size=32g $TRAVAIL atlas-mot-reveil bash scripts/mot_reveil/entrainer.sh
```

Ça prend plusieurs heures sur le GPU.

## 10. Rapatrier le modèle et l'évaluer

### Sur l'Unraid (ou depuis où `<dossier-travail-unraid>` est visible)

```bash
scp <dossier-travail-unraid>/modele/hey_atlas.onnx <ton-mac>:<depot-sur-le-mac>/models/hey_atlas.onnx  # ou tout autre moyen de copie
```

### Sur le Mac

Depuis la racine du dépôt (les modèles de traits d'openWakeWord ne se
téléchargent qu'une fois) :

```bash
uv run python -c "import openwakeword.utils as u; u.download_models()"
uv run python -m scripts.mot_reveil.evaluer --modele models/hey_atlas.onnx
```

`evaluer` affiche le taux de détection par distance, les réveils sur « Atlas »
seul, et les faux réveils sur ta parole et ton bureau, pour plusieurs seuils.
**Ce seuil conseillé ne repose que sur quelques minutes d'audio mis de côté
pour le test : il a tendance à être bas.** C'est la veille (étape 11), sur une
vraie journée de travail, qui le confirme ou le corrige. Reporte-le d'abord
dans ton `.env` :

```
ATLAS_REVEILLEUR=motcle
ATLAS_REVEIL_SEUIL=<seuil conseillé par evaluer>
```

## 11. Une journée de veille

`uv run` ne charge pas `.env` : sans `--seuil` explicite, la veille mesurerait au
seuil par défaut plutôt qu'à celui retenu à l'étape précédente. Passe-le donc
toujours toi-même :

```bash
uv run python -m scripts.mot_reveil.veiller --modele models/hey_atlas.onnx --seuil <seuil retenu à l'étape 10>
```

Laisse tourner une journée de travail normale. Deux règles pendant la veille :

- **Ne lance jamais `veiller` en même temps que le client Atlas** : les deux
  se disputeraient le micro.
- **Ne dis pas « Hey Atlas » pendant la veille** : tout ce qu'elle garde doit
  être un vrai faux réveil, jamais une détection correcte.

À la fin (Ctrl-C), les alertes sont dans
`donnees/mot_reveil/veille/<horodatage>/`, avec un `journal.json`. Copie
**toutes** les alertes vers `<dossier-travail-unraid>/david/faux_reveils/` —
aussi bien les « FAUX RÉVEIL » que les « presque », en dessous du seuil réel :
ces quasi-détections sont aussi de bons négatifs pour le prochain tour.
Écoute-les d'abord et supprime celles qui contiennent vraiment « Hey Atlas ».
Les noms de fichiers sont préfixés par l'horodatage de la session : plusieurs
journées copiées dans le même dossier ne s'écrasent pas. `preparer.py`
reprendra le tout comme négatifs précieux.

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
