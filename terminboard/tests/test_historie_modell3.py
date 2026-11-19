"""Tests für den Modell-3-Import (historie.importiere_modell3)."""
from datetime import datetime

import pytest
from flask import Flask

from models import db
from historie import Betriebsmittel, Vorgang, importiere_modell3, ausfall_je_pruefstand
from betriebsmittel_sync import sync_betriebsmittel


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


def _bm(bezeichnung='P03 NRA', typ='Prüfstand', id='BM-001'):
    return {'id': id, 'typ': typ, 'bezeichnung': bezeichnung,
            'zusammenfuehren_mit': None, 'hinweis': '', 'excel_zeile': 2}


def _t(nr='T-001', art='Kalibrierung', typ='Prüfstand', bm='P03 NRA',
       bm_id='BM-001', von=None, bis=None, info='x', status='offen', zeile=2):
    return {'nr': nr, 'art': art, 'typ': typ, 'betriebsmittel': bm,
            'betriebsmittel_id': bm_id,
            'von': von or datetime(2026, 11, 16, 0, 0),
            'bis': bis or datetime(2026, 11, 16, 23, 59),
            'info': info, 'status': status, 'excel_zeile': zeile}


def _n(nr='N-001', art='Audit', titel='Audit LH', von=None, bis=None,
       info='', status='offen'):
    return {'nr': nr, 'art': art, 'titel': titel,
            'von': von or datetime(2026, 11, 16, 0, 0), 'bis': bis,
            'info': info, 'status': status, 'excel_zeile': 2}


def _daten(**kw):
    basis = {'termine': [], 'news': [], 'bloecke': {},
             'archiv_termine': [], 'archiv_news': [], 'fehler': []}
    basis.update(kw)
    return basis


class TestIdentitaet:
    def test_termin_und_news_werden_angelegt(self, app):
        sync_betriebsmittel([_bm()])
        report = importiere_modell3(_daten(termine=[_t()], news=[_n()]))
        assert report['neu'] == 2
        v = Vorgang.query.filter_by(vorgangsnummer='T-001').one()
        assert v.art == 'kalibrierung'
        assert v.betriebsmittel.kennung == 'BM-001'
        assert v.pruefstand == 'P03 NRA'
        n = Vorgang.query.filter_by(vorgangsnummer='N-001').one()
        assert n.titel == 'Audit LH'
        assert n.betriebsmittel_id is None
        assert n.pruefstand == ''

    def test_nummer_ist_die_identitaet_nicht_art_name_von(self, app):
        sync_betriebsmittel([_bm()])
        importiere_modell3(_daten(termine=[_t()]))
        # Andere Art, anderes Datum, andere Info – aber dieselbe Nummer.
        report = importiere_modell3(_daten(termine=[
            _t(art='Wartung', von=datetime(2026, 12, 1, 0, 0), info='anders')]))
        assert report['geaendert'] == 1
        assert report['neu'] == 0
        v = Vorgang.query.one()
        assert v.vorgangsnummer == 'T-001'
        assert v.revision == 2
        assert v.art == 'wartung'

    def test_statuswechsel_revidiert_dieselbe_zeile(self, app):
        sync_betriebsmittel([_bm()])
        importiere_modell3(_daten(termine=[_t(status='offen')]))
        vorher = Vorgang.query.one().id
        importiere_modell3(_daten(termine=[_t(status='abgeschlossen')]))
        v = Vorgang.query.one()
        assert v.id == vorher
        assert v.status == 'abgeschlossen'
        assert v.abgeschlossen_am is not None

    def test_zweiter_import_bucht_nicht_doppelt(self, app):
        sync_betriebsmittel([_bm()])
        importiere_modell3(_daten(termine=[_t()], news=[_n()]))
        report = importiere_modell3(_daten(termine=[_t()], news=[_n()]))
        assert report['unveraendert'] == 2
        assert Vorgang.query.count() == 2


class TestAufloesung:
    def test_id_ist_primaer(self, app):
        sync_betriebsmittel([_bm(bezeichnung='P03 NRA', id='BM-001')])
        report = importiere_modell3(_daten(termine=[_t(bm_id='BM-001')]))
        assert report['neu'] == 1

    def test_zusammengefuehrter_name_loest_auf_ziel_auf(self, app):
        sync_betriebsmittel([
            _bm(bezeichnung='ALT', id='BM-001'),
            _bm(bezeichnung='NEU', id='BM-002'),
        ])
        sync_betriebsmittel([
            _bm(bezeichnung='NEU', id='BM-002'),
            {'id': 'BM-001', 'typ': 'Prüfstand', 'bezeichnung': 'ALT',
             'zusammenfuehren_mit': 'BM-002', 'hinweis': '', 'excel_zeile': 3},
        ])
        report = importiere_modell3(_daten(termine=[_t(bm_id=None, bm='ALT')]))
        assert report['neu'] == 1
        assert Vorgang.query.one().betriebsmittel.kennung == 'BM-002'

    def test_blanke_id_faellt_auf_name_typ_zurueck(self, app):
        sync_betriebsmittel([_bm(bezeichnung='P03 NRA', typ='Prüfstand', id='BM-001')])
        report = importiere_modell3(_daten(termine=[_t(bm_id=None, bm='P03 NRA')]))
        assert report['neu'] == 1
        assert Vorgang.query.one().betriebsmittel.kennung == 'BM-001'

    def test_unbekannte_id_ist_ein_fehler(self, app):
        sync_betriebsmittel([_bm(id='BM-001')])
        report = importiere_modell3(_daten(termine=[_t(bm_id='BM-999')]))
        assert report['neu'] == 0
        assert any('Unbekannte Betriebsmittel-ID' in f['grund']
                   for f in report['fehler'])

    def test_unbekannter_name_ist_ein_fehler(self, app):
        sync_betriebsmittel([_bm(bezeichnung='P03 NRA')])
        report = importiere_modell3(_daten(termine=[_t(bm_id=None, bm='UNBEKANNT')]))
        assert report['neu'] == 0
        assert any('Unbekanntes Betriebsmittel' in f['grund']
                   for f in report['fehler'])


