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
