"""Tests für den Excel-Parser und -Generator (Modell 3)."""
import os
from datetime import date, datetime

import openpyxl
import pytest

from excel_modell3 import lies_datei, _zu_datetime
from tools_vorlage_modell3_bauen import baue_vorlage, pruefe
from tools_vorlage_bauen import PRUEFSTAENDE as MODEL2_PRUEFSTAENDE

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VORLAGE = os.path.join(HIER, 'vorlagen', 'termine_modell3.xlsx')


def _modell2_auswahlname(eintrag):
    """Bildet den Auswahlnamen eines Modell-2-Prüfstands nach (wie im Generator)."""
    return eintrag[2] if len(eintrag) > 2 else '%s %s' % (eintrag[0], eintrag[1])


MODEL2_AUSWAHLEN = [_modell2_auswahlname(e) for e in MODEL2_PRUEFSTAENDE]

KOPF_TERMINE = ['Nr', 'Art', 'Typ', 'Betriebsmittel', 'Von', 'Bis', 'Info',
                'Status', 'Betriebsmittel-ID']
KOPF_NEWS = ['Nr', 'Art', 'Titel', 'Von', 'Bis', 'Info', 'Status']
KOPF_BM = ['ID', 'Typ', 'Bezeichnung', 'Zusammenführen mit', 'Hinweis']
KOPF_ZEITEN = ['Termin-Nr.', 'Von', 'Bis', 'Notiz']


def _schreibe(pfad, blaetter):
    """``blaetter``: ``{Name: (kopfzeile, [zeilen, ...])}`` → schreibt xlsx."""
    wb = openpyxl.Workbook()
    erste = True
    for name, (kopf, zeilen) in blaetter.items():
        ws = wb.active if erste else wb.create_sheet()
        erste = False
        ws.title = name
        if kopf:
            ws.append(kopf)
        for z in zeilen:
            ws.append(z)
    wb.save(pfad)
    return pfad


class TestDatum:
    def test_datum_ohne_zeit_wird_tagesbeginn(self):
        assert _zu_datetime('16.11.2026') == datetime(2026, 11, 16, 0, 0)

    def test_datum_als_ende_wird_tagesende(self):
        assert _zu_datetime('16.11.2026', als_ende=True) == datetime(2026, 11, 16, 23, 59)

    def test_datum_mit_zeit(self):
        assert _zu_datetime('16.11.2026 08:30') == datetime(2026, 11, 16, 8, 30)

    def test_iso_format(self):
        assert _zu_datetime('2026-11-16 08:30') == datetime(2026, 11, 16, 8, 30)

    def test_leer_ergibt_none(self):
        assert _zu_datetime('') is None
        assert _zu_datetime(None) is None

    def test_unsinn_ergibt_none(self):
        assert _zu_datetime('keine Ahnung') is None


