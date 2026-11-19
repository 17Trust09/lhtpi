"""Tests für den Betriebsmittel-Abgleich (betriebsmittel_sync)."""
from datetime import datetime

import pytest
from flask import Flask

from models import db
from historie import Betriebsmittel, Vorgang
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


def _zeile(bezeichnung, typ='Prüfstand', id=None, zusammen=None, zeile=2):
    return {'id': id, 'typ': typ, 'bezeichnung': bezeichnung,
            'zusammenfuehren_mit': zusammen, 'hinweis': '', 'excel_zeile': zeile}


class TestIdVergabe:
    def test_leere_id_bekommt_naechste_nummer(self, app):
        report = sync_betriebsmittel([_zeile('NEUE KONSOLE', typ='Konsole')])
        assert report['id_vergeben'] == [{
            'excel_zeile': 2, 'bezeichnung': 'NEUE KONSOLE', 'kennung': 'BM-001'}]
        assert report['writeback'] == [{
            'blatt': 'Betriebsmittel', 'excel_zeile': 2, 'kennung': 'BM-001'}]
        bm = Betriebsmittel.query.one()
        assert bm.kennung == 'BM-001'
        assert bm.typ == 'konsole'

    def test_zweite_leere_id_zaehlt_weiter(self, app):
        sync_betriebsmittel([_zeile('A', id='BM-001')])
        report = sync_betriebsmittel([_zeile('A', id='BM-001'), _zeile('B')])
        assert report['id_vergeben'][0]['kennung'] == 'BM-002'

    def test_leerer_name_wird_uebersprungen(self, app):
        report = sync_betriebsmittel([_zeile('', id='BM-050')])
        assert Betriebsmittel.query.count() == 0
        assert report['id_vergeben'] == []

    def test_leere_id_vor_expliziter_id_bleibt_getrennt(self, app):
        # Leere Zeile steht VOR der expliziten BM-001 – sie darf nicht mit ihr
        # kollidieren, sondern bekommt die nächste freie Nummer (BM-002).
        report = sync_betriebsmittel([
            _zeile('NEUE KONSOLE', typ='Konsole', zeile=2),
            _zeile('EXPLIZIT', id='BM-001', zeile=3),
        ])
        assert Betriebsmittel.query.count() == 2
        bm = Betriebsmittel.query.filter_by(bezeichnung='NEUE KONSOLE').one()
        assert bm.kennung == 'BM-002'
        explizit = Betriebsmittel.query.filter_by(kennung='BM-001').one()
        assert explizit.bezeichnung == 'EXPLIZIT'
        assert report['id_vergeben'][0]['kennung'] == 'BM-002'


class TestUpdate:
    def test_umbenennen_aendert_denselben_datensatz(self, app):
        sync_betriebsmittel([_zeile('ALT', id='BM-001')])
        vorher = Betriebsmittel.query.one().id
        report = sync_betriebsmittel([_zeile('NEU', id='BM-001')])
        assert report['geaendert']
        assert Betriebsmittel.query.count() == 1
        assert Betriebsmittel.query.one().id == vorher
        assert Betriebsmittel.query.one().bezeichnung == 'NEU'

    def test_typwechsel_aendert_denselben_datensatz(self, app):
        sync_betriebsmittel([_zeile('K1', typ='Prüfstand', id='BM-001')])
        report = sync_betriebsmittel([_zeile('K1', typ='Konsole', id='BM-001')])
        assert Betriebsmittel.query.count() == 1
        assert Betriebsmittel.query.one().typ == 'konsole'


class TestDuplikate:
    def test_exakt_doppelt_wird_gemeldet(self, app):
        report = sync_betriebsmittel([
            _zeile('KONSOLE 1', typ='Konsole', id='BM-001', zeile=2),
            _zeile('konsole 1', typ='KONSOLE', id='BM-002', zeile=3),
        ])
        assert any('Doppeltes Betriebsmittel' in f['grund'] for f in report['fehler'])

    def test_aehnliche_namen_bleiben_getrennt(self, app):
        report = sync_betriebsmittel([
            _zeile('KONSOLE 1', typ='Konsole', id='BM-001'),
            _zeile('KONSOLE 2', typ='Konsole', id='BM-002'),
        ])
        assert report['fehler'] == []
        assert Betriebsmittel.query.count() == 2


