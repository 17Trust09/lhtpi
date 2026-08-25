# USB-Stick-Vorlage (ein Stick für beides)

Ein **einziger** USB-Stick versorgt **beide** Anzeigen: die Präsentation
(LHTPi) und das Terminboard. Der Inhalt kommt **direkt in den Stick-Root**
(oberste Ebene) — nicht in einen Unterordner.

```
<Stick-Root>/
├── slides/                 ← Präsentation (LHTPi)
│   ├── 01-start.jpg
│   ├── video.mp4
│   └── settings.txt        ← optional: Anzeigedauern
└── termine.csv             ← Terminboard
```

## Präsentation (`slides/`)

- Erkannt werden nur Dateien **direkt im Ordner `slides/`** (keine Unterordner).
- Erlaubte Formate: `png`, `jpg`, `jpeg`, `gif`, `mp4`.
- Abspielreihenfolge: alphabetisch (case-insensitive).
- Ohne `settings.txt`: Bilder 10 Sekunden, Videos volle Länge.
- Mit `settings.txt` (siehe Beispiel): `default=` für die Standarddauer,
  `dateiname=sekunden` für einzelne Dateien, `0` = volle Videolänge.

## Terminboard (`termine.csv`)

- Eine Datei `termine.csv` im Stick-Root (UTF-8, Semikolon-getrennt).
- Erste Zeile = Spaltenüberschrift (exakt):

      typ;titel;referenz;start;ende;text

- Datum: `TT.MM.JJJJ` oder `JJJJ-MM-TT`.
- `typ` ∈ `kalibrierung | audit | info | wartung` (sonst `info`).
- `referenz`, `ende` und `text` dürfen leer sein.
- Zeilen ohne Titel sowie Leer-/Kommentarzeilen (`#`) werden ignoriert.

## Hinweise

- Stick einstecken → der Pi erkennt `slides/` **und** `termine.csv` automatisch
  (USB hat Vorrang, solange im jeweiligen Dashboard „Automatisch" steht).
- Abgelaufene Termine (Ende-Datum bzw. Start-Datum ohne Ende überschritten)
  werden automatisch aus der Tafel entfernt — Datum neu setzen, um sie wieder
  sichtbar zu machen.
- Die zwei `beispiel-folie-*.png` in `slides/` sind echte Beispielbilder — du
  kannst diesen Ordner 1:1 auf einen Stick kopieren und direkt testen.
