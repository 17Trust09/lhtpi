#!/bin/bash
# LHTPi: HDMI-Ausgaenge dauerhaft aktiv halten.
#
# Das Problem: Die Bildschirme gehen nachts aus (Zeitschaltuhr, Standby). Dabei
# faellt die Hotplug-Leitung weg, und der Linux-Treiber meldet den Ausgang als
# "disconnected" - er schaltet ihn ab. Morgens, wenn der Bildschirm wieder
# Strom hat, kommt nicht zuverlaessig ein Hotplug-Ereignis, und das Bild bleibt
# schwarz. xrandr kann dann nichts mehr tun: ohne erkannten Bildschirm gibt es
# keine Modi, die man setzen koennte.
#
# Die Loesung sitzt eine Ebene tiefer: In der Kernel-Kommandozeile wird der
# Ausgang fest eingeschaltet, unabhaengig von der Erkennung.
#
#   video=HDMI-A-1:3840x2160@60D
#
# Das "D" heisst: digital, und einschalten auch ohne Hotplug. Der Ausgang sendet
# dann dauerhaft; der Bildschirm findet beim Einschalten sofort ein Signal.
#
# Wichtig: hdmi_force_hotplug aus der config.txt wirkt beim KMS-Treiber NICHT
# (so steht es in der offiziellen Raspberry-Pi-Dokumentation). Die Zeile steht
# bei vielen Geraeten noch drin und suggeriert eine Loesung, die es nicht gibt.
# Dieses Skript raeumt sie weg.
#
# Aufruf (als root):  bash scripts/hdmi-fixieren.sh [--entfernen]
set -u

ENTFERNEN=0
[ "${1:-}" = "--entfernen" ] && ENTFERNEN=1

[ "$(id -u)" = "0" ] || { echo "Bitte mit sudo starten: sudo bash $0"; exit 1; }

PI_USER="${LHTPI_USER:-pi}"
CMDLINE=""
for kandidat in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
    [ -f "${kandidat}" ] && CMDLINE="${kandidat}" && break
done
CONFIG=""
for kandidat in /boot/firmware/config.txt /boot/config.txt; do
    [ -f "${kandidat}" ] && CONFIG="${kandidat}" && break
done

[ -n "${CMDLINE}" ] || { echo "cmdline.txt nicht gefunden - nichts geaendert."; exit 1; }

sag() { echo "  $*"; }

# ── Aufloesung je Ausgang bestimmen ───────────────────────────────────────
# Nicht raten: die Aufloesung, die jetzt laeuft, ist die, die der Bildschirm
# kann. Ein erzwungener Modus, den er nicht kennt, ergibt kein Bild.
hole_modus() {
    local ausgang="$1"
    local zeile
    zeile="$(DISPLAY=:0 XAUTHORITY="/home/${PI_USER}/.Xauthority" \
        xrandr --query 2>/dev/null | grep -E "^${ausgang} connected" | head -1)"
    # Format: "HDMI-1 connected primary 3840x2160+0+0 ..."
    local aufloesung
    aufloesung="$(printf '%s' "${zeile}" | awk '{print $3}' | grep -oE '^[0-9]+x[0-9]+')"
    local rate
    rate="$(DISPLAY=:0 XAUTHORITY="/home/${PI_USER}/.Xauthority" \
        xrandr --query 2>/dev/null | grep -A1 -E "^${ausgang} connected" \
        | grep -oE '[0-9]+\.[0-9]+\*' | head -1 | tr -d '*')"
    [ -n "${rate}" ] || rate="$(DISPLAY=:0 XAUTHORITY="/home/${PI_USER}/.Xauthority" \
        xrandr --query 2>/dev/null | grep -A1 -E "^${ausgang} connected" \
        | grep -oE '[0-9]+\.[0-9]+' | head -1)"
    [ -n "${rate}" ] || rate="60"
    case "${aufloesung}" in
        *x*) echo "${aufloesung}@${rate%.*}" ;;
        *)   echo "" ;;
    esac
}

# ── Bestehende Eintraege entfernen ────────────────────────────────────────
entferne_video() {
    local datei="$1"
    local sicherung="${datei}.vor-lhtpi-hdmi"
    [ -f "${sicherung}" ] || cp -a "${datei}" "${sicherung}" 2>/dev/null || true

    # cmdline.txt ist EINE Zeile. video=-Eintraege werden als Wort entfernt,
    # nicht als Zeile - sonst waere die Startzeile zerstoert.
    local inhalt
    inhalt="$(tr '\n' ' ' < "${datei}" | tr -s ' ')"
    local neu=""
    for wort in ${inhalt}; do
        case "${wort}" in
            video=HDMI-A-*|video=HDMI-A-*) continue ;;
        esac
        neu="${neu} ${wort}"
    done
    printf '%s\n' "$(echo "${neu}" | sed 's/^ //')" > "${datei}"
}

# ── Eintraege schreiben ───────────────────────────────────────────────────
schreibe_video() {
    local datei="$1"; shift
    entferne_video "${datei}"
    local inhalt
    inhalt="$(tr -d '\n' < "${datei}")"
    printf '%s %s\n' "${inhalt}" "$*" > "${datei}"
}

if [ "${ENTFERNEN}" = "1" ]; then
    entferne_video "${CMDLINE}"
    sag "video=-Eintraege aus ${CMDLINE} entfernt."
    sag "Nach einem Neustart gilt wieder die automatische Erkennung."
    exit 0
fi

# ── Modi bestimmen ────────────────────────────────────────────────────────
modus1="$(hole_modus HDMI-1)"
modus2="$(hole_modus HDMI-2)"

# Wenn kein X laeuft, die Aufloesung aus der EDID des Kernels nehmen.
edid_modus() {
    local ausgang="$1"
    local datei
    datei="$(ls /sys/class/drm/card*-${ausgang}/modes 2>/dev/null | head -1)"
    [ -n "${datei}" ] || return 0
    head -1 "${datei}" 2>/dev/null
}

[ -n "${modus1}" ] || modus1="$(edid_modus HDMI-1)"
[ -n "${modus2}" ] || modus2="$(edid_modus HDMI-2)"
[ -n "${modus1}" ] || modus1="1920x1080@60"
[ -n "${modus2}" ] || modus2="1920x1080@60"

anzahl="$(cat /etc/lhtpi/screens 2>/dev/null || echo 1)"
case "${anzahl}" in ''|*[!0-9]*) anzahl=1 ;; esac

eintraege="video=HDMI-A-1:${modus1}D"
if [ "${anzahl}" -ge 2 ]; then
    eintraege="${eintraege} video=HDMI-A-2:${modus2}D"
fi

schreibe_video "${CMDLINE}" "${eintraege}"
sag "In ${CMDLINE} eingetragen: ${eintraege}"
sag "Der Ausgang bleibt damit auch ohne Bildschirm aktiv."

# ── Wirkungslose Altlast raeumen ──────────────────────────────────────────
if [ -n "${CONFIG}" ] && grep -qE '^[[:space:]]*hdmi_force_hotplug' "${CONFIG}"; then
    sed -i -E 's/^([[:space:]]*hdmi_force_hotplug)/#\1/' "${CONFIG}"
    sag "hdmi_force_hotplug in ${CONFIG} auskommentiert (wirkt beim KMS-Treiber nicht)."
fi

echo
echo "Damit die Eintraege wirken, ist ein Neustart noetig:  sudo reboot"
