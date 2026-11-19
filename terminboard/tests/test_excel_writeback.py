"""Tests für das sichere Zurückschreiben (excel_writeback)."""
import os

from openpyxl import Workbook, load_workbook

from excel_writeback import wende_an
from excel_modell3 import lies_datei

KOPF_BM = ['ID', 'Typ', 'Bezeichnung', 'Zusammenführen mit', 'Hinweis']
KOPF_T = ['Nr', 'Art', 'Typ', 'Betriebsmittel', 'Von', 'Bis', 'Info', 'Status',
          'Betriebsmittel-ID']
KOPF_N = ['Nr', 'Art', 'Titel', 'Von', 'Bis', 'Info', 'Status']


def _datei(pfad):
    wb = Workbook()
    bm = wb.active
    bm.title = 'Betriebsmittel'
    bm.append(KOPF_BM)
    bm.append(['BM-001', 'Prüfstand', 'P03 NRA', None, ''])
    bm.append([None, 'Konsole', 'NEUE KONSOLE', None, ''])   # leere ID → Zeile 3

    ws = wb.create_sheet('Termine')
    ws.append(KOPF_T)
    ws.append(['T-001', 'Kalibrierung', 'Prüfstand', 'P03 NRA',
               '16.11.2026', None, 'x', 'abgeschlossen', None])
    ws.append(['T-002', 'Wartung', 'Prüfstand', 'P03 NRA',
               '01.12.2026', None, 'y', 'offen', None])

    nw = wb.create_sheet('News & Audits')
    nw.append(KOPF_N)
    nw.append(['N-001', 'Audit', 'Audit LH', '16.11.2026', None, '', 'abgeschlossen'])

    at = wb.create_sheet('Archiv Termine')
    at.append(KOPF_T)
    an = wb.create_sheet('Archiv News & Audits')
    an.append(KOPF_N)
    wb.save(pfad)
    return str(pfad)


WRITEBACK = [
    {'blatt': 'Betriebsmittel', 'excel_zeile': 3, 'kennung': 'BM-002'},
]


class TestWriteback:
    def test_ids_und_archiv_werden_geschrieben(self, tmp_path):
        pfad = _datei(tmp_path / 't.xlsx')
        ergebnis = wende_an(pfad, WRITEBACK)
        assert ergebnis['fehler'] is None
        assert ergebnis['geaendert'] is True
        assert sorted(ergebnis['verschoben']) == ['N-001', 'T-001']

        wb = load_workbook(pfad)
        assert wb['Betriebsmittel'].cell(row=3, column=1).value == 'BM-002'
        # Die ausgeblendete BM-ID-Spalte (I) wird NICHT beschrieben – dort
        # stehen Formeln, die kein statischer Wert zerstören darf.
        assert wb['Archiv Termine'].cell(row=2, column=9).value is None
        termine = [r[0] for r in wb['Termine'].iter_rows(min_row=2, values_only=True) if r[0]]
        assert termine == ['T-002']
        assert wb['Archiv Termine'].cell(row=2, column=1).value == 'T-001'
        assert wb['Archiv News & Audits'].cell(row=2, column=1).value == 'N-001'

    def test_sicherung_wird_angelegt(self, tmp_path):
        pfad = _datei(tmp_path / 't.xlsx')
        ergebnis = wende_an(pfad, WRITEBACK)
        assert ergebnis['sicherung']
        assert os.path.exists(ergebnis['sicherung'])

    def test_datei_bleibt_lesbar(self, tmp_path):
        pfad = _datei(tmp_path / 't.xlsx')
        wende_an(pfad, WRITEBACK)
        daten = lies_datei(pfad)
        assert not any('Datei nicht lesbar' in f.get('grund', '')
                       for f in daten['fehler'])

    def test_zweiter_lauf_aendert_nichts(self, tmp_path):
        pfad = _datei(tmp_path / 't.xlsx')
        wende_an(pfad, WRITEBACK)
        zweiter = wende_an(pfad, WRITEBACK)
        assert zweiter['geaendert'] is False
        assert zweiter['verschoben'] == []

    def test_trockenlauf_schreibt_nicht(self, tmp_path):
        pfad = _datei(tmp_path / 't.xlsx')
        ergebnis = wende_an(pfad, WRITEBACK, trocken=True)
        assert ergebnis['geaendert'] is True     # hätte geändert
        wb = load_workbook(pfad)
        assert wb['Betriebsmittel'].cell(row=3, column=1).value is None
        assert wb['Termine'].cell(row=2, column=9).value is None

    def test_fehlende_datei_meldet_fehler(self, tmp_path):
        ergebnis = wende_an(str(tmp_path / 'gibtsnicht.xlsx'), WRITEBACK)
        assert ergebnis['fehler']

    def test_ohne_aenderungen_bleibt_datei_unberuehrt(self, tmp_path):
        pfad = _datei(tmp_path / 't.xlsx')
        ergebnis = wende_an(pfad, [])
        # Nur die Archivierung läuft (T-001/N-001 sind abgeschlossen).
        assert ergebnis['geaendert'] is True
        assert sorted(ergebnis['verschoben']) == ['N-001', 'T-001']


