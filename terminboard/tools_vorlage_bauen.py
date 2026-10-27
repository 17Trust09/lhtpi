"""Erzeugt die Excel-Vorlage „Modell 2" neu.

Warum ein Skript statt einer gepflegten Binärdatei: Jede Änderung an Spalten,
Auswahllisten oder Blättern ist im Code nachvollziehbar, und die Vorlage kann
jederzeit identisch wiederhergestellt werden.

Aufruf:
    python3 tools_vorlage_bauen.py            # schreibt die Vorlage neu
    python3 tools_vorlage_bauen.py --pruefen  # prüft nur die Auswahllisten

Drop-Downs (Auswahllisten):
  * ``Termine``!B  Art          – Kalibrierung / Wartung / Ausfall / Audit / Info
  * ``Termine``!C  Prüfstand    – Bereichsname ``Pruefstaende`` → Blatt „Prüfstände"
  * ``Termine``!G  Status       – offen / abgeschlossen / storniert
  * ``Archiv``!B/C/G            – dieselben Listen wie im Blatt „Termine"
  * ``Zeiten``!A   Termin (Nr)  – Nummern aus dem Blatt „Termine" (dynamisch)

Die Listen reichen bis Zeile 500 (wie bisher). Excel wertet eine Auswahl, deren
Quelle leer ist, nicht als Fehler – neue Zeilen funktionieren also sofort.
"""
import os
import sys
from datetime import date, datetime

from openpyxl import load_workbook, Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

HIER = os.path.dirname(os.path.abspath(__file__))
VORLAGE = os.path.join(HIER, 'vorlagen', 'termine_modell2.xlsx')

# ── Inhalt der Auswahllisten ────────────────────────────────────────────────
ARTEN = ['Kalibrierung', 'Wartung', 'Ausfall', 'Audit', 'Info']
STATUS = ['offen', 'abgeschlossen', 'storniert']

PRUEFSTAENDE = [
    ('P01', 'NRA'),
    ('P02', 'NRA'),
    ('P03', 'NRA'),
    ('P04', 'NRA'),
    ('P06', 'EHSV NRA'),
    ('P07', 'EHSV NRA'),
    ('P10', 'PTU TESTFUCHS'),
    ('P11', 'PUMO HYCOM'),
    ('P12', 'PUMO TESTFUCHS'),
    ('P20', 'THRUST-REVERSER'),
    ('P21', 'NRC HYCOM'),
    ('P31', 'THSA'),
    ('P40', 'AKKU/HOCHDRUCK-RAUM'),
    ('P41', 'MIL'),
    ('P43', 'LOW-PRESSURE'),
]

# ── Die vorhandenen Zeilen (Datenbestand der Vorlage) ───────────────────────
# Blatt „Termine“ ist tagesgenau: nur Datum, keine Uhrzeit. Uhrzeiten gehören
# ausschließlich ins Blatt „Zeiten“ - sonst gäbe es zwei Orte für dieselbe
# Angabe, und niemand wüsste, welcher gilt.
TERMINE = [
    (1, 'Wartung', 'P03 NRA', date(2026, 11, 2), date(2026, 11, 2),
     'Jahreswartung Hydraulik', 'abgeschlossen'),
    (2, 'Kalibrierung', 'P10 PTU TESTFUCHS', date(2026, 11, 16), date(2026, 11, 21),
     'Kalibrierung Druckmessung, unterbrochen', 'abgeschlossen'),
    (3, 'Ausfall', 'P21 NRC HYCOM', date(2026, 11, 18), date(2026, 11, 19),
     'Steuerung ausgefallen, Ersatzteil', 'offen'),
    (4, 'Kalibrierung', 'P31 THSA', date(2026, 11, 24), date(2026, 11, 24),
     'Halbtag, Rest des Tages freigegeben', 'offen'),
    (5, 'Audit', 'P40 AKKU/HOCHDRUCK-RAUM', date(2026, 11, 27), date(2026, 11, 27),
     'interner Audit', 'offen'),
    (6, 'Info', 'P07 EHSV NRA', date(2026, 12, 1), None,
     'Hinweis Software-Update', 'offen'),
]

