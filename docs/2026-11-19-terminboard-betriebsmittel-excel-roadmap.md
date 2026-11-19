# Terminboard: Betriebsmittel- und Excel-Weiterentwicklung – Roadmap

> **Status: Nur Planung.** Mit der Implementierung wird erst begonnen, wenn Tim außerhalb dieser Planung ausdrücklich den Coding-Start freigibt.
>
> **Für Hermes:** Bei der späteren Umsetzung `subagent-driven-development`, `test-driven-development`, `baseline-gated-verification` und `embedded-kiosk-hardening` laden. Aufgaben der Reihe nach umsetzen, nach jedem Abschnitt testen und nur gezielt committen – niemals `git add -A`, weil Tim parallel am Repository arbeiten kann.

**Stand der Planung:** 19. November 2026  
**Repository:** `/opt/data/projects/lhtpi`  
**Teilprojekt:** `/opt/data/projects/lhtpi/terminboard`  
**Branch beim Erstellen der Roadmap:** `feature/multitool-kiosk`  
**Ausgangs-Commit:** `f12566e`  
**Baseline:** `192 passed, 10 warnings`

## Ziel

Die Excel-Datei `termine.xlsx` wird zur eindeutigen, langfristig pflegbaren Datenquelle für:

1. ausfallrelevante Termine von Prüfständen und Konsolen,
2. separate News und Audits,
3. stabile Betriebsmittel-IDs trotz Umbenennung,
4. eindeutige Vorgangsnummern ohne Wiederverwendung,
5. automatische Archivierung,
6. rückwirkend korrekte Monats- und Jahresberichte.

Die Anwender arbeiten fast ausschließlich in Excel. Deshalb müssen Anlage, Auswahl, Korrektur und Zusammenführung von Betriebsmitteln vollständig über die Arbeitsmappe möglich sein. Eine zusätzliche Webverwaltung darf dafür nicht erforderlich sein.

---

# 1. Festgelegte fachliche Anforderungen

## 1.1 Blatt `Termine`

Das Blatt enthält ausschließlich ausfallrelevante Vorgänge.

Sichtbare Spalten:

```text
Nr. | Art | Typ | Betriebsmittel | Von | Bis | Info | Status
```

Interne, ausgeblendete Spalte:

```text
Betriebsmittel-ID
```

Erlaubte Werte:

```text
Art:
- Kalibrierung
- Wartung
- Ausfall

Typ:
- Prüfstand
- Konsole

Status:
- offen
- abgeschlossen
```

Nicht mehr erlaubt:

```text
Art: Audit
Art: Info
Status: storniert
```

Regeln:

- Ein Betriebsmittel wird ausschließlich über das Dropdown ausgewählt.
- Freie manuelle Eingaben in `Termine.Betriebsmittel` werden von Excel blockiert.
- Neue Betriebsmittel müssen zuerst im Blatt `Betriebsmittel` angelegt werden.
- Nur abgeschlossene Kalibrierungen, Wartungen und Ausfälle gehen in die Ausfallstatistik ein.
- Die Ausfallzeit wird weiterhin ausschließlich innerhalb des Betriebsfensters Montag bis Freitag, 06:00–22:45 Uhr, ohne Hamburger Feiertage berechnet.
- Existieren Zeitblöcke im Blatt `Zeiten`, haben diese Vorrang vor dem vollständigen Von-bis-Zeitraum.

## 1.2 Blatt `News & Audits`

Audit und Info werden aus dem Blatt `Termine` herausgelöst, weil sie auf dem Bildschirm in der rechten Spalte `NEWS & AUDITS` erscheinen und keine Ausfallzeit erzeugen.

Spalten:

```text
Nr. | Art | Titel | Von | Bis | Info | Status
```

Erlaubte Werte:

```text
Art:
- Audit
- Info

Status:
- offen
- abgeschlossen
```

Regeln:

- Kein Pflichtfeld für Typ oder Betriebsmittel.
- Keine Einbeziehung in Prüfstands- oder Konsolenausfallzeiten.
- Offene Einträge werden in der rechten Bildschirmspalte angezeigt.
- Abgeschlossene Einträge werden in `Archiv News & Audits` verschoben.
- Vergangene Einträge werden nach den bestehenden Anzeigevorgaben ausgeblendet.

## 1.3 Blatt `Betriebsmittel`

Spalten:

```text
ID | Typ | Bezeichnung | Zusammenführen mit | Hinweis
```

Bewusst nicht vorhanden:

```text
Status aktiv/inaktiv
```

Begründung: Die Spalte war für den normalen Excel-Anwender nicht selbsterklärend und wird für den vereinbarten Ablauf nicht benötigt.

Regeln:

- `ID` wird durch LHTPi vergeben und darf durch Anwender nicht verändert werden.
- Neue Zeilen werden mit leerer ID angelegt.
- `Typ` ist `Prüfstand` oder `Konsole`.
- `Bezeichnung` ist der aktuell sichtbare Name.
- Nach dem ersten LHTPi-Import erhält das Betriebsmittel eine feste ID wie `BM-006`.
- Die ID bleibt auch bei Umbenennung und Typänderung unverändert.
- Ein neuer Name steht innerhalb derselben Excel-Datei sofort im Termine-Dropdown zur Auswahl; spätestens beim ersten LHTPi-Import wird die feste ID ergänzt.
- Ähnlich klingende Namen werden nicht automatisch vereinigt. `TESTFUCHS KONSOLE 1` und `TESTFUCHS KONSOLE 2` sind legitime, unterschiedliche Betriebsmittel.
- Exakt gleiche Kombinationen aus Typ und normalisierter Bezeichnung werden als Dublette gemeldet.

## 1.4 Blatt `Zeiten`

Spalten:

```text
Termin-Nr. | Von | Bis | Notiz
```

Regeln:

- `Termin-Nr.` verwendet ausschließlich T-Nummern aus dem Blatt `Termine`.
- Beispiel: `T-037`.
- Ein Termin darf mehrere Zeitblöcke besitzen.
- News- und Auditnummern dürfen hier nicht ausgewählt werden.

## 1.5 Archive

Zwei getrennte Archive:

```text
Archiv Termine
Archiv News & Audits
```

Regeln:

- Beim Status `abgeschlossen` wird der Datensatz automatisch in das passende Archiv verschoben.
- Die ursprüngliche Vorgangsnummer bleibt erhalten.
- Archivierte Nummern werden niemals erneut verwendet.
- Ziel zuerst schreiben, Quelle danach entfernen.
- Vor jeder Änderung der Arbeitsmappe wird eine `.bak`-Sicherung erstellt.
- Bei einem Schreibfehler wird auf die Sicherung zurückgerollt.
- Ein schreibgeschützter Stick verhindert nicht den erfolgreichen Datenimport; der Schreibfehler wird separat gemeldet.

---

# 2. Nummernkonzept

## 2.1 Termine

```text
T-001 bis T-500
```

## 2.2 News und Audits

```text
N-001 bis N-500
```

## 2.3 Regeln

- Beide Nummernkreise sind bereits in der Vorlage vollständig vorgegeben.
- Die Nummernspalten werden in Excel geschützt.
- Eine Zeile, die nur eine vorgegebene Nummer enthält, ist eine leere Vorlagenzeile und darf nicht importiert werden.
- Nummern sind über aktive Blätter und Archive hinweg eindeutig.
- Eine vorhandene Nummer darf nicht in einem zweiten Datensatz verwendet werden.
- `T-037` bleibt `T-037`, auch wenn der Termin archiviert wird.
- Fehlende, geänderte oder doppelte Nummern werden beim Import gemeldet.
- Die Anwendung darf Nummern nicht anhand der Excel-Zeilennummer ableiten.
- Nach Ausschöpfung von 500 Nummern wird die Vorlage durch den Generator erweitert; bestehende Nummern bleiben unverändert.

Interne Bezeichnung im Code:

```text
vorgangsnummer
```

Die sichtbare Excel-Überschrift darf weiterhin kurz `Nr.` heißen.

---