class TestBetriebsmittel:
    def _bm(self, tmp_path, zeilen):
        return _schreibe(tmp_path / 'bm.xlsx', {
            'Betriebsmittel': (KOPF_BM, zeilen),
        })

    def test_neue_zeile_ohne_id(self, tmp_path):
        pfad = self._bm(tmp_path, [[None, 'Konsole', 'NEUE KONSOLE', None, '']])
        daten = lies_datei(str(pfad))
        assert len(daten['betriebsmittel']) == 1
        e = daten['betriebsmittel'][0]
        assert e['id'] is None
        assert e['bezeichnung'] == 'NEUE KONSOLE'
        assert e['zusammenfuehren_mit'] is None

    def test_doppelte_typ_name_gemeldet(self, tmp_path):
        pfad = self._bm(tmp_path, [
            ['BM-001', 'Prüfstand', 'TESTFUCHS KONSOLE 1', None, ''],
            ['BM-002', 'prüfstand', ' testfuchs konsole 1 ', None, ''],
        ])
        daten = lies_datei(str(pfad))
        assert len(daten['betriebsmittel']) == 2
        assert any('Doppeltes Betriebsmittel' in f['grund'] for f in daten['fehler'])

    def test_aehnliche_namen_bleiben_getrennt(self, tmp_path):
        pfad = self._bm(tmp_path, [
            ['BM-001', 'Prüfstand', 'TESTFUCHS KONSOLE 1', None, ''],
            ['BM-002', 'Prüfstand', 'TESTFUCHS KONSOLE 2', None, ''],
        ])
        daten = lies_datei(str(pfad))
        assert daten['fehler'] == []
        assert {e['bezeichnung'] for e in daten['betriebsmittel']} == \
            {'TESTFUCHS KONSOLE 1', 'TESTFUCHS KONSOLE 2'}

    def test_zusammenfuehren_mit(self, tmp_path):
        pfad = self._bm(tmp_path, [
            ['BM-001', 'Konsole', 'ALTE KONSOLE', 'BM-002', 'wird zusammengeführt'],
        ])
        daten = lies_datei(str(pfad))
        assert daten['betriebsmittel'][0]['zusammenfuehren_mit'] == 'BM-002'

    def test_zusammenfuehren_mit_falsch(self, tmp_path):
        pfad = self._bm(tmp_path, [
            ['BM-001', 'Konsole', 'ALTE KONSOLE', 'Konsole 2', ''],
        ])
        daten = lies_datei(str(pfad))
        assert any('Zusammenführen' in f['grund'] for f in daten['fehler'])

    def test_ungueltige_id(self, tmp_path):
        pfad = self._bm(tmp_path, [['X1', 'Konsole', 'KONSOLE', None, '']])
        daten = lies_datei(str(pfad))
        assert any('ID' in f['grund'] for f in daten['fehler'])


class TestTermine:
    def _datei(self, tmp_path, termine, bm=None, archiv=None):
        blaetter = {'Termine': (KOPF_TERMINE, termine)}
        if bm is not None:
            blaetter['Betriebsmittel'] = (KOPF_BM, bm)
        if archiv is not None:
            blaetter['Archiv Termine'] = (KOPF_TERMINE, archiv)
        return _schreibe(tmp_path / 'termine.xlsx', blaetter)

    def test_nur_nummer_wird_ignoriert(self, tmp_path):
        pfad = self._datei(tmp_path, [['T-001', None, None, None, None, None,
                                       None, None, None]])
        daten = lies_datei(str(pfad))
        assert daten['termine'] == []
        assert daten['fehler'] == []

    def test_voller_termin(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Kalibrierung', 'Prüfstand', 'TESTFUCHS KONSOLE 1',
              '16.11.2026', '21.11.2026', 'eintrag', 'offen', 'BM-001']],
            bm=[['BM-001', 'Prüfstand', 'TESTFUCHS KONSOLE 1', None, '']],
        )
        daten = lies_datei(str(pfad))
        assert daten['fehler'] == []
        z = daten['termine'][0]
        assert z['nr'] == 'T-001'
        assert z['art'] == 'Kalibrierung'
        assert z['typ'] == 'Prüfstand'
        assert z['betriebsmittel'] == 'TESTFUCHS KONSOLE 1'
        assert z['betriebsmittel_id'] == 'BM-001'
        assert z['von'] == datetime(2026, 11, 16, 0, 0)
        assert z['bis'] == datetime(2026, 11, 21, 23, 59)
        assert z['status'] == 'offen'

    def test_leeres_bis_wird_tagesende(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Wartung', 'Prüfstand', 'TESTFUCHS KONSOLE 1',
              '05.11.2026', None, 'eintägig', 'offen', None]],
            bm=[['BM-001', 'Prüfstand', 'TESTFUCHS KONSOLE 1', None, '']],
        )
        daten = lies_datei(str(pfad))
        assert daten['termine'][0]['bis'] == datetime(2026, 11, 5, 23, 59)

    def test_ungueltige_nummer(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['123', 'Kalibrierung', 'Prüfstand', 'X', '16.11.2026', None,
              '', 'offen', None]],
            bm=[['BM-001', 'Prüfstand', 'TESTFUCHS KONSOLE 1', None, '']],
        )
        daten = lies_datei(str(pfad))
        assert daten['termine'] == []
        assert any('Nummer' in f['grund'] for f in daten['fehler'])

    def test_ungueltige_art(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Info', 'Prüfstand', 'TESTFUCHS KONSOLE 1',
              '16.11.2026', None, '', 'offen', None]],
            bm=[['BM-001', 'Prüfstand', 'TESTFUCHS KONSOLE 1', None, '']],
        )
        daten = lies_datei(str(pfad))
        assert any('Art' in f['grund'] for f in daten['fehler'])

    def test_unbekanntes_betriebsmittel(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Kalibrierung', 'Prüfstand', 'UNBEKANNT',
              '16.11.2026', None, '', 'offen', None]],
            bm=[['BM-001', 'Prüfstand', 'TESTFUCHS KONSOLE 1', None, '']],
        )
        daten = lies_datei(str(pfad))
        assert len(daten['termine']) == 1          # Zeile bleibt erhalten
        assert any('Betriebsmittel' in f['grund'] for f in daten['fehler'])

    def test_doppelte_nummer_aktiv_archiv(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Kalibrierung', 'Prüfstand', 'TESTFUCHS KONSOLE 1',
              '16.11.2026', None, '', 'offen', None]],
            bm=[['BM-001', 'Prüfstand', 'TESTFUCHS KONSOLE 1', None, '']],
            archiv=[['T-001', 'Wartung', 'Konsole', 'TESTFUCHS KONSOLE 2',
                     '01.12.2026', None, '', 'abgeschlossen', None]],
        )
        daten = lies_datei(str(pfad))
        assert any('Doppelte Nummer' in f['grund'] for f in daten['fehler'])


