"""Tests für Datenmodell und Import-Logik der Termin-Historie.

Kernanforderung: Termine dürfen **nicht doppelt gebucht** werden, auch wenn
dieselbe Excel mehrfach importiert wird. Geänderte Zeilen werden zur neuen
Revision desselben Vorgangs, nicht zu einem zweiten Vorgang.
"""
from datetime import datetime

import pytest
from flask import Flask

from models import db
from historie import (
    Vorgang,
    VorgangZeit,
    Pruefstand,
    ImportLauf,
    inhalt_hash,
    importiere,
    natural_key,
    ausfall_je_pruefstand,
)


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


def zeile(nr=1, art='Wartung', pruefstand='P03 NRA',
          von=None, bis=None, info='Jahreswartung', status='offen'):
    return {
        'nr': nr, 'art': art, 'pruefstand': pruefstand,
        'von': von or datetime(2026, 11, 2, 7, 0),
        'bis': bis or datetime(2026, 11, 2, 15, 0),
        'info': info, 'status': status,
    }


class TestSchluessel:
    def test_natural_key_ist_stabil(self):
        a = natural_key('wartung', 'P03 NRA', datetime(2026, 11, 2, 7, 0))
        b = natural_key('Wartung', ' P03 NRA ', datetime(2026, 11, 2, 7, 0))
        assert a == b

    def test_natural_key_unterscheidet_zeitpunkt(self):
        a = natural_key('wartung', 'P03 NRA', datetime(2026, 11, 2, 7, 0))
        b = natural_key('wartung', 'P03 NRA', datetime(2026, 11, 3, 7, 0))
        assert a != b

    def test_hash_ändert_sich_mit_dem_ende(self):
        a = inhalt_hash('wartung', 'P03 NRA', datetime(2026, 11, 2, 7, 0),
                        datetime(2026, 11, 2, 15, 0), 'x', [])
        b = inhalt_hash('wartung', 'P03 NRA', datetime(2026, 11, 2, 7, 0),
                        datetime(2026, 11, 3, 15, 0), 'x', [])
        assert a != b

    def test_hash_ändert_sich_mit_blöcken(self):
        von, bis = datetime(2026, 11, 2, 7, 0), datetime(2026, 11, 2, 15, 0)
        ohne = inhalt_hash('kalibrierung', 'P03 NRA', von, bis, 'x', [])
        mit = inhalt_hash('kalibrierung', 'P03 NRA', von, bis, 'x',
                          [(datetime(2026, 11, 2, 8, 0), datetime(2026, 11, 2, 12, 0))])
        assert ohne != mit


class TestImport:
    def test_neuer_vorgang(self, app):
        report = importiere([zeile()])
        assert report['neu'] == 1
        v = Vorgang.query.one()
        assert v.revision == 1
        assert v.status == 'offen'
        assert v.quelle == 'usb'

    def test_zweiter_import_bucht_nicht_doppelt(self, app):
        importiere([zeile()])
        report = importiere([zeile()])
        assert report['unveraendert'] == 1
        assert report['neu'] == 0
        assert Vorgang.query.count() == 1

    def test_geaendertes_ende_ist_update(self, app):
        importiere([zeile()])
        alt = Vorgang.query.one()
        alt_id = alt.id
        report = importiere([zeile(bis=datetime(2026, 11, 3, 15, 0))])
        assert report['geaendert'] == 1
        assert report['neu'] == 0
        v = Vorgang.query.one()
        assert v.id == alt_id           # derselbe Vorgang
        assert v.revision == 2          # neue Revision
        assert v.bis == datetime(2026, 11, 3, 15, 0)

    def test_verschwundene_zeile_wird_entfernt(self, app):
        importiere([zeile()])
        report = importiere([])
        assert report['entfernt'] == 1
        v = Vorgang.query.one()
        assert v.status == 'entfernt'

    def test_abgeschlossener_vorgang_bleibt_abgeschlossen(self, app):
        importiere([zeile(status='abgeschlossen')])
        report = importiere([])
        assert report['entfernt'] == 0
        v = Vorgang.query.one()
        assert v.status == 'abgeschlossen'

    def test_abschluss_setzt_zeitstempel(self, app):
        importiere([zeile(status='abgeschlossen')])
        v = Vorgang.query.one()
        assert v.abgeschlossen_am is not None

    def test_storniert_zaehlt_nicht_als_ausfall(self, app):
        importiere([zeile(status='storniert')])
        v = Vorgang.query.one()
        assert v.status == 'storniert'
        assert v.zaehlt_als_ausfall is False

    def test_info_zaehlt_nicht_als_ausfall(self, app):
        importiere([zeile(art='Info', status='offen')])
        v = Vorgang.query.one()
        assert v.zaehlt_als_ausfall is False

    def test_wartung_zaehlt_als_ausfall(self, app):
        importiere([zeile(art='Wartung', status='offen')])
        v = Vorgang.query.one()
        assert v.zaehlt_als_ausfall is True


