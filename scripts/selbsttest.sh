#!/bin/bash
# LHTPi: prueft nach der Installation, ob alles wirklich steht.
#
# Warum das noetig ist: Die Fehler der letzten Wochen waren alle stumm. Ein
# Dienst war "active", weil er freiwillig abbrach. Ein Speichern lief durch,
# ohne zu wirken. Ein Waechter meldete Gesundheit, waehrend das Bild schwarz
# war. Nichts davon faellt bei "Installation abgeschlossen" auf.
#
# Dieses Skript fragt nicht, ob Dateien existieren, sondern ob die Kette
# funktioniert.
#
# Aufruf:  bash scripts/selbsttest.sh      (ohne root, prueft was es darf)
set -u

PI_USER="${LHTPI_USER:-pi}"
fehler=0
warnungen=0

gruen() { printf '  \033[32mOK\033[0m    %s\n' "$*"; }
rot()   { printf '  \033[31mFEHLT\033[0m %s\n' "$*"; fehler=$((fehler + 1)); }
gelb()  { printf '  \033[33m?     %s\033[0m\n' "$*"; warnungen=$((warnungen + 1)); }

echo
echo "===== LHTPi Selbsttest ====="

# ── 1. Kiosk-Dienste ─────────────────────────────────────────────────────
anzahl="$(cat /etc/lhtpi/screens 2>/dev/null || echo 0)"
case "${anzahl}" in ''|*[!0-9]*) anzahl=0 ;; esac
echo "Bildschirme laut Einstellung: ${anzahl}"

for dienst in kiosk-screen1 kiosk-screen2; do
    case "${dienst}" in
        *1) [ "${anzahl}" -ge 1 ] || continue ;;
        *2) [ "${anzahl}" -ge 2 ] || continue ;;
    esac
    if systemctl is-active --quiet "${dienst}.service"; then
        gruen "${dienst} laeuft"
    else
        rot "${dienst} laeuft nicht"
    fi
done

# ── 2. Bildschirm-Waechter ───────────────────────────────────────────────
if [ "${anzahl}" -ge 2 ]; then
    if systemctl is-active --quiet lhtpi-screen2-watch.service; then
        gruen "Bildschirm-Waechter laeuft"
    else
        rot "Bildschirm-Waechter laeuft nicht"
    fi

    # Er muss den Fall kennen, der den Reboot gekostet hat: Ausgang meldet
    # sich ab. Steht die Zeile nicht im Skript, ist es die alte Fassung.
    if grep -q 'meldet nicht .connected.' /home/${PI_USER}/lhtpi-screen2-watch.sh 2>/dev/null; then
        gruen "Waechter kennt den Fall 'Ausgang abgemeldet'"
    else
        rot "Waechter ist die alte Fassung (blind bei Signalverlust)"
    fi

    if [ -f "/home/${PI_USER}/lhtpi-hdmi.log" ]; then
        gruen "Waechter-Protokoll vorhanden"
    else
        gelb "Waechter-Protokoll noch leer (erste Meldung kommt beim Start)"
    fi
fi

# ── 3. Werkzeuge, ohne die der Waechter blind ist ────────────────────────
for werkzeug in xrandr xset; do
    if command -v "${werkzeug}" >/dev/null 2>&1; then
        gruen "${werkzeug} vorhanden"
    else
        rot "${werkzeug} fehlt"
    fi
done

# Fensterpruefung: xdotool ist der genaue Weg, xwininfo der Ersatz. Fehlt
# beides, kann der Waechter ein fehlendes Fenster nicht erkennen - dann bleibt
# nur der Ausgang als Kriterium.
if command -v xdotool >/dev/null 2>&1; then
    gruen "xdotool vorhanden (Fensterpruefung genau)"
elif command -v xwininfo >/dev/null 2>&1; then
    gelb "xdotool fehlt - xwininfo uebernimmt die Fensterpruefung"
    echo "        Nachinstallieren: sudo apt-get install -y xdotool"
else
    rot "weder xdotool noch xwininfo - Fenster werden nicht geprueft"
    echo "        Nachinstallieren: sudo apt-get install -y xdotool x11-utils"
fi

# ── 4. Rettungsskript ────────────────────────────────────────────────────
if [ -x /usr/local/bin/lhtpi-anzeige-rettung.sh ]; then
    gruen "Anzeige-Rettung installiert"
else
    rot "Anzeige-Rettung fehlt (/usr/local/bin/lhtpi-anzeige-rettung.sh)"
fi

# ── 5. Freigaben: pruefen, ob sudo ohne Passwort darf ────────────────────
# Das ist der Punkt, an dem es bisher still scheiterte: Die Regel fehlte oder
# der Pfad stimmte nicht, sudo fragte nach dem Passwort, und niemand merkte es.
pruefe_freigabe() {
    local beschreibung="$1"; shift
    if sudo -n -l "$@" >/dev/null 2>&1; then
        gruen "ohne Passwort erlaubt: ${beschreibung}"
    else
        rot "NICHT ohne Passwort erlaubt: ${beschreibung}"
    fi
}

if [ "${anzahl}" -ge 1 ]; then
    pruefe_freigabe "Bildschirmzahl setzen" /usr/local/bin/lhtpi-screens.sh
    pruefe_freigabe "Kiosk 1 neu starten" /usr/bin/systemctl restart kiosk-screen1
