# Aktualisieren

Der Pi holt neue Fassungen direkt aus dem Git-Repository. Es gibt **zwei Wege** —
welcher gilt, hängt davon ab, **was** sich geändert hat:

* **`install.sh` geändert** (Systemeinrichtung: Anmeldung, Dienste, Kiosk-Fenster,
  Lizenzschritt, Autostart) → **voller Weg** (Einrichtung erneut ausführen).
* **nur App-Code geändert** (Oberfläche, Router, Anzeigen) → **kurzer Weg**
  (Dienst neu starten, Einrichtung bleibt).

## 1. Kurz prüfen, was kommt

Per SSH auf dem Pi (`ssh pi@<IP-des-Pi>`, Standard `pi` / `raspberry`):

```bash
cd /home/pi/lhtpi
git fetch origin
git log --oneline -1                                  # was ist drauf?
git log --oneline -1 origin/feature/multitool-kiosk   # was kommt?
git diff --name-only HEAD origin/feature/multitool-kiosk | grep -x install.sh \
  && echo "-> voller Weg (install.sh betroffen)" \
  || echo "-> kurzer Weg (nur App-Code)"
```

## 2a. Voller Weg (install.sh betroffen)

```bash
cd /home/pi/lhtpi
git checkout feature/multitool-kiosk
git pull
sudo bash install.sh
sudo reboot
```

Nach dem Neustart: **kein Login** → die Anzeigen-Seite erscheint → Tools wählen,
„Speichern" → „Einrichtung abschließen und Anzeige starten".

## 2b. Kurzer Weg (nur App-Code)

```bash
cd /home/pi/lhtpi
git checkout feature/multitool-kiosk
git pull
sudo systemctl restart lhtpi.service
# läuft schon eine Anzeige? dann die Fenster frisch laden:
sudo systemctl restart kiosk-screen1.service
sudo systemctl restart kiosk-screen2.service    # nur falls Bildschirm 2 läuft
```

Kein Neustart des Geräts nötig, die Einrichtung (Lizenz, Bildschirme) bleibt
unangetastet.

## 3. Kontrolle, dass es angekommen ist

```bash
cd /home/pi/lhtpi && git log --oneline -1        # erwartet: der neue Commit
systemctl --no-pager status lhtpi.service        # active (running)
curl -s http://localhost:8000/display | grep -c "Anzeige starten"
```

Die Anzeigen-Seite ist von außen (LAN) weiterhin nur mit Login erreichbar
(Standard `admin` / `admin`), am Gerät selbst ohne.

## Wenn der Bildschirm schwarz bleibt

Die Anzeigen-Seite zurück auf den Schirm holen (per SSH):

```bash
sudo systemctl start lhtpi-setup.service
```

Zustandsbericht des Geräts ansehen — die Seite `/diagnose` zeigt Dienste,
Anzeigen, Logs und die Bildschirm-Erkennung als reinen Text (Login nötig,
Standard `admin` / `admin`):

```bash
curl -s -c /tmp/c -b /tmp/c -d 'username=admin&password=admin' \
     http://localhost:8000/login >/dev/null
curl -s -b /tmp/c http://localhost:8000/diagnose
```

## Wenn etwas schiefgeht

```bash
journalctl -u lhtpi.service -n 50 --no-pager     # App-Log
cat /home/pi/setup.log                            # Einrichtungs-Protokoll
```

Alte Fassung zurückholen (Notnagel):

```bash
cd /home/pi/lhtpi
git log --oneline -10          # gewünschten Commit aussuchen
git checkout <commit>
sudo systemctl restart lhtpi.service
```

Der private Lizenzschlüssel liegt **nicht** im Repository — Aktualisieren kann
die Lizenz auf dem Gerät nicht ungültig machen.
