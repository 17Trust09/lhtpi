# LHTPi - Lokaler Präsentations- und Medienplayer für Raspberry Pi

LHTPi ist eine lokale Web-Anwendung für Raspberry Pi 4/5 mit Raspberry Pi OS Bookworm.
Der Pi läuft als autarker Präsentations- und Medienplayer im Chromium-Kioskmodus.

## Schnellstart

```bash
sudo bash install.sh
sudo reboot
```

Nach dem Neustart:
- WLAN "LHTPi" mit Passwort "LHTPi123" verbinden
- http://192.168.4.1:8000 im Browser öffnen
- Login: admin / admin

## Projektstruktur

```
/home/pi/lhtpi/
├── app.py              # Flask-App
├── models.py           # Datenbankmodelle
├── config.py           # Konfiguration
├── requirements.txt    # Python-Abhängigkeiten
├── install.sh          # Installationsskript
├── templates/          # Jinja2-Templates
├── static/             # CSS, JS
└── uploads/            # Hochgeladene Medien
```
