#!/bin/bash
# LHTPi: Update von einem USB-Stick einspielen.
#
# Aufruf (als root):  lhtpi-update.sh [--probe]
#
# Erwartet auf dem Stick (Hauptverzeichnis):
#   lhtpi-update/version.json      {"version": "1.2.0", ...}
#   lhtpi-update/app/              → Inhalt nach /home/pi/lhtpi
#   lhtpi-update/terminboard/      → Inhalt nach /home/pi/lhtpi/terminboard
#   lhtpi-update/safety-cross/     → Inhalt nach /opt/safety-cross
#
# Oder ein Archiv lhtpi-update.tar.gz mit derselben Struktur.
#
# Grundsatz: Es werden AUSSCHLIESSLICH Programmdateien ersetzt.
#   /etc/lhtpi/*        (Tool-Auswahl, Bildschirme, Lizenz)  → unberührt
#   /var/lib/lhtpi/*    (Datenbanken, Uploads, Berichte)     → unberührt
#   venv                → bleibt stehen, nur Abhängigkeiten werden nachgezogen
#
# Das alte Programmverzeichnis wird vorher gesichert (/var/backups/…), damit
# ein Update notfalls zurückgedreht werden kann.

set -uo pipefail

STICK="${LHTPI_USB_MOUNT:-/mnt/lhtpi-usb}"
PROJEKT="${LHTPI_PROJECT_DIR:-/home/pi/lhtpi}"
TERMIN="${LHTPI_TERMIN_DIR:-${PROJEKT}/terminboard}"
SAFETYCROSS="${LHTPI_SC_DIR:-/opt/safety-cross}"
VERSIONSDATEI="${LHTPI_VERSION_FILE:-/etc/lhtpi/version}"
BACKUP_WURZEL="${LHTPI_BACKUP_DIR:-/var/backups}"
DIENSTE="${LHTPI_SERVICES:-lhtpi terminboard safetycross}"
PI_USER="${LHTPI_USER:-pi}"
RW_HELFER="/usr/local/bin/lhtpi-usb-rw.sh"

PROBE=0
[ "${1:-}" = "--probe" ] && PROBE=1

LOG_ZIEL="${STICK}/LHTPi-Update.log"

sag() {
    echo "$*"
    if [ -w "${STICK}" ] 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S')  $*" >> "${LOG_ZIEL}" 2>/dev/null || true
    fi
}

abbrechen() {
    sag "ABBRUCH: $*"
    sag "Es wurde nichts verändert."
    exit 1
}

# ── Stick beschreibbar machen (für Protokoll und Markierung) ───────────────
stick_rw() {
    [ -x "${RW_HELFER}" ] && "${RW_HELFER}" rw >/dev/null 2>&1 || true
}
stick_ro() {
    [ -x "${RW_HELFER}" ] && "${RW_HELFER}" ro >/dev/null 2>&1 || true
}
trap stick_ro EXIT

# ── 1. Update-Paket finden ─────────────────────────────────────────────────
[ -d "${STICK}" ] || { sag "Kein Stick unter ${STICK}."; exit 0; }
stick_rw

PAKET=""
if [ -f "${STICK}/lhtpi-update/version.json" ]; then
    PAKET="${STICK}/lhtpi-update"
elif [ -f "${STICK}/lhtpi-update.tar.gz" ]; then
    ENTPACK="${STICK}/.lhtpi-update-entpackt"
    rm -rf "${ENTPACK}"
    mkdir -p "${ENTPACK}"
    if ! tar -xzf "${STICK}/lhtpi-update.tar.gz" -C "${ENTPACK}" 2>/dev/null; then
        abbrechen "Archiv lhtpi-update.tar.gz ließ sich nicht entpacken."
    fi
    if [ -f "${ENTPACK}/lhtpi-update/version.json" ]; then
        PAKET="${ENTPACK}/lhtpi-update"
    elif [ -f "${ENTPACK}/version.json" ]; then
        PAKET="${ENTPACK}"
    else
        abbrechen "Im Archiv fehlt version.json."
    fi
