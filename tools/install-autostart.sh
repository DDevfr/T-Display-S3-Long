#!/usr/bin/env bash
# install-autostart.sh — installe nuc-monitor comme service systemd
# Usage : sudo bash tools/install-autostart.sh

set -e

SERVICE_NAME="nuc-monitor"
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
SERVICE_FILE="${SCRIPT_DIR}/${SERVICE_NAME}.service"
DEST="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ $EUID -ne 0 ]]; then
    echo "Ce script doit être exécuté en root : sudo bash $0"
    exit 1
fi

# Le service tourne sous l'utilisateur qui a lancé sudo, jamais en root
SVC_USER="${SUDO_USER:-}"
if [[ -z "$SVC_USER" || "$SVC_USER" == "root" ]]; then
    echo "Lancer ce script avec sudo depuis votre compte utilisateur (pas depuis root)."
    exit 1
fi
SVC_GROUP="$(id -gn "$SVC_USER")"

echo "→ Installation du service pour ${SVC_USER} (${PROJECT_ROOT}) vers ${DEST}"
sed -e "s|@USER@|${SVC_USER}|g" -e "s|@GROUP@|${SVC_GROUP}|g" \
    -e "s|@PROJECT_DIR@|${PROJECT_ROOT}|g" "$SERVICE_FILE" > "$DEST"
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
