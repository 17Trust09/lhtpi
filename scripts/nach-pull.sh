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

# ── Terminboard: DB-Sicherung und Healthcheck ────────────────────────────────

terminboard_db_pfad() {
    # Feste Produktionspfade, identisch zum Root-Helfer
    # scripts/terminboard-db-backup.py (dort PRIMAER_DB/LEGACY_DB). Kein
    # TERMINBOARD_DB, kein LHTPI_DATA_DIR: die Erkennung darf nicht über die
    # Umgebung auf einen anderen Pfad laufen als der Helfer tatsächlich sichert.
    local neu="/var/lib/lhtpi/terminboard/terminboard.db"
    local alt="/home/pi/lhtpi/terminboard/terminboard.db"
    [ -f "${neu}" ] && { echo "${neu}"; return 0; }
    [ -f "${alt}" ] && { echo "${alt}"; return 0; }
    echo "${neu}"
}

sicher_terminboard_db() {
    # Vor dem Neustart einen konsistenten Snapshot der Live-DB anlegen. Das
    # macht ein Root-Helfer (sqlite3-Backup-API inkl. WAL) - ein blosses cp
    # als pi-Benutzer koennte eine halb geschriebene -wal-Datei mitkopieren
    # und so eine unbrauchbare Sicherung hinterlassen. Schlaegt die Sicherung
    # fehl, bricht der Pull ab: eine kaputte DB ohne Sicherung ist schlimmer
    # als ein fehlender Neustart.
    local db
    db="$(terminboard_db_pfad)" || return 0
    if [ ! -f "${db}" ]; then
        echo "  Terminboard-DB nicht gefunden (${db}) - keine Sicherung."
        return 0
    fi
    if ! sudo -n /usr/local/sbin/lhtpi-terminboard-backup; then
        echo "  FEHLER: Terminboard-DB-Sicherung fehlgeschlagen (${db})." >&2
        return 1
    fi
    return 0
}

pruefe_terminboard() {
    # Nach dem Neustart muss die App antworten. Beide Seiten werden bis zu
    # insgesamt ca. 30 s wiederholt angefragt - der Neustart braucht einen
    # Moment, bis Flask die DB-Migration durch hat. Ein Fehlschlag wird als
    # Fehlschlag gemeldet, damit er in der git-pull-Ausgabe sichtbar wird.
    local basis="http://127.0.0.1:${TERMINBOARD_PORT:-8001}"
    local probe start jetzt max_sec schritt
    max_sec="${TERMINBOARD_HEALTHCHECK_SEKUNDEN:-30}"
    schritt="${TERMINBOARD_HEALTHCHECK_SCHRITT:-1}"
    start="$(date +%s)"
    for probe in "/login" "/board/api/status"; do
        while true; do
            if curl -fsS --max-time 2 "${basis}${probe}" >/dev/null 2>&1; then
                break
            fi
            jetzt="$(date +%s)"
            if [ $((jetzt - start)) -ge "${max_sec}" ]; then
                echo "  FEHLER: Terminboard antwortet nicht auf ${probe} (nach ${max_sec} s)."
                return 1
            fi
            sleep "${schritt}"
        done
    done
    echo "  Terminboard antwortet auf /login und /board/api/status."
    return 0
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
    # Sicher synchronisieren: erst kopieren (ueberschreibt), nie zuerst loeschen.
    # Ein fehlgeschlagenes Kopieren darf die vorhandenen Templates nicht loeschen -
    # sonst zeigt der Kiosk nach einem Pull nur noch ein schwarzes Bild.
    [ -d "${src}/templates" ] && { mkdir -p "${dst}/templates"; cp -r "${src}/templates/." "${dst}/templates/"; }
    [ -d "${src}/static" ] && { mkdir -p "${dst}/static"; cp -r "${src}/static/." "${dst}/static/"; }
    return 0
}

if printf '%s\n' "${geaendert}" | grep -qE '^terminboard/'; then
    # Abhängigkeiten idempotent nachziehen, wenn sich die requirements geändert
    # haben – so wirkt eine neue Python-Abhängigkeit schon beim ersten Pull.
    if printf '%s\n' "${geaendert}" | grep -qE '^terminboard/requirements\.txt$'; then
        VENV="${REPO}/terminboard/venv"
        if [ -x "${VENV}/bin/pip" ]; then
            echo "LHTPi: Terminboard-Anforderungen geändert – installiere ins venv."
            if "${VENV}/bin/pip" install -r "${REPO}/terminboard/requirements.txt" -q; then
                echo "  Terminboard-Abhängigkeiten aktualisiert."
            else
                echo "LHTPi: Terminboard-Abhängigkeiten ließen sich nicht installieren – kein Neustart." >&2
                exit 1
            fi
        else
            echo "LHTPi: ${VENV} fehlt – Abhängigkeiten nicht installiert – kein Neustart." >&2
            exit 1
        fi
    fi

    # Vor dem Neustart die Live-DB sichern (überlebt eine fehlgeschlagene
    # Migration). Danach neu starten und per Healthcheck prüfen – ein Fehlschlag
    # bricht den Pull mit sichtbarem Fehler ab.
    if ! sicher_terminboard_db; then
        echo "LHTPi: Terminboard-DB konnte nicht gesichert werden – kein Neustart." >&2
        exit 1
    fi

    if starte_dienst terminboard.service; then
        neu_gestartet=1
        if ! pruefe_terminboard; then
            echo "LHTPi: Terminboard-Healthcheck fehlgeschlagen." >&2
            exit 1
        fi
    else
        echo "LHTPi: Terminboard konnte nicht neu gestartet werden." >&2
        exit 1
    fi
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
