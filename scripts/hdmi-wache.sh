#!/bin/bash
# LHTPi: hält beide Bildschirme am Leben.
#
# Warum es diesen Wächter gibt: Ein 4K-Bildschirm, der über Nacht in den
# Standby geht, meldet beim Aufwachen nicht immer ein Hotplug-Ereignis. Dann
# steht der Ausgang auf "disconnected", X schaltet ihn ab, und morgens ist das
# Bild weg - obwohl der Rechner die ganze Zeit lief. Ein Neustart hilft, ist
# aber keine Lösung für ein Gerät, das einfach weiterlaufen soll.
#
# Der Wächter prüft im Takt und greift in dieser Reihenfolge ein:
#   1. Ausgang ist abgeschaltet, aber der Bildschirm soll genutzt werden
#      -> Ausgang wieder einschalten (xrandr --auto)
#   2. Ausgang ist an, aber kein Fenster da
#      -> Kiosk-Dienst neu starten
#   3. Alles da, aber der Schirm schwarz (DPMS)
#      -> xset dpms force on
#
# Er handelt nur bei Änderung. Ein Ausgang, der im Sekundentakt neu gesetzt
# wird, flackert - und ein flackerndes Bild ist schlimmer als ein kurzer
# Ausfall am Morgen.
set -u

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/home/pi/.Xauthority}"

# Im Home, weil der Waechter als pi laeuft und /var/log ihm nicht gehoert.
LOG="/home/pi/lhtpi-hdmi.log"
STEUER="/etc/lhtpi/screens"
TAKT=10               # Sekunden zwischen zwei Prüfungen
FEHLER_GRENZE=3       # so oft ohne Fenster, bevor neu gestartet wird

sag() { echo "$(date '+%F %T') - $*" >> "${LOG}" 2>/dev/null || true; }

# Protokoll nicht unbegrenzt wachsen lassen
if [ -f "${LOG}" ] && [ "$(stat -c %s "${LOG}" 2>/dev/null || echo 0)" -gt 200000 ]; then
    tail -n 1000 "${LOG}" > "${LOG}.tmp" 2>/dev/null && mv "${LOG}.tmp" "${LOG}" || true
fi

gewuenschte_bildschirme() {
    local anzahl
    anzahl="$(cat "${STEUER}" 2>/dev/null || echo 1)"
    case "${anzahl}" in ''|*[!0-9]*) anzahl=1 ;; esac
    echo "${anzahl}"
}

# Welche HDMI-Ausgaenge sind laut X verbunden?
verbundene() {
    xrandr --query 2>/dev/null \
        | grep -E '^HDMI-[12] connected' \
        | awk '{print $1}' | tr '\n' ' '
}

# Ist der Ausgang im X-Server ueberhaupt bekannt (auch wenn disconnected)?
ausgang_bekannt() {
    xrandr --query 2>/dev/null | grep -qE "^$1 "
}

# Laeuft ein Fenster fuer diesen Bildschirm?
#
# xdotool fragt die Fensterklasse ab - das ist der genaue Weg. Fehlt es, wird
# ueber xwininfo gesucht; das ist ungenauer, aber besser als gar nicht zu
# pruefen. Fehlt beides, gilt "unbekannt" und es wird NICHT neu gestartet:
# ein Waechter, der aus Unwissen die Anzeige alle 30 Sekunden neu startet,
# waere schlimmer als einer, der nur den Ausgang prueft.
fenster_da() {
    local klasse="$1"
    if command -v xdotool >/dev/null 2>&1; then
        xdotool search --class "${klasse}" >/dev/null 2>&1
        return $?
    fi
    if command -v xwininfo >/dev/null 2>&1; then
        xwininfo -root -children 2>/dev/null | grep -q "${klasse}"
        return $?
    fi
    return 0    # unbekannt: nichts erzwingen
}

ausgang_einschalten() {
    local ausgang="$1" andere="$2"
    # Eine bewusst gewaehlte Aufloesung hat Vorrang. Ohne sie nimmt --auto die
    # hoechste - und wuerde damit eine Auswahl aus "Anzeigen" sofort wieder
    # ueberschreiben, sobald der Waechter einmal einschaltet.
    local gewaehlt=""
    gewaehlt="$(gewaehlte_aufloesung "${ausgang}")"
    if [ -n "${andere}" ] && printf '%s' "${verbundene}" | grep -q "${andere}"; then
        if [ -n "${gewaehlt}" ]; then
            xrandr --output "${andere}" --auto --pos 0x0 \
                   --output "${ausgang}" --mode "${gewaehlt}" --right-of "${andere}" >/dev/null 2>&1
        else
            xrandr --output "${andere}" --primary --auto --pos 0x0 \
                   --output "${ausgang}" --auto --right-of "${andere}" >/dev/null 2>&1
        fi
    else
        if [ -n "${gewaehlt}" ]; then
            xrandr --output "${ausgang}" --mode "${gewaehlt}" --pos 0x0 >/dev/null 2>&1
        else
            xrandr --output "${ausgang}" --primary --auto --pos 0x0 >/dev/null 2>&1
        fi
    fi
}

# Aus "Anzeigen" gemerkte Aufloesung fuer einen Ausgang, sonst leer.
gewaehlte_aufloesung() {
    local ausgang="$1" nummer="${ausgang#HDMI-}"
    python3 - "${nummer}" <<'PY' 2>/dev/null
import sys
try:
    import anzeige_fein
    v = anzeige_fein.aufloesung(int(sys.argv[1]))
    print(v if v else '')
except Exception:
    print('')
PY
}