fi

if [ -z "${PAKET}" ]; then
    # Kein Update auf dem Stick – das ist der Normalfall, kein Fehler.
    exit 0
fi

NEUE_VERSION="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${PAKET}/version.json" | head -1)"
[ -n "${NEUE_VERSION}" ] || abbrechen "version.json enthält keine Version."

ALTE_VERSION="$(cat "${VERSIONSDATEI}" 2>/dev/null | tr -d '[:space:]')"
ALTE_VERSION="${ALTE_VERSION:-0.0.0}"

sag "Gefundene Version: ${NEUE_VERSION} (installiert: ${ALTE_VERSION})"

# ── 2. Schon eingespielt? ──────────────────────────────────────────────────
if [ "${NEUE_VERSION}" = "${ALTE_VERSION}" ]; then
    sag "Version ${NEUE_VERSION} ist bereits installiert – nichts zu tun."
    exit 0
fi

if [ "${PROBE}" = "1" ]; then
    sag "Probelauf: Version ${NEUE_VERSION} würde eingespielt."
    sag "Programm: ${PROJEKT} / ${TERMIN} / ${SAFETYCROSS}"
    exit 0
fi

# ── 3. Pflichtdateien prüfen ───────────────────────────────────────────────
for zweig in app terminboard safety-cross; do
    [ -d "${PAKET}/${zweig}" ] || abbrechen "Im Paket fehlt der Ordner ${zweig}."
done
[ -f "${PAKET}/app/app.py" ] || abbrechen "app/app.py fehlt – unvollständiges Paket."
[ -f "${PAKET}/terminboard/app.py" ] || abbrechen "terminboard/app.py fehlt."
[ -f "${PAKET}/safety-cross/app.py" ] || abbrechen "safety-cross/app.py fehlt."

# ── 4. Dienste anhalten (vor der Sicherung, damit die Datenbanken ruhen) ───
if command -v systemctl >/dev/null 2>&1 && [ "${LHTPI_SKIP_SERVICES:-0}" != "1" ]; then
    for dienst in ${DIENSTE}; do
        systemctl stop "${dienst}" >/dev/null 2>&1 || true
    done
    sag "Dienste angehalten."
else
    sag "Dienste nicht angehalten (kein systemctl/Testlauf)."
fi

# ── 5. Sicherung des alten Stands ──────────────────────────────────────────
ZEITSTEMPEL="$(date '+%Y%m%d-%H%M%S')"
SICHERUNG="${BACKUP_WURZEL}/lhtpi-update-${ALTE_VERSION}-${ZEITSTEMPEL}"
mkdir -p "${SICHERUNG}" || abbrechen "Sicherungsordner ${SICHERUNG} nicht anlegbar."

for quelle in "${PROJEKT}" "${TERMIN}" "${SAFETYCROSS}"; do
    [ -d "${quelle}" ] || continue
    name="$(echo "${quelle}" | sed 's|/|_|g')"
    # venv und Caches nicht mitsichern – das bläht die Sicherung nur auf
    tar -czf "${SICHERUNG}/${name}.tar.gz" \
        --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' \
        -C "$(dirname "${quelle}")" "$(basename "${quelle}")" 2>/dev/null \
        || abbrechen "Sicherung von ${quelle} fehlgeschlagen."
done
sag "Sicherung angelegt: ${SICHERUNG}"

# ── 6. Programmdateien ersetzen ────────────────────────────────────────────
# Kopiert wird ausschließlich Inhalt der drei Paketordner. Datenbanken,
# Uploads und Konfiguration liegen woanders und werden nicht berührt.
kopiere() {
    local quelle="$1" ziel="$2"
    if [ ! -d "${ziel}" ]; then
        mkdir -p "${ziel}" || return 1
    fi
    # --delete wäre falsch: es würde z. B. venv entfernen.
    tar -C "${quelle}" -cf - . 2>/dev/null | tar -C "${ziel}" -xf - 2>/dev/null
}