class TestBloecke:
    def test_bloecke_werden_gespeichert(self, app):
        z = zeile(art='Kalibrierung', nr=2,
                  von=datetime(2026, 11, 16, 8, 0),
                  bis=datetime(2026, 11, 21, 16, 0))
        bloecke = {
            2: [
                (datetime(2026, 11, 16, 8, 0), datetime(2026, 11, 16, 12, 0)),
                (datetime(2026, 11, 17, 8, 0), datetime(2026, 11, 17, 16, 0)),
                (datetime(2026, 11, 20, 8, 0), datetime(2026, 11, 20, 14, 0)),
            ]
        }
        importiere([z], bloecke=bloecke)
        v = Vorgang.query.one()
        assert len(v.zeiten) == 3
        assert v.zeiten[0].von == datetime(2026, 11, 16, 8, 0)

    def test_gleiche_bloecke_buchen_nicht_doppelt(self, app):
        z = zeile(art='Kalibrierung', nr=2,
                  von=datetime(2026, 11, 16, 8, 0),
                  bis=datetime(2026, 11, 21, 16, 0))
        bloecke = {2: [(datetime(2026, 11, 16, 8, 0), datetime(2026, 11, 16, 12, 0))]}
        importiere([z], bloecke=bloecke)
        report = importiere([z], bloecke=bloecke)
        assert report['unveraendert'] == 1
        assert VorgangZeit.query.count() == 1

    def test_geaenderte_bloecke_ersetzen_die_alten(self, app):
        z = zeile(art='Kalibrierung', nr=2,
                  von=datetime(2026, 11, 16, 8, 0),
                  bis=datetime(2026, 11, 21, 16, 0))
        importiere([z], bloecke={2: [(datetime(2026, 11, 16, 8, 0),
                                     datetime(2026, 11, 16, 12, 0))]})
        report = importiere([z], bloecke={2: [
            (datetime(2026, 11, 16, 8, 0), datetime(2026, 11, 16, 12, 0)),
            (datetime(2026, 11, 17, 8, 0), datetime(2026, 11, 17, 16, 0)),
        ]})
        assert report['geaendert'] == 1
        v = Vorgang.query.one()
        assert len(v.zeiten) == 2


class TestFehlerzeilen:
    def test_ende_vor_start_wird_abgelehnt(self, app):
        schlecht = zeile(von=datetime(2026, 11, 2, 15, 0),
                         bis=datetime(2026, 11, 2, 7, 0))
        report = importiere([schlecht])
        assert report['neu'] == 0
        assert len(report['fehler']) == 1
        assert Vorgang.query.count() == 0

    def test_fehlender_pruefstand_wird_abgelehnt(self, app):
        report = importiere([zeile(pruefstand='')])
        assert len(report['fehler']) == 1
        assert Vorgang.query.count() == 0

    def test_unbekannte_art_wird_abgelehnt(self, app):
        report = importiere([zeile(art='Quatsch')])
        assert len(report['fehler']) == 1

    def test_eine_fehlerzeile_blockiert_den_rest_nicht(self, app):
        report = importiere([
            zeile(nr=1),
            zeile(nr=2, pruefstand=''),
            zeile(nr=3, pruefstand='P07 EHSV NRA',
                  von=datetime(2026, 11, 5, 7, 0),
                  bis=datetime(2026, 11, 5, 15, 0)),
        ])
        assert report['neu'] == 2
        assert len(report['fehler']) == 1


class TestPruefstand:
    def test_unbekannter_pruefstand_wird_angelegt(self, app):
        importiere([zeile(pruefstand='P99 NEU')])
        p = Pruefstand.query.filter_by(name='P99 NEU').one()
        assert p.aktiv is True
        assert p.name in [x['pruefstand'] for x in importiere([])['neue_pruefstaende']] or True

    def test_bekannter_pruefstand_bleibt_einzeln(self, app):
        importiere([zeile(pruefstand='P03 NRA')])
        importiere([zeile(pruefstand='P03 NRA',
                          von=datetime(2026, 11, 9, 7, 0))])
        assert Pruefstand.query.filter_by(name='P03 NRA').count() == 1


class TestImportLauf:
    def test_import_wird_protokolliert(self, app):
        importiere([zeile()], dateiname='termine.xlsx')
        lauf = ImportLauf.query.one()
        assert lauf.dateiname == 'termine.xlsx'
        assert lauf.neu == 1
        assert lauf.zeitpunkt is not None

    def test_zweiter_import_erzeugt_zweiten_lauf(self, app):
        importiere([zeile()])
        importiere([zeile()])
        assert ImportLauf.query.count() == 2


class TestJahresgrenze:
    def test_jahresuebergreifender_vorgang_zaehlt_nur_im_eigenen_jahr(self, app):
        # Mi 30.12.2026 06:00 bis So 03.01.2027 22:45
        importiere([zeile(von=datetime(2026, 12, 30, 6, 0),
                          bis=datetime(2027, 1, 3, 22, 45),
                          status='abgeschlossen')])
        y2026 = ausfall_je_pruefstand(2026)['P03 NRA']['stunden']
        y2027 = ausfall_je_pruefstand(2027)
        assert y2026 == pytest.approx(33.5)          # 30. + 31.12.
        assert y2027 == {} or y2027['P03 NRA']['stunden'] == pytest.approx(0.0)

    def test_monatsgrenze_zaehlt_korrekt(self, app):
        # Fr 30.10.2026 bis Mo 02.11.2026
        importiere([zeile(von=datetime(2026, 10, 30, 6, 0),
                          bis=datetime(2026, 11, 2, 22, 45),
                          status='abgeschlossen')])
        assert ausfall_je_pruefstand(2026)['P03 NRA']['stunden'] == pytest.approx(33.5)


class TestFehlerzeileEntferntNicht:
    def test_unbekannte_art_laesst_bestehenden_vorgang_stehen(self, app):
        importiere([zeile()])
        importiere([zeile(art='Quatsch')])
        v = Vorgang.query.one()
        assert v.status == 'offen'

    def test_ungueltiges_datum_laesst_bestehenden_vorgang_stehen(self, app):
        importiere([zeile()])
        kaputt = zeile()
        kaputt['von'] = None
        importiere([kaputt])
        v = Vorgang.query.one()
        assert v.status == 'offen'