class TestZusammenfuehren:
    def _vorbereiten(self, app):
        a = Betriebsmittel(kennung='BM-001', typ='pruefstand', bezeichnung='ALTE')
        b = Betriebsmittel(kennung='BM-002', typ='pruefstand', bezeichnung='NEUE')
        db.session.add_all([a, b])
        db.session.flush()
        v = Vorgang(nr=None, art='wartung', pruefstand='ALTE',
                    betriebsmittel_id=a.id, von=datetime(2026, 11, 2, 7, 0),
                    natural_key='wartung|ALTE|2026-11-02T07:00', revision=1,
                    inhalt_hash='x', quelle='usb')
        db.session.add(v)
        db.session.commit()
        return a, b, v

    def test_haengt_vorgaenge_um_und_behaelt_alias(self, app):
        a, b, v = self._vorbereiten(app)
        report = sync_betriebsmittel([
            _zeile('NEUE', id='BM-002'),
            _zeile('ALTE', id='BM-001', zusammen='BM-002'),
        ])
        assert report['zusammengefuehrt'] == [{'quelle': 'BM-001', 'ziel': 'BM-002'}]
        db.session.refresh(a)
        assert a.merge_ziel_id == b.id
        v2 = Vorgang.query.one()
        assert v2.betriebsmittel_id == b.id
        assert v2.pruefstand == 'NEUE'

    def test_unbekanntes_ziel_meldet_fehler(self, app):
        sync_betriebsmittel([_zeile('ALTE', id='BM-001')])
        report = sync_betriebsmittel(
            [_zeile('ALTE', id='BM-001', zusammen='BM-999')])
        assert any('unbekannt' in f['grund'] for f in report['fehler'])

    def test_ziel_ist_man_selbst(self, app):
        sync_betriebsmittel([_zeile('ALTE', id='BM-001')])
        report = sync_betriebsmittel(
            [_zeile('ALTE', id='BM-001', zusammen='BM-001')])
        assert any('selbst' in f['grund'] for f in report['fehler'])

    def test_zyklus_meldet_fehler(self, app):
        sync_betriebsmittel([
            _zeile('A', id='BM-001'),
            _zeile('B', id='BM-002'),
        ])
        # A -> B und B -> A wäre ein Zyklus.
        sync_betriebsmittel([_zeile('A', id='BM-001', zusammen='BM-002')])
        report = sync_betriebsmittel([
            _zeile('A', id='BM-001', zusammen='BM-002'),
            _zeile('B', id='BM-002', zusammen='BM-001'),
        ])
        assert any('Zyklus' in f['grund'] for f in report['fehler'])


class TestMergeKette:
    """A→B→C muss unabhängig von der Zeilenreihenfolge auf C enden."""

    @pytest.mark.parametrize('reihenfolge', [
        ['A', 'B', 'C'],    # A→B zuerst
        ['C', 'B', 'A'],    # B→C zuerst, dann A→B
    ])
    def test_merge_kette_haengt_an_terminal_ziel(self, app, reihenfolge):
        from historie import _aufloesen_final
        a = Betriebsmittel(kennung='BM-001', typ='pruefstand', bezeichnung='A')
        b = Betriebsmittel(kennung='BM-002', typ='pruefstand', bezeichnung='B')
        c = Betriebsmittel(kennung='BM-003', typ='pruefstand', bezeichnung='C')
        db.session.add_all([a, b, c])
        db.session.flush()
        v = Vorgang(nr=None, art='wartung', pruefstand='A', betriebsmittel_id=a.id,
                    von=datetime(2026, 11, 2, 7, 0), natural_key='w|A|1',
                    revision=1, inhalt_hash='x', quelle='usb')
        db.session.add(v)
        db.session.commit()

        zusammen = {'A': 'BM-002', 'B': 'BM-003', 'C': None}
        zeilen = []
        for name in reihenfolge:
            kennung = 'BM-%03d' % ('ABC'.index(name) + 1)
            ziel = zusammen[name]
            zeilen.append(_zeile(name, id=kennung, zusammen=ziel))
        sync_betriebsmittel(zeilen)

        db.session.refresh(a)
        db.session.refresh(b)
        db.session.refresh(c)
        assert _aufloesen_final(a).kennung == 'BM-003'
        assert _aufloesen_final(b).kennung == 'BM-003'
        # Der Vorgang hängt direkt am endgültigen Ziel C.
        assert Vorgang.query.one().betriebsmittel_id == c.id


class TestInaktiv:
    def test_fehlende_fruehere_id_wird_inaktiv(self, app):
        sync_betriebsmittel([
            _zeile('A', id='BM-001'),
            _zeile('B', id='BM-002'),
        ])
        report = sync_betriebsmittel([_zeile('A', id='BM-001')])
        assert report['inaktiv'] == [{'kennung': 'BM-002', 'bezeichnung': 'B'}]
        b = Betriebsmittel.query.filter_by(kennung='BM-002').one()
        assert b.in_excel_aktiv is False
        assert Betriebsmittel.query.count() == 2          # Historie bleibt

    def test_wiederauftauchen_aktiviert(self, app):
        sync_betriebsmittel([_zeile('A', id='BM-001'), _zeile('B', id='BM-002')])
        sync_betriebsmittel([_zeile('A', id='BM-001')])
        report = sync_betriebsmittel([_zeile('A', id='BM-001'), _zeile('B', id='BM-002')])
        b = Betriebsmittel.query.filter_by(kennung='BM-002').one()
        assert b.in_excel_aktiv is True