# Blatt „Zeiten“: hier stehen die Uhrzeiten. Ein Block je Zeitraum, in dem
# tatsaechlich gearbeitet wurde. Fehlt ein Block, gilt der Termin als
# durchgehend ausser Betrieb.
ZEITEN = [
    # Ein halber Tag: der Termin steht im Blatt „Termine“ als ganzer Tag,
    # die tatsaechliche Arbeitszeit steht hier.
    (4, datetime(2026, 11, 24, 9, 0), datetime(2026, 11, 24, 13, 0),
     'Halbtag, Rest des Tages freigegeben'),
    (2, datetime(2026, 11, 16, 8, 0), datetime(2026, 11, 16, 12, 0), 'Tag 1, vormittags'),
    (2, datetime(2026, 11, 17, 8, 0), datetime(2026, 11, 17, 16, 0), 'Tag 2, ganztags'),
    (2, datetime(2026, 11, 19, 7, 0), datetime(2026, 11, 19, 11, 0), 'Tag 4, vormittags'),
    (2, datetime(2026, 11, 20, 8, 0), datetime(2026, 11, 20, 14, 0), 'Tag 5, 6 Stunden'),
]

ARCHIV = [
    (7, 'Ausfall', 'P02 NRA', date(2026, 10, 5), date(2026, 10, 7),
     'Kühlmittelverlust, Reparatur', 'abgeschlossen'),
    (8, 'Wartung', 'P41 MIL', date(2026, 10, 12), date(2026, 10, 12),
     'Dichtungen getauscht', 'abgeschlossen'),
]

LETZTE_ZEILE = 500

# ── Legende ─────────────────────────────────────────────────────────────────
# Zwei Spalten Luft, dann eine Legende ausserhalb der Datenspalten. Der Parser
# liest nur die festen Datenspalten (A-F bzw. A-D), die Legende wird also nie
# als Datensatz gelesen - auch dann nicht, wenn jemand die Zeilen verschiebt.
LEGENDE_SPALTE = 8          # Spalte H
LEGENDE_START = 2           # ab Zeile 2


def _legende(ws, eintraege, beschriftung):
    """Schreibt eine Legende rechts neben die Datenspalten."""
    trennspalte = LEGENDE_SPALTE - 1
    ws.column_dimensions[chr(64 + trennspalte)].width = 3
    ws.column_dimensions[chr(64 + LEGENDE_SPALTE)].width = 13
    ws.column_dimensions[chr(65 + LEGENDE_SPALTE)].width = 34

    zelle = ws.cell(row=1, column=LEGENDE_SPALTE, value=beschriftung)
    zelle.font = Font(bold=True, italic=True, color='808080')

    for nummer, (beispiel, bedeutung) in enumerate(eintraege):
        zeile = LEGENDE_START + nummer
        zelle = ws.cell(row=zeile, column=LEGENDE_SPALTE, value=beispiel)
        zelle.font = Font(italic=True, color='808080')
        zelle.alignment = Alignment(horizontal='right')
        ws.cell(row=zeile, column=LEGENDE_SPALTE + 1,
                value=bedeutung).font = Font(color='808080')


def _kopf(ws, titel, breiten):
    ws.append(titel)
    for spalte, breite in enumerate(breiten, start=1):
        zelle = ws.cell(row=1, column=spalte)
        zelle.font = Font(bold=True)
        zelle.alignment = Alignment(horizontal='center', vertical='center')
        ws.column_dimensions[chr(64 + spalte)].width = breite
    ws.freeze_panes = 'A2'


def _auswahl(ws, formel, bereich, hinweis='', titel='Auswahl'):
    dv = DataValidation(type='list', formula1=formel, allow_blank=True,
                        showDropDown=False)
    dv.error = 'Bitte einen Wert aus der Liste wählen.'
    dv.errorTitle = 'Ungültiger Wert'
    if hinweis:
        dv.prompt = hinweis
        dv.promptTitle = titel
    ws.add_data_validation(dv)
    dv.add(bereich)


