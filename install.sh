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

# ── Terminboard (Add-on, zweiter HDMI-Ausgang) ────────────────────────
TERMIN_DIR="/home/pi/lhtpi/terminboard"
TERMIN_PORT="8001"
TERMIN_KIOSK_URL="http://localhost:8001/board/kiosk"
SERVICE_TERMIN_APP="terminboard.service"
SERVICE_TERMIN_KIOSK="terminboard-kiosk.service"
TERMIN_KIOSK_SCRIPT="/home/pi/start_terminboard_kiosk.sh"
TERMIN_KIOSK_LOG="/home/pi/terminboard-kiosk.log"

# ── Installations-Auswahl ─────────────────────────────────────────────
INSTALL_LHTPI=0
INSTALL_TERMIN=0
NO_REBOOT=0

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
        xorg openbox unclutter-xfixes \
        chromium-browser chromium-browser-l10n \
        exfatprogs ntfs-3g dosfstools usbutils
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

# Feste Monitor-Zuordnung: HDMI-1 = primär (LHTPi), HDMI-2 rechts daneben (Terminboard)
xrandr --output HDMI-1 --primary --mode 1920x1080 --pos 0x0 \
       --output HDMI-2 --mode 1920x1080 --right-of HDMI-1 >/dev/null 2>&1 || true

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

# Mauszeiger sofort ausblenden (funktioniert auf X11 + Wayland)
unclutter -idle 0 -root >/dev/null 2>&1 &
mkdir -p /home/pi/.icons
cd /tmp
rm -rf Transparent_Cursor_Theme 2>/dev/null || true
# Nur die benötigte Datei holen – den Transparent-Ordner
mkdir -p /home/pi/.icons/Transparent/cursors
# cursor.theme schreiben
cat > /home/pi/.icons/Transparent/cursor.theme <<'XEOF'
[Icon Theme]
Name=Transparent
Inherits=Transparent
XEOF
# Leere Cursor-Dateien erstellen (1x1 transparent)
# Da das Repo keine Quelldateien hat, erstellen wir echte leere Cursor
for c in X_cursor all-scroll bd_double_arrow bottom_left_corner bottom_right_corner bottom_side bottom_tee cell circle context-menu copy cross crosshair cross_reverse default diamond_cross dnd-ask dnd-copy dnd-link dnd-move dnd-none dotbox double_arrow e-resize ew-resize fd_double_arrow fleur grab grabbing hand hand1 hand2 hand2 help ibeam left_ptr left_ptr_watch left_side left_tee link ll_angle lr_angle move n-resize ne-resize nesw-resize no-drop not-allowed ns-resize nw-resize nwse-resize pencil pirate pointer plus question_arrow right_ptr right_side right_tee row-resize s-resize se-resize sw-resize target tcross text top_left_arrow top_side top_tee ul_angle ur_angle v_double_arrow wait watch w-resize xterm zoom-in zoom-out; do
  touch "/home/pi/.icons/Transparent/cursors/$c"
done
# 3. Als Systemdefault setzen
mkdir -p /home/pi/.icons/default
cat > /home/pi/.icons/default/index.theme <<'XEOF'
[Icon Theme]
Name=Default
Comment=Transparent Cursor Theme
Inherits=Transparent
XEOF
# 4. XDG-Umgebungsvariable setzen (für Wayland-Anwendungen)
export XCURSOR_THEME=Transparent
export XCURSOR_SIZE=1
# 5. labwc zwingen, das Theme zu laden + Cursor komplett aus
mkdir -p /home/pi/.config/labwc
cat > /home/pi/.config/labwc/rc.xml <<'LABWC_EOF'
<?xml version="1.0"?>
<labwc_config>
  <theme>
    <name>Transparent</name>
    <cornerRadius>0</cornerRadius>
  </theme>
  <mouse>
    <theme>
      <name>Transparent</name>
      <size>1</size>
    </theme>
  </mouse>
