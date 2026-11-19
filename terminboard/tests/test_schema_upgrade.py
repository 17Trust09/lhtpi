"""Tests für die Schema-Migration (schema_upgrade)."""
import os
import sqlite3

import pytest
from flask import Flask

from models import db
import schema_upgrade
from tools_vorlage_modell3_bauen import BETRIEBSMITTEL

VORLAGE_ZUORDNUNG = {name.casefold(): (kennung, typ)
                     for kennung, typ, name in BETRIEBSMITTEL}


def _alte_db(pfad):
    """Baut eine DB im alten Schema (vor Modell 3) mit Beispieldaten."""
    conn = sqlite3.connect(pfad)
    conn.executescript(
        """
        CREATE TABLE pruefstand (
            id INTEGER NOT NULL PRIMARY KEY,
            name VARCHAR(80) NOT NULL UNIQUE,
            aktiv BOOLEAN NOT NULL,
            sortierung INTEGER NOT NULL
        );
        CREATE TABLE vorgang (
            id INTEGER NOT NULL PRIMARY KEY,
            nr INTEGER,
            art VARCHAR(20) NOT NULL,
            pruefstand VARCHAR(80) NOT NULL,
            von DATETIME NOT NULL,
            bis DATETIME,
            info VARCHAR(500),
            status VARCHAR(20) NOT NULL,
            natural_key VARCHAR(200) NOT NULL UNIQUE,
            revision INTEGER NOT NULL,
            inhalt_hash VARCHAR(64) NOT NULL,
            quelle VARCHAR(10) NOT NULL,
            abgeschlossen_am DATETIME,
            created_at DATETIME,
            updated_at DATETIME
        );
        CREATE TABLE vorgang_zeit (
            id INTEGER NOT NULL PRIMARY KEY,
            vorgang_id INTEGER NOT NULL,
            von DATETIME NOT NULL,
            bis DATETIME NOT NULL,
            notiz VARCHAR(200)
        );
        CREATE TABLE import_lauf (
            id INTEGER NOT NULL PRIMARY KEY,
            zeitpunkt DATETIME NOT NULL,
            dateiname VARCHAR(200),
            datei_hash VARCHAR(64),
            zeilen INTEGER,
            neu INTEGER,
            geaendert INTEGER,
            unveraendert INTEGER,
            entfernt INTEGER,
            fehler INTEGER,
            bericht TEXT
        );
        """
    )
    conn.execute("INSERT INTO pruefstand (name, aktiv, sortierung) VALUES ('P03 NRA', 1, 0)")
    conn.execute("INSERT INTO pruefstand (name, aktiv, sortierung) VALUES ('P07 EHSV NRA', 1, 1)")
    conn.execute(
        "INSERT INTO vorgang (nr, art, pruefstand, von, bis, info, status, natural_key, "
        "revision, inhalt_hash, quelle) VALUES "
        "(1, 'wartung', 'P03 NRA', '2026-11-02 07:00:00', '2026-11-02 15:00:00', "
        "'Jahreswartung', 'abgeschlossen', 'wartung|P03 NRA|2026-11-02T07:00', 2, 'abc', 'usb')")
    conn.execute(
        "INSERT INTO vorgang (nr, art, pruefstand, von, bis, info, status, natural_key, "
        "revision, inhalt_hash, quelle) VALUES "
        "(2, 'ausfall', 'EIGENES LABOR', '2026-11-05 06:00:00', '2026-11-05 22:45:00', "
        "'Sonderanlage', 'offen', 'ausfall|EIGENES LABOR|2026-11-05T06:00', 1, 'def', 'usb')")
    conn.execute(
        "INSERT INTO vorgang_zeit (vorgang_id, von, bis, notiz) VALUES "
        "(1, '2026-11-02 08:00:00', '2026-11-02 12:00:00', 'Block')")
    conn.execute(
        "INSERT INTO import_lauf (zeitpunkt, dateiname, datei_hash, neu) VALUES "
        "('2026-11-02 16:00:00', 'termine.xlsx', 'x', 2)")
    conn.commit()
    conn.close()
    return pfad