def _datumsformat(ws, spalten, mit_zeit=True):
    for zeile in range(2, LETZTE_ZEILE + 1):
        for spalte in spalten:
            ws.cell(row=zeile, column=spalte).number_format = (
                'DD.MM.YYYY HH:MM' if mit_zeit else 'DD.MM.YYYY')


def baue_vorlage(pfad=VORLAGE):
    wb = Workbook()

    # ── Blatt „Termine" ────────────────────────────────────────────────────
    ws = wb.active
    ws.title = 'Termine'
    _kopf(ws, ['Nr', 'Art', 'Prüfstand', 'Von', 'Bis', 'Info', 'Status'],
          [6, 16, 24, 18, 18, 46, 15])
    for zeile in TERMINE:
        ws.append(list(zeile))
    _datumsformat(ws, (4, 5), mit_zeit=False)
    _auswahl(ws, '"%s"' % ','.join(ARTEN), 'B2:B%d' % LETZTE_ZEILE,
             'Art des Termins wählen.', 'Art')
    _auswahl(ws, '=Pruefstaende', 'C2:C%d' % LETZTE_ZEILE,
             'Prüfstand aus dem Blatt „Prüfstände“ wählen.', 'Prüfstand')
    _auswahl(ws, '"%s"' % ','.join(STATUS), 'G2:G%d' % LETZTE_ZEILE,
             'offen / abgeschlossen / storniert.', 'Status')
    _legende(ws, [
        ('1', 'Wartung, erledigt'),
        ('2', 'Kalibrierung über mehrere Tage –'),
        ('', 'Zeitblöcke im Blatt „Zeiten“'),
        ('6', 'Info – „Bis“ darf leer bleiben'),
        ('', ''),
        ('Von / Bis', 'nur Datum, keine Uhrzeit'),
        ('', ''),
        ('Art', 'Kalibrierung / Wartung /'),
        ('', 'Ausfall / Audit / Info'),
        ('Prüfstand', 'Reihenfolge: erst mit'),
        ('', 'Dropdown wählen – falsche'),
        ('', 'Namen zählen nicht'),
    ], 'Beispiel')
    ws.sheet_view.showGridLines = True

    # ── Blatt „Zeiten" ─────────────────────────────────────────────────────
    ws = wb.create_sheet('Zeiten')
    _kopf(ws, ['Termin (Nr)', 'Von', 'Bis', 'Notiz'], [13, 18, 18, 40])
    for zeile in ZEITEN:
        ws.append(list(zeile))
    _datumsformat(ws, (2, 3))
    _auswahl(ws, '=Termine!$A$2:$A$%d' % LETZTE_ZEILE, 'A2:A%d' % LETZTE_ZEILE,
             'Nummer des Termins aus dem Blatt „Termine“.', 'Termin')
    _legende(ws, [
        ('4', 'Halbtag: 09:00–13:00'),
        ('2', 'erster Block einer mehrtägigen'),
        ('', 'Kalibrierung'),
        ('', ''),
        ('Uhrzeiten', 'gehören ausschließlich'),
        ('', 'in dieses Blatt'),
        ('', ''),
        ('Kein Eintrag', 'Prüfstand war durchgehend'),
        ('', 'außer Betrieb'),
    ], 'Beispiel')

    # ── Blatt „Prüfstände" ─────────────────────────────────────────────────
    ws = wb.create_sheet('Prüfstände')
    _kopf(ws, ['Kennung', 'Bezeichnung', 'Auswahl (für Dropdown)'], [12, 28, 28])
    for kennung, bezeichnung in PRUEFSTAENDE:
        ws.append([kennung, bezeichnung, '%s %s' % (kennung, bezeichnung)])

    wb.defined_names['Pruefstaende'] = DefinedName(
        'Pruefstaende', attr_text="'Prüfstände'!$C$2:$C$%d" % (len(PRUEFSTAENDE) + 1))

    # ── Blatt „Archiv" ─────────────────────────────────────────────────────
    ws = wb.create_sheet('Archiv')
    _kopf(ws, ['Nr', 'Art', 'Prüfstand', 'Von', 'Bis', 'Info', 'Status'],
          [6, 16, 24, 18, 18, 46, 15])
    for zeile in ARCHIV:
        ws.append(list(zeile))
    _datumsformat(ws, (4, 5), mit_zeit=False)
    # Archiv ist sonst nur lesend - die Listen helfen beim Nachtragen von Hand.
    _auswahl(ws, '"%s"' % ','.join(ARTEN), 'B2:B%d' % LETZTE_ZEILE,
             'Art des Termins wählen.', 'Art')
    _auswahl(ws, '=Pruefstaende', 'C2:C%d' % LETZTE_ZEILE,
             'Prüfstand aus dem Blatt „Prüfstände“ wählen.', 'Prüfstand')
    _auswahl(ws, '"%s"' % ','.join(STATUS), 'G2:G%d' % LETZTE_ZEILE,
             'offen / abgeschlossen / storniert.', 'Status')

    _anleitung(wb.create_sheet('Anleitung'))

    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    wb.save(pfad)
    return pfad


