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
SERVICE_DISPLAY_GUARD="lhtpi-display-guard.service"
SERVICE_SCREEN2_WATCH="lhtpi-screen2-watch.service"

# ── Bildschirm-Wächter: Dauerbetrieb + spätes Einschalten ─────────────

render_display_guard() {
    cat <<'DISPLAY_GUARD_EOF'
#!/bin/bash
set -u

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/home/pi/.Xauthority}"
letzter_zustand=""

while true; do
    # Nicht nur einmal beim Start: Desktop-Komponenten oder ein Hotplug dürfen
    # Bildschirmschoner/DPMS später nicht wieder einschalten.
    # Bildschirm 2 läuft nur, wenn er laut Einstellung genutzt wird. Die Zahl steht
# in /etc/lhtpi/screens. Der Dienst hat bewusst keine Pfad-Bedingung mehr –
# sonst startet er wortlos nicht, wenn die Marke fehlt.
anzahl="$(cat /etc/lhtpi/screens 2>/dev/null || echo 2)"
case "${anzahl}" in ''|*[!0-9]*) anzahl=2 ;; esac
if [ "__IDX__" = "2" ] && [ "${anzahl}" -lt 2 ]; then
    echo "$(date '+%F %T') - Bildschirm 2 ist ausgeschaltet (screens=${anzahl}) - Ende" >> "$LOG"
    exit 0
fi

xset s off >/dev/null 2>&1 || true
    xset dpms force on >/dev/null 2>&1 || true
    xset -dpms >/dev/null 2>&1 || true
    xset s noblank >/dev/null 2>&1 || true

    zustand="$(xrandr --query 2>/dev/null | awk '$1 ~ /^HDMI-[12]$/ {print $0}')"
    if [ -n "${zustand}" ] && [ "${zustand}" != "${letzter_zustand}" ]; then
        angeschlossen=""
        for ausgang in HDMI-1 HDMI-2; do
            if printf '%s\n' "${zustand}" | grep -q "^${ausgang} connected"; then
                angeschlossen="${angeschlossen} ${ausgang}"
            fi
        done
        # Bildschirm 1 ist der erste tatsächlich angeschlossene Port. So kommt
        # das Bild auch dann, wenn beim Boot kein Monitor an war oder nur HDMI-2
        # verwendet wird.
        set -- ${angeschlossen}
        # --auto: die Auflösung kommt aus dem EDID des Bildschirms. Eine feste
        # 1920x1080 würde bei anderer Panel-Auflösung schwarze Balken erzeugen.
        if [ "$#" -eq 1 ]; then
            xrandr --output "$1" --primary --auto --pos 0x0 >/dev/null 2>&1 || true
            for ausgang in HDMI-1 HDMI-2; do
                [ "${ausgang}" = "$1" ] || xrandr --output "${ausgang}" --off >/dev/null 2>&1 || true
            done
        elif [ "$#" -ge 2 ]; then
            xrandr --output "$1" --primary --auto --pos 0x0 \
                   --output "$2" --auto --right-of "$1" >/dev/null 2>&1 || true
        fi
        letzter_zustand="${zustand}"
    fi
    sleep 2
done
DISPLAY_GUARD_EOF
}

configure_display_guard() {
    local script="/usr/local/bin/lhtpi-display-guard.sh"
    log "Richte Bildschirm-Wächter ein (kein Standby, Hotplug-sicher)"
    render_display_guard > "${script}"
    chmod 755 "${script}"

    cat > "${UNIT_DIR}/lhtpi-display-guard.service" <<EOF
[Unit]
Description=LHTPi Bildschirm dauerhaft wach halten und Hotplug aktivieren
After=getty@tty1.service

[Service]
Type=simple
User=${PI_USER}
Group=${PI_GROUP}
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/${PI_USER}/.Xauthority
ExecStart=${script}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --now "${SERVICE_DISPLAY_GUARD}"
    ok "Bildschirm-Wächter aktiv (DPMS/Schoner aus, spätes Einschalten erkannt)"
}

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
VERSION_FILE="${LHTPI_VERSION_FILE:-/etc/lhtpi/version}"
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
SCREENS_EXPLIZIT=0   # 1, wenn --screens=... angegeben wurde
TOOLS_EXPLIZIT=0     # 1, wenn --tools=... angegeben wurde
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
        xorg openbox x11-utils xdotool \
        chromium-browser chromium-browser-l10n \
        i2c-tools util-linux-extra \
        exfatprogs ntfs-3g dosfstools usbutils
    ok "Systempakete installiert"
}

