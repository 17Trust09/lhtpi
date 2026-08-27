import os
import sys
import tempfile
from datetime import date

# terminboard/-Ordner in den Pfad aufnehmen (vor den Imports)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Isolierte Test-DB, bevor app.py die Env liest
_TMP_DB = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
_TMP_DB.close()
os.environ['TERMINBOARD_DB'] = _TMP_DB.name

from app import app          # noqa: E402
from models import db, Termin  # noqa: E402
import usb_source            # noqa: E402
import routes                # noqa: E402  (registriert die Routen)


def _clean_termine():
    with app.app_context():
        Termin.query.delete()
        db.session.commit()


# ── Datum-Parsing ────────────────────────────────────────────────────

def test_parse_date_dmy():
    assert usb_source.parse_date('25.08.2026') == date(2026, 8, 25)


def test_parse_date_iso():
    assert usb_source.parse_date('2026-08-25') == date(2026, 8, 25)


def test_parse_date_single_digit():
    assert usb_source.parse_date('5.8.2026') == date(2026, 8, 5)


def test_parse_date_invalid():
    assert usb_source.parse_date('31.13.2026') is None
    assert usb_source.parse_date('garbage') is None


def test_parse_date_none_empty():
    assert usb_source.parse_date(None) is None
    assert usb_source.parse_date('') is None
    assert usb_source.parse_date('   ') is None


# ── CSV-Parsing ──────────────────────────────────────────────────────

_CSV = "typ;titel;referenz;start;ende;text\n"


def test_csv_basic():
    text = _CSV + "kalibrierung;Druckprüfstand P3;P3;25.08.2026;30.08.2026;Jährlich\n"
    rows = usb_source.parse_termin_csv(text)
    assert len(rows) == 1
    r = rows[0]
    assert r['typ'] == 'kalibrierung'
    assert r['titel'] == 'Druckprüfstand P3'
    assert r['referenz'] == 'P3'
    assert r['start'] == date(2026, 8, 25)
    assert r['ende'] == date(2026, 8, 30)
    assert r['text'] == 'Jährlich'


def test_csv_iso_dates_and_optional():
    text = _CSV + "audit;ISO-Audit QS;;2026-09-14;;\n"
    rows = usb_source.parse_termin_csv(text)
    assert rows[0]['start'] == date(2026, 9, 14)
    assert rows[0]['ende'] is None
    assert rows[0]['referenz'] is None


def test_csv_skips_comments_blank_and_header():
    text = "# Kommentar\n\n" + _CSV + "info;Meldung;;01.09.2026;;Text\n"
    rows = usb_source.parse_termin_csv(text)
    assert len(rows) == 1
    assert rows[0]['titel'] == 'Meldung'


def test_csv_invalid_typ_falls_back_to_info():
    text = _CSV + "foobar;Titel;;01.09.2026;;\n"
    assert usb_source.parse_termin_csv(text)[0]['typ'] == 'info'


def test_csv_skips_row_without_title():
    text = _CSV + "info;;;01.09.2026;;\n"
    assert usb_source.parse_termin_csv(text) == []


def test_csv_whitespace_stripped():
    text = _CSV + "  wartung  ;  Titel  ;  P1  ;  01.09.2026  ;   ;  Note  \n"
    r = usb_source.parse_termin_csv(text)[0]
    assert r['typ'] == 'wartung'
    assert r['titel'] == 'Titel'
    assert r['referenz'] == 'P1'
    assert r['text'] == 'Note'


def test_csv_skips_row_without_start():
    text = _CSV + "info;Ohne Start;;;\n"
    assert usb_source.parse_termin_csv(text) == []


def test_csv_skips_invalid_start():
    text = _CSV + "info;Ungueltig;;31.13.2026;;\n"
    assert usb_source.parse_termin_csv(text) == []


def test_csv_skips_too_few_columns():
    text = _CSV + "info;Titel\n"
    assert usb_source.parse_termin_csv(text) == []


