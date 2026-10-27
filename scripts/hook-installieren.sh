#!/bin/bash
# LHTPi: Haken für git pull einrichten.
#
# Einmal ausführen:   bash scripts/hook-installieren.sh
#
# Danach genügt bei jeder Änderung ein "git pull", und alles Weitere passiert
# von selbst: Kiosk-Skripte erneuern, Systemeinstellungen nachziehen, Dienste
# neu starten.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="${REPO}/.git/hooks/post-merge"
PI_USER="${LHTPI_USER:-pi}"

[ -d "${REPO}/.git" ] || { echo "FEHLER: ${REPO} ist kein Git-Verzeichnis." >&2; exit 1; }

# ── 1. Haken schreiben ─────────────────────────────────────────────────────
cat > "${HOOK}" <<'HOOK_EOF'
#!/bin/bash
# Nach jedem git pull: nur wenn Systemteile betroffen sind, nachziehen.
#
# Der Haken gehört nicht ins Repository (Hooks werden nicht versioniert),
# deshalb legt ihn scripts/hook-installieren.sh an.

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "${REPO}" || exit 0

# Hat sich etwas geändert, das Systemdateien betrifft?
geaendert="$(git diff --name-only 'HEAD@{1}' HEAD 2>/dev/null || true)"
if [ -z "${geaendert}" ]; then
    exit 0
fi
if ! printf '%s\n' "${geaendert}" | grep -qE '^(install\.sh|scripts/)'; then
    echo "LHTPi: nur Programmdateien geändert - kein Nachziehen nötig."
    exit 0
fi

echo "LHTPi: Systemteile geändert - Bildschirme und Einstellungen werden nachgezogen."
if [ -x scripts/kiosk-neu.sh ]; then
    sudo -n bash scripts/kiosk-neu.sh || \
        echo "LHTPi: Nachziehen nicht möglich (kein sudo ohne Passwort). Bitte: sudo bash scripts/kiosk-neu.sh"
fi

# Läuft ein Bildschirm nicht, direkt die Diagnose zeigen - dann muss niemand
# Befehle abtippen, um den Zustand zu melden.
# Diagnose immer zeigen: ob ein Fenster da ist, sieht man am Dienst allein
# nicht - der Dienst kann laufen, waehrend Chromium auf dem falschen Ausgang
# sitzt.
if [ -x scripts/diagnose.sh ]; then
    echo
    echo "LHTPi: Zustand der Anzeige nach dem Nachziehen:"
    bash scripts/diagnose.sh --kurz
fi
HOOK_EOF

chmod 0755 "${HOOK}"
echo "  Haken angelegt: ${HOOK}"

# ── 2. Erlauben, dass der Haken ohne Passwort nachzieht ────────────────────
tmp="$(mktemp)"
cat > "${tmp}" <<SUDO_EOF
${PI_USER} ALL=(root) NOPASSWD: /usr/bin/bash ${REPO}/scripts/kiosk-neu.sh, /bin/bash ${REPO}/scripts/kiosk-neu.sh, /usr/local/bin/lhtpi-screens.sh
SUDO_EOF
if visudo -c -f "${tmp}" >/dev/null 2>&1; then
    install -m 0440 -o root -g root "${tmp}" /etc/sudoers.d/022_lhtpi-pull
    echo "  Freigabe gesetzt: /etc/sudoers.d/022_lhtpi-pull"
else
    echo "  WARNUNG: Freigabe nicht gesetzt - nach dem Pull bitte selbst"
    echo "           sudo bash scripts/kiosk-neu.sh ausführen."
fi
rm -f "${tmp}"

echo
echo "Fertig. Ab jetzt genügt:"
echo "  cd ${REPO} && git pull"
