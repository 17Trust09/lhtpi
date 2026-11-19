"""Erzeugt die Excel-Vorlage „Modell 3" neu.

Warum ein Skript statt einer gepflegten Binärdatei: Jede Änderung an Spalten,
Auswahllisten oder Blättern ist im Code nachvollziehbar, und die Vorlage kann
jederzeit identisch (deterministisch) wiederhergestellt werden.

Aufruf:
    python3 tools_vorlage_modell3_bauen.py            # schreibt die Vorlage neu
    python3 tools_vorlage_modell3_bauen.py --pruefen  # prüft die Vorlage

Blätter:
  * ``Termine``            – Nr | Art | Typ | Betriebsmittel | Von | Bis | Info
                             | Status | Betriebsmittel-ID (Spalte I, ausgeblendet)
  * ``News & Audits``      – Nr | Art | Titel | Von | Bis | Info | Status
  * ``Betriebsmittel``     – ID | Typ | Bezeichnung | Zusammenführen mit | Hinweis
  * ``Zeiten``             – Termin-Nr. | Von | Bis | Notiz
  * ``Archiv Termine``     – Schema wie ``Termine``
  * ``Archiv News & Audits`` – Schema wie ``News & Audits``
  * ``Anleitung``          – deutsche Bedienhinweise

Die Nummern-Spalten (T-001…T-500, N-001…N-500) und die ID-Spalte des Blatts
„Betriebsmittel" sind vorausgefüllt und per Blattschutz gesperrt (nur
Bedienkomfort, kein Sicherheitsmerkmal). Die ausgeblendete Betriebsmittel-ID
(Spalte I) wird per INDEX/VERGLEICH automatisch aus dem gewählten Namen
ermittelt. Bereichsnamen reichen bis Zeile 501 (Zeilen 2:501).
"""
import os
import re
import sys
import zipfile
from datetime import datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

from tools_vorlage_bauen import PRUEFSTAENDE as MODEL2_PRUEFSTAENDE

HIER = os.path.dirname(os.path.abspath(__file__))
VORLAGE = os.path.join(HIER, 'vorlagen', 'termine_modell3.xlsx')

# ── Wertemengen ──────────────────────────────────────────────────────────────
ARTEN_TERMINE = ['Kalibrierung', 'Wartung', 'Ausfall']
ARTEN_NEWS = ['Audit', 'Info']
TYPEN = ['Prüfstand', 'Konsole']
STATUS = ['offen', 'abgeschlossen']

# ── Stammdaten Betriebsmittel ────────────────────────────────────────────────
# Prüfstände aus Modell 2 unverändert übernehmen (exakt gleiche Auswahlnamen),
# damit vorhandene Zeilen weiterhin zum Drop-Down passen. Konsolen ergänzen.
# Neue Zeilen dürfen eine leere ID haben (wird später vom Gerät vergeben).
KONSOLEN = ['TESTFUCHS KONSOLE 1', 'TESTFUCHS KONSOLE 2']


def _modell2_auswahlname(eintrag):
    return eintrag[2] if len(eintrag) > 2 else '%s %s' % (eintrag[0], eintrag[1])


BETRIEBSMITTEL = [
    ('BM-%03d' % i, typ, name)
    for i, (name, typ) in enumerate(
        [(_modell2_auswahlname(e), 'Prüfstand') for e in MODEL2_PRUEFSTAENDE]
        + [(k, 'Konsole') for k in KONSOLEN],
        start=1)
]

LETZTE_ZEILE = 500          # Datenzeilen 2…501

# Fester Zeitstempel für ZIP-Einträge – macht die Ausgabedatei reproduzierbar.
FESTE_ZEIT = (1980, 1, 1, 0, 0, 0)
FESTE_ZEIT_ISO = '2020-01-01T00:00:00Z'