class TestParserBetriebsmittelId:
    """Verstärkter Parser: eine vorhandene Betriebsmittel-ID wird validiert."""

    def _datei(self, tmp_path, termine, bm):
        return _schreibe(tmp_path / 't.xlsx', {
            'Termine': (KOPF_TERMINE, termine),
            'Betriebsmittel': (KOPF_BM, bm),
        })

    def test_id_stimmt_mit_name_und_typ_ueberein(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Kalibrierung', 'Prüfstand', 'P01 NRA',
              '16.11.2026', None, '', 'offen', 'BM-001']],
            [['BM-001', 'Prüfstand', 'P01 NRA', None, '']],
        )
        daten = lies_datei(str(pfad))
        assert daten['fehler'] == []
        assert daten['termine'][0]['betriebsmittel_id'] == 'BM-001'

    def test_id_unbekannt_gemeldet(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Kalibrierung', 'Prüfstand', 'P01 NRA',
              '16.11.2026', None, '', 'offen', 'BM-999']],
            [['BM-001', 'Prüfstand', 'P01 NRA', None, '']],
        )
        daten = lies_datei(str(pfad))
        assert any('Unbekannte Betriebsmittel-ID' in f['grund']
                   for f in daten['fehler'])

    def test_id_malformed_gemeldet(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Kalibrierung', 'Prüfstand', 'P01 NRA',
              '16.11.2026', None, '', 'offen', 'X7']],
            [['BM-001', 'Prüfstand', 'P01 NRA', None, '']],
        )
        daten = lies_datei(str(pfad))
        assert any('Betriebsmittel-ID' in f['grund'] for f in daten['fehler'])

    def test_id_passt_nicht_zum_namen(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Kalibrierung', 'Prüfstand', 'P02 NRA',
              '16.11.2026', None, '', 'offen', 'BM-001']],
            [['BM-001', 'Prüfstand', 'P01 NRA', None, '']],
        )
        daten = lies_datei(str(pfad))
        assert any('gehört zu' in f['grund'] for f in daten['fehler'])

    def test_id_passt_nicht_zum_typ(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Kalibrierung', 'Konsole', 'P01 NRA',
              '16.11.2026', None, '', 'offen', 'BM-001']],
            [['BM-001', 'Prüfstand', 'P01 NRA', None, '']],
        )
        daten = lies_datei(str(pfad))
        assert any('Typ' in f['grund'] for f in daten['fehler'])

    def test_leere_id_mit_bekanntem_namen_ok(self, tmp_path):
        # Neue, noch nicht zugeordnete Zeile: leere ID ist erlaubt.
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Kalibrierung', 'Prüfstand', 'P01 NRA',
              '16.11.2026', None, '', 'offen', None]],
            [['BM-001', 'Prüfstand', 'P01 NRA', None, '']],
        )
        daten = lies_datei(str(pfad))
        assert daten['fehler'] == []
        assert daten['termine'][0]['betriebsmittel_id'] is None


