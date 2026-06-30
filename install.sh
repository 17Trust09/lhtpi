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

# ── Hilfsfunktionen ────────────────────────────────────────────────────
log()  { echo -e "\n==> $*"; }
ok()   { echo "  ✅ $*"; }
warn() { echo "  ⚠️  $*"; }
fail() { echo -e "\n  ❌ $*" >&2; exit 1; }

require_root() {
    if [ "${EUID}" -ne 0 ]; then
        fail "Bitte als root ausführen: sudo bash install.sh"
    fi
}

require_desktop_target() {
    if [ -f /proc/device-tree/model ] && ! grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then
        warn "Dieses System ist kein Raspberry Pi. Installation wird trotzdem versucht."
    fi
    if ! command -v Xorg &>/dev/null && ! dpkg -l xorg &>/dev/null 2>&1; then
        warn "Xorg scheint nicht installiert. Stelle sicher, dass Raspberry Pi OS Desktop verwendet wird."
    fi
}

ensure_pi_user() {
    if ! id "${PI_USER}" >/dev/null 2>&1; then
        fail "Benutzer '${PI_USER}' existiert nicht. Bitte Raspberry Pi OS Desktop verwenden."
    fi
    if [ ! -d "/home/${PI_USER}" ]; then
        fail "Home-Verzeichnis /home/${PI_USER} nicht gefunden."
    fi
}

retry_nmcli() {
    # Führt nmcli aus, wartet bei transienten Fehlern und wiederholt.
    local cmd=("$@")
    for i in 1 2 3; do
        if "${cmd[@]}" 2>/dev/null; then
            return 0
        fi
        warn "nmcli (Versuch $i/3) fehlgeschlagen: ${cmd[*]}"
        sleep 2
    done
    # Letzter Versuch – Fehler wird ausgegeben, Skript läuft weiter
    "${cmd[@]}" 2>&1 || warn "nmcli-Kommando endgültig fehlgeschlagen (nicht kritisch): ${cmd[*]}"
    return 0
}

wait_for_ap() {
    # Wartet maximal 30s, bis der Access Point aktiv ist.
    log "Warte auf Access Point '${AP_SSID}'..."
    for i in $(seq 1 15); do
        if nmcli -t con show lhtpi-ap --active 2>/dev/null | grep -q lhtpi-ap; then
            ok "Access Point '${AP_SSID}' ist aktiv"
            return 0
        fi
        if iw dev wlan0 info 2>/dev/null | grep -q type.ap; then
            ok "wlan0 ist im AP-Modus"
            return 0
        fi
        sleep 2
    done
    warn "Access Point wurde nicht als aktiv erkannt. Das Dashboard ist trotzdem per LAN erreichbar."
    warn "Nach dem Reboot sollte der AP automatisch starten."
    return 0
}

# ── Installationsschritte ──────────────────────────────────────────────

install_packages() {
    log "Installiere Systempakete"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq \
        python3 python3-pip python3-venv \
        ufw curl git \
        xorg openbox unclutter \
        chromium-browser chromium-browser-l10n
    ok "Systempakete installiert"
}

