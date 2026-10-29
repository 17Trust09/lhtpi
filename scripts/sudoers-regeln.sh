#!/bin/bash
# LHTPi: sudo-Regeln an einer Stelle.
#
# Warum das eine eigene Datei ist: Die Regeln standen doppelt - einmal in
# install.sh und einmal in kiosk-neu.sh - und liefen auseinander. Bei einer
# frischen Installation fehlten dadurch Freigaben, die nach einem Update da
# waren. Folge: "Speichern" und der Bildschirm-Waechter taten still nichts,
# weil sudo nach dem Passwort fragte und niemand es eingeben konnte.
#
# Wichtig: sudo vergleicht woertlich. Jede Regel braucht den vollen Pfad, und
# die App ruft genau diesen Pfad auf. Ein relatives "scripts/..." passt nicht.
#
# Aufruf (als root):  bash scripts/sudoers-regeln.sh
set -u

PI_USER="${LHTPI_USER:-pi}"
ZIEL="/etc/sudoers.d/021_lhtpi-screens"

[ "$(id -u)" = "0" ] || { echo "Bitte mit sudo starten: sudo bash $0"; exit 1; }

SCREENS_HELFER="/usr/local/bin/lhtpi-screens.sh"
RETTUNG="/usr/local/bin/lhtpi-anzeige-rettung.sh"
SYSTEMCTL="$(command -v systemctl || echo /usr/bin/systemctl)"

tmp="$(mktemp)"
cat > "${tmp}" <<EOF
# LHTPi - erzeugt von scripts/sudoers-regeln.sh, nicht von Hand aendern.
# Ohne diese Zeilen fragt sudo nach dem Passwort, und die App kann nichts
# nachziehen; der Fehler faellt nur auf, weil das Bild schwarz bleibt.
${PI_USER} ALL=(root) NOPASSWD: ${SCREENS_HELFER}
${PI_USER} ALL=(root) NOPASSWD: ${RETTUNG}
${PI_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL} restart kiosk-screen1
${PI_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL} restart kiosk-screen2
${PI_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL} restart terminboard.service
${PI_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL} restart lhtpi.service
${PI_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL} restart safetycross.service
${PI_USER} ALL=(root) NOPASSWD: /usr/local/bin/lhtpi-usb-rw.sh
# Aufloesung dauerhaft setzen: erlaubt nur Ausgang und Modus, keine freien
# Argumente - sonst waere die Regel ein Freifahrtschein fuer beliebige Befehle.
${PI_USER} ALL=(root) NOPASSWD: /usr/local/bin/lhtpi-cmdline.sh HDMI-1 [0-9]*x[0-9]*
${PI_USER} ALL=(root) NOPASSWD: /usr/local/bin/lhtpi-cmdline.sh HDMI-2 [0-9]*x[0-9]*
EOF

# visudo -c prueft die Syntax. Eine kaputte Datei in sudoers.d kann sudo
# komplett lahmlegen - dann kommt niemand mehr an root.
if command -v visudo >/dev/null 2>&1; then
    if ! visudo -cf "${tmp}" >/dev/null 2>&1; then
        echo "FEHLER: Die erzeugten Regeln sind fehlerhaft - nichts geaendert."
        visudo -cf "${tmp}"
        rm -f "${tmp}"
        exit 1
    fi
fi

install -m 0440 -o root -g root "${tmp}" "${ZIEL}"
rm -f "${tmp}"

echo "  sudo-Regeln geschrieben: ${ZIEL}"
