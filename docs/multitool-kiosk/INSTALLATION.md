# Multitool-Kiosk — Installation

Ein Raspberry Pi, bis zu **drei Tools**, ein oder zwei Bildschirme. Der Installer
richtet alles ein; **welche Tools auf welchen Bildschirmen laufen, wird beim
ersten Start auf dem Bildschirm gefragt** (Maus + Tastatur) — siehe
[ERSTEINRICHTUNG.md](ERSTEINRICHTUNG.md).

## Tools

| Ziffer | Tool | Port | Rolle |
|---|---|---|---|
| 1 | **Folien / Playlist** (Slideshow) | 8000 | Teil der Verteiler-App |
| 2 | **Terminboard** (Termine, Kalibrierungen) | 8001 | eigenes Tool |
| 3 | **Safety Cross** (Arbeitssicherheit) | 8002 | eigenes Tool |

Die **Verteiler-App** (Port 8000) ist immer installiert. Sie trägt Dashboard,
Anzeige-Router und Lizenz — also die Stelle, an der eingestellt wird, welches
Tool welchen Bildschirm nutzt.

## Installation

```bash
cd /home/pi/lhtpi
sudo bash install.sh                 # richtet alles ein; gefragt wird beim ersten Start
sudo bash install.sh --tools=1,3 --screens=2 --no-reboot    # Image-Vorbereitung ohne Fragen
```

Optionen:

| Option | Bedeutung |
|---|---|
| `--tools=1,2,3` | welche Tools installiert werden (Standard: alle; auch Namen: `slideshow,terminboard,safetycross`) |
| `--screens=1\|2` | wie viele Bildschirme die Lizenz erlaubt (Standard: 2) |
| `--no-reboot` | kein automatischer Neustart am Ende |
| `--help` | Hilfe |

Gewählt wird auf dem Gerät: Beim ersten Start erscheint die Anzeigen-Seite auf
dem Bildschirm, dort werden Tools, Bildschirme und Anzeigedauern eingestellt.
`--tools=` / `--screens=` sind nur für die Image-Vorbereitung gedacht.

**Kein Access Point:** das Gerät richtet kein WLAN ein und verändert keine
WLAN-Verbindungen (frühere Versionen machten `wlan0` zum AP `LHTPi` — das ist
entfernt).

Beispiele: `--tools=3` (nur Safety Cross, eine Abteilung), `--tools=1,2`
(Folien + Termine), `--tools=1,2,3 --screens=2` (alles, zwei Bildschirme).

## Was der Installer einrichtet

* Verteiler-App (Dashboard, Anzeige-Router, Lizenz) auf Port 8000
* nur die **gewählten** Tools zusätzlich (Terminboard und/oder Safety Cross)
* **ein Chromium-Kiosk je Bildschirm**: `kiosk-screen1.service`,
  `kiosk-screen2.service` — jeder öffnet `http://localhost:8000/screen/<n>`
* Monitor-Zuordnung: Bildschirm 1 = HDMI-1 (primär, links),
  Bildschirm 2 = HDMI-2 (rechts daneben)
* zwei Kiosk-Merker für die App:
  * `/etc/lhtpi/tools` — welche Tools auf diesem Gerät laufen
  * `/etc/lhtpi/screens` — wie viele Bildschirme (Startwert für die Einstellungen)
* Hardware-Lizenz für dieses Gerät (siehe `PLAN.md`, Paket S5)
* Kiosk-Services früherer Versionen (ein Kiosk je Tool) werden entfernt

## Einstellen (das Wichtigste im Betrieb)

Dashboard aufrufen: `http://<LAN-IP>:8000` → Menü **🧩 Anzeigen**
(oder direkt `http://<LAN-IP>:8000/display`). Dort steht je Bildschirm:

* **Name** und **HDMI-Ausgang**
* **Bildschirm an/aus**
* **welche Tools** auf diesem Bildschirm laufen
  * genau **ein** Tool → bleibt stehen (kein Wechsel)
  * **mehrere** Tools → sie **wechseln sich ab**
* **Anzeigedauer je Tool** in Sekunden
  (Beispiel: Projekt 1 = 300 s / 5 min, Projekt 2 = 120 s / 2 min)
* **Reihenfolge** (Sortierwert) innerhalb der Rotation
* **Cursor-Idle**: Sekunden ohne Mausbewegung, bis der Zeiger verschwindet
  — beim Bewegen ist er sofort wieder da (in allen drei Tools gleich)
* **Frame-Reload**: Minuten, nach denen ein eingebettetes Tool neu geladen wird
* **Zahl der Bildschirme** (1 oder 2)