@pytest.fixture
def app(pfad_db):
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + pfad_db
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        yield app
        db.session.remove()


@pytest.fixture
def pfad_db(tmp_path):
    return str(tmp_path / 'terminboard.db')


def _spalten(conn, tabelle):
    return [z[1] for z in conn.execute('PRAGMA table_info(%s)' % tabelle)]


class TestMigration:
    def test_alte_daten_bleiben_erhalten(self, app, pfad_db):
        _alte_db(pfad_db)
        report = schema_upgrade.upgrade(db)
        assert report['fehler'] is None
        assert report['migriert'] is True
        assert report['gesichert'] and os.path.exists(report['gesichert'])

        conn = sqlite3.connect(pfad_db)
        spalten = _spalten(conn, 'vorgang')
        for neu in ('vorgangsnummer', 'betriebsmittel_id', 'titel'):
            assert neu in spalten

        # Alte Daten unangetastet
        assert conn.execute('SELECT count(*) FROM vorgang').fetchone()[0] == 2
        assert conn.execute('SELECT count(*) FROM vorgang_zeit').fetchone()[0] == 1
        assert conn.execute('SELECT count(*) FROM import_lauf').fetchone()[0] == 1
        zeile = conn.execute(
            "SELECT art, pruefstand, natural_key, revision, inhalt_hash "
            "FROM vorgang WHERE natural_key='wartung|P03 NRA|2026-11-02T07:00'").fetchone()
        assert zeile == ('wartung', 'P03 NRA', 'wartung|P03 NRA|2026-11-02T07:00', 2, 'abc')
        conn.close()

    def test_bm_ids_folgen_der_vorlage(self, app, pfad_db):
        _alte_db(pfad_db)
        schema_upgrade.upgrade(db)
        conn = sqlite3.connect(pfad_db)
        zeilen = dict(conn.execute(
            'SELECT bezeichnung, kennung FROM betriebsmittel'))
        conn.close()
        for name in ('P03 NRA', 'P07 EHSV NRA'):
            assert name in zeilen
            assert zeilen[name] == VORLAGE_ZUORDNUNG[name.casefold()][0]

    def test_unbekannter_name_bekommt_freie_kennung(self, app, pfad_db):
        _alte_db(pfad_db)
        schema_upgrade.upgrade(db)
        conn = sqlite3.connect(pfad_db)
        kennung = conn.execute(
            "SELECT kennung FROM betriebsmittel WHERE bezeichnung='EIGENES LABOR'"
        ).fetchone()[0]
        conn.close()
        max_vorlage = max(int(k[3:]) for k, _, _ in BETRIEBSMITTEL)
        assert int(kennung[3:]) > max_vorlage

    def test_vorgaenge_werden_verknuepft(self, app, pfad_db):
        _alte_db(pfad_db)
        schema_upgrade.upgrade(db)
        conn = sqlite3.connect(pfad_db)
        zeile = conn.execute(
            "SELECT v.betriebsmittel_id, b.bezeichnung "
            "FROM vorgang v JOIN betriebsmittel b ON b.id = v.betriebsmittel_id "
            "WHERE v.pruefstand='P03 NRA'").fetchone()
        conn.close()
        assert zeile is not None
        assert zeile[1] == 'P03 NRA'

    def test_idempotent(self, app, pfad_db):
        _alte_db(pfad_db)
        erster = schema_upgrade.upgrade(db)
        zweiter = schema_upgrade.upgrade(db)
        assert erster['migriert'] is True
        assert zweiter['migriert'] is False
        assert zweiter['fehler'] is None
        conn = sqlite3.connect(pfad_db)
        assert conn.execute('SELECT count(*) FROM betriebsmittel').fetchone()[0] == 3
        conn.close()

    def test_index_auf_betriebsmittel_id(self, app, pfad_db):
        _alte_db(pfad_db)
        schema_upgrade.upgrade(db)
        conn = sqlite3.connect(pfad_db)
        indexe = [z[1] for z in conn.execute("PRAGMA index_list('vorgang')")]
        conn.close()
        assert 'ix_vorgang_betriebsmittel_id' in indexe

    def test_non_ascii_name_wird_ueber_casefold_verknuepft(self, app, pfad_db):
        _alte_db(pfad_db)
        conn = sqlite3.connect(pfad_db)
        conn.execute("INSERT INTO pruefstand (name, aktiv, sortierung) "
                     "VALUES ('MÜNCHEN', 1, 2)")
        conn.execute(
            "INSERT INTO vorgang (nr, art, pruefstand, von, bis, info, status, "
            "natural_key, revision, inhalt_hash, quelle) VALUES "
            "(3, 'wartung', 'München', '2026-11-06 08:00:00', '2026-11-06 16:00:00', "
            "'x', 'offen', 'wartung|München|2026-11-06T08:00', 1, 'ghi', 'usb')")
        conn.commit()
        conn.close()

        schema_upgrade.upgrade(db)
        conn = sqlite3.connect(pfad_db)
        zeile = conn.execute(
            "SELECT v.betriebsmittel_id, b.bezeichnung FROM vorgang v "
            "JOIN betriebsmittel b ON b.id = v.betriebsmittel_id "
            "WHERE v.pruefstand='München'").fetchone()
        conn.close()
        # SQLite lower() würde 'MÜNCHEN'/'München' nicht angleichen – casefold schon.
        assert zeile is not None
        assert zeile[1] == 'MÜNCHEN'


