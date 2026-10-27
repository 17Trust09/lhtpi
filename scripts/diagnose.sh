#!/bin/bash
# LHTPi: Kurzdiagnose für die Anzeige.
#
# Aufruf:   bash scripts/diagnose.sh      (kein sudo nötig)
#
# Sammelt alles, was zur Fehlersuche nötig ist, und schreibt es lesbar auf den
# Schirm. Gedacht zum Abfotografieren.

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
set -u

PI_USER="${LHTPI_USER:-pi}"
HOME_DIR="/home/${PI_USER}"

# ── Kurzbericht ────────────────────────────────────────────────────────────
# Nur die Werte, an denen die Fehlersuche haengt, gross und knapp. Gedacht zum
# Abfotografieren - der lange Bericht ist auf einem Foto nicht lesbar.
if [ "${1:-}" = "--kurz" ]; then
    echo
    echo "===== LHTPi Kurzbericht ====="
    echo "Geraet : $(hostname)   $(date '+%F %H:%M')"
    echo "Version: $(cat /etc/lhtpi/version 2>/dev/null || echo '?')"
    echo

    xp="$(pgrep -c Xorg 2>/dev/null)"; case "${xp}" in ''|*[!0-9]*) xp=0 ;; esac
    echo "X-Server   : ${xp} Prozess(e), Socket $([ -S /tmp/.X11-unix/X0 ] && echo da || echo FEHLT)"
    DISPLAY=:0 xrandr --query 2>/dev/null | grep -E '^HDMI-[12]' | cut -c1-52 | sed 's/^/  /'

    an="$(cat /etc/lhtpi/screens 2>/dev/null)"
    echo "Bildschirme: screens='${an:-leer}'  Marke2=$([ -f /etc/lhtpi/screen2 ] && echo da || echo FEHLT)"

    for idx in 1 2; do
        da="$(pgrep -af "class=kiosk-screen${idx}" 2>/dev/null | head -1 | grep -oE '\-\-window-position=[^ ]+' || true)"
        echo "Kiosk ${idx}    : $([ -n "${da}" ] && echo "laeuft  ${da}" || echo 'laeuft NICHT')"
    done

    echo "Dienst 2   : $(systemctl is-active kiosk-screen2 2>/dev/null) / $(systemctl show kiosk-screen2 -p Result --value 2>/dev/null)"
    echo "Seite /2   : $(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8000/screen/2 2>/dev/null || echo '---')"
    echo "Ausgaenge  : $(cat /sys/class/drm/card*-HDMI-*/status 2>/dev/null | grep -c '^connected$') verbunden (Kernel)"
    verb="$(cat /sys/class/drm/card*-HDMI-*/status 2>/dev/null | grep -c '^connected$')"
    echo "DB-Zahl    : $("${LHTPI_PYTHON:-python3}" -c "import sqlite3;print((sqlite3.connect('/var/lib/lhtpi/app/lhtpi.db').execute(\"SELECT value FROM setting WHERE key='kiosk_screen_count'\").fetchone() or ['?'])[0])" 2>/dev/null || echo '?')"
    echo "Audio-Fehler: $(dmesg 2>/dev/null | grep -c 'hdmi-audio\|ASoC error')"
    echo "============================="
    echo
    exit 0
fi

strich() { printf '%s\n' "----------------------------------------"; }
titel() { echo; strich; echo "  $*"; strich; }

titel "1. X-Server"
xprozesse="$(pgrep -c Xorg 2>/dev/null)"
case "${xprozesse}" in ''|*[!0-9]*) xprozesse=0 ;; esac
xvorgang="$(pgrep -a Xorg 2>/dev/null | head -2)"
echo "Xorg-Prozesse: ${xprozesse}"
[ -n "${xvorgang}" ] && echo "${xvorgang}"
if [ -S /tmp/.X11-unix/X0 ]; then
    echo "X-Socket :0   vorhanden"
else
    echo "X-Socket :0   FEHLT  <-- ohne Socket gibt es keine Anzeige"
fi

echo
echo "LightDM (soll inaktiv sein, X kommt von startx):"
systemctl is-active lightdm 2>/dev/null | sed 's/^/  /'

titel "2. Bildschirme laut X"
if [ "${xprozesse}" -gt 0 ]; then
    DISPLAY=:0 xrandr --query 2>&1 | grep -E "^HDMI|^Screen|Cannot|error" | sed 's/^/  /'
else
    echo "  (kein X - nicht abfragbar)"
fi

titel "3. Zugang zu X"
for datei in "${HOME_DIR}/.Xauthority" /run/lightdm/root/:0; do
    if [ -e "${datei}" ]; then
        echo "  $(ls -l "${datei}" 2>/dev/null | awk '{print $1, $3, $4, $9}')"
    else
        echo "  ${datei}  fehlt"
    fi
done
echo "  Prozess des ersten Chromium:"
pgrep -a chromium 2>/dev/null | head -1 | cut -c1-120 | sed 's/^/    /'

titel "3b. Fenster und Chromium-Aufrufe"
echo "  Chromium-Prozesse: $(pgrep -c chromium 2>/dev/null || echo 0)"
echo "  Startargumente je Prozess (Position und Groesse):"
pgrep -a chromium 2>/dev/null | grep -oE '\-\-class=[^ ]+|\-\-window-position=[^ ]+|\-\-window-size=[^ ]+|\-\-app=[^ ]+' \
    | sed 's/^/    /' | head -12
echo "  Bekannte Fenster laut X:"
if command -v xwininfo >/dev/null 2>&1; then
    xwininfo -root -children 2>/dev/null | grep -iE 'kiosk|chromium' | head -6 | cut -c1-100 | sed 's/^/    /' \
        || echo "    (keine passenden Fenster gefunden)"
else
    echo "    (xwininfo nicht installiert)"
fi
echo "  Seitenabruf auf dem Gerät:"
for port in 8000 8001; do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:${port}/screen/2" 2>/dev/null || echo '---')"
    echo "    /screen/2 auf Port ${port}: ${code}"
done

titel "4. Dienst Bildschirm 2"
echo "  Zustand: $(systemctl is-active kiosk-screen2 2>/dev/null)"
echo "  Ergebnis des letzten Starts:"
systemctl show kiosk-screen2 -p Result -p ExecMainStatus 2>/dev/null | sed 's/^/    /'

titel "5. Startskripte"
for datei in "${HOME_DIR}/start_kiosk_screen1.sh" "${HOME_DIR}/start_kiosk_screen2.sh"; do
    if [ -f "${datei}" ]; then
        echo "  $(ls -l "${datei}" | awk '{print $1, $3, $4, $5, $9}')"
    else
        echo "  ${datei}  FEHLT"
    fi
done
echo "  Marke /etc/lhtpi/screen2: $([ -f /etc/lhtpi/screen2 ] && echo vorhanden || echo FEHLT)"
echo "  Bildschirmzahl: '$(cat /etc/lhtpi/screens 2>/dev/null)'"

titel "6. Chromium"
chromium="$(command -v chromium-browser || command -v chromium || echo '')"
echo "  Pfad: ${chromium:-NICHT GEFUNDEN}"
if [ -n "${chromium}" ]; then
    fehlend="$(ldd "${chromium}" 2>/dev/null | grep -c 'not found')"
    echo "  Fehlende Bibliotheken: ${fehlend}"
    [ "${fehlend}" -gt 0 ] && ldd "${chromium}" 2>/dev/null | grep "not found" | head -5 | sed 's/^/    /'
fi

titel "7. Letzte Zeilen des Kiosk-Protokolls"
if [ -f "${HOME_DIR}/kiosk-screen2.log" ]; then
    tail -6 "${HOME_DIR}/kiosk-screen2.log" | cut -c1-140 | sed 's/^/  /'
else
    echo "  (kein Protokoll)"
fi

titel "8. Audio-Fehler seit dem Start"
treffer="$(dmesg 2>/dev/null | grep -c 'hdmi-audio\|ASoC error')"
case "${treffer}" in ''|*[!0-9]*) treffer="?" ;; esac
echo "  Treffer hdmi-audio: ${treffer}"

titel "9. Bootparameter"
grep -E "vc4-kms|hdmi_ignore|hdmi_force|disable_overscan" /boot/firmware/config.txt 2>/dev/null | sed 's/^/  /' || \
    echo "  (config.txt nicht lesbar)"

echo
strich
echo "  Diagnose fertig - dieses Bild genügt."
strich