FORMEL_I = ('=IF(D{zeile}="","",IFERROR(INDEX(BetriebsmittelIDs,'
            'MATCH(D{zeile},BetriebsmittelNamen,0)),""))')


def _datei_mit_formel(pfad):
    """Wie ``_datei``, aber Spalte I von T-001 trägt die INDEX/VERGLEICH-Formel."""
    wb = Workbook()
    bm = wb.active
    bm.title = 'Betriebsmittel'
    bm.append(KOPF_BM)
    bm.append(['BM-001', 'Prüfstand', 'P03 NRA', None, ''])
    bm.append([None, 'Konsole', 'NEUE KONSOLE', None, ''])

    ws = wb.create_sheet('Termine')
    ws.append(KOPF_T)
    ws.append(['T-001', 'Kalibrierung', 'Prüfstand', 'P03 NRA',
               '16.11.2026', None, 'x', 'abgeschlossen', None])
    ws['I2'] = FORMEL_I.format(zeile=2)

    nw = wb.create_sheet('News & Audits')
    nw.append(KOPF_N)
    nw.append(['N-001', 'Audit', 'Audit LH', '16.11.2026', None, '', 'offen'])

    wb.create_sheet('Archiv Termine').append(KOPF_T)
    wb.create_sheet('Archiv News & Audits').append(KOPF_N)
    wb.save(pfad)
    return str(pfad)


class TestFormelSchutz:
    def test_formel_in_i_ueberlebt_writeback_und_archiv(self, tmp_path):
        pfad = _datei_mit_formel(tmp_path / 'formel.xlsx')
        ergebnis = wende_an(pfad, [{'blatt': 'Betriebsmittel', 'excel_zeile': 3,
                                    'kennung': 'BM-002'}])
        assert ergebnis['fehler'] is None
        assert sorted(ergebnis['verschoben']) == ['T-001']

        # Formel bleibt erhalten – kein statischer Wert ersetzt sie.
        wb = load_workbook(pfad)          # data_only=False → Formeln sichtbar
        archiv_i = wb['Archiv Termine'].cell(row=2, column=9).value
        assert isinstance(archiv_i, str) and archiv_i.startswith('=')

        # Nach dem openpyxl-Roundtrip ist der zwischengespeicherte Formelwert
        # weg → der Parser fällt über Name/Typ korrekt zurück (kein Fehler).
        daten = lies_datei(pfad)
        assert daten['termine'] == []
        zeile = daten['archiv_termine'][0]
        assert zeile['betriebsmittel_id'] is None
        assert zeile['betriebsmittel'] == 'P03 NRA'
        assert not any('Betriebsmittel' in f.get('grund', '')
                       for f in daten['fehler'])

    def test_zweiter_lauf_erzeugt_keine_wiederholten_aenderungen(self, tmp_path):
        pfad = _datei_mit_formel(tmp_path / 'formel.xlsx')
        writeback = [{'blatt': 'Betriebsmittel', 'excel_zeile': 3,
                      'kennung': 'BM-002'}]
        wende_an(pfad, writeback)
        zweiter = wende_an(pfad, writeback)
        assert zweiter['geaendert'] is False
        assert zweiter['verschoben'] == []
