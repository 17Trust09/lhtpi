#!/bin/bash
# Live-Prüfung des Lizenz-Kopierschutzes über HTTP.
#
# Braucht den echten privaten Signaturschlüssel (außerhalb des Repos):
#   LHTPI_SIGN_KEY_FILE=/pfad/privat.json bash tools/test-lizenz-live.sh
# Ohne Schlüssel wird der Lauf übersprungen (auf dem Kundenimage gibt es ihn nicht).
set -u
cd "$(dirname "$0")/.."
PROJEKT="$(pwd)"

SIGN="${LHTPI_SIGN_KEY_FILE:-$HOME/.lhtpi/lizenz-privat.json}"
if [ ! -f "$SIGN" ]; then
    echo "Kein Signierschlüssel ($SIGN) – Prüfung übersprungen."
    exit 0
fi

TMP="$(mktemp -d /tmp/lhtpi-lizenz-live-XXXX)"
GERAET_A="piserial:10000000geraetA"
GERAET_B="piserial:10000000geraetB"
PORT=8905
B="http://localhost:$PORT"

export LHTPI_DB="$TMP/app.db" LHTPI_PORT="$PORT" \
       LHTPI_TOOLS=slideshow,terminboard,safetycross \
       LHTPI_LICENSE_FILE="$TMP/license.key" \
       LHTPI_INSTALLED_MARKER="$TMP/installed" \
       LHTPI_SCREENS_FILE="$TMP/screens" \
       LHTPI_LICENSE_ENFORCE=1 LHTPI_SCREEN_COUNT=2 \
       LHTPI_TOOL_URLS="slideshow=$B/present/kiosk,terminboard=$B/board/kiosk,safetycross=$B/"

start() {   # start() <Geräte-ID>
    LHTPI_HWID="$1" ./venv/bin/python app.py > "$TMP/app.log" 2>&1 &
    APP_PID=$!
    for _ in $(seq 20); do
        sleep 0.5
        curl -s -o /dev/null "$B/login" && return 0
    done
    echo "App startet nicht – Log:"; tail -5 "$TMP/app.log"; exit 1
}
stop() { kill "$APP_PID" 2>/dev/null; wait "$APP_PID" 2>/dev/null; }
code() { curl -s -o "$TMP/seite.html" -w '%{http_code}' "$B$1"; }

echo "=== Schritt 1: ohne Lizenz sperrt das Gerät ==="
start "$GERAET_A"
printf '/screen/1  HTTP %s\n' "$(code /screen/1)"
grep -o "Geräte-ID[^<]*<[^>]*>[^<]*" "$TMP/seite.html" | head -1
stop

echo
echo "=== Schritt 2: Lizenz mit dem echten Schlüssel erzeugen ==="
LHTPI_HWID="$GERAET_A" LHTPI_SIGN_KEY_FILE="$SIGN" \
    ./venv/bin/python license_bundle.py --make-key --tools=1,2,3 --screens=2 > "$TMP/neu.key"
echo "Lizenz: $(head -c 12 "$TMP/neu.key")… ($(wc -c < "$TMP/neu.key") Bytes), Gerät $GERAET_A"
cp "$TMP/neu.key" "$LHTPI_LICENSE_FILE"

echo
echo "=== Schritt 3: gleiches Gerät -> freigeschaltet ==="
start "$GERAET_A"
for p in /screen/1 /screen/2 /api/screens; do
    printf '%-14s HTTP %s\n' "$p" "$(code $p)"
done
stop

echo
echo "=== Schritt 4: dieselbe Lizenz auf einem anderen Pi -> gesperrt ==="
start "$GERAET_B"
printf '/screen/1  HTTP %s\n' "$(code /screen/1)"
grep -o "gehört zu einem anderen Gerät\|nicht freigeschaltet" "$TMP/seite.html" | head -1
stop

echo
echo "=== Schritt 5: veränderte Lizenz -> gesperrt ==="
python3 - "$TMP/neu.key" "$LHTPI_LICENSE_FILE" <<'PYEOF'
import sys
roh = open(sys.argv[1]).read()
# ein Zeichen der Signatur kippen
zeichen = list(roh.strip())
for i in range(len(zeichen) - 1, -1, -1):
    if zeichen[i].isalnum():
        zeichen[i] = 'F' if zeichen[i].upper() != 'F' else 'E'
        break
open(sys.argv[2], 'w').write(''.join(zeichen) + '\n')
PYEOF
start "$GERAET_A"
printf '/screen/1  HTTP %s\n' "$(code /screen/1)"
grep -o "nicht freigeschaltet" "$TMP/seite.html" | head -1
stop

rm -rf "$TMP"
echo
echo "fertig"
