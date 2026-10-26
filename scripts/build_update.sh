#!/bin/bash
# Baut ein LHTPi-Update-Paket für den Stick.
#
# Aufruf:  scripts/build_update.sh 1.3.0 ["Notiz"]
#          scripts/build_update.sh 1.3.0 "Neue Berichte, ein Excel-Leser"
#
# Ergebnis: dist/lhtpi-update-<version>.tar.gz
#
# Im Paket stehen ausschließlich Programmdateien:
#   app/            → /home/pi/lhtpi
#   terminboard/    → /home/pi/lhtpi/terminboard
#   safety-cross/   → /opt/safety-cross
#
# Nicht enthalten (und das ist Absicht): Datenbanken, uploads, venv, Caches,
# Konfiguration. Alles, was der Kunde eingestellt hat, bleibt am Gerät.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-}"
NOTIZ="${2:-}"
if [ -z "${VERSION}" ] && [ -f "${REPO}/VERSION" ]; then
    VERSION="$(tr -d '[:space:]' < "${REPO}/VERSION")"
fi
if [ -z "${VERSION}" ]; then
    echo "Aufruf: $0 [version] [\"Notiz\"]   (ohne Angabe gilt die Datei VERSION)" >&2
    exit 2
fi
ARBEIT="$(mktemp -d)"
PAKET="${ARBEIT}/lhtpi-update"
DIST="${REPO}/dist"

aufraeumen() { rm -rf "${ARBEIT}"; }
trap aufraeumen EXIT

mkdir -p "${PAKET}/app" "${PAKET}/terminboard" "${PAKET}/safety-cross"

# Kopiert wird mit tar (überall vorhanden) – nur Programmdateien, niemals
# Datenbanken, Uploads oder das venv.
kopiere() {
    local quelle="$1" ziel="$2"
    shift 2
    ( cd "${quelle}" && tar -cf - "$@" . 2>/dev/null ) | ( cd "${ziel}" && tar -xf - )
}

# ── Haupt-App ──────────────────────────────────────────────────────────────
kopiere "${REPO}" "${PAKET}/app" \
    --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='uploads' --exclude='*.db' --exclude='*.sqlite*' \
    --exclude='docs' --exclude='dist' --exclude='.git' \
    --exclude='test_*.py' --exclude='run-tests.sh'

# ── Terminboard ────────────────────────────────────────────────────────────
kopiere "${REPO}/terminboard" "${PAKET}/terminboard" \
    --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='uploads' --exclude='*.db' --exclude='*.sqlite*' \
    --exclude='tests'

# ── Safety-Cross ───────────────────────────────────────────────────────────
kopiere "${REPO}/tools/safety-cross" "${PAKET}/safety-cross" \
    --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='*.db' --exclude='*.sqlite*' \
    --exclude='tests' --exclude='docs'


# ── Pflichtdateien prüfen, bevor ein Paket entsteht ────────────────────────
for datei in app/app.py terminboard/app.py safety-cross/app.py; do
    if [ ! -f "${PAKET}/${datei}" ]; then
        echo "FEHLER: ${datei} fehlt im Paket – Abbruch." >&2
        exit 1
    fi
done

# ── Versionsinformation ────────────────────────────────────────────────────
cat > "${PAKET}/version.json" <<JSON
{
  "version": "${VERSION}",
  "datum": "$(date '+%Y-%m-%d')",
  "notiz": "${NOTIZ}",
  "teile": ["app", "terminboard", "safety-cross"]
}
JSON

# ── Packen ─────────────────────────────────────────────────────────────────
mkdir -p "${DIST}"
ZIEL="${DIST}/lhtpi-update-${VERSION}.tar.gz"
tar -czf "${ZIEL}" -C "${ARBEIT}" lhtpi-update

echo "Paket gebaut: ${ZIEL}"
echo "Größe: $(du -h "${ZIEL}" | cut -f1)"
echo
echo "Auf den Stick: Inhalt entpacken, sodass"
echo "  <Stick>/lhtpi-update/version.json"
echo "  <Stick>/lhtpi-update/app/..."
echo "  <Stick>/lhtpi-update/terminboard/..."
echo "  <Stick>/lhtpi-update/safety-cross/..."
echo "liegt – oder das tar.gz direkt ins Hauptverzeichnis des Sticks legen."
