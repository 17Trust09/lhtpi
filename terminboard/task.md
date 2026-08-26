> ⚠️ **HISTORISCH** — Arbeitsauftrag (Prompt) für die ursprüngliche
> Implementierung des Terminboards. Erledigt. Aktueller Stand:
> `terminboard/README.md` und `STAND.md` im Repo-Root.

Du bist ein erfahrener Full-Stack-Entwickler (Flask + SQLAlchemy + Vanilla JS).

## Aufgabe

Lies zuerst die vollständige Spezifikation:
`/opt/data/projects/lhtpi/terminboard/GOAL.md`

Implementiere danach das komplette „Terminboard"-Projekt exakt nach dieser Spec.
Arbeitsverzeichnis: `/opt/data/projects/lhtpi/terminboard/`

Der aktuelle Git-Branch ist `feature/terminboard` (im Repo
`/opt/data/projects/lhtpi`). Bleib auf diesem Branch.

## Wichtige Umgebungshinweise

- Es gibt bereits eine funktionierende Referenz-App im selben Repo (LHTPi, im
  Repo-Root: `app.py`, `models.py`, `routes.py`, `usb_source.py`). Orientiere
  dich an deren Struktur/Muster, aber **ändere diese Dateien NICHT**.
- Python 3.13, Flask 3.1. Vorhandene Abhängigkeiten siehe
  `/opt/data/projects/lhtpi/requirements.txt`.
- Für lokale Tests ein venv unter `terminboard/test_venv` anlegen (bitte am
  Ende NICHT löschen, solange Tests laufen; aufräumen erst ganz am Schluss).
- Die App soll ohne echten USB-Stick testbar sein (USB-Erkennung ist mock-bar).

## Arbeitsweise (STRENG einhalten)

1. TDD: erst Tests für `usb_source.py` (CSV-/Datum-Parsing) und Source-Logik,
   dann Implementierung.
2. **Nach jeder abgeschlossenen Teilaufgabe `git add -A && git commit -m "..."`
   ausführen.** Niemals einen uncommitteten Zustand hinterlassen.
3. **Lösche NIEMALS Test-Dateien.**
4. **Ändere NICHTS außerhalb von `terminboard/`** (insbesondere keine Dateien
   im Repo-Root).
5. UI-Texte auf Deutsch. Keine externen CDN/Fonts.

## Abschluss-Kriterien (alles selbst prüfen, bevor du fertig bist)

- `python -m pytest` (im venv) → alle Tests grün.
- `python -m py_compile` auf allen `.py`-Dateien → keine Fehler.
- `bash -n install.sh` → OK.
- Die Flask-App importiert fehlerfrei und startet kurz auf Port 8001
  (`curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/login` → 200).
- `git status --short` → sauber (alles committet).

## Abschluss-Bericht (auf Deutsch)

Am Ende kurz melden: welche Dateien erstellt wurden, Testergebnis, und ob alle
Akzeptanzkriterien aus GOAL.md erfüllt sind. Bei bewussten Abweichungen von der
Spec diese explizit nennen.