letzter_zustand=""
fehler_zaehler=0
dpms_zuletzt=0

sag "Waechter gestartet"

while true; do
    anzahl="$(gewuenschte_bildschirme)"
    verbundene="$(verbundene)"

    if [ "${anzahl}" -lt 2 ]; then
        # Nur ein Bildschirm gewuenscht: trotzdem dafuer sorgen, dass er an ist.
        if ! printf '%s' "${verbundene}" | grep -q 'HDMI-1'; then
            if [ "${letzter_zustand}" != "1-weg" ]; then
                sag "HDMI-1 nicht verbunden - versuche einzuschalten"
                letzter_zustand="1-weg"
            fi
            ausgang_einschalten HDMI-1 ""
            xset dpms force on >/dev/null 2>&1 || true
        fi
        sleep "${TAKT}"
        continue
    fi

    # ── HDMI-1: immer gebraucht ────────────────────────────────────────────
    if ! printf '%s' "${verbundene}" | grep -q 'HDMI-1'; then
        if [ "${letzter_zustand}" != "1-weg" ]; then
            sag "HDMI-1 meldet nicht 'connected' - Ausgang wird neu gesetzt"
            letzter_zustand="1-weg"
        fi
        ausgang_einschalten HDMI-1 ""
        xset dpms force on >/dev/null 2>&1 || true
    fi

    # ── HDMI-2: der anfaellige Ausgang ─────────────────────────────────────
    if printf '%s' "${verbundene}" | grep -q 'HDMI-2'; then
        if [ "${letzter_zustand}" = "2-weg" ] || [ -z "${letzter_zustand}" ]; then
            sag "HDMI-2 wieder verbunden - Fenster werden neu aufgebaut"
            ausgang_einschalten HDMI-2 HDMI-1
            letzter_zustand="2-da"
        fi

        if ! fenster_da kiosk-screen2; then
            fehler_zaehler=$((fehler_zaehler + 1))
            if [ "${fehler_zaehler}" -ge "${FEHLER_GRENZE}" ]; then
                sag "kein Fenster auf HDMI-2 nach ${fehler_zaehler} Pruefungen - Dienst wird neu gestartet"
                sudo -n systemctl restart kiosk-screen2.service >/dev/null 2>&1 \
                    || sag "Neustart von kiosk-screen2 nicht erlaubt (sudo-Freigabe fehlt)"
                fehler_zaehler=0
                sleep 5
            fi
        else
            fehler_zaehler=0
        fi
    else
        # Der Fall, der den Ausfall verursacht hat: der Ausgang ist da, meldet
        # aber nicht 'connected'. Ein blosses Warten hilft nicht - der Ausgang
        # muss neu gesetzt werden, damit der Treiber ihn wieder abfragt.
        if [ "${letzter_zustand}" != "2-weg" ]; then
            sag "HDMI-2 meldet nicht 'connected' (bekannt: $(ausgang_bekannt HDMI-2 && echo ja || echo nein)) - Ausgang wird neu gesetzt"
            letzter_zustand="2-weg"
        fi
        if ausgang_bekannt HDMI-2; then
            # Eine gewaehlte Aufloesung bleibt - --auto wuerde sie aufs Maximum setzen.
            local gewaehlt=""
            gewaehlt="$(gewaehlte_aufloesung HDMI-2)"
            if [ -n "${gewaehlt}" ]; then
                xrandr --output HDMI-2 --mode "${gewaehlt}" >/dev/null 2>&1 || true
            else
                xrandr --output HDMI-2 --auto >/dev/null 2>&1 || true
            fi
        fi
        xset dpms force on >/dev/null 2>&1 || true

        # Kein Bild heisst nicht automatisch: Kiosk kaputt. Aber wenn der
        # Ausgang nach mehreren Versuchen immer noch weg ist, hilft nur ein
        # Neustart des Fensters - der Dienst setzt beim Start auch xrandr neu.
        fehler_zaehler=$((fehler_zaehler + 1))
        if [ "${fehler_zaehler}" -ge $((FEHLER_GRENZE * 3)) ]; then
            sag "HDMI-2 seit ${fehler_zaehler} Pruefungen ohne Signal - starte Anzeige neu"
            if [ -x /usr/local/bin/lhtpi-anzeige-rettung.sh ]; then
                sudo -n /usr/local/bin/lhtpi-anzeige-rettung.sh >/dev/null 2>&1 \
                    || sag "Anzeige-Neustart nicht erlaubt (sudo-Freigabe fehlt)"
            fi
            fehler_zaehler=0
            # Nach einem Eingriff Luft lassen: der Bildschirm braucht Sekunden,
            # bis er zurueckmeldet. Ohne Pause wuerde der Waechter alle 30
            # Sekunden neu starten.
            sleep 60
        fi
    fi

    # DPMS: einmal pro Minute reicht. Der Schirm geht sonst irgendwann aus,
    # weil X die Anforderung vergisst.
    jetzt="$(date +%s)"
    if [ $((jetzt - dpms_zuletzt)) -ge 60 ]; then
        xset s off >/dev/null 2>&1 || true
        xset -dpms >/dev/null 2>&1 || true
        xset s noblank >/dev/null 2>&1 || true
        dpms_zuletzt="${jetzt}"
    fi

    sleep "${TAKT}"
done
