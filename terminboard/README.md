# Terminboard

Anzeigetafel (Digital Signage) für Kalibrierungen und News/Audits — als
eigenständige Flask-App, die **parallel zu LHTPi** auf demselben Raspberry Pi
läuft und auf dem **zweiten HDMI-Ausgang** angezeigt wird.

## Architektur

- Flask + Flask-SQLAlchemy + Flask-Login, SQLite (`terminboard.db`).
- Port **8001** (LHTPi bleibt auf 8000).
- Eigener Chromium-Kiosk auf HDMI-1 (`--window-position=1920,0`).
- USB-Stick mit `termine.csv` als alternative Datenquelle (wie LHTPi: USB hat
  in `auto`-Modus Vorrang, sonst interne DB, manueller Override im Dashboard).

## Schnellstart (lokal)

```bash
cd terminboard
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py          # → http://localhost:8001
```

Login: `admin` / `admin`.

## Endpunkte

| Route | Zugriff | Zweck |
|-------|---------|-------|
| `/` | Login | Dashboard (Termine verwalten) |
| `/login`, `/logout` | öffentlich | Anmeldung |
| `/termine` (GET, `?format=json`) | Login | JSON-Liste |
| `/termine/create` / `<id>/update` / `<id>/delete` | Login | CRUD |
| `/settings/source` | Login | Quelle Auto/Manuell + Web/USB |
| `/board/kiosk` | öffentlich | Kiosk-Anzeige |
| `/board/api/status` | öffentlich | JSON-Status für den Kiosk |

## USB-Stick (`termine.csv`)

Semikolon-getrennt, UTF-8, mit Header-Zeile. Datum als `TT.MM.JJJJ` oder
`JJJJ-MM-TT`.

```
typ;titel;referenz;start;ende;text
kalibrierung;Druckprüfstand P3;P3;25.08.2026;30.08.2026;Jährlich
audit;ISO-Audit QS;;14.09.2026;;
info;Neue Schichtregelung;;01.09.2026;;
```

`typ` ∈ `kalibrierung | audit | info | wartung` (sonst `info`). Zeilen ohne
Titel sowie Leer-/Kommentarzeilen (`#`) werden ignoriert.

## Installation auf dem Pi

**Voraussetzung:** LHTPi `install.sh` wurde bereits ausgeführt (X11/Openbox/
LightDM/NetworkManager-AP vorhanden).

```bash
cd /home/pi/lhtpi/terminboard
sudo bash install.sh
```

Das Skript legt `terminboard.service` (Port 8001) und
`terminboard-kiosk.service` (zweiter Monitor) an, richtet den USB-Auto-Mount
nach `/mnt/terminboard-usb` ein und gibt Port 8001 in der Firewall frei.

> ⚠️ **Dual-Screen-Hinweis:** Die Positionierung des zweiten Chromium-Fensters
> auf HDMI-1 (`SCREEN2_X` in `/home/pi/start_terminboard_kiosk.sh`) muss einmal
> auf echter Hardware verifiziert werden — das ist der einzige hardwareabhängige
> Punkt. Standardannahme: erster Monitor 1920 px breit.

## Tests

```bash
cd terminboard
./venv/bin/pip install pytest
./venv/bin/python -m pytest tests/ -q
```

## Sicherheit

- Session-Cookies mit `SameSite=Lax` und `HttpOnly` gesetzt.
- Kein CSRF-Schutz (bewusste Entscheidung wie bei LHTPi — LAN/Offline-Kiosk mit
  Login). Bei Bedarf später `Flask-WTF` ergänzen.
- Default-Login `admin`/`admin` — für den Produktivbetrieb das Passwort ändern
  (aktuell kein UI dafür; per Env/DB oder zukünftiges Feature).

## Farbthema

Lufthansa-Stil: Navy `#05164D`, Gelb `#FFAD00`, Sekundär-Blau `#1B4B8F`,
heller Hintergrund `#F4F6FA`.
