#!/usr/bin/env bash
#
# Safety Cross – Ein-Run-Setup für Raspberry Pi (Raspberry Pi OS Desktop, 32-/64-bit)
#
#   sudo bash install.sh
#
# Richtet ein: Python-venv + Flask-App, SQLite-DB (admin/admin),
# Hardware-Lizenz (Pi-Seriennummer + HMAC), Kiosk (Chromium fullscreen,
# Mauszeiger via CSS ausgeblendet), die Uhr und das Screen-Blanking:
#   - DS3231-RTC, WENN vorhanden (echte Hardware-Uhr, offline korrekt)
#   - sonst fake-hwclock (Zeit übersteht Reboot/Stromausfall bestmöglich)
#   - Bildschirm-Abschalten (Idle/DPMS) aus -> Daueranzeige (Wayfire + labwc + X11)
#
# Idempotent: kann gefahrlos mehrfach laufen.
#
set -Eeuo pipefail

APP_DIR=/opt/safety-cross
APP_PORT=8002
LICENSE_FILE="$APP_DIR/license.key"
USER="${SUDO_USER:-pi}"
CONFIG=""
if [ -f /boot/firmware/config.txt ]; then CONFIG=/boot/firmware/config.txt; else CONFIG=/boot/config.txt; fi
CHROME="$(command -v chromium || command -v chromium-browser || echo /usr/bin/chromium)"

