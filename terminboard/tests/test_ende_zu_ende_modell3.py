"""Ende-zu-Ende Modell 3: Excel-Datei → Parser → Abgleich → Import → Statistik."""
import pytest
from flask import Flask
from openpyxl import Workbook

from models import db
from excel_modell3 import lies_datei
from betriebsmittel_sync import sync_betriebsmittel
from historie import Vorgang, importiere_modell3, ausfall_je_pruefstand

KOPF_BM = ['ID', 'Typ', 'Bezeichnung', 'Zusammenführen mit', 'Hinweis']
KOPF_T = ['Nr', 'Art', 'Typ', 'Betriebsmittel', 'Von', 'Bis', 'Info', 'Status',
          'Betriebsmittel-ID']
KOPF_N = ['Nr', 'Art', 'Titel', 'Von', 'Bis', 'Info', 'Status']


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _datei(pfad):
    wb = Workbook()
    bm = wb.active
    bm.title = 'Betriebsmittel'
    bm.append(KOPF_BM)
    bm.append(['BM-001', 'Prüfstand', 'P03 NRA', None, ''])
    bm.append(['BM-002', 'Konsole', 'KONSOLE A', None, ''])

    ws = wb.create_sheet('Termine')
    ws.append(KOPF_T)
    ws.append(['T-001', 'Wartung', 'Prüfstand', 'P03 NRA',
               '02.11.2026', '02.11.2026', 'Jahreswartung', 'abgeschlossen', 'BM-001'])
    ws.append(['T-002', 'Kalibrierung', 'Konsole', 'KONSOLE A',
               '16.11.2026', '16.11.2026', 'Messkette', 'abgeschlossen', 'BM-002'])

    nw = wb.create_sheet('News & Audits')
    nw.append(KOPF_N)
    nw.append(['N-001', 'Audit', 'Audit LH', '16.11.2026', None, '', 'offen'])

    wb.create_sheet('Archiv Termine').append(KOPF_T)
    wb.create_sheet('Archiv News & Audits').append(KOPF_N)
    wb.save(pfad)
    return str(pfad)


class TestEndeZuEnde:
    def test_kompletter_pfad(self, app, tmp_path):
        pfad = _datei(tmp_path / 'modell3.xlsx')
        daten = lies_datei(pfad)
        assert daten['fehler'] == []

        sync_report = sync_betriebsmittel(daten['betriebsmittel'])
        assert len(sync_report['neu']) == 2

        report = importiere_modell3(daten, dateiname=daten['dateiname'])
        assert report['neu'] == 3
        assert report['fehler'] == []

        # Nur abgeschlossene Kalibrierung/Wartung/Ausfall zählen.
        assert Vorgang.query.filter_by(vorgangsnummer='N-001').one().zaehlt_als_ausfall is False

        statistik = ausfall_je_pruefstand(2026)
        # 02.11.2026 ist ein Montag → ganzer Betriebstag (16,75 h).
        assert statistik['P03 NRA']['stunden'] == pytest.approx(16.75)
        assert statistik['P03 NRA']['typ'] == 'pruefstand'
        assert statistik['KONSOLE A']['typ'] == 'konsole'