class TestStatusUndArt:
    def test_storniert_wird_abgelehnt(self, app):
        sync_betriebsmittel([_bm()])
        report = importiere_modell3(_daten(termine=[_t(status='storniert')]))
        assert report['neu'] == 0
        assert any('Status' in f['grund'] for f in report['fehler'])

    def test_news_art_zaehlt_nicht_als_ausfall(self, app):
        sync_betriebsmittel([_bm()])
        importiere_modell3(_daten(termine=[_t(art='Kalibrierung', status='abgeschlossen')],
                                  news=[_n(art='Audit', status='abgeschlossen')]))
        assert Vorgang.query.filter_by(vorgangsnummer='T-001').one().zaehlt_als_ausfall is True
        assert Vorgang.query.filter_by(vorgangsnummer='N-001').one().zaehlt_als_ausfall is False

    def test_news_ohne_titel_ist_ein_fehler(self, app):
        report = importiere_modell3(_daten(news=[_n(titel='')]))
        assert report['neu'] == 0
        assert any('Titel fehlt' in f['grund'] for f in report['fehler'])


class TestStatistik:
    def test_gruppiert_nach_aktuellem_namen_mit_typ(self, app):
        sync_betriebsmittel([
            _bm(bezeichnung='P03 NRA', typ='Prüfstand', id='BM-001'),
            _bm(bezeichnung='KONSOLE A', typ='Konsole', id='BM-002'),
        ])
        importiere_modell3(_daten(termine=[
            _t(nr='T-001', bm='P03 NRA', bm_id='BM-001',
               von=datetime(2026, 11, 2, 7, 0), bis=datetime(2026, 11, 2, 15, 0),
               status='abgeschlossen'),
            _t(nr='T-002', art='Wartung', bm='KONSOLE A', bm_id='BM-002',
               von=datetime(2026, 11, 3, 7, 0), bis=datetime(2026, 11, 3, 15, 0),
               status='abgeschlossen'),
        ]))
        statistik = ausfall_je_pruefstand(2026)
        assert statistik['P03 NRA']['typ'] == 'pruefstand'
        assert statistik['KONSOLE A']['typ'] == 'konsole'

    def test_umbenennen_verschiebt_die_statistik(self, app):
        sync_betriebsmittel([_bm(bezeichnung='ALT', id='BM-001')])
        importiere_modell3(_daten(termine=[
            _t(bm='ALT', bm_id='BM-001',
               von=datetime(2026, 11, 2, 7, 0), bis=datetime(2026, 11, 2, 15, 0),
               status='abgeschlossen')]))
        # Umbenennen in der Stammdaten-Abgleichung
        sync_betriebsmittel([_bm(bezeichnung='NEU', id='BM-001')])
        statistik = ausfall_je_pruefstand(2026)
        assert 'NEU' in statistik
        assert 'ALT' not in statistik


class TestParserfehler:
    def test_parserfehler_verhindert_entfernen(self, app):
        sync_betriebsmittel([_bm()])
        importiere_modell3(_daten(termine=[_t()]))   # T-001 offen
        # Nächster Import: die T-001-Zeile wurde übersprungen (malformed) und
        # der Parser meldet einen Fehler → der bestehende Vorgang darf NICHT
        # als entfernt markiert werden.
        daten = _daten(termine=[], fehler=[{
            'blatt': 'Termine', 'excel_zeile': 2, 'grund': 'Ungültige Nummer'}])
        report = importiere_modell3(daten)
        assert report['entfernt'] == 0
        assert report['parser_fehler']
        v = Vorgang.query.filter_by(vorgangsnummer='T-001').one()
        assert v.status == 'offen'


class TestKeinWriteback:
    def test_blanke_id_erzeugt_keinen_writeback(self, app):
        # Die ausgeblendete T-Spalte (Formel) wird NICHT zurückgeschrieben –
        # der Name/Typ-Fallback löst die Zeile auf, ohne Spalte I anzufassen.
        sync_betriebsmittel([_bm()])
        report = importiere_modell3(_daten(termine=[_t(bm_id=None, bm='P03 NRA')]))
        assert report.get('writeback', []) == []
        assert report['neu'] == 1
        assert Vorgang.query.one().betriebsmittel.kennung == 'BM-001'
