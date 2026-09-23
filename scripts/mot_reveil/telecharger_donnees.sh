#!/usr/bin/env bash
# Télécharge une fois tout ce dont l'entraînement a besoin. Reprend là où il s'était arrêté.
# À lancer dans le conteneur atlas-mot-reveil, /travail monté.
set -euo pipefail
TRAVAIL=${TRAVAIL:-/travail}
D="$TRAVAIL/donnees"
V="$TRAVAIL/voix_piper"
HF=https://huggingface.co
mkdir -p "$D/rir" "$D/fonds/esc50" "$V"

recuperer() {  # recuperer <url> <fichier>
    [ -s "$2" ] && return 0
    curl -L --fail -C - -o "$2.partiel" "$1"
    mv "$2.partiel" "$2"
}

# Traits négatifs précalculés (17,3 Go, CC-BY-NC-SA-4.0) et jeu de validation (185 Mo).
recuperer "$HF/datasets/davidscripka/openwakeword_features/resolve/main/openwakeword_features_ACAV100M_2000_hrs_16bit.npy" \
    "$D/openwakeword_features_ACAV100M_2000_hrs_16bit.npy"
recuperer "$HF/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy" \
    "$D/validation_set_features.npy"

# Réponses impulsionnelles de pièces (MIT, déjà en 16 kHz).
if [ -z "$(ls -A "$D/rir")" ]; then
    python - "$D/rir_brut" <<'EOF'
import sys
from huggingface_hub import snapshot_download
snapshot_download("davidscripka/MIT_environmental_impulse_responses", repo_type="dataset",
                  allow_patterns=["16khz/*"], local_dir=sys.argv[1])
EOF
    cp "$D"/rir_brut/16khz/*.wav "$D/rir/"
fi

# Fond générique : ESC-50, 2 000 sons d'environnement (licence non commerciale).
if [ ! -f "$D/fonds/esc50/.fait" ]; then
    recuperer https://github.com/karolpiczak/ESC-50/archive/refs/heads/master.zip "$D/esc50.zip"
    unzip -q -o "$D/esc50.zip" 'ESC-50-master/audio/*' -d "$D"
    (cd /app && python -m scripts.mot_reveil.convertir "$D/ESC-50-master/audio" "$D/fonds/esc50")
    touch "$D/fonds/esc50/.fait"
fi

# Voix Piper françaises.
for voix in fr_FR-mls-medium fr_FR-siwis-medium fr_FR-upmc-medium fr_FR-gilles-low \
            fr_FR-tom-medium fr_FR-mls_1840-low; do
    IFS=- read -r langue jeu qualite <<< "$voix"
    base="$HF/rhasspy/piper-voices/resolve/main/fr/$langue/$jeu/$qualite/$voix"
    recuperer "$base.onnx" "$V/$voix.onnx"
    recuperer "$base.onnx.json" "$V/$voix.onnx.json"
done
echo "Données prêtes dans $D et $V."