def test_csv_no_header_first_line_is_data():
    text = "kalibrierung;Ohne Header;P1;01.09.2026;03.09.2026;\n"
    rows = usb_source.parse_termin_csv(text)
    assert len(rows) == 1
    assert rows[0]['titel'] == 'Ohne Header'


def test_csv_quoted_semicolon():
    text = _CSV + 'info;"Titel; mit Semikolon";;01.09.2026;;"Text; mit Semikolon"\n'
    rows = usb_source.parse_termin_csv(text)
    assert len(rows) == 1
    assert rows[0]['titel'] == 'Titel; mit Semikolon'
    assert rows[0]['text'] == 'Text; mit Semikolon'


# ── XLSX-Parsing ─────────────────────────────────────────────────────

def _write_xlsx(path, rows, header=("Art", "Prüfstand", "Von", "Bis", "Info")):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Termine"
    ws.append(list(header))
    for r in rows:
        ws.append(list(r))
    wb.save(path)


def test_xlsx_basic(tmp_path):
    xlsx = tmp_path / 'termine.xlsx'
    _write_xlsx(xlsx, [
        ["Kalibrierung", "P3", date(2026, 8, 25), date(2026, 8, 30), "Jährliche Kalibrierung"],
    ])
    rows = usb_source.parse_termin_xlsx(str(xlsx))
    assert len(rows) == 1
    r = rows[0]
    assert r['typ'] == 'kalibrierung'
    assert r['referenz'] == 'P3'
    assert r['start'] == date(2026, 8, 25)
    assert r['ende'] == date(2026, 8, 30)
    assert r['titel'] == 'Jährliche Kalibrierung'
    assert r['text'] is None


def test_xlsx_deutsche_art(tmp_path):
    xlsx = tmp_path / 'termine.xlsx'
    _write_xlsx(xlsx, [
        ["Audit", "QS", date(2026, 9, 14), "", "ISO-Audit"],
        ["Wartung", "Druckluft", date(2026, 9, 1), date(2026, 9, 2), "Wartung"],
        ["Info", "Alle", date(2026, 9, 1), "", "Meldung"],
    ])
    rows = usb_source.parse_termin_xlsx(str(xlsx))
    assert [r['typ'] for r in rows] == ['audit', 'wartung', 'info']
    assert rows[0]['ende'] is None


def test_xlsx_skips_header_and_invalid(tmp_path):
    xlsx = tmp_path / 'termine.xlsx'
    _write_xlsx(xlsx, [
        ["Kalibrierung", "P1", date(2026, 9, 1), "", "Gültig"],
        ["Info", "", date(2026, 9, 1), "", ""],          # kein Prüfstand
        ["Info", "P2", "", "", ""],                       # kein Startdatum
    ])
    rows = usb_source.parse_termin_xlsx(str(xlsx))
    assert len(rows) == 1
    assert rows[0]['titel'] == 'Gültig'


def test_xlsx_datum_als_string(tmp_path):
    xlsx = tmp_path / 'termine.xlsx'
    _write_xlsx(xlsx, [
        ["Kalibrierung", "P2", "25.08.2026", "30.08.2026", "String-Datum"],
    ])
    rows = usb_source.parse_termin_xlsx(str(xlsx))
    assert rows[0]['start'] == date(2026, 8, 25)
    assert rows[0]['ende'] == date(2026, 8, 30)


def test_xlsx_unbekannte_art_faellt_auf_info(tmp_path):
    xlsx = tmp_path / 'termine.xlsx'
    _write_xlsx(xlsx, [
        ["Sonstiges", "P1", date(2026, 9, 1), "", "Titel"],
    ])
    assert usb_source.parse_termin_xlsx(str(xlsx))[0]['typ'] == 'info'


