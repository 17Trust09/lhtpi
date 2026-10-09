# LHTPi – HDMI-Kiosk und Präsentations-Player für Raspberry Pi OS Desktop

LHTPi verwandelt einen Raspberry Pi 4/5 in einen autarken Präsentations-Player: Die Flask-Web-App läuft auf Port `8000`, der angeschlossene HDMI-Bildschirm zeigt automatisch Chromium im Kioskmodus, und Medien/Playlists werden über ein Browser-Dashboard verwaltet.

> **Wichtig:** LHTPi unterstützt in dieser Installation ausschließlich **Raspberry Pi OS Desktop (Trixie, mit GUI)**. Es gibt **keinen Lite-Modus** mehr.

---

## Funktionen

- Web-Dashboard mit Login auf Port `8000`
- Standard-Login: `admin` / `admin`
- Upload von Bildern/Videos in `uploads/`
- Playlist-Verwaltung und Endlos-Wiedergabe
- **USB-Stick als Quelle**: Ordner `slides/` im Stick-Root wird automatisch abgespielt (Vorrang vor der Web-Playlist)
- Automatischer HDMI-Kiosk mit Chromium: `http://localhost:8000/present/kiosk`
- Hardware-Lizenz **signiert** (RSA-2048): Kopie auf ein anderes Gerät ist gesperrt,
  Lizenzen kann nur der Hersteller erzeugen ([Details](docs/multitool-kiosk/LIZENZ.md))
- **Kein Access Point**: `wlan0` wird nicht angefasst, keine WLAN-Verbindungen gelöscht
- `eth0` optional per DHCP (die Anzeige braucht kein Netzwerk)
- Kein `hostapd`, kein `dnsmasq`, kein `iptables-persistent`
- UFW-Firewall erlaubt SSH und Port `8000/tcp`

---

## Zielumgebung

| Komponente | Vorgabe |
|---|---|
| Hardware | Raspberry Pi 4 oder Raspberry Pi 5 |
| Betriebssystem | Raspberry Pi OS Desktop **Trixie, 64 Bit (arm64)** — 32 Bit läuft auch |
| Desktop | X11 / LightDM / Openbox |
| Kiosk | Chromium Browser |
| Netzwerk | **kein Netzwerk nötig** (alles über `localhost`); `eth0` optional per DHCP |
| WLAN | wird **nicht** angefasst (kein Access Point mehr) |
| App | Flask, SQLite, Port `8000` |

**Empfehlung:** Raspberry Pi OS Desktop **Trixie 64 Bit**. Der Pi 4 kann 64 Bit,
und alle Dienste (Flask, SQLite, Chromium) laufen dort nativ; bei 8-GB-Modellen
werden so auch alle 8 GB genutzt. 32 Bit funktioniert genauso (reine
Python-Dienste, keine Binär-Abhängigkeiten) — sinnvoll nur für sehr alte Karten
oder wenn ein bestehendes Image weiterverwendet wird.

**Nicht unterstützt:** Raspberry Pi OS Lite/headless-only Installationen. Der Kiosk braucht eine Desktop-/X11-Umgebung. Ebenso nicht nötig: eine eigene
Image-Anpassung — nach dem ersten Start fragt das Gerät selbst (siehe
[ERSTEINRICHTUNG.md](docs/multitool-kiosk/ERSTEINRICHTUNG.md)).

---

## Installation

### 1. Raspberry Pi vorbereiten

1. Raspberry Pi OS **Desktop (Trixie)** installieren.
2. Standardbenutzer `pi` verwenden.
3. Netzwerk ist **optional** — die Anzeige läuft vollständig über `localhost`.
4. Optional, aber empfohlen: Im Router eine feste DHCP-Reservierung setzen, z. B.:
   - LAN-IP: `192.168.178.188`
   - Gerät: Raspberry Pi / LHTPi

So bleibt der Pi im Heimnetz zuverlässig erreichbar.

### 2. Projekt nach `/home/pi/lhtpi` kopieren

```bash
git clone https://github.com/17Trust09/lhtpi /home/pi/lhtpi
cd /home/pi/lhtpi
```

Wenn das Projekt bereits anders auf den Pi kopiert wurde, trotzdem aus dem Projektordner starten.

### 3. Installer ausführen

```bash
sudo bash install.sh
```

