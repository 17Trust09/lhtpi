# USB-Stick für die Präsentation (LHTPi)

So muss der Stick aufgebaut sein — alles im **Stick-Root**:

```
<Stick-Root>/
└── slides/
    ├── 01-start.jpg      ← Bilder/Videos, alphabetisch sortiert
    ├── 02-prozess.jpg
    ├── video.mp4
    └── settings.txt      ← optional: Anzeigedauern
```

## Regeln

- Erkannt werden nur Dateien **direkt im Ordner `slides/`** (keine Unterordner).
- Erlaubte Formate: `png`, `jpg`, `jpeg`, `gif`, `mp4`.
- Abspielreihenfolge: alphabetisch (case-insensitive).
- Ohne `settings.txt`: Bilder 10 Sekunden, Videos volle Länge.
- Mit `settings.txt` (siehe Beispiel): `default=` für die Standarddauer,
  `dateiname=sekunden` für einzelne Dateien, `0` = volle Videolänge.

## Beispiel

Die zwei Dateien `beispiel-folie-1.png` und `beispiel-folie-2.png` in diesem
Ordner sind echte Beispielbilder — du kannst den ganzen `slides/`-Ordner 1:1
auf einen Stick kopieren und direkt testen.
