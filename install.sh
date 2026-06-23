#!/bin/bash
# LHTPi Installationsskript
# Ziel: Raspberry Pi OS Desktop (Trixie) mit LAN-DHCP, NetworkManager-AP und HDMI-Kiosk.
# Nutzung auf dem Pi:
#   cd /home/pi/lhtpi
#   sudo bash install.sh

set -Eeuo pipefail

PROJECT_NAME="LHTPi"
PROJECT_DIR="/home/pi/lhtpi"
PI_USER="pi"
PI_GROUP="pi"
APP_PORT="8000"
AP_SSID="LHTPi"
AP_PASS="LHTPi123"
AP_ADDR="192.168.4.1/24"
KIOSK_URL="http://localhost:8000/present/kiosk"
SERVICE_APP="lhtpi.service"
SERVICE_KIOSK="lhtpi-kiosk.service"
KIOSK_SCRIPT="/home/pi/start_lhtpi_kiosk.sh"
KIOSK_LOG="/home/pi/lhtpi-kiosk.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="/root/lhtpi-backup-$(date +%Y%m%d%H%M%S)"

log() { echo -e "\n==> $*"; }
ok() { echo "✅ $*"; }
warn() { echo "⚠️  $*"; }
fail() { echo "❌ $*" >&2; exit 1; }

require_root() {
    if [ "${EUID}" -ne 0 ]; then
        fail "Bitte als root ausführen: sudo bash install.sh"
    fi
}

require_desktop_target() {
    if [ -f /proc/device-tree/model ] && ! grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then
        warn "Dieses System meldet sich nicht als Raspberry Pi. Installation wird trotzdem fortgesetzt."
    elif [ ! -f /proc/device-tree/model ]; then
        warn "Raspberry-Pi-Hardware konnte nicht erkannt werden. Installation wird trotzdem fortgesetzt."
    fi

    if [ ! -d /boot/firmware ]; then
        warn "/boot/firmware fehlt. Das Skript ist für Raspberry Pi OS Desktop (Trixie) gedacht."
    fi
}

ensure_pi_user() {
    if ! id "${PI_USER}" >/dev/null 2>&1; then
        fail "Benutzer '${PI_USER}' existiert nicht. Bitte Raspberry Pi OS Desktop mit Standardbenutzer 'pi' verwenden oder das Skript anpassen."
    fi
}

install_packages() {
    log "Installiere Systempakete für Desktop/Kiosk"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y \
        python3 python3-pip python3-venv \
        ufw curl git \
        xorg openbox \
        chromium-browser chromium-browser-l10n
    ok "Systempakete installiert"
}

prepare_project() {
    log "Richte Projekt unter ${PROJECT_DIR} ein"
    mkdir -p "${PROJECT_DIR}" "${PROJECT_DIR}/uploads"

    # Wenn das Skript aus einem anderen Verzeichnis gestartet wurde, Projektdateien nach /home/pi/lhtpi kopieren.
    if [ "${SCRIPT_DIR}" != "${PROJECT_DIR}" ]; then
        tar --exclude='./venv' --exclude='./.venv' --exclude='./__pycache__' --exclude='./lhtpi.db' \
            -C "${SCRIPT_DIR}" -cf - . | tar -C "${PROJECT_DIR}" -xf -
    fi

    [ -f "${PROJECT_DIR}/requirements.txt" ] || fail "${PROJECT_DIR}/requirements.txt fehlt. Bitte Repository nach ${PROJECT_DIR} kopieren."
    chown -R "${PI_USER}:${PI_GROUP}" "${PROJECT_DIR}"
    ok "Projektverzeichnis und uploads/ sind vorhanden"
}

setup_python() {
    log "Erstelle Python-Virtualenv und installiere requirements.txt"
    cd "${PROJECT_DIR}"
    sudo -u "${PI_USER}" python3 -m venv venv
    sudo -u "${PI_USER}" "${PROJECT_DIR}/venv/bin/python" -m pip install --upgrade pip
    sudo -u "${PI_USER}" "${PROJECT_DIR}/venv/bin/pip" install -r requirements.txt
    chown -R "${PI_USER}:${PI_GROUP}" "${PROJECT_DIR}"
    ok "Python-Umgebung fertig"
}

backup_configs() {
    log "Sichere relevante bestehende Konfigurationen nach ${BACKUP_DIR}"
    mkdir -p "${BACKUP_DIR}"
    cp -a /etc/NetworkManager/system-connections "${BACKUP_DIR}/system-connections" 2>/dev/null || true
    cp -a /etc/NetworkManager/conf.d "${BACKUP_DIR}/NetworkManager-conf.d" 2>/dev/null || true
    cp -a /etc/lightdm "${BACKUP_DIR}/lightdm" 2>/dev/null || true
    cp -a /boot/firmware/config.txt "${BACKUP_DIR}/config.txt" 2>/dev/null || true
    ok "Backup abgeschlossen"
}

