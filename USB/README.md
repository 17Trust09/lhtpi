# USB-Stick-Vorlagen

Dieser Ordner enthält Beispiel-Strukturen für die beiden USB-Sticks, die der
Raspberry Pi erkennt. **Wichtig:** Der Pi erwartet den Inhalt jeweils direkt im
**Stick-Root** (oberste Ebene des Sticks) — nicht in einem Unterordner.

| Zweck | Ordner hier | Was auf den Stick-Root kommt |
|-------|-------------|------------------------------|
| Präsentation (LHTPi) | `praesentation/` | der Ordner `slides/` |
| Terminboard | `terminboard/` | die Datei `termine.csv` |

Details und Regeln stehen in den jeweiligen `README.md`.

In beiden Fällen gilt: Stick einstecken → der Pi erkennt ihn automatisch und
spielt/zeigt den Inhalt an (USB hat Vorrang, solange im Dashboard
„Automatisch" ausgewählt ist).
