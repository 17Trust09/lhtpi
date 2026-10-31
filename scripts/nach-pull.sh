#!/bin/bash
# LHTPi: nach einem git pull nachziehen.
#
# Wird vom post-merge-Haken aufgerufen. Diese Datei liegt im Repository und
# wird mit jedem Pull aktualisiert - der Haken selbst bleibt schlank und muss
# deshalb nur ein einziges Mal eingerichtet werden.
set -u

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "${REPO}" || exit 0

geaendert="$(git diff --name-only 'HEAD@{1}' HEAD 2>/dev/null || true)"
[ -z "${geaendert}" ] && exit 0

# ── Systemteile (Kiosk, Bildschirme, Freigaben) ────────────────────────────
# Zuerst, weil kiosk-neu.sh die sudo-Freigaben setzt - die Dienste weiter unten
# brauchen sie schon.
# Wichtig: absoluter Pfad. Die sudo-Freigabe lautet auf den vollen Pfad; ein
# relatives "scripts/kiosk-neu.sh" passt nicht darauf, sudo fragt dann nach dem
# Passwort - und genau das ist stillschweigend passiert.
if printf '%s\n' "${geaendert}" | grep -qE '^(install\.sh|scripts/)'; then
    echo "LHTPi: Systemteile geändert - Bildschirme und Einstellungen werden nachgezogen."
    systemteile=1
    SKRIPT="${REPO}/scripts/kiosk-neu.sh"
    if [ -x "${SKRIPT}" ]; then
        if ! sudo -n bash "${SKRIPT}"; then
            echo
            echo "LHTPi: Nachziehen braucht root. Einmal ausführen:"
            echo "  sudo bash ${SKRIPT}"
        fi
    fi
fi

# ── Dienste neu starten ────────────────────────────────────────────────────
# Ein git pull tauscht Dateien, die laufende App behaelt aber den alten Code im
# Speicher. Ohne Neustart wirkt eine Aenderung erst beim naechsten Boot - und
# niemand denkt daran.
starte_dienst() {
    local dienst="$1"
    sudo -n systemctl restart "${dienst}" >/dev/null 2>&1 && {
        echo "  ${dienst} neu gestartet."
        return 0
    }
    echo "  ${dienst} konnte nicht neu gestartet werden (Freigabe fehlt?)."
    return 1
}

neu_gestartet=0
systemteile=0

# Safety Cross aus dem Repo nach /opt/safety-cross synchronisieren (nur Code:
# .py + templates/ + static/). license.key, .secret, venv und DB bleiben
# unangetastet - sonst waere die Lizenz/Anmeldung nach einem Pull weg.
sync_safetycross() {
    local src="${REPO}/tools/safety-cross"
    local dst="/opt/safety-cross"
    [ -d "${dst}" ] || return 0
    for f in app.py auth.py db.py license.py requirements.txt; do
        [ -f "${src}/${f}" ] && cp "${src}/${f}" "${dst}/${f}"
    done
    rm -rf "${dst}/templates" "${dst}/static"
    cp -r "${src}/templates" "${dst}/templates" 2>/dev/null
    cp -r "${src}/static" "${dst}/static" 2>/dev/null
    return 0
}

if printf '%s\n' "${geaendert}" | grep -qE '^terminboard/'; then
    starte_dienst terminboard.service && neu_gestartet=1
fi
# Haupt-App: .py-Dateien im Wurzel sowie templates/ und static/.
if printf '%s\n' "${geaendert}" | grep -qE '(^[^/]+\.py$|^templates/|^static/)'; then
    starte_dienst lhtpi.service && neu_gestartet=1
fi
if printf '%s\n' "${geaendert}" | grep -qE '^tools/safety-cross/'; then
    sync_safetycross && starte_dienst safetycross.service && neu_gestartet=1
fi

if [ "${neu_gestartet}" = "0" ] && [ "${systemteile}" = "0" ]; then
    echo "LHTPi: keine Aenderung, die einen Neustart braucht."
fi

# Zustand zeigen: ob ein Fenster da ist, sieht man am Dienst allein nicht.
if [ -x "${REPO}/scripts/diagnose.sh" ]; then
    echo
    bash "${REPO}/scripts/diagnose.sh" --kurz
fi

exit 0
