"""Ende-zu-Ende: Excel-Vorlage → Import → Auswertung.

Prüft, dass Parser, Import-Logik und Betriebszeit-Rechnung zusammen das
liefern, was am Prüfstand erwartet wird.
"""
import os

import pytest
from flask import Flask

from models import db
from historie import Vorgang, importiere, ausfall_je_pruefstand
from excel_modell2 import lies_datei

VORLAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'vorlagen', 'termine_modell2.xlsx')


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


@pytest.mark.skipif(not os.path.exists(VORLAGE), reason='Vorlage fehlt')
class TestVorlageEndeZuEnde:
    @pytest.fixture
    def report(self, app):
        daten = lies_datei(VORLAGE)
        return importiere(daten['zeilen'], bloecke=daten['bloecke'],
                          dateiname=daten['dateiname'])

    def test_alle_zeilen_importiert(self, report):
        assert report['neu'] == 6
        assert report['fehler'] == []

    def test_zweiter_import_bucht_nichts_doppelt(self, app, report):
        daten = lies_datei(VORLAGE)
        zweiter = importiere(daten['zeilen'], bloecke=daten['bloecke'],
                             dateiname=daten['dateiname'])
        assert zweiter['neu'] == 0
        assert zweiter['unveraendert'] == 6
        assert Vorgang.query.count() == 6

    def test_wartung_p03_ganzer_tag(self, report):
        statistik = ausfall_je_pruefstand(2026)
        p03 = statistik['P03 NRA']
        # Das Blatt „Termine“ kennt nur Datum: 02.11. ist ein ganzer Tag,
        # ohne Block im Blatt „Zeiten“ also die volle Betriebszeit.
        assert p03['stunden'] == pytest.approx(16.75)
        assert p03['tage'] == 1

    def test_kalibrierung_p10_ohne_bloecke_ganze_tage(self, report):
        # Das Blatt „Zeiten“ der Vorlage ist leer: 16.–20.11. sind fünf
        # Werktage (der 21.11. ist Samstag), also 5 x 16,75 h Betriebszeit.
        statistik = ausfall_je_pruefstand(2026)
        p10 = statistik['P10 PTU TESTFUCHS']
        assert p10['stunden'] == pytest.approx(83.75)
        assert p10['tage'] == 5

    def test_ausfall_p21_stunden(self, report):
        statistik = ausfall_je_pruefstand(2026)
        p21 = statistik['P21 NRC HYCOM']
        # 18.11. bis 19.11. sind zwei ganze Tage, ohne Block im Blatt „Zeiten“
        # also 2 x 16,75 h Betriebszeit.
        assert p21['stunden'] == pytest.approx(33.5)
        assert p21['tage'] == 2

    def test_halbtag_p31_ohne_zeitenblatt_ganzer_tag(self, report):
        # Ohne Block im Blatt „Zeiten“ gilt der Termin als durchgehend
        # ausser Betrieb - der 24.11. ist ein ganzer Tag.
        statistik = ausfall_je_pruefstand(2026)
        p31 = statistik['P31 THSA']
        assert p31['stunden'] == pytest.approx(16.75)
        assert p31['tage'] == 1

    def test_halbtag_entsteht_durch_zeitblock(self, app, tmp_path):
        # Die Verkürzung durch Blöcke wird an eigener Datei geprüft.
        import openpyxl
        from datetime import datetime
        pfad = tmp_path / 'halbtag.xlsx'
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Termine'
        ws.append(['Nr', 'Art', 'Prüfstand', 'Von', 'Bis', 'Info', 'Status'])
        ws.append([1, 'Kalibrierung', 'P31 THSA', '24.11.2026', '24.11.2026',
                   'Halbtag', 'offen'])
        zeiten = wb.create_sheet('Zeiten')
        zeiten.append(['Termin (Nr)', 'Von', 'Bis', 'Notiz'])
        zeiten.append([1, datetime(2026, 11, 24, 9, 0),
                       datetime(2026, 11, 24, 13, 0), 'vormittags'])
        wb.save(pfad)

        daten = lies_datei(str(pfad))
        importiere(daten['zeilen'], bloecke=daten['bloecke'],
                   dateiname=daten['dateiname'])
        p31 = ausfall_je_pruefstand(2026)['P31 THSA']
        assert p31['stunden'] == pytest.approx(4.0)
        assert p31['tage'] == 1

    def test_audit_und_info_zaehlen_nicht(self, report):
        statistik = ausfall_je_pruefstand(2026)
        assert 'P40 AKKU/HOCHDRUCK-RAUM' not in statistik   # Audit
        assert 'P07 EHSV NRA' not in statistik              # Info

    def test_abgeschlossene_vorgaenge_zaehlen_mit(self, report):
        v = Vorgang.query.filter_by(pruefstand='P10 PTU TESTFUCHS').one()
        assert v.status == 'abgeschlossen'
        assert v.zaehlt_als_ausfall is True
