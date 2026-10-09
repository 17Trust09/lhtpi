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
# Kein WLAN-Access-Point: die Anzeige läuft ohne Netzwerk (alles über localhost).
KIOSK_URL="http://localhost:8000/present/kiosk"
SERVICE_APP="lhtpi.service"
SERVICE_LICENSE="lhtpi-lizenz-import"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="/root/lhtpi-backup-$(date +%Y%m%d%H%M%S)"

# ── Terminboard (zweites Tool) ────────────────────────────────────────
TERMIN_DIR="/home/pi/lhtpi/terminboard"
TERMIN_PORT="8001"
TERMIN_KIOSK_URL="http://localhost:8001/board/kiosk"
SERVICE_TERMIN_APP="terminboard.service"

# ── Safety Cross (drittes Tool) ───────────────────────────────────────
SC_DIR="/opt/safety-cross"
SC_PORT="8002"
SERVICE_SC_APP="safetycross.service"

# ── Bundle: gemeinsame Anzeige – EIN Kiosk je Bildschirm ──────────────
ROUTER_BASE_URL="http://localhost:${APP_PORT}/screen"
# Überschreibbar über Umgebungsvariablen (wie in der App) - so lassen sich die
# Schritte auch ohne /etc testen.
LIGHTDM_DIR="${LHTPI_LIGHTDM_DIR:-/etc/lightdm}"
UNIT_DIR="${LHTPI_UNIT_DIR:-/etc/systemd/system}"
PI_HOME="${LHTPI_PI_HOME:-/home/${PI_USER}}"
LIGHTDM_CONF="${LHTPI_LIGHTDM_CONF:-${LIGHTDM_DIR}/lightdm.conf}"
TOOLS_FILE="${LHTPI_TOOLS_FILE:-/etc/lhtpi/tools}"
SCREENS_FILE="${LHTPI_SCREENS_FILE:-/etc/lhtpi/screens}"
LICENSE_FILE="${LHTPI_LICENSE_FILE:-/etc/lhtpi/license.key}"
MARKER_FILE="${LHTPI_INSTALLED_MARKER:-/etc/lhtpi/installed}"
MAX_SCREENS="2"
# Merkmal: Bildschirm 2 ist eingerichtet (steuert den zweiten Kiosk)
SCREEN2_FILE="${LHTPI_SCREEN2_FILE:-/etc/lhtpi/screen2}"

# ── Installations-Auswahl ─────────────────────────────────────────────
# Die Verteiler-App (LHTPi, Port 8000) trägt Dashboard, Anzeige-Router und
# Lizenz und ist deshalb IMMER installiert. Die Auswahl bestimmt, welche Tools
# zusätzlich installiert und angezeigt werden dürfen.
TOOL_SLIDESHOW=0     # Folien / Playlist  (Teil der Verteiler-App)
TOOL_TERMIN=0        # Terminboard          (Port 8001)
TOOL_SC=0            # Safety Cross         (Port 8002)
SCREEN_COUNT="1"     # 1 oder 2 HDMI-Ausgänge
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



# ── Installationsschritte ──────────────────────────────────────────────

install_packages() {
    log "Installiere Systempakete"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq \
        python3 python3-pip python3-venv \
        ufw curl git \
        xorg openbox \
        chromium-browser chromium-browser-l10n \
        i2c-tools util-linux-extra \
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
    log "  eth0: per DHCP, falls ein Kabel steckt"
    log "  wlan0: bleibt unangetastet - bewusst KEIN Access Point"

    # Altlasten früherer Versionen stilllegen
    log "  Deaktiviere alte AP-Dienste (hostapd/dnsmasq)..."
    systemctl stop hostapd dnsmasq 2>/dev/null || true
    systemctl disable hostapd dnsmasq 2>/dev/null || true
    systemctl mask hostapd dnsmasq 2>/dev/null || true

    # Alten Access Point der früheren Version entfernen
    if command -v nmcli >/dev/null 2>&1 && nmcli -t con show lhtpi-ap &>/dev/null; then
        log "  Entferne alten Access Point 'lhtpi-ap'"
        nmcli con delete lhtpi-ap 2>/dev/null || true
    fi

    if command -v nmcli >/dev/null 2>&1; then
        log "  NetworkManager: WiFi-Powersave aus"
        mkdir -p /etc/NetworkManager/conf.d
        cat > /etc/NetworkManager/conf.d/99-lhtpi-wifi-powersave.conf <<'EOF'
[connection]
wifi.powersave = 2
EOF
        systemctl reload NetworkManager 2>/dev/null || true
    else
        warn "NetworkManager nicht vorhanden - Netzwerk bleibt, wie es ist (kein AP nötig)"
    fi

    ok "Netzwerk: kein Access Point, keine WLAN-Verbindungen verändert"
}

# ── Gemeinsame Anzeige: EIN Chromium-Kiosk je Bildschirm ───────────────
# Jeder Bildschirm zeigt den Anzeige-Router der Verteiler-App
# (http://localhost:8000/screen/<n>). Welche Tools dort laufen und wie lange
# jeder angezeigt wird, wird im Dashboard unter „Anzeigen" eingestellt.

kiosk_service_name() { echo "kiosk-screen$1.service"; }
kiosk_script_path()  { echo "/home/pi/start_kiosk_screen$1.sh"; }
kiosk_log_path()     { echo "/home/pi/kiosk-screen$1.log"; }