def _speichern(wb, pfad):
    """Speichert die Arbeitsmappe byte-deterministisch.

    openpyxl schreibt die Erstellungs-/Änderungszeit (``docProps/core.xml``) und
    die Zeitstempel der ZIP-Einträge mit der aktuellen Uhrzeit – und überschreibt
    dabei ``modified`` beim Speichern erneut mit ``now()`` (siehe
    ``openpyxl/writer/excel.py``). Für eine reproduzierbare Vorlage werden deshalb
    sowohl die ZIP-Zeitstempel als auch ``created``/``modified`` in der XML auf
    feste Werte gesetzt.
    """
    wb.properties.created = datetime(2020, 1, 1)
    wb.properties.modified = datetime(2020, 1, 1)
    wb.save(pfad)
    tmp = pfad + '.tmp'
    fest = FESTE_ZEIT_ISO.encode('utf-8')
    with zipfile.ZipFile(pfad, 'r') as zin:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                daten = zin.read(info.filename)
                if info.filename == 'docProps/core.xml':
                    for feld in (b'created', b'modified'):
                        daten = re.sub(
                            rb'(<dcterms:%s xsi:type="dcterms:W3CDTF">)'
                            rb'[^<]*(</dcterms:%s>)' % (feld, feld),
                            lambda m: m.group(1) + fest + m.group(2),
                            daten)
                info.date_time = FESTE_ZEIT
                zout.writestr(info, daten)
    os.replace(tmp, pfad)

KOPF_TERMINE = ['Nr', 'Art', 'Typ', 'Betriebsmittel', 'Von', 'Bis', 'Info',
                'Status', 'Betriebsmittel-ID']
KOPF_NEWS = ['Nr', 'Art', 'Titel', 'Von', 'Bis', 'Info', 'Status']
KOPF_BM = ['ID', 'Typ', 'Bezeichnung', 'Zusammenführen mit', 'Hinweis']
KOPF_ZEITEN = ['Termin-Nr.', 'Von', 'Bis', 'Notiz']

# Farben für den Status: offen = stillstehend (rot), abgeschlossen = erledigt
# (grün).
STATUS_FARBEN = {
    'offen': ('FFC7CE', '9C0006'),
    'abgeschlossen': ('C6EFCE', '006100'),
}


def _kopf(ws, titel, breiten):
    ws.append(titel)
    for spalte, breite in enumerate(breiten, start=1):
        zelle = ws.cell(row=1, column=spalte)
        zelle.font = Font(bold=True)
        zelle.alignment = Alignment(horizontal='center', vertical='center')
        ws.column_dimensions[chr(64 + spalte)].width = breite
    ws.freeze_panes = 'A2'


def _auswahl(ws, formel, bereich, hinweis='', titel='Auswahl'):
    # showDropDown=False heißt „Pfeil zeigen“ (das OOXML-Attribut bedeutet
    # „Dropdown unterdrücken“). showErrorMessage + errorStyle='stop' blockieren
    # ungültige manuelle Eingaben; showInputMessage zeigt den Hinweis (prompt).
    dv = DataValidation(type='list', formula1=formel, allow_blank=True,
                        showErrorMessage=True, showInputMessage=True,
                        showDropDown=False, errorStyle='stop')
    dv.error = 'Bitte einen Wert aus der Liste wählen.'
    dv.errorTitle = 'Ungültiger Wert'
    if hinweis:
        dv.prompt = hinweis
        dv.promptTitle = titel
    ws.add_data_validation(dv)
    dv.add(bereich)


def _status_farben(ws, spalte, letzte_zeile=LETZTE_ZEILE):
    from openpyxl.formatting.rule import CellIsRule

    bereich = '%s2:%s%d' % (spalte, spalte, letzte_zeile + 1)
    for wert, (fuellung, schrift) in STATUS_FARBEN.items():
        ws.conditional_formatting.add(
            bereich,
            CellIsRule(operator='equal', formula=['"%s"' % wert],
                       fill=PatternFill('solid', start_color=fuellung,
                                        end_color=fuellung),
                       font=Font(color=schrift, bold=(wert == 'offen'))))


def _datumsformat(ws, spalten, mit_zeit=True):
    for zeile in range(2, LETZTE_ZEILE + 2):
        for spalte in spalten:
            ws.cell(row=zeile, column=spalte).number_format = (
                'DD.MM.YYYY HH:MM' if mit_zeit else 'DD.MM.YYYY')


def _nummerspalte(ws, praefix):
    for zeile in range(2, LETZTE_ZEILE + 2):
        ws.cell(row=zeile, column=1, value='%s-%03d' % (praefix, zeile - 1))


