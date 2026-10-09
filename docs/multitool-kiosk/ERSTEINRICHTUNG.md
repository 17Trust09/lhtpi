# Ersteinrichtung und Netzwerk (LHT-Kiosk-Bundle)

Stand: 09.10.2026 · Entscheidungen von Tim, umgesetzt in `install.sh` und der
Verteiler-App.

## Entscheidungen

1. **Erststart auf dem Bildschirm, mit Maus und Tastatur.** Das Gerät hat kein
   Netzwerk (kein Internet, kein LAN, kein WLAN) — es gibt also keinen
   Handy-/LAN-Weg zur Einrichtung, und es wird keiner gebaut.
2. **Kein Access Point mehr.** Frühere Versionen machten `wlan0` zum AP `LHTPi`
   und löschten dazu vorhandene WLAN-Verbindungen. Das ist ersatzlos entfernt:
   der Installer fasst WLAN nicht mehr an.
3. **Danach ein Ort zum Konfigurieren:** Der Knopf „Anzeigen-Einstellungen
   öffnen" in der **Safety-Cross-Admin-Seite** (`http://<gerät>:8002/admin`)
   führt auf die Anzeigen-Seite (`:8000/display`). Kein zweiter Umbau — die
   Anzeigen-Seite bleibt die einzige Stelle, an der konfiguriert wird.

## Ablauf beim ersten Booten

1. Der Installer (`sudo bash install.sh`) richtet alles ein, erzeugt die
   Hardware-Lizenz für dieses Gerät — setzt aber **kein** Merkmal
   „eingerichtet". Fragen nach Tools/Bildschirmen stellt er nicht mehr (nur noch
   per Argument `--tools=` / `--screens=` für die Image-Vorbereitung).
2. Beim ersten Booten startet **kein Kiosk**. Stattdessen öffnet
   `lhtpi-setup.service` auf dem ersten angeschlossenen Ausgang die
   **Anzeigen-Seite** (`http://localhost:8000/display`) im Vollbild.
   Angeschlossene Ausgänge werden per `xrandr --auto` eingeschaltet.
3. Auf der Seite steht oben der Hinweis **„Erste Einrichtung"** mit der Anzahl
   erkannter Ausgänge. Man wählt: Anzahl Bildschirme, welches Tool auf welchem
   Bildschirm, Anzeigedauer je Tool, Mauszeiger-Ausblendung — dann
   **„Speichern"**.
4. Darunter **„Einrichtung abschließen und Anzeige starten"** → setzt
   `/etc/lhtpi/installed`.
5. Ein Pfad-Wächter (`lhtpi-anzeige.path`) reagiert sofort: die
   Ersteinrichtungs-Seite wird beendet, die Anzeige(n) starten — **kein
   Neustart nötig**.

## Technik

Merk- und Konfigurationsdateien in `/etc/lhtpi` (Verzeichnis `root:pi`, `775`,
damit die App schreiben darf — kein `sudo` in der App nötig):

| Datei | Inhalt |
|---|---|
| `tools` | installierte Tools (eine ID je Zeile) |
| `screens` | Anzahl der Bildschirme (schreibt die Anzeigen-Seite beim Speichern) |
| `screen2` | existiert nur, wenn zwei Bildschirme genutzt werden |
| `installed` | Merkmal: Ersteinrichtung abgeschlossen |
| `license.key` | Hardware-Lizenz (`root`, die App liest nur) |

systemd-Einheiten:

* `lhtpi-setup.service` — `ConditionPathExists=!installed`: zeigt die
  Anzeigen-Seite, solange nicht eingerichtet ist.
* `kiosk-screen1.service` — `ConditionPathExists=installed`.
* `kiosk-screen2.service` — `ConditionPathExists=screen2`.
* `lhtpi-anzeige.path` + `lhtpi-anzeige.service` — reagieren auf `installed`
  und jede Änderung an `screens` und starten/stoppen die Anzeigen passend
  (`/usr/local/bin/lhtpi-anzeige-steuern.sh`).

Damit gilt: Bildschirm-Anzahl ändern wirkt **sofort**, auch später im Betrieb.

## Einrichtung wiederholen (z. B. Gerät umstellen)

```bash
sudo rm -f /etc/lhtpi/installed /etc/lhtpi/screen2
sudo reboot
```

Danach erscheint wieder die Anzeigen-Seite auf dem Bildschirm.

## Ohne Netzwerk

Alle Dienste laufen über `localhost` (Router :8000, Termine :8001, Safety Cross
:8002). Die Anzeige funktioniert also vollständig ohne Netzwerk. Uhrzeit kommt
vom Fake-Hwclock-Dienst (siehe `install.sh`). Der einzige Grund für ein Netz
wäre Fernzugriff — bewusst nicht vorgesehen.

## Grenzen

* Ist kein Bildschirm beim ersten Booten angeschlossen, erscheint nichts.
  Gerät mit Bildschirm neu starten.
* Ohne Merkmal gilt der Entwicklungsmodus der Lizenzprüfung (keine Sperre) —
  das ist gewollt, sonst käme man bei der Einrichtung nicht weiter.
* Der echte Test auf dem Pi steht noch aus (S6): Installer, Erststart, Maus +
  Tastatur, Umschalten der Bildschirm-Anzahl im Betrieb.
