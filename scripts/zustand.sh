#!/bin/bash
# Zeigt den Zustand der Installation auf dem Pi. Ändert nichts.
#
# Aufruf:  sudo bash zustand.sh
#
# Gedacht für die Frage "ist das ein Git-Klon, und wo steht er?" – danach
# entscheidet sich, ob ein git pull reicht oder ob neu geklont werden muss.
set -u

PROJEKT="${1:-/home/pi/lhtpi}"
SC_DIR="/opt/safety-cross"
DATA_DIR="/var/lib/lhtpi"

sag() { printf '%s\n' "$*"; }

# SQLite-Abfrage mit Rückfall auf Python (sqlite3 fehlt auf manchen Systemen)
frage() {
    local datei="$1" sql="$2"
    if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "${datei}" "${sql}" 2>/dev/null
    elif command -v python3 >/dev/null 2>&1; then
        python3 - "${datei}" "${sql}" <<'PYEOF' 2>/dev/null
import sqlite3, sys
try:
    for zeile in sqlite3.connect(sys.argv[1]).execute(sys.argv[2]):
        print('|'.join('' if w is None else str(w) for w in zeile))
except sqlite3.Error:
    pass
PYEOF
    fi
}
titel() { printf '\n== %s\n' "$*"; }

titel "Programmverzeichnis"
if [ -d "${PROJEKT}" ]; then
    sag "vorhanden: ${PROJEKT}"
    sag "Belegt: $(du -sh "${PROJEKT}" 2>/dev/null | cut -f1)"
else
    sag "FEHLT: ${PROJEKT}"
fi

titel "Git"
if [ -d "${PROJEKT}/.git" ]; then
    sag "Ja, ${PROJEKT} ist ein Git-Klon."
    cd "${PROJEKT}" || exit 1
    sag "Branch:   $(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
    sag "Stand:    $(git log -1 --format='%h %ad %s' --date=short 2>/dev/null)"
    sag "Remote:   $(git remote get-url origin 2>/dev/null)"
    aenderungen="$(git status --porcelain 2>/dev/null | wc -l)"
    sag "Lokale Änderungen: ${aenderungen}"
    if [ "${aenderungen}" -gt 0 ]; then
        sag "  (bei einem pull im Weg – vorher ansehen)"
        git status --short 2>/dev/null | head -10 | sed 's/^/  /'
    fi
    sag "Branches mit Remote:"
    git branch -r 2>/dev/null | sed 's/^/  /' | head -10
else
    sag "Nein, kein .git – das Verzeichnis ist eine Kopie, kein Klon."
    sag "Dann ist ein einmaliges Klonen nötig (siehe Ablauf)."
fi

titel "Installierte Version"
for datei in /etc/lhtpi/version "${PROJEKT}/VERSION"; do
    [ -f "${datei}" ] && sag "${datei}: $(cat "${datei}")"
done

titel "Datenbanken – wo liegen sie?"
for paare in \
    "${DATA_DIR}/safety-cross/safetycross.db|${SC_DIR}/safetycross.db" \
    "${DATA_DIR}/terminboard/terminboard.db|${PROJEKT}/terminboard/terminboard.db" \
    "${DATA_DIR}/app/lhtpi.db|${PROJEKT}/lhtpi.db"
