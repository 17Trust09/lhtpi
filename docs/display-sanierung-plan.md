# LHTPi Display-Sanierung – Plan

Stand: 2026-10-29 · Ausgangslage: „es funktioniert alles noch nicht richtig" bzw.
„ich schließe an einen beliebigen Bildschirm an → native Auflösung automatisch →
fertig, idealerweise ohne Skalieren".

## Ziel (vom Nutzer bestätigt)

1. **Anschließen = fertig.** An beliebigen Fernseher/Monitor (4K / FullHD / 720p)
   stecken → der Pi wählt automatisch die beste native Auflösung und stellt sie scharf ein.
2. **Überall gleich lesbar.** Eine Terminkarte / Safety-Cross / Folie soll auf jedem
   Bildschirm in derselben wahrgenommenen Größe erscheinen – nicht auf 4K winzig
   und auf 720p riesig. Ist das erreicht, entfällt das manuelle Skalieren weitgehend.
3. **Kein „Not Found"-Flackern.** Der Kiosk darf nie – auch nicht kurz – auf einer
   404-/Fehlermeldung landen, weder beim Start noch nach einem Anzeige-Neustart.

## Befund (Ursachen, belegt durch Code-Lektüre + Codex-Vergleich)

### A. Kein Single-Owner für die Anzeige
Mindestens fünf bis sechs Stellen sprechen xrandr mit `--auto`/`--mode` an und
können sich gegenseitig überschreiben:
- `scripts/hdmi-wache.sh` (10s-Takt, plus Rollback-Timer)
- Kiosk-Startskript aus `install.sh` (`render_screen_kiosk_script`, inkl. 5s-Geometrie-Watcher)
- `scripts/anzeige-rettung.sh`
- `scripts/anzeige-zurueck.sh`
- `bildschirm_info.setze_aufloesung` (Admin-Route) + `dauerhaft_setzen` (cmdline.txt)
- zusätzlich `lhtpi-display-guard.sh` / `lhtpi-entkoppeln.sh`

Es gibt keinen **einen** Ort, der „Welcher Modus, welche Position, welche
Skalierung, welcher primäre Ausgang?" beantwortet.