</labwc_config>
LABWC_EOF
# 6. Vorhandene Cursor-Root-Setups
xsetroot -bitmap /home/pi/.icons/blank.xbm -fg black -bg black >/dev/null 2>&1 || true
# 7. Chrome Extension für Kiosk-Cursor ausblenden (zusätzliche Sicherheit)
mkdir -p /home/pi/.config/chromium/Default/Extensions/hidecursor/1.0
cat > /home/pi/.config/chromium/Default/Extensions/hidecursor/1.0/manifest.json <<'CE_EOF'
{
"name": "Hide Cursor",
"version": "1.0",
"manifest_version": 2,
"description": "Blendet den Mauszeiger im Kiosk-Modus aus",
"content_scripts": [{
"matches": ["<all_urls>"],
"css": ["hide-cursor.css"],
"run_at": "document_start",
"all_frames": true
}],
"web_accessible_resources": ["hide-cursor.css"]
}
CE_EOF
cat > /home/pi/.config/chromium/Default/Extensions/hidecursor/1.0/hide-cursor.css <<'CE_EOF'
* { cursor: none !important; }
html { cursor: none !important; }
:root { cursor: none !important; }
CE_EOF

# Extension automatisch laden per Preferences
mkdir -p /home/pi/.config/chromium/Default
cat > /home/pi/.config/chromium/Default/Preferences <<'CE_EOF'
{
"extensions": {
"settings": {
  "hidecursor": {
    "toolbar": false,
    "location": 1,
    "ack_external": true
  }
}
},
"browser": {
"show_cursor": false
}
}
CE_EOF

CHROMIUM="/usr/bin/chromium-browser"
[ -x "$CHROMIUM" ] || CHROMIUM="/usr/bin/chromium"

exec "$CHROMIUM" \
    --app="$APP_URL" \
    --class=lhtpi-kiosk \
    --window-position=0,0 \
    --window-size=1920,1080 \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-features=Translate,TranslateUI \
    --no-first-run \
    --check-for-update-interval=31536000 \
    --autoplay-policy=no-user-gesture-required \
    --disable-popup-blocking \
    --disable-translate \
    --overscroll-history-navigation=0 \
    --disable-pinch \
    --disable-context-menu \
    --password-store=basic \
    --touch-events=disabled \
    --simulate-outdated-no-au='01-01-2200' \
    --disable-component-update \
    --lang=de \
    --force-fieldtrials="*Translate/Disabled/" \
    --disable-gpu \
    --disable-gpu-compositing \
    --load-extension=/home/pi/.config/chromium/Default/Extensions/hidecursor/1.0 \
    "$APP_URL" >> "$LOG" 2>&1
EOF
    chmod +x "${KIOSK_SCRIPT}"
    chown "${PI_USER}:${PI_GROUP}" "${KIOSK_SCRIPT}"
    chown -R "${PI_USER}:${PI_GROUP}" /home/pi/.config/chromium
    ok "Chrome Extension 'Hide Cursor' installiert und aktiviert"

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
Environment=XCURSOR_THEME=Transparent
Environment=XCURSOR_SIZE=1
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

    # Openbox-Konfiguration: unsichtbarer Cursor + kein Dekor
    mkdir -p "/home/${PI_USER}/.config/openbox"
    cat > "/home/${PI_USER}/.config/openbox/rc.xml" <<'EOF'
<?xml version="1.0"?>
<openbox_config>
  <mouse>
    <theme>
      <name>X_cursor</name>
    </theme>
  </mouse>
  <resistance>
    <move>0</move>
  </resistance>
  <applications>
    <application class="lhtpi-kiosk"><monitor>1</monitor><decor>no</decor><maximized>yes</maximized></application>
    <application class="terminboard-kiosk"><monitor>2</monitor><decor>no</decor><maximized>yes</maximized></application>
    <application name="LHTPi*"><monitor>1</monitor><decor>no</decor><maximized>yes</maximized></application>
    <application name="Terminboard*"><monitor>2</monitor><decor>no</decor><maximized>yes</maximized></application>
  </applications>
</openbox_config>
EOF
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

