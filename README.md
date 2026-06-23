# LHTPi – HDMI-Kiosk und Präsentations-Player für Raspberry Pi OS Desktop

LHTPi verwandelt einen Raspberry Pi 4/5 in einen autarken Präsentations-Player: Die Flask-Web-App läuft auf Port `8000`, der angeschlossene HDMI-Bildschirm zeigt automatisch Chromium im Kioskmodus, und Medien/Playlists werden über ein Browser-Dashboard verwaltet.

> **Wichtig:** LHTPi unterstützt in dieser Installation ausschließlich **Raspberry Pi OS Desktop (Trixie, mit GUI)**. Es gibt **keinen Lite-Modus** mehr.

---

## Funktionen

- Web-Dashboard mit Login auf Port `8000`
- Standard-Login: `admin` / `admin`
- Upload von Bildern/Videos in `uploads/`
- Playlist-Verwaltung und Endlos-Wiedergabe
- Automatischer HDMI-Kiosk mit Chromium: `http://localhost:8000/present/kiosk`
- LAN bleibt über `eth0` per DHCP erreichbar
- WLAN `wlan0` wird als Access Point über **NetworkManager** betrieben
- Kein `hostapd`, kein `dnsmasq`, kein `iptables-persistent`
- UFW-Firewall erlaubt SSH und Port `8000/tcp`

---

## Zielumgebung

| Komponente | Vorgabe |
|---|---|
| Hardware | Raspberry Pi 4 oder Raspberry Pi 5 |
| Betriebssystem | Raspberry Pi OS Desktop **Trixie** |
| Desktop | X11 / LightDM / Openbox |
| Kiosk | Chromium Browser |
| Netzwerk LAN | `eth0` per DHCP |
| Netzwerk WLAN | `wlan0` als NetworkManager-Access-Point |
| App | Flask, SQLite, Port `8000` |

**Nicht unterstützt:** Raspberry Pi OS Lite/headless-only Installationen. Der Kiosk braucht eine Desktop-/X11-Umgebung.

---

## Installation

### 1. Raspberry Pi vorbereiten

1. Raspberry Pi OS **Desktop (Trixie)** installieren.
2. Standardbenutzer `pi` verwenden.
3. Pi per LAN-Kabel an den Router anschließen.
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

### WLAN: `wlan0` als Access Point

Der Pi erstellt ein eigenes WLAN:

| Feld | Wert |
|---|---|
| SSID | `LHTPi` |
| Passwort | `LHTPi123` |
| AP-IP | `192.168.4.1` |
| Dashboard | `http://192.168.4.1:8000` |

Der AP wird nativ über **NetworkManager** eingerichtet (`ipv4.method shared`). Alte WLAN-Client-Verbindungen werden gelöscht, damit sich der Pi nicht mehr automatisch mit vorhandenen WLANs verbindet.

---

## Nutzung

1. Pi einschalten.
2. HDMI-Bildschirm zeigt nach dem Boot automatisch den Chromium-Kiosk.
3. Dashboard öffnen:
   - über LAN: `http://192.168.178.188:8000` (bei empfohlener Router-Reservierung)
   - über AP: `http://192.168.4.1:8000`
4. Einloggen:
   - Benutzer: `admin`
   - Passwort: `admin`
5. Medien hochladen, Playlist erstellen, Playlist aktivieren.

Der Kiosk lädt automatisch:

```text
http://localhost:8000/present/kiosk
```

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
- NetworkManager-AP: `lhtpi-ap`
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

### AP `LHTPi` ist nicht sichtbar

1. NetworkManager-Verbindung prüfen:
   ```bash
   nmcli con show
   nmcli con show lhtpi-ap
   nmcli dev status
   ```
2. AP manuell starten:
   ```bash
   sudo nmcli con up lhtpi-ap
   ```
3. Sicherstellen, dass keine alten AP-Dienste laufen:
   ```bash
   systemctl status hostapd dnsmasq
   ```
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
