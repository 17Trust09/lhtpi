# Terminboard — Anzeigetafel für Kalibrierungen & News/Audits

## Ziel

Zweites Kiosk-Projekt auf demselben Raspberry Pi wie LHTPi (Raspberry Pi 4/5,
Raspberry Pi OS Desktop Trixie). Läuft als **eigenständige** Flask-App auf
**Port 8001** und wird auf dem **zweiten HDMI-Ausgang (HDMI-1)** als eigener
Chromium-Kiosk angezeigt.

Inhalt: eine professionelle Terminübersicht (Anzeigetafel) mit zwei Bereichen:

1. **Kalibrierungen** — Tabelle (Prüfstand | Art | Zeitraum | Resttage/Status)
2. **News & Audits** — Feed-Liste mit farbigem Typ-Badge (optionaler Zeitraum)

## Architektur

- Eigener Unterordner `terminboard/` im LHTPi-Repo. **Bestehende LHTPi-Dateien
  im Repo-Root (`app.py`, `models.py`, `routes.py`, `usb_source.py`, `install.sh`,
  `templates/`, `static/`) NICHT anfassen oder verändern.**
- Eigene SQLite-DB (`terminboard.db`), eigener Login (`admin`/`admin`), eigenes
  Port (8001), eigenes venv.
- Gleiche Bauart wie LHTPi (Flask + Flask-SQLAlchemy + Flask-Login), aber
  **ohne** Medien-Upload/Playlists.
- UI komplett Deutsch. Vanilla JS, **keine externen Frameworks/CDN/Fonts**
  (der Pi ist offline).

## Zu erstellende Dateien (alle unter `terminboard/`)

```
terminboard/
├── app.py
├── models.py
├── routes.py
├── usb_source.py
├── requirements.txt
├── install.sh
├── README.md
├── templates/
│   ├── login.html
│   ├── dashboard.html
│   └── board.html
├── static/
│   └── style.css
└── tests/
    └── test_terminboard.py
```

## App-Konfiguration (`app.py`)

- `Flask(__name__)`, Secret über Env `TERMINBOARD_SECRET`
  (Fallback `terminboard-dev-secret-change-me`).
- DB-Pfad über Env `TERMINBOARD_DB`, sonst `terminboard.db` im App-Ordner.
- `Flask-Login` (LoginManager), Default-Admin `admin`/`admin` beim Start anlegen
  (wie LHTPi).
- `db.create_all()` im App-Kontext.
- Port über `TERMINBOARD_PORT` (Default **8001**), Host `TERMINBOARD_HOST`
  (Default `0.0.0.0`).

## Datenmodell (`models.py`)

**User** (wie LHTPi): id, username, password_hash, set_password/check_password.

**Termin**:

| Feld | Typ | Hinweis |
|------|-----|---------|
| id | int PK | |
| typ | String | erlaubt: `kalibrierung`, `audit`, `info`, `wartung` (Default `info`) |
| titel | String | Pflicht |
| referenz | String | optional, z. B. `P3` (Prüfstand/Anlage) |
| start | Date | Pflicht |
| ende | Date | optional (leer bei News ohne Zeitraum) |
| text | String | optionaler Einzeiler |
| created_at | DateTime | default now |

**Setting** (Key/Value, wie LHTPi): für `player_mode` (`auto`/`manual`) und
`manual_source` (`web`/`usb`).

## Routen (`routes.py`)

- `GET/POST /login`, `GET /logout` — Login (admin/admin).
- `GET /` → Dashboard (login-required).
- Termin-CRUD (login-required, AJAX-fähig):
  - `GET /termine` (JSON via `?format=json` oder `X-Requested-With`)
  - `POST /termine/create`
  - `POST /termine/<id>/update`
  - `POST /termine/<id>/delete`
- `GET /settings/source` + `POST /settings/source` — Quelle Auto/Manuell + Web/USB.
- **Öffentlich (ohne Login, für den Kiosk):**
  - `GET /board/kiosk` → `board.html`
  - `GET /board/api/status` → JSON

