# Projektstand — LHTPi + Terminboard

> Stand: **19.11.2026** · Branch: `feature/multitool-kiosk` · Status: ✅ läuft (Modell 3)

Kurzer Einstieg für alle, die das Projekt fortsetzen wollen. Details in den
jeweiligen `README.md` (Repo-Root und `terminboard/`).

---

## Kurzfassung

Zwei Flask-Apps laufen parallel auf einem **Raspberry Pi 4** und werden über
**zwei HDMI-Ausgänge** als Chromium-Kiosks angezeigt:

| App | Port | HDMI | Anzeige |
|---|---|---|---|
| LHTPi | `8000` | HDMI-A-1 | Präsentations-Player (Folien) |
| Terminboard | `8001` | HDMI-A-2 | Kalibrierungen / News & Audits |

Beide lesen bei Bedarf von **einem gemeinsamen USB-Stick**.

---

## Einheitliche Datenstruktur (Terminboard, Modell 3)

Die Excel-Datei `termine.xlsx` ist die eindeutige Datenquelle. Sechs Blätter:

| Blatt | Inhalt | Nummern |
|---|---|---|
| `Termine` | Kalibrierung / Wartung / Ausfall | `T-001 … T-500` |
| `News & Audits` | Audit / Info | `N-001 … N-500` |
| `Betriebsmittel` | Stammdaten (ID, Typ, Bezeichnung, Zusammenführen mit) | `BM-001 …` |
| `Zeiten` | Uhrzeitblöcke, verweisen auf `T-Nummern` | – |
| `Archiv Termine` / `Archiv News & Audits` | abgeschlossene Vorgänge | – |

Arbeitsablauf: **Betriebsmittel zuerst anlegen** (unten im Stammdatenblatt,
`ID` leer lassen – das Gerät vergibt sie beim Import und schreibt sie zurück),
dann in `Termine` per Dropdown wählen. Umbenennen/Typwechsel bei gleicher `ID`
wirken rückwirkend auf Historie und Berichte; Zusammenführung über
`Zusammenführen mit` = Ziel-`BM-NNN`. Status nur `offen`/`abgeschlossen`
(kein `storniert`); `abgeschlossen` wandert automatisch ins Archiv.

Interne DB-Felder (`models.py`): `typ`, `titel`, `referenz`, `start`, `ende`,
`text`. Die Web-Oberfläche dient der Anzeige und dem Abruf der Berichte – die
Pflege erfolgt in Excel.

---

## USB-Stick (eine Quelle für beide Apps)

```text
<Stick-Root>/          exFAT, Label "LHTPi", Mount-Point /mnt/lhtpi-usb
├── slides/
│   ├── bild1.jpg
│   └── settings.txt   (optional: default=10 = Sekunden je Bild)
└── termine.xlsx       (Excel-Vorlage mit Dropdown + Anleitung)
```

- USB hat im `auto`-Modus Vorrang vor der internen DB/Playlist.
- Excel-Vorlage neu erzeugen (lokal):
  ```bash
  cd terminboard && ./venv/bin/python tools_vorlage_modell3_bauen.py
  ```
- Modell-2-Altbestand migrieren:
  ```bash
  cd terminboard
  ./venv/bin/python tools_modell2_zu_modell3.py --quelle alt.xlsx --ziel neu.xlsx
  ./venv/bin/python tools_modell2_zu_modell3.py --quelle alt.xlsx --ersetzen   # sichert .bak
  ```

---

## Wichtige Fixes dieser Session

- **`unclutter` im Hintergrund (`&`)** — lief vorher im Vordergrund und
  blockierte den Chromium-Start → LHTPi-Monitor blieb schwarz.
- **Feste HDMI-Zuordnung** via `xrandr` + Openbox-Regel (Terminboard auf
  Monitor 2), statt fragilem `--window-position`.
- **Excel-Vorlage statt kryptischer CSV** (5 Spalten, Dropdown, Anleitung).
- **CSV-Fallback**, falls die `.xlsx` kaputt/nicht lesbar ist.
- **Spalten umbenannt**: „Titel" → „Info", „Prüfstand/Referenz" → „Prüfstand"
  (jetzt Pflicht). Kiosk-Spaltenüberschrift „Kalibrierung" → „Info".

---

## Pi (Produktivsystem)