# 3. Betriebsmittel-Identität und nachträgliche Pflege

## 3.1 Feste Identität

Nicht der Name und nicht die Excel-Zeile identifizieren ein Betriebsmittel, sondern eine unveränderliche ID:

```text
BM-001 | Prüfstand | P31 THSA
BM-002 | Konsole   | TESTFUCHS KONSOLE 1
BM-003 | Konsole   | TESTFUCHS KONSOLE 2
```

Die neutralen `BM-…`-IDs werden verwendet, damit ein Typ später geändert werden kann, ohne dass eine ID wie `PS-…` fachlich falsch wird.

## 3.2 Umbenennung

Beispiel:

```text
BM-002 | Konsole | TESTTUCHS KONSOLE 1
```

wird geändert zu:

```text
BM-002 | Konsole | TESTFUCHS KONSOLE 1
```

Folgen:

- Historische Vorgänge bleiben über `BM-002` verbunden.
- Neue Bildschirmansichten verwenden den aktuellen Namen.
- Neu erzeugte Monats- und Jahresberichte verwenden den aktuellen Namen.
- Die Ausfallstunden werden nicht neu gebucht und nicht dupliziert.

## 3.3 Typänderung

Bei derselben ID darf geändert werden:

```text
Prüfstand → Konsole
Konsole → Prüfstand
```

Danach werden Berichte rückwirkend in der korrekten Kategorie dargestellt.

## 3.4 Zusammenführen

Beispiel:

```text
BM-021 | Konsole | TESTTUCHS KONSOLE 1 | Zusammenführen mit: BM-006
BM-006 | Konsole | TESTFUCHS KONSOLE 1
```

Beim Import:

1. Alle Vorgänge von `BM-021` werden atomar `BM-006` zugeordnet.
2. Zeitblöcke und Ausfallstunden bleiben unverändert.
3. `BM-021` wird als Alias/zusammengeführt intern erhalten, damit ältere Excel-Dateien weiterhin zugeordnet werden können.
4. Die Quellzeile wird nach erfolgreichem Schreibvorgang aus der aktiven Betriebsmittelliste entfernt.
5. Die Spalte `Zusammenführen mit` wird nur mit existierenden, anderen BM-IDs akzeptiert.
6. Selbstzusammenführung und zyklische Zusammenführungen werden abgelehnt.
7. Danach werden alle betroffenen Berichte neu erzeugt.

## 3.5 Entfernte Betriebsmittelzeilen

Wenn eine bestehende BM-ID aus dem Excel-Blatt gelöscht wird, ohne sie zusammenzuführen:

- Historische Daten werden nicht gelöscht.
- Das Betriebsmittel bleibt intern zur Darstellung alter Vorgänge erhalten.
- Es erscheint nicht mehr im Excel-Dropdown.
- Der Importbericht weist auf die Entfernung aus der aktiven Excel-Stammliste hin.

Damit ist keine zusätzliche sichtbare Aktiv/inaktiv-Spalte notwendig.

---

# 4. Zielarchitektur

## 4.1 Datenbankmodell

Das bisherige Modell `Pruefstand` wird fachlich durch ein allgemeines Betriebsmittelmodell ersetzt.

Vorgesehene Struktur:

```text
Betriebsmittel
- id                interne DB-ID
- kennung           eindeutige feste ID, z. B. BM-001
- typ               pruefstand | konsole
- bezeichnung       aktueller sichtbarer Name
- in_excel_aktiv    interne Information, nicht als Excel-Statusspalte sichtbar
- zusammengefuehrt_in_id  optionaler Verweis auf Zielbetriebsmittel
- created_at
- updated_at
```

`Vorgang` wird erweitert:

```text
Vorgang
- vorgangsnummer       T-001 oder N-001, eindeutig
- art                  kalibrierung | wartung | ausfall | audit | info
- betriebsmittel_id    Pflicht für T-Vorgänge, leer für News/Audits
- titel                Pflicht für News/Audits, optional bei T-Vorgängen
- von
- bis
- info
- status               offen | abgeschlossen | entfernt
- revision
- inhalt_hash
- quelle
- abgeschlossen_am
```

