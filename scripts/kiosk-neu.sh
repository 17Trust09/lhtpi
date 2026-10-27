#!/bin/bash
# LHTPi: Kiosk-Skripte und Bildschirm-Helfer neu einrichten.
#
# Aufruf (als root):  sudo bash scripts/kiosk-neu.sh
#
# Nötig nach einem Update, das nur die Kiosk-Skripte betrifft: die Skripte
# werden von install.sh erzeugt und liegen deshalb nicht im Programmordner.
# Dieses Skript macht nur diesen Teil – keine Pakete, keine Diensteinrichtung.
set -uo pipefail

[ "$(id -u)" = "0" ] || { echo "Bitte mit sudo starten: sudo bash $0"; exit 1; }

REPO="${LHTPI_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PI_USER="${LHTPI_USER:-pi}"
PI_GROUP="${LHTPI_GROUP:-${PI_USER}}"
HELFER="/usr/local/bin/lhtpi-entkoppeln.sh"

sag() { echo "  $*"; }

[ -f "${REPO}/install.sh" ] || { echo "FEHLER: install.sh nicht gefunden in ${REPO}"; exit 1; }

# ── 1. Helfer zum Trennen der Bildschirme ──────────────────────────────────
if grep -q "lhtpi-entkoppeln.sh <<'ENTK_EOF'" "${REPO}/install.sh"; then
    python3 - "${REPO}/install.sh" "${HELFER}" <<'PYEOF'
import pathlib, sys
quelle, ziel = sys.argv[1], sys.argv[2]
s = pathlib.Path(quelle).read_text()
marker = "cat > /usr/local/bin/lhtpi-entkoppeln.sh <<'ENTK_EOF'"
a = s.index(marker)
a = s.index("\n", a) + 1
b = s.index("ENTK_EOF", a)
pathlib.Path(ziel).write_text(s[a:b])
PYEOF
    chmod 0755 "${HELFER}"
    if bash -n "${HELFER}"; then
        sag "Helfer eingerichtet: ${HELFER}"
    else
        echo "FEHLER: ${HELFER} hat einen Syntaxfehler." >&2
        exit 1
    fi
else
    sag "Kein Helfer in install.sh – übersprungen."
fi

# ── 2. Kiosk-Skripte neu erzeugen ──────────────────────────────────────────
for idx in 1 2; do
    ziel="/home/${PI_USER}/start_kiosk_screen${idx}.sh"
    tmp="/tmp/lhtpi-kiosk-${idx}.sh"

    if ! bash -c "source '${REPO}/install.sh'; render_screen_kiosk_script ${idx}" > "${tmp}" 2>/dev/null; then
        echo "FEHLER: Kiosk-Skript ${idx} ließ sich nicht erzeugen." >&2
        exit 1
    fi
    if [ ! -s "${tmp}" ]; then
        echo "FEHLER: Kiosk-Skript ${idx} ist leer." >&2
        exit 1
    fi
    if ! bash -n "${tmp}"; then
        echo "FEHLER: Kiosk-Skript ${idx} hat einen Syntaxfehler." >&2
        exit 1
    fi

    install -m 0755 -o "${PI_USER}" -g "${PI_GROUP}" "${tmp}" "${ziel}" \
        || { echo "FEHLER: ${ziel} ließ sich nicht schreiben." >&2; exit 1; }
    rm -f "${tmp}"
    sag "Kiosk-Skript ${idx} erneuert: ${ziel}"
done

# ── 3. Dienste neu starten ─────────────────────────────────────────────────
if command -v systemctl >/dev/null 2>&1; then
    for dienst in kiosk-screen1 kiosk-screen2; do
        systemctl restart "${dienst}" >/dev/null 2>&1 || true
    done
    sag "Kiosk-Dienste neu gestartet."
fi

# ── 4. Kurz nachsehen, wie die Ausgänge stehen ─────────────────────────────
sleep 3
echo
echo "Bildschirme jetzt:"
DISPLAY=:0 XAUTHORITY="/home/${PI_USER}/.Xauthority" \
    xrandr --query 2>/dev/null | grep -E "^HDMI-[12] connected" || echo "  (nicht abfragbar – kein X oder kein Bildschirm)"
echo
echo "Fertig. Steht bei beiden dieselbe Position, hat der Treiber es nicht "
echo "akzeptiert – dann steht der Grund in /home/${PI_USER}/kiosk-screen2.log"
