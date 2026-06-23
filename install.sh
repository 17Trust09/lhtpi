#!/bin/bash
# LHTPi Installationsskript
# Richtet einen Raspberry Pi 4/5 als autarken Präsentations-Player ein.
#
# Zwei Modi:
#   Desktop (Standard) – mit X11/Openbox/Chromium-Kiosk
#   Lite              – ohne GUI, nur Access Point + Web-Dashboard
#
# Nutzung:
#   sudo bash install.sh          → Desktop-Modus
#   sudo bash install.sh lite     → Lite-Modus (für Lite OS / headless)

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

BASE_PKGS="python3 python3-pip python3-venv hostapd dnsmasq ufw curl git"

if [ "$MODE" = "desktop" ]; then
    GUI_PKGS="xorg openbox chromium-browser chromium-browser-l10n"
else
    GUI_PKGS=""
    echo "   (Lite-Modus: Kein X11/Chromium – Web-Dashboard nur per WLAN)"
fi

apt-get update -qq
# shellcheck disable=SC2086
apt-get install -y -qq $BASE_PKGS $GUI_PKGS

apt-mark hold hostapd dnsmasq 2>/dev/null || true

# ── 2. Projektverzeichnis ──────────────────────────────────────────────
echo "📁 Richte Projektverzeichnis ein..."
mkdir -p "$PROJECT_DIR"
if [ "$SCRIPT_DIR" != "$PROJECT_DIR" ]; then
    cp -r "$SCRIPT_DIR"/* "$PROJECT_DIR/" 2>/dev/null || true
fi
chown -R pi:pi "$PROJECT_DIR"
cd "$PROJECT_DIR"

# ── 3. Python-Venv ─────────────────────────────────────────────────────
echo "🐍 Erstelle Python-Virtualenv..."
sudo -u pi python3 -m venv venv
sudo -u pi ./venv/bin/pip install --upgrade pip -q
sudo -u pi ./venv/bin/pip install -r requirements.txt -q
echo "✅ Python-Abhängigkeiten installiert"

# ── 4. Bestehende Konfiguration sichern ─────────────────────────────────
echo "💾 Sichere bestehende Konfiguration..."
mkdir -p "$BACKUP_DIR"
BACKUP_FILES="/etc/hostapd/hostapd.conf /etc/dnsmasq.conf"
if [ "$MODE" = "desktop" ]; then
    BACKUP_FILES="$BACKUP_FILES /etc/dhcpcd.conf /etc/lightdm/lightdm.conf /boot/firmware/config.txt"
fi
for f in $BACKUP_FILES; do
    [ -f "$f" ] && cp "$f" "$BACKUP_DIR/" 2>/dev/null || true
done
echo "✅ Backup nach $BACKUP_DIR"

# ── 5. Access Point konfigurieren ──────────────────────────────────────
echo "📡 Konfiguriere Access Point..."

# hostapd – Optimierte Konfiguration
cat > /etc/hostapd/hostapd.conf << 'HOSTAPDEOF'
interface=wlan0
driver=nl80211
ssid=LHTPi
hw_mode=g
channel=6

# 20 MHz Kanalbreite (kein HT40, viele Clients haben Probleme damit)
ht_capab=[HT20][SHORT-GI-20][RX-STBC1]

# WMM für Multimedia-Performance
wmm_enabled=1

# Sicherheit
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=LHTPi123
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
rsn_pairwise=CCMP

# Beacon-Intervall
beacon_int=100

# DTIM-Periode
dtim_period=2
HOSTAPDEOF
chmod 600 /etc/hostapd/hostapd.conf

# dnsmasq – DHCP + DNS, optimiert für stabile Clients
cat > /etc/dnsmasq.conf << 'DNSMASQEOF'
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.100,255.255.255.0,24h
dhcp-option=3,192.168.4.1
dhcp-option=6,192.168.4.1
# MTU auf 1500 – viele Clients/Geräte haben kaputte PMTU-Discovery
dhcp-option=26,1500
dhcp-lease-max=50
# Lokale DNS-Weiterleitung
address=/lhtpi.local/192.168.4.1
no-resolv
server=8.8.8.8
server=1.1.1.1
cache-size=1000
neg-ttl=60
DNSMASQEOF

# Statische IP für wlan0 via systemd-networkd (Bookworm-kompatibel)
mkdir -p /etc/systemd/network/
cat > /etc/systemd/network/08-wlan0-ap.network << NETEOF
[Match]
Name=wlan0

[Network]
Address=192.168.4.1/24
DHCPServer=no
IPForward=yes
NETEOF

# dhcpcd deaktivieren
if systemctl is-enabled dhcpcd &>/dev/null; then
    systemctl stop dhcpcd 2>/dev/null || true
    systemctl disable dhcpcd 2>/dev/null || true
fi

# hostapd-Daemon-Pfad setzen
if grep -q "^#DAEMON_CONF=" /etc/default/hostapd; then
    sed -i 's|^#DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd
elif ! grep -q "^DAEMON_CONF=" /etc/default/hostapd; then
    echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' >> /etc/default/hostapd
fi

echo "✅ Access Point konfiguriert (SSID: ${AP_SSID})"

# ── 6. Flask-App als systemd-Service ───────────────────────────────────
echo "⚙️  Erstelle systemd-Service (App)..."

cat > /etc/systemd/system/${SERVICE_APP} << APPEOF
[Unit]
Description=LHTPi - Präsentations-Player Web-App
After=network.target

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

# ── 7. Desktop-Modus: Kiosk + X11 ─────────────────────────────────────
if [ "$MODE" = "desktop" ]; then

    # ── 7a. Kiosk-Skript ──────────────────────────────────────────────
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

    # ── 7b. Kiosk-Service ─────────────────────────────────────────────
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

    # ── 7c. X11-Autostart + Desktop-Session ───────────────────────────
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

    if command -v raspi-config &>/dev/null; then
        raspi-config nonint do_boot_behaviour B4 2>/dev/null || true
    fi

    # X11 erzwingen
    mkdir -p /etc/systemd/system/lightdm.service.d/
    cat > /etc/systemd/system/lightdm.service.d/x11.conf << 'X11EOF'
[Service]
Environment=XDG_SESSION_TYPE=x11
X11EOF

    echo "✅ Desktop-Session eingerichtet"

    # ── 7d. boot/config.txt ──────────────────────────────────────────
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

    # ── 7e. Energiesparmodus ─────────────────────────────────────────
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

# ── 8. UFW Firewall ────────────────────────────────────────────────────
echo "🔥 Konfiguriere Firewall..."

ufw --force reset 2>/dev/null || true
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 8000/tcp
ufw allow 67/udp
ufw allow 53/udp
ufw allow 53/tcp
ufw --force enable 2>/dev/null || true
echo "✅ Firewall konfiguriert"

# ── 9. Services aktivieren ─────────────────────────────────────────────
echo "🚀 Aktiviere Services..."

systemctl daemon-reload

# Alte Dienste deaktivieren
systemctl disable dhcpcd 2>/dev/null || true
systemctl stop dhcpcd 2>/dev/null || true

# AP-Dienste
systemctl unmask hostapd 2>/dev/null || true
systemctl unmask dnsmasq 2>/dev/null || true
systemctl enable hostapd
systemctl enable dnsmasq

# LHTPi App
systemctl enable ${SERVICE_APP}

# Kiosk (nur im Desktop-Modus)
if [ "$MODE" = "desktop" ]; then
    systemctl enable ${SERVICE_KIOSK}
    systemctl enable lightdm 2>/dev/null || true
fi

# NetworkManager wlan0 entziehen
if command -v nmcli &>/dev/null; then
    nmcli dev set wlan0 managed no 2>/dev/null || true
fi
mkdir -p /etc/NetworkManager/conf.d/
cat > /etc/NetworkManager/conf.d/99-lhtpi-unmanaged.cfg << 'NMEOF'
[keyfile]
unmanaged-devices=interface-name:wlan0
NMEOF

# ── 10. Netzwerk-Tuning ──────────────────────────────────────────────
echo "📶 Optimiere WLAN-Netzwerk..."

# WiFi Powersave deaktivieren
if command -v iw &>/dev/null; then
    iw dev wlan0 set power_save off 2>/dev/null || true
fi

# Dauerhaft via NetworkManager
mkdir -p /etc/NetworkManager/conf.d/
cat > /etc/NetworkManager/conf.d/99-lhtpi-wifi-powersave-off.cfg << 'NMPWR'
[connection]
wifi.powersave = 2
NMPWR

# MSS Clamping (verhindert MTU-Probleme)
if command -v iptables &>/dev/null; then
    iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || true
fi

# systemd-resolved Konflikte vermeiden
if systemctl is-active systemd-resolved &>/dev/null 2>&1; then
    mkdir -p /etc/systemd/resolved.conf.d/
    cat > /etc/systemd/resolved.conf.d/lhtpi.conf << 'RESEOF'
[Resolve]
DNSStubListener=no
RESEOF
fi

echo "✅ Netzwerk-Tuning abgeschlossen"

# ── 11. Fertig ────────────────────────────────────────────────────────
echo ""
echo "================================================"
echo "  ✅ ${PROJECT_NAME} Installation abgeschlossen!"
echo "  Modus: ${MODE}"
echo "================================================"
echo ""
echo "  SSID:     ${AP_SSID}"
echo "  Passwort: ${AP_PASS}"
echo "  Dashboard: http://192.168.4.1:${APP_PORT}"
echo "  Login:     admin / admin"
echo ""
echo "📋 Nach einem Neustart startet:"
echo "   - Flask-App als systemd-Service"
echo "   - Access Point mit SSID '${AP_SSID}'"
if [ "$MODE" = "desktop" ]; then
    echo "   - X11/Openbox-Session"
    echo "   - Chromium im Kioskmodus"
else
    echo "   - (Kein Kiosk – Lite-Modus, Dashboard per Browser)"
fi
echo ""
echo "👉 Starte Neustart in 5 Sekunden..."
echo "================================================"
sleep 5
echo "🔄 Reboot..."
reboot
