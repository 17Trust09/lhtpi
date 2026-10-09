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
3. **Ein Ort zum Konfigurieren:** die **Anzeigen-Seite** (`:8000/display`) —
   sie erscheint bei jedem Start von selbst. Außerdem führt der Knopf
   „Anzeigen-Einstellungen öffnen" in der **Safety-Cross-Admin-Seite**
   (`http://<gerät>:8002/admin`) dorthin.
4. **Kein Login am Gerät.** Der Kiosk-Bildschirm hat keine Tastatur: Aufrufe
   über `localhost` gelten als angemeldet (`LHTPI_LOKAL_LOGIN=0` schaltet das
   ab). Aus dem LAN bleibt der Login (admin) Pflicht.
5. **Nur die Anzeige.** Die Anzeigen-Seite hat keinen Link zum Dashboard oder zu
   anderen Seiten; das Gerät landet ausschließlich auf der Anzeigen-Seite und
   danach in den Kiosk-Fenstern.

## Ablauf beim ersten Booten

1. Der Installer (`sudo bash install.sh`) richtet alles ein — setzt aber **kein**
   Merkmal „eingerichtet". Fragen nach Tools/Bildschirmen stellt er nicht mehr
   (nur noch per Argument `--tools=` / `--screens=` für die Image-Vorbereitung).
   Die **Lizenz** legt er nur ab, wenn sie mitgeliefert wird (`--license=…` oder
   `lizenz.key` auf der Boot-Partition) — erzeugen kann er sie nicht, der private
   Signaturschlüssel bleibt beim Hersteller. Siehe [LIZENZ.md](LIZENZ.md).
2. Beim Booten startet **kein Kiosk**. Es öffnet `lhtpi-setup.service` auf dem
   ersten angeschlossenen Ausgang die **Anzeigen-Seite**
   (`http://localhost:8000/display`) im Vollbild — ohne Anmeldung.
   Angeschlossene Ausgänge werden per `xrandr --auto` eingeschaltet.
   Ist das Gerät schon eingerichtet, läuft dort ein Countdown (30 s) mit dem
   Knopf **„Anzeige jetzt starten"** — die Anzeige startet also von selbst, auch
   nach einem Stromausfall, und man kann sie jederzeit früher starten.
3. Auf der Seite steht oben der Hinweis **„Erste Einrichtung"** mit der Anzahl
   erkannter Ausgänge. Man wählt: Anzahl Bildschirme, welches Tool auf welchem
   Bildschirm, Anzeigedauer je Tool, Mauszeiger-Ausblendung — dann
   **„Speichern"**.

   Zur Belegung: **ein Tool auf einem Bildschirm = fest** (keine Dauer nötig,
   das Feld verschwindet), **zwei oder mehr = Rotation** und dann gilt die
   Anzeigedauer je Tool. Die Seite rechnet das live mit, ohne Neuladen.
4. Darunter **„Einrichtung abschließen und Anzeige starten"** → setzt
   `/etc/lhtpi/installed`.
5. Ein Pfad-Wächter (`lhtpi-anzeige.path`) reagiert sofort: die
   Ersteinrichtungs-Seite wird beendet, die Anzeige(n) starten — **kein
   Neustart nötig**. Derselbe Weg greift beim Knopf **„Anzeige jetzt starten"**
   auf der Anzeigen-Seite (Einrichtungs-Fenster zu, Kiosk-Fenster auf).

   Fehlt die Lizenz noch, verweigert die Seite den Abschluss mit einem Hinweis
   (sonst würde sich das Gerät mit dem Merkmal sofort selbst sperren). Dann
   `lizenz.key` auf die Boot-Partition legen, Gerät neu starten — der Dienst
   `lhtpi-lizenz-import.service` holt sie automatisch nach
   `/etc/lhtpi/license.key` — und die Einrichtung abschließen.

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

* `lhtpi-setup.service` — startet bei jedem Booten: zeigt die Anzeigen-Seite
  (Einstiegspunkt am Gerät, ohne Login).
* `kiosk-screen1.service` — `ConditionPathExists=installed`; wird **nicht**
  beim Booten gestartet, sondern von der Anzeigen-Steuerung (sonst lägen
  Einrichtungs-Fenster und Kiosk übereinander).
* `kiosk-screen2.service` — `ConditionPathExists=screen2`, gleicher Start.
* `lhtpi-anzeige.path` + `lhtpi-anzeige.service` — reagieren auf `installed`
  und jede Änderung an `screens` und starten/stoppen die Anzeigen passend
  (`/usr/local/bin/lhtpi-anzeige-steuern.sh`).

Damit gilt: Bildschirm-Anzahl ändern wirkt **sofort**, auch später im Betrieb.
Der Installer räumt außerdem alte Kiosk-Einheiten früherer Fassungen weg
(inklusive solcher, die noch das Dashboard zeigten).

## Wieder zur Anzeigen-Seite (per SSH)

Die Seite erscheint bei jedem Neustart von selbst. Ohne Neustart des Geräts:

```bash
sudo systemctl stop kiosk-screen1.service kiosk-screen2.service
sudo systemctl start lhtpi-setup.service
```

## Einrichtung von vorn (z. B. Gerät umstellen)

```bash
sudo rm -f /etc/lhtpi/installed /etc/lhtpi/screen2
sudo systemctl restart lhtpi-setup.service
```

Danach erscheint wieder die Anzeigen-Seite mit dem Hinweis „Erste Einrichtung"
(oder einmal neu starten).

## Ohne Netzwerk

Alle Dienste laufen über `localhost` (Router :8000, Termine :8001, Safety Cross
:8002). Die Anzeige funktioniert also vollständig ohne Netzwerk. Uhrzeit kommt
vom Fake-Hwclock-Dienst (siehe `install.sh`). Der einzige Grund für ein Netz
wäre Fernzugriff — bewusst nicht vorgesehen.

## Grenzen

* Ist kein Bildschirm beim ersten Booten angeschlossen, erscheint nichts.
  Gerät mit Bildschirm neu starten.
* Ohne Merkmal gilt der Entwicklungsmodus der Lizenzprüfung (keine Sperre) —
  das ist gewollt, sonst käme man bei der Einrichtung nicht weiter. Mit Merkmal
  **und** ohne gültige Lizenz ist alles gesperrt (Sperrseite mit Geräte-ID).
* Lizenzen sind **gerätegebunden und signiert**: eine Kopie der SD-Karte auf
  einem anderen Pi ist ungültig. Erzeugt wird sie beim Hersteller, siehe
  [LIZENZ.md](LIZENZ.md).
* Von den Kiosk-Fenstern kommt man nur per SSH oder Neustart zurück auf die
  Anzeigen-Seite — gewollt, damit am Gerät niemand aus der Anzeige heraus
  navigieren kann.
