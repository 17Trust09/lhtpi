#!/bin/bash
# Live-Prüfung der Ersteinrichtung über echtes HTTP (frische Datenbank, kein Merkmal)
set -u
cd /opt/data/projects/lhtpi
rm -rf /tmp/erst
mkdir -p /tmp/erst

export LHTPI_DB=/tmp/erst/lhtpi.db LHTPI_PORT=8904 \
       LHTPI_TOOLS=slideshow,terminboard,safetycross \
       LHTPI_HWID=piserial:10000000erst \
       LHTPI_LICENSE_FILE=/tmp/erst/license.key \
       LHTPI_INSTALLED_MARKER=/tmp/erst/installed \
       LHTPI_SCREENS_FILE=/tmp/erst/screens \
       LHTPI_KIOSK_PROBE=0 LHTPI_SCREEN_COUNT=2

./venv/bin/python license_bundle.py --install --tools=slideshow,terminboard,safetycross --screens=2

./venv/bin/python app.py > /tmp/erst/app.log 2>&1 &
APP_PID=$!
sleep 5

B=http://localhost:8904
curl -s -c /tmp/erst/cookies -o /dev/null "$B/login"
curl -s -b /tmp/erst/cookies -c /tmp/erst/cookies -o /dev/null -d "username=admin&password=admin" "$B/login"

echo "=== 1) Vorher: Banner auf der Anzeigen-Seite? ==="
curl -s -b /tmp/erst/cookies "$B/display" -o /tmp/erst/vorher.html
grep -o "Erste Einrichtung" /tmp/erst/vorher.html | head -1
grep -o "Erkannte Ausgänge: <b>[0-9]*</b>" /tmp/erst/vorher.html | head -1
grep -c "Einrichtung abschließen" /tmp/erst/vorher.html

echo "=== 2) Dateien vor dem Abschluss ==="
ls /tmp/erst/installed 2>&1 | tail -1
ls /tmp/erst/screens 2>&1 | tail -1

echo "=== 3) Einrichtung abschließen ==="
curl -s -b /tmp/erst/cookies -o /dev/null -w "HTTP %{http_code} -> %{redirect_url}\n" \
     -X POST "$B/setup/abschluss"

echo "=== 4) Dateien danach ==="
ls -l /tmp/erst/installed /tmp/erst/screens 2>&1 | tail -2
echo "screens-Inhalt: $(cat /tmp/erst/screens 2>/dev/null)"

echo "=== 5) Nachher: Banner verschwunden? ==="
curl -s -b /tmp/erst/cookies "$B/display" -o /tmp/erst/nachher.html
grep -c "Erste Einrichtung" /tmp/erst/nachher.html

echo "=== 6) Anzeige-Seiten weiter erreichbar ==="
for p in /screen/1 /screen/2 /api/screens; do
    printf '%-14s HTTP %s\n' "$p" "$(curl -s -o /dev/null -w '%{http_code}' "$B$p")"
done

kill "$APP_PID" 2>/dev/null
wait "$APP_PID" 2>/dev/null
echo "fertig"
