#!/bin/bash
# LHTPi: Aufloesung pruefen und auf die native Groesse setzen.
#
# Warum ein Bild unscharf ist: Der Bildschirm hat eine feste Punktzahl (z. B.
# 3840x2160). Laeuft der Rechner mit 1920x1080, muss das Bild hochgerechnet
# werden - jede Kante wird weich. Scharf wird es nur in der nativen Aufloesung.
#
# Aufruf:
#   sudo bash scripts/aufloesung.sh            nur anzeigen
#   sudo bash scripts/aufloesung.sh --setzen   beste Aufloesung setzen
#   sudo bash scripts/aufloesung.sh --dauerhaft  zusaetzlich in cmdline.txt
set -u

PI_USER="${LHTPI_USER:-pi}"
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/home/${PI_USER}/.Xauthority}"

SETZEN=0
DAUERHAFT=0
for arg in "$@"; do
    case "${arg}" in
        --setzen) SETZEN=1 ;;
        --dauerhaft) SETZEN=1; DAUERHAFT=1 ;;
    esac
done

sag() { echo "  $*"; }

if ! xrandr --query >/dev/null 2>&1; then
    echo "Der X-Server antwortet nicht. Bitte am Geraet selbst ausfuehren."
    exit 1
fi

echo "===== Aufloesung ====="
echo

# ── Was kann der Bildschirm? ──────────────────────────────────────────────
# Die EDID des Bildschirms listet seine Modi. Der erste Eintrag ist der
# native, also der, in dem er gebaut wurde.
for ausgang in HDMI-1 HDMI-2; do
    if ! xrandr --query | grep -qE "^${ausgang} "; then
        continue
    fi

    zeile="$(xrandr --query | grep -E "^${ausgang} " | head -1)"
    zustand="$(printf '%s' "${zeile}" | awk '{print $2}')"
    aktuell="$(printf '%s' "${zeile}" | grep -oE '[0-9]+x[0-9]+\+[0-9]+\+[0-9]+' | head -1 | cut -d+ -f1)"

    echo "${ausgang}  (${zustand})"

    if [ "${zustand}" != "connected" ]; then
        sag "nicht angeschlossen - keine Modi bekannt."
        echo
        continue
    fi

    sag "aktuell: ${aktuell:-unbekannt}"

    # Alle Modi, die der Bildschirm meldet - hoechste Aufloesung zuerst.
    modi="$(xrandr --query | sed -n "/^${ausgang} /,/^[^ ]/p" | grep -oE '^[[:space:]]+[0-9]+x[0-9]+' | tr -d ' ' | sort -t x -k1,1nr -k2,2nr | uniq)"
    if [ -n "${modi}" ]; then
        sag "moeglich (groesste zuerst):"
        printf '%s\n' "${modi}" | head -5 | sed 's/^/      /'
        nativ="$(printf '%s\n' "${modi}" | head -1)"
        sag "nativ waere: ${nativ}"
        if [ "${aktuell}" != "${nativ}" ]; then
            sag "-> das Bild wird hochgerechnet, deshalb unscharf."
        else
            sag "-> laeuft bereits nativ, scharf."
        fi
    else
        # Keine Modi im X: dann in der EDID des Kernels nachsehen.
        edid="$(ls /sys/class/drm/card*-${ausgang}/modes 2>/dev/null | head -1)"
        if [ -n "${edid}" ]; then
            sag "Modi laut Kernel:"
            head -5 "${edid}" | sed 's/^/      /'
        else
            sag "keine Modi gefunden (kein EDID?)"
        fi
    fi
    echo
done

# ── Alte Zwangszeilen in config.txt ──────────────────────────────────────
# hdmi_mode/hdmi_group stammen vom alten Videotreiber und legen die Aufloesung
# fest, bevor der Bildschirm ueberhaupt gefragt wird. Mit KMS sind sie falsch
# und erzeugen genau das Bild, das hier auffaellt: klein und hochgerechnet.
# framebuffer_width/height tun dasselbe auf anderem Weg.
CONFIG=""
for kandidat in /boot/firmware/config.txt /boot/config.txt; do
    [ -f "${kandidat}" ] && CONFIG="${kandidat}" && break
done
if [ -n "${CONFIG}" ]; then
    altlasten="$(grep -nE '^[[:space:]]*(hdmi_group|hdmi_mode|hdmi_force_hotplug|framebuffer_width|framebuffer_height|hdmi_cvt)' "${CONFIG}" 2>/dev/null)"
    if [ -n "${altlasten}" ]; then
        echo "Alte Zwangszeilen in ${CONFIG}:"
        printf '%s\n' "${altlasten}" | sed 's/^/  /'
        echo
        echo "  Diese Zeilen legen die Aufloesung fest, bevor der Bildschirm"
        echo "  gefragt wird. Mit dem KMS-Treiber sind sie falsch und erklaeren"
        echo "  ein kleines, hochgerechnetes Bild. Entfernen mit:"
        echo "    sudo bash scripts/hdmi-fixieren.sh --altlasten"
        echo
    fi
fi

