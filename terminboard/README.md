# Terminboard

Anzeigetafel (Digital Signage) für Kalibrierungen und News/Audits — als
eigenständige Flask-App, die **parallel zu LHTPi** auf demselben Raspberry Pi
läuft und auf dem **zweiten HDMI-Ausgang (HDMI-A-2)** angezeigt wird.

## Architektur

- Flask + Flask-SQLAlchemy + Flask-Login, SQLite (`terminboard.db`).
- Port **8001** (LHTPi bleibt auf 8000).
- Eigener Chromium-Kiosk auf **HDMI-A-2** — feste Zuordnung via `xrandr`
  (`HDMI-A-1` primär, `HDMI-A-2` rechts) plus Openbox-Regel
  (`<application name="Terminboard*"><monitor>2</monitor>`), auflösungs- und
  positionsunabhängig.
- USB-Stick mit **`termine.xlsx`** als Datenquelle (Excel-Vorlage, Fallback
  `termine.csv`). In `auto`-Modus hat USB Vorrang, sonst interne DB, manueller
  Override im Dashboard.

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

## Datenmodell (`models.py`)

| Feld | Typ | Hinweis |
|------|-----|---------|
| `typ` | String | `kalibrierung`/`audit`/`info`/`wartung` (sonst `info`) |
| `titel` | String | **Pflicht**, UI-Label „Info" |
| `referenz` | String | **Pflicht**, UI-Label „Prüfstand" (z. B. `P3`) |
| `start` | Date | **Pflicht**, UI-Label „Von" |
| `ende` | Date | optional, UI-Label „Bis" |
| `text` | String | optional, UI-Label „Notiz" (nur Web-Formular) |

## USB-Stick (`termine.xlsx`)

Bevorzugte Quelle ist die **Excel-Vorlage** mit 5 Spalten, Dropdown für die
Art, Datumsfeldern und einem Anleitung-Blatt:

```text
Art | Prüfstand | Von | Bis | Info
```

| Spalte | Bedeutung | Pflicht |
|---|---|---|
| Art | Kalibrierung/Audit/Wartung/Info | ✓ Dropdown |
| Prüfstand | z. B. `P3` | ✓ |
| Von | Startdatum `TT.MM.JJJJ` | ✓ |
| Bis | Enddatum | – |
| Info | Beschreibung | ✓ |

**Fallback `termine.csv`** (Semikolon-getrennt, UTF-8, Header
`typ;titel;referenz;start;ende;text`, Datum `TT.MM.JJJJ` ODER `JJJJ-MM-TT`).
Liegt eine gültige `.xlsx` vor, hat sie Vorrang; ist sie kaputt/nicht lesbar,
fällt die App automatisch auf die CSV zurück.

Vorlage neu erzeugen (lokal):

```bash
cd terminboard
./venv/bin/python generate_termine_template.py
```

## Installation auf dem Pi

Der kombinierte Installer im Repo-Root installiert LHTPi und/oder Terminboard
in einem Durchgang (Menü `1) LHTPi · 2) Terminboard · 3) Beides`):

```bash
cd /home/pi/lhtpi
sudo bash install.sh 3
```

Der Installer erledigt: Systempakete, venv + Abhängigkeiten, systemd-Services
(`terminboard.service` Port 8001, `terminboard-kiosk.service`), Chromium-Kiosk
auf HDMI-A-2, gemeinsamer USB-Auto-Mount (`/mnt/lhtpi-usb`), Firewall.

## Tests

```bash
cd terminboard
./venv/bin/python -m pytest tests/ -q    # 34 passed
```

## Sicherheit

- Session-Cookies mit `SameSite=Lax` und `HttpOnly` gesetzt.
- Kein CSRF-Schutz (bewusste Entscheidung wie bei LHTPi — LAN/Offline-Kiosk mit
  Login). Bei Bedarf später `Flask-WTF` ergänzen.
- Default-Login `admin`/`admin` — für den Produktivbetrieb das Passwort ändern.

## Farbthema

Lufthansa-Stil: Navy `#05164D`, Gelb `#FFAD00`, Sekundär-Blau `#1B4B8F`,
heller Hintergrund `#F4F6FA`.