AJAX-Helfer `is_ajax()` + `ajax_or_redirect()` wie in LHTPi übernehmen. Jeder
`return`-Pfad einer POST-Route muss bei AJAX JSON liefern (kein Redirect).

## Source-Logik (Auto/Manuell — wie LHTPi)

- Modus `manual`: feste Quelle aus `manual_source` (`web`/`usb`).
- Modus `auto` (Standard): **USB-CSV hat Vorrang**, sonst interne DB.
- `/board/api/status` liefert `source`, `mode`, `usb_present` und die Einträge.

## USB-Quelle (`usb_source.py`)

- USB-Stick-Root enthält **`termine.csv`** (Semikolon-getrennt, UTF-8, mit
  Header-Zeile).
- Spalten (exakt): `typ;titel;referenz;start;ende;text`
- Datum: **`TT.MM.JJJJ` ODER `JJJJ-MM-TT`** (beides parsen). Leere Felder erlaubt
  (`referenz`, `ende`, `text` optional).
- Parser fehlertolerant: Whitespace strippen, Leer-/Kommentarzeilen (`#`) und
  Zeilen mit zu wenigen Spalten ignorieren.
- Mount-Erkennung wie LHTPi (`os.listdir`-Guard gegen stale Mount), fester
  Mount-Pfad **`/mnt/terminboard-usb`**.
- Liefert eine Liste von Termin-Dicts (gleiche Form wie DB-Termine).

## Kiosk (`board.html`, öffentlich)