def test_xlsx_info_als_art_wird_nicht_als_header_uebersprungen(tmp_path):
    # "Info" ist sowohl Spaltenname (E) als auch gültiger Art-Wert → eine
    # Datenzeile mit Art="Info" darf NICHT als Kopfzeile verworfen werden.
    xlsx = tmp_path / 'termine.xlsx'
    _write_xlsx(xlsx, [
        ["Info", "Alle", date(2026, 9, 1), "", "Wichtige Meldung"],
    ])
    rows = usb_source.parse_termin_xlsx(str(xlsx))
    assert len(rows) == 1
    assert rows[0]['typ'] == 'info'
    assert rows[0]['titel'] == 'Wichtige Meldung'


def test_read_termin_from_dir_bevorzugt_xlsx(tmp_path):
    (tmp_path / 'termine.csv').write_text(_CSV + "info;Aus CSV;;01.09.2026;;\n", encoding='utf-8')
    _write_xlsx(tmp_path / 'termine.xlsx', [
        ["Info", "Alle", date(2026, 9, 1), "", "Aus XLSX"],
    ])
    rows = usb_source.read_termin_from_dir(str(tmp_path))
    assert len(rows) == 1
    assert rows[0]['titel'] == 'Aus XLSX'


def test_read_termin_from_dir_faellt_bei_kaputter_xlsx_auf_csv_zurueck(tmp_path):
    (tmp_path / 'termine.xlsx').write_bytes(b'kaputte datei')
    (tmp_path / 'termine.csv').write_text(_CSV + "info;Aus CSV;;01.09.2026;;\n", encoding='utf-8')
    rows = usb_source.read_termin_from_dir(str(tmp_path))
    assert len(rows) == 1
    assert rows[0]['titel'] == 'Aus CSV'


# ── Einstellungen / Source-Logik ─────────────────────────────────────

def test_mode_default_auto():
    with app.app_context():
        assert usb_source.get_mode() == 'auto'


def test_set_and_get_setting():
    with app.app_context():
        usb_source.set_setting(usb_source.SETTING_MODE, 'manual')
        assert usb_source.get_mode() == 'manual'
        usb_source.set_setting(usb_source.SETTING_MODE, 'auto')


def test_active_termine_splits_cal_and_news():
    _clean_termine()
    with app.app_context():
        db.session.add(Termin(typ='kalibrierung', titel='Kal P3', referenz='P3',
                              start=date(2026, 9, 1), ende=date(2026, 9, 3)))
        db.session.add(Termin(typ='audit', titel='Audit QS', referenz='QS', start=date(2026, 9, 14)))
        db.session.commit()
    with app.test_client() as c:
        d = c.get('/board/api/status').get_json()
        assert d['source'] == 'web'
        assert len(d['kalibrierungen']) == 1
        assert len(d['news']) == 1
        assert d['kalibrierungen'][0]['start'] == '2026-09-01'
        assert d['news'][0]['start'] == '2026-09-14'
    _clean_termine()


def test_active_termine_wartung_in_kalibrierungen():
    _clean_termine()
    with app.app_context():
        db.session.add(Termin(typ='wartung', titel='Snubber', referenz='',
                              start=date(2026, 9, 16), ende=date(2026, 9, 17)))
        db.session.commit()
    with app.test_client() as c:
        d = c.get('/board/api/status').get_json()
        assert len(d['kalibrierungen']) == 1
        assert d['kalibrierungen'][0]['typ'] == 'wartung'
        assert d['news'] == []
    _clean_termine()


def test_find_azubi_images(monkeypatch, tmp_path):
    (tmp_path / 'flyer.png').write_bytes(b'x')
    (tmp_path / 'seite2.jpg').write_bytes(b'y')
    (tmp_path / 'notiz.txt').write_text('x')
    monkeypatch.setattr(usb_source, 'find_azubi_dir', lambda: str(tmp_path))
    assert usb_source.find_azubi_images() == ['flyer.png', 'seite2.jpg']


def test_find_azubi_images_none(monkeypatch):
    monkeypatch.setattr(usb_source, 'find_azubi_dir', lambda: None)
    assert usb_source.find_azubi_images() == []


# ── Azubi-Einstellungen (Start + Dauer) ──────────────────────────────


