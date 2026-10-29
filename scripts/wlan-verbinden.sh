#!/bin/bash
# LHTPi: WLAN einrichten, ohne lange Befehle abzutippen.
#
# Warum es das gibt: "nmcli device wifi connect ..." ist eine lange Zeile, und
# wenn das Geraet schon mit einem Netz verbunden ist, scheitert sie mit
# "key-mgmt: property is missing" - dann muss man die Sicherheitseinstellungen
# von Hand setzen, und das wird am Bildschirm zur Tipperei.
#
# Zwei Wege, weil es zwei Generationen von Raspberry-Pi-Installationen gibt:
#   * NetworkManager (Debian 12/13, aktuell)  -> nmcli
#   * wpa_supplicant (aeltere Installationen) -> wpa_supplicant.conf
# "No supported network connection manager found" aus raspi-config heisst:
# keiner von beiden ist aktiv. Deshalb fragt dieses Skript nicht raspi-config,
# sondern nimmt den Weg, der auf dem Geraet wirklich vorhanden ist.
#
# Aufruf (als root):  sudo bash scripts/wlan-verbinden.sh
set -u

[ "$(id -u)" = "0" ] || { echo "Bitte mit sudo starten: sudo bash $0"; exit 1; }

sag() { echo "  $*"; }

# ── Welcher Dienst verwaltet das WLAN? ────────────────────────────────────
nm_aktiv() {
    command -v nmcli >/dev/null 2>&1 || return 1
    systemctl is-active --quiet NetworkManager 2>/dev/null
}

if nm_aktiv; then
    WEG="networkmanager"
elif command -v wpa_supplicant >/dev/null 2>&1; then
    WEG="wpa_supplicant"
else
    echo "Weder NetworkManager noch wpa_supplicant gefunden."
    echo "Ohne einen von beiden laesst sich WLAN nicht einrichten."
    exit 1
fi

echo "===== WLAN einrichten ====="
sag "Verwaltung: ${WEG}"
echo

# ── Geraet ────────────────────────────────────────────────────────────────
wlan=""
if [ "${WEG}" = "networkmanager" ]; then
    wlan="$(nmcli -t -f DEVICE,TYPE device 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}')"
fi
if [ -z "${wlan}" ]; then
    # Ohne NetworkManager heisst das Geraet wlan0 (oder wlp*).
    wlan="$(ls /sys/class/net 2>/dev/null | grep -E '^(wlan|wlp)' | head -1)"
fi
if [ -z "${wlan}" ]; then
    echo "Kein WLAN-Geraet gefunden (kein wlan0)."
    echo "Pruefen:  ip link  |  rfkill list"
    exit 1
fi
sag "Geraet: ${wlan}"

# ── Verfuegbare Netze ─────────────────────────────────────────────────────
echo
echo "Verfuegbare Netze:"
if [ "${WEG}" = "networkmanager" ]; then
    nmcli -t -f SSID,SIGNAL,SECURITY device wifi list 2>/dev/null \
        | awk -F: 'NF && $1!="" {printf "  %-28s %3s%%  %s\n", $1, $2, $3}' \
        | head -12
else
    # Ohne NetworkManager ueber iw bzw. wpa_cli.
    if command -v iw >/dev/null 2>&1; then
        iw dev "${wlan}" scan 2>/dev/null \
            | awk '/^[ \t]*SSID:/{sub(/^[ \t]*SSID:[ \t]*/, ""); if ($0 != "") print "  " $0}' \
            | sort -u | head -12
    else
        sav=$( (wpa_cli -i "${wlan}" scan && sleep 3 && wpa_cli -i "${wlan}" scan_results) 2>/dev/null \
               | awk -F'\t' 'NR>1 && $5!="" {print "  " $5}' | sort -u | head -12)
        printf '%s\n' "${sav:-  (keine Liste - iw fehlt)}"
    fi
fi
echo

# ── Eingaben ──────────────────────────────────────────────────────────────
aktuell="$(iwgetid -r 2>/dev/null || true)"
[ -n "${aktuell}" ] && echo "  (aktuell verbunden mit: ${aktuell})"

printf 'SSID%s: ' "${aktuell:+ [$aktuell]}"
read -r eingabe
ssid="${eingabe:-${aktuell}}"
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

