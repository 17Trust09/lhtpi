#!/bin/bash
# LHTPi: Kiosk-Skripte und Bildschirm-Helfer neu einrichten.
#
# Aufruf (als root):  sudo bash scripts/kiosk-neu.sh
#
# Nötig nach einem Update, das nur die Kiosk-Skripte betrifft: die Skripte
# werden von install.sh erzeugt und liegen deshalb nicht im Programmordner.
# Dieses Skript macht nur diesen Teil – keine Pakete, keine Diensteinrichtung.
set -uo pipefail
NEUSTART_NOETIG=0
APP_NEU=0
NEU_LADEN=0

[ "$(id -u)" = "0" ] || { echo "Bitte mit sudo starten: sudo bash $0"; exit 1; }

REPO="${LHTPI_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PI_USER="${LHTPI_USER:-pi}"
PI_GROUP="${LHTPI_GROUP:-${PI_USER}}"
HELFER="/usr/local/bin/lhtpi-entkoppeln.sh"
HOME_DIR="/home/${PI_USER}"

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

# ── 2a. Bildschirmzahl-Helfer und Marke ────────────────────────────────────
# Ohne den Helfer kann die Web-App die Bildschirmzahl nicht setzen (sie läuft
# als pi, /etc/lhtpi gehört root). Und ohne die Marke startete der Dienst für
# Bildschirm 2 bisher gar nicht.
SCREENS_HELFER="/usr/local/bin/lhtpi-screens.sh"
if [ ! -x "${SCREENS_HELFER}" ] && grep -q "lhtpi-screens.sh <<'SCR_EOF'" "${REPO}/install.sh"; then
    python3 - "${REPO}/install.sh" "${SCREENS_HELFER}" <<'PYSCR'
import pathlib, sys
quelle, ziel = sys.argv[1], sys.argv[2]
s = pathlib.Path(quelle).read_text()
marker = "cat > /usr/local/bin/lhtpi-screens.sh <<'SCR_EOF'"
a = s.index(marker)
a = s.index("\n", a) + 1
b = s.index("SCR_EOF", a)
pathlib.Path(ziel).write_text(s[a:b])
PYSCR
    chmod 0755 "${SCREENS_HELFER}"
    bash -n "${SCREENS_HELFER}" && sag "Helfer eingerichtet: ${SCREENS_HELFER}"
fi

# Freigaben: Bildschirmzahl setzen und die Kiosk-Dienste neu starten. Ohne die
# zweite Regel scheiterte das Neustarten nach dem Speichern still - die Anzeige
# behielt dann die alte Belegung.
# Alle Freigaben an einer Stelle - dieselbe Datei wie bei der Installation.
if [ -f "${REPO}/scripts/sudoers-regeln.sh" ]; then
    if LHTPI_USER="${PI_USER}" bash "${REPO}/scripts/sudoers-regeln.sh"; then
        sag "Freigaben gesetzt (Bildschirme, Rettung, Dienste, Stick)."
    else
        warn_freigabe=1
        sag "WARNUNG: Freigaben nicht gesetzt - Speichern startet die Anzeige nicht neu."
    fi
else
    warn_freigabe=1
    sag "WARNUNG: scripts/sudoers-regeln.sh fehlt."
fi

# Marke für Bildschirm 2 sicherstellen
mkdir -p /etc/lhtpi
ANZAHL="$(cat /etc/lhtpi/screens 2>/dev/null || echo 2)"
# Leere oder kaputte Datei heisst NICHT "ein Bildschirm": das Geraet ist mit zwei
# eingerichtet, und ein leerer Wert haette Bildschirm 2 stillschweigend
# abgeschaltet.
case "${ANZAHL}" in ''|*[!0-9]*) ANZAHL=2 ;; esac
# Selbstheilung: Steht die Zahl auf 1, obwohl zwei Ausgänge verbunden sind,
# wurde sie irgendwo falsch gesetzt (die App schrieb frueher still ins Leere).
# Dann gilt der tatsaechliche Aufbau - sonst bleibt ein Bildschirm schwarz,
# ohne dass jemand versteht warum.
# Ausgaenge direkt im Kernel zaehlen: das braucht kein X und funktioniert
# auch dann, wenn xrandr im Installer-Kontext keinen Zugang bekommt.
verbunden="${LHTPI_CONNECTED:-$(cat /sys/class/drm/card*-HDMI-*/status 2>/dev/null | grep -c '^connected$')}"
if [ "${verbunden}" -lt 1 ]; then
    verbunden="$(DISPLAY=:0 XAUTHORITY="/home/${PI_USER}/.Xauthority" \
        xrandr --query 2>/dev/null | grep -cE '^HDMI-[12] connected')"
