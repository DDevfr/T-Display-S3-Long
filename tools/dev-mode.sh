#!/usr/bin/env bash
# dev-mode.sh — arrête/relance nuc-monitor pour libérer le port série
# Usage :
#   sudo bash tools/dev-mode.sh          # arrêter (mode développement)
#   sudo bash tools/dev-mode.sh resume   # relancer le service

set -e

SERVICE_NAME="nuc-monitor"

if [[ $EUID -ne 0 ]]; then
    echo "Ce script doit être exécuté en root : sudo bash $0 $*"
    exit 1
fi

if [[ "${1:-}" == "resume" ]]; then
    echo "→ Relance de ${SERVICE_NAME}..."
    systemctl start "${SERVICE_NAME}"
    systemctl status "${SERVICE_NAME}" --no-pager --lines=5
    echo ""
    echo "✓ Service relancé — l'écran reprend dans quelques secondes."
else
    echo "→ Arrêt de ${SERVICE_NAME}..."
    systemctl stop "${SERVICE_NAME}"

    # Attendre que le port série soit libéré (max 3 s)
    PORT=$(grep ExecStart /etc/systemd/system/${SERVICE_NAME}.service 2>/dev/null \
           | grep -oP -- '--port \K\S+' || true)
    if [[ -n "$PORT" ]]; then
        for i in 1 2 3; do
            fuser "$PORT" &>/dev/null || break
            sleep 1
        done
    fi

    echo ""
    echo "✓ Service arrêté — port série disponible pour PlatformIO."
    echo ""
    echo "  Flasher le firmware :  pio run -t upload"
    echo "  Moniteur série      :  pio device monitor"
    echo ""
    echo "Pour relancer le service après développement :"
    echo "  sudo bash tools/dev-mode.sh resume"
fi