class TestRollback:
    def test_fehler_stellt_den_altzustand_wieder_her(self, app, pfad_db, monkeypatch):
        _alte_db(pfad_db)
        with open(pfad_db, 'rb') as fh:
            vorher = fh.read()

        def kaputt(conn):
            raise RuntimeError('Migration gescheitert')

        monkeypatch.setattr(schema_upgrade, '_migriere', kaputt)
        report = schema_upgrade.upgrade(db)
        assert report['fehler'] == 'Migration gescheitert'
        assert report['migriert'] is False
        assert os.path.exists(pfad_db + '.bak')
        with open(pfad_db, 'rb') as fh:
            assert fh.read() == vorher

        # Kein halb geschriebenes Schema: betriebsmittel fehlt weiterhin.
        conn = sqlite3.connect(pfad_db)
        assert conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE name='betriebsmittel'"
        ).fetchone()[0] == 0
        conn.close()


class TestInMemory:
    def test_in_memory_wird_uebersprungen(self):
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
        db.init_app(app)
        with app.app_context():
            report = schema_upgrade.upgrade(db)
        assert report['migriert'] is False
        assert report['fehler'] is None


class TestKeineMigration:
    def test_frisches_schema_ist_noop(self, app, pfad_db):
        with app.app_context():
            db.create_all()          # frisches Schema direkt aus den Modellen
        report = schema_upgrade.upgrade(db)
        assert report['migriert'] is False


class TestStartupAbbruch:
    def test_fehler_wirft_runtime_error(self, app, pfad_db, monkeypatch):
        _alte_db(pfad_db)

        def kaputt(conn):
            raise RuntimeError('Migration gescheitert')

        monkeypatch.setattr(schema_upgrade, '_migriere', kaputt)
        with pytest.raises(RuntimeError) as exc:
            schema_upgrade.upgrade_oder_abbrechen(db)
        assert 'Schema-Migration fehlgeschlagen' in str(exc.value)

    def test_noop_wirft_nicht(self, app, pfad_db):
        with app.app_context():
            db.create_all()
        # Kein Fehler, kein Wurf – sauberer No-op bleibt erlaubt.
        ergebnis = schema_upgrade.upgrade_oder_abbrechen(db)
        assert ergebnis['fehler'] is None
        assert ergebnis['migriert'] is False
