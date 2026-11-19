"""Stick-Watcher-Integration für Modell 3 (Abgleich → Import → Writeback)."""
import os

import pytest
from flask import Flask
from openpyxl import Workbook, load_workbook

from models import db
from historie import Vorgang, Betriebsmittel
from stick_watcher import verarbeite_stick


@pytest.fixture
def app(monkeypatch):
    import stick_watcher
    monkeypatch.setattr(stick_watcher, 'erstelle_berichte_automatisch',
                        lambda mount: {'monate': [], 'jahr': None, 'fehler': None})
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


KOPF_BM = ['ID', 'Typ', 'Bezeichnung', 'Zusammenführen mit', 'Hinweis']
KOPF_T = ['Nr', 'Art', 'Typ', 'Betriebsmittel', 'Von', 'Bis', 'Info', 'Status',
          'Betriebsmittel-ID']
KOPF_N = ['Nr', 'Art', 'Titel', 'Von', 'Bis', 'Info', 'Status']


@pytest.fixture
def stick(tmp_path):
    ordner = tmp_path / 'stick'
    ordner.mkdir()
    wb = Workbook()
    bm = wb.active
    bm.title = 'Betriebsmittel'
    bm.append(KOPF_BM)
    bm.append(['BM-001', 'Prüfstand', 'P03 NRA', None, ''])
    bm.append([None, 'Konsole', 'NEUE KONSOLE', None, ''])        # leere ID

    ws = wb.create_sheet('Termine')
    ws.append(KOPF_T)
    ws.append(['T-001', 'Kalibrierung', 'Prüfstand', 'P03 NRA',
               '02.11.2026', '02.11.2026', 'Jahreswartung', 'abgeschlossen', 'BM-001'])
    ws.append(['T-002', 'Wartung', 'Prüfstand', 'P03 NRA',
               '01.12.2026', None, 'geplant', 'offen', None])

    nw = wb.create_sheet('News & Audits')
    nw.append(KOPF_N)
    nw.append(['N-001', 'Audit', 'Audit LH', '16.11.2026', None, '', 'offen'])

    at = wb.create_sheet('Archiv Termine')
    at.append(KOPF_T)
    an = wb.create_sheet('Archiv News & Audits')
    an.append(KOPF_N)
    wb.save(ordner / 'termine.xlsx')
    return str(ordner)


class TestModell3:
    def test_import_abgleich_und_writeback(self, app, stick):
        pfad = os.path.join(stick, 'termine.xlsx')
        ergebnis = verarbeite_stick(stick)
        assert ergebnis['stick'] is True
        assert ergebnis['importiert'] is True

        assert Vorgang.query.count() == 3
        # Leere ID wurde vergeben.
        bm = Betriebsmittel.query.filter_by(bezeichnung='NEUE KONSOLE').one()
        assert bm.kennung == 'BM-002'

        # Writeback in die Datei.
        wb = load_workbook(pfad)
        assert wb['Betriebsmittel'].cell(row=3, column=1).value == 'BM-002'
        # T-001 ist abgeschlossen → archiviert; T-002 bleibt offen. Die
        # ausgeblendete BM-ID-Spalte (I) wird NICHT beschrieben.
        assert wb['Archiv Termine'].cell(row=2, column=1).value == 'T-001'
        assert wb['Termine'].cell(row=2, column=1).value == 'T-002'
        assert wb['Termine'].cell(row=2, column=9).value is None

    def test_kein_selbst_reimport(self, app, stick):
        verarbeite_stick(stick)
        zweiter = verarbeite_stick(stick)
        assert zweiter['importiert'] is False
        assert Vorgang.query.count() == 3

    def test_erzwingen_importiert_erneut(self, app, stick):
        verarbeite_stick(stick)
        zweiter = verarbeite_stick(stick, erzwinge=True)
        assert zweiter['importiert'] is True
        assert zweiter['report']['unveraendert'] == 3

    def test_nicht_beschreibbarer_stick_import_committed_und_retry(self, app, stick, monkeypatch):
        import stick_watcher
        # Stick nicht beschreibbar simulieren (unabhängig vom Mount-Pfad).
        monkeypatch.setattr(stick_watcher, '_schreibbar', lambda mount: False)
        pfad = os.path.join(stick, 'termine.xlsx')

        ergebnis = verarbeite_stick(stick)
        # Import ist trotz Writeback-Fehler in der DB committed.
        assert ergebnis['importiert'] is True
        assert Vorgang.query.count() == 3
        assert ergebnis['report']['writeback']['fehler'] == 'Stick nicht beschreibbar'

        # Datei blieb unangetastet (kein Writeback durchgekommen).
        wb = load_workbook(pfad)
        assert wb['Betriebsmittel'].cell(row=3, column=1).value is None

        # Nächster Durchlauf: kein Absturz, Writeback wird erneut versucht.
        zweiter = verarbeite_stick(stick)
        assert zweiter['report']['writeback']['fehler'] == 'Stick nicht beschreibbar'
        assert Vorgang.query.count() == 3          # kein Doppelimport