fi
case "${verbunden}" in ''|*[!0-9]*) verbunden=0 ;; esac
if [ "${verbunden}" -ge 2 ] && [ "${ANZAHL}" -lt 2 ]; then
    sag "Zwei Ausgänge verbunden, Bildschirmzahl stand auf ${ANZAHL} - korrigiere auf 2."
    ANZAHL=2
    if [ -x "${SCREENS_HELFER}" ]; then
        "${SCREENS_HELFER}" 2 >/dev/null 2>&1 || printf '2\n' > /etc/lhtpi/screens
    else
        printf '2\n' > /etc/lhtpi/screens
    fi
fi

if [ "${ANZAHL}" -ge 2 ]; then
    [ -f /etc/lhtpi/screen2 ] || { : > /etc/lhtpi/screen2; chmod 644 /etc/lhtpi/screen2; sag "Marke /etc/lhtpi/screen2 angelegt."; }
    sag "Bildschirmzahl: ${ANZAHL} (zwei Anzeigen aktiv)"

    # Auch die gespeicherte Einstellung der App nachziehen. Sie hatte xrandr
    # nicht zur Verfuegung (kein DISPLAY im Dienst) und hielt deshalb 1 fest -
    # dadurch beendete sich das Startskript von Bildschirm 2 sofort wieder
    # ("inactive, Result=success"), obwohl zwei Monitore hingen.
    # Python statt sqlite3-Kommando: das venv ist immer da, sqlite3 nicht.
    DBS="${LHTPI_APP_DB:-/var/lib/lhtpi/app/lhtpi.db}"
    PYTHON="${REPO}/venv/bin/python"
    [ -x "${PYTHON}" ] || PYTHON="${LHTPI_PYTHON:-$(command -v python3 || true)}"
    if [ -f "${DBS}" ] && [ -n "${PYTHON}" ] && [ -x "${PYTHON}" ]; then
        ergebnis="$("${PYTHON}" - "${DBS}" <<'PYDB' 2>&1
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
alt = db.execute("SELECT value FROM setting WHERE key='kiosk_screen_count'").fetchone()
if alt is None:
    db.execute("INSERT INTO setting (key, value) VALUES ('kiosk_screen_count','2')")
    db.commit()
    print("nichts -> 2")
elif str(alt[0]) != '2':
    db.execute("UPDATE setting SET value='2' WHERE key='kiosk_screen_count'")
    db.commit()
    print("%s -> 2" % alt[0])
db.close()
PYDB
)"
        [ -n "${ergebnis}" ] && sag "Gespeicherte Bildschirmzahl korrigiert (${ergebnis})."
    fi
else
    sag "Nur ${ANZAHL} Bildschirm eingestellt - Bildschirm 2 bleibt aus."
fi

# App-Dienst braucht DISPLAY: sonst kann sie xrandr nicht fragen, zaehlt einen
# Bildschirm und schreibt die 1 bei jedem Speichern der Anzeige fest.
APP_UNIT="/etc/systemd/system/lhtpi.service"
if [ -f "${APP_UNIT}" ] && ! grep -qE '^Environment=DISPLAY=' "${APP_UNIT}"; then
    sed -i "/^Environment=PYTHONUNBUFFERED=1/a Environment=DISPLAY=:0" "${APP_UNIT}"
    sed -i "/^Environment=DISPLAY=:0$/a Environment=XAUTHORITY=/home/${PI_USER}/.Xauthority" "${APP_UNIT}"
    sag "App-Dienst mit DISPLAY versehen."
    NEU_LADEN=1
    APP_NEU=1
fi