configure_network() {
    log "Konfiguriere Netzwerk: eth0 bleibt DHCP, wlan0 wird NetworkManager-Access-Point"

    command -v nmcli >/dev/null 2>&1 || fail "nmcli fehlt. Raspberry Pi OS Desktop/Trixie mit NetworkManager wird benötigt."

    # Alte AP-Dienste dürfen nicht parallel zu NetworkManager laufen.
    systemctl stop hostapd dnsmasq 2>/dev/null || true
    systemctl disable hostapd dnsmasq 2>/dev/null || true
    systemctl mask hostapd dnsmasq 2>/dev/null || true

    # Trixie Desktop nutzt NetworkManager. systemd-networkd soll wlan0 nicht übernehmen.
    systemctl stop systemd-networkd 2>/dev/null || true
    systemctl disable systemd-networkd 2>/dev/null || true

    systemctl enable NetworkManager
    systemctl restart NetworkManager

    # WLAN-Powersave dauerhaft abschalten.
    mkdir -p /etc/NetworkManager/conf.d
    cat > /etc/NetworkManager/conf.d/99-lhtpi-wifi-powersave.conf <<'EOF'
[connection]
wifi.powersave = 2
EOF
    systemctl reload NetworkManager || systemctl restart NetworkManager

    # Alle bestehenden WLAN-Verbindungen löschen, damit der Pi nicht als Client in ein altes WLAN geht.
    while IFS=: read -r name uuid type device; do
        if [ "${type}" = "802-11-wireless" ] || [ "${device}" = "wlan0" ]; then
            nmcli con delete "${uuid}" || true
        fi
    done < <(nmcli -t -f NAME,UUID,TYPE,DEVICE con show)

    nmcli radio wifi on || true

    # eth0 wird bewusst nicht verändert: Raspberry Pi OS/NetworkManager belässt DHCP als Default.
    nmcli con add type wifi ifname wlan0 mode ap con-name lhtpi-ap ssid "${AP_SSID}"
    nmcli con modify lhtpi-ap wifi.band bg
    nmcli con modify lhtpi-ap wifi.channel 6
    nmcli con modify lhtpi-ap 802-11-wireless-security.key-mgmt wpa-psk
    nmcli con modify lhtpi-ap 802-11-wireless-security.psk "${AP_PASS}"
    nmcli con modify lhtpi-ap ipv4.method shared
    nmcli con modify lhtpi-ap ipv4.addresses "${AP_ADDR}"
    nmcli con modify lhtpi-ap ipv6.method ignore
    nmcli con modify lhtpi-ap connection.autoconnect yes
    nmcli con up lhtpi-ap || true

    ok "Access Point '${AP_SSID}' konfiguriert (${AP_ADDR}); eth0 bleibt per DHCP erreichbar"
}

