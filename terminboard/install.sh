#!/bin/bash
# Terminboard – Add-on-Installer
# Ziel: Raspberry Pi OS Desktop (Trixie), läuft PARALLEL zu LHTPi auf dem
#       zweiten HDMI-Ausgang (HDMI-1).
# VORAUSSETZUNG: LHTPi install.sh wurde bereits ausgeführt
#                (X11/Openbox/LightDM/NetworkManager-AP vorhanden).
# Nutzung auf dem Pi:
#   cd /home/pi/lhtpi/terminboard
#   sudo bash install.sh
set -Eeuo pipefail

PROJECT_NAME="Terminboard"
PROJECT_DIR="/home/pi/lhtpi/terminboard"
PI_USER="pi"
PI_GROUP="pi"
APP_PORT="8001"
KIOSK_URL="http://localhost:8001/board/kiosk"
SERVICE_APP="terminboard.service"
SERVICE_KIOSK="terminboard-kiosk.service"
KIOSK_SCRIPT="/home/pi/start_terminboard_kiosk.sh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()  { echo -e "\n==> $*"; }
ok()   { echo "  ✅ $*"; }
warn() { echo "  ⚠️  $*"; }
fail() { echo -e "\n  ❌ $*" >&2; exit 1; }

require_root() {
    if [ "${EUID}" -ne 0 ]; then
        fail "Bitte als root ausführen: sudo bash install.sh"
    fi
}

install_packages() {
    log "Installiere benötigte Systempakete (falls fehlend)"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv exfatprogs ntfs-3g dosfstools usbutils
    ok "Systempakete vorhanden"
}

