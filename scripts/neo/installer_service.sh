#!/usr/bin/env bash
# Installe (ou réinstalle) le service launchd qui lance le Core d'Atlas au démarrage du
# néo et le relance s'il tombe. À lancer depuis le dépôt cloné sur le néo, en tant que
# l'utilisateur qui fera tourner Atlas (pas en root) : le script demande lui-même sudo
# pour écrire dans /Library/LaunchDaemons.
#
#   ./scripts/neo/installer_service.sh            installe le service
#   ./scripts/neo/installer_service.sh --apercu   affiche le service, sans rien installer
set -euo pipefail

ETIQUETTE="fr.atlas.core"
DOSSIER="$(cd "$(dirname "$0")/../.." && pwd)"
MODELE="$DOSSIER/scripts/neo/$ETIQUETTE.plist"
CIBLE="/Library/LaunchDaemons/$ETIQUETTE.plist"
UTILISATEUR="$(id -un)"

generer() {
    sed -e "s|__DOSSIER__|$DOSSIER|g" \
        -e "s|__MAISON__|$HOME|g" \
        -e "s|__UTILISATEUR__|$UTILISATEUR|g" \
        "$MODELE"
}

if [[ "${1:-}" == "--apercu" ]]; then
    generer
    exit 0
fi
if [[ "$UTILISATEUR" == "root" ]]; then
    echo "Lance ce script sans sudo : il le demandera lui-même." >&2
    exit 1
fi
if [[ ! -f "$DOSSIER/.env" ]]; then
    echo "Il manque $DOSSIER/.env : écris-le d'abord (étape 4 du LISEZMOI)." >&2
    exit 1
fi
for nom in ATLAS_WEB_CLE ATLAS_AUDIO_CLE CLAUDE_CODE_OAUTH_TOKEN; do
    if ! grep -Eq "^${nom}=.+" "$DOSSIER/.env"; then
        echo "Il manque $nom dans $DOSSIER/.env (étapes 3 et 4 du LISEZMOI)." >&2
        exit 1
    fi
done

mkdir -p "$DOSSIER/donnees/logs"
TEMPORAIRE="$(mktemp)"
trap 'rm -f "$TEMPORAIRE"' EXIT
generer >"$TEMPORAIRE"
plutil -lint "$TEMPORAIRE" >/dev/null

sudo launchctl bootout "system/$ETIQUETTE" 2>/dev/null || true
sudo install -m 644 -o root -g wheel "$TEMPORAIRE" "$CIBLE"
sudo launchctl bootstrap system "$CIBLE"
echo "Service $ETIQUETTE installé : le Core tourne, et redémarrera avec le néo."
echo "Son journal : tail -f $DOSSIER/donnees/logs/core.log"