# ══ Weg 1: NetworkManager ═════════════════════════════════════════════════
if [ "${WEG}" = "networkmanager" ]; then
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

    echo
    sag "verbinde ..."
    if nmcli connection up "${ssid}" >/dev/null 2>&1; then
        sag "verbunden."
    else
        echo "  Verbindung fehlgeschlagen."
        echo "  Details:"
        nmcli connection up "${ssid}" 2>&1 | tail -3 | sed 's/^/    /'
    fi

    echo
    echo "--- Stand jetzt"
    nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device 2>/dev/null \
        | grep ':wifi:' | sed 's/^/  /'
    sag "IP: $(hostname -I 2>/dev/null)"
    echo
    sag "Profil steht dauerhaft: verbindet sich beim Start von selbst."
    exit 0
fi

# ══ Weg 2: wpa_supplicant ═════════════════════════════════════════════════
# Hier gibt es keine Profile im NetworkManager, sondern eine Textdatei mit
# einem Block je Netz. Der Block fuer diese SSID wird ersetzt, nicht doppelt
# angehaengt - zwei Bloecke mit verschiedenem Passwort sind ein Fehler, der
# erst nach Wochen auffaellt.
CONF=""
for kandidat in /etc/wpa_supplicant/wpa_supplicant.conf \
                /etc/wpa_supplicant/wpa_supplicant-"${wlan}".conf; do
    [ -f "${kandidat}" ] && CONF="${kandidat}" && break
done
if [ -z "${CONF}" ]; then
    CONF="/etc/wpa_supplicant/wpa_supplicant.conf"
    printf 'ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\ncountry=DE\n\n' > "${CONF}"
    chmod 600 "${CONF}"
    sag "Neue ${CONF} angelegt."
fi

cp -a "${CONF}" "${CONF}.vor-lhtpi" 2>/dev/null || true

# Block fuer diese SSID entfernen (von "network={" bis zur schliessenden "}").
python3 - "${CONF}" "${ssid}" <<'PY'
import re
import sys

pfad, ssid = sys.argv[1], sys.argv[2]
with open(pfad, encoding='utf-8') as datei:
    inhalt = datei.read()

# Bloecke mit dieser SSID finden - auch solche mit eingerueckter SSID-Zeile.
muster = re.compile(r'network\s*=\s*\{[^}]*ssid\s*=\s*"' + re.escape(ssid) + r'"[^}]*\}\s*',
                    re.DOTALL)
neu, anzahl = muster.subn('', inhalt)
with open(pfad, 'w', encoding='utf-8') as datei:
    datei.write(neu.rstrip() + '\n')
print('ersetzt' if anzahl else 'neu', anzahl)
PY

# PSK gehasht schreiben: Das Klartext-Passwort muss nicht in der Datei stehen,
# und der Hash ist das, was wpa_supplicant ohnehin bildet.
if [ -n "${passwort}" ]; then
    block="$(wpa_passphrase "${ssid}" "${passwort}" | grep -v '^#psk=')"
else
    block="$(printf 'network={\n\tssid="%s"\n\tkey_mgmt=NONE\n}\n' "${ssid}")"
fi
printf '%s\n' "${block}" >> "${CONF}"
chmod 600 "${CONF}"
sag "Block fuer \"${ssid}\" eingetragen."

echo
sag "wende an ..."
wpa_cli -i "${wlan}" reconfigure >/dev/null 2>&1 \
    && sag "wpa_supplicant neu geladen." \
    || sag "wpa_cli nicht erreichbar - wirkt beim naechsten Start."

# Adresse erneuern, sonst bleibt die alte IP vom vorherigen Netz stehen.
if command -v dhcpcd >/dev/null 2>&1; then
    dhcpcd -n "${wlan}" >/dev/null 2>&1 || true
elif command -v dhclient >/dev/null 2>&1; then
    dhclient -r "${wlan}" >/dev/null 2>&1 || true
    dhclient "${wlan}" >/dev/null 2>&1 || true
fi

sleep 3
echo
echo "--- Stand jetzt"
sag "Netz: ${aktuell:-$(iwgetid -r 2>/dev/null || echo '-')}"
sag "IP:   $(hostname -I 2>/dev/null)"
echo
echo "Der Eintrag steht in ${CONF} und gilt auch nach einem Neustart."
echo "Falls nicht:  sudo systemctl status wpa_supplicant"
