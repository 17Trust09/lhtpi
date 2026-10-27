#!/bin/bash
# LHTPi: Haken für git pull einrichten.
#
# Einmal ausführen:   sudo bash scripts/hook-installieren.sh
#
# Danach genügt bei jeder Änderung ein "git pull", und alles Weitere passiert
# von selbst. Der Haken ist absichtlich winzig: die Arbeit steckt in
# scripts/nach-pull.sh, und die kommt mit jedem Pull aktuell ins Haus.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="${REPO}/.git/hooks/post-merge"
PI_USER="${LHTPI_USER:-pi}"

[ -d "${REPO}/.git" ] || { echo "FEHLER: ${REPO} ist kein Git-Verzeichnis." >&2; exit 1; }
[ -f "${REPO}/scripts/nach-pull.sh" ] || { echo "FEHLER: scripts/nach-pull.sh fehlt." >&2; exit 1; }

# ── 1. Haken schreiben ─────────────────────────────────────────────────────
cat > "${HOOK}" <<'HOOK_ENDE'
#!/bin/bash
# Nach jedem git pull: die eigentliche Arbeit steckt in scripts/nach-pull.sh.
# Diese Datei ist absichtlich winzig - sie muss nur einmal eingerichtet werden,
# Aenderungen kommen ueber das Repository.
REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -x "${REPO}/scripts/nach-pull.sh" ] || exit 0
exec bash "${REPO}/scripts/nach-pull.sh"
HOOK_ENDE

chmod 0755 "${HOOK}"
echo "  Haken angelegt: ${HOOK}"

# ── 2. Erlauben, dass der Haken ohne Passwort nachzieht ────────────────────
# Absoluter Pfad ist Pflicht: die Freigabe gilt fuer den vollen Pfad, ein
# relatives "scripts/kiosk-neu.sh" passt nicht darauf, sudo fragt dann nach dem
# Passwort - genau das ist passiert und niemand hat es bemerkt.
tmp="$(mktemp)"
cat > "${tmp}" <<SUDO_ENDE
${PI_USER} ALL=(root) NOPASSWD: /usr/bin/bash ${REPO}/scripts/kiosk-neu.sh, /bin/bash ${REPO}/scripts/kiosk-neu.sh, /usr/bin/bash ${REPO}/scripts/nach-pull.sh, /bin/bash ${REPO}/scripts/nach-pull.sh, /usr/local/bin/lhtpi-screens.sh
SUDO_ENDE
if visudo -c -f "${tmp}" >/dev/null 2>&1; then
    install -m 0440 -o root -g root "${tmp}" /etc/sudoers.d/022_lhtpi-pull
    echo "  Freigabe gesetzt: /etc/sudoers.d/022_lhtpi-pull"
else
    echo "  WARNUNG: Freigabe nicht gesetzt - bitte selbst ausführen:"
    echo "           sudo bash ${REPO}/scripts/kiosk-neu.sh"
fi
rm -f "${tmp}"

# ── 3. Gleich einmal ausprobieren ──────────────────────────────────────────
if sudo -n bash "${REPO}/scripts/kiosk-neu.sh" >/dev/null 2>&1; then
    echo "  Probe gelaufen: Nachziehen funktioniert ohne Passwort."
else
    echo "  WARNUNG: Probe fehlgeschlagen - bitte ausführen:"
    echo "           sudo bash ${REPO}/scripts/kiosk-neu.sh"
fi

echo
echo "Fertig. Ab jetzt genügt:"
echo "  cd ${REPO} && git pull"
