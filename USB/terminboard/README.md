# USB-Stick für das Terminboard

So muss der Stick aufgebaut sein — Datei direkt im **Stick-Root**:

```
<Stick-Root>/
└── termine.csv
```

## Regeln

- Eine Datei `termine.csv` im Stick-Root (UTF-8, Semikolon-getrennt).
- Erste Zeile = Spaltenüberschrift (exakt):

      typ;titel;referenz;start;ende;text

- Datum: `TT.MM.JJJJ` oder `JJJJ-MM-TT`.
- `typ` ∈ `kalibrierung | audit | info | wartung` (sonst `info`).
- `referenz`, `ende` und `text` dürfen leer sein.
- Zeilen ohne Titel sowie Leer-/Kommentarzeilen (`#`) werden ignoriert.

## Hinweis

Abgelaufene Einträge (Ende-Datum überschritten, bzw. ohne Ende das Start-Datum)
werden automatisch aus der Anzeige entfernt. Soll ein Eintrag weiterhin sichtbar
bleiben, einfach das Datum neu setzen.