Das Skript installiert Pakete, richtet Python-Venv, NetworkManager-AP, systemd-Services, LightDM-Autologin, HDMI-Fallback und UFW ein. Am Ende wartet es 5 Sekunden und startet den Pi neu.

---

## Netzwerk nach der Installation

### LAN: `eth0` bleibt DHCP

`eth0` wird vom Installer nicht statisch überschrieben. Der Pi bekommt seine IP weiter vom Router.

Empfehlung: Im Router eine DHCP-Reservierung auf diese Adresse setzen:

```text
192.168.178.188
```

Dashboard dann im LAN:

```text
http://192.168.178.188:8000
```

Falls eine andere LAN-IP vergeben wurde, im Router nachsehen oder auf dem Pi ausführen:

```bash
hostname -I
```

### Netzwerk

Das Gerät braucht **kein** Netzwerk: Router (Port 8000), Termine (8001) und
Safety Cross (8002) laufen alle über `localhost`. Steckt ein LAN-Kabel, ist das
Dashboard zusätzlich über die IP des Pi erreichbar (`hostname -I`).

**Es gibt keinen Access Point mehr.** Frühere Versionen machten `wlan0` zum AP
`LHTPi` und löschten vorhandene WLAN-Verbindungen — das ist entfernt. Der
Installer fasst WLAN nicht mehr an.

---

## Nutzung

1. Pi einschalten.
2. HDMI-Bildschirm zeigt nach dem Boot automatisch den Chromium-Kiosk.
3. Beim **ersten Start** erscheint die Anzeigen-Seite auf dem Bildschirm
   (Maus + Tastatur): Tools und Bildschirme wählen, dann „Einrichtung
   abschließen" — siehe [ERSTEINRICHTUNG.md](docs/multitool-kiosk/ERSTEINRICHTUNG.md).
4. Danach Dashboard öffnen (auf dem Gerät oder über die LAN-IP):
   `http://localhost:8000` bzw. die IP aus `hostname -I`.
4. Einloggen:
   - Benutzer: `admin`
   - Passwort: `admin`
5. Medien hochladen, Playlist erstellen, Playlist aktivieren.

Der Kiosk lädt automatisch:

```text
http://localhost:8000/present/kiosk
```

---

## USB-Stick als Quelle (Auto-Play)

Der Pi erkennt einen eingesteckten USB-Stick automatisch und spielt ihn ab, **ohne dass jemand das Dashboard öffnen muss**. Das ist der schnellste Weg für Personen, die nur die Bilder austauschen wollen.

### Ordner-Struktur auf dem Stick

Im Stick-Root einen Ordner `slides/` anlegen und dort die Bilder/Videos ablegen:

```text
/stick/
└── slides/
    ├── bild1.jpg
    ├── bild2.png
    ├── video.mp4
    └── settings.txt   (optional)
```

* Dateien werden **alphabetisch** (nach Dateiname) abgespielt.
* Erlaubte Formate: `png`, `jpg`, `jpeg`, `gif`, `mp4`.
* Videos laufen standardmäßig in voller Länge.
* Unterordner werden ignoriert (nur Dateien direkt in `slides/`).

### Anzeigedauer konfigurieren (optional)

Mit einer `settings.txt` im `slides/`-Ordner lässt sich die Dauer steuern:

```text
# Standarddauer für alle Bilder (Sekunden). Default: 10
default=10

# Dauer für einzelne Dateien überschreiben
bild1.jpg=5
bild2.png=20
video.mp4=0     # 0 = volle Videolänge
```

Wird keine Dauer angegeben, gilt `default` (bzw. 10 Sekunden).

### Umschalt-Verhalten

| Modus | Verhalten |
|---|---|
| **Auto** (Standard) | USB-Stick hat Vorrang. Stick rein → spielt vom Stick. Stick raus → interne Playlist. Stick wieder rein → wieder vom Stick. |
| **Manuell** | Im Dashboard lässt sich eine feste Quelle erzwingen (Web oder USB). |

Die Umschaltung erfolgt im Dashboard unter **„Wiedergabe-Quelle"**.

---

## Was `install.sh` einrichtet

- Pakete:
  - `python3`, `python3-pip`, `python3-venv`
  - `ufw`, `curl`, `git`
  - `xorg`, `openbox`
  - `chromium-browser`, `chromium-browser-l10n`