Hinweise:

- `entfernt` bleibt ein interner DB-Zustand und ist kein Excel-Dropdownwert.
- `storniert` wird aus dem Excel-Vertrag entfernt und zählt nicht mehr als fachlicher Eingabestatus.
- Der bisher direkt gespeicherte Text `Vorgang.pruefstand` wird durch die Beziehung zu `Betriebsmittel` ersetzt.
- Die Auswertung gruppiert über die Betriebsmittel-ID und liest den aktuellen Namen erst beim Erzeugen des Reports.

## 4.2 SQLite-Migration

Da derzeit kein Alembic eingesetzt wird, wird eine eigene idempotente Migration benötigt.

Vorgesehener neuer Pfad:

```text
terminboard/schema_upgrade.py
```

Anforderungen:

1. Datenbank vor der Migration sichern.
2. Vorhandene Tabellen und Spalten über SQLite-PRAGMA prüfen.
3. `Betriebsmittel` aus bisherigen `Pruefstand`-Einträgen und den eindeutigen Werten aus `Vorgang.pruefstand` aufbauen.
4. Eindeutige BM-IDs deterministisch vergeben.
5. Bestehende Vorgänge den neuen Betriebsmitteln zuordnen.
6. Bestehende numerische Nummern ohne Kollision in T-Nummern überführen.
7. Audit- und Info-Vorgänge ohne Betriebsmittelbezug erhalten.
8. Migration in einer Transaktion ausführen.
9. Wiederholter Start darf keine weiteren Änderungen verursachen.
10. Bei Fehlern Originaldatenbank unangetastet lassen und Sicherung melden.

## 4.3 Excel-Vertrag

Der Parser liefert künftig getrennte Bereiche:

```python
{
    'termine': [...],
    'news': [...],
    'zeiten': {...},
    'betriebsmittel': [...],
    'fehler': [...],
    'dateiname': 'termine.xlsx',
}
```

Für Übergangsdateien kann eine klar begrenzte Kompatibilität mit dem derzeitigen Modell-2-Format bestehen. Die neue Vorlage selbst ist Modell 3 und muss eindeutig erkannt werden.

Vorgesehene Dateien:

```text
terminboard/excel_modell3.py
terminboard/tools_vorlage_modell3_bauen.py
terminboard/vorlagen/termine_modell3.xlsx
```

Das bestehende `excel_modell2.py` bleibt während der Migration zunächst unverändert als Fallback erhalten und wird erst entfernt, wenn die neue Vorlage auf dem Pi erfolgreich produktiv getestet wurde.

## 4.4 Schreibprotokoll für den USB-Stick

LHTPi ist bereits zweiter Schreiber für die Archivierung. Modell 3 erweitert das kontrollierte Schreiben um:

- Vergabe leerer BM-IDs,
- Eintragen/Bestätigen der ausgeblendeten BM-ID in Terminzeilen,
- Entfernen erfolgreich zusammengeführter Betriebsmittelzeilen,
- Archivieren von Terminen,
- Archivieren von News und Audits.

Sicherheitsreihenfolge:

1. Arbeitsmappe vollständig lesen und validieren.
2. Datenbankimport in Transaktion vorbereiten.
3. Falls Excel-Änderungen nötig sind, Schreibrecht prüfen.
4. `.bak` anlegen.
5. Neue vollständige Datei in temporären Pfad schreiben.
6. Temporäre Datei erneut mit `openpyxl` öffnen und Struktur prüfen.
7. Original atomar ersetzen.
8. Datenbanktransaktion abschließen.
9. Dateihash des tatsächlich geschriebenen Stands erfassen.
10. Stick wieder read-only schalten.

Bei einem nicht beschreibbaren Stick:

- gültige Daten lesen und importieren,
- keine IDs erfinden, deren Rückschreiben unbestätigt bleibt,
- Importbericht mit konkretem Schreibproblem ausgeben,
- beim nächsten Lauf erneut versuchen.

---

# 5. Bildschirm und API