- Header mit **aktuellem Datum** (deutsch, z. B. „Dienstag, 25. August 2026").
- Abschnitt **KALIBRIERUNGEN**: Tabelle mit Spalten
  `Prüfstand | Art/Titel | Zeitraum | Resttage/Status`.
- Abschnitt **NEWS & AUDITS**: Feed mit farbigem Typ-Badge, Titel, Datum/Zeitraum,
  Einzeiler.
- **Resttage** live in JS berechnet: `start − heute`.
- **Status-Farbcode:** 🟢 grün >7 Tage · 🟡 gelb 0–7 Tage · 🔴 rot heute ·
  🔵 blau „läuft" (start ≤ heute ≤ ende).
- **Vergangene Einträge ausblenden** (`ende < heute` → nicht anzeigen).
- Einträge nach `start` aufsteigend sortieren (ohne `start` ans Ende).
- Poll `GET /board/api/status` alle **30 s**.
- `cursor:none`, reine Anzeige (keine Interaktion).

## `board/api/status` (JSON)

```json
{
  "source": "web|usb",
  "mode": "auto|manual",
  "usb_present": true,
  "termine": [ {"id","typ","titel","referenz","start","ende","text"} ],
  "kalibrierungen": [...],
  "news": [...]
}
```
`start`/`ende` als `YYYY-MM-DD` (oder `null`). `kalibrierungen` = typ `kalibrierung`;
`news` = alle anderen Typen.

## Farbthema (`static/style.css`) — Lufthansa-Stil

| Variable | Wert | Verwendung |
|----------|------|------------|
| Navy-Blau | `#05164D` | Header, Tabellenkopf, primäre Flächen |
| Gelb | `#FFAD00` | Akzent, Badges, Hervorhebung, „läuft"-Status |
| Sekundär-Blau | `#1B4B8F` | Gradienten/Hover |
| Hintergrund | `#FFFFFF` / `#F4F6FA` | helle Flächen |
| Text | `#1A1A1A` | |
| Muted | `#5D6B7C` | |

Sauber, corporate, professionell. **Helles Theme** (kein Dark-Theme). Dashboard
und Login im selben Farbsystem.

## `install.sh` (Add-on, in `terminboard/`)

Eigenständiges Skript, das **voraussetzt, dass LHTPi `install.sh` bereits
ausgeführt wurde** (X11/Openbox/LightDM/NetworkManager-AP vorhanden). Das im
Skript-Header dokumentieren. Aufgaben:

1. terminboard-Code nach `/home/pi/lhtpi/terminboard` kopieren (falls SCRIPT_DIR
   abweicht), `chown pi:pi`.
2. Eigenes venv anlegen + `requirements.txt` installieren.
3. **`terminboard.service`**: Flask-App, `User=pi`, `WorkingDirectory`,
   `Environment=TERMINBOARD_HOST=0.0.0.0`, `TERMINBOARD_PORT=8001`,
   `TERMINBOARD_SECRET=<random>`, `ExecStart=.../venv/bin/python .../app.py`,
   `Restart=always`, `WantedBy=multi-user.target`.
4. **`start_terminboard_kiosk.sh`** + **`terminboard-kiosk.service`**:
   - `DISPLAY=:0`, `XAUTHORITY=/home/pi/.Xauthority`.
   - `After=graphical.target terminboard.service`, `WantedBy=graphical.target`.
   - Chromium lädt `http://localhost:8001/board/kiosk`.
   - **Eigenes `--user-data-dir=/home/pi/.config/chromium-terminboard`**
     (NICHT das LHTPi-Verzeichnis teilen!).
   - **Zweiter Monitor**: `--window-position=${SCREEN2_X},0`
     `--window-size=1920,1080` (SCREEN2_X default 1920, oben als Variable).
   - Gleiche Härtungs-Flags wie LHTPi-Kiosk (`--kiosk`, `--noerrdialogs`,
     `--disable-infobars`, `--no-first-run`, `--disable-translate`,
     `--autoplay-policy=no-user-gesture-required`, `--lang=de`, `--disable-gpu`,
     etc.). Mauszeiger-Overlay kann weggelassen werden, da `board.html` selbst
     `cursor:none` setzt.
5. **USB-Auto-Mount** für CSV: eigene udev-Regel + Mount-Helfer
   `/usr/local/bin/terminboard-usb-mount.sh` → `/mnt/terminboard-usb`
   (read-only, `umask=022`, `umount -l` vor Mount). Pakete
   `exfatprogs ntfs-3g dosfstools` (falls noch nicht installiert).
6. **Firewall**: UFW Port `8001/tcp` zusätzlich freigeben.
7. Am Ende Hinweis (kein Reboot erzwungen), dass Dual-Screen-Positionierung
   auf Hardware zu verifizieren ist.

## Tests (`tests/test_terminboard.py`)

`pytest`-Tests für:
1. CSV-Parsing: Semikolon-Trennung, `TT.MM.JJJJ` **und** `JJJJ-MM-TT`,
   fehlende/optionale Spalten, Leer-/Kommentarzeilen, Whitespace.
2. Datum-Parsing (gültig/ungültig, None-Fälle).
3. Source-Logik: auto+USB, auto+kein-USB, manual+web, manual+usb.
4. `board/api/status`: korrekte Trennung kalibrierungen/news, ISO-Datumfelder.

Tests importieren die Module per Pfad (z. B. `sys.path`-Insert oder
`pytest`-conftest), ohne die Flask-App zu starten, wo nicht nötig.

## Akzeptanzkriterien

1. App importiert fehlerfrei, startet auf 8001, Login admin/admin, Dashboard 200.
2. Termin anlegen/bearbeiten/löschen funktioniert (AJAX JSON).
3. `/board/kiosk` öffentlich (200 ohne Login), zeigt beide Bereiche.
4. `/board/api/status` liefert korrektes JSON mit berechneten Feldern.
5. CSV-Import vom USB-Stick parst beide Datumsformate.
6. `pytest` grün.
7. `bash -n install.sh` OK.
8. **Keine** bestehende LHTPi-Datei im Repo-Root verändert.

## Constraints (STRIKT)

- Nur in `terminboard/` arbeiten.
- UI-Sprache Deutsch.
- Keine externen CDN-Ressourcen.
- Test-Dateien NIE löschen.
- Nach jeder abgeschlossenen Teilaufgabe `git commit` (Branch bleibt
  `feature/terminboard`).
- TDD für `usb_source.py` und Source-Logik.
