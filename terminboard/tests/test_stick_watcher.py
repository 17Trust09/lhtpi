"""Tests für die Stick-Verarbeitung (Import + Berichtsauslöser)."""
import os
import shutil
from datetime import datetime

import openpyxl
import pytest
from flask import Flask

from models import db
from historie import Vorgang, ImportLauf
from stick_watcher import verarbeite_stick, datei_hash

VORLAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'vorlagen', 'termine_modell2.xlsx')


@pytest.fixture
def app(tmp_path, monkeypatch):
    import bericht
    monkeypatch.setattr(bericht, 'DATA_DIR', str(tmp_path / 'data'))
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
def stick(tmp_path):
    """Ein Stick mit der Beispiel-Vorlage als termine.xlsx."""
    if not os.path.exists(VORLAGE):
        pytest.skip('Vorlage fehlt')
    ordner = tmp_path / 'stick'
    ordner.mkdir()
    shutil.copy(VORLAGE, ordner / 'termine.xlsx')
    return str(ordner)


class TestImport:
    def test_ohne_stick_passiert_nichts(self, app):
        ergebnis = verarbeite_stick('/gibt/es/nicht')
        assert ergebnis['stick'] is False
        assert ergebnis['importiert'] is False

    def test_stick_mit_excel_wird_importiert(self, app, stick):
        from excel_modell2 import lies_datei
        erwartet = len(lies_datei(VORLAGE)['zeilen'])
        ergebnis = verarbeite_stick(stick)
        assert ergebnis['stick'] is True
        assert ergebnis['importiert'] is True
        assert ergebnis['report']['neu'] == erwartet
        assert Vorgang.query.count() == erwartet

    def test_gleiche_datei_wird_nicht_erneut_importiert(self, app, stick):
        verarbeite_stick(stick)
        zweiter = verarbeite_stick(stick)
        assert zweiter['importiert'] is False
        assert ImportLauf.query.count() == 1

    def test_geaenderte_datei_wird_neu_importiert(self, app, stick):
        verarbeite_stick(stick)
        # Datei verändern: eine Zeile mehr
        wb = openpyxl.load_workbook(os.path.join(stick, 'termine.xlsx'))
        ws = wb['Termine']
        ws.append([7, 'Wartung', 'P43 LOW-PRESSURE',
                   datetime(2026, 12, 7, 7, 0), datetime(2026, 12, 7, 15, 0),
                   'Zusatztermin', 'offen'])
        wb.save(os.path.join(stick, 'termine.xlsx'))

        zweiter = verarbeite_stick(stick)
        assert zweiter['importiert'] is True
        assert zweiter['report']['neu'] == 1
        from excel_modell2 import lies_datei
        assert Vorgang.query.count() == len(lies_datei(VORLAGE)['zeilen']) + 1

    def test_erzwingen_importiert_auch_bei_gleichem_hash(self, app, stick):
        verarbeite_stick(stick)
        zweiter = verarbeite_stick(stick, erzwinge=True)
        assert zweiter['importiert'] is True
        from excel_modell2 import lies_datei
        assert zweiter['report']['unveraendert'] == len(lies_datei(VORLAGE)['zeilen'])
        from excel_modell2 import lies_datei
        assert Vorgang.query.count() == len(lies_datei(VORLAGE)['zeilen'])


class TestBerichtsausloeser:
    def test_ohne_trigger_kein_bericht(self, app, stick):
        ergebnis = verarbeite_stick(stick)
        assert ergebnis['bericht'] is None

    def test_trigger_erzeugt_berichte(self, app, stick):
        with open(os.path.join(stick, 'LHTPi-Bericht.jetzt'), 'w') as fh:
            fh.write('')
        ergebnis = verarbeite_stick(stick)
        assert ergebnis['bericht'] is not None
        assert ergebnis['bericht']['ausgeloest'] is True
        ordner = os.path.join(stick, 'LHTPi-Berichte')
        assert len([n for n in os.listdir(ordner) if n.endswith('.pdf')]) == 2


class TestHash:
    def test_hash_ist_stabil(self, stick):
        pfad = os.path.join(stick, 'termine.xlsx')
        assert datei_hash(pfad) == datei_hash(pfad)
        assert len(datei_hash(pfad)) == 64

    def test_hash_aendert_sich(self, stick):
        pfad = os.path.join(stick, 'termine.xlsx')
        vorher = datei_hash(pfad)
        with open(pfad, 'ab') as fh:
            fh.write(b'x')
        assert datei_hash(pfad) != vorher

    def test_fehlende_datei_ergibt_leeren_hash(self):
        assert datei_hash('/gibt/es/nicht.xlsx') == ''
