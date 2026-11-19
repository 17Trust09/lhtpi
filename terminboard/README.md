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
./venv/bin/python tools_vorlage_modell3_bauen.py            # Modell-3-Vorlage
./venv/bin/python tools_vorlage_modell3_bauen.py --pruefen  # Vorlage prüfen
```

## Modell 3 – Excel-Arbeitsablauf

Die Excel-Datei `termine.xlsx` ist seit Modell 3 die eindeutige Datenquelle.
Die Anwender arbeiten ausschließlich in Excel; eine Webverwaltung ist für den
Alltag nicht nötig.

**Blätter:** `Termine` (Kalibrierung/Wartung/Ausfall), `News & Audits`
(Audit/Info), `Betriebsmittel` (Stammdaten), `Zeiten` (Uhrzeiten), plus die
beiden Archive.

### Betriebsmittel anlegen, umbenennen, Typ ändern, zusammenführen

1. **Neu anlegen:** Im Blatt `Betriebsmittel` unten eine Zeile ergänzen –
   `Typ` (Prüfstand/Konsole) und `Bezeichnung`. Die `ID`-Spalte bleibt leer;
   das Gerät vergibt beim ersten Import die feste Kennung `BM-001` usw. und
   schreibt sie zurück.
2. **Auswählen:** Im Blatt `Termine` wird das Betriebsmittel ausschließlich
   über das Dropdown gewählt (Spalte `Betriebsmittel`). Freie Eingaben blockt
   Excel.
3. **Umbenennen:** Einfach die `Bezeichnung` ändern – die `ID` bleibt. Historie
   und Berichte zeigen ab sofort den neuen Namen; Stunden werden nicht neu
   gebucht.
4. **Typ ändern:** `Prüfstand` ↔ `Konsole` bei gleicher `ID` ist erlaubt.
   Berichte ordnen das Betriebsmittel rückwirkend der richtigen Kategorie zu.
5. **Zusammenführen:** In der Spalte `Zusammenführen mit` die Ziel-`BM-NNN`
   eintragen. Alle Vorgänge der Quelle werden atomar auf das Ziel umgehängt,
   die Quelle bleibt intern als Alias erhalten. Selbst- und Ring-Zusammenführung
   werden abgelehnt.
6. **Entfernen:** Eine Zeile ohne Zusammenführung löschen entfernt das
   Betriebsmittel aus der aktiven Liste – die Historie bleibt erhalten, nur das
   Dropdown führt es nicht mehr.

### Nummern (T/N) und Archive

- Termine haben `T-001 … T-500`, News/Audits `N-001 … N-500`. Die Nummern sind
  vorausgefüllt und gesperrt; eine Nummer darf nur in genau einem der beiden
  Blätter (aktiv oder Archiv) vorkommen.
- Beim Status `abgeschlossen` verschiebt das Gerät die Zeile automatisch ins
  passende Archiv (`Archiv Termine` bzw. `Archiv News & Audits`). Die Nummer
  bleibt erhalten und wird nie wiederverwendet.
- `Zeiten` verweist ausschließlich auf `T-Nummern` (nicht auf News).

### Schreibgeschützter Stick und `.bak`-Wiederherstellung

- Vor jeder Änderung der Arbeitsmappe legt das Gerät eine `.bak`-Sicherung an
  und schreibt erst in eine temporäre Datei, prüft sie, und ersetzt dann das
  Original atomar.
- Ein schreibgeschützter Stick verhindert den **Import** nicht: die Daten werden
  gelesen, nur das Zurückschreiben (IDs, Archiv) wird gemeldet und beim nächsten
  Lauf erneut versucht.
- Wiederherstellung: die jüngste `<datei>.bak` nach `termine.xlsx` zurückkopieren.

### Migration von Modell 2 auf Modell 3

```bash
cd terminboard
./venv/bin/python tools_modell2_zu_modell3.py --quelle alt.xlsx --ziel neu.xlsx
# oder in place (sichert alt.xlsx → alt.xlsx.bak):
./venv/bin/python tools_modell2_zu_modell3.py --quelle alt.xlsx --ersetzen
```

Termine und Archivzeilen werden übernommen, `T-/N-Nummern` deterministisch neu
vergeben, Audit/Info wandern nach `News & Audits`, `Zeiten`-Blöcke werden auf
die neuen Nummern abgebildet. Nicht zuordenbare Zeilen werden gemeldet, nie
still verworfen. `TESTFUCHS KONSOLE …` (und die exakt so eingetragene
Schreibweise `TESTTUCHS KONSOLE …`) werden als Konsole eingestuft, alles andere
als Prüfstand.

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
./venv/bin/python -m pytest tests/ -q
```

## Sicherheit

- Session-Cookies mit `SameSite=Lax` und `HttpOnly` gesetzt.
- Kein CSRF-Schutz (bewusste Entscheidung wie bei LHTPi — LAN/Offline-Kiosk mit
  Login). Bei Bedarf später `Flask-WTF` ergänzen.
- Default-Login `admin`/`admin` — für den Produktivbetrieb das Passwort ändern.

## Farbthema

Lufthansa-Stil: Navy `#05164D`, Gelb `#FFAD00`, Sekundär-Blau `#1B4B8F`,
heller Hintergrund `#F4F6FA`.