def test_azubi_is_active_no_start():
    with app.app_context():
        usb_source.set_setting(usb_source.SETTING_AZUBI_START, '')
        assert usb_source.azubi_is_active(date(2026, 1, 1)) is True


def test_azubi_is_active_within_window():
    with app.app_context():
        usb_source.set_setting(usb_source.SETTING_AZUBI_START, '2026-08-01')
        usb_source.set_setting(usb_source.SETTING_AZUBI_WEEKS, '2')
        assert usb_source.azubi_is_active(date(2026, 8, 10)) is True


def test_azubi_is_active_expired():
    with app.app_context():
        usb_source.set_setting(usb_source.SETTING_AZUBI_START, '2026-08-01')
        usb_source.set_setting(usb_source.SETTING_AZUBI_WEEKS, '2')
        assert usb_source.azubi_is_active(date(2026, 8, 20)) is False


def test_azubi_is_active_before_start():
    with app.app_context():
        usb_source.set_setting(usb_source.SETTING_AZUBI_START, '2026-08-01')
        usb_source.set_setting(usb_source.SETTING_AZUBI_WEEKS, '2')
        assert usb_source.azubi_is_active(date(2026, 7, 20)) is False


def test_get_azubi_weeks_default_and_invalid():
    with app.app_context():
        usb_source.set_setting(usb_source.SETTING_AZUBI_WEEKS, '')
        assert usb_source.get_azubi_weeks() == 2
        usb_source.set_setting(usb_source.SETTING_AZUBI_WEEKS, 'abc')
        assert usb_source.get_azubi_weeks() == 2
        usb_source.set_setting(usb_source.SETTING_AZUBI_WEEKS, '3')
        assert usb_source.get_azubi_weeks() == 3


def test_settings_azubi_save():
    with app.test_client() as c:
        c.post('/login', data={'username': 'admin', 'password': 'admin'})
        r = c.post('/settings/azubi', data={'azubi_start': '2026-09-01', 'azubi_weeks': '3'})
        assert r.status_code in (200, 302)
    with app.app_context():
        assert usb_source.get_azubi_start() == date(2026, 9, 1)
        assert usb_source.get_azubi_weeks() == 3


def test_azubi_image_urls_respects_window(monkeypatch):
    monkeypatch.setattr(routes, 'find_azubi_images', lambda: ['flyer.png'])
    monkeypatch.setattr(routes, 'azubi_is_active', lambda: True)
    with app.test_request_context():
        assert routes.azubi_image_urls() == ['/board/azubi/flyer.png']
    monkeypatch.setattr(routes, 'azubi_is_active', lambda: False)
    with app.test_request_context():
        assert routes.azubi_image_urls() == []


def test_active_termine_usb_priority(monkeypatch, tmp_path):
    _clean_termine()
    with app.app_context():
        db.session.add(Termin(typ='info', titel='Intern', referenz='Alle', start=date(2026, 9, 1)))
        db.session.commit()
    csv = tmp_path / 'termine.csv'
    csv.write_text(_CSV + "kalibrierung;Von USB;P9;10.10.2026;12.10.2026;\n", encoding='utf-8')
    # routes.py nutzt seine eigene importierte Referenz auf find_usb_termin_dir
    monkeypatch.setattr(routes, 'find_usb_termin_dir', lambda: str(tmp_path))
    with app.test_client() as c:
        d = c.get('/board/api/status').get_json()
        assert d['source'] == 'usb'
        assert d['usb_present'] is True
        assert len(d['kalibrierungen']) == 1
        assert d['kalibrierungen'][0]['titel'] == 'Von USB'
    _clean_termine()