## 5.1 Linke Bildschirmspalte

Titel kann bei Bedarf von `KALIBRIERUNG / WARTUNG` auf eine umfassendere Bezeichnung angepasst werden, beispielsweise:

```text
KALIBRIERUNG / WARTUNG / AUSFALL
```

Anzeigen:

- Kalibrierung,
- Wartung,
- Ausfall,
- Prüfstände,
- Konsolen.

Die Spaltenüberschrift `Prüfstand` wird auf `Betriebsmittel` geändert.

## 5.2 Rechte Bildschirmspalte

`NEWS & AUDITS` liest ausschließlich das gleichnamige Excel-Blatt.

Anzeigen:

- Audit,
- Info.

Ausfallereignisse dürfen nicht mehr versehentlich in der rechten Spalte landen. Die aktuelle Logik in `routes.py`, die alles außer Kalibrierung/Wartung als News behandelt, muss ersetzt werden.

Zieltrennung:

```python
termine = art in {'kalibrierung', 'wartung', 'ausfall'}
news = art in {'audit', 'info'}
```

## 5.3 API

`/board/api/status` soll weiterhin kompatible Hauptfelder liefern, aber intern eindeutig trennen:

```json
{
  "termine": [],
  "kalibrierungen": [],
  "news": [],
  "betriebsmittel": []
}
```

Die genaue öffentliche Nutzlast wird durch Tests festgeschrieben, bevor bestehende Feldnamen geändert werden.

---

# 6. Berichte

## 6.1 Monatsbericht

Der Monatsbericht erhält getrennte Bereiche:

```text
Offene Termine
Abgeschlossene Termine
Ausfallzeiten Prüfstände
Ausfallzeiten Konsolen
```

Audit und Info werden nicht in die Ausfallstatistik aufgenommen. Falls sie im Terminbericht erscheinen sollen, erhalten sie einen eigenen Abschnitt `News & Audits`, nicht die Ausfalltabelle.

## 6.2 Jahresbericht

Getrennte Auswertung nach Betriebsmitteltyp:

```text
Prüfstände
Konsolen
```

Optional zusätzlich:

```text
Gesamtausfallzeit aller Betriebsmittel
```

Die Summe darf dabei nicht doppelt gebildet werden.

## 6.3 Umbenennung und Regeneration

Bei Umbenennung, Typänderung oder Zusammenführung eines Betriebsmittels:

1. betroffene Jahre aus den zugeordneten Vorgängen bestimmen,
2. alle Monatsberichte dieser Jahre neu erzeugen,
3. Jahresberichte dieser Jahre neu erzeugen,
4. vorhandene PDF-Dateien lokal und auf dem Stick ersetzen.

Damit zeigen auch historische Berichte den aktuell korrigierten Namen. Die eigentlichen Vorgangsdaten und Stunden bleiben unverändert.

---

# 7. Umsetzungsphasen

## Phase 0: Baseline sichern

**Dateien:** keine Produktivänderung.

1. Aktuellen Branch und Commit dokumentieren.
2. `git status --short` prüfen und fremde Änderungen nicht anfassen.
3. Vollständige Testsuite ausführen.
4. Aktuelle Vorlage und eine Testdatenbank sichern.
5. Aktuelles Verhalten der Kiosk-API als JSON-Fixture speichern.

Verifikation:

```bash
cd /opt/data/projects/lhtpi/terminboard
./venv/bin/python -m pytest tests/ -q
```

Erwartete Ausgangsbasis: `192 passed`.

## Phase 1: Modell-3-Vertrag durch Tests festschreiben

**Create:**

```text
terminboard/tests/test_excel_modell3.py
terminboard/tests/fixtures/modell3_minimal.xlsx
```

Tests zuerst für:

- 500 eindeutige T-Nummern,
- 500 eindeutige N-Nummern,
- leere vorgefüllte Zeilen werden ignoriert,
- getrennte Termine und News,
- Status nur offen/abgeschlossen,
- kein Audit/Info in Termine,
- keine Kalibrierung/Wartung/Ausfall in News,
- Betriebsmittel ohne ID,
- bestehende BM-ID,
- exakte Dublette,
- legitime ähnliche Namen,
- versteckte BM-ID,
- Zeitblock mit T-Nummer,
- doppelte Vorgangsnummer über Aktivblatt und Archiv.

