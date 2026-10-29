#!/bin/bash
# LHTPi: WLAN-Verbindung pruefen und reparieren.
#
# Gedacht fuer den Fall "verbindet sich nicht mehr von selbst". Das Skript
# sieht erst nach, was los ist, und repariert dann - aber nur, was wirklich
# klemmt. Ein gesundes Profil wird nicht angefasst.
#
# Aufruf (als root):  sudo bash scripts/wlan-reparieren.sh
#
# Was geprueft wird:
#   1. Ist der Funk ueberhaupt freigegeben (rfkill)? Nach einem Kernel- oder
#      Firmware-Update steht er manchmal auf "blocked", und dann hilft keine
#      noch so gute Einstellung.
#   2. Ist WLAN im NetworkManager eingeschaltet?
#   3. Gibt es Profile, und sind sie auf "automatisch verbinden" gestellt?
#   4. Liegt das Passwort systemweit oder nur im Schluesselbund des Benutzers?
#      Nur im Schluesselbund heisst: verbindet erst nach einer Anmeldung.
#   5. Was sagt das Protokoll?
set -u

[ "$(id -u)" = "0" ] || { echo "Bitte mit sudo starten: sudo bash $0"; exit 1; }

sag()  { echo "  $*"; }
titel(){ echo; echo "--- $*"; }

echo "===== WLAN-Befund ====="

# ── 1. Funk freigegeben? ──────────────────────────────────────────────────
titel "Funk"
if command -v rfkill >/dev/null 2>&1; then
    rfkill list 2>/dev/null | sed 's/^/  /'
    if rfkill list wifi 2>/dev/null | grep -q 'blocked: yes'; then
        sag "WLAN ist gesperrt - wird freigegeben."
        rfkill unblock wifi
        rfkill unblock all
    else
        sag "nicht gesperrt."
    fi
else
    sag "rfkill fehlt (kein WLAN-Modul?)"
fi

# ── 1b. Regulierungsdomaene ───────────────────────────────────────────────
# Ohne Laendercode darf der Funk nicht auf allen Kanaelen senden. Bei
# Raspberry Pi OS steht das in der Kernel-Zeile: cfg80211.ieee80211_regdom=DE
# Fehlt es, verbindet er sich je nach Kanal gar nicht - und es sieht aus wie
# ein kaputtes WLAN-Profil.
titel "Laendercode"
# Nur die erste vorhandene Datei pruefen und dann abbrechen: Auf manchen
# Geraeten liegen beide Pfade, und /boot/cmdline.txt ist eine alte Kopie ohne
# den Eintrag. Ohne break meldet das Skript dann faelschlich ein Problem.
for cmd in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
    [ -f "${cmd}" ] || continue
    if grep -q 'cfg80211.ieee80211_regdom' "${cmd}" 2>/dev/null; then
        sag "cmdline: $(grep -o 'cfg80211.ieee80211_regdom=[A-Z]*' "${cmd}")"
    else
        sag "kein Laendercode in ${cmd}"
        # Nur ergaenzen, wenn eine Sicherung des Installers existiert - dann
        # ist sicher, dass die Datei schon einmal angefasst wurde.
        if [ -f "${cmd}.vor-lhtpi-hdmi" ]; then
            sag "Sicherung vorhanden - ergaenze den Laendercode."
            # Ans Ende der einen Zeile haengen - nicht per sed an jede Zeile,
            # sonst steht der Eintrag mehrfach drin.
            printf '%s %s\n' "$(tr -d '\n' < "${cmd}")" "cfg80211.ieee80211_regdom=DE" > "${cmd}"
            sag "eingetragen (wirkt nach einem Neustart)."
        else
            sag "Bitte in raspi-config setzen: 5 Localisation Options -> L4 WLAN Country"
        fi
    fi
    break
done
iw reg get 2>/dev/null | head -3 | sed 's/^/  /' || true

# ── 2. Ist ein WLAN-Geraet da? ────────────────────────────────────────────
titel "Geraet"
wlan="$(nmcli -t -f DEVICE,TYPE device 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}')"
if [ -z "${wlan}" ]; then
    echo "  KEIN WLAN-Geraet gefunden."
    echo "  Das ist kein Einstellungsproblem: entweder ist der Funk im"
    echo "  raspi-config abgeschaltet (5 Localisation Options), oder das Modul"
    echo "  fehlt. Pruefen:  dmesg | grep -i brcm"
    exit 1
fi
sag "Geraet: ${wlan}"

zustand="$(nmcli -t -f DEVICE,STATE device 2>/dev/null | awk -F: -v d="${wlan}" '$1==d{print $2}')"
sag "Zustand: ${zustand}"

if [ "${zustand}" = "unmanaged" ]; then
    echo
    echo "  Das Geraet wird NICHT vom NetworkManager verwaltet. Meist steht"
    echo "  dann in /etc/NetworkManager/NetworkManager.conf unter [keyfile]"
    echo "  ein 'unmanaged-devices'-Eintrag, oder es gibt eine alte"
    echo "  /etc/network/interfaces mit wlan0. Bitte melden - das ist ein"
    echo "  Einzelfall, den ich mir ansehen muss."
    exit 1
fi

# ── 3. WLAN eingeschaltet? ────────────────────────────────────────────────
titel "Funkschalter"
radio="$(nmcli radio wifi 2>/dev/null)"
sag "WLAN laut NetworkManager: ${radio:-unbekannt}"
if [ "${radio}" != "enabled" ]; then
    nmcli radio wifi on 2>/dev/null && sag "eingeschaltet."
fi

