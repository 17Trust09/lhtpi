"""parse_termin_xlsx: Modell 3 liefert Termine und News als Anzeige-Dicts."""
from openpyxl import Workbook

from usb_source import parse_termin_xlsx


def _modell3(pfad):
    wb = Workbook()
    bm = wb.active
    bm.title = 'Betriebsmittel'
    bm.append(['ID', 'Typ', 'Bezeichnung', 'Zusammenführen mit', 'Hinweis'])
    bm.append(['BM-001', 'Prüfstand', 'P03 NRA', None, ''])

    ws = wb.create_sheet('Termine')
    ws.append(['Nr', 'Art', 'Typ', 'Betriebsmittel', 'Von', 'Bis', 'Info',
               'Status', 'Betriebsmittel-ID'])
    ws.append(['T-001', 'Kalibrierung', 'Prüfstand', 'P03 NRA',
               '16.11.2026', '21.11.2026', 'Messkette', 'offen', 'BM-001'])

    nw = wb.create_sheet('News & Audits')
    nw.append(['Nr', 'Art', 'Titel', 'Von', 'Bis', 'Info', 'Status'])
    nw.append(['N-001', 'Audit', 'Audit LH', '16.11.2026', None, '', 'offen'])
    wb.save(pfad)
    return str(pfad)


def test_modell3_liefert_termine_und_news(tmp_path):
    pfad = _modell3(tmp_path / 't.xlsx')
    zeilen = parse_termin_xlsx(pfad)
    assert zeilen is not None
    assert len(zeilen) == 2

    termin = [z for z in zeilen if z['referenz']][0]
    assert termin['typ'] == 'kalibrierung'
    assert termin['referenz'] == 'P03 NRA'
    assert termin['start'].isoformat() == '2026-11-16'

    news = [z for z in zeilen if not z['referenz']][0]
    assert news['titel'] == 'Audit LH'
    assert news['typ'] == 'audit'
    assert news['ende'] is None


def test_ausfall_bleibt_ausfall_nicht_info(tmp_path):
    # Regression: 'Ausfall' darf nicht auf 'info' normalisiert werden – es ist
    # ein eigener Typ und wird später links als Termin geroutet.
    wb = Workbook()
    bm = wb.active
    bm.title = 'Betriebsmittel'
    bm.append(['ID', 'Typ', 'Bezeichnung', 'Zusammenführen mit', 'Hinweis'])
    bm.append(['BM-001', 'Prüfstand', 'P03 NRA', None, ''])

    ws = wb.create_sheet('Termine')
    ws.append(['Nr', 'Art', 'Typ', 'Betriebsmittel', 'Von', 'Bis', 'Info',
               'Status', 'Betriebsmittel-ID'])
    ws.append(['T-001', 'Ausfall', 'Prüfstand', 'P03 NRA',
               '16.11.2026', '17.11.2026', 'Defekt', 'offen', 'BM-001'])
    pfad = str(tmp_path / 'ausfall.xlsx')
    wb.save(pfad)

    zeilen = parse_termin_xlsx(pfad)
    assert zeilen[0]['typ'] == 'ausfall'


def test_normalize_type_behaelt_ausfall():
    from usb_source import normalize_type
    assert normalize_type('Ausfall') == 'ausfall'
    assert normalize_type('ausfall') == 'ausfall'


def test_modell2_faellt_weiter_zurueck(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Termine'
    ws.append(['Nr', 'Art', 'Prüfstand', 'Von', 'Bis', 'Info', 'Status'])
    ws.append([1, 'Wartung', 'P03 NRA', '02.11.2026', '02.11.2026',
               'Jahreswartung', 'offen'])
    pfad = str(tmp_path / 'm2.xlsx')
    wb.save(pfad)
    zeilen = parse_termin_xlsx(pfad)
    assert zeilen is not None
    assert zeilen[0]['referenz'] == 'P03 NRA'
