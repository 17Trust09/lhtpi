#!/bin/bash
# LHTPi: nach einem git pull Systemteile nachziehen.
#
# Wird vom post-merge-Haken aufgerufen. Diese Datei liegt im Repository und
# wird mit jedem Pull aktualisiert - der Haken selbst bleibt schlank und muss
# deshalb nur ein einziges Mal eingerichtet werden.
set -u

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "${REPO}" || exit 0

# Hat sich etwas geändert, das Systemdateien betrifft?
geaendert="$(git diff --name-only 'HEAD@{1}' HEAD 2>/dev/null || true)"
[ -z "${geaendert}" ] && exit 0

if ! printf '%s\n' "${geaendert}" | grep -qE '^(install\.sh|scripts/)'; then
    echo "LHTPi: nur Programmdateien geändert - kein Nachziehen nötig."
    exit 0
fi

echo "LHTPi: Systemteile geändert - Bildschirme und Einstellungen werden nachgezogen."

# Wichtig: absoluter Pfad. Die sudo-Freigabe lautet auf den vollen Pfad; ein
# relatives "scripts/kiosk-neu.sh" passt nicht darauf, sudo fragt dann nach dem
# Passwort - und genau das ist stillschweigend passiert.
SKRIPT="${REPO}/scripts/kiosk-neu.sh"
if [ ! -x "${SKRIPT}" ]; then
    echo "LHTPi: ${SKRIPT} fehlt - nichts nachzuziehen."
    exit 0
fi

if ! sudo -n bash "${SKRIPT}"; then
    echo
    echo "LHTPi: Nachziehen braucht root. Einmal ausführen:"
    echo "  sudo bash ${SKRIPT}"
fi

# Zustand zeigen: ob ein Fenster da ist, sieht man am Dienst allein nicht.
if [ -x "${REPO}/scripts/diagnose.sh" ]; then
    echo
    bash "${REPO}/scripts/diagnose.sh" --kurz
fi