# ── 4. Profile ────────────────────────────────────────────────────────────
titel "Profile"
profile="$(nmcli -t -f NAME,TYPE connection show 2>/dev/null | awk -F: '$2=="wifi"{print $1}')"
if [ -z "${profile}" ]; then
    echo "  Kein NetworkManager-Profil fuer WLAN."
    echo

    # Das Geraet kann trotzdem verbunden sein - dann laeuft die Verbindung
    # an NetworkManager vorbei, typischerweise ueber die alte
    # /etc/wpa_supplicant/wpa_supplicant.conf. In dem Fall gibt es nichts,
    # was sich automatisch verbinden koennte: kein Profil, kein Autoconnect.
    aktiv="$(nmcli -t -f GENERAL.CONNECTION device show "${wlan}" 2>/dev/null | cut -d: -f2-)"
    ssid="$(iwgetid -r 2>/dev/null || true)"
    echo "  Verbunden mit:  ${ssid:-unbekannt}"
    echo "  Laut NetworkManager: ${aktiv:-nichts}"
    echo

    if [ -f /etc/wpa_supplicant/wpa_supplicant.conf ]; then
        echo "  Gefunden: /etc/wpa_supplicant/wpa_supplicant.conf (alte Verwaltung)"
        grep -E '^[[:space:]]*ssid=' /etc/wpa_supplicant/wpa_supplicant.conf 2>/dev/null \
            | sed 's/^/    /' || true
        echo
        echo "  Diese Datei kennt kein 'automatisch verbinden' - sie wird beim"
        echo "  Start von dhcpcd gelesen. Wenn es trotzdem nicht klappt, liegt es"
        echo "  an dhcpcd oder am Profil selbst, nicht an NetworkManager."
        echo
        echo "  Sauberer Weg: ein NetworkManager-Profil anlegen, dann gibt es"
        echo "  Autoconnect und Prioritaeten:"
        echo "    sudo nmcli device wifi connect \"DEIN-HOTSPOT\" password \"PASSWORT\""
    else
        echo "  Keine wpa_supplicant.conf und kein Profil - dann ist nichts"
        echo "  gespeichert, was sich verbinden koennte."
        echo
        echo "  Einrichten:"
        echo "    sudo nmcli device wifi connect \"DEIN-HOTSPOT\" password \"PASSWORT\""
    fi
    echo
    echo "  Verfuegbare Netze:"
    nmcli device wifi list 2>/dev/null | head -8 | sed 's/^/    /'
    exit 1
fi

echo "${profile}" | while IFS= read -r name; do
    [ -n "${name}" ] || continue
    auto="$(nmcli -t -f connection.autoconnect connection show "${name}" 2>/dev/null | cut -d: -f2)"
    prio="$(nmcli -t -f connection.autoconnect-priority connection show "${name}" 2>/dev/null | cut -d: -f2)"
    psk="$(nmcli -t -f wifi-sec.psk-flags connection show "${name}" 2>/dev/null | cut -d: -f2)"
    echo "  ${name}"
    echo "    automatisch verbinden: ${auto:-?}   Prioritaet: ${prio:-0}   Passwort-Flags: ${psk:-?}"

    # Passwort systemweit ablegen: 0 heisst "im Klartext in der
    # Verbindungsdatei", also ohne Anmeldung verfuegbar. 2 heisst "nur im
    # Schluesselbund des Benutzers" - dann verbindet er erst nach dem Login.
    if [ "${psk:-0}" != "0" ]; then
        sag "Passwort liegt im Schluesselbund - wird systemweit abgelegt."
        nmcli connection modify "${name}" wifi-sec.psk-flags 0 2>/dev/null \
            || echo "    (Konnte nicht geaendert werden - Passwort fehlt?)"
    fi
    if [ "${auto}" != "yes" ]; then
        sag "automatisch verbinden war aus - wird eingeschaltet."
        nmcli connection modify "${name}" connection.autoconnect yes 2>/dev/null
    fi
done

# ── 5. Verbinden ──────────────────────────────────────────────────────────
titel "Verbindungsversuch"
if [ "${zustand}" = "connected" ]; then
    sag "bereits verbunden."
else
    # Das Profil mit der hoechsten Prioritaet zuerst versuchen
    erstes="$(echo "${profile}" | head -1)"
    sag "versuche: ${erstes}"
    if nmcli connection up "${erstes}" 2>&1 | tail -2 | sed 's/^/    /'; then
        sag "Verbindung aufgebaut."
    fi
fi

# ── 6. Ergebnis ───────────────────────────────────────────────────────────
titel "Stand jetzt"
ip="$(hostname -I 2>/dev/null)"
sag "IP-Adressen: ${ip:-keine}"
nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device 2>/dev/null | grep ':wifi:' | sed 's/^/  /'

if ! echo "${ip}" | grep -qE '192\.168\.43\.|172\.20\.10\.'; then
    echo
    echo "  Keine typische Hotspot-Adresse dabei. Falls der Pi im Firmennetz"
    echo "  haengt, ist das normal - das WLAN ist dann nur eine zweite Leitung."
fi

# ── 7. Was sagt das Protokoll? ────────────────────────────────────────────
titel "Protokoll (letzte WLAN-Meldungen)"
journalctl -u NetworkManager -b --no-pager 2>/dev/null \
    | grep -iE 'wlan|wifi|supplicant|association|handshake|dhcp' \
    | tail -8 | cut -c1-150 | sed 's/^/  /' || echo "  (nicht lesbar)"

echo
echo "Fertig. Wenn es weiter nicht verbindet: Foto von oben genuegt."
