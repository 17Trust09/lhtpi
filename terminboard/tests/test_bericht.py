"""Tests für den monatlichen PDF-Bericht."""
import os
from datetime import datetime

import pytest
from flask import Flask
from pypdf import PdfReader

from models import db
from historie import importiere
from bericht import (
    erstelle_bericht,
    sammle_daten,
    erstelle_monatsbericht,
    kopiere_auf_stick,
    berichtsordner_lokal,
    FUSSNOTE,
)


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


def zeile(nr=1, art='Wartung', pruefstand='P03 NRA',
          von=None, bis=None, info='Jahreswartung', status='offen'):
    return {
        'nr': nr, 'art': art, 'pruefstand': pruefstand,
        'von': von or datetime(2026, 11, 2, 7, 0),
        'bis': bis or datetime(2026, 11, 2, 15, 0),
        'info': info, 'status': status,
    }


def text_aus_pdf(pfad):
    leser = PdfReader(pfad)
    return '\n'.join(seite.extract_text() or '' for seite in leser.pages)


class TestBericht:
    def test_pdf_wird_erzeugt(self, app, tmp_path):
        pfad = tmp_path / 'bericht.pdf'
        erstelle_bericht(str(pfad), 2026, 11)
        assert pfad.exists()
        assert pfad.stat().st_size > 1000

    def test_kopfzeile_enthaelt_monat(self, app, tmp_path):
        pfad = tmp_path / 'bericht.pdf'
        erstelle_bericht(str(pfad), 2026, 11)
        text = text_aus_pdf(pfad)
        assert 'Terminbericht' in text
        assert 'November 2026' in text

    def test_aktive_termine_erscheinen(self, app, tmp_path):
        importiere([zeile(status='offen')])
        pfad = tmp_path / 'bericht.pdf'
        erstelle_bericht(str(pfad), 2026, 11)
        text = text_aus_pdf(pfad)
        assert 'P03 NRA' in text
        assert 'Wartung' in text

    def test_ausfallzeiten_mit_stunden(self, app, tmp_path):
        importiere([zeile(status='abgeschlossen')])
        pfad = tmp_path / 'bericht.pdf'
        erstelle_bericht(str(pfad), 2026, 11)
        text = text_aus_pdf(pfad)
        assert '8,00' in text

    def test_fussnote_mit_betriebstag(self, app, tmp_path):
        pfad = tmp_path / 'bericht.pdf'
        erstelle_bericht(str(pfad), 2026, 11)
        text = text_aus_pdf(pfad)
        assert '06:00' in text
        assert '16,75 h' in text

    def test_wochenende_erzeugt_keine_ausfallstunden(self, app, tmp_path):
        importiere([zeile(von=datetime(2026, 11, 7, 8, 0),
                          bis=datetime(2026, 11, 7, 16, 0),
                          status='abgeschlossen')])
        statistik = sammle_daten(2026, 11)['statistik']
        assert statistik['P03 NRA']['stunden'] == pytest.approx(0.0)

    def test_ohne_daten_kein_absturz(self, app, tmp_path):
        pfad = tmp_path / 'leer.pdf'
        erstelle_bericht(str(pfad), 2026, 11)
        text = text_aus_pdf(pfad)
        assert 'Keine aktiven Termine' in text
        assert 'Noch kein Import' in text


class TestAblage:
    def test_monatsbericht_liegt_im_berichtsordner(self, app, tmp_path):
        pfad = erstelle_monatsbericht(2026, 11)
        assert os.path.dirname(pfad) == berichtsordner_lokal()
        assert os.path.basename(pfad) == 'Terminbericht_2026-11.pdf'
        assert os.path.exists(pfad)

    def test_kopie_auf_stick(self, app, tmp_path):
        erstelle_monatsbericht(2026, 10)
        erstelle_monatsbericht(2026, 11)
        stick = tmp_path / 'stick'
        stick.mkdir()

        ergebnis = kopiere_auf_stick(str(stick))
        assert len(ergebnis['kopiert']) == 2

        ziel = stick / 'LHTPi-Berichte'
        assert (ziel / 'Terminbericht_2026-11.pdf').exists()
        assert (ziel / 'Terminbericht_2026-10.pdf').exists()

    def test_zweite_kopie_legt_keine_dublette_an(self, app, tmp_path):
        erstelle_monatsbericht(2026, 11)
        stick = tmp_path / 'stick'
        stick.mkdir()

        kopiere_auf_stick(str(stick))
        zweite = kopiere_auf_stick(str(stick))
        assert zweite['kopiert'] == []
        assert zweite['vorhanden'] == ['Terminbericht_2026-11.pdf']
        assert len(list((stick / 'LHTPi-Berichte').iterdir())) == 1

    def test_ohne_stick_passiert_nichts(self, app, tmp_path):
        erstelle_monatsbericht(2026, 11)
        ergebnis = kopiere_auf_stick(str(tmp_path / 'gibt-es-nicht'))
        assert ergebnis['kopiert'] == []


class TestStickAusloeser:
    def test_ohne_trigger_passiert_nichts(self, app, tmp_path):
        from bericht import pruefe_stick_befehl
        stick = tmp_path / 'stick'
        stick.mkdir()
        ergebnis = pruefe_stick_befehl(str(stick))
        assert ergebnis['ausgeloest'] is False

    def test_trigger_erzeugt_berichte_und_wird_erledigt(self, app, tmp_path):
        from bericht import pruefe_stick_befehl, TRIGGER_NAME, TRIGGER_ERLEDIGT
        stick = tmp_path / 'stick'
        stick.mkdir()
        (stick / TRIGGER_NAME).write_text('')

        ergebnis = pruefe_stick_befehl(str(stick))

        assert ergebnis['ausgeloest'] is True
        assert os.path.exists(ergebnis['monat'])
        assert os.path.exists(ergebnis['jahr'])
        assert (stick / TRIGGER_ERLEDIGT).exists()
        assert not (stick / TRIGGER_NAME).exists()

        berichte = stick / 'LHTPi-Berichte'
        assert len(list(berichte.glob('*.pdf'))) == 2

    def test_zweiter_trigger_legt_keine_dubletten_an(self, app, tmp_path):
        from bericht import pruefe_stick_befehl, TRIGGER_NAME
        stick = tmp_path / 'stick'
        stick.mkdir()
        (stick / TRIGGER_NAME).write_text('')
        pruefe_stick_befehl(str(stick))

        (stick / TRIGGER_NAME).write_text('')
        ergebnis = pruefe_stick_befehl(str(stick))

        assert ergebnis['kopiert'] == []      # schon vorhanden
        assert len(list((stick / 'LHTPi-Berichte').glob('*.pdf'))) == 2


class TestSchreibgeschuetzterStick:
    def test_readonly_stick_meldet_fehler_statt_abzustuerzen(self, app, tmp_path):
        erstelle_monatsbericht(2026, 11)
        stick = tmp_path / 'stick'
        (stick / 'LHTPi-Berichte').mkdir(parents=True)
        os.chmod(stick / 'LHTPi-Berichte', 0o555)
        try:
            ergebnis = kopiere_auf_stick(str(stick))
        finally:
            os.chmod(stick / 'LHTPi-Berichte', 0o755)
        assert ergebnis['fehler'] is not None
        assert ergebnis['kopiert'] == []

    def test_schreibfenster_ohne_helfer_erlaubt_direktes_schreiben(self, app, tmp_path):
        from bericht import schreibfenster
        ordner = tmp_path / 'irgendein'
        ordner.mkdir()
        with schreibfenster(str(ordner)) as bereit:
            assert bereit is True
