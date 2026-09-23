#!/usr/bin/env bash
# Enrichit les extraits (échos de pièce, fonds sonores), puis entraîne le modèle.
# À lancer dans le conteneur atlas-mot-reveil, après preparer.py.
set -euo pipefail
TRAVAIL=${TRAVAIL:-/travail}
CONFIG="$TRAVAIL/entrainement/hey_atlas.yml"
[ -f "$CONFIG" ] || { echo "Configuration absente : lance d'abord preparer.py." >&2; exit 1; }
cd /opt/openWakeWord
python openwakeword/train.py --training_config "$CONFIG" --augment_clips --overwrite
python openwakeword/train.py --training_config "$CONFIG" --train_model
mkdir -p "$TRAVAIL/modele"
cp "$TRAVAIL/entrainement/hey_atlas.onnx" "$TRAVAIL/modele/hey_atlas.onnx"
echo "Modèle prêt : $TRAVAIL/modele/hey_atlas.onnx"