class TestNews:
    def _datei(self, tmp_path, news, archiv=None):
        blaetter = {'News & Audits': (KOPF_NEWS, news)}
        if archiv is not None:
            blaetter['Archiv News & Audits'] = (KOPF_NEWS, archiv)
        return _schreibe(tmp_path / 'news.xlsx', blaetter)

    def test_nur_nummer_wird_ignoriert(self, tmp_path):
        pfad = self._datei(tmp_path, [['N-001', None, None, None, None, None, None]])
        daten = lies_datei(str(pfad))
        assert daten['news'] == []
        assert daten['fehler'] == []

    def test_news_zeile(self, tmp_path):
        pfad = self._datei(tmp_path, [
            ['N-001', 'Audit', 'Audit LH', '16.11.2026', '18.11.2026',
             'Details', 'offen'],
        ])
        daten = lies_datei(str(pfad))
        assert daten['fehler'] == []
        n = daten['news'][0]
        assert n['nr'] == 'N-001'
        assert n['art'] == 'Audit'
        assert n['titel'] == 'Audit LH'
        assert n['von'] == datetime(2026, 11, 16, 0, 0)
        assert n['bis'] == datetime(2026, 11, 18, 23, 59)
        assert n['status'] == 'offen'

    def test_leeres_bis_bleibt_none(self, tmp_path):
        # Für News ist das leere Bis „nicht relevant“ → bleibt None statt Tagesende.
        pfad = self._datei(tmp_path, [
            ['N-001', 'Info', 'Hinweis', '16.11.2026', None, '', 'offen'],
        ])
        daten = lies_datei(str(pfad))
        assert daten['news'][0]['bis'] is None

    def test_ungueltige_art(self, tmp_path):
        pfad = self._datei(tmp_path, [
            ['N-001', 'Kalibrierung', 'Titel', '16.11.2026', None, '', 'offen'],
        ])
        daten = lies_datei(str(pfad))
        assert any('Art' in f['grund'] for f in daten['fehler'])

    def test_doppelte_nummer_aktiv_archiv(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['N-001', 'Audit', 'Audit 1', '16.11.2026', None, '', 'offen']],
            archiv=[['N-001', 'Info', 'Info 1', '01.12.2026', None, '',
                     'abgeschlossen']],
        )
        daten = lies_datei(str(pfad))
        assert any('Doppelte Nummer' in f['grund'] for f in daten['fehler'])


