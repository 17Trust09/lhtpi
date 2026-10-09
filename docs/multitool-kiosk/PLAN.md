# Multitool-Kiosk — Slideshow + Terminboard + Safety Cross auf **einem** Gerät

> Planungsstand: **09.10.2026** · Branch `feature/multitool-kiosk` (Basis `feature/terminboard` @ `48afcce`)
> Auftrag: Tim · Umsetzung: Slices (Codex/Claude) · Verifikation: Yuuki
>
> **Entschieden (09.10.2026):** **Bundle** — `lhtpi` ist der Verteiler (Installer + Anzeige-Router +
> Lizenz). Safety-Cross-Code liegt als Kopie in **`tools/safety-cross/`**; das eigene Repo
> `17Trust09/safety-cross` wird **nicht** weiter verzweigt. Rotationstechnik: iframe-Rotation.

---

## 1. Anforderungen

1. **Ein Gerät** kann Slideshow + Terminboard + Safety Cross zeigen (heute: 3 getrennte Installationen).
2. **Mehrere Tools können sich einen Ausgang teilen** → sie **wechseln sich ab** (Rotation).
   Beispiel: Projekt 1 für 5 min, Projekt 2 für 2 min (Dauer je Tool frei einstellbar).
3. **Anzeigedauer einstellbar** — pro Tool, in Sekunden („wie lange wird was angezeigt").
4. **Welches Tool einen festen Bildschirm bekommt und welche sich einen teilen** → einstellbar
   (Tool mit einem Eintrag = fest; mehrere Einträge = Rotation).
5. **Anzahl Bildschirme einstellbar (1 oder 2)** — Abteilungen mit unterschiedlichem Bedarf.
6. **Mauszeiger** überall gleich: bei Inaktivität ausgeblendet, **sobald die Maus bewegt wird wieder da**.
   Gilt auch für Safety Cross (dort aktuell noch sichtbar).
7. **Installation mit Auswahl**: nur eins, zwei oder alle drei Tools aktivieren.
8. **Hardware-Lizenz für alles** — Kopie auf ein anderes Gerät wird gesperrt.

---

## 2. Ist-Zustand

| Tool | Repo | Port | Kiosk-URL | Cursor heute |
|---|---|---|---|---|
| Slideshow (Folien/Playlist/USB) | `17Trust09/lhtpi` (`.`) | 8000 | `/present/kiosk` | dauerhaft aus (CSS + transparentes Cursor-Thema + Chromium-Extension + `unclutter -idle 0`) |
| Terminboard | `17Trust09/lhtpi` (`terminboard/`) | 8001 | `/board/kiosk` | dauerhaft aus (`cursor:none!important`) |
| Safety Cross | `17Trust09/safety-cross` | 8002 | `/` | JS: 30 s Idle → `hide-cursor`-Klasse; greift am Gerät nicht zuverlässig |

`lhtpi/install.sh` installiert LHTPi + Terminboard als **Add-on**, ordnet per `xrandr` HDMI-1/HDMI-2 zu und
startet **einen Chromium je Tool** (`lhtpi-kiosk.service`, `terminboard-kiosk.service`).
Safety Cross ist heute eine **eigene Installation** (`/opt/safety-cross`, eigenes Repo, eigene Lizenz).
Im Bundle liegt der Code jetzt unter `tools/safety-cross/` — ab hier ist **diese Kopie die Quelle**.

---

## 3. Architektur (Vorschlag)

```
Raspberry Pi 4/5  (ein Gerät, 1 oder 2 HDMI-Ausgänge)
│
├── Flask "slideshow"      :8000   ← Verteiler-App (Dashboard, Anzeige-Router, DB, Lizenz)
├── Flask "terminboard"    :8001   ┐
├── Flask "safetycross"    :8002   ┘ nur installiert, wenn aktiviert
│
├── Chromium #1  →  http://localhost:8000/screen/1     (immer)
└── Chromium #2  →  http://localhost:8000/screen/2     (nur bei 2 Bildschirmen)
        └── "Anzeige-Router": zeigt je Bildschirm die konfigurierten Tools,
            Tool mit 1 Eintrag = fest, mehrere = Rotation mit Anzeigedauer
```

**Kern: der Anzeige-Router.** Eine Chromium-Instanz je Bildschirm lädt eine Router-Seite.
Der Router bettet die Tools als `<iframe>` ein (gleiche Maschine, `localhost:PORT`) und blendet sie
nach Zeitplan um. Damit braucht die Rotation **keinen Fenstermanager-Eingriff** (kein xrandr-Umschalten,
kein Openbox-Regelwerk) und läuft **offline**.

* 1 Tool auf dem Bildschirm → iframe fest, kein Timer.
* N Tools → Sequenz: aktiv für `dwell_seconds`, dann Crossfade zum nächsten.
* Alle iframes werden vorab geladen und nur ein-/ausgeblendet → **kein Neuladen, kein Flackern**;
  jede Tool-Seite pollt ihre Daten selbst weiter.
* Jeder iframe wird zusätzlich nach `iframe_reload_minutes` (Default 30) frisch geladen.
* **Tool offline** (Service down) → Router überspringt es und zeigt einen Hinweis statt Schwarz (`/screen/N` bleibt bedienbar).

### Warum so

| Alternative | Bewertung |
|---|---|
| **iframe-Rotation (gewählt)** | robust, offline, einstellbar, kein WM-Gefrickel, testbar ohne Hardware |
| Fensterwechsel via `xdotool`/Openbox | fragil, jeder Tool-Wechsel braucht WM-Regeln, Fehler = schwarzer Bildschirm |
| Alles in eine Flask-App migrieren | großer Umbau aller drei Apps, hohes Risiko, kein Mehrwert für die Anzeige |

---

## 4. Datenmodell (SQLite der Verteiler-App)

```sql
CREATE TABLE kiosk_screen (            -- Bildschirm-Ausgänge
  id INTEGER PRIMARY KEY, idx INTEGER UNIQUE,   -- 1..2  (bestimmt /screen/<idx>)
  name TEXT, hdmi TEXT, enabled INTEGER DEFAULT 1);

CREATE TABLE kiosk_screen_tool (       -- Tool-Belegungen je Bildschirm
  id INTEGER PRIMARY KEY,
  screen_id INTEGER NOT NULL REFERENCES kiosk_screen(id),
  tool TEXT NOT NULL,                  -- slideshow | terminboard | safetycross
  dwell_seconds INTEGER DEFAULT 20,    -- Anzeigedauer
  sort INTEGER DEFAULT 0,
  enabled INTEGER DEFAULT 1,
  UNIQUE(screen_id, tool));

CREATE TABLE kiosk_setting (key TEXT PRIMARY KEY, value TEXT);
-- screen_count, cursor_idle_seconds, iframe_reload_minutes, tool_urls
```

**Tool-Registry** (`tools.py`, eine Quelle der Wahrheit):

| id | Label | URL (Default) | Default-Dauer |
|---|---|---|---|
| `slideshow` | Folien / Playlist | `http://localhost:8000/present/kiosk` | 60 s |
| `terminboard` | Termine | `http://localhost:8001/board/kiosk` | 30 s |
| `safetycross` | Safety Cross | `http://localhost:8002/` | 30 s |

---

## 5. Admin-Oberfläche „Anzeigen"

Neue Seite `/display` in der Verteiler-App (Dashboard-Menüpunkt):

* **Anzahl Bildschirme**: 1 / 2 (Umschalten legt Bildschirm 2 an/ab bzw. deaktiviert ihn).
* **Je Bildschirm**: Name, HDMI-Ausgang, Liste der Tools mit
  * Checkbox „aktiv",
  * Feld **Anzeigedauer (s)** — vorbelegt mit Default-Dauer,
  * Reihenfolge (Pfeile ▲▼),
  * Hinweis, ob das Tool **fest** (einziges) oder **rotierend** ist.
* **Buttons**: Speichern, „Vorschau" (öffnet `/screen/N` im neuen Tab), „Geräte-ID anzeigen".
* Speicherung wie im restlichen Dashboard (AJAX, kein Sammel-Dialog, ganze Zeile klickbar).

Zulässige Tools = die **installierten** und von der **Lizenz erlaubten** (siehe §7/§8).
Defaults beim Erst-Setup: 1 Bildschirm mit Slideshow fest; 2. Bildschirm mit Terminboard fest.

---

## 6. Mauszeiger — einheitlich in allen Tools

Ein Mechanismus für alle drei Seiten (`static/kiosk-cursor.js`, in jede Kiosk-Seite eingebunden):

```js
(function(){var MS=(window.KIOSK_CURSOR_IDLE||3000),t;
 function hide(){if(!document.getElementById('_kh')){var s=document.createElement('style');
   s.id='_kh';s.textContent='*,html,body{cursor:none!important}';document.head.appendChild(s);}}
 function show(){var s=document.getElementById('_kh');if(s)s.remove();clearTimeout(t);t=setTimeout(hide,MS);}
 ['mousemove','mousedown','wheel','keydown','touchstart'].forEach(function(e){
   document.addEventListener(e,show,true);});
 t=setTimeout(hide,MS);})();
```

* Idle-Zeit kommt aus den Einstellungen (`cursor_idle_seconds`, Default 3, per Meta/JS oder Daten-Attribut).
* **Konflikt auflösen:** das **transparente Cursor-Thema**, die Chromium-Extension `hidecursor` und
  `unclutter -idle 0 -root` werden aus `install.sh` **entfernt**. Sie blenden den Cursor dauerhaft aus —
  mit ihnen kann er beim Bewegen **nicht** wiederkommen. Sichtbarkeit steuert ab jetzt nur noch die Seite.
* Safety Cross bekommt dasselbe Snippet (dortige 30-s-Logik ersetzen), damit alle Tools identisch sind.

---

## 7. Installation mit Auswahl

`install.sh` der Verteiler-App wird das **eine** Installationsprogramm:

```bash
# interaktiv (Default) – fragt, was gebraucht wird:
#   "Welche Tools?  [1] Folien  [2] Termine  [3] Safety Cross   (z. B. 1,2)"
#   "Wie viele Bildschirme?  [1] / [2]"
sudo ./install.sh

# unbeaufsichtigt (für mehrere Geräte / Deployment):
sudo ./install.sh --tools=slideshow,terminboard --screens=2
```

* Nur gewählte Tools werden installiert (venv, Service, Port, Autostart).
* **Kiosk-Services je Bildschirm** statt je Tool: `kiosk-screen1.service`, `kiosk-screen2.service`
  → `chromium --kiosk --app=http://localhost:8000/screen/1` (bzw. `/screen/2`).
* 1 Bildschirm → keine 2-Monitor-Konfiguration, kein `xrandr`-Zweitschrift.
* Abteilungen „brauchen nur eins oder zwei" → genau das installieren + passende Lizenz.

---

## 8. Hardware-Lizenz (Bundle)

Ein Secret (Tim, **nie im Repo**), ein Key je Gerät, Gültigkeit für **Seriennummer + Tool-Set**:

```
license.key (auf dem Pi, /etc/lhtpi/license.key, chmod 600)
  features=slideshow,terminboard,safetycross
  key=9f2c…              # HMAC_SHA256(secret, serial|features|v1)
```

* Prüfung beim Start **aller** installierten Apps (gemeinsames Modul `common/license.py`);
  Mismatch → **Lock-Screen** (weiße Seite: „Lizenz gilt nicht für dieses Gerät").
* **Geräte-ID** (Pi-Seriennummer aus `/proc/cpuinfo`, gehasht) wird in der Admin-Seite angezeigt
  → Tim erzeugt den Key für genau dieses Gerät + Tool-Set.
* **Key-Generator** `tools/license-gen.py` (läuft offline bei Tim): Geräte-ID + Tool-Set → Key.
  Alternative Zufuhr: `install.sh --license-file /boot/lhtpi-license.txt` (Stick/Boot-Partition).
* Ohne Seriennummer (Dev/VM) → permissiv, damit Entwicklung/Tests laufen.
* Ehrliche Grenze dokumentieren: Offline-Lizenz = **Hürde gegen Kopieren**, kein DRM.

---

## 9. Arbeitspakete

| # | Paket | Repo | Fertig wenn |
|---|---|---|---|
| **S1** | Anzeige-Router: Registry, DB-Tabellen, `/screen/<n>`, `/api/screens`, Admin-Seite „Anzeigen", Tests | lhtpi | pytest grün; `curl /screen/1` liefert Rotation-HTML; je Bildschirm anderes Tool-Set; fest vs. rotierend korrekt |
| **S2** | Installer: Bildschirm-Anzahl, Kiosk-Service je Bildschirm, xrandr nur bei 2 Bildschirmen | lhtpi | frische Installation auf Pi: 1 und 2 Bildschirme korrekt, richtige URL je Ausgang |
| **S3** | Cursor einheitlich (Snippet + Entfernen von `unclutter`/Thema/Extension) | lhtpi + safety-cross | Cursor weg nach Idle, wieder da bei Bewegung — in allen drei Tools |
| **S4** | Installation mit Auswahl (interaktiv + Flags), nur gewählte Tools | lhtpi | `--tools=slideshow` installiert nur das; nichts Fremdes läuft |
| **S5** | Lizenz-Bundle + Key-Generator + Lock-Screens (alle Apps) | lhtpi + safety-cross | Kopie auf anderen Pi → Lock-Screen; falsches Tool-Set → Lock-Screen; Dev/VM läuft |
| **S6** | Doku (README, Bedienungsanleitung, Screenshots) + Hardware-Test | alle | Tim bestätigt auf echter Hardware |

Reihenfolge: **S1 → S2 → S4 → S5**, S3 parallel (klein, unabhängig). S6 am Ende je Paket mitwachsend.

---

## 10. Entscheidungen (09.10.2026)

1. **Bundle statt drei Repos.** `lhtpi` wird Verteiler: Anzeige-Router, Installer und Lizenz liegen hier;
   Safety-Cross-Code liegt als Kopie unter `tools/safety-cross/` (zusammen arbeiten → auswählen, wer sich
   einen Bildschirm teilt, geht nur mit einem gemeinsamen Stand). Das Repo `17Trust09/safety-cross`
   bekommt **keinen** eigenen Branch; die Kopie im Bundle ist ab jetzt die weiterentwickelte Fassung.
2. **Rotationstechnik:** iframe-Rotation im Browser (randlos eingebettet, kein Fenstermanager-Eingriff).
3. **Default-Anzeigedauern:** Folien 60 s · Termine 30 s · Safety Cross 30 s — je Tool änderbar
   (Beispiel 5 min / 2 min ist damit abgedeckt).

## 11. Stand der Umsetzung

| # | Paket | Stand |
|---|---|---|
| S1 | Anzeige-Router (Registry, DB, `/screen/<n>`, `/api/screens`, Admin-Seite, Tests) | ✅ erledigt (`test_kiosk_router.py`, 45 Prüfungen) |
| S3 | Cursor einheitlich in allen drei Tools + OS-Hacks entfernt | ✅ erledigt (`test_cursor_unified.py`) |
| S2 | Installer: ein Kiosk **je Bildschirm**, Monitor-Zuordnung, Aufräumen alter Kiosks | ✅ erledigt (`test_install_bundle.py`, 29 Prüfungen) |
| S4 | Installation mit Auswahl (1/2/3 Tools, Bildschirm-Anzahl, interaktiv + `--tools`/`--screens`) | ✅ erledigt; Merker `/etc/lhtpi/tools` + `/etc/lhtpi/screens` |
| S5 | Lizenz-Bundle + Key-Generator + Sperrseiten für das gewählte Tool-Set | ✅ erledigt (`test_license_bundle.py`, 28 Prüfungen) |
| S6 | Doku/Screenshots + Hardware-Test auf dem Pi | teils (Doku `INSTALLATION.md`); Hardware-Test offen |

### Lizenz in Kurzform

* Eine Lizenz gilt für **genau ein Gerät** (Pi-Seriennummer) und schaltet die
  gebuchten **Tools** und **Bildschirme** frei.
* Format `LHTPI-XXXX-XXXX-XXXX-XXXX`; die Signatur läuft über Nutzlast **und**
  volle Geräte-ID → kopierte SD-Karte = ungültige Lizenz.
* Der Installer erzeugt sie automatisch für das Gerät (`configure_license`),
  hinterlegt `/etc/lhtpi/license.key` und setzt das Merkmal
  `/etc/lhtpi/installed` (ab da ist die Prüfung aktiv).
* Ohne Lizenz und ohne Merkmal läuft die App im **Entwicklungsmodus** (keine
  Sperre) — auf einem echten Gerät ist immer eine Lizenz vorhanden.
* Beim Kunden nachlesen: Geräte-ID unter `http://<LAN-IP>:8000/lizenz`
  (bleibt auch bei gesperrter App erreichbar).
* Schlüssel erzeugen (nur beim Hersteller):

```bash
python3 license_bundle.py --make-key --tools=1,3 --screens=2 --hwid=piserial:1000000012345678
```

**Grenze:** Wer den Signaturschlüssel (`SECRET` in `license_bundle.py`) aus dem
ausgelieferten Image holt, kann sich selbst Lizenzschlüssel erzeugen. Im
Kunden-Image deshalb das Modul verschleiern (Skill `python-source-protection`).

### Tests im Bundle ausführen

```bash
bash run-tests.sh                          # alle Suiten auf einmal
./venv/bin/python test_kiosk_router.py     # Anzeige-Router (48 Prüfungen)
./venv/bin/python test_install_bundle.py   # Installer: Auswahl, Skripte, Services
./venv/bin/python test_license_bundle.py   # Hardware-Lizenz
./venv/bin/python test_cursor_unified.py   # Mauszeiger in allen drei Tools
./venv/bin/python test_usb_source.py       # Bestand (USB-Quelle)
```

### Installer in Kurzform

```bash
sudo bash install.sh                                  # fragt Tools + Bildschirme
sudo bash install.sh --tools=1,3 --screens=2 --no-reboot
```

* `--tools=1,2,3` → 1 Folien · 2 Terminboard · 3 Safety Cross (Namen gehen auch)
* Die Verteiler-App (Router + Lizenz) ist **immer** dabei; die Auswahl bestimmt,
  welche Tools zusätzlich installiert und angezeigt werden.
* Ein Chromium-Kiosk **je Bildschirm** (`kiosk-screen1/2.service`) auf
  `http://localhost:8000/screen/<n>`; alte Kiosk-Services je Tool werden entfernt.
* Der Router liest `/etc/lhtpi/tools` (nicht installierte Tools werden nie
  angezeigt) und `/etc/lhtpi/screens` (Startwert für die Bildschirm-Anzahl).

### Tests im Bundle ausführen

```bash
cd lhtpi
./venv/bin/python test_kiosk_router.py     # Anzeige-Router
./venv/bin/python test_cursor_unified.py   # Mauszeiger in allen drei Tools
./venv/bin/python test_usb_source.py       # Bestand (USB-Quelle)
cd tools/safety-cross && ../../venv/bin/python -m pytest tests/ -q   # SC (braucht pytest)
```

## 11. Ersteinrichtung und Netzwerk (09.10.2026)

Entscheidungen von Tim: gefragt wird **beim ersten Booten auf dem Bildschirm**
(Maus + Tastatur, das Gerät hat kein Netzwerk), **kein Access Point mehr**, und
konfiguriert wird weiterhin auf der Anzeigen-Seite — erreichbar über einen
Knopf in der **Safety-Cross-Admin-Seite**.

| Schritt | Inhalt | Stand |
|---|---|---|
| S7 | Access Point entfernen (`install.sh`, kein `wlan0`-Eingriff) | ✅ erledigt |
| S8 | Erststart-Modus: Anzeigen-Seite statt Kiosk, Merkmal `installed`, Pfad-Wächter für die Anzeigen | ✅ erledigt (`test_install_bundle.py`, `test_kiosk_router.py`) |
| S9 | Knopf „Anzeigen-Einstellungen öffnen" in der Safety-Cross-Admin-Seite | ✅ erledigt |
| S10 | Hardware-Test: Erststart, Maus + Tastatur, Bildschirm-Anzahl im Betrieb umstellen | offen (braucht Pi) |

Details: [ERSTEINRICHTUNG.md](ERSTEINRICHTUNG.md)