prepare_project() {
    log "Richte Projekt unter ${PROJECT_DIR} ein"
    mkdir -p "${PROJECT_DIR}"
    if [ "${SCRIPT_DIR}" != "${PROJECT_DIR}" ]; then
        for f in "${SCRIPT_DIR}"/*; do
            [ -f "$f" ] && cp "$f" "${PROJECT_DIR}/" 2>/dev/null || true
        done
        for d in templates static tests; do
            [ -d "${SCRIPT_DIR}/${d}" ] && cp -r "${SCRIPT_DIR}/${d}" "${PROJECT_DIR}/" 2>/dev/null || true
        done
    fi
    if [ ! -f "${PROJECT_DIR}/requirements.txt" ]; then
        fail "${PROJECT_DIR}/requirements.txt fehlt. Bitte Repository korrekt klonen."
    fi
    chown -R "${PI_USER}:${PI_GROUP}" "${PROJECT_DIR}"
    ok "Projektverzeichnis bereit"
}

setup_python() {
    log "Erstelle Python-Virtualenv"
    cd "${PROJECT_DIR}"
    sudo -u "${PI_USER}" python3 -m venv venv
    sudo -u "${PI_USER}" "${PROJECT_DIR}/venv/bin/python" -m pip install --upgrade pip -q
    sudo -u "${PI_USER}" "${PROJECT_DIR}/venv/bin/pip" install -r requirements.txt -q
    chown -R "${PI_USER}:${PI_GROUP}" "${PROJECT_DIR}"
    ok "Python-Umgebung fertig"
}

configure_app_service() {
    log "Erstelle systemd-Service für die Terminboard-App"
    local secret
    secret="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 48 || true)"
    [ -n "${secret}" ] || secret="terminboard-change-me-$(date +%s)"

    cat > "/etc/systemd/system/${SERVICE_APP}" <<EOF
[Unit]
Description=Terminboard - Flask Web-App
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${PI_USER}
Group=${PI_GROUP}
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=TERMINBOARD_HOST=0.0.0.0
Environment=TERMINBOARD_PORT=${APP_PORT}
Environment=TERMINBOARD_SECRET=${secret}
ExecStart=${PROJECT_DIR}/venv/bin/python ${PROJECT_DIR}/app.py
Restart=always
RestartSec=5
StartLimitIntervalSec=120
StartLimitBurst=5

[Install]
WantedBy=multi-user.target
EOF
    ok "App-Service erstellt"
}

configure_kiosk() {
    log "Erstelle Kiosk-Startskript ${KIOSK_SCRIPT}"
    cat > "${KIOSK_SCRIPT}" <<'EOF'
#!/bin/bash
set -u
LOG="/home/pi/terminboard-kiosk.log"
APP_URL="http://localhost:8001/board/kiosk"
READY_URL="http://localhost:8001/login"
# Position des zweiten Monitors (X-Offset = Breite des ersten Monitors).
SCREEN2_X="1920"
SCREEN2_Y="0"
SCREEN2_W="1920"
SCREEN2_H="1080"
# Eigenes Chromium-Profil (NICHT mit LHTPi teilen!)
PROFILE="/home/pi/.config/chromium-terminboard"

mkdir -p "$(dirname "$LOG")"
touch "$LOG"
echo "$(date '+%F %T') - Terminboard-Kiosk gestartet, warte auf Flask-App" >> "$LOG"

ready=0
for i in $(seq 1 30); do
    if curl -fsS --connect-timeout 2 --max-time 5 "$READY_URL" >/dev/null 2>&1; then
        ready=1
        echo "$(date '+%F %T') - Flask-App erreichbar, starte Chromium" >> "$LOG"
        break
    fi
    sleep 2
done
[ "$ready" -ne 1 ] && echo "$(date '+%F %T') - App nicht erreichbar, starte Chromium trotzdem" >> "$LOG"

xset s off >/dev/null 2>&1 || true
xset -dpms >/dev/null 2>&1 || true
xset s noblank >/dev/null 2>&1 || true

mkdir -p "$PROFILE"
CHROMIUM="/usr/bin/chromium-browser"
[ -x "$CHROMIUM" ] || CHROMIUM="/usr/bin/chromium"

exec "$CHROMIUM" \
    --kiosk \
    --app="$APP_URL" \
    --user-data-dir="$PROFILE" \
    --window-position="${SCREEN2_X},${SCREEN2_Y}" \
    --window-size="${SCREEN2_W},${SCREEN2_H}" \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-features=Translate,TranslateUI \
    --no-first-run \
    --check-for-update-interval=31536000 \
    --autoplay-policy=no-user-gesture-required \
    --disable-popup-blocking \
    --disable-translate \
    --disable-context-menu \
    --password-store=basic \
    --lang=de \
    --disable-gpu \
    --disable-gpu-compositing >> "$LOG" 2>&1
EOF
    chmod +x "${KIOSK_SCRIPT}"
    chown "${PI_USER}:${PI_GROUP}" "${KIOSK_SCRIPT}"

    log "Erstelle systemd-Service für den zweiten HDMI-Kiosk"
    cat > "/etc/systemd/system/${SERVICE_KIOSK}" <<EOF
[Unit]
Description=Terminboard - HDMI Chromium Kiosk (zweiter Monitor)
After=graphical.target ${SERVICE_APP}
Requires=${SERVICE_APP}

[Service]
Type=simple
User=${PI_USER}
Group=${PI_GROUP}
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/${PI_USER}/.Xauthority
ExecStartPre=/bin/sleep 5
ExecStart=${KIOSK_SCRIPT}
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=120
StartLimitBurst=3

[Install]
WantedBy=graphical.target
EOF
    ok "Kiosk-Service erstellt"
}

configure_usb_automount() {
    log "Richte USB-Auto-Mount für termine.csv ein (Mount /mnt/terminboard-usb)"
    mkdir -p /mnt/terminboard-usb
    cat > /usr/local/bin/terminboard-usb-mount.sh <<'EOF'
#!/bin/bash
# Terminboard: USB-Stick nach /mnt/terminboard-usb mounten (read-only, weltlesbar).
set -u
dev="${1:-}"
[ -n "$dev" ] || exit 0
mkdir -p /mnt/terminboard-usb
if mountpoint -q /mnt/terminboard-usb; then
    umount -l /mnt/terminboard-usb 2>/dev/null || true
fi
if mount "$dev" /mnt/terminboard-usb -o ro,umask=022 2>/dev/null \
    || mount "$dev" /mnt/terminboard-usb -o ro,umask=022 -t vfat 2>/dev/null \
    || mount "$dev" /mnt/terminboard-usb -o ro,umask=022 -t exfat 2>/dev/null; then
    :
else
    logger -t terminboard-usb "Mount von $dev nach /mnt/terminboard-usb fehlgeschlagen"
fi
exit 0
EOF
    chmod +x /usr/local/bin/terminboard-usb-mount.sh

    cat > /etc/udev/rules.d/99-terminboard-usb.rules <<'EOF'
ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_USAGE}=="filesystem", ENV{ID_BUS}=="usb", RUN+="/usr/bin/systemd-run --no-block --on-active=2 /usr/local/bin/terminboard-usb-mount.sh $env{DEVNAME}"
ACTION=="remove", SUBSYSTEM=="block", ENV{ID_FS_USAGE}=="filesystem", ENV{ID_BUS}=="usb", RUN+="/usr/bin/systemd-run --no-block /bin/umount -l /mnt/terminboard-usb"
EOF
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger --subsystem-match=block 2>/dev/null || true
    ok "USB-Auto-Mount eingerichtet"
}

configure_firewall() {
    log "Gib Firewall-Port ${APP_PORT}/tcp frei (falls UFW aktiv)"
    if command -v ufw >/dev/null 2>&1; then
        ufw allow "${APP_PORT}/tcp" 2>/dev/null || warn "UFW-Regel konnte nicht gesetzt werden"
        ok "Port ${APP_PORT}/tcp freigegeben"
    else
        warn "ufw nicht vorhanden – überspringe Firewall"
    fi
}

enable_services() {
    systemctl daemon-reload
    systemctl enable "${SERVICE_APP}" "${SERVICE_KIOSK}"
    systemctl restart "${SERVICE_APP}" 2>/dev/null || warn "App-Service konnte nicht gestartet werden"
    ok "Services aktiviert"
}

print_summary() {
    echo ""
    echo "=================================================="
    echo "  ✅ ${PROJECT_NAME} Installation abgeschlossen!"
    echo "=================================================="
    echo "  🌐 Dashboard: http://<LAN-IP>:${APP_PORT}  (admin / admin)"
    echo "  📺 HDMI-1:    Chromium-Kiosk mit ${KIOSK_URL}"
    echo "  💾 USB-Stick: termine.csv im Stick-Root → wird automatisch angezeigt"
    echo "  ⚠️  Dual-Screen: Positionierung auf HDMI-1 muss auf echter Hardware"
    echo "     verifiziert werden (SCREEN2_X im ${KIOSK_SCRIPT} anpassen)."
    echo ""
}

main() {
    require_root
    install_packages
    prepare_project
    setup_python
    configure_app_service
    configure_kiosk
    configure_usb_automount
    configure_firewall
    enable_services
    print_summary
}

main "$@"
