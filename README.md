# 🎬 LHTPi – Autarker Präsentations- und Medien-Player für Raspberry Pi

LHTPi verwandelt einen **Raspberry Pi 4/5** in einen eigenständigen Präsentations- und Medien-Player.
Per Web-Dashboard können Bilder und Videos hochgeladen, zu Playlists zusammengestellt und auf einem
angeschlossenen Bildschirm im **Chromium-Kioskmodus** automatisch abgespielt werden.

> 🚀 **Altes Projekt SlidePi wurde komplett durch LHTPi ersetzt.**

---

## ✨ Funktionen

### 🖥️ Web-Dashboard
- **Flask-Web-App** auf Port 8000
- **Login-geschützt** – Standard: `admin` / `admin`
- Erreichbar per WLAN über den integrierten Access Point
- Live-Statusanzeige mit aktuellem Medium und Wiedergabestatus

### 🖼️ Medienverwaltung
- **Upload** von: PNG, JPG, JPEG, GIF, MP4
- **Vorschau** und **Suche** nach Dateinamen
- **Sortierung** nach Datum, Name und Dateityp
- **Löschen** mit Bestätigung

### 📋 Playlist-Verwaltung
- Playlists **erstellen, umbenennen und löschen**
- Medien **hinzufügen und entfernen**
- **Drag & Drop** für die Reihenfolge
- **Anzeigedauer** pro Medium einstellbar (in Sekunden)
- **Aktive Playlist** auswählen für die Präsentation
- Automatische **Endlos-Wiedergabe**
- Bei Videos: wird **vollständig abgespielt**, Anzeigedauer wird ignoriert

### 🖥️ Kiosk-Präsentation
- Automatischer **Chromium-Kioskmodus** im Vollbild
- Bilder und Videos in **bildschirmfüllender Darstellung**
- Öffentliche Kiosk-API (`/present/api/status`) für Live-Daten
- Startet **automatisch nach dem Einschalten**

### 📡 Access Point
- Eigener WLAN-Hotspot: **SSID: `LHTPi`**, Passwort: `LHTPi123`
- DHCP/DNS für verbundene Geräte
- **Komplett offline-fähig** – kein Internet nötig
- Dashboard erreichbar unter: `http://192.168.4.1:8000`

---

## 🚀 Schnellstart

### 1. Projekt auf den Pi kopieren
```bash
git clone https://github.com/17Trust09/lhtpi /home/pi/lhtpi
```

### 2. Installation starten
```bash
cd /home/pi/lhtpi
sudo bash install.sh
```

### 3. Neustarten
```bash
sudo reboot
```

### 4. Nutzen
Nach dem Neustart:
1. WLAN **`LHTPi`** mit Passwort **`LHTPi123`** verbinden
2. Browser öffnen: **http://192.168.4.1:8000**
3. Login: **`admin`** / **`admin`**
4. Medien hochladen → Playlist erstellen → Playlist aktivieren → Kiosk startet automatisch

---

## 🛠️ Technische Details

### Zielumgebung
| Komponente | Vorgabe |
|---|---|
| Hardware | Raspberry Pi 4 oder Raspberry Pi 5 |
| Betriebssystem | Raspberry Pi OS Bookworm |
| Python | 3.x |
| Framework | Flask |
| Datenbank | SQLite |
| Kiosk | Xorg + Openbox + Chromium |
| Access Point | hostapd + dnsmasq |
| Firewall | UFW |

### systemd-Services
| Service | Beschreibung |
|---|---|
| `lhtpi.service` | Flask-Web-App (Port 8000) |
| `lhtpi-kiosk.service` | Chromium-Kioskmodus (startet nach App) |

### Projektstruktur
```
/home/pi/lhtpi/
├── app.py              # Flask-App (Startpunkt)
├── models.py           # Datenbankmodelle (SQLite)
├── routes.py           # Webrouten & Logik
├── config.py           # Konfiguration
├── requirements.txt    # Python-Abhängigkeiten
├── install.sh          # 🎯 Installationsskript
├── README.md           # Diese Datei
├── templates/          # HTML-Templates (Jinja2)
│   ├── login.html      # Login-Seite
│   ├── dashboard.html  # Dashboard-Startseite
│   ├── media.html      # Medienverwaltung
│   ├── playlists.html  # Playlist-Verwaltung
│   └── kiosk.html      # Kiosk-Präsentationsseite
├── static/
│   └── style.css       # Dark Dashboard-Design
└── uploads/            # Hochgeladene Medien
```

### Autostart-Ablauf (nach Einschalten)
1. **Raspberry Pi OS** bootet
2. **LightDM** startet mit Auto-Login für User `pi`
3. **Openbox** (X11-Fenstermanager) startet
4. **`lhtpi.service`** startet die Flask-App
5. **`lhtpi-kiosk.service`** wartet auf die App, startet dann Chromium
6. **Chromium** öffnet `http://localhost:8000/present/kiosk` im Vollbild

---

## 🔧 Installationsdetails

Das Skript `install.sh` führt folgende Schritte automatisch aus:

- **Pakete installieren:** Python, hostapd, dnsmasq, Xorg, Openbox, Chromium, UFW, curl
- **Python-Venv** erstellen und Abhängigkeiten installieren
- **Access Point** konfigurieren (SSID: LHTPi, PW: LHTPi123)
- **systemd-Services** anlegen und aktivieren (`lhtpi.service`, `lhtpi-kiosk.service`)
- **Kiosk-Startskript** erstellen (`/home/pi/start_lhtpi_kiosk.sh`)
- **X11-Autostart** mit LightDM + Auto-Login
- **HDMI-Fallback** aktivieren (1080p, Force Hotplug)
- **Bildschirm-Energiesparmodus** deaktivieren
- **Firewall** konfigurieren (SSH, Port 8000, DHCP/DNS)
- **Backup** bestehender Konfigurationsdateien

---

## 🐛 Fehlerbehebung

| Problem | Lösung |
|---|---|
| Kein Bild auf dem Monitor | HDMI-Kabel prüfen, Pi startet auch ohne erkannten Monitor (HDMI-Fallback) |
| Kiosk startet nicht nach Boot | `ssh pi@192.168.4.1`, dann `systemctl status lhtpi-kiosk.service` und `cat /home/pi/lhtpi-kiosk.log` |
| Dashboard nicht erreichbar | Prüfen ob WLAN mit LHTPi verbunden ist, `ping 192.168.4.1` |
| Kein WLAN sichtbar | Evtl. muss wlan0 freigegeben werden: `sudo nmcli dev set wlan0 managed no` |
| SSH nicht erreichbar | Tastatur & Monitor am Pi: `sudo systemctl enable ssh && sudo systemctl start ssh` |

---

## 📝 Lizenz

MIT – siehe LICENSE-Datei.
