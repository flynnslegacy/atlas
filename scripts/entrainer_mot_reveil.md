# Entraînement du modèle « Hey Helios »

## Point critique — Français obligatoire

**« Hey Helios » se prononce en FRANÇAIS.** Le générateur d'échantillons d'openWakeWord utilise une
voix anglaise par défaut. Un modèle entraîné sur une prononciation anglaise ne réagira **jamais** 
à la prononciation française « eille élios ». 

**Les échantillons positifs doivent être synthétisés avec plusieurs voix Piper FRANÇAISES.**

---

## Procédure

Cette procédure s'exécute sur **l'Unraid**, pour bénéficier du GPU et de la capacité mémoire.

### 1. Installer les outils

```bash
# Cloner openWakeWord
git clone https://github.com/dscripka/openWakeWord
cd openWakeWord
pip install -e '.[full]'

# Cloner le générateur d'échantillons Piper
cd ..
git clone https://github.com/rhasspy/piper-sample-generator
```

### 2. Préparer les voix Piper françaises

Télécharger plusieurs voix Piper français (fr_FR) depuis 
[rhasspy/piper-voices](https://github.com/rhasspy/piper-voices/releases):

- `fr_FR-siwis-medium.onnx`
- `fr_FR-upmc-medium.onnx`  
- `fr_FR-gilles-low.onnx`
- `fr_FR-mls-medium.onnx`

Placer les fichiers `.onnx` et `.json` dans un répertoire `piper_voices/`.

### 3. Générer les échantillons positifs

Créer un fichier `positive_examples.txt` contenant plusieurs variations du texte:

```
Hey Helios
Hey helios
hey Helios
hey helios
Hey Helios
```

Générer ~30 000 échantillons positifs avec variation de vitesse, hauteur et réverbération:

```bash
python piper-sample-generator/audio_sample_generator.py \
  --text "$(cat positive_examples.txt)" \
  --output_directory ./positive_samples \
  --voice_dir ./piper_voices \
  --num_samples 30000 \
  --speed_range 0.8 1.2 \
  --pitch_range -5 5 \
  --noise_factor 0.01
```

### 4. Préparer les échantillons négatifs

Combiner plusieurs sources:

- **AudioSet**: extraits d'environnement sans parole
- **FMA (Free Music Archive)**: musique variée
- **Parole naturelle**: enregistrements de David qui parle normalement **sans dire le mot**
  (ce dernier point est crucial — des faux négatifs rendront le modèle hyper-sensible)

Placer tous les négatifs dans `negative_samples/`.

### 5. Entraîner le modèle

```bash
cd openWakeWord

python -m openwakeword.train \
  --positive_dir ../positive_samples \
  --negative_dir ../negative_samples \
  --output_model ./hey_helios \
  --epochs 50 \
  --batch_size 32
```

### 6. Exporter en ONNX

```bash
python -m openwakeword.export \
  --model_path ./hey_helios \
  --output_path ./hey_helios.onnx \
  --format onnx
```

### 7. Rapatrier le modèle

Copier le fichier vers le dépôt Helios:

```bash
scp hey_helios.onnx david@[adresse_locale]:/Users/david/claude-code/Helios/models/hey_helios.onnx
```

---

## Vérification

Une fois le modèle en place, le client audio est prêt à utiliser le wake word:

```bash
cd /Users/david/claude-code/Helios
HELIOS_REVEILLEUR=motcle make run-audio
```

Le réglage fin du seuil se fait au banc de mesure (tâche 14), pas à l'oreille.

**Important**: pendant les tests, parler naturellement pendant dix minutes **sans jamais dire le mot**, 
et compter les faux réveils. Un seuil mal réglé trahira rapidement.