def test_manual_web_ignores_usb(monkeypatch, tmp_path):
    _clean_termine()
    with app.app_context():
        db.session.add(Termin(typ='info', titel='Intern', referenz='Alle', start=date(2026, 9, 1)))
        usb_source.set_setting(usb_source.SETTING_MODE, 'manual')
        usb_source.set_setting(usb_source.SETTING_MANUAL_SOURCE, 'web')
        db.session.commit()
    csv = tmp_path / 'termine.csv'
    csv.write_text(_CSV + "info;Von USB;;10.10.2026;;\n", encoding='utf-8')
    monkeypatch.setattr(routes, 'find_usb_termin_dir', lambda: str(tmp_path))
    with app.test_client() as c:
        d = c.get('/board/api/status').get_json()
        assert d['source'] == 'web'
        assert d['news'][0]['titel'] == 'Intern'
    with app.app_context():
        usb_source.set_setting(usb_source.SETTING_MODE, 'auto')
        db.session.commit()
    _clean_termine()


def test_manual_usb_without_stick_returns_empty(monkeypatch):
    _clean_termine()
    with app.app_context():
        db.session.add(Termin(typ='info', titel='Intern', referenz='Alle', start=date(2026, 9, 1)))
        usb_source.set_setting(usb_source.SETTING_MODE, 'manual')
        usb_source.set_setting(usb_source.SETTING_MANUAL_SOURCE, 'usb')
        db.session.commit()
    monkeypatch.setattr(routes, 'find_usb_termin_dir', lambda: None)
    with app.test_client() as c:
        d = c.get('/board/api/status').get_json()
        assert d['source'] == 'usb'
        assert d['termine'] == []
        assert d['kalibrierungen'] == []
    with app.app_context():
        usb_source.set_setting(usb_source.SETTING_MODE, 'auto')
        db.session.commit()
    _clean_termine()


def test_iter_mount_candidates_no_deep_under_mnt(monkeypatch):
    tree = {
        '/media': ['pi'],
        '/media/pi': ['MYSTICK'],
        '/run/media': [],
        '/mnt': ['lhtpi-usb', 'backup'],
        '/mnt/lhtpi-usb': ['slides'],
        '/mnt/backup': ['data'],
    }
    dirs = {
        '/media', '/run/media', '/mnt',
        '/media/pi', '/media/pi/MYSTICK',
        '/mnt/lhtpi-usb', '/mnt/lhtpi-usb/slides',
        '/mnt/backup', '/mnt/backup/data',
    }
    monkeypatch.setattr(os, 'listdir', lambda p: tree.get(p, []))
    monkeypatch.setattr(os.path, 'isdir', lambda p: p in dirs)

    cands = list(usb_source._iter_mount_candidates())

    assert '/mnt/lhtpi-usb' in cands
    assert '/mnt/backup' in cands                # direkte Kinder von /mnt werden erkannt
    assert '/mnt/lhtpi-usb/slides' not in cands  # kein Deep-Scan unter /mnt
    assert '/mnt/backup/data' not in cands       # kein Deep-Scan unter /mnt
    assert '/media/pi/MYSTICK' in cands          # Deep-Scan unter /media bleibt


def test_kiosk_public():
    with app.test_client() as c:
        assert c.get('/board/kiosk').status_code == 200


def test_dashboard_requires_login():
    with app.test_client() as c:
        r = c.get('/')
        assert r.status_code == 302
        assert '/login' in r.headers['Location']


def test_create_update_delete_termin():
    _clean_termine()
    with app.test_client() as c:
        c.post('/login', data={'username': 'admin', 'password': 'admin'})
        c.post('/termine/create', data={
            'typ': 'kalibrierung', 'titel': 'P5', 'referenz': 'P5',
            'start': '2026-10-01', 'ende': '2026-10-02', 'text': 'Test'})
        data = c.get('/termine?format=json').get_json()
        assert len(data['termine']) == 1
        assert data['termine'][0]['titel'] == 'P5'
        tid = data['termine'][0]['id']

        c.post(f'/termine/{tid}/update', data={
            'typ': 'kalibrierung', 'titel': 'P5 neu', 'referenz': 'P5',
            'start': '2026-10-01', 'ende': '2026-10-02', 'text': 'Test'})
        assert c.get('/termine?format=json').get_json()['termine'][0]['titel'] == 'P5 neu'

        c.post(f'/termine/{tid}/delete')
        assert len(c.get('/termine?format=json').get_json()['termine']) == 0
    _clean_termine()
