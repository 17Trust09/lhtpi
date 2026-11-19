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
        # 0 Stunden am Wochenende → der Prüfstand taucht gar nicht erst auf.
        assert 'P03 NRA' not in statistik

    def test_abgeschlossen_ordnet_nach_bis_statt_abhakdatum(self, app):
        # Termin endet im Oktober, wird aber erst im November abgehakt.
        # Er gehört in den Oktober-Bericht, nicht in den November-Bericht.
        importiere([zeile(nr=1, von=datetime(2026, 10, 19, 7, 0),
                          bis=datetime(2026, 10, 26, 15, 0),
                          status='abgeschlossen')])
        assert len(sammle_daten(2026, 11)['abgeschlossen']) == 0
        assert len(sammle_daten(2026, 10)['abgeschlossen']) == 1

    def test_ohne_daten_kein_absturz(self, app, tmp_path):
        pfad = tmp_path / 'leer.pdf'
        erstelle_bericht(str(pfad), 2026, 11)
        text = text_aus_pdf(pfad)
        assert 'Keine aktiven Termine' in text
        assert 'Noch kein Import' in text


class TestMonatsbezug:
    """Aktive Termine/News sind auf den Berichtsmonat bezogen (Überlappung)."""

    def test_vergangener_offener_termin_erscheint_nicht_in_jedem_bericht(
            self, app):
        importiere([zeile(nr=1, von=datetime(2024, 5, 2, 7, 0),
                          bis=datetime(2024, 5, 2, 15, 0),
                          status='offen')])
        assert len(sammle_daten(2024, 5)['aktive']) == 1
        assert sammle_daten(2024, 6)['aktive'] == []
        assert sammle_daten(2026, 11)['aktive'] == []

    def test_vergangene_offene_news_erscheint_nicht_in_jedem_bericht(self, app):
        from historie import importiere_modell3
        news = _n3(nr='N-001', art='Audit', titel='Audit LH',
                   von=datetime(2024, 5, 2, 0, 0), status='offen')
        news['bis'] = datetime(2024, 5, 3, 0, 0)   # endet in der Vergangenheit
        importiere_modell3(_daten3(news=[news]))
        assert len(sammle_daten(2024, 5)['news']) == 1
        assert sammle_daten(2024, 6)['news'] == []
        assert sammle_daten(2026, 11)['news'] == []

    def test_offene_news_ohne_ende_bleibt_sichtbar(self, app):
        # Eine Meldung ohne Bis gilt weiter – sie bleibt in späteren Monaten.
        from historie import importiere_modell3
        importiere_modell3(_daten3(news=[
            _n3(nr='N-001', art='Info', titel='Hinweis',
                von=datetime(2024, 5, 2, 0, 0), status='offen'),
        ]))
        assert len(sammle_daten(2024, 5)['news']) == 1
        assert len(sammle_daten(2024, 6)['news']) == 1
        assert len(sammle_daten(2026, 11)['news']) == 1

    def test_offener_termin_der_den_monat_ueberschneidet_erscheint(self, app):
        # Läuft über die Monatsgrenzen → in jedem berührten Monat sichtbar.
        importiere([zeile(nr=1, von=datetime(2026, 10, 15, 7, 0),
                          bis=datetime(2026, 12, 10, 15, 0),
                          status='offen')])
        assert len(sammle_daten(2026, 10)['aktive']) == 1
        assert len(sammle_daten(2026, 11)['aktive']) == 1
        assert len(sammle_daten(2026, 12)['aktive']) == 1

    def test_entfernter_termin_bleibt_aus_dem_bericht(self, app, tmp_path):
        # Vergangener offener Termin → sichtbar. Nach dem Entfernen verschwindet
        # er aus dem Bericht (kein veralteter Bericht).
        importiere([zeile(nr=1, von=datetime(2024, 5, 2, 7, 0),
                          bis=datetime(2024, 5, 2, 15, 0),
                          status='offen')])
        pfad = tmp_path / 'vorher.pdf'
        erstelle_bericht(str(pfad), 2024, 5)
        assert 'P03 NRA' in text_aus_pdf(pfad)

        importiere([])                       # Zeile weg → als entfernt markiert
        assert sammle_daten(2024, 5)['aktive'] == []
        assert sammle_daten(2026, 11)['aktive'] == []

        pfad2 = tmp_path / 'nachher.pdf'
        erstelle_bericht(str(pfad2), 2024, 5)
        assert 'P03 NRA' not in text_aus_pdf(pfad2)


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

    def test_zweite_kopie_ueberschreibt(self, app, tmp_path):
        erstelle_monatsbericht(2026, 11)
        stick = tmp_path / 'stick'
        stick.mkdir()

        kopiere_auf_stick(str(stick))
        zweite = kopiere_auf_stick(str(stick))
        assert zweite['kopiert'] == ['Terminbericht_2026-11.pdf']
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

    def test_zweiter_trigger_ueberschreibt(self, app, tmp_path):
        from bericht import pruefe_stick_befehl, TRIGGER_NAME
        stick = tmp_path / 'stick'
        stick.mkdir()
        (stick / TRIGGER_NAME).write_text('')
        pruefe_stick_befehl(str(stick))

        (stick / TRIGGER_NAME).write_text('')
        ergebnis = pruefe_stick_befehl(str(stick))

        assert ergebnis['kopiert'] == ['Terminbericht_2026-11.pdf',
                                       'Terminbericht_Jahr_2026.pdf']
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


