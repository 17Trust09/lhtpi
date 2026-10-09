# Safety Cross ⛑️

Digitale Anzeigetafel (Safety Cross) für Arbeitssicherheit — ein **offline-fähiger
Raspberry-Pi-Kiosk** mit Web-Admin.

- **Anzeige:** Monats-Kreuz (Plus-Form), vergangene/heutige Tage grün/gelb/rot,
  zukünftige Tage weiß, „Tage unfallfrei“-Zähler, Ersthelfer, Abteilung + Meister,
  Notruf & wichtige Nummern.
- **Admin** (passwortgeschützt): Abteilung, Meister, Ersthelfer, Notruf & wichtige
  Nummern, Zählung (Tage ODER Startdatum), Unfall-Meldung (Datum · Typ · Person ·
  Beschreibung), Historie (Monate blättern), System (Neustart/Herunterfahren).
- **Lizenz:** hardware-gebunden (Pi-Seriennummer + HMAC) → nicht trivial kopierbar.

## Installation

Auf einem Raspberry Pi (32-bit Raspberry Pi OS **Desktop**):

```bash
git clone https://github.com/17Trust09/safety-cross.git
cd safety-cross
sudo bash install.sh
sudo reboot
```

`install.sh` richtet ein: venv + Flask-App, SQLite-DB (Login `admin`/`admin`),
Lizenz-Key, Chromium-Kiosk (Fullscreen, dauerhaft 200 % Zoom), Maus-Auto-Hide (via CSS),
die Uhr (**DS3231-RTC, falls vorhanden, sonst `fake-hwclock`**) und deaktiviert das
Bildschirm-Abschalten (Idle/DPMS) für eine Daueranzeige.

## Lokal entwickeln

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python app.py        # http://127.0.0.1:8002
```

## Tests

```bash
venv/bin/pip install pytest
venv/bin/python -m pytest tests/ -q
```

## Struktur

```
app.py        Flask-App + Routen
db.py         SQLite-Datenschicht (config, ersthelfer, notruf, days)
auth.py       Passwort-Hash + Login-Schutz
license.py    Hardware-Lizenz (Seriennummer + HMAC)
templates/    board.html · login.html · admin.html · locked.html
static/       style.css
install.sh    Ein-Run-Setup
```