kopiere "${PAKET}/app" "${PROJEKT}" || abbrechen "Kopieren nach ${PROJEKT} fehlgeschlagen."
kopiere "${PAKET}/terminboard" "${TERMIN}" || abbrechen "Kopieren nach ${TERMIN} fehlgeschlagen."
kopiere "${PAKET}/safety-cross" "${SAFETYCROSS}" || abbrechen "Kopieren nach ${SAFETYCROSS} fehlgeschlagen."
sag "Programmdateien ersetzt."

# ── 7. Abhängigkeiten nachziehen ───────────────────────────────────────────
if [ -x "${PROJEKT}/venv/bin/pip" ] && [ -f "${PROJEKT}/requirements.txt" ]; then
    sudo -u "${PI_USER}" "${PROJEKT}/venv/bin/pip" install -q -r "${PROJEKT}/requirements.txt" \
        >/dev/null 2>&1 && sag "Abhängigkeiten der Haupt-App aktualisiert." \
        || sag "WARNUNG: Abhängigkeiten der Haupt-App konnten nicht aktualisiert werden."
fi
if [ -x "${TERMIN}/venv/bin/pip" ] && [ -f "${TERMIN}/requirements.txt" ]; then
    sudo -u "${PI_USER}" "${TERMIN}/venv/bin/pip" install -q -r "${TERMIN}/requirements.txt" \
        >/dev/null 2>&1 && sag "Abhängigkeiten des Terminboards aktualisiert." \
        || sag "WARNUNG: Abhängigkeiten des Terminboards nicht aktualisiert."
fi

# Besitzrechte geraderücken (Kopieren als root setzt sonst root:root)
chown -R "${PI_USER}:${PI_USER}" "${PROJEKT}" 2>/dev/null || true

# ── 8. Dienste starten und prüfen ──────────────────────────────────────────
FEHLER=""
if ! command -v systemctl >/dev/null 2>&1; then
    sag "systemctl nicht vorhanden – Dienststart übersprungen."
elif [ "${LHTPI_SKIP_SERVICES:-0}" = "1" ]; then
    sag "Dienststart übersprungen (Testlauf)."
else
    for dienst in ${DIENSTE}; do
        systemctl start "${dienst}" >/dev/null 2>&1 || true
        sleep 2
        if systemctl is-active --quiet "${dienst}"; then
            sag "Dienst ${dienst}: läuft"
        else
            FEHLER="${FEHLER} ${dienst}"
            sag "Dienst ${dienst}: NICHT gestartet"
        fi
    done
fi

# ── 9. Ergebnis festhalten ─────────────────────────────────────────────────
mkdir -p "$(dirname "${VERSIONSDATEI}")"
if [ -z "${FEHLER}" ]; then
    echo "${NEUE_VERSION}" > "${VERSIONSDATEI}"
    sag "Update auf ${NEUE_VERSION} abgeschlossen."
    ERGEBNIS="erledigt"
else
    # Version NICHT hochschreiben, damit das Update wiederholbar bleibt.
    sag "Update unvollständig – folgende Dienste starten nicht:${FEHLER}"
    sag "Sicherung liegt unter ${SICHERUNG}"
    ERGEBNIS="fehler"
fi

# Paket auf dem Stick markieren, damit es nicht erneut läuft
if [ -d "${STICK}/lhtpi-update" ]; then
    mv "${STICK}/lhtpi-update" "${STICK}/lhtpi-update.${ERGEBNIS}" 2>/dev/null || true
fi
if [ -f "${STICK}/lhtpi-update.tar.gz" ]; then
    mv "${STICK}/lhtpi-update.tar.gz" "${STICK}/lhtpi-update.${ERGEBNIS}.tar.gz" 2>/dev/null || true
fi

[ -z "${FEHLER}" ] && exit 0 || exit 1