# Pfad-Bedingung aus den Diensten nehmen: sie verhinderte den Start, sobald die
# Marke fehlte - der Bildschirm blieb schwarz, die Maus lief weiter.
NEU_LADEN=0
for unit in /etc/systemd/system/kiosk-screen2.service /etc/systemd/system/lhtpi-screen2-watch.service; do
    [ -f "${unit}" ] || continue
    if grep -qE '^ConditionPathExists=/etc/lhtpi/screen2[[:space:]]*$' "${unit}"; then
        sed -i -E '/^ConditionPathExists=\/etc\/lhtpi\/screen2[[:space:]]*$/d' "${unit}"
        sag "Pfad-Bedingung aus $(basename "${unit}") entfernt."
        NEU_LADEN=1
    fi
done
[ "${NEU_LADEN}" = "1" ] && systemctl daemon-reload
if [ "${APP_NEU:-0}" = "1" ]; then
    systemctl restart lhtpi >/dev/null 2>&1 && sag "App neu gestartet (kennt die Bildschirme jetzt)."
fi

# ── 2b. HDMI-Audio abschalten ──────────────────────────────────────────────
# Manche Bildschirme können die Audio-Kanäle nicht zuordnen. Der Treiber
# schreibt dann endlos Fehler ins Log und bremst dabei den Grafiktreiber aus –
# ein Ausgang bleibt schwarz, die Maus läuft weiter. Der Kiosk braucht keinen
# Ton, deshalb wird die Audio-Fähigkeit gar nicht erst ausgelesen.
CONFIG="/boot/firmware/config.txt"
[ -f "${CONFIG}" ] || CONFIG="/boot/config.txt"
if [ -f "${CONFIG}" ]; then
    [ -f "${CONFIG}.vor-lhtpi-audio" ] || cp -a "${CONFIG}" "${CONFIG}.vor-lhtpi-audio" 2>/dev/null || true

    # Ebene 1: EDID-Audio ignorieren
    if grep -qE '^[[:space:]]*hdmi_ignore_edid_audio=1' "${CONFIG}"; then
        sag "hdmi_ignore_edid_audio ist gesetzt."
    else
        printf '\n# LHTPi: kein HDMI-Ton - verhindert die Endlosschleife des Audio-Codecs\nhdmi_ignore_edid_audio=1\n' >> "${CONFIG}"
        sag "hdmi_ignore_edid_audio gesetzt."
        NEUSTART_NOETIG=1
    fi

    # Ebene 2: Audio direkt im KMS-Treiber abschalten (noaudio). Ebene 1 allein
    # reicht nicht - der Codec wird trotzdem angesprochen.
    if grep -qE '^[[:space:]]*dtoverlay=vc4-kms-v3d' "${CONFIG}"; then
        if grep -qE '^[[:space:]]*dtoverlay=vc4-kms-v3d[[:space:]]*,.*noaudio' "${CONFIG}"; then
            sag "KMS-Treiber läuft bereits ohne Audio (noaudio)."
        else
            sed -i -E 's/^[[:space:]]*dtoverlay=vc4-kms-v3d[[:space:]]*$/dtoverlay=vc4-kms-v3d,noaudio/' "${CONFIG}"
            sed -i -E 's/^[[:space:]]*dtoverlay=vc4-kms-v3d,([^n].*)$/dtoverlay=vc4-kms-v3d,noaudio,\1/' "${CONFIG}"
            sag "KMS-Treiber ohne Audio eingetragen (noaudio)."
            NEUSTART_NOETIG=1
        fi
    else
        printf '\ndtoverlay=vc4-kms-v3d,noaudio\n' >> "${CONFIG}"
        sag "KMS-Treiber mit noaudio eingetragen."
        NEUSTART_NOETIG=1
    fi
else
    sag "config.txt nicht gefunden - HDMI-Audio nicht angepasst."
fi

# ── 2c. Versionsdatei nachziehen ───────────────────────────────────────────
# Sie wird von install.sh geschrieben und blieb deshalb nach einem reinen
# git pull auf dem alten Stand - verwirrend, wenn man spaeter nachsieht.
if [ -f "${REPO}/VERSION" ]; then
    NEUE_VERSION="$(tr -d '[:space:]' < "${REPO}/VERSION")"
    ALTE_VERSION="$(cat /etc/lhtpi/version 2>/dev/null || true)"
    if [ -n "${NEUE_VERSION}" ] && [ "${NEUE_VERSION}" != "${ALTE_VERSION}" ]; then
        mkdir -p /etc/lhtpi
        printf '%s' "${NEUE_VERSION}" > /etc/lhtpi/version
        chmod 644 /etc/lhtpi/version
        sag "Version vermerkt: ${ALTE_VERSION:-nichts} -> ${NEUE_VERSION}"
    fi