# ── Modell-3-Berichte: Typ-Trennung, aktuelle Namen, betroffene Jahre ──

def _bm(bezeichnung, typ='Prüfstand', kennung='BM-001'):
    return {'id': kennung, 'typ': typ, 'bezeichnung': bezeichnung,
            'zusammenfuehren_mit': None, 'hinweis': '', 'excel_zeile': 2}


def _t3(nr, art, bm, bm_id, von, bis, status='abgeschlossen'):
    return {'nr': nr, 'art': art, 'typ': None, 'betriebsmittel': bm,
            'betriebsmittel_id': bm_id, 'von': von, 'bis': bis,
            'info': 'x', 'status': status, 'excel_zeile': 2}


def _n3(nr='N-001', art='Audit', titel='Audit LH', von=None, status='offen'):
    return {'nr': nr, 'art': art, 'titel': titel,
            'von': von or datetime(2026, 11, 16, 0, 0), 'bis': None,
            'info': '', 'status': status, 'excel_zeile': 2}


def _daten3(**kw):
    basis = {'termine': [], 'news': [], 'bloecke': {}, 'archiv_termine': [],
             'archiv_news': [], 'fehler': []}
    basis.update(kw)
    return basis


class TestBetriebsmittelBerichte:
    def test_statistik_getrennt_nach_typ(self, app):
        from betriebsmittel_sync import sync_betriebsmittel
        from historie import importiere_modell3
        sync_betriebsmittel([
            _bm('P31 THSA', 'Prüfstand', 'BM-001'),
            _bm('TESTFUCHS KONSOLE 1', 'Konsole', 'BM-002'),
        ])
        importiere_modell3(_daten3(termine=[
            _t3('T-001', 'Kalibrierung', 'P31 THSA', 'BM-001',
                datetime(2026, 11, 2, 7, 0), datetime(2026, 11, 2, 15, 0)),
            _t3('T-002', 'Wartung', 'TESTFUCHS KONSOLE 1', 'BM-002',
                datetime(2026, 11, 3, 7, 0), datetime(2026, 11, 3, 15, 0)),
        ]))
        daten = sammle_daten(2026, 11)
        assert 'P31 THSA' in daten['statistik_pruefstaende']
        assert 'TESTFUCHS KONSOLE 1' in daten['statistik_konsolen']
        assert daten['statistik_pruefstaende']['P31 THSA']['typ'] == 'pruefstand'
        assert daten['statistik_konsolen']['TESTFUCHS KONSOLE 1']['typ'] == 'konsole'

    def test_umbenennen_aendert_namen_nicht_stunden(self, app, tmp_path):
        from betriebsmittel_sync import sync_betriebsmittel
        from historie import importiere_modell3
        sync_betriebsmittel([_bm('ALT', 'Prüfstand', 'BM-001')])
        importiere_modell3(_daten3(termine=[
            _t3('T-001', 'Kalibrierung', 'ALT', 'BM-001',
                datetime(2026, 11, 2, 7, 0), datetime(2026, 11, 2, 15, 0)),
        ]))
        pfad = tmp_path / 'alt.pdf'
        erstelle_bericht(str(pfad), 2026, 11)
        text_alt = text_aus_pdf(pfad)
        assert 'ALT' in text_alt
        assert '8,00' in text_alt

        sync_betriebsmittel([_bm('NEU', 'Prüfstand', 'BM-001')])
        pfad2 = tmp_path / 'neu.pdf'
        erstelle_bericht(str(pfad2), 2026, 11)
        text_neu = text_aus_pdf(pfad2)
        assert 'NEU' in text_neu
        assert 'ALT' not in text_neu
        assert '8,00' in text_neu          # Stunden unverändert

    def test_typwechsel_verschiebt_kategorie(self, app):
        from betriebsmittel_sync import sync_betriebsmittel
        from historie import importiere_modell3
        sync_betriebsmittel([_bm('P31 THSA', 'Prüfstand', 'BM-001')])
        importiere_modell3(_daten3(termine=[
            _t3('T-001', 'Kalibrierung', 'P31 THSA', 'BM-001',
                datetime(2026, 11, 2, 7, 0), datetime(2026, 11, 2, 15, 0)),
        ]))
        daten = sammle_daten(2026, 11)
        assert 'P31 THSA' in daten['statistik_pruefstaende']
        assert daten['statistik_konsolen'] == {}

        sync_betriebsmittel([_bm('P31 THSA', 'Konsole', 'BM-001')])
        daten = sammle_daten(2026, 11)
        assert daten['statistik_pruefstaende'] == {}
        assert 'P31 THSA' in daten['statistik_konsolen']

    def test_merge_summiert_korrekt(self, app):
        from betriebsmittel_sync import sync_betriebsmittel
        from historie import importiere_modell3
        sync_betriebsmittel([
            _bm('ALT', 'Prüfstand', 'BM-001'),
            _bm('NEU', 'Prüfstand', 'BM-002'),
        ])
        importiere_modell3(_daten3(termine=[
            _t3('T-001', 'Kalibrierung', 'ALT', 'BM-001',
                datetime(2026, 11, 2, 7, 0), datetime(2026, 11, 2, 15, 0)),
            _t3('T-002', 'Wartung', 'NEU', 'BM-002',
                datetime(2026, 11, 3, 7, 0), datetime(2026, 11, 3, 15, 0)),
        ]))
        # Zusammenführen: BM-001 → BM-002.
        sync_betriebsmittel([
            _bm('NEU', 'Prüfstand', 'BM-002'),
            {'id': 'BM-001', 'typ': 'Prüfstand', 'bezeichnung': 'ALT',
             'zusammenfuehren_mit': 'BM-002', 'hinweis': '', 'excel_zeile': 3},
        ])
        statistik = sammle_daten(2026, 11)['statistik']
        assert 'NEU' in statistik
        assert 'ALT' not in statistik
        assert statistik['NEU']['stunden'] == 16.0
        assert statistik['NEU']['vorgaenge'] == 2

    def test_news_erzeugt_keine_ausfallzeit(self, app, tmp_path):
        from betriebsmittel_sync import sync_betriebsmittel
        from historie import importiere_modell3
        sync_betriebsmittel([_bm('P31 THSA', 'Prüfstand', 'BM-001')])
        importiere_modell3(_daten3(
            termine=[_t3('T-001', 'Kalibrierung', 'P31 THSA', 'BM-001',
                         datetime(2026, 11, 2, 7, 0),
                         datetime(2026, 11, 2, 15, 0))],
            news=[_n3(status='offen'), _n3(nr='N-002', art='Info',
                                          titel='Hinweis', status='offen')],
        ))
        daten = sammle_daten(2026, 11)
        assert len(daten['news']) == 2
        assert daten['statistik_pruefstaende']['P31 THSA']['stunden'] == 8.0
        assert daten['statistik_konsolen'] == {}
        assert all(v.art in ('audit', 'info') for v in daten['news'])

        pfad = tmp_path / 'news.pdf'
        erstelle_bericht(str(pfad), 2026, 11)
        text = text_aus_pdf(pfad)
        assert 'News & Audits' in text
        assert 'Audit LH' in text

    def test_import_report_enthaelt_betroffene_jahre(self, app):
        from betriebsmittel_sync import sync_betriebsmittel
        from historie import importiere_modell3
        sync_betriebsmittel([_bm('P31 THSA', 'Prüfstand', 'BM-001')])
        report = importiere_modell3(_daten3(termine=[
            _t3('T-001', 'Kalibrierung', 'P31 THSA', 'BM-001',
                datetime(2024, 5, 2, 7, 0), datetime(2024, 5, 2, 15, 0)),
            _t3('T-002', 'Wartung', 'P31 THSA', 'BM-001',
                datetime(2025, 3, 2, 7, 0), datetime(2025, 3, 2, 15, 0)),
        ]))
        assert report['jahre'] == {2024, 2025}


