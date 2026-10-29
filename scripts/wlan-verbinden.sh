#!/bin/bash
# LHTPi: WLAN-Profil anlegen, ohne lange Befehle abzutippen.
#
# Warum es das gibt: "nmcli device wifi connect ..." ist eine lange Zeile, und
# wenn das Geraet schon mit einem Netz verbunden ist, scheitert sie mit
# "key-mgmt: property is missing" - dann muss man die Sicherheitseinstellungen
# von Hand setzen, und das wird am Bildschirm zur Tipperei.
#
# Dieses Skript fragt nur zwei Dinge: welches Netz, und welches Passwort.
# Das Passwort wird nicht angezeigt und landet nicht in der Befehlshistorie.
#
# Aufruf (als root):  sudo bash scripts/wlan-verbinden.sh
set -u

[ "$(id -u)" = "0" ] || { echo "Bitte mit sudo starten: sudo bash $0"; exit 1; }

sag() { echo "  $*"; }

echo "===== WLAN einrichten ====="
echo

# ── Geraet ────────────────────────────────────────────────────────────────
wlan="$(nmcli -t -f DEVICE,TYPE device 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}')"
if [ -z "${wlan}" ]; then
    echo "Kein WLAN-Geraet gefunden. Pruefen:"
    echo "  sudo raspi-config  ->  5 Localisation Options  ->  L4 WLAN Country"
    exit 1
fi
sag "Geraet: ${wlan}"

# ── Verfuegbare Netze ─────────────────────────────────────────────────────
echo
echo "Verfuegbare Netze:"
nmcli -t -f SSID,SIGNAL,SECURITY device wifi list 2>/dev/null \
    | awk -F: 'NF && $1!="" {printf "  %-28s %3s%%  %s\n", $1, $2, $3}' \
    | head -12
echo

# ── Eingaben ──────────────────────────────────────────────────────────────
aktuell="$(iwgetid -r 2>/dev/null || true)"
vorschlag="${aktuell:-}"
[ -n "${vorschlag}" ] && echo "  (aktuell verbunden mit: ${vorschlag})"

printf 'SSID%s: ' "${vorschlag:+ [$vorschlag]}"
read -r eingabe
ssid="${eingabe:-${vorschlag}}"
if [ -z "${ssid}" ]; then
    echo "Ohne SSID geht es nicht."
    exit 1
fi

# Passwort verdeckt lesen. Es landet damit nicht in der Historie und nicht
# auf dem Bildschirm - bei einem Hotspot-Passwort ist das der Punkt.
printf 'Passwort fuer "%s" (wird nicht angezeigt): ' "${ssid}"
stty -echo 2>/dev/null || true
read -r passwort
stty echo 2>/dev/null || true
echo

if [ -z "${passwort}" ]; then
    echo "Kein Passwort eingegeben. Bei einem offenen Netz bitte leer bestaetigen."
    printf 'Wirklich ohne Passwort fortfahren? [j/N] '
    read -r antwort
    case "${antwort}" in j|J|y|Y) : ;; *) echo "Abgebrochen."; exit 1 ;; esac
fi

# ── Profil anlegen oder ergaenzen ─────────────────────────────────────────
# Existiert schon eines mit diesem Namen, wird es aktualisiert - sonst
# entstehen Dubletten mit widersprechenden Einstellungen.
if nmcli -t -f NAME connection show 2>/dev/null | grep -qxF "${ssid}"; then
    sag "Profil existiert - wird aktualisiert."
    nmcli connection modify "${ssid}" \
        connection.interface-name "${wlan}" \
        wifi.ssid "${ssid}" >/dev/null 2>&1
else
    nmcli connection add type wifi con-name "${ssid}" \
        ifname "${wlan}" ssid "${ssid}" >/dev/null 2>&1 || {
            echo "Profil konnte nicht angelegt werden."
            exit 1
        }
    sag "Profil angelegt."
fi

# Die Zeile, die bei "key-mgmt: property is missing" gefehlt hat.
if [ -n "${passwort}" ]; then
    nmcli connection modify "${ssid}" \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.psk "${passwort}" >/dev/null 2>&1 || {
            sed 's/^/  /' <<'EOF'
Konnte die Sicherheitseinstellungen nicht setzen.
Moeglich: Das Passwort ist zu kurz (WPA verlangt mindestens 8 Zeichen)
oder das Netz nutzt eine andere Verschluesselung (WPA3/Enterprise).
EOF
            exit 1
        }
fi

# Ohne diese zwei Zeilen verbindet er erst nach einer Anmeldung, und beim
# Booten bleibt er offline.
nmcli connection modify "${ssid}" \
    connection.autoconnect yes \
    wifi-sec.psk-flags 0 >/dev/null 2>&1

# ── Verbinden ─────────────────────────────────────────────────────────────
echo
sag "verbinde ..."
if nmcli connection up "${ssid}" >/dev/null 2>&1; then
    sag "verbunden."
else
    echo "  Verbindung fehlgeschlagen."
    echo "  Details:"
    nmcli connection up "${ssid}" 2>&1 | tail -3 | sed 's/^/    /'
fi

# ── Ergebnis ──────────────────────────────────────────────────────────────
echo
echo "--- Stand jetzt"
nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device 2>/dev/null \
    | grep ':wifi:' | sed 's/^/  /'
sag "IP: $(hostname -I 2>/dev/null)"
echo
sag "Profil steht dauerhaft: verbindet sich beim Start von selbst."