## Phase 2: Generator für die neue Excel-Vorlage

**Create:**

```text
terminboard/tools_vorlage_modell3_bauen.py
terminboard/vorlagen/termine_modell3.xlsx
```

**Modify:**

```text
terminboard/README.md
USB/README.md
```

Generator erzeugt vollständig:

- Anleitung,
- Termine,
- Zeiten,
- News & Audits,
- Betriebsmittel,
- Archiv Termine,
- Archiv News & Audits,
- Dropdowns,
- Zellschutz,
- Statusfarben,
- ausgeblendete BM-ID,
- T-001 bis T-500,
- N-001 bis N-500.

Ein `--pruefen`-Modus lädt die Datei erneut und validiert alle Dropdownbereiche, Blattnamen und Nummernkreise.

## Phase 3: Parser Modell 3

**Create:**

```text
terminboard/excel_modell3.py
```

**Modify:**

```text
terminboard/usb_source.py
terminboard/stick_watcher.py
```

Parserregeln:

- feste maximale Spaltenzahl je Blatt,
- keine Dekoration als Datensatz lesen,
- T-/N-Format streng prüfen,
- leere Vorlagenzeilen überspringen,
- fehlerhafte Zeilen einzeln melden,
- gültige Zeilen trotzdem importieren,
- Betriebsmittel-ID bevorzugen,
- bei leerer ID über Typ + exakten Namen auflösen,
- keine unscharfe automatische Zusammenführung.

## Phase 4: Datenmodell und Migration

**Create:**

```text
terminboard/schema_upgrade.py
terminboard/tests/test_schema_upgrade.py
```

**Modify:**

```text
terminboard/models.py
terminboard/historie.py
terminboard/app.py
```

TDD für:

- leere neue Datenbank,
- Migration bestehender Prüfstände,
- Migration bestehender Vorgänge,
- stabile BM-IDs,
- wiederholte idempotente Migration,
- Rückrollback bei Fehler,
- Erhalt sämtlicher Zeitblöcke und Stunden.

## Phase 5: Betriebsmittel-Synchronisation

**Create:**

```text
terminboard/betriebsmittel_sync.py
terminboard/tests/test_betriebsmittel_sync.py
```

Funktionen:

- neue BM-ID vergeben,
- Umbenennung erkennen,
- Typänderung erkennen,
- exakte Dublette melden,
- Zusammenführung validieren,
- Vorgänge atomar umhängen,
- Alias erhalten,
- entfernte Excel-Zeile intern erhalten,
- benötigte Excel-Rückschreibungen beschreiben.

## Phase 6: Import und Revisionen auf Vorgangsnummer umstellen

**Modify:**

```text
terminboard/historie.py
terminboard/tests/test_historie.py
terminboard/tests/test_ende_zu_ende.py
```

Neue Identität:

```text
vorgangsnummer
```

Nicht mehr als Hauptidentität verwenden:

```text
Art + Name + Von
```

Dadurch darf ein Termin umbenannt oder zeitlich korrigiert werden, ohne einen zweiten Vorgang zu erzeugen.

## Phase 7: Zwei Archive generalisieren

**Modify:**

```text
terminboard/archiv.py
terminboard/tests/test_archiv.py
```

Archivfunktion wird für zwei Blattpaare konfigurierbar:

```text
Termine → Archiv Termine
News & Audits → Archiv News & Audits
```

Zusätzlich prüfen:

- T-/N-Nummer bleibt erhalten,
- vorgefüllte Leerzeilen werden nicht archiviert,
- keine doppelte Archivnummer,
- Ziel zuerst, Quelle danach,
- Backup und Rollback,
- Formatierungen und Validierungen bleiben intakt.

## Phase 8: Sicheres Excel-Rückschreiben

**Create:**