- `/home/pi/lhtpi/uploads`
- Python-Venv unter `/home/pi/lhtpi/venv`
- Flask-App-Service: `lhtpi.service`
- Kiosk-Service: `lhtpi-kiosk.service`
- Kiosk-Skript: `/home/pi/start_lhtpi_kiosk.sh`
- WLAN-Powersave aus: `/etc/NetworkManager/conf.d/99-lhtpi-wifi-powersave.conf`
- LightDM-Autologin für Benutzer `pi`
- Openbox-Autostart mit deaktiviertem Bildschirmschoner/DPMS
- Getty-Autologin auf `tty1`
- HDMI-Fallback in `/boot/firmware/config.txt`:
  - `hdmi_force_hotplug=1`
  - `hdmi_group=2`
  - `hdmi_mode=82`
- UFW-Regeln:
  - SSH erlaubt
  - `8000/tcp` erlaubt

---

## systemd-Kommandos

Status prüfen:

```bash
systemctl status lhtpi.service
systemctl status lhtpi-kiosk.service
```

Logs der Web-App:

```bash
journalctl -u lhtpi.service -f
```

Logs des Kiosk-Starts:

```bash
journalctl -u lhtpi-kiosk.service -f
cat /home/pi/lhtpi-kiosk.log
```

Services neu starten:

```bash
sudo systemctl restart lhtpi.service
sudo systemctl restart lhtpi-kiosk.service
```

---

## Troubleshooting

### Dashboard ist nicht erreichbar

1. Prüfen, ob die App läuft:
   ```bash
   systemctl status lhtpi.service
   journalctl -u lhtpi.service -n 100 --no-pager
   ```
2. Prüfen, ob Port 8000 lauscht:
   ```bash
   curl -I http://localhost:8000/login
   ```
3. UFW prüfen:
   ```bash
   sudo ufw status
   ```
4. LAN-IP prüfen:
   ```bash
   hostname -I
   ```

### Beim ersten Start erscheint nichts auf dem Bildschirm

1. Ist ein Bildschirm beim Booten angeschlossen und eingeschaltet?
   ```bash
   xrandr --current | grep connected
   ```
2. Läuft die Ersteinrichtung?
   ```bash
   systemctl status lhtpi-setup.service
   tail -20 /home/pi/setup.log
   ```
3. Einrichtung wiederholen: Merkmale löschen und das Gerät neu starten
   ```bash
   sudo rm -f /etc/lhtpi/installed /etc/lhtpi/screen2
   ```
   (danach neu booten)
   Beide Dienste sollen gestoppt/maskiert sein.
4. WLAN-Powersave prüfen:
   ```bash
   cat /etc/NetworkManager/conf.d/99-lhtpi-wifi-powersave.conf
   ```

### Kiosk startet nicht

1. Prüfen, ob Desktop/LightDM läuft:
   ```bash
   systemctl status lightdm
   echo $DISPLAY
   ```
2. Kiosk-Service prüfen:
   ```bash
   systemctl status lhtpi-kiosk.service
   journalctl -u lhtpi-kiosk.service -n 100 --no-pager
   cat /home/pi/lhtpi-kiosk.log
   ```
3. App lokal testen:
   ```bash
   curl -I http://localhost:8000/login
   curl -I http://localhost:8000/present/kiosk
   ```
4. Kiosk neu starten:
   ```bash
   sudo systemctl restart lhtpi-kiosk.service
   ```

### Kein Bild über HDMI

- HDMI-Kabel und Eingang am Monitor prüfen.
- Pi einmal mit angeschlossenem Monitor neu starten.
- HDMI-Fallback prüfen:
  ```bash
  grep -E 'hdmi_force_hotplug|hdmi_group|hdmi_mode' /boot/firmware/config.txt
  ```

### Upload schlägt fehl

`uploads/` muss existieren und dem Benutzer `pi` gehören:

```bash
sudo mkdir -p /home/pi/lhtpi/uploads
sudo chown -R pi:pi /home/pi/lhtpi/uploads
```

---

## Projektstruktur

```text
/home/pi/lhtpi/
├── app.py
├── models.py
├── routes.py
├── config.py
├── requirements.txt
├── install.sh
├── README.md
├── templates/
├── static/
└── uploads/
```

---

## Sicherheitshinweis

Der Standard-Login `admin` / `admin` ist nur für die Erstinstallation gedacht. Nach dem ersten Login sollte das Passwort geändert werden, wenn der Pi in einem nicht vertrauenswürdigen Netzwerk erreichbar ist.

---

## Lizenz

MIT – siehe LICENSE-Datei.
