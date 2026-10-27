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


@pytest.fixture
def testdatei(tmp_path):
    """Eine Datei mit bekannten Terminen.

    Die Vorlage selbst gehoert dem Betrieb und aendert sich - Tests, die darauf
    feste Zahlen stuetzen, brechen dann grundlos. Hier stehen die Werte, mit
    denen gerechnet wird.
    """
    from datetime import datetime
    import openpyxl

    pfad = tmp_path / 'test.xlsx'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Termine'
    ws.append(['Nr', 'Art', 'Prüfstand', 'Von', 'Bis', 'Info', 'Status'])
    ws.append([1, 'Wartung', 'P03 NRA', '02.11.2026', '02.11.2026', 'Jahreswartung', 'abgeschlossen'])
    ws.append([2, 'Kalibrierung', 'P10 PTU TESTFUCHS', '16.11.2026', '21.11.2026', 'mehrtaegig', 'abgeschlossen'])
    ws.append([3, 'Ausfall', 'P21 NRC HYCOM', '18.11.2026', '19.11.2026', 'Steuerung', 'offen'])
    ws.append([4, 'Kalibrierung', 'P31 THSA', '24.11.2026', '24.11.2026', 'Halbtag', 'offen'])
    ws.append([5, 'Audit', 'P40 AKKU/HOCHDRUCK-RAUM', '27.11.2026', '27.11.2026', 'intern', 'offen'])
    ws.append([6, 'Info', 'P07 EHSV NRA', '01.12.2026', None, 'Hinweis', 'offen'])

    zeiten = wb.create_sheet('Zeiten')
    zeiten.append(['Termin (Nr)', 'Von', 'Bis', 'Notiz'])
    # P10: vier Bloecke statt durchgehend
    zeiten.append([2, datetime(2026, 11, 16, 8, 0), datetime(2026, 11, 16, 12, 0), 'Tag 1'])
    zeiten.append([2, datetime(2026, 11, 17, 8, 0), datetime(2026, 11, 17, 16, 0), 'Tag 2'])
    zeiten.append([2, datetime(2026, 11, 19, 7, 0), datetime(2026, 11, 19, 11, 0), 'Tag 4'])
    zeiten.append([2, datetime(2026, 11, 20, 8, 0), datetime(2026, 11, 20, 14, 0), 'Tag 5'])
    # P31: ein halber Tag
    zeiten.append([4, datetime(2026, 11, 24, 9, 0), datetime(2026, 11, 24, 13, 0), 'vormittags'])
    wb.save(pfad)
    return str(pfad)


class TestEndeZuEnde:
    @pytest.fixture
    def report(self, app, testdatei):
        daten = lies_datei(testdatei)
        return importiere(daten['zeilen'], bloecke=daten['bloecke'],
                          dateiname=daten['dateiname'])

    def test_alle_zeilen_importiert(self, report):
        assert report['neu'] == 6
        assert report['fehler'] == []

    def test_zweiter_import_bucht_nichts_doppelt(self, app, report, testdatei):
        daten = lies_datei(testdatei)
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

    def test_kalibrierung_p10_aus_bloecken(self, report):
        # Vier Zeitbloecke: 4 + 8 + 4 + 6 Stunden an vier Tagen
        statistik = ausfall_je_pruefstand(2026)
        p10 = statistik['P10 PTU TESTFUCHS']
        assert p10['stunden'] == pytest.approx(22.0)
        assert p10['tage'] == 4

    def test_ausfall_p21_stunden(self, report):
        statistik = ausfall_je_pruefstand(2026)
        p21 = statistik['P21 NRC HYCOM']
        # 18.11. bis 19.11. sind zwei ganze Tage, ohne Block im Blatt „Zeiten“
        # also 2 x 16,75 h Betriebszeit.
        assert p21['stunden'] == pytest.approx(33.5)
        assert p21['tage'] == 2

    def test_halbtag_p31_aus_zeitenblatt(self, report):
        # Ein halber Tag entsteht durch einen Block im Blatt „Zeiten“:
        # der Termin steht dort als ganzer Tag, die Arbeitszeit hier.
        statistik = ausfall_je_pruefstand(2026)
        p31 = statistik['P31 THSA']
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