def _bm_id_formel(ws, buchstabe='D'):
    """INDEX/VERGLEICH: ausgeblendete ID aus dem gewählten Namen ableiten."""
    for zeile in range(2, LETZTE_ZEILE + 2):
        ws.cell(row=zeile, column=9, value=(
            '=IF(%s%d="","",IFERROR(INDEX(BetriebsmittelIDs,'
            'MATCH(%s%d,BetriebsmittelNamen,0)),""))' % (buchstabe, zeile,
                                                          buchstabe, zeile)))


def _schuetze(ws, spalten, nummer_gesperrt=True, bm_id_gesperrt=False):
    """Blattschutz: alles entsperren, gezielt Nummer-/ID-Spalte wieder sperren.

    Reiner Bedienkomfort – der Schutz ist ohne Passwort und damit keine
    Sicherheitsgrenze.
    """
    for zeile in range(2, LETZTE_ZEILE + 2):
        for spalte in range(1, spalten + 1):
            ws.cell(row=zeile, column=spalte).protection = Protection(locked=False)
    if nummer_gesperrt:
        for zeile in range(2, LETZTE_ZEILE + 2):
            ws.cell(row=zeile, column=1).protection = Protection(locked=True)
    if bm_id_gesperrt:
        for zeile in range(2, LETZTE_ZEILE + 2):
            ws.cell(row=zeile, column=9).protection = Protection(locked=True)
    ws.protection.sheet = True


def _termin_schema(ws):
    """Spalten, Dropdowns und Schutz für ein Termine-Schema-Blatt."""
    _kopf(ws, KOPF_TERMINE, [9, 14, 12, 26, 12, 12, 42, 14, 16])
    _nummerspalte(ws, 'T')
    ws.column_dimensions['I'].hidden = True
    _bm_id_formel(ws, 'D')
    _datumsformat(ws, (5, 6), mit_zeit=False)

    _auswahl(ws, '"%s"' % ','.join(ARTEN_TERMINE), 'B2:B%d' % (LETZTE_ZEILE + 1),
             'Art des Termins wählen.', 'Art')
    _auswahl(ws, '"%s"' % ','.join(TYPEN), 'C2:C%d' % (LETZTE_ZEILE + 1),
             'Typ des Betriebsmittels wählen.', 'Typ')
    _auswahl(ws, '=BetriebsmittelNamen', 'D2:D%d' % (LETZTE_ZEILE + 1),
             'Betriebsmittel aus dem Blatt „Betriebsmittel“ wählen.',
             'Betriebsmittel')
    _auswahl(ws, '"%s"' % ','.join(STATUS), 'H2:H%d' % (LETZTE_ZEILE + 1),
             'offen / abgeschlossen.', 'Status')
    _status_farben(ws, 'H')
    _schuetze(ws, 9, nummer_gesperrt=True, bm_id_gesperrt=True)


def _news_schema(ws):
    """Spalten, Dropdowns und Schutz für ein News-Schema-Blatt."""
    _kopf(ws, KOPF_NEWS, [9, 12, 34, 12, 12, 42, 14])
    _nummerspalte(ws, 'N')
    _datumsformat(ws, (4, 5), mit_zeit=False)

    _auswahl(ws, '"%s"' % ','.join(ARTEN_NEWS), 'B2:B%d' % (LETZTE_ZEILE + 1),
             'Art des Eintrags wählen.', 'Art')
    _auswahl(ws, '"%s"' % ','.join(STATUS), 'G2:G%d' % (LETZTE_ZEILE + 1),
             'offen / abgeschlossen.', 'Status')
    _status_farben(ws, 'G')
    _schuetze(ws, 7, nummer_gesperrt=True)