# Kiosk-Startskript für einen Bildschirm erzeugen (nach stdout)
render_screen_kiosk_script() {
    local idx="$1" mon="HDMI-1"
    [ "$idx" = "2" ] && mon="HDMI-2"
    sed -e "s|__IDX__|${idx}|g" \
        -e "s|__MON__|${mon}|g" \
        -e "s|__LOG__|$(kiosk_log_path "$idx")|g" \
        -e "s|__APP_URL__|${ROUTER_BASE_URL}/${idx}|g" \
        -e "s|__PORT__|${APP_PORT}|g" <<'KIOSK_EOF'
#!/bin/bash
set -u

# Kiosk Bildschirm __IDX__ – Anzeige-Router der Verteiler-App
# Monitor-Zuordnung: HDMI-1 primär links, HDMI-2 rechts daneben
xrandr --output HDMI-1 --primary --mode 1920x1080 --pos 0x0 \
       --output HDMI-2 --mode 1920x1080 --right-of HDMI-1 >/dev/null 2>&1 || true

LOG="__LOG__"
APP_URL="__APP_URL__"
READY_URL="http://localhost:__PORT__/login"
MON="__MON__"
PROFILE="/home/pi/.config/chromium-screen__IDX__"

mkdir -p "$(dirname "$LOG")" "$PROFILE"
touch "$LOG"
echo "$(date '+%F %T') - Kiosk Bildschirm __IDX__ gestartet, warte auf den Bildschirm" >> "$LOG"

# Ohne Anmeldedienst startet X gleichzeitig - hier kurz warten, bis er da ist
for i in $(seq 1 60); do
    xset q >/dev/null 2>&1 && break
    sleep 1
done

# Geometrie dieses Ausgangs (Breite x Höhe +X+Y) – Fallback 1920x1080
GEO=$(xrandr --current 2>/dev/null | awk -v m="$MON" \
      '$1==m && $2=="connected"{for(i=1;i<=NF;i++) if($i ~ /^[0-9]+x[0-9]+/){print $i; exit}}')
W=$(echo "$GEO" | cut -dx -f1)
REST=$(echo "$GEO" | cut -dx -f2)
H=$(echo "$REST" | cut -d+ -f1)
X=$(echo "$GEO" | cut -d+ -f2)
Y=$(echo "$GEO" | cut -d+ -f3)
W=${W:-1920}; H=${H:-1080}
case "${X:-}" in ''|*[!0-9]*) X=0 ;; esac
case "${Y:-}" in ''|*[!0-9]*) Y=0 ;; esac
# Zweiter Ausgang ohne Position -> rechts neben HDMI-1
if [ "$MON" = "HDMI-2" ] && [ "$X" = "0" ]; then
    X=$(xrandr --current 2>/dev/null | awk \
        '$1=="HDMI-1" && $2=="connected"{for(i=1;i<=NF;i++) if($i ~ /^[0-9]+x[0-9]+/){split($i,a,"x"); print a[1]; exit}}')
    X=${X:-1920}
fi

ready=0
for i in $(seq 1 30); do
    if curl -fsS --connect-timeout 2 --max-time 5 "$READY_URL" >/dev/null 2>&1; then
        ready=1
        echo "$(date '+%F %T') - App erreichbar, starte Chromium" >> "$LOG"
        break
    fi
    echo "$(date '+%F %T') - Versuch $i/30: App noch nicht bereit" >> "$LOG"
    sleep 2
done
[ "$ready" -ne 1 ] && echo "$(date '+%F %T') - App nicht erreichbar, starte Chromium trotzdem" >> "$LOG"

xset s off >/dev/null 2>&1 || true
xset -dpms >/dev/null 2>&1 || true
xset s noblank >/dev/null 2>&1 || true

# Mauszeiger: NICHT auf OS-Ebene ausblenden – das macht die Anzeige selbst
# (tools/kiosk-cursor.js: nach Inaktivität aus, bei Bewegung sofort wieder da).

CHROMIUM="/usr/bin/chromium-browser"
[ -x "$CHROMIUM" ] || CHROMIUM="/usr/bin/chromium"

# Alte Sitzung verwerfen. Sonst stellt Chromium nach einem Neustart zusätzlich
# frühere Tabs wieder her (z. B. die Anzeigen-Seite) - die legen sich dann über
# die Anzeige. Die Anzeige braucht nur ihr eigenes Fenster.
rm -f "$PROFILE/Default/Current Session" "$PROFILE/Default/Current Tabs" \
      "$PROFILE/Default/Last Session" "$PROFILE/Default/Last Tabs" 2>/dev/null || true
rm -rf "$PROFILE/Default/Sessions" 2>/dev/null || true

exec "$CHROMIUM" \
    --app="$APP_URL" \
    --class=kiosk-screen__IDX__ \
    --user-data-dir="$PROFILE" \
    --window-position="${X},${Y}" \
    --window-size="${W},${H}" \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --hide-crash-restore-bubble \
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
    --disable-gpu-compositing >> "$LOG" 2>&1
KIOSK_EOF
}

configure_screen_kiosk() {
    local idx="$1" script service
    script="$(kiosk_script_path "$idx")"
    service="$(kiosk_service_name "$idx")"

    # Bildschirm 1 startet nach der Ersteinrichtung, Bildschirm 2 nur,
    # wenn er bei der Einrichtung gewählt wurde.
    local cond="ConditionPathExists=${MARKER_FILE}"
    if [ "$idx" = "2" ]; then
        cond="ConditionPathExists=${SCREEN2_FILE}"
    fi

    log "Kiosk für Bildschirm ${idx}: ${ROUTER_BASE_URL}/${idx}"
    render_screen_kiosk_script "$idx" > "$script"
    chmod +x "$script"
    chown "${PI_USER}:${PI_GROUP}" "$script"

    cat > "/etc/systemd/system/${service}" <<EOF
[Unit]
Description=Kiosk Bildschirm ${idx} - Anzeige-Router
After=${SERVICE_APP}
Requires=${SERVICE_APP}
# Startet erst, wenn die Einrichtung abgeschlossen ist
${cond}
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
Type=simple
User=${PI_USER}
Group=${PI_GROUP}
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/${PI_USER}/.Xauthority
ExecStartPre=/bin/sleep 5
ExecStart=${script}
Restart=on-failure
RestartSec=10
EOF
    systemctl daemon-reload
    # NICHT beim Booten starten: die Anzeigen-Steuerung startet das Fenster,
    # sobald die Einrichtung abgeschlossen ist - sonst lägen zwei Fenster
    # übereinander (Einrichtungs-Seite und Kiosk).
    systemctl disable "${service}" >/dev/null 2>&1 || true
    ok "Bildschirm ${idx} eingerichtet (${service}, Start über die Anzeige)"
}

configure_screens() {
    local i=1
    while [ "$i" -le "${SCREEN_COUNT}" ]; do
        configure_screen_kiosk "$i"
        i=$((i + 1))
    done
}

# ── Ersteinrichtung: das Gerät fragt beim ersten Booten selbst ─────────────
# Ohne ${MARKER_FILE} startet kein Kiosk, sondern die Anzeigen-Seite des
# Dashboards auf dem Bildschirm - mit Maus und Tastatur einrichten, dann
# "Einrichtung abschließen". Danach übernimmt die Anzeige automatisch.

