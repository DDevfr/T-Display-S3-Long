#!/usr/bin/env bash
# install-autostart.sh — installe nuc-monitor comme service systemd
# Usage : sudo bash tools/install-autostart.sh

set -e

SERVICE_NAME="nuc-monitor"
SERVICE_FILE="$(dirname "$(realpath "$0")")/${SERVICE_NAME}.service"
DEST="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ $EUID -ne 0 ]]; then
    echo "Ce script doit être exécuté en root : sudo bash $0"
    exit 1
fi

echo "→ Copie du fichier service vers ${DEST}"
cp "$SERVICE_FILE" "$DEST"
chmod 644 "$DEST"

echo "→ Rechargement de systemd"
systemctl daemon-reload

echo "→ Activation du service au démarrage"
systemctl enable "${SERVICE_NAME}"

echo "→ Démarrage immédiat du service"
systemctl start "${SERVICE_NAME}"

echo ""
echo "✓ Service installé et démarré."
echo ""
echo "Commandes utiles :"
echo "  sudo systemctl status ${SERVICE_NAME}    # état"
echo "  sudo systemctl stop   ${SERVICE_NAME}    # arrêter"
echo "  sudo systemctl start  ${SERVICE_NAME}    # démarrer"
echo "  sudo systemctl disable ${SERVICE_NAME}   # désactiver l'autostart"
echo "  sudo journalctl -u ${SERVICE_NAME} -f    # logs en direct"