log()  { echo -e "\033[1;34m[SC]\033[0m $*"; }
ok()   { echo -e "\033[1;32m  ✓\033[0m $*"; }
warn() { echo -e "\033[1;33m  ⚠\033[0m $*"; }
fail() { echo -e "\033[1;31m  ✗ $*\033[0m"; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "Bitte mit sudo ausführen: sudo bash install.sh"

append_line() { # datei zeile
    grep -qxF "$2" "$1" 2>/dev/null || echo "$2" >> "$1"
}

# ---------------------------------------------------------------- Pakete
log "System aktualisieren + Pakete installieren (braucht Internet)"
apt-get update -y
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    chromium chromium-browser i2c-tools util-linux-extra 2>/dev/null \
    || apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip chromium-browser i2c-tools util-linux-extra
ok "Pakete installiert"

# ---------------------------------------------------------------- Uhr (RTC / fake-hwclock)
log "Uhr konfigurieren (RTC, wenn vorhanden, sonst fake-hwclock)"
# I2C aktivieren + DS3231-Overlay (harmlos ohne RTC)
append_line "$CONFIG" "dtparam=i2c_arm=on"
append_line "$CONFIG" "dtoverlay=i2c-rtc,ds3231"
# HDMI-Fallback auf Full-HD (wie LHTPi): auch ohne EDID sicher 1080p
append_line "$CONFIG" "hdmi_force_hotplug=1"
append_line "$CONFIG" "hdmi_group=2"
append_line "$CONFIG" "hdmi_mode=82"

modprobe i2c-dev 2>/dev/null || true
# Robust: /dev/rtc0 existiert nur, wenn eine RTC (DS3231) aktiv ist. i2cdetect ist nur
# Fallback für den Zustand VOR dem ersten Reboot (Treiber noch nicht geladen -> "68"/"UU").
if [ -e /dev/rtc0 ] || i2cdetect -y 1 2>/dev/null | grep -qiE "68|UU"; then
    ok "DS3231-RTC erkannt -> nutze Hardware-Uhr, deaktiviere fake-hwclock"
    systemctl disable fake-hwclock 2>/dev/null || true
    systemctl stop fake-hwclock 2>/dev/null || true
    # Systemzeit einmal in die RTC schreiben (falls frisch gesteckt):
    hwclock -w 2>/dev/null || true
else
    warn "Keine DS3231-RTC erkannt -> nutze fake-hwclock (Zeit übersteht Reboot)"
    systemctl enable fake-hwclock 2>/dev/null || true
fi
timedatectl set-timezone Europe/Berlin 2>/dev/null || true
ok "Uhr konfiguriert"

# ---------------------------------------------------------------- Desktop-Autologin (Kiosk)
log "Desktop-Autologin aktivieren (Standard-Session, kein X11-Zwang)"

# Aufräumen: evtl. alte X11/Openbox-Konfiguration einer früheren Version entfernen
rm -f /etc/lightdm/lightdm.conf.d/50-safetycross-autologin.conf
if [ -d /usr/share/wayland-sessions/disabled ]; then
    for f in /usr/share/wayland-sessions/disabled/*.desktop; do
        [ -f "$f" ] && mv "$f" /usr/share/wayland-sessions/ 2>/dev/null || true
    done
    rmdir /usr/share/wayland-sessions/disabled 2>/dev/null || true
fi

raspi-config nonint do_boot_behaviour B4 2>/dev/null || true
# do_blanking 1 = Screen-Blanking AUS (Konsolen-Blanking + Xorg-DPMS deaktivieren; 0 würde es aktivieren)
raspi-config nonint do_blanking 1 2>/dev/null || true

# Chromium-Policy: Übersetzer komplett deaktivieren
mkdir -p /etc/chromium/policies/managed
cat > /etc/chromium/policies/managed/safetycross-translate-off.json <<'XEOF'
{"TranslateEnabled": false}
XEOF

# zram-Swap: komprimierter RAM-Swap statt SD-Karten-Swapping
# (wichtig auf dem 1-GB-Pi 3 B — verhindert Ruckeln durch langsames SD-Swap)
apt-get install -y --no-install-recommends zram-tools 2>/dev/null || true
systemctl enable zramswap 2>/dev/null || true
systemctl restart zramswap 2>/dev/null || true

systemctl set-default graphical.target
ok "Autologin + Screen-Blanking-Off + zram + Translate-Off konfiguriert"

# ---------------------------------------------------------------- Screen-Blanking deaktivieren
log "Bildschirm-Abschalten deaktivieren (Wayfire / labwc / X11)"

# Ziel-User-Home ermitteln (Skript läuft als root via sudo)
HOME_DIR="$(getent passwd "$USER" | cut -d: -f6)"
[ -n "$HOME_DIR" ] && [ -d "$HOME_DIR" ] || HOME_DIR="/home/$USER"

# --- Wayfire (Bookworm-Standard): Idle/DPMS nie abschalten ---
WF_INI="$HOME_DIR/.config/wayfire.ini"
if command -v wayfire >/dev/null 2>&1 || [ -f /usr/share/wayland-sessions/wayfire.desktop ]; then
    mkdir -p "$(dirname "$WF_INI")"
    if [ ! -f "$WF_INI" ]; then
        if [ -f /etc/wayfire.ini ]; then
            cp /etc/wayfire.ini "$WF_INI"
        else
            : > "$WF_INI"
        fi
    fi
    if grep -q '^\[idle\]' "$WF_INI" 2>/dev/null; then
        if grep -q '^[[:space:]]*screensaver_timeout' "$WF_INI"; then
            sed -i 's/^[[:space:]]*screensaver_timeout.*/screensaver_timeout = -1/' "$WF_INI"
        else
            sed -i '/^\[idle\]/a screensaver_timeout = -1' "$WF_INI"
        fi
        if grep -q '^[[:space:]]*dpms_timeout' "$WF_INI"; then
            sed -i 's/^[[:space:]]*dpms_timeout.*/dpms_timeout = -1/' "$WF_INI"
        else
            sed -i '/^\[idle\]/a dpms_timeout = -1' "$WF_INI"
        fi
    else
        printf '\n[idle]\nscreensaver_timeout = -1\ndpms_timeout = -1\n' >> "$WF_INI"
    fi
    chown "$USER":"$USER" "$WF_INI" 2>/dev/null || true
    ok "Wayfire: Idle/DPMS deaktiviert"
fi

# --- labwc (neuere Bookworm): swayidle-Zeile auskommentieren ---
LABWC_AUTO="$HOME_DIR/.config/labwc/autostart"
if command -v labwc >/dev/null 2>&1 || [ -f /usr/share/wayland-sessions/labwc.desktop ]; then
    mkdir -p "$(dirname "$LABWC_AUTO")"
    if [ ! -f "$LABWC_AUTO" ] && [ -f /etc/xdg/labwc/autostart ]; then
        cp /etc/xdg/labwc/autostart "$LABWC_AUTO"
    fi
    if [ -f "$LABWC_AUTO" ]; then
        sed -i '/swayidle/s/^/#/' "$LABWC_AUTO"
        chown "$USER":"$USER" "$LABWC_AUTO" 2>/dev/null || true
        ok "labwc: swayidle (Blanking) deaktiviert"
    fi
fi

# --- X11 (Fallsicherung): DPMS/Screensaver aus ---
if command -v xset >/dev/null 2>&1; then
    XAUTO="$HOME_DIR/.config/lxsession/LXDE-pi/autostart"
    mkdir -p "$(dirname "$XAUTO")"
    append_line "$XAUTO" "@xset s off"
    append_line "$XAUTO" "@xset -dpms"
    append_line "$XAUTO" "@xset s noblank"
    chown "$USER":"$USER" "$XAUTO" 2>/dev/null || true
    ok "X11: DPMS/Screensaver deaktiviert (Fallsicherung)"
fi

# ---------------------------------------------------------------- App installieren
log "App nach $APP_DIR installieren"
mkdir -p "$APP_DIR"
for f in app.py db.py auth.py license.py requirements.txt; do
    cp "$(dirname "$0")/$f" "$APP_DIR/"
done
cp -r "$(dirname "$0")/templates" "$APP_DIR/"
cp -r "$(dirname "$0")/static" "$APP_DIR/"

python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip -q
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
ok "venv + Abhängigkeiten"

# DB initialisieren (admin/admin)
"$APP_DIR/venv/bin/python" -c "import db, auth; db.init_db(); auth.init_admin_password('admin'); print('DB ok')"
ok "SQLite-DB initialisiert (Login admin/admin)"

# ---------------------------------------------------------------- Lizenz
log "Hardware-Lizenz generieren (Pi-Seriennummer + HMAC)"
SECRET_FILE="$APP_DIR/.secret"
# Secret-Quelle (Priorität): 1) SAFETY_SECRET env, 2) /boot/safety-secret.txt, 3) zufällig
if [ -n "${SAFETY_SECRET:-}" ]; then
    printf '%s' "$SAFETY_SECRET" > "$SECRET_FILE"
    chmod 600 "$SECRET_FILE"
    ok "Secret aus SAFETY_SECRET übernommen"
elif [ -f /boot/safety-secret.txt ]; then
    cp /boot/safety-secret.txt "$SECRET_FILE"
    chmod 600 "$SECRET_FILE"
    ok "Secret aus /boot/safety-secret.txt übernommen"
elif [ -f /boot/firmware/safety-secret.txt ]; then
    cp /boot/firmware/safety-secret.txt "$SECRET_FILE"
    chmod 600 "$SECRET_FILE"
    ok "Secret aus /boot/firmware/safety-secret.txt übernommen"
elif [ -f "$SECRET_FILE" ]; then
    ok "Vorhandenes Secret wird weiterverwendet"
else
    head -c 32 /dev/urandom | base64 > "$SECRET_FILE"
    chmod 600 "$SECRET_FILE"
    warn "Zufälliges Secret erzeugt (Basis-Schutz: verhindert SD-Karten-Kopie)."
    warn "Für echten Schutz: SAFETY_SECRET/Datei nutzen und das Secret NUR bei dir aufbewahren."
fi
# Key über license.py erzeugen (eine Quelle der Wahrheit)
if "$APP_DIR/venv/bin/python" "$APP_DIR/license.py" --make-key >/dev/null 2>&1; then
    ok "Lizenz-Key geschrieben (gebunden an die Seriennummer dieses Pi)"
else
    warn "Lizenz-Key konnte nicht erzeugt werden (kein Pi erkannt?)."
fi

# ---------------------------------------------------------------- Kiosk-Skript
log "Kiosk-Startskript schreiben"
cat > "$APP_DIR/start_kiosk.sh" <<'EOF'
#!/bin/bash
APP_URL="http://127.0.0.1:8002"
LOG="/opt/safety-cross/kiosk.log"
echo "$(date) - Kiosk startet" >> "$LOG"

# Warte, bis die Web-App erreichbar ist (max. 60 s)
for i in $(seq 1 30); do
    if curl -s -o /dev/null --connect-timeout 2 "$APP_URL" 2>/dev/null; then
        echo "$(date) - App erreichbar" >> "$LOG"
        break
    fi
    sleep 2
done

# (Auflösung kommt über config.txt hdmi_mode=82; Screen-Blanking via raspi-config do_blanking)
exec chromium-browser \
    --kiosk \
    --class=safety-cross-kiosk \
    --window-position=0,0 \
    --window-size=1920,1080 \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --no-first-run \
    --check-for-update-interval=31536000 \
    --disable-translate \
    --disable-features=Translate,TranslateUI \
    --force-fieldtrials="*Translate/Disabled/" \
    --autoplay-policy=no-user-gesture-required \
    --disable-dev-shm-usage \
    --renderer-process-limit=1 \
    --enable-gpu-rasterization \
    --force-device-scale-factor=2.0 \
    --app="$APP_URL" >> "$LOG" 2>&1
EOF
chmod +x "$APP_DIR/start_kiosk.sh"
# Chromium-Binary im Skript robust machen (chromium-browser vs. chromium)
sed -i "s#exec chromium-browser#exec ${CHROME}#" "$APP_DIR/start_kiosk.sh"
ok "Kiosk-Skript geschrieben"

# ---------------------------------------------------------------- systemd-Services
log "systemd-Services anlegen"

cat > /etc/systemd/system/safety-cross.service <<EOF
[Unit]
Description=Safety Cross Web-App
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python app.py
Restart=always
RestartSec=5
StartLimitIntervalSec=120
StartLimitBurst=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/safety-cross-kiosk.service <<EOF
[Unit]
Description=Safety Cross Kiosk
After=graphical.target safety-cross.service
Requires=safety-cross.service

[Service]
Type=simple
User=$USER
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/$USER/.Xauthority
ExecStartPre=/bin/sleep 5
ExecStart=$APP_DIR/start_kiosk.sh
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=120
StartLimitBurst=3

[Install]
WantedBy=graphical.target
EOF

chown -R "$USER":"$USER" "$APP_DIR"
systemctl daemon-reload
systemctl enable safety-cross.service
systemctl enable safety-cross-kiosk.service
systemctl restart safety-cross.service
ok "Services aktiviert + App gestartet"

# ---------------------------------------------------------------- Passwordless sudo (Admin: Neustart/Herunterfahren)
log "Passwordless sudo für shutdown/reboot einrichten"
SUDOERS_FILE=/etc/sudoers.d/10-safety-cross
cat > "$SUDOERS_FILE" <<EOF
# Safety Cross: Neustart/Herunterfahren ohne Passwort aus der Admin-Oberfläche
$USER ALL=(ALL) NOPASSWD: /sbin/shutdown, /sbin/reboot, /sbin/poweroff, /sbin/halt, /usr/sbin/shutdown, /usr/sbin/reboot, /usr/sbin/poweroff, /usr/sbin/halt
EOF
chown root:root "$SUDOERS_FILE"
chmod 440 "$SUDOERS_FILE"
if visudo -c -f "$SUDOERS_FILE" >/dev/null 2>&1; then
    ok "Passwordless sudo für shutdown/reboot eingerichtet"
else
    warn "sudoers-Datei ungültig -> entferne sie wieder (kein Schaden)"
    rm -f "$SUDOERS_FILE"
fi

# ---------------------------------------------------------------- Fertig
echo
log "Fertig!"
echo "  Web-App:  http://127.0.0.1:$APP_PORT"
echo "  Admin:    http://127.0.0.1:$APP_PORT/admin  (Login admin/admin)"
echo "  Lizenz:   $LICENSE_FILE (an diesen Pi gebunden)"
echo "  Uhr:      DS3231-RTC (falls vorhanden), sonst fake-hwclock"
echo "  Hinweis:  Ein Reboot ist nötig, damit RTC/I2C + Kiosk voll greifen:"
echo "            sudo reboot"