class TestZeiten:
    def _datei(self, tmp_path, termine, zeiten):
        return _schreibe(tmp_path / 'zeiten.xlsx', {
            'Termine': (KOPF_TERMINE, termine),
            'Zeiten': (KOPF_ZEITEN, zeiten),
        })

    def test_block(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Kalibrierung', 'Prüfstand', 'K1', '16.11.2026', None,
              '', 'offen', None]],
            [['T-001', datetime(2026, 11, 16, 8, 0),
              datetime(2026, 11, 16, 12, 0), 'Tag 1']],
        )
        daten = lies_datei(str(pfad))
        assert daten['bloecke']['T-001'] == [(datetime(2026, 11, 16, 8, 0),
                                              datetime(2026, 11, 16, 12, 0))]

    def test_nicht_t_referenz(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Kalibrierung', 'Prüfstand', 'K1', '16.11.2026', None,
              '', 'offen', None]],
            [['N-001', datetime(2026, 11, 16, 8, 0),
              datetime(2026, 11, 16, 12, 0), '']],
        )
        daten = lies_datei(str(pfad))
        assert daten['bloecke'] == {}
        assert any('Termin-Nr' in f['grund'] for f in daten['fehler'])

    def test_bis_vor_von(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Kalibrierung', 'Prüfstand', 'K1', '16.11.2026', None,
              '', 'offen', None]],
            [['T-001', datetime(2026, 11, 16, 12, 0),
              datetime(2026, 11, 16, 8, 0), '']],
        )
        daten = lies_datei(str(pfad))
        assert daten['bloecke'] == {}
        assert any('Bis liegt vor Von' in f['grund'] for f in daten['fehler'])

    def test_unbekannte_nummer(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [['T-001', 'Kalibrierung', 'Prüfstand', 'K1', '16.11.2026', None,
              '', 'offen', None]],
            [['T-999', datetime(2026, 11, 16, 8, 0),
              datetime(2026, 11, 16, 12, 0), '']],
        )
        daten = lies_datei(str(pfad))
        assert daten['bloecke'] == {}
        assert any('Unbekannte Termin-Nr' in f['grund'] for f in daten['fehler'])