render_setup_script() {
    sed -e "s|__LOG__|/home/${PI_USER}/setup.log|g" \
        -e "s|__PI_USER__|${PI_USER}|g" \
        -e "s|__APP_URL__|http://localhost:${APP_PORT}/display|g" \
        -e "s|__PORT__|${APP_PORT}|g" <<'SETUP_EOF'
#!/bin/bash
set -u

# Ersteinrichtung - Anzeigen-Seite auf dem ersten angeschlossenen Ausgang
LOG="__LOG__"
SETUP_URL="__APP_URL__"
READY_URL="http://localhost:__PORT__/login"

mkdir -p "$(dirname "$LOG")"
touch "$LOG"
echo "$(date '+%F %T') - Ersteinrichtung gestartet" >> "$LOG"

# Ohne Anmeldedienst startet X gleichzeitig - erst warten, dann Ausgaenge setzen
for i in $(seq 1 60); do
    xset q >/dev/null 2>&1 && break
    sleep 1
done

# Alle angeschlossenen Ausgaenge einschalten, der erste wird primaer
xrandr --auto >/dev/null 2>&1 || true

for i in $(seq 1 30); do
    if curl -fsS --connect-timeout 2 --max-time 5 "$READY_URL" >/dev/null 2>&1; then
        echo "$(date '+%F %T') - App erreichbar" >> "$LOG"
        break
    fi
    sleep 2
done

xset s off >/dev/null 2>&1 || true
exec chromium \
    --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble \
    --no-first-run --disable-features=Translate,MediaRouter \
    --user-data-dir=/home/__PI_USER__/.config/chromium-setup \
    "$SETUP_URL" >> "$LOG" 2>&1
SETUP_EOF
}

render_anzeige_steuerung() {
    cat <<'STEUER_EOF'
#!/bin/bash
# Startet/stoppt die Anzeigen passend zu /etc/lhtpi/screens.
# Wird vom Pfad-Waechter aufgerufen, sobald die Einrichtung speichert oder
# die Bildschirm-Anzahl spaeter geaendert wird.
set -u

# Pfade und Wartezeiten sind überschreibbar (Tests, Werkstatt).
INSTALLED="${LHTPI_INSTALLED:-/etc/lhtpi/installed}"

n="$(cat "${LHTPI_SCREENS:-/etc/lhtpi/screens}" 2>/dev/null || echo 1)"
case "$n" in
    2) n=2 ;;
    *) n=1 ;;
esac

# Ohne abgeschlossene Einrichtung bleibt die Anzeigen-Seite stehen. Sonst
# wäre der Bildschirm schwarz, weil kein Kiosk-Fenster übernimmt (Speichern
# allein darf die Seite nicht wegnehmen).
if [ ! -f "${INSTALLED}" ]; then
    exit 0
fi

systemctl stop lhtpi-setup.service 2>/dev/null || true
systemctl start kiosk-screen1.service 2>/dev/null || true
if [ "$n" -ge 2 ]; then
    systemctl start kiosk-screen2.service 2>/dev/null || true
else
    systemctl stop kiosk-screen2.service 2>/dev/null || true
fi

# Selbstheilung: kommt das Kiosk-Fenster nicht hoch, kommt die Anzeigen-Seite
# zurück - der Schirm bleibt nie schwarz.
for i in $(seq 1 "${LHTPI_STEUER_WARTE:-20}"); do
    zustand="$(systemctl is-active kiosk-screen1.service 2>/dev/null || true)"
    case "$zustand" in
        active|activating|reloading) exit 0 ;;
    esac
    sleep 1
done
echo "$(date '+%F %T') - Kiosk-Fenster kam nicht hoch, versuche es erneut" >> /home/pi/anzeige-steuerung.log
systemctl restart kiosk-screen1.service 2>/dev/null || true
sleep "${LHTPI_STEUER_WARTE2:-8}"
zustand="$(systemctl is-active kiosk-screen1.service 2>/dev/null || true)"
case "$zustand" in
    active|activating|reloading) exit 0 ;;
esac
echo "$(date '+%F %T') - Kiosk startet nicht - Anzeigen-Seite zurueck" >> /home/pi/anzeige-steuerung.log
systemctl start lhtpi-setup.service 2>/dev/null || true
STEUER_EOF
}

configure_setup_mode() {
    log "Ersteinrichtung vorbereiten (die Frage kommt beim ersten Booten)"

    # Die App läuft als ${PI_USER} und muss Bildschirm-Anzahl und Merkmal
    # schreiben dürfen (Zugriffsrechte, kein sudo nötig).
    local cfg_dir
    cfg_dir="$(dirname "${MARKER_FILE}")"
    mkdir -p "${cfg_dir}"
    chown "root:${PI_GROUP}" "${cfg_dir}"
    chmod 775 "${cfg_dir}"
    if [ -f "${TOOLS_FILE}" ]; then
        chown "root:${PI_GROUP}" "${TOOLS_FILE}"
        chmod 664 "${TOOLS_FILE}"
    fi

    local script="/home/${PI_USER}/start_setup.sh"
    render_setup_script > "$script"
    chmod +x "$script"
    chown "${PI_USER}:${PI_GROUP}" "$script"

    cat > /etc/systemd/system/lhtpi-setup.service <<EOF
[Unit]
Description=Ersteinrichtung - Anzeigen-Seite auf dem Bildschirm
After=${SERVICE_APP}
Requires=${SERVICE_APP}
# Immer beim Booten: das Gerät landet auf der Anzeigen-Seite. Ist es schon
# eingerichtet, startet die Anzeige von dort automatisch (Knopf oder Countdown).

[Service]
Type=simple
User=${PI_USER}
Group=${PI_GROUP}
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/${PI_USER}/.Xauthority
ExecStartPre=/bin/sleep 5
ExecStart=${script}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    local steuer="/usr/local/bin/lhtpi-anzeige-steuern.sh"
    render_anzeige_steuerung > "$steuer"
    chmod 755 "$steuer"

    cat > /etc/systemd/system/lhtpi-anzeige.service <<EOF
[Unit]
Description=Anzeigen passend zur Einrichtung starten oder stoppen

[Service]
Type=oneshot
ExecStart=${steuer}
EOF

    cat > /etc/systemd/system/lhtpi-anzeige.path <<EOF
[Unit]
Description=Wacht ueber Einrichtung und Bildschirm-Anzahl
After=${SERVICE_APP}

[Path]
PathExists=${MARKER_FILE}
PathChanged=${SCREENS_FILE}
Unit=lhtpi-anzeige.service

[Install]
WantedBy=paths.target
EOF

    systemctl daemon-reload
    systemctl enable lhtpi-setup.service >/dev/null 2>&1 || true
    systemctl enable --now lhtpi-anzeige.path >/dev/null 2>&1 || true
    ok "Ersteinrichtung bereit: beim ersten Booten erscheint die Anzeigen-Seite"
}

