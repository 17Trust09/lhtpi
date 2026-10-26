"""Tests für den Excel-Parser (Modell 2)."""
import os
from datetime import datetime

import openpyxl
import pytest

from excel_modell2 import lies_datei, _zu_datetime

VORLAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'vorlagen', 'termine_modell2.xlsx')


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


@pytest.mark.skipif(not os.path.exists(VORLAGE), reason='Vorlage fehlt')
class TestVorlage:
    @pytest.fixture(scope='class')
    def daten(self):
        return lies_datei(VORLAGE)

    def test_sechs_termine(self, daten):
        assert len(daten['zeilen']) == 6

    def test_erste_zeile(self, daten):
        z = daten['zeilen'][0]
        assert z['nr'] == 1
        assert z['art'] == 'Wartung'
        assert z['pruefstand'] == 'P03 NRA'
        assert z['von'] == datetime(2026, 11, 2, 7, 0)
        assert z['bis'] == datetime(2026, 11, 2, 15, 0)
        assert z['status'] == 'abgeschlossen'

    def test_bloecke_der_kalibrierung(self, daten):
        assert 2 in daten['bloecke']
        assert len(daten['bloecke'][2]) == 4
        assert daten['bloecke'][2][0] == (datetime(2026, 11, 16, 8, 0),
                                          datetime(2026, 11, 16, 12, 0))

    def test_pruefstaende_gelesen(self, daten):
        assert len(daten['pruefstaende']) == 15
        assert 'P03 NRA' in daten['pruefstaende']
        assert 'P43 LOW-PRESSURE' in daten['pruefstaende']

    def test_keine_fehler(self, daten):
        assert daten['fehler'] == []


class TestFehlerzeilen:
    def _datei(self, tmp_path, termin_zeilen, zeiten_zeilen=None):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Termine'
        ws.append(['Nr', 'Art', 'Prüfstand', 'Von', 'Bis', 'Info', 'Status'])
        for z in termin_zeilen:
            ws.append(z)
        if zeiten_zeilen is not None:
            wz = wb.create_sheet('Zeiten')
            wz.append(['Termin', 'Von', 'Bis', 'Notiz'])
            for z in zeiten_zeilen:
                wz.append(z)
        pfad = tmp_path / 'test.xlsx'
        wb.save(pfad)
        return pfad

    def test_fehlende_nr_nimmt_zeilennummer(self, tmp_path):
        pfad = self._datei(tmp_path, [
            [None, 'Wartung', 'P03 NRA', '02.11.2026 07:00', '02.11.2026 15:00', 'x', 'offen'],
        ])
        daten = lies_datei(str(pfad))
        assert daten['zeilen'][0]['nr'] == 2   # Kopfzeile ist Zeile 1

    def test_leerer_status_wird_offen(self, tmp_path):
        pfad = self._datei(tmp_path, [
            [1, 'Wartung', 'P03 NRA', '02.11.2026 07:00', '02.11.2026 15:00', 'x', None],
        ])
        daten = lies_datei(str(pfad))
        assert daten['zeilen'][0]['status'] == 'offen'

    def test_zeiten_mit_bis_vor_von_werden_gemeldet(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [[1, 'Kalibrierung', 'P03 NRA', '16.11.2026 08:00', '16.11.2026 16:00', 'x', 'offen']],
            [[1, '16.11.2026 12:00', '16.11.2026 08:00', '']],
        )
        daten = lies_datei(str(pfad))
        assert len(daten['fehler']) == 1
        assert daten['bloecke'] == {}

    def test_zeiten_ohne_nr_gemeldet(self, tmp_path):
        pfad = self._datei(
            tmp_path,
            [[1, 'Kalibrierung', 'P03 NRA', '16.11.2026 08:00', '16.11.2026 16:00', 'x', 'offen']],
            [[None, '16.11.2026 08:00', '16.11.2026 12:00', '']],
        )
        daten = lies_datei(str(pfad))
        assert len(daten['fehler']) == 1