Nur installierte Tools sind auswählbar. Ein Tool, dessen Dienst gerade nicht
läuft, wird in der Rotation **übersprungen** (kein schwarzer Bildschirm).

## Mauszeiger

Der Zeiger wird **nicht** auf Systemebene ausgeblendet (kein `unclutter`, kein
transparentes Cursor-Thema, keine Chromium-Extension). Das Ausblenden nach
Inaktivität und das sofortige Wiedereinblenden bei Bewegung macht die Anzeige
selbst — dieselbe Logik in allen drei Tools, Referenz `tools/kiosk-cursor.js`,
Idle-Zeit aus den Einstellungen.

## Nach der Installation prüfen

```bash
systemctl status lhtpi.service kiosk-screen1.service kiosk-screen2.service
curl -s localhost:8000/api/screens        # Zuordnung Bildschirm -> Tools
cat /etc/lhtpi/tools /etc/lhtpi/screens   # was installiert ist
```

## Screenshots

In `docs/multitool-kiosk/screenshots/` liegen echte Aufnahmen (keine Mockups):
`00-uebersicht.png` (alle neun auf einer Tafel), Dashboard, Einstellungen,
Lizenz, Anzeige Schirm 1 (Rotation) und 2 (fest), die drei Tools einzeln und
die Sperrseite.

Neu erzeugen (auf einem Rechner, nicht auf dem Pi):

```bash
bash tools/shots-setup.sh                 # Chrome-for-Testing + Playwright
./venv/bin/python tools/shots-demo-daten.py   # Demo-Daten + Titelbilder
# Demo-Instanzen starten (eigene Ports, eigene DBs):
LHTPI_DB=/tmp/shots/lhtpi.db LHTPI_PORT=8900 LHTPI_SCREEN_COUNT=2 \
  LHTPI_TOOL_URLS="slideshow=http://localhost:8900/present/kiosk,terminboard=http://localhost:8901/board/kiosk,safetycross=http://localhost:8902/" \
  LHTPI_LICENSE_FILE=/tmp/shots/license.key ./venv/bin/python app.py
# + Terminboard auf 8901, Safety Cross auf 8902, gesperrte Instanz auf 8903
/tmp/shots-venv/bin/python tools/shots-machen.py      # PNGs
./venv/bin/python tools/shots-uebersicht.py           # Übersichtstafel
```

Hinweis: Die Demo-Instanzen laufen bewusst auf **anderen Ports** (8900+). Auf
Port 8000 kann ein fremder Dienst liegen (z. B. Django) — dann startet die App
dort nicht und die Screenshots zeigen die falsche Seite.

## Hardware-Lizenz

Jede Installation ist an **dieses** Gerät gebunden (Seriennummer des Pi). Die
Lizenz schaltet frei, **welche Tools** und **wie viele Bildschirme** erlaubt
sind. Eine kopierte SD-Karte auf einem anderen Pi ist damit ungültig.

* Schlüsselformat: `LHTPI-XXXX-XXXX-XXXX-XXXX`
* Ablage: `/etc/lhtpi/license.key`, Merkmal `/etc/lhtpi/installed`
* Der Installer erzeugt die Lizenz passend zur gewählten Ausstattung selbst.
* Status ansehen: `http://<LAN-IP>:8000/lizenz` (auch bei gesperrter App)
  oder auf der Konsole:

```bash
cd /home/pi/lhtpi
./venv/bin/python license_bundle.py --check     # gilt die Lizenz hier?
./venv/bin/python license_bundle.py --info      # Geräte-ID für den Hersteller
```

* Ist die Lizenz ungültig, zeigen alle Seiten eine Sperrseite mit der
  Geräte-ID — diesen Wert zum Nachfragen weitergeben.
* Steht die Anzeige im **Entwicklungsmodus** (keine Lizenz, kein Merkmal),
  laufen alle installierten Tools ohne Sperre. Auf einem ausgelieferten Gerät
  ist immer eine Lizenz vorhanden.

> Sicherheitshinweis: Der Signaturschlüssel steckt im Modul `license_bundle.py`.
> Im Kunden-Image gehört er verschleiert (siehe Skill
> `python-source-protection`), sonst lassen sich Lizenzen selbst erzeugen.

## Sicherheitshinweis

Die App-Ports 8000/8001/8002 sind im LAN offen (Firewall/UFW im Installer
entsprechend gesetzt). Die Standard-Logins (`admin` / `admin`) **bitte sofort
ändern** und für die Pi-Adresse eine DHCP-Reservierung im Router eintragen,
damit die LAN-IP stabil bleibt.