def _anleitung(ws):
    ws.column_dimensions['B'].width = 96

    zeilen = [
        ('titel', 'Terminübersicht (Modell 3) – so wird sie ausgefüllt'),
        ('leer', ''),
        ('kopf', 'Blatt „Termine“ – hier werden Termine eingetragen'),
        ('text', 'A  Nr              – T-001 … T-500, bereits vorausgefüllt und gesperrt'),
        ('text', 'B  Art             – Auswahl: %s' % ' / '.join(ARTEN_TERMINE)),
        ('text', 'C  Typ             – Auswahl: %s' % ' / '.join(TYPEN)),
        ('text', 'D  Betriebsmittel  – Auswahl aus dem Blatt „Betriebsmittel“'),
        ('text', 'E  Von             – nur Datum, z. B. 16.11.2026 (Tagesbeginn)'),
        ('text', 'F  Bis             – nur Datum (Tagesende); leer = endet am selben Tag'),
        ('text', 'G  Info            – kurze Beschreibung'),
        ('text', 'H  Status          – %s' % ' / '.join(STATUS)),
        ('text', 'I  Betriebsmittel-ID – ausgeblendet, wird automatisch ermittelt'),
        ('leer', ''),
        ('kopf', 'Blatt „News & Audits“ – Ankündigungen und Audits'),
        ('text', 'A  Nr    – N-001 … N-500, bereits vorausgefüllt und gesperrt'),
        ('text', 'B  Art   – Auswahl: %s' % ' / '.join(ARTEN_NEWS)),
        ('text', 'C  Titel – Überschrift der Meldung'),
        ('text', 'D  Von   – Datum, ab dem die Meldung gilt'),
        ('text', 'E  Bis   – Datum, bis zu dem die Meldung gilt (darf leer bleiben)'),
        ('text', 'F  Info  – Beschreibung'),
        ('text', 'G  Status – %s' % ' / '.join(STATUS)),
        ('leer', ''),
        ('kopf', 'Blatt „Betriebsmittel“ – Stammdaten'),
        ('text', 'A  ID                – BM-001 …, wird vom Gerät vergeben (gesperrt)'),
        ('text', 'B  Typ               – Auswahl: %s' % ' / '.join(TYPEN)),
        ('text', 'C  Bezeichnung       – eindeutiger Name, z. B. TESTFUCHS KONSOLE 1'),
        ('text', 'D  Zusammenführen mit – BM-Nummer, falls dieses Betriebsmittel'),
        ('text', '                        mit einem anderen zusammengeführt wird'),
        ('text', 'E  Hinweis           – freier Text'),
        ('leer', ''),
        ('text', 'Neue Betriebsmittel unten ergänzen – die ID darf leer bleiben.'),
        ('text', 'Ähnliche Namen wie TESTFUCHS KONSOLE 1 und 2 bleiben getrennt.'),
        ('leer', ''),
        ('kopf', 'Blatt „Zeiten“ – Uhrzeiten (nur für Termine)'),
        ('text', 'Nur wenn ein Prüfstand NICHT durchgehend außer Betrieb ist,'),
        ('text', 'werden hier Zeiträume eingetragen: Termin-Nr. | Von | Bis | Notiz.'),
        ('text', 'Die Termin-Nr. muss eine gültige T-Nummer sein (z. B. T-001).'),
        ('leer', ''),
        ('kopf', 'Archiv'),
        ('text', 'Abgeschlossene Zeilen aus „Termine“ in „Archiv Termine“ verschieben,'),
        ('text', 'abgeschlossene Meldungen aus „News & Audits“ in „Archiv News & Audits“.'),
        ('text', 'Eine Nummer darf nur in genau einem der beiden Blätter vorkommen.'),
        ('leer', ''),
        ('kopf', 'Status'),
        ('text', 'offen          – läuft bzw. steht noch aus, wird am Kiosk angezeigt'),
        ('text', 'abgeschlossen  – erledigt, zählt in die Statistik'),
        ('leer', ''),
        ('kopf', 'Drop-Downs'),
        ('text', 'In die Zelle klicken, dann am Zellrand auf den Pfeil klicken.'),
        ('text', 'So entstehen keine Tippfehler und keine unbekannten Werte.'),
        ('leer', ''),
        ('kopf', 'Beispiele'),
        ('text', 'Diese Vorlage enthält keine Beispiel-Termine – nur vorausgefüllte'),
        ('text', 'Nummern. Vor dem ersten echten Eintrag einfach in die Zeilen schreiben.'),
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


def baue_vorlage(pfad=VORLAGE):
    wb = Workbook()

    # ── Termine ──────────────────────────────────────────────────────────────
    _termin_schema(wb.active)
    wb.active.title = 'Termine'

    # ── News & Audits ────────────────────────────────────────────────────────
    _news_schema(wb.create_sheet('News & Audits'))

    # ── Betriebsmittel ───────────────────────────────────────────────────────
    ws = wb.create_sheet('Betriebsmittel')
    _kopf(ws, KOPF_BM, [10, 12, 28, 22, 40])
    for eintrag in BETRIEBSMITTEL:
        ws.append(list(eintrag) + [None, None])
    _auswahl(ws, '"%s"' % ','.join(TYPEN), 'B2:B%d' % (LETZTE_ZEILE + 1),
             'Typ des Betriebsmittels wählen.', 'Typ')
    _auswahl(ws, '=BetriebsmittelIDs', 'D2:D%d' % (LETZTE_ZEILE + 1),
             'BM-Nummer, mit der zusammengeführt wird.', 'Zusammenführen mit')
    _schuetze(ws, 5, nummer_gesperrt=True)

    # ── Zeiten ───────────────────────────────────────────────────────────────
    ws = wb.create_sheet('Zeiten')
    _kopf(ws, KOPF_ZEITEN, [13, 18, 18, 40])
    _datumsformat(ws, (2, 3))
    _auswahl(ws, '=TermineNr', 'A2:A%d' % (LETZTE_ZEILE + 1),
             'Nummer des Termins aus dem Blatt „Termine“.', 'Termin')
    _schuetze(ws, 4, nummer_gesperrt=False)

    # ── Archiv Termine / Archiv News & Audits ────────────────────────────────
    _termin_schema(wb.create_sheet('Archiv Termine'))
    _news_schema(wb.create_sheet('Archiv News & Audits'))

    _anleitung(wb.create_sheet('Anleitung'))

    # ── Bereichsnamen (Zeilen 2:501) ─────────────────────────────────────────
    wb.defined_names['TermineNr'] = DefinedName(
        'TermineNr', attr_text="'Termine'!$A$2:$A$%d" % (LETZTE_ZEILE + 1))
    wb.defined_names['NewsNr'] = DefinedName(
        'NewsNr', attr_text="'News & Audits'!$A$2:$A$%d" % (LETZTE_ZEILE + 1))
    wb.defined_names['BetriebsmittelNamen'] = DefinedName(
        'BetriebsmittelNamen',
        attr_text="'Betriebsmittel'!$C$2:$C$%d" % (LETZTE_ZEILE + 1))
    wb.defined_names['BetriebsmittelIDs'] = DefinedName(
        'BetriebsmittelIDs',
        attr_text="'Betriebsmittel'!$A$2:$A$%d" % (LETZTE_ZEILE + 1))
    wb.defined_names['ArchivTermineNr'] = DefinedName(
        'ArchivTermineNr',
        attr_text="'Archiv Termine'!$A$2:$A$%d" % (LETZTE_ZEILE + 1))
    wb.defined_names['ArchivNewsNr'] = DefinedName(
        'ArchivNewsNr',
        attr_text="'Archiv News & Audits'!$A$2:$A$%d" % (LETZTE_ZEILE + 1))

    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    _speichern(wb, pfad)
    return pfad


def _quote_entfernen(formel):
    return str(formel).strip().strip('=').strip('"')


def _listen(ws):
    gefunden = {}
    for dv in ws.data_validations.dataValidation:
        for bereich in str(dv.sqref).split():
            spalte = ''.join(c for c in bereich.split(':')[0] if c.isalpha())
            gefunden[spalte] = dv.formula1
    return gefunden


def _pruefe_liste(ws, blatt, spalte, muss, fehler):
    gefunden = _listen(ws)
    if spalte not in gefunden:
        fehler.append('%s!%s hat kein Drop-Down' % (blatt, spalte))
        return
    werte = [w.strip() for w in _quote_entfernen(gefunden[spalte]).split(',')]
    if werte != muss:
        fehler.append('%s!%s: %r statt %r' % (blatt, spalte, werte, muss))


def _pruefe_quelle(ws, blatt, spalte, muss, fehler):
    gefunden = _listen(ws)
    if spalte not in gefunden:
        fehler.append('%s!%s hat kein Drop-Down' % (blatt, spalte))
    elif _quote_entfernen(gefunden[spalte]) != muss:
        fehler.append('%s!%s zeigt auf %r statt %r'
                      % (blatt, spalte, gefunden[spalte], muss))


def pruefe(pfad=VORLAGE):
    """Lädt die Vorlage neu und prüft Blätter, Bereiche, Dropdowns und IDs."""
    wb = load_workbook(pfad)
    fehler = []

    erwartete = ['Termine', 'News & Audits', 'Betriebsmittel', 'Zeiten',
                 'Archiv Termine', 'Archiv News & Audits', 'Anleitung']
    for name in erwartete:
        if name not in wb.sheetnames:
            fehler.append('Blatt %s fehlt' % name)

    bereiche = {
        'TermineNr': "'Termine'!$A$2:$A$501",
        'NewsNr': "'News & Audits'!$A$2:$A$501",
        'BetriebsmittelNamen': "'Betriebsmittel'!$C$2:$C$501",
        'BetriebsmittelIDs': "'Betriebsmittel'!$A$2:$A$501",
        'ArchivTermineNr': "'Archiv Termine'!$A$2:$A$501",
        'ArchivNewsNr': "'Archiv News & Audits'!$A$2:$A$501",
    }
    for name, muster in bereiche.items():
        if name not in wb.defined_names:
            fehler.append('Bereichsname %s fehlt' % name)
        elif muster not in wb.defined_names[name].attr_text:
            fehler.append('%s zeigt auf %r' % (name, wb.defined_names[name].attr_text))

    # Dropdowns je Blatt/Spalte
    for blatt in ('Termine', 'Archiv Termine'):
        _pruefe_liste(wb[blatt], blatt, 'B', ARTEN_TERMINE, fehler)
        _pruefe_liste(wb[blatt], blatt, 'C', TYPEN, fehler)
        _pruefe_quelle(wb[blatt], blatt, 'D', 'BetriebsmittelNamen', fehler)
        _pruefe_liste(wb[blatt], blatt, 'H', STATUS, fehler)
    for blatt in ('News & Audits', 'Archiv News & Audits'):
        _pruefe_liste(wb[blatt], blatt, 'B', ARTEN_NEWS, fehler)
        _pruefe_liste(wb[blatt], blatt, 'G', STATUS, fehler)
    _pruefe_quelle(wb['Zeiten'], 'Zeiten', 'A', 'TermineNr', fehler)
    _pruefe_liste(wb['Betriebsmittel'], 'Betriebsmittel', 'B', TYPEN, fehler)
    _pruefe_quelle(wb['Betriebsmittel'], 'Betriebsmittel', 'D',
                   'BetriebsmittelIDs', fehler)

    # Jede Auswahlliste muss ungültige Eingaben blockieren (showErrorMessage +
    # errorStyle='stop'), den Hinweis zeigen (showInputMessage) und den Pfeil
    # anzeigen (showDropDown=False – OOXML „suppress dropdown“).
    for name in wb.sheetnames:
        for dv in wb[name].data_validations.dataValidation:
            if dv.showErrorMessage is not True:
                fehler.append('%s (%s): showErrorMessage fehlt' % (name, dv.sqref))
            if dv.showInputMessage is not True:
                fehler.append('%s (%s): showInputMessage fehlt' % (name, dv.sqref))
            if dv.showDropDown is not False:
                fehler.append('%s (%s): showDropDown muss False sein'
                              % (name, dv.sqref))
            if dv.errorStyle != 'stop':
                fehler.append('%s (%s): errorStyle muss stop sein'
                              % (name, dv.sqref))

    # Vorausgefüllte Nummern: eindeutig und lückenlos.
    for blatt, praefix in (('Termine', 'T'), ('News & Audits', 'N'),
                           ('Archiv Termine', 'T'), ('Archiv News & Audits', 'N')):
        ids = [wb[blatt].cell(row=r, column=1).value for r in range(2, 502)]
        erwartet = ['%s-%03d' % (praefix, i) for i in range(1, 501)]
        if ids != erwartet:
            fehler.append('%s!A: Nummern nicht vorausgefüllt/eindeutig' % blatt)

    # Ausgeblendete Betriebsmittel-ID (Spalte I).
    for blatt in ('Termine', 'Archiv Termine'):
        if not wb[blatt].column_dimensions['I'].hidden:
            fehler.append('%s!I ist nicht ausgeblendet' % blatt)

    return fehler


if __name__ == '__main__':
    if '--pruefen' in sys.argv:
        maengel = pruefe()
        if maengel:
            print('MÄNGEL:')
            for m in maengel:
                print('  -', m)
            sys.exit(1)
        print('Vorlage in Ordnung: Blätter, Bereiche, Dropdowns und IDs korrekt.')
    else:
        ziel = baue_vorlage()
        maengel = pruefe(ziel)
        print('Vorlage geschrieben:', ziel)
        if maengel:
            print('MÄNGEL:')
            for m in maengel:
                print('  -', m)
            sys.exit(1)
        print('Prüfung bestanden.')
