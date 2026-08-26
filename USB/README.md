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
└── termine.xlsx            ← Terminboard (bevorzugt, Excel-Vorlage)
```

## Terminboard (`termine.xlsx`)

Für Nicht-Techniker gedacht: eine **Excel-Vorlage** mit verständlichen
deutschen Spalten, einem **Dropdown** für die Art und **Datumsfeldern**.

- Spalten: `Art | Titel | Referenz | Von | Bis | Hinweis`
- `Art` über Dropdown: `Kalibrierung`, `Audit`, `Wartung`, `Info`
- `Von` ist Pflicht; `Bis`, `Referenz` und `Hinweis` dürfen leer bleiben.
- Datum `TT.MM.JJJJ`.
- Die Datei enthält ein zweites Blatt **„Anleitung“** und Beispielzeilen,
  die man einfach überschreiben oder löschen kann.
- Abgelaufene Termine werden automatisch von der Anzeige entfernt.

### Fallback `termine.csv`

Falls keine `termine.xlsx` vorhanden ist, liest das Terminboard weiterhin die
alte `termine.csv` (UTF-8, Semikolon-getrennt, Header
`typ;titel;referenz;start;ende;text`). Die `xlsx` hat aber **Vorrang**, wenn
beide Dateien auf dem Stick liegen.

## Präsentation (`slides/`)

- Erkannt werden nur Dateien **direkt im Ordner `slides/`** (keine Unterordner).
- Erlaubte Formate: `png`, `jpg`, `jpeg`, `gif`, `mp4`.
- Abspielreihenfolge: alphabetisch (case-insensitive).
- Ohne `settings.txt`: Bilder 10 Sekunden, Videos volle Länge.
- Mit `settings.txt` (siehe Beispiel): `default=` für die Standarddauer,
  `dateiname=sekunden` für einzelne Dateien, `0` = volle Videolänge.

## Hinweise

- Stick einstecken → der Pi erkennt `slides/` **und** `termine.xlsx`
  automatisch (USB hat Vorrang, solange im jeweiligen Dashboard „Automatisch“
  steht).
- Die zwei `beispiel-folie-*.png` in `slides/` sind echte Beispielbilder — du
  kannst diesen Ordner 1:1 auf einen Stick kopieren und direkt testen.