def _anleitung(ws):
    """Blatt „Anleitung" – der Text der bisherigen Vorlage, plus Drop-Down-Hinweis."""
    ws.column_dimensions['B'].width = 96

    zeilen = [
        ('titel', 'Terminübersicht – so wird sie ausgefüllt'),
        ('leer', ''),
        ('kopf', 'Blatt „Termine“ – hier wird alles eingetragen'),
        ('text', 'A  Nr        – fortlaufende Nummer, wird für das Blatt „Zeiten“ gebraucht'),
        ('text', 'B  Art       – Auswahl: %s' % ' / '.join(ARTEN)),
        ('text', 'C  Prüfstand – Auswahl aus der Liste (Blatt „Prüfstände“)'),
        ('text', 'D  Von       – nur Datum, z. B. 16.11.2026'),
        ('text', 'E  Bis       – nur Datum, bei „Info“ darf das Feld leer bleiben'),
        ('text', '              Uhrzeiten gehören NICHT hierher, sondern ins Blatt „Zeiten“.'),
        ('text', 'F  Info      – kurze Beschreibung'),
        ('text', 'G  Status    – %s' % ' / '.join(STATUS)),
        ('leer', ''),
        ('tipp', 'Die Spalten Art, Prüfstand, Status und Termin-Nr haben ein Drop-Down:'),
        ('tipp', 'in die Zelle klicken, dann rechts am Zellrand auf den Pfeil klicken.'),
        ('tipp', 'So kann kein Tippfehler und kein unbekannter Prüfstand entstehen.'),
        ('leer', ''),
        ('kopf', 'Blatt „Zeiten“ – hier stehen die Uhrzeiten'),
        ('text', 'Das Blatt „Termine“ kennt nur ganze Tage. Sobald eine Uhrzeit eine Rolle'),
        ('text', 'spielt, wird sie hier eingetragen – als Zeitraum mit Von und Bis.'),
        ('text', 'Ein Termin kann mehrere Zeilen haben (z. B. eine Kalibrierung, die über'),
        ('text', 'mehrere Tage läuft, aber täglich nur vormittags).'),
        ('leer', ''),
        ('kopf', 'Wann ist das Blatt „Zeiten“ nötig?'),
        ('text', 'Nur wenn der Prüfstand NICHT durchgehend außer Betrieb ist.'),
        ('text', 'Beispiel: Kalibrierung von Montag bis Samstag, aber täglich nur 4–8 Stunden,'),
        ('text', 'und zwischendurch zwei Tage gar nicht.'),
        ('leer', ''),
        ('text', 'Dann für jeden Zeitraum, in dem wirklich gearbeitet wurde, eine Zeile:'),
        ('text', '   Termin-Nr | Von | Bis | Notiz'),
        ('leer', ''),
        ('text', 'Kein Eintrag im Blatt „Zeiten“ = Prüfstand war durchgehend außer Betrieb.'),
        ('text', 'Bei Wartung und Ausfall ist das der Normalfall – das Blatt bleibt dann leer.'),
        ('leer', ''),
        ('kopf', 'Status'),
        ('text', 'offen         – Termin läuft bzw. steht noch aus, wird am Kiosk angezeigt'),
        ('text', 'abgeschlossen – erledigt, geht in die Historie und in die Ausfallstatistik'),
        ('text', 'storniert     – versehentlich eingetragen, zählt NICHT als Ausfall'),
        ('leer', ''),
        ('kopf', 'Nach dem Abschluss'),
        ('text', 'Abgeschlossene Zeilen aus „Termine“ in das Blatt „Archiv“ verschieben.'),
        ('text', 'Die Historie bleibt im Gerät erhalten, auch wenn die Zeile hier verschwindet.'),
        ('leer', ''),
        ('kopf', 'Neue Prüfstände'),
        ('text', 'Im Blatt „Prüfstände“ unten eine Zeile ergänzen (Kennung, Bezeichnung, Auswahl).'),
        ('text', 'Das Dropdown im Blatt „Termine“ zieht automatisch nach.'),
        ('leer', ''),
        ('kopf', 'Beispiele'),
        ('text', 'Die Zeilen in dieser Vorlage sind Muster zum Ansehen. Vor dem ersten'),
        ('text', 'echten Eintrag löschen – sonst werden sie als echte Termine importiert.'),
    ]
    for art, text in zeilen:
        ws.append([None, text or None])
        zelle = ws.cell(row=ws.max_row, column=2)
        if art == 'titel':
            zelle.font = Font(bold=True, size=14)
        elif art == 'kopf':
            zelle.font = Font(bold=True, size=11)
        elif art == 'tipp':
            zelle.font = Font(italic=True)