class TestHistorischeRegeneration:
    def test_jahre_der_betriebsmittel(self, app):
        from betriebsmittel_sync import sync_betriebsmittel
        from historie import importiere_modell3, jahre_der_betriebsmittel
        sync_betriebsmittel([_bm('P31 THSA', 'Prüfstand', 'BM-001')])
        importiere_modell3(_daten3(termine=[
            _t3('T-001', 'Kalibrierung', 'P31 THSA', 'BM-001',
                datetime(2024, 5, 2, 7, 0), datetime(2024, 5, 2, 15, 0)),
            _t3('T-002', 'Wartung', 'P31 THSA', 'BM-001',
                datetime(2026, 11, 2, 7, 0), datetime(2026, 11, 2, 15, 0)),
        ]))
        assert jahre_der_betriebsmittel({'BM-001'}) == {2024, 2026}

    def test_automatisch_regeneriert_alle_angegebenen_jahre(self, app, tmp_path):
        from bericht import erstelle_berichte_automatisch
        stick = tmp_path / 'stick'
        stick.mkdir()
        ergebnis = erstelle_berichte_automatisch(str(stick), jahre={2024, 2025})
        assert sorted(ergebnis['jahre']) == [2024, 2025]
        assert len(ergebnis['monate']) == 24
        assert len(ergebnis['jahresberichte']) == 2
        # Lokal und auf dem Stick liegen die historischen Dateien.
        ziel = stick / 'LHTPi-Berichte'
        assert (ziel / 'Terminbericht_2024-05.pdf').exists()
        assert (ziel / 'Terminbericht_Jahr_2024.pdf').exists()
        assert (ziel / 'Terminbericht_2025-12.pdf').exists()

    def test_historische_datei_wird_ueberschrieben(self, app, tmp_path):
        from betriebsmittel_sync import sync_betriebsmittel
        from historie import importiere_modell3
        from bericht import erstelle_berichte_automatisch
        import hashlib
        sync_betriebsmittel([_bm('P31 THSA', 'Prüfstand', 'BM-001')])
        importiere_modell3(_daten3(termine=[
            _t3('T-001', 'Kalibrierung', 'P31 THSA', 'BM-001',
                datetime(2024, 5, 2, 7, 0), datetime(2024, 5, 2, 15, 0)),
        ]))
        stick = tmp_path / 'stick'
        stick.mkdir()
        erstelle_berichte_automatisch(str(stick), jahre={2024})
        ziel = stick / 'LHTPi-Berichte' / 'Terminbericht_2024-05.pdf'
        hash_vorher = hashlib.sha256(ziel.read_bytes()).hexdigest()

        # Neuer Termin im selben historischen Jahr → Regeneration ersetzt die Datei.
        importiere_modell3(_daten3(termine=[
            _t3('T-001', 'Kalibrierung', 'P31 THSA', 'BM-001',
                datetime(2024, 5, 2, 7, 0), datetime(2024, 5, 2, 15, 0)),
            _t3('T-002', 'Wartung', 'P31 THSA', 'BM-001',
                datetime(2024, 6, 2, 7, 0), datetime(2024, 6, 2, 15, 0)),
        ]))
        erstelle_berichte_automatisch(str(stick), jahre={2024})
        hash_nachher = hashlib.sha256(ziel.read_bytes()).hexdigest()
        assert hash_nachher != hash_vorher
        # Die Datei bleibt ein gültiges, nicht-leeres PDF.
        assert ziel.stat().st_size > 1000