```text
terminboard/excel_writeback.py
terminboard/tests/test_excel_writeback.py
```

Rückschreibungen:

- neue BM-ID,
- versteckte BM-ID im Termin,
- erfolgreich erledigte Zusammenführung,
- Archivverschiebungen.

Die eigentliche Datei wird erst ersetzt, nachdem die temporäre Datei erneut erfolgreich geladen und strukturell geprüft wurde.

## Phase 9: Kiosk-API und Bildschirmtrennung

**Modify:**

```text
terminboard/routes.py
terminboard/usb_source.py
terminboard/templates/board.html
terminboard/tests/test_terminboard.py
```

Tests:

- Ausfall erscheint links, nicht rechts,
- Audit erscheint rechts, nicht links,
- Info erscheint rechts, nicht links,
- Konsole wird als Betriebsmittel angezeigt,
- Überschrift lautet nicht mehr ausschließlich Prüfstand,
- bestehende API-Grundfelder bleiben soweit möglich kompatibel.

## Phase 10: Berichte auf Betriebsmittel-ID umstellen

**Modify:**

```text
terminboard/bericht.py
terminboard/historie.py
terminboard/tests/test_bericht.py
```

Tests:

- Prüfstände und Konsolen getrennt,
- Name kommt aus aktueller Betriebsmittelzeile,
- Umbenennung ändert Reporttext, nicht Stunden,
- Zusammenführung summiert korrekt,
- Audit und Info erzeugen keine Ausfallstunden,
- betroffene historische Jahre werden neu generiert.

## Phase 11: Stick-Watcher integrieren

**Modify:**

```text
terminboard/stick_watcher.py
terminboard/tests/test_stick_watcher.py
```

Reihenfolge je Durchlauf:

1. Hash und Format erkennen.
2. Lesen und validieren.
3. Betriebsmittel synchronisieren.
4. Termine/News importieren.
5. Rückschreibbedarf bestimmen.
6. Excel sicher aktualisieren.
7. Archivieren.
8. neuen Hash registrieren.
9. betroffene Berichte regenerieren.
10. Stick wieder read-only schalten.

Wichtig: Ein vom Gerät selbst erzeugter neuer Dateihash darf nicht zu einer Endlosschleife aus Selbstimport und erneutem Schreiben führen.

## Phase 12: Dokumentation und Updatepfad

**Modify:**

```text
terminboard/README.md
USB/README.md
STAND.md
OFFENE-PUNKTE.md
```

Dokumentieren:

- Excel-Arbeitsablauf für Nutzer,
- neues Betriebsmittel anlegen,
- Umbenennen,
- Typ ändern,
- Zusammenführen,
- T-/N-Nummern,
- Archive,
- Fehlerfälle bei schreibgeschütztem Stick,
- Migration von Modell 2 auf Modell 3,
- Wiederherstellung aus `.bak`.

## Phase 13: Vollständige Verifikation

Ausführen:

```bash
cd /opt/data/projects/lhtpi/terminboard
./venv/bin/python -m pytest tests/ -q
./venv/bin/python -m py_compile *.py
cd /opt/data/projects/lhtpi
bash -n install.sh
```

Zusätzlich:

- Flask-App lokal starten,
- `/login` muss HTTP 200 liefern,
- `/board/kiosk` muss HTTP 200 liefern,
- `/board/api/status` mit Modell-3-Testdatei prüfen,
- Modell-3-Datei zweimal importieren: zweiter Import ohne Doppelbuchung,
- Testumbenennung durchführen und PDFs neu erzeugen,
- Testzusammenführung durchführen und Stunden vergleichen,
- Testarchivierung auf einer Kopie durchführen,
- Schreibfehler simulieren und Rollback nachweisen.

## Phase 14: Pi2-Deployment erst nach Freigabe

Zielgerät laut aktuellem Projektstand:

```text
Pi2 / lhtpi2 / 192.168.178.49
Repository: /home/pi/lhtpi
Terminboard: Port 8001
```

Deployment erst nach lokaler Freigabe:

1. Datenbank und `termine.xlsx` auf dem Pi sichern.
2. Code gezielt aktualisieren.
3. Migration einmalig ausführen und Log sichern.
4. Services neu starten.
5. HTTP-Healthchecks durchführen.
6. Kiosk auf dem echten Bildschirm visuell prüfen.
7. Teststick mit Kopie der Excel verwenden.
8. Erst danach produktiven Stick einsetzen.
9. Rollbackpfad für Code, DB und Excel bereithalten.

---

# 8. Akzeptanzkriterien

Die Umsetzung gilt erst als abgeschlossen, wenn alle Punkte nachgewiesen sind:

- [ ] Modell-3-Vorlage wird reproduzierbar per Skript erzeugt.
- [ ] `Termine` enthält ausschließlich Kalibrierung, Wartung und Ausfall.
- [ ] `News & Audits` enthält ausschließlich Audit und Info.
- [ ] `storniert` ist kein Excel-Status mehr.
- [ ] Betriebsmittel besitzt keine sichtbare Aktiv/inaktiv-Spalte.
- [ ] Neue Betriebsmittel werden zuerst im Stammdatenblatt angelegt.
- [ ] Termine erlauben nur die Dropdown-Auswahl eines Betriebsmittels.
- [ ] Leere BM-ID wird beim ersten Import sicher vergeben und zurückgeschrieben.
- [ ] Umbenennung bei gleicher BM-ID erhält sämtliche Historie.
- [ ] Typänderung bei gleicher BM-ID ordnet Berichte rückwirkend korrekt zu.
- [ ] Ähnliche Namen werden nicht automatisch vereinigt.
- [ ] Manuelle Zusammenführung über Ziel-ID funktioniert atomar.
- [ ] T-001 bis T-500 sind eindeutig und vorgefüllt.
- [ ] N-001 bis N-500 sind eindeutig und vorgefüllt.
- [ ] Leere nummerierte Vorlagenzeilen werden ignoriert.
- [ ] Nummern bleiben beim Archivieren erhalten.
- [ ] Archivierte Nummern werden nicht wiederverwendet.
- [ ] Zeitblöcke verwenden ausschließlich T-Nummern.
- [ ] Prüfstands- und Konsolenausfälle werden getrennt ausgewertet.
- [ ] Audit und Info erzeugen keine Ausfallzeit.
- [ ] Berichte verwenden immer den aktuellen Betriebsmittelnamen.
- [ ] Namens- oder Typänderungen regenerieren alle betroffenen Berichte.
- [ ] Mehrfachimport erzeugt keine Doppelbuchungen.
- [ ] Excel-Schreibvorgänge besitzen Backup, temporäre Datei, Prüfung und Rollback.
- [ ] Ein schreibgeschützter Stick bringt Import und Kiosk nicht zum Absturz.
- [ ] Komplette Testsuite ist grün.
- [ ] Lokaler HTTP- und Kiosk-Test ist erfolgreich.
- [ ] Deployment auf Pi2 wurde mit Sicherung und Rückrolltest verifiziert.

---

# 9. Nicht Teil des Coding-Starts ohne zusätzliche Freigabe

- Keine Änderung an der eigentlichen LHTPi-App auf Port 8000, sofern nicht technisch zwingend.
- Keine Änderung an Monitorzuordnung, Kiosk-Härtung oder systemd-Startreihenfolge außerhalb des notwendigen Terminboard-Updates.
- Keine automatische unscharfe Namenskorrektur.
- Kein Löschen historischer Vorgänge oder Ausfallzeiten.
- Kein produktives Pi-Deployment, bevor die lokale Umsetzung vollständig getestet und Tim die Freigabe erteilt hat.
- Kein Start der Implementierung allein aufgrund dieser Roadmap.

---

# 10. Coding-Start

Der Coding-Start erfolgt ausschließlich nach einer ausdrücklichen Nachricht von Tim, beispielsweise:

```text
Fang mit der Umsetzung der LHTPi-Roadmap an.
```

Bis dahin bleibt dieses Dokument die verbindliche Planung und es werden keine Produktivdateien des Terminboards verändert.
