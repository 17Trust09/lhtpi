#!/bin/bash
# LHTPi: Anzeige retten, ohne den Rechner neu zu starten.
#
# Gedacht fuer den Fall "ein Bildschirm ist schwarz". Das Skript geht von
# harmlos nach hart und hoert auf, sobald beide Bilder stehen:
#
#   1. Stromsparen und Bildschirmschoner abschalten (DPMS)
#   2. Ausgaenge neu setzen (Position, Aufloesung)
#   3. Kiosk-Fenster neu starten
#
# Aufruf:  sudo bash scripts/anzeige-rettung.sh
set -u

if [ "$(id -u)" != "0" ]; then
    echo "Bitte mit sudo starten: sudo bash $0"
    exit 1
fi

PI_USER="${LHTPI_USER:-pi}"
export DISPLAY=":0"
export XAUTHORITY="/home/${PI_USER}/.Xauthority"

sag() { echo "  $*"; }

echo "=== LHTPi Anzeige retten ==="

# ── 1. X erreichbar? ─────────────────────────────────────────────────────
if ! xset q >/dev/null 2>&1; then
    echo "Der X-Server antwortet nicht. Das laesst sich nur mit einem Neustart"
    echo "beheben:  sudo systemctl restart display-manager"
    exit 1
fi
sag "X-Server antwortet."

# ── 2. Stromsparen aus ───────────────────────────────────────────────────
xset s off      >/dev/null 2>&1 || true
xset -dpms      >/dev/null 2>&1 || true
xset s noblank  >/dev/null 2>&1 || true
xset dpms force on >/dev/null 2>&1 || true
sag "Stromsparen und Bildschirmschoner aus."

# ── 3. Ausgaenge neu setzen ──────────────────────────────────────────────
verbunden="$(xrandr --query 2>/dev/null | grep -E '^HDMI-[12] connected' | awk '{print $1}')"
sag "Verbunden: $(echo ${verbunden:-keiner})"

# In "Anzeigen" gewaehlte Aufloesung hat Vorrang. Ohne sie nimmt --auto die
# hoechste - und wuerde damit eine bewusste Auswahl wieder ueberschreiben.
gewaehlt() {
    local nummer="${1#HDMI-}"
    python3 - "${nummer}" <<'PY' 2>/dev/null
import json
import sys
try:
    daten = json.load(open('/etc/lhtpi/anzeige-fein.json'))
    v = (daten.get(str(int(sys.argv[1]))) or {}).get('aufloesung')
    print(v if v else '')
except Exception:
    print('')
PY
}

g1="$(gewaehlt HDMI-1)"
g2="$(gewaehlt HDMI-2)"

if printf '%s' "${verbunden}" | grep -q 'HDMI-1'; then
    if printf '%s' "${verbunden}" | grep -q 'HDMI-2'; then
        if [ -n "${g1}" ]; then
            xrandr --output HDMI-1 --mode "${g1}" --pos 0x0 \
                   --output HDMI-2 --${g2:+mode "${g2}"}${g2:-auto} --right-of HDMI-1 >/dev/null 2>&1 || true
        else
            xrandr --output HDMI-1 --primary --auto --pos 0x0 \
                   --output HDMI-2 --auto --right-of HDMI-1 >/dev/null 2>&1 || true
        fi
        sag "Beide Ausgaenge gesetzt (HDMI-2 rechts von HDMI-1)."
    else
        if [ -n "${g1}" ]; then
            xrandr --output HDMI-1 --mode "${g1}" --pos 0x0 >/dev/null 2>&1 || true
        else
            xrandr --output HDMI-1 --primary --auto --pos 0x0 >/dev/null 2>&1 || true
        fi
        # HDMI-2 ist gemeldet, aber nicht verbunden - einmal anstossen
        if [ -n "${g2}" ]; then
            xrandr --output HDMI-2 --mode "${g2}" >/dev/null 2>&1 || true
        else
            xrandr --output HDMI-2 --auto >/dev/null 2>&1 || true
        fi
        sag "HDMI-1 gesetzt, HDMI-2 angestossen."
    fi
else
    if [ -n "${g1}" ]; then
        xrandr --output HDMI-1 --mode "${g1}" >/dev/null 2>&1 || true
    else
        xrandr --output HDMI-1 --auto >/dev/null 2>&1 || true
    fi
    sag "HDMI-1 angestossen."
fi

# ── 4. Kiosk-Fenster neu starten ─────────────────────────────────────────
geheimnis_frei=0
sudo -n true >/dev/null 2>&1 && geheimnis_frei=1

for dienst in kiosk-screen1 kiosk-screen2; do
    [ "${geheimnis_frei}" = "1" ] || break
    systemctl restart "${dienst}.service" >/dev/null 2>&1 || true
    sag "${dienst} neu gestartet."
done

sleep 3

# ── 5. Ergebnis ──────────────────────────────────────────────────────────
echo
echo "--- Stand jetzt"
xrandr --query 2>/dev/null | grep -E '^HDMI-[12]' | sed 's/^/  /'
echo "  Fenster: $(xdotool search --class kiosk 2>/dev/null | wc -l) (kiosk)"
echo
echo "Wenn ein Bildschirm weiter schwarz ist: Stecker am Bildschirm ziehen und"
echo "nach fuenf Sekunden wieder stecken - das loest ein Hotplug aus."
echo "Bleibt es dabei, hilft nur:  sudo reboot"