class TestGenerator:
    def test_baue_und_pruefe(self, tmp_path):
        pfad = str(tmp_path / 'termine_modell3.xlsx')
        baue_vorlage(pfad)
        assert os.path.exists(pfad)
        assert pruefe(pfad) == []

    def test_blattnamen(self, tmp_path):
        pfad = str(tmp_path / 'termine_modell3.xlsx')
        baue_vorlage(pfad)
        wb = openpyxl.load_workbook(pfad)
        assert set(wb.sheetnames) == {'Termine', 'News & Audits', 'Betriebsmittel',
                                      'Zeiten', 'Archiv Termine',
                                      'Archiv News & Audits', 'Anleitung'}

    def test_ids_vorausgefuellt_eindeutig(self, tmp_path):
        pfad = str(tmp_path / 'termine_modell3.xlsx')
        baue_vorlage(pfad)
        wb = openpyxl.load_workbook(pfad)
        ids = [wb['Termine'].cell(row=r, column=1).value for r in range(2, 502)]
        assert ids == ['T-%03d' % i for i in range(1, 501)]
        nids = [wb['News & Audits'].cell(row=r, column=1).value for r in range(2, 502)]
        assert nids == ['N-%03d' % i for i in range(1, 501)]

    def test_bm_id_spalte_versteckt(self, tmp_path):
        pfad = str(tmp_path / 'termine_modell3.xlsx')
        baue_vorlage(pfad)
        wb = openpyxl.load_workbook(pfad)
        assert wb['Termine'].column_dimensions['I'].hidden is True
        assert wb['Archiv Termine'].column_dimensions['I'].hidden is True

    def test_template_parsen_leer(self, tmp_path):
        pfad = str(tmp_path / 'termine_modell3.xlsx')
        baue_vorlage(pfad)
        daten = lies_datei(pfad)
        assert daten['termine'] == []
        assert daten['news'] == []
        assert daten['bloecke'] == {}
        assert daten['archiv_termine'] == []
        assert daten['archiv_news'] == []
        assert daten['fehler'] == []
        assert len(daten['betriebsmittel']) >= 2
        assert daten['dateiname'] == 'termine_modell3.xlsx'

    def test_validierungs_flags(self, tmp_path):
        # Jede Auswahlliste muss ungültige Eingaben blockieren (showErrorMessage,
        # errorStyle=stop), den Hinweis zeigen (showInputMessage) und den Pfeil
        # anzeigen (showDropDown=False – OOXML „suppress dropdown“).
        pfad = str(tmp_path / 'termine_modell3.xlsx')
        baue_vorlage(pfad)
        wb = openpyxl.load_workbook(pfad)
        anz = 0
        for ws in wb.worksheets:
            for dv in ws.data_validations.dataValidation:
                anz += 1
                assert dv.type == 'list'
                assert dv.showErrorMessage is True, (ws.title, str(dv.sqref))
                assert dv.showInputMessage is True, (ws.title, str(dv.sqref))
                assert dv.showDropDown is False, (ws.title, str(dv.sqref))
                assert dv.errorStyle == 'stop', (ws.title, str(dv.sqref))
        assert anz > 0

    def test_pruefe_erkennt_fehlende_flags(self, tmp_path):
        pfad = str(tmp_path / 'termine_modell3.xlsx')
        baue_vorlage(pfad)
        wb = openpyxl.load_workbook(pfad)
        for ws in wb.worksheets:
            for dv in ws.data_validations.dataValidation:
                dv.showErrorMessage = False
        wb.save(pfad)
        maengel = pruefe(pfad)
        assert any('showErrorMessage' in m for m in maengel)

    def test_betriebsmittel_seed_enthaelt_alle_model2_pruefstaende(self, tmp_path):
        pfad = str(tmp_path / 'termine_modell3.xlsx')
        baue_vorlage(pfad)
        daten = lies_datei(pfad)
        typ_zu_name = {(e['typ'], e['bezeichnung']) for e in daten['betriebsmittel']}
        for name in MODEL2_AUSWAHLEN:
            assert ('Prüfstand', name) in typ_zu_name, name

    def test_konsolen_sind_typ_konsole(self, tmp_path):
        pfad = str(tmp_path / 'termine_modell3.xlsx')
        baue_vorlage(pfad)
        daten = lies_datei(pfad)
        typen = {e['bezeichnung']: e['typ'] for e in daten['betriebsmittel']}
        assert typen['TESTFUCHS KONSOLE 1'] == 'Konsole'
        assert typen['TESTFUCHS KONSOLE 2'] == 'Konsole'

    def test_kein_testfuchs_konsole_3(self, tmp_path):
        pfad = str(tmp_path / 'termine_modell3.xlsx')
        baue_vorlage(pfad)
        daten = lies_datei(pfad)
        namen = {e['bezeichnung'] for e in daten['betriebsmittel']}
        assert 'TESTFUCHS KONSOLE 3' not in namen

    def test_bm_ids_eindeutig(self, tmp_path):
        pfad = str(tmp_path / 'termine_modell3.xlsx')
        baue_vorlage(pfad)
        daten = lies_datei(pfad)
        ids = [e['id'] for e in daten['betriebsmittel']]
        assert all(ids)
        assert len(ids) == len(set(ids))

    def test_deterministisch(self, tmp_path):
        import hashlib
        a = str(tmp_path / 'a.xlsx')
        b = str(tmp_path / 'b.xlsx')
        baue_vorlage(a)
        baue_vorlage(b)
        ha = hashlib.sha256(open(a, 'rb').read()).hexdigest()
        hb = hashlib.sha256(open(b, 'rb').read()).hexdigest()
        assert ha == hb


@pytest.mark.skipif(not os.path.exists(VORLAGE), reason='Vorlage fehlt')
class TestVorlage:
    @pytest.fixture
    def daten(self):
        return lies_datei(VORLAGE)

    def test_fehlerfrei(self, daten):
        assert daten['fehler'] == []

    def test_betriebsmittel_getrennt(self, daten):
        namen = {e['bezeichnung'] for e in daten['betriebsmittel']}
        assert 'TESTFUCHS KONSOLE 1' in namen
        assert 'TESTFUCHS KONSOLE 2' in namen
