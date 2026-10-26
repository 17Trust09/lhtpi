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

    def test_wartung_p03_acht_stunden(self, report):
        statistik = ausfall_je_pruefstand(2026)
        p03 = statistik['P03 NRA']
        assert p03['stunden'] == pytest.approx(8.0)
        assert p03['tage'] == 1

    def test_kalibrierung_p10_aus_bloecken(self, report):
        statistik = ausfall_je_pruefstand(2026)
        p10 = statistik['P10 PTU TESTFUCHS']
        # 4 + 8 + 4 + 6 Stunden an vier Tagen
        assert p10['stunden'] == pytest.approx(22.0)
        assert p10['tage'] == 4

    def test_ausfall_p21_stunden(self, report):
        statistik = ausfall_je_pruefstand(2026)
        p21 = statistik['P21 NRC HYCOM']
        # Mi 18.11. 06:00–22:45 = 16,75 h; Do 19.11. 06:00–18:00 = 12 h
        assert p21['stunden'] == pytest.approx(28.75)
        assert p21['tage'] == 2

    def test_halbtag_p31(self, report):
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
