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
    for ausgang in HDMI-1 HDMI-2; do
        xrandr --query | grep -qE "^${ausgang} connected" || continue
        nativ="$(xrandr --query | sed -n "/^${ausgang} connected/,/^[^ ]/p" \
            | grep -oE '^[[:space:]]+[0-9]+x[0-9]+' | tr -d ' ' \
            | sort -t x -k1,1nr -k2,2nr | uniq | head -1)"
        [ -n "${nativ}" ] || continue
        if xrandr --output "${ausgang}" --mode "${nativ}" >/dev/null 2>&1; then
            sag "${ausgang} auf ${nativ} gesetzt."
        else
            sag "${ausgang}: ${nativ} liess sich nicht setzen."
        fi
    done
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