# Kiosk-Services früherer Versionen (ein Kiosk je Tool) entfernen
cleanup_old_kiosks() {
    # Namen früherer Fassungen (ein Kiosk je Tool, teils mit dem Dashboard)
    # Alles, was DIESE Fassung anlegt, muss bleiben - sonst räumt sich die
    # Einrichtung selbst weg (Lizenz-Import, Uhrzeit-Dienst, Anzeige-Einheiten).
    local behalten=" lhtpi.service lhtpi-setup.service lhtpi-anzeige.service lhtpi-anzeige.path \
kiosk-screen1.service kiosk-screen2.service lhtpi-lizenz-import.service \
lhtpi-fake-hwclock.service lhtpi-fake-hwclock-save.service lhtpi-fake-hwclock-save.timer "
    local unit name datei
    for unit in lhtpi-kiosk.service terminboard-kiosk.service safety-cross-kiosk.service; do
        if [ -f "${UNIT_DIR}/${unit}" ]; then
            systemctl disable --now "${unit}" >/dev/null 2>&1 || true
            rm -f "${UNIT_DIR}/${unit}"
            log "  alten Kiosk-Service entfernt: ${unit}"
        fi
    done

    # Alles aus unserem Namensraum, das nicht zur aktuellen Fassung gehört.
    # Fängt alte Kiosk-Einheiten ab, die z. B. das Dashboard auf dem Schirm
    # öffneten - die Anzeige darf nur die Kiosk-Seiten zeigen.
    for datei in "${UNIT_DIR}"/*.service; do
        [ -f "${datei}" ] || continue
        name="$(basename "${datei}")"
        # Nur unser Namensraum. "display-manager.service" gehoert dem System
        # (Anmeldedienst) und darf hier NIE angefasst werden.
        if [ "${name}" = "display-manager.service" ]; then
            continue
        fi
        case "${name}" in
            lhtpi*|*kiosk*|*anzeige*|*dashboard*) ;;
            *) continue ;;
        esac
        case "${behalten}" in
            *" ${name} "*) continue ;;
        esac
        systemctl disable --now "${name}" >/dev/null 2>&1 || true
        rm -f "${datei}"
        log "  alte Einheit entfernt (nicht mehr Teil der Anzeige): ${name}"
    done

    # Startskripte früherer Fassungen (Einrichtung und Anzeige bleiben)
    rm -f /home/pi/start_lhtpi_kiosk.sh /home/pi/start_terminboard_kiosk.sh \
          /home/pi/start_dashboard.sh /home/pi/start_anzeige_kiosk.sh
    systemctl daemon-reload || true
}

# Welche Tools sind auf diesem Gerät aktiv? (Der Anzeige-Router liest das)
# Tool-Kennungen der gewählten Tools (eine pro Zeile)
tools_file_content() {
    [ "$TOOL_SLIDESHOW" = "1" ] && echo slideshow || true
    [ "$TOOL_TERMIN" = "1" ] && echo terminboard || true
    [ "$TOOL_SC" = "1" ] && echo safetycross || true
    return 0
}

# Wie viele Bildschirme hat dieses Gerät? (Startwert für die Anzeige-Einstellungen)
configure_screens_file() {
    mkdir -p "$(dirname "${SCREENS_FILE}")"
    echo "${SCREEN_COUNT}" > "${SCREENS_FILE}"
    chmod 644 "${SCREENS_FILE}"
    ok "Bildschirme: bis ${SCREEN_COUNT} möglich (Auswahl beim ersten Start)"
}

# Hardware-Lizenz hinterlegen (signiert - der private Schlüssel bleibt beim Hersteller).
#
# Auf dem Gerät liegt nur der ÖFFENTLICHE Schlüssel. Eine Lizenz wird deshalb
# mitgeliefert und hier nur übernommen:
#   * --license=/pfad/datei
#   * lizenz.key auf der Boot-Partition der SD-Karte (/boot/firmware/lizenz.key)
#   * lizenz.key im Projektverzeichnis
# Nur auf dem Hersteller-Rechner (LHTPI_SIGN_KEY_FILE gesetzt) wird sie direkt
# erzeugt - dann läuft die Installation in einem Schritt.
LICENSE_STATUS="fehlt"
# Leer vorbelegen: wird nur bei --license=<datei> gefüllt (set -u!)
LICENSE_ARG=""

lizenz_uebernehmen() {
    install -m 644 "$1" "${LICENSE_FILE}" || return 1
    LICENSE_STATUS="übernommen ($1)"
    ok "Lizenz übernommen: $1"
    return 0
}

configure_license() {
    log "Hardware-Lizenz hinterlegen"
    local ordner
    ordner="$(dirname "${LICENSE_FILE}")"
    mkdir -p "${ordner}"
    chown "root:${PI_GROUP}" "${ordner}" 2>/dev/null \
        || warn "Konfigurationsordner ${ordner} gehört weiterhin root (Gruppe ${PI_GROUP} fehlt?)"
    chmod 775 "${ordner}" 2>/dev/null || true

    if [ -n "${LICENSE_ARG}" ]; then
        if [ -f "${LICENSE_ARG}" ] && lizenz_uebernehmen "${LICENSE_ARG}"; then
            return 0
        fi
        warn "Lizenzdatei '${LICENSE_ARG}' nicht gefunden"
    fi

    local quelle
    for quelle in /boot/firmware/lizenz.key /boot/lizenz.key "${PROJECT_DIR}/lizenz.key"; do
        if [ -f "${quelle}" ] && lizenz_uebernehmen "${quelle}"; then
            return 0
        fi
    done

    if [ -f "${LICENSE_FILE}" ]; then
        LICENSE_STATUS="vorhanden (unverändert)"
        ok "Vorhandene Lizenz bleibt erhalten"
        return 0
    fi

    local sign_key="${LHTPI_SIGN_KEY_FILE:-}"
    if [ -n "${sign_key}" ] && [ -f "${sign_key}" ]; then
        local tools_arg
        tools_arg="$(tools_file_content | paste -sd, -)"
        if [ -n "${tools_arg}" ] && "${PROJECT_DIR}/venv/bin/python" \
                "${PROJECT_DIR}/license_bundle.py" --install \
                "--tools=${tools_arg}" "--screens=${SCREEN_COUNT}"; then
            LICENSE_STATUS="erzeugt und hinterlegt"
            ok "Lizenz erzeugt und hinterlegt (${LICENSE_FILE})"
            return 0
        fi
    fi

    warn "Keine Lizenz hinterlegt – die Anzeige bleibt gesperrt."
    warn "Lizenz auf einem anderen Rechner erzeugen:"
    warn "  1) auf dem Pi:   python3 license_bundle.py --info      (Geräte-ID ablesen)"
    warn "  2) herstellen:   python3 license_bundle.py --make-key \\"
    warn "                     --tools=1,2,3 --screens=2 --hwid=<Geräte-ID> > lizenz.key"
    warn "  3) lizenz.key auf die Boot-Partition der SD-Karte legen (oder --license=…)"
}

# Holt eine später gelieferte Lizenz beim Start von der Boot-Partition nach.
configure_license_import() {
    log "Erstelle Dienst zum Nachholen der Lizenz"
    cat > /usr/local/bin/lhtpi-lizenz-import.sh <<'IMPORT_EOF'
#!/bin/bash
# Holt eine mitgelieferte Lizenz von der Boot-Partition (lizenz.key), wenn noch
# keine hinterlegt ist oder sich die Datei geändert hat.
set -u
ZIEL=/etc/lhtpi/license.key
for quelle in /boot/firmware/lizenz.key /boot/lizenz.key; do
    [ -f "$quelle" ] || continue
    if ! cmp -s "$quelle" "$ZIEL" 2>/dev/null; then
        install -m 644 "$quelle" "$ZIEL"
        logger -t lhtpi "Lizenz von $quelle uebernommen"
    fi
done
exit 0
IMPORT_EOF
    chmod 755 /usr/local/bin/lhtpi-lizenz-import.sh

    cat > "/etc/systemd/system/${SERVICE_LICENSE}.service" <<EOF
[Unit]
Description=LHTPi - Lizenz von der Boot-Partition uebernehmen
After=local-fs.target
Before=${SERVICE_APP}

[Service]
Type=oneshot
ExecStart=/usr/local/bin/lhtpi-lizenz-import.sh

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload 2>/dev/null || true
    systemctl enable "${SERVICE_LICENSE}.service" >/dev/null 2>&1 || true
    ok "Lizenz-Dienst eingerichtet (${SERVICE_LICENSE}.service)"
}

configure_tools_file() {
    mkdir -p "$(dirname "${TOOLS_FILE}")"
    tools_file_content > "${TOOLS_FILE}"
    chmod 644 "${TOOLS_FILE}"
    ok "Aktivierte Tools: $(tr '\n' ' ' < "${TOOLS_FILE}")"
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
StartLimitIntervalSec=120
StartLimitBurst=5

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

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "${SERVICE_APP}"
    ok "Verteiler-App installiert und aktiviert (Port ${APP_PORT})"
}

# Automatische Anmeldung: der Kiosk muss ohne Login starten.
#
# Drei Wege, weil die Wirksamkeit je nach Image unterschiedlich ist:
#   1) Werte direkt in lightdm.conf (dort greifen sie unabhaengig von der
#      Reihenfolge der Dateien)
#   2) Drop-in in lightdm.conf.d (bereits in configure_desktop geschrieben)
#   3) das Werkzeug von Raspberry Pi OS (raspi-config)
# Am Ende wird geprueft, was LightDM wirklich verwendet.
# Automatische Anmeldung: der Kiosk muss ohne Anmeldung starten.
#
# Häufigste Ursache für einen Anmeldebildschirm: der Sitzungsname stimmt nicht
# mit dem Image überein - LightDM führt das Autologin dann nicht aus und zeigt
# den Greeter. Deshalb legt der Installer seine EIGENE Sitzung an und räumt
# widersprüchliche Werte in der Konfiguration weg.
# Die Anzeige startet ohne jede Anmeldung.
#
# Weg (so macht es Raspberry Pi OS von Haus aus):
#   1) Anmeldebildschirm (LightDM) abschalten
#   2) tty1 meldet den Benutzer automatisch an (kein Passwort, keine Eingabe)
#   3) X startet bei dieser Anmeldung selbst (startx + openbox, kein Desktop)
#
# Damit gibt es keinen Anmeldebildschirm und keine Passworteingabe.
# Wartung läuft über SSH - dort wird nichts automatisch gestartet.
configure_autologin() {
    log "Anzeige ohne Anmeldung einrichten (kein Anmeldebildschirm)"

    # 1) Grafik-Anmeldung abschalten
    if [ -f "${UNIT_DIR}/display-manager.service" ] \
       || [ -f /lib/systemd/system/lightdm.service ] \
       || [ -f /usr/lib/systemd/system/lightdm.service ]; then
        systemctl disable lightdm.service >/dev/null 2>&1 || true
        systemctl stop lightdm.service >/dev/null 2>&1 || true
        ok "Anmeldebildschirm (LightDM) abgeschaltet"
    else
        log "  Kein LightDM gefunden - nichts abzuschalten"
    fi

    # 2) Automatische Anmeldung auf tty1
    if command -v raspi-config >/dev/null 2>&1; then
        raspi-config nonint do_boot_behaviour B2 >/dev/null 2>&1 \
            && ok "raspi-config: automatische Konsolen-Anmeldung gesetzt" \
            || warn "raspi-config B2 nicht möglich - Übersteuerung wird selbst angelegt"
    fi
    mkdir -p "${UNIT_DIR}/getty@tty1.service.d"
    cat > "${UNIT_DIR}/getty@tty1.service.d/lhtpi-autologin.conf" <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin ${PI_USER} --noclear %I \$TERM
EOF
    ok "tty1 meldet ${PI_USER} automatisch an (keine Eingabe nötig)"

    # 3) Anzeige startet bei dieser Anmeldung (nur tty1, nie bei SSH)
    local profil="${PI_HOME}/.bash_profile"
    mkdir -p "${PI_HOME}"
    touch "${profil}"
    if ! grep -q 'LHTPi-Kiosk' "${profil}" 2>/dev/null; then
        cat >> "${profil}" <<'PROFIL_EOF'

# --- LHTPi-Kiosk: Anzeige automatisch starten (nur auf tty1) ---
if [ -z "${DISPLAY:-}" ] && [ "$(tty)" = "/dev/tty1" ]; then
    exec startx
fi
# --- Ende LHTPi-Kiosk ---
PROFIL_EOF
        ok "Anzeige startet beim Booten automatisch (${profil})"
    else
        ok "Anzeige startet beim Booten automatisch (war schon eingerichtet)"
    fi
    chown "${PI_USER}:${PI_GROUP}" "${profil}" 2>/dev/null || true

    # Zeiger-Wache: blendet den Mauszeiger am X-Server aus, wenn er ruht.
    # Ueber CSS allein geht das nicht - Chromium zeichnet den Zeiger erst beim
    # naechsten Mausereignis neu, er bliebe also bis zum Klick sichtbar.
    # Bewusst nicht unclutter: das blendet den Zeiger dauerhaft aus.
    local zeiger_dir="${PI_HOME}/lhtpi-cursor"
    if [ ! -x "${zeiger_dir}/venv/bin/python" ]; then
        python3 -m venv "${zeiger_dir}/venv" >/dev/null 2>&1 || true
        "${zeiger_dir}/venv/bin/pip" install -q python-xlib >/dev/null 2>&1 || true
    fi
    if [ -x "${zeiger_dir}/venv/bin/python" ] \
       && "${zeiger_dir}/venv/bin/python" -c 'import Xlib' >/dev/null 2>&1; then
        ok "Zeiger-Wache bereit (Zeiger verschwindet bei Ruhe)"
    else
        echo "  ! Zeiger-Wache nicht eingerichtet - der Zeiger bleibt sichtbar"
    fi
    chown -R "${PI_USER}:${PI_GROUP}" "${zeiger_dir}" 2>/dev/null || true

    local xinitrc="${PI_HOME}/.xinitrc"
    if ! grep -q 'openbox-session' "${xinitrc}" 2>/dev/null \
       || ! grep -q 'kiosk-cursor-x11' "${xinitrc}" 2>/dev/null; then
        printf '# LHTPi-Kiosk: X-Sitzung ohne Desktop (kein Panel, keine Anmeldung)\n# Mauszeiger ausblenden, wenn er ruht (CSS allein greift in Chromium nicht)\nif [ -x "%s" ]; then\n    setsid "%s" "%s/tools/kiosk-cursor-x11.py" --ruhe 4 >/dev/null 2>&1 &\nfi\nexec openbox-session\n' \
            "${zeiger_dir}/venv/bin/python" "${zeiger_dir}/venv/bin/python" "${PROJECT_DIR}" \
            > "${xinitrc}"
        ok "X-Sitzung eingerichtet (openbox, ohne Anmeldung, Zeiger-Wache)"
    else
        ok "X-Sitzung eingerichtet (war schon vorhanden)"
    fi
    chown "${PI_USER}:${PI_GROUP}" "${xinitrc}" 2>/dev/null || true

    # 4) Ohne Anmeldebildschirm bleiben wir auf multi-user
    systemctl set-default multi-user.target >/dev/null 2>&1 || true
    if ! command -v startx >/dev/null 2>&1 && ! command -v xinit >/dev/null 2>&1; then
        fail "startx/xinit fehlt - X kann nicht starten (Paket xinit installieren)"
    fi
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

    # Wayland-Sessions für den Kiosk deaktivieren – Chromium-Kiosk
    # und xset brauchen zwingend X11
    if [ -d /usr/share/wayland-sessions ]; then
        mkdir -p /usr/share/wayland-sessions/disabled
        for f in /usr/share/wayland-sessions/*.desktop; do
            [ -f "$f" ] && mv "$f" /usr/share/wayland-sessions/disabled/ 2>/dev/null || true
        done
        log "  Wayland-Sessions deaktiviert (X11 erforderlich für Kiosk)"
    fi

    # Openbox-Konfiguration: normaler Mauszeiger (Ausblenden macht die Seite) + kein Dekor
    mkdir -p "/home/${PI_USER}/.config/openbox"
    cat > "/home/${PI_USER}/.config/openbox/rc.xml" <<'EOF'
<?xml version="1.0"?>
<openbox_config>
  <mouse>
    <theme>
      <name>Adwaita</name>
    </theme>
  </mouse>
  <resistance>
    <move>0</move>
  </resistance>
  <applications>
    <application class="kiosk-screen1"><monitor>1</monitor><decor>no</decor><maximized>yes</maximized></application>
    <application class="kiosk-screen2"><monitor>2</monitor><decor>no</decor><maximized>yes</maximized></application>
    <application name="LHTPi*"><monitor>1</monitor><decor>no</decor><maximized>yes</maximized></application>
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

    # HDMI-Fallback in config.txt
    if [ -f /boot/firmware/config.txt ]; then
        grep -qxF 'hdmi_force_hotplug=1' /boot/firmware/config.txt || echo 'hdmi_force_hotplug=1' >> /boot/firmware/config.txt
        grep -qxF 'hdmi_group=2' /boot/firmware/config.txt || echo 'hdmi_group=2' >> /boot/firmware/config.txt
        grep -qxF 'hdmi_mode=82' /boot/firmware/config.txt || echo 'hdmi_mode=82' >> /boot/firmware/config.txt
    else
        warn "/boot/firmware/config.txt nicht gefunden – HDMI-Fallback nicht gesetzt"
    fi

    systemctl set-default multi-user.target >/dev/null 2>&1 || true
    ok "Autostart ohne Anmeldebildschirm konfiguriert"
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
    # Verteiler-App trägt Dashboard + Anzeige-Router
    ufw allow "${APP_PORT}/tcp"
    if [ "$TOOL_TERMIN" = "1" ]; then
        ufw allow "${TERMIN_PORT}/tcp"
    fi
    if [ "$TOOL_SC" = "1" ]; then
        ufw allow "${SC_PORT}/tcp"
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

configure_clock() {
    log "Richte offline-fähige Uhr ein (mini fake-hwclock, kein RTC/NTP)"

    # Skript: Zeit bei 'load' wiederherstellen, bei 'save' auf Disk schreiben.
    cat > /usr/local/sbin/lhtpi-hwclock <<'EOF'
#!/bin/bash
SAVE=/etc/fake-hwclock.data
case "${1:-}" in
  save) date '+%Y-%m-%d %H:%M:%S' > "$SAVE" ;;
  load) [ -f "$SAVE" ] && date -s "$(cat "$SAVE")" >/dev/null 2>&1 ;;
esac
EOF
    chmod +x /usr/local/sbin/lhtpi-hwclock

    # Boot: Zeit laden (vor time-sync.target, damit NTP sie nicht überschreibt)
    cat > /etc/systemd/system/lhtpi-fake-hwclock.service <<'EOF'
[Unit]
Description=Restore clock from disk (offline Pi, no RTC)
Before=time-sync.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/lhtpi-hwclock load
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
EOF

    # Shutdown: Zeit speichern
    cat > /etc/systemd/system/lhtpi-fake-hwclock-save.service <<'EOF'
[Unit]
Description=Save clock to disk (offline Pi)

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/lhtpi-hwclock save

[Install]
WantedBy=shutdown.target
EOF

    # Alle 15 Minuten speichern
    cat > /etc/systemd/system/lhtpi-fake-hwclock-save.timer <<'EOF'
[Unit]
Description=Save clock every 15 min

[Timer]
OnBootSec=15min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
EOF

    systemctl daemon-reload
    systemctl enable lhtpi-fake-hwclock.service lhtpi-fake-hwclock-save.service lhtpi-fake-hwclock-save.timer
    /usr/local/sbin/lhtpi-hwclock save

    ok "Uhr-Speicherung eingerichtet (Boot=load, Shutdown+15min=save)"
}

print_summary() {
    echo ""
    echo "================================================"
    echo "  ✅ ${PROJECT_NAME} Installation abgeschlossen!"
    echo "================================================"
    echo ""
    echo "  🧩 Tools:         $(tools_file_content | tr '\n' ' ')"
    echo "  📺 Bildschirme:   bis ${SCREEN_COUNT} (Auswahl am Bildschirm)"
    echo "     Anzeige 1:     ${ROUTER_BASE_URL}/1"
    if [ "${SCREEN_COUNT}" = "2" ]; then
        echo "     Anzeige 2:     ${ROUTER_BASE_URL}/2"
    fi
    echo ""
    echo "  🖥  Ersteinrichtung: erscheint beim ersten Booten auf dem Bildschirm"
    echo "     (Maus und Tastatur: Tools und Bildschirme wählen, dann abschließen)"
    echo "  🌐 Dashboard:     http://localhost:${APP_PORT}  (bzw. http://<LAN-IP>:${APP_PORT})"
    echo "  🧭 Anzeigen:      http://<LAN-IP>:${APP_PORT}/display   ← hier einstellen:"
    echo "                     welches Tool welchen Bildschirm nutzt, Dauer je Tool,"
    echo "                     und ob mehrere Tools sich einen Bildschirm teilen."
    echo "  🔑 Login:         admin / admin"
    echo ""
    if [ "$TOOL_TERMIN" = "1" ]; then
        echo "  🗓️  Terminboard:   http://<LAN-IP>:${TERMIN_PORT}  (admin / admin)"
    fi
    if [ "$TOOL_SC" = "1" ]; then
        echo "  ⛑️  Safety Cross:  http://<LAN-IP>:${SC_PORT}  (admin / admin)"
    fi
    echo ""
    echo "  🔗 SSH (LAN): ssh pi@<LAN-IP>"
    echo ""
    echo "  💾 USB-Stick: Ordner 'slides/' im Stick-Root anlegen und einstecken –"
    echo "     wird automatisch abgespielt (Vorrang vor der Web-Playlist)."
    echo ""
    echo "  🔑 Lizenz:        ${LICENSE_STATUS}"
    if [ "${LICENSE_STATUS}" = "fehlt" ]; then
        echo "     ⚠️  Ohne Lizenz bleibt die Anzeige gesperrt – lizenz.key auf die"
        echo "        Boot-Partition legen und neu starten."
    fi
    echo ""
    echo "  🔌 Netzwerk ist optional: die Anzeige läuft vollständig über localhost."
    echo "     Ein LAN-Kabel braucht nur, wer die Seiten von einem anderen"
    echo "     Rechner aufrufen will."
    echo "-----------------------------------------------"
    echo ""
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
    local tools_arg="$1" screens_arg="${2:-}"

    if [ -z "$tools_arg" ]; then
        # Ohne Angabe wird alles installiert. Welche Tools die Anzeige nutzt,
        # wird bei der Ersteinrichtung auf dem Bildschirm gefragt.
        tools_arg="1,2,3"
        log "Tools: alle installieren (Auswahl erfolgt bei der Ersteinrichtung)"
    fi

    TOOL_SLIDESHOW=0; TOOL_TERMIN=0; TOOL_SC=0
    local t
    for t in ${tools_arg//,/ }; do
        case "$t" in
            1|slideshow|folien)                TOOL_SLIDESHOW=1 ;;
            2|terminboard|termine)             TOOL_TERMIN=1 ;;
            3|safetycross|safety-cross|safety) TOOL_SC=1 ;;
            *) fail "Ungültige Tool-Auswahl '${t}'. Erlaubt: 1,2,3 (oder slideshow,terminboard,safetycross)" ;;
        esac
    done
    if [ $((TOOL_SLIDESHOW + TOOL_TERMIN + TOOL_SC)) -eq 0 ]; then
        fail "Kein Tool gewählt – mindestens eines angeben."
    fi

    if [ -z "$screens_arg" ]; then
        # Wie viele Bildschirme genutzt werden, wird bei der Ersteinrichtung
        # gewählt (Vorschlag: was erkannt wird).
        screens_arg="${MAX_SCREENS}"
    fi
    case "${screens_arg:-1}" in
        1|2) SCREEN_COUNT="$screens_arg" ;;
        *) fail "Ungültige Bildschirm-Anzahl '${screens_arg}'. Erlaubt: 1 oder 2" ;;
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
StartLimitIntervalSec=120
StartLimitBurst=5

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

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "${SERVICE_TERMIN_APP}"
    ok "Terminboard installiert und aktiviert (Port ${TERMIN_PORT})"
}

# ── Safety Cross (drittes Tool) ────────────────────────────────────────

prepare_safetycross() {
    log "Richte Safety Cross unter ${SC_DIR} ein"
    local src="${SCRIPT_DIR}/tools/safety-cross"
    if [ ! -d "${src}" ]; then
        fail "Safety-Cross-Code nicht gefunden: ${src}"
    fi
    mkdir -p "${SC_DIR}"
    local f d
    for f in app.py auth.py db.py license.py requirements.txt; do
        [ -f "${src}/${f}" ] && cp "${src}/${f}" "${SC_DIR}/"
    done
    for d in templates static; do
        if [ -d "${src}/${d}" ]; then
            rm -rf "${SC_DIR:?}/${d}"
            cp -r "${src}/${d}" "${SC_DIR}/"
        fi
    done
    ok "Safety-Cross-Dateien bereit"
}

setup_safetycross_python() {
    log "Erstelle Safety-Cross-Virtualenv"
    python3 -m venv "${SC_DIR}/venv"
    "${SC_DIR}/venv/bin/pip" install --upgrade pip -q
    "${SC_DIR}/venv/bin/pip" install -q -r "${SC_DIR}/requirements.txt"
    chown -R "${PI_USER}:${PI_GROUP}" "${SC_DIR}"
    ok "Safety-Cross-Python-Umgebung fertig"
}

configure_safetycross_app() {
    log "Richte Safety Cross ein (Datenbank, Login, Hardware-Lizenz)"
    ( cd "${SC_DIR}" && "${SC_DIR}/venv/bin/python" -c \
        "import db, auth; db.init_db(); auth.init_admin_password('admin'); print('DB ok')" )

    if [ ! -f "${SC_DIR}/.secret" ]; then
        tr -dc 'A-Za-z0-9' </dev/urandom | head -c 48 > "${SC_DIR}/.secret" || true
        chmod 600 "${SC_DIR}/.secret"
    fi
    if ( cd "${SC_DIR}" && SAFETY_SECRET_FILE="${SC_DIR}/.secret" \
         "${SC_DIR}/venv/bin/python" "${SC_DIR}/license.py" --make-key >/dev/null 2>&1 ); then
        ok "Hardware-Lizenz für dieses Gerät erzeugt"
    else
        warn "Lizenz-Key konnte nicht erzeugt werden (kein Pi?) – App läuft im Entwicklungsmodus"
    fi

    cat > "/etc/systemd/system/${SERVICE_SC_APP}" <<EOF
[Unit]
Description=Safety Cross - Flask Web-App
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=120
StartLimitBurst=5

[Service]
Type=simple
User=${PI_USER}
Group=${PI_GROUP}
WorkingDirectory=${SC_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=PORT=${SC_PORT}
Environment=SAFETY_SECRET_FILE=${SC_DIR}/.secret
Environment=SAFETY_LICENSE=${SC_DIR}/license.key
ExecStart=${SC_DIR}/venv/bin/python ${SC_DIR}/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    chown -R "${PI_USER}:${PI_GROUP}" "${SC_DIR}"
    systemctl daemon-reload
    systemctl enable "${SERVICE_SC_APP}"
    ok "Safety Cross installiert und aktiviert (Port ${SC_PORT})"
}

usage() {
    cat <<'USAGE_EOF'
Aufruf: sudo bash install.sh [Optionen]

  --tools=1,2,3     Tools: 1=Folien   2=Terminboard   3=Safety Cross
                    (auch Namen: slideshow,terminboard,safetycross)
  --screens=1|2     Bildschirme, die die Lizenz erlaubt (Standard: 2)
                    Welche genutzt werden, wird bei der Ersteinrichtung
                    auf dem Bildschirm gewählt.
  --license=<datei> Lizenzdatei für dieses Gerät (sonst wird lizenz.key auf
                    der Boot-Partition bzw. im Projektverzeichnis gesucht)
  --sign-key=<datei> privater Signaturschlüssel (nur Hersteller-Rechner:
                    damit wird die Lizenz direkt erzeugt)
  --no-reboot       nicht automatisch neu starten
  -h, --help        diese Hilfe

Ohne Optionen fragt das Skript interaktiv nach Tools und Bildschirmen.
USAGE_EOF
}

# ── Hauptprogramm ──────────────────────────────────────────────────────
main() {
    echo "================================================"
    echo "  ${PROJECT_NAME} - Multitool-Kiosk Installation"
    echo "  Raspberry Pi OS Desktop (Trixie)"
    echo "================================================"

    local selection="" screens=""
    for arg in "$@"; do
        case "$arg" in
            -h|--help)   usage; exit 0 ;;
            --no-reboot) NO_REBOOT=1 ;;
            --tools=*)   selection="${arg#--tools=}" ;;
            --screens=*) screens="${arg#--screens=}" ;;
            --license=*) LICENSE_ARG="${arg#--license=}" ;;
            --sign-key=*) export LHTPI_SIGN_KEY_FILE="${arg#--sign-key=}" ;;
            -*)          fail "Unbekannte Option '${arg}' (siehe --help)" ;;
            *)           selection="$arg" ;;
        esac
    done

    require_root
    require_desktop_target
    ensure_pi_user

    select_components "$selection" "$screens"

    echo ""
    echo "  Gewählte Tools: $(tools_file_content | tr '\n' ' ')"
    echo "  Bildschirme:    ${SCREEN_COUNT}"
    echo ""

    install_packages

    # Die Verteiler-App (Dashboard + Anzeige-Router + Lizenz) ist immer dabei,
    # sie zeigt die gewählten Tools an.
    prepare_project
    setup_python
    if [ "$TOOL_TERMIN" = "1" ]; then
        prepare_termin
        setup_termin_python
    fi
    if [ "$TOOL_SC" = "1" ]; then
        prepare_safetycross
        setup_safetycross_python
    fi

    backup_configs
    configure_network
    configure_services
    if [ "$TOOL_TERMIN" = "1" ]; then
        configure_terminboard
    fi
    if [ "$TOOL_SC" = "1" ]; then
        configure_safetycross_app
    fi
    configure_tools_file
    configure_license
    configure_license_import
    configure_setup_mode
    cleanup_old_kiosks
    configure_desktop
    configure_autologin
    configure_screens
    configure_policies
    configure_firewall
    configure_usb_automount
    configure_clock
    print_summary
}

# Nur ausführen, wenn direkt gestartet (nicht beim Sourcen in Tests)
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