configure_policies() {
    log "Erstelle Chromium-Policy: Translate komplett deaktivieren"

    mkdir -p /etc/chromium/policies/managed /etc/chromium/policies/recommended

    cat > /etc/chromium/policies/managed/lhtpi-translate-off.json <<'EOF'
{
  "TranslateEnabled": false
}
EOF

    cat > /etc/chromium/policies/recommended/lhtpi-translate-off.json <<'EOF'
{
  "TranslateEnabled": false
}
EOF

    # Password-Manager deaktivieren (Schlüsselbund-Dialog)
    cat > /etc/chromium/policies/managed/lhtpi-nopassword.json <<'EOF'
{
  "PasswordManagerEnabled": false,
  "AutoFillEnabled": false
}
EOF

    ok "Chromium-Policies gesetzt: Translate + PasswordManager deaktiviert"
}

configure_firewall() {
    log "Konfiguriere Firewall (UFW)"
    ufw --force reset 2>/dev/null || true
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    if [ "$INSTALL_LHTPI" = "1" ]; then
        ufw allow "${APP_PORT}/tcp"
    fi
    if [ "$INSTALL_TERMIN" = "1" ]; then
        ufw allow "${TERMIN_PORT}/tcp"
    fi
    ufw --force enable
    ok "Firewall aktiv: SSH + freigegebene App-Ports"
}

configure_usb_automount() {
    log "Richte gemeinsamen USB-Auto-Mount ein (slides/ + termine.csv)"

    mkdir -p /mnt/lhtpi-usb

    # Mount-Helfer: mountet einen eingesteckten Stick nach /mnt/lhtpi-usb.
    # Read-only, damit ein Herausziehen des Sticks keine Daten beschädigt.
    cat > /usr/local/bin/lhtpi-usb-mount.sh <<'EOF'
#!/bin/bash
# LHTPi: USB-Stick nach /mnt/lhtpi-usb mounten (read-only, weltlesbar).
# Aufruf: lhtpi-usb-mount.sh <device>   (z. B. /dev/sda1)
set -u
dev="${1:-}"
[ -n "$dev" ] || exit 0

mkdir -p /mnt/lhtpi-usb
# Verwaisten/alten Mount lösen, damit ein neuer Stick sauber mounted
if mountpoint -q /mnt/lhtpi-usb; then
    umount -l /mnt/lhtpi-usb 2>/dev/null || true
fi
# Read-only mounten (exFAT/FAT32/NTFS per Auto-Detect, mit explizitem Fallback)
mount "$dev" /mnt/lhtpi-usb -o ro,umask=022 2>/dev/null \
    || mount "$dev" /mnt/lhtpi-usb -o ro,umask=022 -t vfat 2>/dev/null \
    || mount "$dev" /mnt/lhtpi-usb -o ro,umask=022 -t exfat 2>/dev/null \
    || true
exit 0
EOF
    chmod +x /usr/local/bin/lhtpi-usb-mount.sh

    # udev-Regel: bei eingestecktem USB-Laufwerk den Helfer per systemd-run starten.
    # systemd-run verlässt die udev-Sandbox, damit `mount` zuverlässig funktioniert.
    cat > /etc/udev/rules.d/99-lhtpi-usb.rules <<'EOF'
ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_USAGE}=="filesystem", ENV{ID_BUS}=="usb", RUN+="/usr/bin/systemd-run --no-block --on-active=2 /usr/local/bin/lhtpi-usb-mount.sh $env{DEVNAME}"
ACTION=="remove", SUBSYSTEM=="block", ENV{ID_FS_USAGE}=="filesystem", ENV{ID_BUS}=="usb", RUN+="/usr/bin/systemd-run --no-block /bin/umount -l /mnt/lhtpi-usb"
EOF

    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger --subsystem-match=block 2>/dev/null || true

    ok "USB-Auto-Mount eingerichtet (exFAT/FAT32/NTFS, read-only nach /mnt/lhtpi-usb)"
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
    echo "  💾 USB-Stick: Ordner 'slides/' im Stick-Root anlegen und einstecken –"
    echo "     wird automatisch abgespielt (Vorrang vor der Web-Playlist)."
    echo ""
    echo "  ⚠️  Wichtig: DHCP-Reservierung im Router für den Pi einrichten,"
    echo "     damit die LAN-IP stabil bleibt."
    echo "-----------------------------------------------"
    echo ""
    if [ "$INSTALL_TERMIN" = "1" ]; then
        echo "  🌐 Terminboard:  http://192.168.4.1:${TERMIN_PORT}  (admin / admin)"
        echo "  📺 HDMI-1:       Terminboard-Kiosk"
    fi
    if [ "$NO_REBOOT" = "1" ]; then
        echo ""
        echo "  ⚠️  --no-reboot gesetzt: kein automatischer Neustart."
        echo "      Bitte manuell neu starten, damit die Kiosks erscheinen."
    else
        echo "👉 Neustart in 5 Sekunden..."
        sleep 5
        echo "🔄 Reboot..."
        reboot
    fi
}