### B. Kritischer Bug (behoben, v1.11.4)
`bildschirm_info._modi` und `_edid_modi` waren doppelt definiert; die fehlerhafte
zweite Kopie globbte `/sys/class/drm/card*-HDMI-1/modes` statt `card*-HDMI-A-1`.
Folge: EDID-Modi wurden nie gefunden → native Erkennung lief leer → Fallback auf
xrandr-Standardliste („zu viele Auflösungen") und „automatisch nativ" griff nicht.

### C. Auflösung vs. Skalierung vermischt
Zwei parallele Größenmechanismen: xrandr-Moduswechsel (pixelgebunden, kann „kein
Signal"/Unschärfe) UND CSS-`zoom` auf `<body>`. Der gesetzte `SKALA`-Wert wird
nach dem CSS-Zoom-Umbau nirgends mehr als `--force-device-scale-factor` genutzt
(toter Code in `install.sh`). Auflösung (Schärfe) und Skalierung (Lesbarkeit)
müssen konsequent getrennt werden.

### D. „Überall gleich groß" braucht ein Referenz-Raster
Die Tools sind eigenständige Web-Apps in iframes (Folien :8000, Termine :8001,
Safety-Cross :8002). Ihre Pixelgröße hängt an der Bildschirmauflösung. Ohne ein
**festes logisches Raster** (Ankerfläche, z. B. 1920×1080), das Chromium per
device-scale-factor scharf auf die native Auflösung hochrechnet, ist „gleich groß
auf jedem Panel" nicht zu erreichen.

### E. Not Found (mehrere Quellen)
1. Race: synchroner Kiosk-Neustart vs. laufende Anfrage (teilweise durch
   `anzeige_neu_starten_verzoegert` gemildert, aber `system_neustart`-Fehlpfad ruft
   noch die synchrone Variante).
2. `screen_config(..., with_probe=True)` macht pro `/screen/N`-Aufruf einen
   synchronen TCP-Probe je Tool (0,6s) → langsame Antwort.
3. Leere/nicht initialisierte DB → `abort(404)`, `enabled`-Flip über `screen_count`.
4. `READY_URL`-Timing: Startskript startet nach Timeout „trotzdem" Chromium.

## Maßnahmen (priorisiert)

### Phase 1 – Fundament (nativ + scharf verlässlich)
- [x] 1.1 `bildschirm_info.py` entdoppeln (v1.11.4, erledigt).
- [ ] 1.2 „automatisch nativ" als **einziger** Modus: Kein manuelles
      Auflösungs-Menü, kein `video=`-Eintrag, kein `dauerhaft_setzen`. KMS + `--auto`
      (bzw. `--preferred`) setzt beim Anschließen die native Auflösung.
      Der xrandr-Wechsel als Lesbarkeits-Regler entfällt komplett.

### Phase 2 – Single-Owner
- [ ] 2.1 Ein Modul (`screen_state`) wird die EINZIGE Stelle, die xrandr setzt.
      Wächter/Retter/Zurück/Startskript/display-guard rufen nur noch `state.apply()`.
- [ ] 2.2 Geometrie/Position (primärer Ausgang, HDMI-2 rechts) in den Owner ziehen.
- [ ] 2.3 `anzeige-fein.json` bleibt EINZIGE Quelle für „skala je Bildschirm"
      (Auflösung entfällt dort); die drei inline-kopierten Python-Leser werden
      durch einen Owner-Aufruf ersetzt.

### Phase 3 – Referenz-Raster (Kernziel „überall gleich groß")
- [ ] 3.1 `screen.html` bekommt ein fixes logisches Raster (Anker ~1920×1080);
      iframes füllen es proportional.
- [ ] 3.2 Gesamtgröße je Bildschirm ausschließlich per device-scale-factor des
      nativen Modus (Verhältnis native Pixel zu Raster) – vektorscharf.
- [ ] 3.3 CSS-`zoom` auf body + totes `--device-scale-factor=1`/`ermittle_skala`
      entfernen; der Regler „Größe" steuert einen Wert → device-scale-factor-Flag.

### Phase 4 – Not Found strukturell unmöglich
- [ ] 4.1 `/screen/<idx>` liefert nie `abort(404)`; leere/deaktivierte Bildschirme
      bekommen eine „noch-leer"-Hülle. `ensure_defaults` idempotent, kein
      `enabled`-Flip über `screen_count` beim ersten Start.
- [ ] 4.2 Alle Kiosk-Neustarts auf die verzögerte double-fork-Variante;
      synchronen `system_neustart`-Fehlpfad beseitigen.
- [ ] 4.3 Probes async/gecacht statt synchron im Request-Pfad; ein totes Tool darf
      nie die Hülle killen, nur den einzelnen iframe leer lassen (`empty` existiert).
- [ ] 4.4 Chromium-Startziel auf einen nie-fehlschlagenden lokalen Endpunkt;
      Tool-Inhalte dynamisch nachladen.

### Phase 5 – Nachweise
- [ ] 5.1 End-to-End „anschließen = nativ + ausgefüllt" (Hotplug-Simulation, EDID-Rückgriff, Rastergröße).
- [ ] 5.2 Watchdog-Test: 10× schneller Kiosk-Neustart, nie 404 an `/screen`.

## Offene Punkte / Verifikationen am Gerät
- Melden echte 4K-Fernseher preferred=3840x2160 (nicht 4096x2160)? → am Gerät prüfen.
- device-scale-factor-Semantik am echten Chromium des Pi 4/5 verifizieren, bevor
  CSS-Zoom ganz abgeschaltet wird.

## Abgeschlossen (dieser Lauf)
- v1.11.4: doppelte `_modi`/`_edid_modi` entfernt (kritischer Fix, verifiziert).
- v1.11.3: Skalierung als CSS-Zoom, Bereich 0.5–3.0.
- v1.11.2: Anzeige-Neustart verzögert (kein Not-Found-Flackern beim Umstellen).
- v1.11.1: Wächter immer einrichten (Auto-Hotplug + Rollback auch bei 1 Bildschirm).
- v1.11.0: Auto-nativ beim Anschließen + 30s-Rollback bei manueller Wahl.
