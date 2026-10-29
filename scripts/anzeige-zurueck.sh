#!/bin/bash
# LHTPi: Aufloesung auf den nativen Modus zuruecksetzen.
#
# Gedacht fuer den Fall "Bildschirm zeigt nach einem Aufloesungswechsel nur
# noch 'kein Signal'". Der Fernseher kann die gewaehlte Aufloesung nicht
# anzeigen, und weil sie moeglicherweise auch 'dauerhaft' gespeichert wurde,
# haelt der schwarze Bildschirm sogar einen Neustart ueber.
#
# Das Skript macht drei Dinge rueckgaengig:
#   1. setzt die Aufloesung SOFORT auf nativ (--auto)
#   2. entfernt die gemerkte Aufloesung aus /etc/lhtpi/anzeige-fein.json,
#      damit Waechter, Rettung und Startskript sie nicht wieder erzwingen
#   3. entfernt video=HDMI-A-* aus der Kernel-Zeile, damit auch der naechste
#      Start wieder nativ beginnt
#
# Aufruf (als root):  sudo bash scripts/anzeige-zurueck.sh
set -u

[ "$(id -u)" = "0" ] || { echo "Bitte mit sudo starten: sudo bash $0"; exit 1; }

PI_USER="${LHTPI_USER:-pi}"
export DISPLAY=":0"
export XAUTHORITY="/home/${PI_USER}/.Xauthority"

sag() { echo "  $*"; }

echo "===== Aufloesung zuruecksetzen ====="

# ── 1. Sofort auf nativ ──────────────────────────────────────────────────
# --auto nimmt die vom Bildschirm gemeldete (native) Aufloesung - genau die,
# die vor dem Wechsel funktionierte.
xrandr --output HDMI-1 --auto 2>/dev/null && sag "HDMI-1 auf nativ gesetzt."
xrandr --output HDMI-2 --auto 2>/dev/null || true
xset dpms force on >/dev/null 2>&1 || true

# ── 2. Gemerkte Aufloesung loeschen ──────────────────────────────────────
CONF="/etc/lhtpi/anzeige-fein.json"
if [ -f "${CONF}" ]; then
    python3 - "${CONF}" <<'PY'
import json
import sys
pfad = sys.argv[1]
try:
    with open(pfad, encoding='utf-8') as datei:
        daten = json.load(datei)
    if isinstance(daten, dict):
        for schluessel in ('1', '2'):
            eintrag = daten.get(schluessel)
            if isinstance(eintrag, dict) and 'aufloesung' in eintrag:
                del eintrag['aufloesung']
        with open(pfad, 'w', encoding='utf-8') as datei:
            json.dump(daten, datei, indent=1, sort_keys=True)
    print('Aufloesung aus %s entfernt.' % pfad)
except (OSError, ValueError) as fehler:
    print('Konnte %s nicht aendern: %s' % (pfad, fehler))
PY
else
    sag "Keine ${CONF} - nichts zu loeschen."
fi

# ── 3. Kernel-Zeile bereinigen ───────────────────────────────────────────
# Steht dort video=HDMI-A-1:..., zwingt der Kernel genau diese (unbrauchbare)
# Aufloesung schon beim naechsten Boot. Wortweise entfernen, weil cmdline.txt
# EINE Zeile ist.
for ziel in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
    [ -f "${ziel}" ] || continue
    if grep -q 'video=HDMI-A-' "${ziel}"; then
        cp -a "${ziel}" "${ziel}.vor-lhtpi-notfall" 2>/dev/null || true
        neu=""
        for wort in $(tr '\n' ' ' < "${ziel}"); do
            case "${wort}" in
                video=HDMI-A-*) continue ;;
            esac
            neu="${neu} ${wort}"
        done
        printf '%s\n' "$(echo "${neu}" | sed 's/^ //')" > "${ziel}"
        sag "video= aus ${ziel} entfernt."
    else
        sag "${ziel} enthaelt keine video= Eintraege."
    fi
done

echo
echo "Fertig. Das Bild sollte jetzt wieder da sein."
echo "Falls nicht, einmal neu starten:  sudo reboot"
echo
echo "Danach: Diesen Fernseher bei seiner nativen Aufloesung lassen und"
echo "stattdessen 'Groesse der Anzeige' in den Einstellungen nutzen."