configure_services() {
    log "Erstelle systemd-Service für Flask-App"
    local secret
    secret="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 48 || true)"
    [ -n "${secret}" ] || secret="lhtpi-change-me-$(date +%s)"

    cat > "/etc/systemd/system/${SERVICE_APP}" <<EOF
[Unit]
Description=LHTPi - Flask Web-App
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${PI_USER}
Group=${PI_GROUP}
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=LHTPI_HOST=0.0.0.0
Environment=LHTPI_PORT=${APP_PORT}
Environment=LHTPI_SECRET=${secret}
ExecStart=${PROJECT_DIR}/venv/bin/python ${PROJECT_DIR}/app.py
Restart=always
RestartSec=5
StartLimitIntervalSec=120
StartLimitBurst=5

[Install]
WantedBy=multi-user.target
EOF

    log "Erstelle Kiosk-Startskript ${KIOSK_SCRIPT}"
    cat > "${KIOSK_SCRIPT}" <<'EOF'
#!/bin/bash
set -u

LOG="/home/pi/lhtpi-kiosk.log"
APP_URL="http://localhost:8000/present/kiosk"
READY_URL="http://localhost:8000/login"

mkdir -p "$(dirname "$LOG")"
touch "$LOG"

echo "$(date '+%F %T') - LHTPi-Kiosk wartet auf Flask-App" >> "$LOG"

ready=0
for i in $(seq 1 30); do
    if curl -fsS --connect-timeout 2 --max-time 5 "$READY_URL" >/dev/null 2>&1; then
        ready=1
        echo "$(date '+%F %T') - Flask-App erreichbar, starte Chromium" >> "$LOG"
        break
    fi
    echo "$(date '+%F %T') - Versuch $i/30: Flask-App noch nicht erreichbar" >> "$LOG"
    sleep 2
done

if [ "$ready" -ne 1 ]; then
    echo "$(date '+%F %T') - Flask-App nach 30 Versuchen nicht erreichbar; starte Chromium trotzdem" >> "$LOG"
fi

xset s off >/dev/null 2>&1 || true
xset -dpms >/dev/null 2>&1 || true
xset s noblank >/dev/null 2>&1 || true

CHROMIUM="/usr/bin/chromium-browser"
[ -x "$CHROMIUM" ] || CHROMIUM="/usr/bin/chromium"

exec "$CHROMIUM" \
    --kiosk \
    --app="$APP_URL" \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-features=TranslateUI \
    --no-first-run \
    --check-for-update-interval=31536000 \
    --autoplay-policy=no-user-gesture-required \
    --disable-popup-blocking \
    --disable-translate \
    --overscroll-history-navigation=0 \
    --disable-pinch \
    --start-fullscreen \
    "$APP_URL" >> "$LOG" 2>&1
EOF
    chmod +x "${KIOSK_SCRIPT}"
    chown "${PI_USER}:${PI_GROUP}" "${KIOSK_SCRIPT}"

    log "Erstelle systemd-Service für HDMI-Kiosk"
    cat > "/etc/systemd/system/${SERVICE_KIOSK}" <<EOF
[Unit]
Description=LHTPi - HDMI Chromium Kiosk
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

    systemctl daemon-reload
    systemctl enable "${SERVICE_APP}" "${SERVICE_KIOSK}"
    ok "systemd-Services erstellt und aktiviert"
}

configure_desktop() {
    log "Konfiguriere X11/Openbox, LightDM-Autologin und HDMI-Fallback"

    mkdir -p /etc/lightdm/lightdm.conf.d
    cat > /etc/lightdm/lightdm.conf.d/50-lhtpi-autologin.conf <<EOF
[Seat:*]
autologin-user=${PI_USER}
autologin-user-timeout=0
user-session=openbox
EOF

    mkdir -p "/home/${PI_USER}/.config/openbox"
    cat > "/home/${PI_USER}/.config/openbox/autostart" <<'EOF'
# LHTPi: Bildschirm für Dauerbetrieb wach halten
xset s off
xset -dpms
xset s noblank
EOF
    chown -R "${PI_USER}:${PI_GROUP}" "/home/${PI_USER}/.config"

    mkdir -p /etc/systemd/system/getty@tty1.service.d
    cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin ${PI_USER} --noclear %I \$TERM
EOF

    if [ -f /boot/firmware/config.txt ]; then
        grep -qxF 'hdmi_force_hotplug=1' /boot/firmware/config.txt || echo 'hdmi_force_hotplug=1' >> /boot/firmware/config.txt
        grep -qxF 'hdmi_group=2' /boot/firmware/config.txt || echo 'hdmi_group=2' >> /boot/firmware/config.txt
        grep -qxF 'hdmi_mode=82' /boot/firmware/config.txt || echo 'hdmi_mode=82' >> /boot/firmware/config.txt
    else
        warn "/boot/firmware/config.txt nicht gefunden; HDMI-Fallback wurde nicht geschrieben."
    fi

    systemctl set-default graphical.target
    ok "Desktop/Kiosk-Autostart konfiguriert"
}

configure_firewall() {
    log "Konfiguriere UFW"
    ufw allow ssh
    ufw allow "${APP_PORT}/tcp"
    ufw --force enable
    ok "Firewall aktiv: SSH und Port ${APP_PORT}/tcp erlaubt"
}

finish_install() {
    log "Installation abgeschlossen"
    echo "Dashboard über LAN: http://<LAN-IP>:${APP_PORT}"
    echo "Dashboard über LHTPi-AP: http://192.168.4.1:${APP_PORT}"
    echo "AP: SSID '${AP_SSID}', Passwort '${AP_PASS}'"
    echo "Login: admin / admin"
    echo ""
    echo "Neustart in 5 Sekunden ..."
    sleep 5
    reboot
}

main() {
    echo "================================================"
    echo "  ${PROJECT_NAME} Installation - Raspberry Pi OS Desktop/Trixie"
    echo "  Kein Lite-Modus: X11/Openbox/Chromium-Kiosk wird eingerichtet"
    echo "================================================"

    require_root
    require_desktop_target
    ensure_pi_user
    install_packages
    prepare_project
    setup_python
    backup_configs
    configure_network
    configure_services
    configure_desktop
    configure_firewall
    finish_install
}

main "$@"
