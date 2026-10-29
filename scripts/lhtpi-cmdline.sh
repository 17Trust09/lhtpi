#!/bin/bash
# LHTPi: Aufloesung dauerhaft in die Kernel-Zeile schreiben.
#
# Warum ein eigener Helfer: Die App laeuft als pi und darf /boot nicht
# schreiben. Ohne Freigabe scheitert das Setzen still, und das Bild ist nach
# dem naechsten Neustart wieder klein.
#
# Aufruf:  lhtpi-cmdline.sh <HDMI-1|HDMI-2> <BREITExHOEHE>
set -u

AUSGANG="${1:-}"
MODUS="${2:-}"

case "${AUSGANG}" in
    HDMI-1|HDMI-2) : ;;
    *) echo "Unbekannter Ausgang: ${AUSGANG}" >&2; exit 1 ;;
esac

case "${MODUS}" in
    [0-9]*x[0-9]*) : ;;
    *) echo "Ungueltige Aufloesung: ${MODUS}" >&2; exit 1 ;;
esac

ZIEL=""
for kandidat in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
    [ -f "${kandidat}" ] && ZIEL="${kandidat}" && break
done
[ -n "${ZIEL}" ] || { echo "cmdline.txt nicht gefunden" >&2; exit 1; }

NUMMER="${AUSGANG#HDMI-}"
EINTRAG="video=HDMI-A-${NUMMER}:${MODUS}@60D"

# Sicherung nur beim ersten Mal, sonst fuellt sich /boot mit Kopien.
SICHERUNG="${ZIEL}.vor-lhtpi-su"
[ -f "${SICHERUNG}" ] || cp -a "${ZIEL}" "${SICHERUNG}" 2>/dev/null || true

# Wortweise: cmdline.txt ist EINE Zeile. Ein sed auf Zeilen wuerde die
# Startzeile zerstoeren, ein doppelter Eintrag gilt nicht.
NEU=""
for wort in $(tr '\n' ' ' < "${ZIEL}"); do
    case "${wort}" in
        video=HDMI-A-${NUMMER}:*) continue ;;
    esac
    NEU="${NEU} ${wort}"
done
NEU="${NEU} ${EINTRAG}"

printf '%s\n' "$(echo "${NEU}" | sed 's/^ //')" > "${ZIEL}" || {
    echo "Schreiben in ${ZIEL} fehlgeschlagen" >&2
    exit 1
}

echo "eingetragen: ${EINTRAG}"
