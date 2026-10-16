#!/usr/bin/env bash
# deploy.sh — arrête le service, flash l'ESP32 (optionnel), redéploie et redémarre
#
# Usage :
#   bash tools/deploy.sh             # firmware + service (cas normal)
#   bash tools/deploy.sh --no-flash  # service seulement (modif Python uniquement)

set -e

SERVICE_NAME="nuc-monitor"
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
SERVICE_SRC="${SCRIPT_DIR}/${SERVICE_NAME}.service"
SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}.service"
PIO="${HOME}/.platformio/penv/bin/pio"

if [[ $EUID -eq 0 ]]; then
    echo "Lancer ce script sans sudo (il le demande lui-même) : bash $0"
    exit 1
fi

# Fichier service rendu pour l'utilisateur courant et l'emplacement du clone
SERVICE_RENDERED="$(mktemp)"
trap 'rm -f "${SERVICE_RENDERED}"' EXIT
sed -e "s|@USER@|$(id -un)|g" -e "s|@GROUP@|$(id -gn)|g" \
    -e "s|@PROJECT_DIR@|${PROJECT_ROOT}|g" "${SERVICE_SRC}" > "${SERVICE_RENDERED}"

FLASH=true
if [[ "${1:-}" == "--no-flash" ]]; then
    FLASH=false
fi

# ── 1. Arrêt du service ───────────────────────────────────────────────────────
echo "▶ Arrêt de ${SERVICE_NAME}..."
sudo systemctl stop "${SERVICE_NAME}" 2>/dev/null || true   # absent au premier déploiement

# Attendre que le port série soit libéré (max 3 s)
for i in 1 2 3; do
    fuser /dev/ttyACM* &>/dev/null 2>&1 || break
    sleep 1
done

# ── 2. Flash ESP32 ────────────────────────────────────────────────────────────
if $FLASH; then
    echo "▶ Compilation et flash ESP32..."
    cd "${PROJECT_ROOT}"
    "${PIO}" run -e sys_monitor -t upload
    echo "  (L'ESP32 reboot automatiquement)"
else
    echo "▶ Flash ignoré (--no-flash)"
fi

# ── 3. Mise à jour du fichier service si modifié ─────────────────────────────
if [[ -f "${SERVICE_DEST}" ]]; then
    if ! diff -q "${SERVICE_RENDERED}" "${SERVICE_DEST}" &>/dev/null; then
        echo "▶ Fichier service modifié → mise à jour systemd..."
        sudo cp "${SERVICE_RENDERED}" "${SERVICE_DEST}"
        sudo chmod 644 "${SERVICE_DEST}"
        sudo systemctl daemon-reload
    fi
else
    echo "▶ Service non encore installé → installation..."
    sudo cp "${SERVICE_RENDERED}" "${SERVICE_DEST}"
    sudo chmod 644 "${SERVICE_DEST}"
    sudo systemctl daemon-reload
    sudo systemctl enable "${SERVICE_NAME}"
fi

# ── 4. Redémarrage du service ─────────────────────────────────────────────────
echo "▶ Démarrage de ${SERVICE_NAME}..."
sudo systemctl start "${SERVICE_NAME}"

echo ""
echo "✓ Déploiement terminé."
echo ""
sudo systemctl status "${SERVICE_NAME}" --no-pager --lines=6
