#!/bin/bash
# LHTPi Installationsskript
# Richtet einen Raspberry Pi 4/5 (Trixie) als Präsentations-Player ein.
#
# Zwei Modi:
#   Desktop (Standard) – mit X11/Openbox/Chromium-Kiosk
#   Lite              – ohne GUI, nur Access Point + Web-Dashboard
#
# Nutzung:
#   sudo bash install.sh          → Desktop-Modus
#   sudo bash install.sh lite     → Lite-Modus (für Lite OS / headless)
#
# LAN (eth0) bleibt per DHCP erreichbar – Pi ist gleichzeitig im
# Heimnetzwerk per LAN und als WLAN-AP (192.168.4.1) nutzbar.

PROJECT_NAME="LHTPi"
PROJECT_DIR="/home/pi/lhtpi"
APP_PORT="8000"
AP_SSID="LHTPi"
AP_PASS="LHTPi123"
SERVICE_APP="lhtpi.service"
SERVICE_KIOSK="lhtpi-kiosk.service"
KIOSK_SCRIPT="/home/pi/start_lhtpi_kiosk.sh"
KIOSK_LOG="/home/pi/lhtpi-kiosk.log"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="/root/lhtpi-backup-$(date +%Y%m%d%H%M%S)"

# ── Modus erkennen ──────────────────────────────────────────────────────
MODE="${1:-desktop}"
if [ "$MODE" != "desktop" ] && [ "$MODE" != "lite" ]; then
    echo "❌ Unbekannter Modus '$MODE'. Erlaubt: desktop, lite"
    echo "   Beispiel: sudo bash install.sh lite"
    exit 1
fi

echo "================================================"
echo "  ${PROJECT_NAME} - Installation"
echo "  Modus: ${MODE}"
echo "================================================"
echo ""

if [ ! -f /proc/device-tree/model ] || ! grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then
    echo "⚠  Dieses System sieht nicht wie ein Raspberry Pi aus."
    echo "   Installation wird trotzdem fortgesetzt..."
fi

if [ "$EUID" -ne 0 ]; then
    echo "❌ Bitte als root ausführen: sudo bash install.sh [modus]"
    exit 1
fi

# ── 1. Pakete installieren ─────────────────────────────────────────────
echo "📦 Installiere Systempakete..."

BASE_PKGS="python3 python3-pip python3-venv ufw curl git"

if [ "$MODE" = "desktop" ]; then
    GUI_PKGS="xorg openbox chromium-browser chromium-browser-l10n"
else
    GUI_PKGS=""
    echo "   (Lite-Modus: Kein X11/Chromium – Dashboard nur per WLAN)"
fi

apt-get update -qq
# shellcheck disable=SC2086
apt-get install -y -qq $BASE_PKGS $GUI_PKGS

echo "✅ Systempakete installiert"