prepare_project() {
    log "Richte Projekt unter ${PROJECT_DIR} ein"
    mkdir -p "${PROJECT_DIR}" "${PROJECT_DIR}/uploads"

    if [ "${SCRIPT_DIR}" != "${PROJECT_DIR}" ]; then
        # Dateien kopieren, aber venv/Caches ausschließen
        for f in "${SCRIPT_DIR}"/*; do
            [ -f "$f" ] && cp "$f" "${PROJECT_DIR}/" 2>/dev/null || true
        done
        for d in templates static; do
            [ -d "${SCRIPT_DIR}/${d}" ] && cp -r "${SCRIPT_DIR}/${d}" "${PROJECT_DIR}/" 2>/dev/null || true
        done
    fi

    if [ ! -f "${PROJECT_DIR}/requirements.txt" ]; then
        fail "${PROJECT_DIR}/requirements.txt fehlt. Bitte Repository korrekt klonen."
    fi

    chown -R "${PI_USER}:${PI_GROUP}" "${PROJECT_DIR}"
    ok "Projektverzeichnis mit uploads/ bereit"
}

setup_python() {
    log "Erstelle Python-Virtualenv"
    cd "${PROJECT_DIR}"
    sudo -u "${PI_USER}" python3 -m venv venv
    sudo -u "${PI_USER}" "${PROJECT_DIR}/venv/bin/python" -m pip install --upgrade pip -q
    sudo -u "${PI_USER}" "${PROJECT_DIR}/venv/bin/pip" install -r requirements.txt -q
    chown -R "${PI_USER}:${PI_GROUP}" "${PROJECT_DIR}"
    ok "Python-Umgebung fertig (Venv + Abhängigkeiten)"
}

backup_configs() {
    log "Sichere bestehende Konfiguration nach ${BACKUP_DIR}"
    mkdir -p "${BACKUP_DIR}"
    cp -a /etc/NetworkManager/system-connections "${BACKUP_DIR}/system-connections" 2>/dev/null || true
    cp -a /etc/NetworkManager/conf.d "${BACKUP_DIR}/NetworkManager-conf.d" 2>/dev/null || true
    cp -a /etc/lightdm "${BACKUP_DIR}/lightdm" 2>/dev/null || true
    [ -f /boot/firmware/config.txt ] && cp /boot/firmware/config.txt "${BACKUP_DIR}/config.txt"
    ok "Backup abgeschlossen"
}

configure_network() {
    log "Konfiguriere Netzwerk"
    log "  eth0: bleibt per DHCP (LAN-Zugriff)"
    log "  wlan0: wird zum Access Point '${AP_SSID}'"

    command -v nmcli >/dev/null 2>&1 || fail "nmcli fehlt. Raspberry Pi OS Desktop (Trixie) mit NetworkManager benötigt."

    # 1. hostapd/dnsmasq stilllegen (falls aus alter Installation)
    log "  Deaktiviere alte AP-Dienste (hostapd/dnsmasq)..."
    systemctl stop hostapd dnsmasq 2>/dev/null || true
    systemctl disable hostapd dnsmasq 2>/dev/null || true
    systemctl mask hostapd dnsmasq 2>/dev/null || true

    # 2. systemd-networkd deaktivieren (Trixie nutzt NM)
    log "  Deaktiviere systemd-networkd..."
    systemctl stop systemd-networkd 2>/dev/null || true
    systemctl disable systemd-networkd 2>/dev/null || true

    # 3. NetworkManager aktivieren + Powersave ausschalten
    log "  Aktiviere NetworkManager und deaktiviere WiFi Powersave..."
    systemctl enable NetworkManager
    systemctl restart NetworkManager
    sleep 2

    mkdir -p /etc/NetworkManager/conf.d
    cat > /etc/NetworkManager/conf.d/99-lhtpi-wifi-powersave.conf <<'EOF'
[connection]
wifi.powersave = 2
EOF
    systemctl reload NetworkManager 2>/dev/null || systemctl restart NetworkManager
    sleep 1

    # 4. Alte WLAN-Client-Verbindungen löschen
    log "  Lösche alte WLAN-Client-Verbindungen..."
    while IFS=: read -r name uuid type device; do
        if [ "${type}" = "802-11-wireless" ]; then
            log "    Lösche alte WLAN-Verbindung: ${name} (${uuid})"
            nmcli con delete "${uuid}" 2>/dev/null || true
        fi
    done < <(nmcli -t -f NAME,UUID,TYPE,DEVICE con show 2>/dev/null || true)

    # 5. AP-Verbindung anlegen (falls nicht vorhanden)
    log "  Lege AP-Verbindung 'lhtpi-ap' an..."
    if nmcli -t con show lhtpi-ap &>/dev/null; then
        log "    Verbindung existiert bereits, überspringe create"
    else
        retry_nmcli nmcli con add type wifi ifname wlan0 mode ap con-name lhtpi-ap ssid "${AP_SSID}"
        retry_nmcli nmcli con modify lhtpi-ap wifi.band bg
        retry_nmcli nmcli con modify lhtpi-ap wifi.channel 6
        retry_nmcli nmcli con modify lhtpi-ap 802-11-wireless-security.key-mgmt wpa-psk
        retry_nmcli nmcli con modify lhtpi-ap 802-11-wireless-security.psk "${AP_PASS}"
        retry_nmcli nmcli con modify lhtpi-ap ipv4.method shared
        retry_nmcli nmcli con modify lhtpi-ap ipv4.addresses "${AP_ADDR}"
        retry_nmcli nmcli con modify lhtpi-ap ipv6.method ignore
        retry_nmcli nmcli con modify lhtpi-ap connection.autoconnect yes
    fi

    # 6. AP starten
    log "  Starte Access Point..."
    # Vor dem Up kurz warten, damit NM die Änderungen verarbeitet
    sleep 2
    nmcli con up lhtpi-ap 2>&1 || warn "AP konnte nicht sofort gestartet werden (startet nach Reboot)"

    # 7. Warten und prüfen
    wait_for_ap

    # 8. eth0 wird NICHT angefasst – NM belässt DHCP.
    #    Zusätzlich: Notfall-IP auf eth0 falls DHCP fehlschlägt (nur wenn keine IP vorhanden)
    if ! ip addr show eth0 2>/dev/null | grep -q 'inet '; then
        log "  eth0 hat keine IP – setze temporär 192.168.178.250/24 als Fallback"
        ip addr add 192.168.178.250/24 dev eth0 2>/dev/null || true
    fi

    ok "Netzwerk konfiguriert: eth0=DHCP, wlan0=AP '${AP_SSID}'"
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

echo "$(date '+%F %T') - LHTPi-Kiosk gestartet, warte auf Flask-App" >> "$LOG"

ready=0
for i in $(seq 1 30); do
    if curl -fsS --connect-timeout 2 --max-time 5 "$READY_URL" >/dev/null 2>&1; then
        ready=1
        echo "$(date '+%F %T') - Flask-App erreichbar, starte Chromium" >> "$LOG"
        break
    fi
    echo "$(date '+%F %T') - Versuch $i/30: Flask-App noch nicht bereit" >> "$LOG"
    sleep 2
done

if [ "$ready" -ne 1 ]; then
    echo "$(date '+%F %T') - Flask-App nach 30 Versuchen nicht erreichbar, starte Chromium trotzdem" >> "$LOG"
fi

xset s off >/dev/null 2>&1 || true
xset -dpms >/dev/null 2>&1 || true
xset s noblank >/dev/null 2>&1 || true

# Mauszeiger nach 5s Inaktivität ausblenden
unclutter -idle 5 -root >/dev/null 2>&1 || true

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
    log "Konfiguriere X11/LightDM/Openbox und HDMI-Fallback"

    # LightDM-Autologin (Openbox als Default-Session)
    mkdir -p /etc/lightdm/lightdm.conf.d
    cat > /etc/lightdm/lightdm.conf.d/50-lhtpi-autologin.conf <<EOF
[Seat:*]
autologin-user=${PI_USER}
autologin-user-timeout=0
user-session=openbox
autologin-session=openbox
EOF

    # Wayland-Sessions für den Kiosk deaktivieren – Chromium-Kiosk,
    # unclutter und xset brauchen zwingend X11
    if [ -d /usr/share/wayland-sessions ]; then
        mkdir -p /usr/share/wayland-sessions/disabled
        for f in /usr/share/wayland-sessions/*.desktop; do
            [ -f "$f" ] && mv "$f" /usr/share/wayland-sessions/disabled/ 2>/dev/null || true
        done
        log "  Wayland-Sessions deaktiviert (X11 erforderlich für Kiosk)"
    fi

    # Openbox-Autostart
    mkdir -p "/home/${PI_USER}/.config/openbox"
    cat > "/home/${PI_USER}/.config/openbox/autostart" <<'EOF'
# LHTPi: Bildschirm für Dauerbetrieb wach halten
xset s off
xset -dpms
xset s noblank
EOF
    chown -R "${PI_USER}:${PI_GROUP}" "/home/${PI_USER}/.config"

    # Getty-Autologin tty1
    mkdir -p /etc/systemd/system/getty@tty1.service.d
    cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin ${PI_USER} --noclear %I \$TERM
EOF

    # HDMI-Fallback in config.txt
    if [ -f /boot/firmware/config.txt ]; then
        grep -qxF 'hdmi_force_hotplug=1' /boot/firmware/config.txt || echo 'hdmi_force_hotplug=1' >> /boot/firmware/config.txt
        grep -qxF 'hdmi_group=2' /boot/firmware/config.txt || echo 'hdmi_group=2' >> /boot/firmware/config.txt
        grep -qxF 'hdmi_mode=82' /boot/firmware/config.txt || echo 'hdmi_mode=82' >> /boot/firmware/config.txt
    else
        warn "/boot/firmware/config.txt nicht gefunden – HDMI-Fallback nicht gesetzt"
    fi

    systemctl set-default graphical.target
    ok "Desktop/Kiosk-Autostart konfiguriert"
}

configure_firewall() {
    log "Konfiguriere Firewall (UFW)"
    ufw --force reset 2>/dev/null || true
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    ufw allow "${APP_PORT}/tcp"
    ufw --force enable
    ok "Firewall aktiv: SSH + Port ${APP_PORT}/tcp freigegeben"
}

print_summary() {
    echo ""
    echo "================================================"
    echo "  ✅ ${PROJECT_NAME} Installation abgeschlossen!"
    echo "================================================"
    echo ""
    echo "  📡 Access Point:  ${AP_SSID} / ${AP_PASS}"
    echo "  🌐 AP-Dashboard:  http://192.168.4.1:${APP_PORT}"
    echo "  🌐 LAN-Dashboard: http://<LAN-IP>:${APP_PORT}"
    echo "  🔑 Login:         admin / admin"
    echo ""
    echo "  📺 HDMI: Chromium-Kiosk mit ${KIOSK_URL}"
    echo "  🔗 SSH (LAN): ssh pi@<LAN-IP>"
    echo ""
    echo "  ⚠️  Wichtig: DHCP-Reservierung im Router für den Pi einrichten,"
    echo "     damit die LAN-IP stabil bleibt."
    echo "-----------------------------------------------"
    echo ""
    echo "👉 Neustart in 5 Sekunden..."
    sleep 5
    echo "🔄 Reboot..."
    reboot
}

# ── Hauptprogramm ──────────────────────────────────────────────────────
main() {
    echo "================================================"
    echo "  ${PROJECT_NAME} Installation"
    echo "  Raspberry Pi OS Desktop (Trixie)"
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
    print_summary
}

main "$@"