do
    neu="${paare%%|*}"
    alt="${paare##*|}"
    for datei in "${neu}" "${alt}"; do
        if [ -f "${datei}" ]; then
            groesse=$(stat -c%s "${datei}" 2>/dev/null)
            zeilen=$(frage "${datei}" "SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
            sag "$(printf '%-58s' "${datei}") ${groesse} Bytes, ${zeilen:-?} Tabellen"
        fi
    done
done

titel "Einstellungen (Safety Cross)"
for datei in "${DATA_DIR}/safety-cross/safetycross.db" "${SC_DIR}/safetycross.db"; do
    [ -f "${datei}" ] || continue
    anzahl=$(frage "${datei}" "SELECT COUNT(*) FROM config")
    [ -n "${anzahl}" ] && sag "${datei}: ${anzahl} Einträge in config"
    frage "${datei}" "SELECT '  ' || key || ' = ' || value FROM config WHERE key IN ('abteilung','meister','start_date')"
done

titel "Anzeigen-Belegung (im Dashboard eingestellt)"
ANZEIGE_DB="${DATA_DIR}/app/lhtpi.db"
[ -f "${ANZEIGE_DB}" ] || ANZEIGE_DB="${PROJEKT}/lhtpi.db"
if [ -f "${ANZEIGE_DB}" ]; then
    belegung=$(frage "${ANZEIGE_DB}" "SELECT s.idx || '|' || COALESCE(s.name,'') || '|' || COALESCE(s.hdmi,'') || '|' || s.enabled || '|' || COALESCE(t.tool,'') || '|' || COALESCE(t.dwell_seconds,'') FROM kiosk_screen s LEFT JOIN kiosk_screen_tool t ON t.screen_id = s.id ORDER BY s.idx, t.sort")
    if [ -n "${belegung}" ]; then
        printf '%s\n' "${belegung}" | while IFS='|' read -r idx name hdmi an tool dwell; do
            if [ -n "${tool}" ]; then
                sag "  Bildschirm ${idx} (${hdmi:-?}, ${name:-ohne Namen}): ${tool}${dwell:+, ${dwell}s}"
            else
                sag "  Bildschirm ${idx} (${hdmi:-?}, ${name:-ohne Namen}): nicht belegt"
            fi
        done
    else
        sag "  keine Einträge – das Gerät fragt beim ersten Start"
    fi
else
    sag "  ${ANZEIGE_DB} fehlt (noch nie gestartet)"
fi

titel "Konfiguration"
for datei in /etc/lhtpi/tools /etc/lhtpi/screens /etc/lhtpi/screen2 /etc/lhtpi/license.key; do
    if [ -e "${datei}" ]; then
        case "${datei}" in
            */license.key) sag "${datei}: vorhanden" ;;
            *) sag "${datei}: $(tr '\n' ' ' < "${datei}")" ;;
        esac
    else
        sag "${datei}: fehlt"
    fi
done

titel "Dienste"
for dienst in lhtpi terminboard safetycross lhtpi-anzeige lhtpi-screen2-watch lhtpi-update; do
    zustand=$(systemctl is-active "${dienst}" 2>/dev/null)
    aktiv=$(systemctl is-enabled "${dienst}" 2>/dev/null)
    printf '%-24s %-10s %s\n' "${dienst}" "${zustand:-?}" "${aktiv:-?}"
done

titel "Update-Mechanismus"
if [ -x /usr/local/bin/lhtpi-update.sh ]; then
    sag "Update-Skript installiert"
else
    sag "Update-Skript fehlt (einmal install.sh nötig)"
fi
[ -f /etc/udev/rules.d/99-lhtpi-usb.rules ] && sag "udev-Regel vorhanden" || sag "udev-Regel fehlt"

titel "Stick"
for punkt in /mnt/lhtpi-usb; do
    if mountpoint -q "${punkt}" 2>/dev/null; then
        sag "${punkt}: eingehängt"
        ls "${punkt}" 2>/dev/null | head -8 | sed 's/^/  /'
    else
        sag "${punkt}: nicht eingehängt"
    fi
done

titel "Bildschirme (X)"
if command -v xrandr >/dev/null 2>&1 && [ -n "${DISPLAY:-}" ]; then
    xrandr --query 2>/dev/null | grep -E ' connected' | sed 's/^/  /'
else
    sag "xrandr ohne DISPLAY nicht abfragbar – auf dem Pi als pi-Benutzer mit DISPLAY=:0"
fi

sag ""
sag "Fertig – nichts geändert."
