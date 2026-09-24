#!/usr/bin/env bash
# Enrichit les extraits (échos de pièce, fonds sonores), puis entraîne le modèle.
# À lancer dans le conteneur atlas-mot-reveil, après preparer.py.
set -euo pipefail
TRAVAIL=${TRAVAIL:-/travail}
CONFIG="$TRAVAIL/entrainement/hey_atlas.yml"
[ -f "$CONFIG" ] || { echo "Configuration absente : lance d'abord preparer.py." >&2; exit 1; }
cd /opt/openWakeWord
# L'enrichissement (décalage de hauteur par FFT) plante sur les cartes Ada (RTX 40xx) avec le
# cuFFT de CUDA 11.7 qu'embarque torch 1.13.1 : il tourne sur le processeur, GPU masqué.
# L'entraînement, sans FFT, reste sur le GPU.
CUDA_VISIBLE_DEVICES= python openwakeword/train.py --training_config "$CONFIG" --augment_clips --overwrite
python openwakeword/train.py --training_config "$CONFIG" --train_model
mkdir -p "$TRAVAIL/modele"
cp "$TRAVAIL/entrainement/hey_atlas.onnx" "$TRAVAIL/modele/hey_atlas.onnx"
echo "Modèle prêt : $TRAVAIL/modele/hey_atlas.onnx"