def _quote_entfernen(formel):
    return str(formel).strip().strip('=').strip('"')


def pruefe(pfad=VORLAGE):
    """Prüft, ob alle Drop-Downs vorhanden sind und auf gültige Quellen zeigen."""
    wb = load_workbook(pfad)
    fehler = []

    def listen_von(blatt):
        gefunden = {}
        for dv in wb[blatt].data_validations.dataValidation:
            for bereich in str(dv.sqref).split():
                gefunden[bereich[0]] = dv.formula1
        return gefunden

    for blatt in ('Termine', 'Archiv'):
        gefunden = listen_von(blatt)
        for spalte, muss in (('B', ARTEN), ('C', 'Pruefstaende'), ('G', STATUS)):
            if spalte not in gefunden:
                fehler.append('%s!%s hat kein Drop-Down' % (blatt, spalte))
            elif spalte == 'C':
                if _quote_entfernen(gefunden[spalte]) != muss:
                    fehler.append('%s!C zeigt auf %r statt %r' % (blatt, gefunden[spalte], muss))
            else:
                werte = [w.strip() for w in _quote_entfernen(gefunden[spalte]).split(',')]
                if werte != muss:
                    fehler.append('%s!%s: %r statt %r' % (blatt, spalte, werte, muss))

    if 'A' not in listen_von('Zeiten'):
        fehler.append('Zeiten!A hat kein Drop-Down')

    if 'Pruefstaende' not in wb.defined_names:
        fehler.append('Bereichsname Pruefstaende fehlt')
    elif 'Prüfstände' not in wb.defined_names['Pruefstaende'].attr_text:
        fehler.append('Pruefstaende zeigt auf %r'
                      % wb.defined_names['Pruefstaende'].attr_text)

    return fehler


if __name__ == '__main__':
    if '--pruefen' in sys.argv:
        maengel = pruefe()
        if maengel:
            print('MÄNGEL:')
            for m in maengel:
                print('  -', m)
            sys.exit(1)
        print('Vorlage in Ordnung: alle Drop-Downs vorhanden.')
    else:
        ziel = baue_vorlage()
        maengel = pruefe(ziel)
        print('Vorlage geschrieben:', ziel)
        if maengel:
            print('MÄNGEL:')
            for m in maengel:
                print('  -', m)
            sys.exit(1)
        print('Prüfung bestanden: Drop-Downs für Art, Prüfstand, Status und Termin-Nr.')
