"""Tests für das Modell-3-Archiv (Termine → Archiv Termine, News → Archiv News)."""
import os

from openpyxl import Workbook, load_workbook

from archiv import verschiebe_modell3, verschiebe_modell3_im_wb

KOPF_T = ['Nr', 'Art', 'Typ', 'Betriebsmittel', 'Von', 'Bis', 'Info', 'Status',
          'Betriebsmittel-ID']
KOPF_N = ['Nr', 'Art', 'Titel', 'Von', 'Bis', 'Info', 'Status']


def _datei(pfad, termine, news=None, archiv_vorbelegt=True):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Termine'
    ws.append(KOPF_T)
    for z in termine:
        ws.append(z)

    nw = wb.create_sheet('News & Audits')
    nw.append(KOPF_N)
    for z in (news or []):
        nw.append(z)

    at = wb.create_sheet('Archiv Termine')
    at.append(KOPF_T)
    an = wb.create_sheet('Archiv News & Audits')
    an.append(KOPF_N)
    if archiv_vorbelegt:
        # Vorausgefüllte Nummern wie in der Vorlage (sonst leer).
        for i in range(2, 12):
            at.cell(row=i, column=1, value='T-%03d' % (i - 1))
            an.cell(row=i, column=1, value='N-%03d' % (i - 1))
    wb.save(pfad)
    return str(pfad)


def _t(nr='T-001', art='Kalibrierung', typ='Prüfstand', bm='P03 NRA',
       von='16.11.2026', bis=None, info='x', status='offen', bm_id=None):
    return [nr, art, typ, bm, von, bis, info, status, bm_id]


def _n(nr='N-001', art='Audit', titel='Audit', von='16.11.2026', bis=None,
       info='', status='offen'):
    return [nr, art, titel, von, bis, info, status]


class TestVerschieben:
    def test_beide_paare_wandern(self, tmp_path):
        pfad = _datei(tmp_path / 't.xlsx', [
            _t(status='abgeschlossen'),
            _t(nr='T-002', art='Wartung', status='offen'),
        ], news=[
            _n(status='abgeschlossen'),
            _n(nr='N-002', status='offen'),
        ])
        ergebnis = verschiebe_modell3(pfad)
        assert sorted(ergebnis['verschoben']) == ['N-001', 'T-001']
        assert ergebnis['fehler'] is None

        wb = load_workbook(pfad)
        termine = [r[0] for r in wb['Termine'].iter_rows(min_row=2, values_only=True) if r[0]]
        news = [r[0] for r in wb['News & Audits'].iter_rows(min_row=2, values_only=True) if r[0]]
        archiv_t = [r[0] for r in wb['Archiv Termine'].iter_rows(min_row=2, values_only=True)
                    if r[0] and any(r[1:])]
        archiv_n = [r[0] for r in wb['Archiv News & Audits'].iter_rows(min_row=2, values_only=True)
                    if r[0] and any(r[1:])]
        assert termine == ['T-002']
        assert news == ['N-002']
        assert archiv_t == ['T-001']
        assert archiv_n == ['N-001']

    def test_nummer_bleibt_erhalten(self, tmp_path):
        pfad = _datei(tmp_path / 't.xlsx', [_t(nr='T-007', status='abgeschlossen')])
        verschiebe_modell3(pfad)
        wb = load_workbook(pfad)
        assert wb['Archiv Termine'].cell(row=2, column=1).value == 'T-007'

    def test_exakte_schema_breite(self, tmp_path):
        # Termine kopiert 9 Spalten (inkl. versteckter BM-ID), News 7 Spalten.
        pfad = _datei(tmp_path / 't.xlsx', [
            _t(status='abgeschlossen', bm_id='BM-001')],
            news=[_n(status='abgeschlossen')])
        verschiebe_modell3(pfad)
        wb = load_workbook(pfad)
        zeile_t = [wb['Archiv Termine'].cell(row=2, column=c).value for c in range(1, 10)]
        assert zeile_t[8] == 'BM-001'
        # Keine 10. Spalte (keine Legende).
        assert wb['Archiv Termine'].max_column == 9
        assert wb['Archiv News & Audits'].max_column == 7

    def test_vorausgefuellte_zeilen_werden_uebersprungen(self, tmp_path):
        pfad = _datei(tmp_path / 't.xlsx', [
            _t(status='abgeschlossen')])
        verschiebe_modell3(pfad)
        # Die abgeschlossene Zeile landet direkt unter der Kopfzeile (Zeile 2),
        # nicht bei Zeile 11 (nach den vorausgefüllten Nummern).
        wb = load_workbook(pfad)
        assert wb['Archiv Termine'].cell(row=2, column=1).value == 'T-001'

    def test_keine_duplikate(self, tmp_path):
        pfad = _datei(tmp_path / 't.xlsx', [_t(status='abgeschlossen')])
        verschiebe_modell3(pfad)
        zweiter = verschiebe_modell3(pfad)
        assert zweiter['verschoben'] == []


class TestTrockenlaufUndSicherung:
    def test_trockenlauf_schreibt_nicht(self, tmp_path):
        pfad = _datei(tmp_path / 't.xlsx', [_t(status='abgeschlossen')])
        ergebnis = verschiebe_modell3(pfad, trocken=True)
        assert ergebnis['verschoben'] == ['T-001']
        wb = load_workbook(pfad)
        termine = [r[0] for r in wb['Termine'].iter_rows(min_row=2, values_only=True) if r[0]]
        assert termine == ['T-001']

    def test_sicherung_wird_angelegt(self, tmp_path):
        pfad = _datei(tmp_path / 't.xlsx', [_t(status='abgeschlossen')])
        ergebnis = verschiebe_modell3(pfad)
        assert ergebnis['sicherung']
        assert os.path.exists(ergebnis['sicherung'])

    def test_fehlende_datei_meldet_fehler(self, tmp_path):
        ergebnis = verschiebe_modell3(str(tmp_path / 'gibtsnicht.xlsx'))
        assert ergebnis['fehler']
        assert ergebnis['verschoben'] == []


class TestImWb:
    def test_in_memory_ohne_speichern(self, tmp_path):
        pfad = _datei(tmp_path / 't.xlsx', [_t(status='abgeschlossen')])
        wb = load_workbook(pfad)
        verschoben = verschiebe_modell3_im_wb(wb)
        assert verschoben == ['T-001']
        # Noch nicht gespeichert – Datei unverändert.
        wb2 = load_workbook(pfad)
        termine = [r[0] for r in wb2['Termine'].iter_rows(min_row=2, values_only=True) if r[0]]
        assert termine == ['T-001']