# ── Prozessorgeschwindigkeit: was ist ueberhaupt moeglich? ───────────────
echo "Geraet:"
if [ -f /proc/device-tree/model ]; then
    modell="$(tr -d '\0' < /proc/device-tree/model)"
    sag "${modell}"
    case "${modell}" in
        *"Raspberry Pi 3"*|*"Raspberry Pi 2"*|*"Raspberry Pi Zero"*)
            echo
            echo "  Hinweis: Dieses Modell kann hoechstens 1920x1080."
            echo "  Ein 4K-Bildschirm wird dort immer hochgerechnet - scharf"
            echo "  wird es nur mit einem Pi 4 oder 5."
            ;;
    esac
fi

# ── Setzen ────────────────────────────────────────────────────────────────
if [ "${SETZEN}" = "1" ]; then
    echo
    echo "===== Setzen ====="
    geaendert=0
    for ausgang in HDMI-1 HDMI-2; do
        xrandr --query | grep -qE "^${ausgang} connected" || continue

        # Alle angebotenen Modi, groesster zuerst. 3840x2160 (Fernseher) und
        # 4096x2160 (Kino) sind nicht dasselbe - welcher passt, entscheidet
        # das Geraet, nicht die Groesse allein.
        modi="$(xrandr --query | sed -n "/^${ausgang} connected/,/^[^ ]/p" \
            | grep -oE '^[[:space:]]+[0-9]+x[0-9]+' | tr -d ' ' \
            | sort -t x -k1,1nr -k2,2nr | uniq)"
        if [ -z "${modi}" ]; then
            sag "${ausgang}: keine Modi angeboten (kein EDID?)"
            continue
        fi

        gesetzt=0
        while IFS= read -r modus; do
            [ -n "${modus}" ] || continue
            # Fehler NICHT verschlucken: ohne die Meldung von xrandr ist nicht
            # zu sehen, ob der Modus fehlt, der Ausgang aus ist oder der
            # Bildschirm ihn ablehnt.
            meldung="$(xrandr --output "${ausgang}" --mode "${modus}" 2>&1)"
            if [ -z "${meldung}" ]; then
                sag "${ausgang} auf ${modus} gesetzt."
                gesetzt=1
                geaendert=1
                break
            fi
            sag "${ausgang} ${modus}: ${meldung}"
        done <<< "${modi}"

        # Zweiter Versuch: Ausgang einmal aus und wieder an. Dabei fragt der
        # Treiber den Bildschirm neu und bietet oft Modi an, die vorher fehlten.
        if [ "${gesetzt}" = "0" ]; then
            sag "${ausgang}: Ausgang wird neu ausgehandelt ..."
            xrandr --output "${ausgang}" --off >/dev/null 2>&1
            sleep 2
            meldung="$(xrandr --output "${ausgang}" --auto 2>&1)"
            if [ -z "${meldung}" ]; then
                jetzt="$(xrandr --query | grep -E "^${ausgang} connected" | grep -oE '[0-9]+x[0-9]+\+' | head -1 | cut -d+ -f1)"
                sag "${ausgang} automatisch auf ${jetzt:-?} gesetzt."
                [ "${jetzt}" != "720x400" ] && [ "${jetzt}" != "720x480" ] && geaendert=1
            else
                sag "${ausgang}: auto meldet: ${meldung}"
            fi
        fi
    done

    # Die Kiosk-Fenster wurden mit der alten Groesse gestartet. Ohne Neustart
    # sitzt das Bild in einem kleinen Fenster in der Ecke - das sieht aus wie
    # "immer noch unscharf".
    if [ "${geaendert}" = "1" ]; then
        echo
        sag "Kiosk-Fenster neu starten, damit sie die neue Groesse bekommen ..."
        for dienst in kiosk-screen1 kiosk-screen2; do
            systemctl is-active --quiet "${dienst}.service" 2>/dev/null || continue
            sudo -n systemctl restart "${dienst}.service" >/dev/null 2>&1 \
                && sag "${dienst} neu gestartet." \
                || sag "${dienst} konnte nicht neu starten (ohne sudo ausgefuehrt?)"
        done
    fi
fi

# ── Dauerhaft ─────────────────────────────────────────────────────────────
if [ "${DAUERHAFT}" = "1" ]; then
    # Ueber die Kernel-Zeile, weil sie auch dann gilt, wenn der Bildschirm
    # beim Start noch aus ist - und weil sie die Skalierung gar nicht erst
    # zulaesst.
    SKRIPT="$(cd "$(dirname "$0")" && pwd)/hdmi-fixieren.sh"
    if [ -x "${SKRIPT}" ] || [ -f "${SKRIPT}" ]; then
        LHTPI_USER="${PI_USER}" bash "${SKRIPT}"
        echo
        echo "  Nach einem Neustart gilt die Aufloesung dauerhaft."
    else
        sag "hdmi-fixieren.sh nicht gefunden - nicht dauerhaft gesetzt."
    fi
fi

echo
if [ "${SETZEN}" = "0" ]; then
    echo "Zum Setzen:      sudo bash $0 --setzen"
    echo "Dauerhaft:       sudo bash $0 --dauerhaft"
fi