prepare_project() {
    log "Richte Projekt unter ${PROJECT_DIR} ein"
    mkdir -p "${PROJECT_DIR}" "${PROJECT_DIR}/uploads"

    if [ "${SCRIPT_DIR}" != "${PROJECT_DIR}" ]; then
        # Nur Programmdateien kopieren – venv, Datenbanken und Uploads bleiben
        # außen vor (sie liegen ohnehin inzwischen unter /var/lib/lhtpi).
        for f in "${SCRIPT_DIR}"/*; do
            [ -f "$f" ] && cp "$f" "${PROJECT_DIR}/" 2>/dev/null || true
        done
        # Alle Programmordner mitnehmen. Fehlte terminboard/ und tools/, war die
        # Installation aus einem anderen Verzeichnis unvollständig.
        for d in templates static scripts terminboard tools; do
            [ -d "${SCRIPT_DIR}/${d}" ] || continue
            mkdir -p "${PROJECT_DIR}/${d}"
            cp -a "${SCRIPT_DIR}/${d}/." "${PROJECT_DIR}/${d}/" 2>/dev/null || true
        done
        # Nie mitkopieren: Datenbanken, Uploads, venv
        find "${PROJECT_DIR}" -maxdepth 3 \( -name '*.db' -o -name '__pycache__' -o -name 'venv' \) \
            -prune -exec rm -rf {} + 2>/dev/null || true
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


# ── Bildschirm 2: Erkennung, Aufwachen und Zuordnung ───────────────────
# Zwei Dinge müssen auch ohne Neustart funktionieren:
#   1. Ein nachträglich gestecktes HDMI-Kabel liefert Bild (DPMS an, Auflösung setzen).
#   2. Der Kiosk für Bildschirm 2 startet dann – oder wird neu positioniert.
#
# Ein Wächter-Dienst prüft das dauerhaft. Die Kiosk-Skripte selbst überwachen
# ihren Ausgang bereits; dieser Dienst ist die Rückfallebene für den Fall, dass
# ein Fenster nicht mehr existiert.
configure_screen2_watchdog() {
    [ "${SCREEN_COUNT}" -ge 2 ] || return 0
    log "Richte Wächter für Bildschirm 2 ein"

    local skript="/home/${PI_USER}/lhtpi-screen2-watch.sh"
    # Der Waechter liegt im Repository und wird hierher kopiert: so laesst er
    # sich per git pull aktualisieren. Vorher stand er als Heredoc in dieser
    # Datei - eine Korrektur waere nur mit einem neuen install.sh angekommen.
    if [ -f "${SCRIPT_DIR}/scripts/hdmi-wache.sh" ]; then
        cp "${SCRIPT_DIR}/scripts/hdmi-wache.sh" "${skript}"
    else
        warn "scripts/hdmi-wache.sh fehlt - Waechter nicht aktualisiert"
    fi
    chmod +x "${skript}"
    chown "${PI_USER}:${PI_GROUP}" "${skript}"



    cat > "/etc/systemd/system/${SERVICE_SCREEN2_WATCH}" <<EOF
[Unit]
Description=LHTPi Waechter Bildschirm 2
After=lightdm.service

[Service]
Type=simple
User=${PI_USER}
Group=${PI_GROUP}
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/${PI_USER}/.Xauthority
ExecStart=${skript}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --now "${SERVICE_SCREEN2_WATCH}" >/dev/null 2>&1 || true
    ok "Bildschirm 2: Wächter aktiv (${SERVICE_SCREEN2_WATCH})"
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
# Monitor-Zuordnung: HDMI-1 primär links, HDMI-2 rechts daneben.
# --auto statt fester Auflösung: sonst entstehen bei abweichender Panel-Auflösung
# schwarze Balken links und rechts.
if xrandr --query 2>/dev/null | grep -q '^HDMI-2 connected'; then
    xrandr --output HDMI-1 --primary --auto --pos 0x0 \
           --output HDMI-2 --auto --right-of HDMI-1 >/dev/null 2>&1 || true
else
    xrandr --output HDMI-1 --primary --auto --pos 0x0 >/dev/null 2>&1 || true
fi

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

# Läuft ein Skript für Bildschirm 2, und Bildschirm 1 fehlt: dann ist 2 der
# erste (und einzige) Ausgang und wird primär.
[ "__IDX__" = "2" ] && ! xrandr --query 2>/dev/null | grep -q '^HDMI-1 connected' \
    && xrandr --output HDMI-2 --primary --auto --pos 0x0 >/dev/null 2>&1 || true

# Warten, bis der zugeordnete Ausgang wirklich da ist. Ein nachträglich
# gestecktes Kabel liefert seine Auflösung erst nach der Erkennung – ohne diese
# Wartezeit öffnet Chromium ein Fenster mit falscher Größe.
for i in $(seq 1 30); do
    if xrandr --query 2>/dev/null | grep -q "^__MON__ connected"; then
        break
    fi
    # Außerdem: Bildschirm einschalten, falls DPMS ihn hatte ausschalten lassen
    xrandr --output __MON__ --auto >/dev/null 2>&1 || true
    echo "$(date '+%F %T') - warte auf __MON__" >> "$LOG"
    sleep 2
done

# Geometrie dieses Ausgangs (Breite x Höhe +X+Y). Wird bei JEDEM Start neu
# ermittelt: Ein später gesteckter Bildschirm hat eine andere Auflösung als der
# beim Booten angenommene Rückfall – sonst bleiben links und rechts Balken.
W=1920      # Rückfall, falls beim Booten kein Bildschirm steckt
H=1080
X=0
Y=0
# Stehen beide Ausgaenge auf derselben Position, spiegelt der Treiber sie:
# beide Bildschirme zeigen dasselbe Bild und der Mauszeiger ist doppelt zu
# sehen. Beim Pi 4 passiert das bei zwei 4K-Bildschirmen, weil er die
# Aufloesungen nicht getrennt fahren kann. Vor dem Fensterstart wird der
# zweite Ausgang deshalb nach rechts geschoben.
entkopple_ausgaenge() {
    # Gemeinsamer Helfer: steht beide Ausgaenge auf derselben Position, wird
    # HDMI-2 nach rechts geschoben (und notfalls auf Full HD begrenzt).
    [ -x /usr/local/bin/lhtpi-entkoppeln.sh ] && /usr/local/bin/lhtpi-entkoppeln.sh >> "$LOG" 2>&1 || true
}

ermittle_geometrie() {
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
}
ermittle_geometrie

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

# Chromium im Hintergrund starten und überwachen: Fällt der Ausgang weg, weil das
# Kabel gezogen wurde, beendet X das Fenster. Wird es wieder gesteckt, muss das
# Fenster ohne Neustart des Pi zurückkommen.
starte_chromium() {
    echo "$(date '+%F %T') - starte Chromium auf ${MON} (${W}x${H}+${X}+${Y})" >> "$LOG"
    "$CHROMIUM" \
    --app="$APP_URL" \
    --class=kiosk-screen__IDX__ \
    --user-data-dir="$PROFILE" \
    --window-position="${X},${Y}" \
    --window-size="${W},${H}" \
    --start-fullscreen \
    --force-device-scale-factor=1 \
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
}

entkopple_ausgaenge
ermittle_geometrie
LETZTE_GEO="${W}x${H}+${X}+${Y}"
starte_chromium &
PID=$!

# Nachführung: Solange Bildschirm 2 aktiv ist, prüfen wir, ob der Ausgang noch
# da ist. Verschwindet er, beenden wir Chromium; kommt er zurück, starten wir neu.
while true; do
    sleep 5
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "$(date '+%F %T') - Chromium beendet, starte neu" >> "$LOG"
        sleep 3
        entkopple_ausgaenge
        ermittle_geometrie
        LETZTE_GEO="${W}x${H}+${X}+${Y}"
        starte_chromium &
        PID=$!
        continue
    fi

    # Auflösung oder Position geändert? Dann passt das Fenster nicht mehr.
    # Passiert, wenn die Bildschirme neu getrennt werden (oder beim Sperren der
    # Anzeige-Einstellungen) - ohne Neustart bliebe ein schwarzer Bildschirm.
    ermittle_geometrie
    if [ "${W}x${H}+${X}+${Y}" != "${LETZTE_GEO}" ]; then
        echo "$(date '+%F %T') - Geometrie geändert: ${LETZTE_GEO} -> ${W}x${H}+${X}+${Y}, Neustart" >> "$LOG"
        kill "$PID" 2>/dev/null || true
        wait "$PID" 2>/dev/null || true
        sleep 2
        entkopple_ausgaenge
        ermittle_geometrie
        LETZTE_GEO="${W}x${H}+${X}+${Y}"
        starte_chromium &
        PID=$!
        continue
    fi

    if [ "__IDX__" = "2" ] && ! xrandr --query 2>/dev/null | grep -q '^__MON__ connected'; then
        echo "$(date '+%F %T') - __MON__ getrennt, warte auf erneutes Anstecken" >> "$LOG"
        kill "$PID" 2>/dev/null || true
        wait "$PID" 2>/dev/null || true
        # Warten, bis das Kabel wieder steckt
        for i in $(seq 1 120); do
            if xrandr --query 2>/dev/null | grep -q '^__MON__ connected'; then
                break
            fi
            sleep 5
        done
        # Position und Auflösung neu setzen
        if xrandr --query 2>/dev/null | grep -q '^HDMI-1 connected'; then
            xrandr --output HDMI-1 --primary --auto --pos 0x0 \
                   --output HDMI-2 --auto --right-of HDMI-1 >/dev/null 2>&1 || true
        else
            xrandr --output HDMI-2 --primary --auto --pos 0x0 >/dev/null 2>&1 || true
        fi
        sleep 3
        entkopple_ausgaenge
        ermittle_geometrie
        LETZTE_GEO="${W}x${H}+${X}+${Y}"
        starte_chromium &
        PID=$!
    fi
done
KIOSK_EOF
}

# ── HDMI: echter Vollbild-Modus statt Letterbox ───────────────────────────
# Der alte Kiosk lief über den Legacy-Videotreiber mit fest erzwungener
# Auflösung (hdmi_group/hdmi_mode). Auf dem Pi 4/5 mit KMS ist das falsch:
# Der Bildschirm meldet seine Auflösung selbst, und die alten Zeilen erzeugen
# links/rechts schwarze Balken (Letterbox). Hier wird auf KMS umgestellt.
configure_hdmi_modus() {
    log "Prüfe HDMI-Videomodus"
    local config
    if [ -f /boot/firmware/config.txt ]; then
        config=/boot/firmware/config.txt
    else
        warn "/boot/firmware/config.txt nicht gefunden – HDMI nicht angepasst"
        return 0
    fi

    # Sicherung nur einmal je Tag anlegen, damit die Datei nicht zumuellt
    local sicherung="/boot/firmware/config.txt.vor-lhtpi"
    [ -f "${sicherung}" ] || cp -a "${config}" "${sicherung}" 2>/dev/null || true

    # Alte Zeilen entfernen, die die Auflösung erzwingen
    local geaendert=0
    for zeile in hdmi_group hdmi_mode hdmi_force_hotplug hdmi_drive; do
        if grep -qE "^[[:space:]]*#?[[:space:]]*${zeile}=" "${config}"; then
            sed -i -E "/^[[:space:]]*#?[[:space:]]*${zeile}=/d" "${config}"
            geaendert=1
        fi
    done
    [ "${geaendert}" = "1" ] && ok "Alte Auflösungs-Zwangszeilen entfernt (KMS übernimmt)"

    # KMS sicherstellen (Standard bei Pi 4/5, bei Pi 3 nachziehen)
    # noaudio: HDMI-Ton direkt im KMS-Treiber abschalten. hdmi_ignore_edid_audio
    # allein genuegt nicht - der Codec wird trotzdem angesprochen und schreibt
    # endlos "Not able to map channels to speakers (-22)".
    if ! grep -qE '^[[:space:]]*dtoverlay=vc4-kms-v3d' "${config}"; then
        printf '\n# LHTPi: KMS-Treiber – Auflösung kommt vom Bildschirm (kein Letterbox)\ndtoverlay=vc4-kms-v3d,noaudio\n' >> "${config}"
    elif ! grep -qE '^[[:space:]]*dtoverlay=vc4-kms-v3d[[:space:]]*,.*noaudio' "${config}"; then
        sed -i -E 's/^[[:space:]]*dtoverlay=vc4-kms-v3d[[:space:]]*$/dtoverlay=vc4-kms-v3d,noaudio/' "${config}"
        sed -i -E 's/^[[:space:]]*dtoverlay=vc4-kms-v3d,([^n].*)$/dtoverlay=vc4-kms-v3d,noaudio,\1/' "${config}"
        ok "HDMI-Audio im KMS-Treiber abgeschaltet (noaudio)"
    fi

    # HDMI-Erkennung erzwingen: Der Kiosk zeigt auch dann ein Bild, wenn beim
    # Booten kein Kabel steckt. Die Auflösung wählt der Treiber aus dem EDID.
    if ! grep -qE '^[[:space:]]*hdmi_force_hotplug=1[[:space:]]*$' "${config}"; then
        printf 'hdmi_force_hotplug=1\n' >> "${config}"
        ok "HDMI-Erkennung erzwungen (Bild auch ohne Kabel beim Boot)"
    fi

    # Kein Overscan-Beschneiden – der Kiosk soll die volle Fläche nutzen
    if ! grep -qE '^[[:space:]]*disable_overscan=1' "${config}"; then
        printf 'disable_overscan=1\n' >> "${config}"
    fi

    # HDMI-Audio abschalten. Der Kiosk braucht keinen Ton, aber manche
    # Bildschirme können die Kanäle nicht zuordnen – dann schreibt der
    # Audio-Treiber endlos "Not able to map channels to speakers (-22)" und
    # "ASoC error (-22)" ins Log. Diese Schleife kostet Rechenzeit, während der
    # Grafiktreiber dieselbe Hardware anspricht; ein Ausgang bleibt dann schwarz,
    # obwohl die Maus weiterläuft. Mit dieser Zeile wird die Audio-Fähigkeit des
    # Bildschirms gar nicht erst ausgelesen.
    if ! grep -qE '^[[:space:]]*hdmi_ignore_edid_audio=1' "${config}"; then
        printf '\n# LHTPi: kein HDMI-Ton – verhindert die Endlosschleife des Audio-Codecs\nhdmi_ignore_edid_audio=1\n' >> "${config}"
        ok "HDMI-Audio abgeschaltet (Kiosk braucht keinen Ton)"
    fi

    ok "HDMI auf KMS umgestellt (Vollbild, kein Letterbox)"
}

configure_screen_kiosk() {
    local idx="$1" script service
    script="$(kiosk_script_path "$idx")"
    service="$(kiosk_service_name "$idx")"

    # Bildschirm 1 startet nach der Ersteinrichtung, Bildschirm 2 nur,
    # wenn er bei der Einrichtung gewählt wurde.
    # Bildschirm 2 startet immer und prueft die Bildschirmzahl selbst. Eine
    # ConditionPathExists auf die Marke fuehrte dazu, dass der Dienst nach dem
    # Loeschen der Datei wortlos nicht mehr startete - der Bildschirm blieb
    # schwarz, waehrend die Maus weiterlief.
    local cond="ConditionPathExists=${MARKER_FILE}"

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

installiere_entkoppler() {
    log "Richte Helfer zum Trennen der beiden Bildschirme ein"
    cat > /usr/local/bin/lhtpi-entkoppeln.sh <<'ENTK_EOF'
#!/bin/bash
# LHTPi: verhindert, dass beide Bildschirme dasselbe zeigen.
#
# Stehen HDMI-1 und HDMI-2 auf derselben Position, spiegelt der Treiber sie -
# beide Monitore zeigen dasselbe Bild und der Mauszeiger ist doppelt zu sehen.
# Beim Pi 4 passiert das bei zwei 4K-Bildschirmen, weil er sie nicht getrennt
# fahren kann. Dann wird die Aufloesung auf Full HD begrenzt.
set -u
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/home/pi/.Xauthority}"

position() {
    xrandr --query 2>/dev/null | awk -v m="$1" \
        '$1==m && $2=="connected"{for(i=1;i<=NF;i++) if($i ~ /^[0-9]+x[0-9]+\+/) print $i; exit}'
}

p1="$(position HDMI-1)"
p2="$(position HDMI-2)"
[ -n "${p1}" ] && [ -n "${p2}" ] || exit 0

breite1="$(echo "${p1}" | cut -dx -f1)"
x1="$(echo "${p1}" | cut -d+ -f2)"
x2="$(echo "${p2}" | cut -d+ -f2)"

[ "${x1}" = "${x2}" ] || exit 0

# Versuch 1: nur verschieben, Aufloesung behalten
xrandr --output HDMI-2 --pos "${breite1}x0" >/dev/null 2>&1 || true
neu="$(position HDMI-2)"
if [ "$(echo "${neu}" | cut -d+ -f2)" = "${breite1}" ]; then
    echo "$(date '+%F %T') - Ausgaenge getrennt: HDMI-2 auf ${breite1}x0"
    exit 0
fi

# Versuch 2: der Treiber laesst zwei 4K nicht getrennt zu -> Full HD
xrandr --output HDMI-1 --mode 1920x1080 --pos 0x0 \
       --output HDMI-2 --mode 1920x1080 --pos 1920x0 >/dev/null 2>&1 || true
echo "$(date '+%F %T') - Ausgaenge getrennt: auf 1920x1080 begrenzt (zwei 4K nicht moeglich)"
ENTK_EOF
    chmod 0755 /usr/local/bin/lhtpi-entkoppeln.sh
    ok "Helfer /usr/local/bin/lhtpi-entkoppeln.sh eingerichtet"
}

configure_screens() {
    # Wie viele Bildschirme werden tatsächlich genutzt? Das entscheidet das
    # Gerät (/etc/lhtpi/screens), nicht die Lizenz. Sonst würde ein Update die
    # Kiosk-Einheiten für beide Ausgänge anlegen, obwohl nur einer gewählt ist.
    local genutzt="${SCREEN_COUNT}"
    if [ "${SCREENS_EXPLIZIT}" != "1" ] && [ -s "${SCREENS_FILE}" ]; then
        genutzt="$(tr -dc '0-9' < "${SCREENS_FILE}")"
        [ -n "${genutzt}" ] || genutzt=1
        [ "${genutzt}" -ge 2 ] || genutzt=1
    fi
    SCREEN_COUNT="${genutzt}"
    ok "Genutzte Bildschirme laut Gerät: ${SCREEN_COUNT}"

    # Die Datei ist die Wahrheit für die Start-Steuerung: sie liest sie beim
    # Booten und startet kiosk-screen2 nur, wenn dort 2 steht. Wurde --screens
    # ausdrücklich angegeben, muss sie mitziehen – sonst bliebe Bildschirm 2
    # schwarz, obwohl er eingerichtet ist.
    if [ "${SCREENS_EXPLIZIT}" = "1" ] || [ ! -s "${SCREENS_FILE}" ]; then
        mkdir -p "$(dirname "${SCREENS_FILE}")"
        echo "${SCREEN_COUNT}" > "${SCREENS_FILE}"
        chmod 644 "${SCREENS_FILE}"
        ok "Bildschirmzahl gespeichert: ${SCREEN_COUNT} (${SCREENS_FILE})"
    fi

    local i=1
    while [ "$i" -le "${SCREEN_COUNT}" ]; do
        configure_screen_kiosk "$i"
        i=$((i + 1))
    done

    # Zweiter Bildschirm muss auch die Marke haben, sonst startet er nie
    if [ "${SCREEN_COUNT}" -ge 2 ]; then
        mkdir -p "$(dirname "${SCREEN2_FILE}")"
        : > "${SCREEN2_FILE}"
        ok "Bildschirm 2 als aktiv markiert (${SCREEN2_FILE})"
    fi
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

# Beim Booten entscheidet ausschließlich das dauerhafte Installationsmerkmal:
# ohne Merkmal kommt die Ersteinrichtung, mit Merkmal sofort die gespeicherte
# Anzeige. So braucht ein eingerichtetes Gerät nach Stromausfall keinen Klick.
if [ ! -f "${INSTALLED}" ]; then
    systemctl start lhtpi-setup.service 2>/dev/null || true
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
# Nur Bildschirm 1: faellt das Fenster aus, kommt die Anzeigen-Seite zurueck.
# Bildschirm 2 hat keine Anzeigen-Seite - ein Neustart waere dort das falsche
# Mittel und liess den Schirm schwarz.
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
    if [ -f "${SCRIPT_DIR}/VERSION" ]; then
        mkdir -p "$(dirname "${VERSION_FILE}")"
        tr -d '[:space:]' < "${SCRIPT_DIR}/VERSION" > "${VERSION_FILE}"
        chmod 644 "${VERSION_FILE}"
        ok "Version $(cat "${VERSION_FILE}") vermerkt"
    fi

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
# Wird nur von der Boot-Steuerung bzw. als Fehler-Fallback gestartet. Ist das
# Gerät eingerichtet, startet die Steuerung direkt die gespeicherte Anzeige.

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
After=${SERVICE_APP}
Requires=${SERVICE_APP}

[Service]
Type=oneshot
ExecStart=${steuer}

[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/lhtpi-anzeige.path <<EOF
[Unit]
Description=Wacht ueber Einrichtung und Bildschirm-Anzahl
After=${SERVICE_APP}

[Path]
# Flankengesteuert: PathExists würde bei dauerhaft vorhandenem Merkmal das
# oneshot-Service unmittelbar immer wieder starten (StartLimit-Hit).
PathChanged=${MARKER_FILE}
PathChanged=${SCREENS_FILE}
Unit=lhtpi-anzeige.service

[Install]
WantedBy=paths.target
EOF

    systemctl daemon-reload
    # Nicht die Einstellungsseite selbst startet beim Boot, sondern die
    # Steuerung oben. Sie prüft /etc/lhtpi/installed und wählt dann sicher
    # zwischen Ersteinrichtung und gespeicherter Anzeige.
    systemctl disable lhtpi-setup.service >/dev/null 2>&1 || true
    systemctl enable lhtpi-anzeige.service >/dev/null 2>&1 || true
    systemctl enable --now lhtpi-anzeige.path >/dev/null 2>&1 || true
    ok "Boot-Steuerung bereit: Ersteinrichtung nur beim ersten Start"
}

# Kiosk-Services früherer Versionen (ein Kiosk je Tool) entfernen
cleanup_old_kiosks() {
    # Namen früherer Fassungen (ein Kiosk je Tool, teils mit dem Dashboard)
    # Alles, was DIESE Fassung anlegt, muss bleiben - sonst räumt sich die
    # Einrichtung selbst weg (Lizenz-Import, Uhrzeit-Dienst, Anzeige-Einheiten).
    local behalten=" lhtpi.service lhtpi-setup.service lhtpi-anzeige.service lhtpi-anzeige.path lhtpi-display-guard.service \
kiosk-screen1.service kiosk-screen2.service lhtpi-lizenz-import.service \
lhtpi-fake-hwclock.service lhtpi-fake-hwclock-save.service lhtpi-fake-hwclock-save.timer \
lhtpi-update.service lhtpi-screen2-watch.service "
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
    # Wurde --screens=... ausdrücklich angegeben, gilt das. Sonst bleibt die am
    # Gerät gewählte Zahl erhalten.
    if [ -s "${SCREENS_FILE}" ] && [ "${LHTPI_FORCE_SCREENS:-0}" != "1" ] \
       && [ "${SCREENS_EXPLIZIT}" != "1" ]; then
        ok "Bildschirmzahl bleibt erhalten: $(cat "${SCREENS_FILE}")"
        return 0
    fi
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
    # Bei einer erneuten Installation bleibt die Auswahl am Gerät erhalten –
    # sonst wären nach jedem Lauf wieder alle Tools aktiv. Ausdrücklich
    # angegebene Tools (--tools=...) gewinnen jedoch.
    if [ -s "${TOOLS_FILE}" ] && [ "${LHTPI_FORCE_TOOLS:-0}" != "1" ] \
       && [ "${TOOLS_EXPLIZIT}" != "1" ]; then
        ok "Aktivierte Tools bleiben erhalten: $(tr '\n' ' ' < "${TOOLS_FILE}")"
        return 0
    fi
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
# Ohne DISPLAY kann die App xrandr nicht fragen und zaehlt immer einen
# Bildschirm - dann schrieb jedes Speichern der Anzeige-Einstellungen die 1
# fest, und Bildschirm 2 blieb aus.
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/${PI_USER}/.Xauthority
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

    # Zeiger-Helfer: loest am X-Server einen Klick aus, damit Chromium den
    # Mauszeiger neu zeichnet (die Anzeige ruft ihn ueber POST /zeiger/klick
    # auf, siehe tools/kiosk-cursor-x11.py). Ueber CSS allein geht das nicht:
    # Chromium zeichnet den Zeiger erst beim naechsten Mausereignis neu, er
    # bliebe also bis zum Klick sichtbar.
    # Bewusst nicht unclutter: das blendet den Zeiger dauerhaft aus.
    local zeiger_dir="${PI_HOME}/lhtpi-cursor"
    if [ ! -x "${zeiger_dir}/venv/bin/python" ]; then
        python3 -m venv "${zeiger_dir}/venv" >/dev/null 2>&1 || true
        "${zeiger_dir}/venv/bin/pip" install -q python-xlib >/dev/null 2>&1 || true
    fi
    if [ -x "${zeiger_dir}/venv/bin/python" ] \
       && "${zeiger_dir}/venv/bin/python" -c 'import Xlib' >/dev/null 2>&1; then
        ok "Zeiger-Helfer bereit (tools/kiosk-cursor-x11.py)"
    else
        echo "  ! Zeiger-Helfer nicht eingerichtet - der Zeiger bleibt sichtbar"
    fi
    chown -R "${PI_USER}:${PI_GROUP}" "${zeiger_dir}" 2>/dev/null || true

    local xinitrc="${PI_HOME}/.xinitrc"
    if ! grep -q 'openbox-session' "${xinitrc}" 2>/dev/null \
       || grep -q 'kiosk-cursor-x11' "${xinitrc}" 2>/dev/null; then
        printf '# LHTPi-Kiosk: X-Sitzung ohne Desktop (kein Panel, keine Anmeldung)\nexec openbox-session\n' \
            > "${xinitrc}"
        ok "X-Sitzung eingerichtet (openbox, ohne Anmeldung)"
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

    configure_hdmi_modus

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

installiere_update_mechanismus() {
    # Update-Skript und Dienst: ersetzt ausschließlich Programmdateien.
    # Einstellungen (/etc/lhtpi) und Daten (/var/lib/lhtpi) bleiben unberührt.
    log "Richte Update-Mechanismus ein"

    if [ -f "${SCRIPT_DIR}/scripts/lhtpi-update.sh" ]; then
        install -m 0755 "${SCRIPT_DIR}/scripts/lhtpi-update.sh" /usr/local/bin/lhtpi-update.sh
    else
        warn "scripts/lhtpi-update.sh fehlt – Update über den Stick nicht verfügbar."
        return 0
    fi

    cat > /etc/systemd/system/lhtpi-update.service <<'EOF'
[Unit]
Description=LHTPi Update von USB-Stick
After=local-fs.target
ConditionPathExists=/mnt/lhtpi-usb

[Service]
Type=oneshot
ExecStart=/usr/local/bin/lhtpi-update.sh
TimeoutStartSec=600
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload 2>/dev/null || true
    # Der Dienst wird beim Einstecken gestartet, nicht beim Booten – kein enable.
    ok "Update-Dienst eingerichtet (lhtpi-update.service)"

    # udev: nach dem Mounten das Update anstoßen
    cat > /etc/udev/rules.d/98-lhtpi-update.rules <<'EOF'
ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_USAGE}=="filesystem", ENV{ID_BUS}=="usb", RUN+="/usr/bin/systemd-run --no-block --on-active=6 systemctl start lhtpi-update.service"
EOF
    udevadm control --reload-rules 2>/dev/null || true
    ok "Update-Start beim Einstecken aktiviert"
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

    # Umschalter: Stick für das Schreiben von Berichten kurz auf rw, danach
    # sofort zurück auf ro. Wird nur über sudo für genau dieses Skript erlaubt.
    cat > /usr/local/bin/lhtpi-usb-rw.sh <<'EOF'
#!/bin/sh
# LHTPi: /mnt/lhtpi-usb kurz beschreibbar schalten (nur für Berichte).
# Aufruf: lhtpi-usb-rw.sh rw|ro
ZIEL=/mnt/lhtpi-usb
[ -d "$ZIEL" ] || exit 0
case "$1" in
    rw) mountpoint -q "$ZIEL" || exit 0; exec mount -o remount,rw "$ZIEL" ;;
    ro) mountpoint -q "$ZIEL" || exit 0; sync; exec mount -o remount,ro "$ZIEL" ;;
    *)  echo "Aufruf: $0 rw|ro" >&2; exit 2 ;;
esac
EOF
    chmod 0755 /usr/local/bin/lhtpi-usb-rw.sh

    # udev-Regel: bei eingestecktem USB-Laufwerk den Helfer per systemd-run starten.
    # systemd-run verlässt die udev-Sandbox, damit `mount` zuverlässig funktioniert.
    cat > /etc/udev/rules.d/99-lhtpi-usb.rules <<'EOF'
ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_USAGE}=="filesystem", ENV{ID_BUS}=="usb", RUN+="/usr/bin/systemd-run --no-block --on-active=2 /usr/local/bin/lhtpi-usb-mount.sh $env{DEVNAME}"
ACTION=="remove", SUBSYSTEM=="block", ENV{ID_FS_USAGE}=="filesystem", ENV{ID_BUS}=="usb", RUN+="/usr/bin/systemd-run --no-block /bin/umount -l /mnt/lhtpi-usb"
EOF

    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger --subsystem-match=block 2>/dev/null || true

    ok "USB-Auto-Mount eingerichtet (exFAT/FAT32/NTFS, read-only nach /mnt/lhtpi-usb)"

    installiere_update_mechanismus
}

configure_clock() {
    log "Richte offline-fähige Uhr ein (DS3231 automatisch, sonst fake-hwclock)"

    # I2C und DS3231-Kerneltreiber dauerhaft aktivieren. Das Overlay ist auch
    # ohne angeschlossenes Modul harmlos; /dev/rtc0 erscheint nur mit RTC.
    local boot_config
    if [ -f /boot/firmware/config.txt ]; then
        boot_config=/boot/firmware/config.txt
    else
        boot_config=/boot/config.txt
    fi
    touch "${boot_config}"
    grep -qxF 'dtparam=i2c_arm=on' "${boot_config}" || echo 'dtparam=i2c_arm=on' >> "${boot_config}"
    grep -qxF 'dtoverlay=i2c-rtc,ds3231' "${boot_config}" || echo 'dtoverlay=i2c-rtc,ds3231' >> "${boot_config}"

    # Ein Helfer für beide Fälle: echte RTC lesen/schreiben, andernfalls die
    # zuletzt gespeicherte Zeit von der SD-Karte verwenden. Beim Boot kurz auf
    # udev warten, damit ein vorhandenes /dev/rtc0 nicht übersehen wird.
    cat > /usr/local/sbin/lhtpi-hwclock <<'EOF'
#!/bin/bash
set -u
SAVE=/etc/fake-hwclock.data
RTC_DEVICE=/dev/rtc0
RTC_SYSFS=/sys/class/rtc/rtc0
meldung() { logger -t lhtpi-clock -- "$*" 2>/dev/null || true; }

rtc_plausibel() {
  local rtc_epoch minimum_epoch ersatz_epoch
  [ -r "$RTC_SYSFS/date" ] && [ -r "$RTC_SYSFS/time" ] || return 1
  rtc_epoch=$(date -u -d "$(cat "$RTC_SYSFS/date") $(cat "$RTC_SYSFS/time")" +%s 2>/dev/null) || return 1
  minimum_epoch=$(date -u -d '2024-01-01 00:00:00' +%s)
  [ "$rtc_epoch" -ge "$minimum_epoch" ] || return 1

  # Die beim Installieren gespeicherte Zeit ist der Vertrauensanker. Die RTC
  # darf höchstens einen Tag hinter diesem Anker und bis zu fünf Jahre danach
  # liegen – so bleiben lange Lagerzeiten erlaubt, typische 2000/2099-Werkswerte
  # werden aber nicht blind übernommen.
  if [ -f "$SAVE" ]; then
    ersatz_epoch=$(date -d "$(cat "$SAVE")" +%s 2>/dev/null) || return 1
    [ "$rtc_epoch" -ge "$((ersatz_epoch - 86400))" ] || return 1
    [ "$rtc_epoch" -le "$((ersatz_epoch + 157788000))" ] || return 1
  fi
}

case "${1:-}" in
  load)
    for _ in $(seq 1 10); do
      if [ -e "$RTC_DEVICE" ]; then
        if rtc_plausibel && hwclock --hctosys --utc; then
          meldung "DS3231 erkannt: plausible Systemzeit aus Hardware-Uhr geladen"
          exit 0
        fi
        break
      fi
      sleep 0.5
    done
    meldung "RTC nicht bereit oder unplausibel: verwende gespeicherte Ersatzzeit"
    if [ -f "$SAVE" ] && date -s "$(cat "$SAVE")" >/dev/null 2>&1; then
      # Eine neue/uninitialisierte RTC sofort aus dem verlässlichen Fallback
      # initialisieren, damit bereits der nächste Offline-Boot korrekt ist.
      if [ -e "$RTC_DEVICE" ] && hwclock --systohc --utc; then
        meldung "DS3231 aus gespeicherter Ersatzzeit initialisiert"
      fi
    fi
    ;;
  save)
    # Die Ersatzdatei immer aktuell halten. So bleibt auch nach einem späteren
    # Batterie-/RTC-Ausfall ein frischer Vertrauensanker erhalten.
    date '+%Y-%m-%d %H:%M:%S' > "$SAVE"
    if [ -e "$RTC_DEVICE" ] && hwclock --systohc --utc; then
      meldung "Systemzeit in DS3231 gespeichert"
    else
      meldung "RTC nicht erkannt: Systemzeit als Ersatz auf SD-Karte gespeichert"
    fi
    ;;
  *)
    echo "Nutzung: $0 load|save" >&2
    exit 2
    ;;
esac
EOF
    chmod +x /usr/local/sbin/lhtpi-hwclock

    # Boot: RTC bzw. Ersatzzeit vor time-sync.target laden. NTP darf sie danach
    # korrigieren; der Timer schreibt die korrigierte Zeit später zurück.
    cat > /etc/systemd/system/lhtpi-fake-hwclock.service <<'EOF'
[Unit]
Description=Restore clock from DS3231 or disk fallback
After=systemd-modules-load.service systemd-udev-trigger.service
Before=time-sync.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/lhtpi-hwclock load
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
EOF

    # Shutdown: Zeit in RTC oder Ersatzdatei sichern.
    cat > /etc/systemd/system/lhtpi-fake-hwclock-save.service <<'EOF'
[Unit]
Description=Save clock to DS3231 or disk fallback
DefaultDependencies=no
Before=shutdown.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/lhtpi-hwclock save

[Install]
WantedBy=shutdown.target
EOF

    # Alle 15 Minuten sichern; bei vorhandener RTC wird diese aktualisiert.
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

    ok "Uhr eingerichtet (DS3231 wird automatisch erkannt, sonst SD-Fallback)"
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
# ── Daten aus dem Programmverzeichnis herausziehen ───────────────────────────
# Datenbanken und Uploads liegen danach unter /var/lib/lhtpi. Ein Update kann
# damit den Programmstand austauschen, ohne Termine, Einstellungen oder Folien
# zu verlieren. Die Originale bleiben als Sicherung liegen (es wird kopiert).
migrate_data_dir() {
    local skript="${SCRIPT_DIR}/scripts/migrate_data_dir.sh"
    [ -f "$skript" ] || skript="${PROJECT_DIR}/scripts/migrate_data_dir.sh"
    if [ ! -f "$skript" ]; then
        log "  WARNUNG: migrate_data_dir.sh nicht gefunden - Daten bleiben im Projektverzeichnis"
        return 0
    fi
    log "Trenne Daten vom Programmstand"
    # Dienste anhalten, damit die SQLite-Dateien in Ruhe kopiert werden
    systemctl stop lhtpi terminboard safetycross 2>/dev/null || true
    if LHTPI_DATA_DIR=/var/lib/lhtpi \
       PROJECT_DIR="${PROJECT_DIR}" \
       SC_DIR="${SC_DIR}" \
       OWNER="${PI_USER}:${PI_GROUP}" \
       bash "$skript"; then
        ok "Daten liegen unter /var/lib/lhtpi"
    else
        log "  WARNUNG: Migration mit Fehler beendet - bitte Ausgabe prüfen"
    fi
}

# ── Installationsskript aus dem Projektverzeichnis entfernen ────────────────
# Wunsch: Nach der Installation soll install.sh nicht mehr im Projekt liegen,
# damit der Aufbau nicht auf den ersten Blick nachvollziehbar ist.
# Nicht löschen, sondern nach /root verschieben (Rechte 700) - so bleibt sie
# für eine Wiederherstellung erhalten, ist aber für den pi-Benutzer unsichtbar.
entferne_installer() {
    local quelle="${PROJECT_DIR}/install.sh"
    local ziel
    ziel="/root/lhtpi-install-$(date +%Y%m%d-%H%M).sh"

    if [ ! -f "$quelle" ]; then
        log "Kein install.sh im Projektverzeichnis - nichts zu tun"
        return 0
    fi

    if install -m 0700 -o root -g root "$quelle" "$ziel" 2>/dev/null; then
        rm -f "$quelle"
        log "install.sh aus dem Projekt entfernt"
        log "  Sicherung: ${ziel} (nur root lesbar)"
    else
        log "  WARNUNG: install.sh konnte nicht gesichert werden - bleibt liegen"
    fi
}

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
            --tools=*)   selection="${arg#--tools=}"; TOOLS_EXPLIZIT=1 ;;
            --screens=*) screens="${arg#--screens=}"; SCREENS_EXPLIZIT=1 ;;
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
    migrate_data_dir
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
    configure_hdmi_modus
    configure_display_guard
    installiere_entkoppler
    configure_screens
    configure_screen2_watchdog
    configure_policies
    installiere_bildschirm_helfer
    installiere_anzeige_rettung
    installiere_pull_haken
    configure_sudoers_kiosk
    configure_firewall
    configure_usb_automount
    configure_clock
    entferne_installer

    # Zum Schluss pruefen, ob die Kette wirklich steht. Die Fehler der letzten
    # Wochen waren alle stumm: ein Dienst "active", der freiwillig abbrach, ein
    # Speichern, das nichts bewirkte, ein Waechter, der Gesundheit meldete,
    # waehrend das Bild schwarz war. "Installation abgeschlossen" hiess bisher
    # nicht "Geraet laeuft".
    if [ -f "${SCRIPT_DIR}/scripts/selbsttest.sh" ]; then
        LHTPI_USER="${PI_USER}" bash "${SCRIPT_DIR}/scripts/selbsttest.sh" || true
    fi

    print_summary
}

# ── Freigabe für Neustart / Herunterfahren ───────────────────────────────────
# WICHTIG: Das muss im Hauptteil stehen. Steht der Block im erzeugten
# Steuer-Skript (render_anzeige_steuerung), dann schreibt JEDER Anzeigen-Start
# die Datei wieder leer - die Knöpfe gehen dann still nicht.
installiere_pull_haken() {
    # Nach jedem git pull sollen Kiosk-Skripte und Systemeinstellungen
    # nachgezogen werden - dann genuegt am Geraet ein "git pull".
    local repo="${PROJECT_DIR:-/home/${PI_USER}/lhtpi}"
    if [ -f "${repo}/scripts/hook-installieren.sh" ]; then
        bash "${repo}/scripts/hook-installieren.sh" >/dev/null 2>&1 \
            && ok "git pull zieht Aenderungen selbst nach" \
            || warn "git-Haken nicht eingerichtet"
    fi
}

# Die Rettung nuetzt auch bei einem einzigen Bildschirm - sie wird deshalb
# unabhaengig von der Bildschirmzahl installiert.
installiere_anzeige_rettung() {
    if [ -f "${SCRIPT_DIR}/scripts/anzeige-rettung.sh" ]; then
        install -m 0755 "${SCRIPT_DIR}/scripts/anzeige-rettung.sh" \
            /usr/local/bin/lhtpi-anzeige-rettung.sh && ok "Anzeige-Rettung installiert"
    else
        warn "scripts/anzeige-rettung.sh fehlt"
    fi
}

installiere_bildschirm_helfer() {
    log "Richte Helfer zum Setzen der Bildschirmzahl ein"
    cat > /usr/local/bin/lhtpi-screens.sh <<'SCR_EOF'
#!/bin/bash
# LHTPi: Bildschirmzahl setzen (1 oder 2).
#
# Die Web-App laeuft als pi und darf /etc/lhtpi nicht schreiben. Ohne diesen
# Helfer scheiterte das Speichern der Anzeige-Einstellungen still, und die
# Marke fuer Bildschirm 2 entstand nie - der Dienst startete dann nicht.
#
# Aufruf: lhtpi-screens.sh <1|2>
set -u
anzahl="${1:-}"
case "${anzahl}" in
    1|2) ;;
    *) echo "Aufruf: $0 <1|2>" >&2; exit 2 ;;
esac

ordner=/etc/lhtpi
mkdir -p "${ordner}"
printf '%s\n' "${anzahl}" > "${ordner}/screens"
chmod 644 "${ordner}/screens"

marke="${ordner}/screen2"
if [ "${anzahl}" -ge 2 ]; then
    : > "${marke}"
    chmod 644 "${marke}"
elif [ -e "${marke}" ]; then
    rm -f "${marke}"
fi
echo "Bildschirmzahl: ${anzahl}"
SCR_EOF
    chmod 0755 /usr/local/bin/lhtpi-screens.sh

    # Alle Freigaben an einer Stelle (scripts/sudoers-regeln.sh) - vorher
    # standen sie doppelt in install.sh und kiosk-neu.sh und liefen
    # auseinander. Bei einer frischen Installation fehlten dadurch Rechte,
    # die nach einem Update vorhanden waren.
    if [ -f "${SCRIPT_DIR}/scripts/sudoers-regeln.sh" ]; then
        if LHTPI_USER="${PI_USER}" bash "${SCRIPT_DIR}/scripts/sudoers-regeln.sh"; then
            ok "Freigaben gesetzt (Bildschirme, Rettung, Dienste, Stick)"
        else
            warn "Freigaben nicht gesetzt - Speichern und Waechter bleiben wirkungslos"
        fi
    else
        warn "scripts/sudoers-regeln.sh fehlt - Freigaben nicht gesetzt"
    fi
}

configure_sudoers_kiosk() {
    log "Erlaube Neustart und Herunterfahren vom Bildschirm"
    local datei=/etc/sudoers.d/020_lhtpi-kiosk
    local tmp
    tmp="$(mktemp)"
    cat >"${tmp}" <<SUDOEOF
${PI_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl reboot, /usr/bin/systemctl poweroff, /sbin/reboot, /sbin/poweroff
SUDOEOF
    if [ ! -s "${tmp}" ]; then
        log "  WARNUNG: Freigabe leer geblieben - Knöpfe gehen nicht"
        rm -f "${tmp}"
        return 0
    fi
    if ! visudo -c -f "${tmp}" >/dev/null 2>&1; then
        log "  WARNUNG: Prüfung fehlgeschlagen - Freigabe nicht gesetzt"
        rm -f "${tmp}"
        return 0
    fi
    install -m 0440 -o root -g root "${tmp}" "${datei}"
    rm -f "${tmp}"
    log "  Freigabe steht in ${datei} ($(wc -c < "${datei}") Bytes)"
}

# Nur ausführen, wenn direkt gestartet (nicht beim Sourcen in Tests)
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