| Feld | Wert |
|---|---|
| Modell | Raspberry Pi 4 Model B Rev 1.5 |
| IP (LAN) | `192.168.178.47` |
| Projektpfad | `/home/pi/lhtpi` |
| Branch | `feature/terminboard` |
| DB | `/home/pi/lhtpi/terminboard/terminboard.db` |
| Uploads | `/home/pi/lhtpi/uploads/` |

Services (systemd):

| Service | Zweck |
|---|---|
| `lhtpi.service` | LHTPi-Flask (Port 8000) |
| `lhtpi-kiosk.service` | LHTPi-Chromium-Kiosk |
| `terminboard.service` | Terminboard-Flask (Port 8001) |
| `terminboard-kiosk.service` | Terminboard-Chromium-Kiosk |

USB-Auto-Mount: udev-Regel → `/usr/local/bin/lhtpi-usb-mount.sh` →
`/mnt/lhtpi-usb`.

### Update auf den Pi

Ein einziger Befehl genügt – der post-merge-Haken erledigt den Rest:

```bash
cd /home/pi/lhtpi
git pull
```

`scripts/nach-pull.sh` (via post-merge-Haken) führt dabei automatisch aus:

1. **Abhängigkeiten:** Ändern sich `terminboard/requirements.txt` (oder andere
   relevante Anforderungen), werden sie idempotent in
   `terminboard/venv` installiert. Schlägt die Installation fehl, bricht der
   Nachzug ab – **kein Neustart** mit halb installierten Abhängigkeiten.
2. **DB-Sicherung:** Vor dem Terminboard-Neustart sichert ein Root-Helfer
   (`/usr/local/sbin/lhtpi-terminboard-backup`, via `sudo -n`) die Live-DB
   (`/var/lib/lhtpi/terminboard/terminboard.db`) mit der sqlite3-Backup-API –
   das ergibt auch im WAL-Modus einen konsistenten Snapshot (kein unsicheres
   `cp` mehr). Sicherungen landen in `<db>/backups/`, alte werden auf die
   letzten 10 begrenzt. Schlägt die Sicherung fehl, wird **nicht** neu
   gestartet.
3. **Neustart + Healthcheck:** `terminboard.service` wird neu gestartet, danach
   werden `http://127.0.0.1:8001/login` und `/board/api/status` geprüft (bis zu
   ca. 30 s mit Wiederholungen). Schlägt der Neustart oder der Healthcheck
   fehl, bricht der Nachzug mit sichtbarem Fehler ab.
4. **Migration:** Die App führt beim Start ihre Schema-Migration automatisch aus
   und bricht bei Fehlern ab (die DB-Sicherung aus Schritt 2 erlaubt die
   Wiederherstellung).

Kein manuelles `sudo systemctl restart` mehr nötig; die bestehenden
`starte_dienst`-Freigaben werden unverändert genutzt.

> **Achtung bei Fehlermeldungen:** Der post-merge-Haken läuft **nach** dem
> Merge – ist der Nachzug fehlgeschlagen, ist `git merge`/`git pull` zu diesem
> Zeitpunkt bereits abgeschlossen und der neue Code liegt im Arbeitsverzeichnis.
> Der Dienst wurde dann aber **nicht** neu gestartet (bzw. die Sicherung fehlt).
> Die rote Fehlerausgabe (`LHTPi: …`, `FEHLER: …`) also nicht überlesen – sonst
> läuft die Anzeige mit altem Code weiter, und niemand merkt es.

### Kiosk-Diagnose

```bash
ps aux | grep -i chromium | grep -v grep        # beide Chromium-Instanzen?
cat /home/pi/lhtpi-kiosk.log
cat /home/pi/terminboard-kiosk.log
DISPLAY=:0 xrandr --current                       # Monitor-Zuordnung
```

---

## Tests

```bash
cd terminboard
./venv/bin/python -m pytest tests/ -q
```

---

## Backup

Vollständiges SD-Image (funktionierender Stand **vor** dem Umbau):

```text
/home/icekey/lhtpi-backup-20260826.img   (59,48 GiB)
```

Zurückspielen — ⚠️ `if`/`of` nicht vertauschen:

```bash
sudo dd if=/home/icekey/lhtpi-backup-20260826.img of=/dev/mmcblk0 bs=4M status=progress conv=fsync
```

---

## Offene Punkte / nächste Schritte

- [ ] Openbox-Regel „Terminboard auf Monitor 2" final auf echter Hardware prüfen
- [ ] Standard-Login `admin`/`admin` ändern (Produktivbetrieb)