# ── 2. Projektverzeichnis ──────────────────────────────────────────────
echo "📁 Richte Projektverzeichnis ein..."
mkdir -p "$PROJECT_DIR" "$PROJECT_DIR/uploads"
if [ "$SCRIPT_DIR" != "$PROJECT_DIR" ]; then
    cp -r "$SCRIPT_DIR"/* "$PROJECT_DIR/" 2>/dev/null || true
fi
chown -R pi:pi "$PROJECT_DIR"
cd "$PROJECT_DIR"
echo "✅ Projektverzeichnis eingerichtet mit uploads/"

# ── 3. Python-Venv ─────────────────────────────────────────────────────
echo "🐍 Erstelle Python-Virtualenv..."
sudo -u pi python3 -m venv venv
sudo -u pi ./venv/bin/pip install --upgrade pip -q
sudo -u pi ./venv/bin/pip install -r requirements.txt -q
echo "✅ Python-Abhängigkeiten installiert"

# ── 4. Bestehende Konfiguration sichern ─────────────────────────────────
echo "💾 Sichere bestehende Konfiguration..."
mkdir -p "$BACKUP_DIR"
BACKUP_FILES=""
for f in /etc/NetworkManager/system-connections/*.nmconnection /boot/firmware/config.txt; do
    [ -f "$f" ] && cp "$f" "$BACKUP_DIR/" 2>/dev/null || true
done
echo "✅ Backup nach $BACKUP_DIR"

# ── 5. Netzwerk: eth0 bleibt per DHCP, wlan0 wird AP ───────────────────
echo "🌐 Konfiguriere Netzwerk..."

# Alte hostapd/dnsmasq-Installationen deaktivieren (falls vorhanden)
systemctl stop hostapd dnsmasq 2>/dev/null || true
systemctl disable hostapd dnsmasq 2>/dev/null || true
systemctl mask hostapd dnsmasq 2>/dev/null || true

# Alte systemd-networkd-Config für wlan0 entfernen (Trixie nutzt NM)
rm -f /etc/systemd/network/08-wlan0-ap.network

# NetworkManager: eth0 bleibt unangetastet (DHCP per default)
# NetworkManager: wlan0 wird zum Access Point
# Bestehende WLAN-Verbindungen löschen (damit wlan0 nicht managed bleibt)
nmcli -t con show | grep -i wlan 2>/dev/null | while IFS=: read -r name uuid type dev; do
    nmcli con delete "$uuid" 2>/dev/null
done

# AP-Verbindung über NetworkManager anlegen (shared = NAT+DHCP)
nmcli con add type wifi ifname wlan0 mode ap con-name lhtpi-ap ssid "$AP_SSID"
nmcli con modify lhtpi-ap wifi.band bg
nmcli con modify lhtpi-ap wifi.channel 6
nmcli con modify lhtpi-ap 802-11-wireless-security.key-mgmt wpa-psk
nmcli con modify lhtpi-ap 802-11-wireless-security.psk "$AP_PASS"
nmcli con modify lhtpi-ap ipv4.method shared
nmcli con modify lhtpi-ap ipv4.address 192.168.4.1/24

# AP sofort aktivieren (ohne Neustart)
nmcli con up lhtpi-ap 2>/dev/null || true

echo "✅ Access Point konfiguriert (SSID: ${AP_SSID})"
echo "   LAN (eth0) bleibt per DHCP erreichbar"

# ── 6. systemd-networkd deaktivieren (nicht benötigt unter Trixie) ──────
systemctl stop systemd-networkd 2>/dev/null || true
systemctl disable systemd-networkd 2>/dev/null || true

# ── 7. Flask-App als systemd-Service ───────────────────────────────────
echo "⚙️  Erstelle systemd-Service (App)..."

cat > /etc/systemd/system/${SERVICE_APP} << APPEOF
[Unit]
Description=LHTPi - Präsentations-Player Web-App
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=LHTPI_SECRET=$(head -c 32 /dev/urandom | base64)
ExecStart=${PROJECT_DIR}/venv/bin/python app.py
Restart=always
RestartSec=5
StartLimitIntervalSec=120
StartLimitBurst=5

[Install]
WantedBy=multi-user.target
APPEOF

echo "✅ App-Service erstellt"

# ── 8. Desktop-Modus: Kiosk + X11 ─────────────────────────────────────
if [ "$MODE" = "desktop" ]; then

    # ── 8a. Kiosk-Skript ──────────────────────────────────────────────
    echo "🖥️  Erstelle Kiosk-Startskript..."

    cat > ${KIOSK_SCRIPT} << 'KIOSKEOF'
#!/bin/bash
# LHTPi - Kiosk-Startskript
LOG="/home/pi/lhtpi-kiosk.log"
APP_URL="http://localhost:8000/present/kiosk"

echo "$(date) - LHTPi Kiosk gestartet" >> "$LOG"

# Warten, bis die Flask-App erreichbar ist
for i in $(seq 1 30); do
    if curl -s -o /dev/null --connect-timeout 2 "http://localhost:8000/present/kiosk" 2>/dev/null; then
        echo "$(date) - Flask-App erreichbar, starte Chromium" >> "$LOG"
        break
    fi
    sleep 2
done

# Bildschirm nicht ausschalten
xset s off
xset -dpms
xset s noblank

# Chromium im Kioskmodus starten
exec /usr/bin/chromium-browser \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-features=TranslateUI \
    --no-first-run \
    --check-for-update-interval=31536000 \
    --touch-events=enabled \
    --fast \
    --fast-start \
    --autoplay-policy=no-user-gesture-required \
    --disable-popup-blocking \
    --disable-translate \
    "${APP_URL}" >> "$LOG" 2>&1
KIOSKEOF

    chmod +x ${KIOSK_SCRIPT}
    chown pi:pi ${KIOSK_SCRIPT}

    # ── 8b. Kiosk-Service ─────────────────────────────────────────────
    cat > /etc/systemd/system/${SERVICE_KIOSK} << KIOSKSVCEOF
[Unit]
Description=LHTPi - Kiosk-Präsentationsmodus
After=${SERVICE_APP}
Requires=${SERVICE_APP}

[Service]
Type=simple
User=pi
Group=pi
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/pi/.Xauthority
ExecStartPre=/bin/sleep 5
ExecStart=${KIOSK_SCRIPT}
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=120
StartLimitBurst=3

[Install]
WantedBy=multi-user.target
KIOSKSVCEOF

    echo "✅ Kiosk-Service erstellt"

    # ── 8c. X11-Autostart + Desktop-Session ───────────────────────────
    echo "🖥️  Richte Desktop-Session ein..."

    # LightDM mit Auto-Login
    mkdir -p /etc/lightdm/
    cat > /etc/lightdm/lightdm.conf << 'LIGHTDM'
[Seat:*]
autologin-user=pi
autologin-user-timeout=0
user-session=LXDE-pi
LIGHTDM

    # Openbox-Autostart
    mkdir -p /home/pi/.config/openbox
    cat > /home/pi/.config/openbox/autostart << 'OBEOF'
# LHTPi - Openbox Autostart
xset s off
xset -dpms
xset s noblank
OBEOF
    chown -R pi:pi /home/pi/.config

    # systemd-logind Auto-Login
    mkdir -p /etc/systemd/system/getty@tty1.service.d/
    cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << 'GETTYEOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty -o '-p -f -- \\u' --noclear --autologin pi %I $TERM
GETTYEOF

    # X11 erzwingen (Trixie: falls Wayland aktiv)
    mkdir -p /etc/systemd/system/lightdm.service.d/
    cat > /etc/systemd/system/lightdm.service.d/x11.conf << 'X11EOF'
[Service]
Environment=XDG_SESSION_TYPE=x11
X11EOF

    if command -v raspi-config &>/dev/null; then
        raspi-config nonint do_boot_behaviour B4 2>/dev/null || true
    fi

    echo "✅ Desktop-Session eingerichtet"

    # ── 8d. boot/config.txt ──────────────────────────────────────────
    echo "🖥️  Konfiguriere boot/config.txt..."

    if [ -f /boot/firmware/config.txt ]; then
        CONFIG="/boot/firmware/config.txt"
    else
        CONFIG="/boot/config.txt"
    fi

    if ! grep -q "### LHTPi START" "$CONFIG" 2>/dev/null; then
        cat >> "$CONFIG" << 'BOOTEOF'

### LHTPi START
# X11 / KMS
dtoverlay=vc4-fkms-v3d
# HDMI Fallback
hdmi_force_hotplug=1
hdmi_group=2
hdmi_mode=82
config_hdmi_boost=4
disable_overscan=1
### LHTPi END
BOOTEOF
    fi

    # ── 8e. Energiesparmodus ─────────────────────────────────────────
    echo "🔌 Deaktiviere Energiesparmodus..."

    cat > /etc/profile.d/lhtpi_display.sh << 'DPYEOF'
#!/bin/sh
if [ "$DISPLAY" != "" ]; then
    xset s off 2>/dev/null
    xset -dpms 2>/dev/null
    xset s noblank 2>/dev/null
fi
DPYEOF
    chmod +x /etc/profile.d/lhtpi_display.sh

    echo "✅ Desktop-Konfiguration abgeschlossen"
fi

# ── 9. UFW Firewall ────────────────────────────────────────────────────
echo "🔥 Konfiguriere Firewall..."

ufw --force reset 2>/dev/null || true
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 8000/tcp
ufw allow from 192.168.4.0/24 to any port 53 proto udp
ufw allow from 192.168.4.0/24 to any port 67 proto udp
ufw --force enable 2>/dev/null || true
echo "✅ Firewall konfiguriert (SSH + Port 8000 offen)"

# ── 10. Services aktivieren ────────────────────────────────────────────
echo "🚀 Aktiviere Services..."

systemctl daemon-reload
systemctl enable ${SERVICE_APP}

if [ "$MODE" = "desktop" ]; then
    systemctl enable ${SERVICE_KIOSK}
    systemctl enable lightdm 2>/dev/null || true
fi

echo "✅ Services aktiviert"

# ── 11. WiFi Powersave deaktivieren ─────────────────────────────────────
echo "📶 Deaktiviere WiFi Powersave..."

if command -v iw &>/dev/null; then
    iw dev wlan0 set power_save off 2>/dev/null || true
fi

# Dauerhaft via NetworkManager
mkdir -p /etc/NetworkManager/conf.d/
cat > /etc/NetworkManager/conf.d/99-lhtpi-wifi-powersave-off.cfg << 'NMPWR'
[connection]
wifi.powersave = 2
NMPWR

echo "✅ WiFi Powersave deaktiviert"

# ── 12. Fertig ────────────────────────────────────────────────────────
echo ""
echo "================================================"
echo "  ✅ ${PROJECT_NAME} Installation abgeschlossen!"
echo "  Modus: ${MODE}"
echo "================================================"
echo ""
echo "  AP-SSID:     ${AP_SSID}"
echo "  AP-Passwort: ${AP_PASS}"
echo "  Dashboard:   http://192.168.4.1:${APP_PORT}"
echo "  LAN-Zugriff: über DHCP-IP (z.B. 192.168.178.188)"
echo "  Login:       admin / admin"
echo ""
echo "📋 Nach Neustart startet automatisch:"
echo "   - Flask-App als systemd-Service"
echo "   - Access Point mit SSID '${AP_SSID}'"
echo "   - LAN (eth0) normal per DHCP"
if [ "$MODE" = "desktop" ]; then
    echo "   - X11/Openbox-Session"
    echo "   - Chromium im Kioskmodus"
else
    echo "   - (Kein Kiosk – Lite-Modus)"
fi
echo ""
echo "👉 Starte Neustart in 5 Sekunden..."
echo "================================================"
sleep 5
echo "🔄 Reboot..."
reboot
