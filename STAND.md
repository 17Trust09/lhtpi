# Projektstand — LHTPi + Terminboard

> Stand: **26.08.2026** · Branch: `feature/terminboard` · Status: ✅ läuft

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

## Einheitliche Datenstruktur (Terminboard)

Excel-Spalten: `Art | Prüfstand | Von | Bis | Info`

| Spalte | Bedeutung | Pflicht |
|---|---|---|
| Art | Kalibrierung / Audit / Wartung / Info | ✓ Dropdown |
| Prüfstand | z. B. `P3` | ✓ |
| Von | Startdatum | ✓ |
| Bis | Enddatum | – |
| Info | Beschreibung | ✓ |

Interne DB-Felder (`models.py`): `typ`, `titel` (= Info), `referenz`
(= Prüfstand, jetzt Pflicht), `start`, `ende`, `text` (Notiz, nur Web-Formular).

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
  cd terminboard && ./venv/bin/python generate_termine_template.py
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

```bash
cd /home/pi/lhtpi
git pull
sudo systemctl restart lhtpi
sudo systemctl restart terminboard
```

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
./venv/bin/python -m pytest tests/ -q        # 34 passed
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
