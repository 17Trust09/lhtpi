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

Die Excel-Datei `termine.xlsx` ist die eindeutige Datenquelle (Modell 3). Sie
enthält sechs Blätter:

- `Termine` — Kalibrierung, Wartung, Ausfall (Nummern `T-001 … T-500`).
- `News & Audits` — Audit und Info (Nummern `N-001 … N-500`).
- `Betriebsmittel` — Stammdaten: `ID`, `Typ` (Prüfstand/Konsole),
  `Bezeichnung`, `Zusammenführen mit`.
- `Zeiten` — Uhrzeitblöcke, verweisen auf `T-Nummern`.
- `Archiv Termine` / `Archiv News & Audits` — abgeschlossene Vorgänge.

Wichtig für die tägliche Arbeit:

- **Neues Betriebsmittel:** zuerst unten im Blatt `Betriebsmittel` anlegen
  (`Typ` + `Bezeichnung`); die `ID` bleibt leer, das Gerät vergibt sie beim
  Import und schreibt sie zurück.
- **Umbenennen/Typ ändern:** einfach die `Bezeichnung` bzw. `Typ` ändern – die
  `ID` bleibt. Historie und Berichte folgen rückwirkend.
- **Zusammenführen:** in `Zusammenführen mit` die Ziel-`BM-NNN` eintragen.
- `Art` und `Typ` und `Betriebsmittel` haben Dropdowns; freie Eingaben blockt
  Excel.
- Der Status kennt nur `offen` und `abgeschlossen` (kein `storniert` mehr).
  `abgeschlossen` verschiebt die Zeile automatisch ins passende Archiv.
- Ein schreibgeschützter Stick verhindert den Import nicht; das Zurückschreiben
  (IDs, Archiv) wird gemeldet und später nachgeholt.
- Vor Änderungen legt das Gerät eine `.bak`-Sicherung an.

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