fi
if [ "${anzahl}" -ge 2 ]; then
    pruefe_freigabe "Kiosk 2 neu starten" /usr/bin/systemctl restart kiosk-screen2
fi
pruefe_freigabe "Anzeige retten" /usr/local/bin/lhtpi-anzeige-rettung.sh
pruefe_freigabe "Terminboard neu starten" /usr/bin/systemctl restart terminboard.service

if sudo -n -l /usr/local/bin/lhtpi-usb-rw.sh >/dev/null 2>&1; then
    gruen "ohne Passwort erlaubt: Stick beschreibbar schalten"
else
    rot "NICHT ohne Passwort erlaubt: Stick beschreibbar schalten"
fi

# ── 6. Nachziehen nach git pull ──────────────────────────────────────────
if [ -f /home/${PI_USER}/lhtpi/.git/hooks/post-merge ]; then
    if grep -q 'nach-pull.sh' /home/${PI_USER}/lhtpi/.git/hooks/post-merge; then
        gruen "git pull zieht Systemteile nach"
    else
        rot "git pull-Haken zeigt nicht auf nach-pull.sh"
    fi
else
    gelb "Kein git-Haken (kein Klon?) - git pull zieht nichts nach"
fi

# ── 6b. Ausgaenge dauerhaft aktiv? ──────────────────────────────────────
# Ohne diesen Eintrag bleibt das Bild morgens schwarz, wenn der Bildschirm
# ueber Nacht aus war - der haeufigste Ausfall bei diesem Geraet.
cmds=""
for kandidat in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
    [ -f "${kandidat}" ] && cmds="${kandidat}" && break
done
if [ -n "${cmds}" ]; then
    if grep -q 'video=HDMI-A-1:' "${cmds}" 2>/dev/null; then
        gruen "HDMI-Ausgang 1 dauerhaft aktiv ($(grep -o 'video=HDMI-A-1:[^ ]*' "${cmds}"))"
    else
        rot "kein video=HDMI-A-1 in cmdline.txt - Bild bleibt nach Standby schwarz"
        echo "        Beheben: sudo bash /home/${PI_USER}/lhtpi/scripts/hdmi-fixieren.sh"
    fi
    if [ "${anzahl}" -ge 2 ]; then
        if grep -q 'video=HDMI-A-2:' "${cmds}" 2>/dev/null; then
            gruen "HDMI-Ausgang 2 dauerhaft aktiv ($(grep -o 'video=HDMI-A-2:[^ ]*' "${cmds}"))"
        else
            rot "kein video=HDMI-A-2 in cmdline.txt - Bild 2 bleibt nach Standby schwarz"
            echo "        Beheben: sudo bash /home/${PI_USER}/lhtpi/scripts/hdmi-fixieren.sh"
        fi
    fi
else
    gelb "cmdline.txt nicht gefunden - Fixierung nicht pruefbar"
fi

# ── 6c. WLAN, falls eingerichtet ────────────────────────────────────────
profile_wlan="$(nmcli -t -f NAME,TYPE connection show 2>/dev/null | awk -F: '$2=="wifi"{print $1}' | head -1)"
if [ -n "${profile_wlan}" ]; then
    wlan_zustand="$(nmcli -t -f DEVICE,TYPE,STATE device 2>/dev/null | awk -F: '$2=="wifi"{print $3; exit}')"
    if [ "${wlan_zustand}" = "connected" ]; then
        gruen "WLAN verbunden (${profile_wlan})"
    else
        gelb "WLAN-Profil '${profile_wlan}' vorhanden, aber nicht verbunden"
        echo "        Pruefen: sudo bash /home/${PI_USER}/lhtpi/scripts/wlan-reparieren.sh"
    fi
fi

# ── 7. Ausgabe am Bildschirm ─────────────────────────────────────────────
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="/home/${PI_USER}/.Xauthority"
if xrandr --query >/dev/null 2>&1; then
    verbunden="$(xrandr --query | grep -E '^HDMI-[12] connected' | awk '{print $1}' | tr '\n' ' ')"
    if [ -n "${verbunden}" ]; then
        gruen "verbunden: ${verbunden}"
    else
        rot "kein HDMI-Ausgang verbunden"
    fi
    doppelt="$(xrandr --query | grep -E '^HDMI-[12] connected' | awk '{print $3}' | sort -u | wc -l)"
    if [ "${anzahl}" -ge 2 ] && [ "${doppelt}" -le 1 ]; then
        rot "beide Ausgaenge zeigen auf dieselbe Flaeche (gespiegelt)"
    fi
else
    gelb "X-Server nicht erreichbar (als normaler Nutzer erwartbar)"
fi

# ── Ergebnis ─────────────────────────────────────────────────────────────
echo
if [ "${fehler}" -eq 0 ] && [ "${warnungen}" -eq 0 ]; then
    echo "Alles in Ordnung."
    exit 0
fi
if [ "${fehler}" -eq 0 ]; then
    echo "${warnungen} Hinweis(e), nichts kaputt."
    exit 0
fi
echo "${fehler} Punkt(e) fehlen, ${warnungen} Hinweis(e)."
echo
echo "Nachziehen (setzt Freigaben und Dienste neu):"
echo "  sudo bash /home/${PI_USER}/lhtpi/scripts/kiosk-neu.sh"
exit 1