fi

# ── 2c2. Fehlende Werkzeuge nachinstallieren ─────────────────────────────
# install_packages laeuft nur bei einer Neuinstallation. Nach einem git pull
# fehlte xdotool deshalb, und der Waechter konnte nicht nach Fenstern fragen -
# ausgerechnet das Werkzeug, das den schwarzen Bildschirm erkennt.
fehlt=""
for werkzeug in xdotool xwininfo; do
    command -v "${werkzeug}" >/dev/null 2>&1 || fehlt="${fehlt} ${werkzeug}"
done
if [ -n "${fehlt}" ]; then
    sag "Fehlende Werkzeuge:${fehlt} - versuche nachzuinstallieren."
    if DEBIAN_FRONTEND=noninteractive timeout 120 apt-get install -y -qq xdotool x11-utils >/dev/null 2>&1; then
        sag "Werkzeuge nachinstalliert."
    else
        sag "Nachinstallieren nicht moeglich (kein Netz?) - der Waechter nutzt einen Ersatzweg."
    fi
fi

# ── 2d. Bildschirm-Waechter nachziehen ────────────────────────────────────
# Der Waechter liegt im Repository, laeuft aber aus dem Home-Verzeichnis. Ohne
# diesen Schritt bliebe nach einem git pull die alte Fassung aktiv - und die
# kennt den Fall "Ausgang meldet sich ab" nicht.
WACHE="${HOME_DIR}/lhtpi-screen2-watch.sh"
if [ -f "${REPO}/scripts/hdmi-wache.sh" ] && [ -f "${WACHE}" ]; then
    if ! cmp -s "${REPO}/scripts/hdmi-wache.sh" "${WACHE}"; then
        cp "${REPO}/scripts/hdmi-wache.sh" "${WACHE}"
        chmod +x "${WACHE}"
        chown "${PI_USER}:${PI_GROUP}" "${WACHE}" 2>/dev/null || true
        sag "Bildschirm-Waechter aktualisiert."
        WACHE_NEU=1
    fi
fi

if [ -f "${REPO}/scripts/anzeige-rettung.sh" ]; then
    install -m 0755 "${REPO}/scripts/anzeige-rettung.sh" \
        /usr/local/bin/lhtpi-anzeige-rettung.sh 2>/dev/null || true
fi

# ── 3. Dienste neu starten ─────────────────────────────────────────────────
if command -v systemctl >/dev/null 2>&1; then
    for dienst in kiosk-screen1 kiosk-screen2; do
        systemctl restart "${dienst}" >/dev/null 2>&1 || true
    done
    sag "Kiosk-Dienste neu gestartet."

    if [ "${WACHE_NEU:-0}" = "1" ]; then
        systemctl restart lhtpi-screen2-watch.service >/dev/null 2>&1 || true
        sag "Bildschirm-Waechter neu gestartet."
    fi
fi

# ── 4. Kurz nachsehen, wie die Ausgänge stehen ─────────────────────────────
sleep 3
echo
echo "Bildschirme jetzt:"
DISPLAY=:0 XAUTHORITY="/home/${PI_USER}/.Xauthority" \
    xrandr --query 2>/dev/null | grep -E "^HDMI-[12] connected" || echo "  (nicht abfragbar – kein X oder kein Bildschirm)"
echo
if [ "${NEUSTART_NOETIG:-0}" = "1" ]; then
    echo
    echo "Bitte einmal neu starten, damit die HDMI-Einstellung greift:"
    echo "  sudo reboot"
fi
# Nach dem Nachziehen pruefen, ob die Kette steht - nicht nur die Ausgaenge.
if [ -f "${REPO}/scripts/selbsttest.sh" ]; then
    LHTPI_USER="${PI_USER}" bash "${REPO}/scripts/selbsttest.sh" || true
fi

echo
echo "Fertig. Steht bei beiden dieselbe Position, hat der Treiber es nicht "
echo "akzeptiert – dann steht der Grund in /home/${PI_USER}/kiosk-screen2.log"