# ── Auswahl ───────────────────────────────────────────────────────────

select_components() {
    local choice="${1:-}"
    if [ -z "$choice" ]; then
        echo ""
        echo "  Was möchtest du installieren?"
        echo "    1) Nur LHTPi (Präsentations-Player)"
        echo "    2) Nur Terminboard (Anzeigetafel)"
        echo "    3) Beides (LHTPi + Terminboard)"
        printf "  Auswahl (1/2/3): "
        read -r choice
    fi
    case "$choice" in
        1) INSTALL_LHTPI=1; INSTALL_TERMIN=0 ;;
        2) INSTALL_LHTPI=0; INSTALL_TERMIN=1 ;;
        3) INSTALL_LHTPI=1; INSTALL_TERMIN=1 ;;
        *) fail "Ungültige Auswahl '$choice'. Erlaubt: 1, 2, 3" ;;
    esac
}

# ── Terminboard (Add-on) ─────────────────────────────────────────────

prepare_termin() {
    log "Richte Terminboard unter ${TERMIN_DIR} ein"
    mkdir -p "${TERMIN_DIR}"
    local term_src="${SCRIPT_DIR}/terminboard"
    if [ ! -d "${term_src}" ]; then
        fail "Terminboard-Ordner ${term_src} nicht gefunden (Branch feature/terminboard nötig)"
    fi
    if [ "${term_src}" != "${TERMIN_DIR}" ]; then
        for f in "${term_src}"/*; do
            [ -f "$f" ] && cp "$f" "${TERMIN_DIR}/" 2>/dev/null || true
        done
        for d in templates static tests; do
            [ -d "${term_src}/${d}" ] && cp -r "${term_src}/${d}" "${TERMIN_DIR}/" 2>/dev/null || true
        done
    fi
    if [ ! -f "${TERMIN_DIR}/requirements.txt" ]; then
        fail "${TERMIN_DIR}/requirements.txt fehlt."
    fi
    chown -R "${PI_USER}:${PI_GROUP}" "${TERMIN_DIR}"
    ok "Terminboard-Verzeichnis bereit"
}

setup_termin_python() {
    log "Erstelle Terminboard-Virtualenv"
    cd "${TERMIN_DIR}"
    sudo -u "${PI_USER}" python3 -m venv venv
    sudo -u "${PI_USER}" "${TERMIN_DIR}/venv/bin/python" -m pip install --upgrade pip -q
    sudo -u "${PI_USER}" "${TERMIN_DIR}/venv/bin/pip" install -r requirements.txt -q
    chown -R "${PI_USER}:${PI_GROUP}" "${TERMIN_DIR}"
    ok "Terminboard-Python-Umgebung fertig"
}

configure_terminboard() {
    log "Erstelle Terminboard-Systemd-Service"
    local secret
    secret="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 48 || true)"
    [ -n "${secret}" ] || secret="terminboard-change-me-$(date +%s)"

    cat > "/etc/systemd/system/${SERVICE_TERMIN_APP}" <<EOF
[Unit]
Description=Terminboard - Flask Web-App
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${PI_USER}
Group=${PI_GROUP}
WorkingDirectory=${TERMIN_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=TERMINBOARD_HOST=0.0.0.0
Environment=TERMINBOARD_PORT=${TERMIN_PORT}
Environment=TERMINBOARD_SECRET=${secret}
ExecStart=${TERMIN_DIR}/venv/bin/python ${TERMIN_DIR}/app.py
Restart=always
RestartSec=5
StartLimitIntervalSec=120
StartLimitBurst=5

[Install]
WantedBy=multi-user.target
EOF

    log "Erstelle Terminboard-Kiosk-Skript ${TERMIN_KIOSK_SCRIPT}"
    cat > "${TERMIN_KIOSK_SCRIPT}" <<'EOF'
#!/bin/bash
set -u

# Feste Monitor-Zuordnung: HDMI-1 = primär (LHTPi), HDMI-2 rechts daneben (Terminboard)
xrandr --output HDMI-1 --primary --mode 1920x1080 --pos 0x0 \
       --output HDMI-2 --mode 1920x1080 --right-of HDMI-1 >/dev/null 2>&1 || true

LOG="/home/pi/terminboard-kiosk.log"
APP_URL="http://localhost:8001/board/kiosk"
READY_URL="http://localhost:8001/login"
# Position + Größe des zweiten Monitors dynamisch aus der xrandr-Geometrie ermitteln.
SCREEN1_W=$(xrandr --current 2>/dev/null | awk '$1=="HDMI-1" && $2=="connected"{for(i=1;i<=NF;i++) if($i ~ /^[0-9]+x[0-9]+/){split($i,a,"[x+]"); print a[1]; exit}}')
SCREEN2_W=$(xrandr --current 2>/dev/null | awk '$1=="HDMI-2" && $2=="connected"{for(i=1;i<=NF;i++) if($i ~ /^[0-9]+x[0-9]+/){split($i,a,"[x+]"); print a[1]; exit}}')
SCREEN2_H=$(xrandr --current 2>/dev/null | awk '$1=="HDMI-2" && $2=="connected"{for(i=1;i<=NF;i++) if($i ~ /^[0-9]+x[0-9]+/){split($i,a,"[x+]"); print a[2]; exit}}')
SCREEN2_X="${SCREEN1_W:-1920}"
SCREEN2_Y="0"
SCREEN2_W="${SCREEN2_W:-1920}"
SCREEN2_H="${SCREEN2_H:-1080}"
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
    --app="$APP_URL" \
    --class=terminboard-kiosk \
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
    chmod +x "${TERMIN_KIOSK_SCRIPT}"
    chown "${PI_USER}:${PI_GROUP}" "${TERMIN_KIOSK_SCRIPT}"

    log "Erstelle Terminboard-Kiosk-Service"
    cat > "/etc/systemd/system/${SERVICE_TERMIN_KIOSK}" <<EOF
[Unit]
Description=Terminboard - HDMI Chromium Kiosk (zweiter Monitor)
After=graphical.target ${SERVICE_TERMIN_APP}
Requires=${SERVICE_TERMIN_APP}

[Service]
Type=simple
User=${PI_USER}
Group=${PI_GROUP}
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/${PI_USER}/.Xauthority
ExecStartPre=/bin/sleep 5
ExecStart=${TERMIN_KIOSK_SCRIPT}
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=120
StartLimitBurst=3

[Install]
WantedBy=graphical.target
EOF

    systemctl enable "${SERVICE_TERMIN_APP}" "${SERVICE_TERMIN_KIOSK}"
    ok "Terminboard-Services aktiviert"
}

# ── Hauptprogramm ──────────────────────────────────────────────────────
main() {
    echo "================================================"
    echo "  ${PROJECT_NAME} + Terminboard Installation"
    echo "  Raspberry Pi OS Desktop (Trixie)"
    echo "================================================"

    require_root
    require_desktop_target
    ensure_pi_user

    # Auswahl: 1) LHTPi  2) Terminboard  3) Beides  (optional als Argument)
    local selection=""
    for arg in "$@"; do
        case "$arg" in
            --no-reboot) NO_REBOOT=1 ;;
            1|2|3) selection="$arg" ;;
        esac
    done
    select_components "$selection"

    install_packages
    if [ "$INSTALL_LHTPI" = "1" ]; then
        prepare_project
        setup_python
    fi
    if [ "$INSTALL_TERMIN" = "1" ]; then
        prepare_termin
        setup_termin_python
    fi
    backup_configs
    configure_network
    if [ "$INSTALL_LHTPI" = "1" ]; then
        configure_services
    fi
    if [ "$INSTALL_TERMIN" = "1" ]; then
        configure_terminboard
    fi
    configure_desktop
    configure_policies
    configure_firewall
    configure_usb_automount
    print_summary
}

main "$@"
