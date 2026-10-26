"""Excel-Formate: Der Kiosk muss beide Vorlagen lesen können.

Im Umlauf sind zwei Formate:
  alt – Art, Prüfstand, Von, Bis, Info (fünf Spalten, ohne Nummer)
  neu – Nr, Art, Prüfstand, Von, Bis, Info, Status (Modell 2)

Beide müssen dieselben Termine ergeben, sonst zeigt das Board bei der neuen
Vorlage nichts oder die falschen Zeilen.
"""
import os

import openpyxl
import pytest

from usb_source import parse_termin_xlsx, USB_XLSX_FILENAME

VORLAGE_NEU = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'vorlagen', 'termine_modell2.xlsx')


def _altes_format(pfad):
    """Baut eine Datei im alten Format (ohne Nr und Status)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Termine'
    ws.append(['Art', 'Prüfstand', 'Von', 'Bis', 'Info'])
    ws.append(['Wartung', 'P03 NRA', '2026-11-02', '2026-11-02', 'Jahreswartung'])
    ws.append(['Kalibrierung', 'P10 PTU TESTFUCHS', '2026-11-16', '2026-11-21', 'Messkette'])
    wb.save(pfad)
    return pfad


class TestNeuesFormat:
    def test_vorlage_wird_vollstaendig_gelesen(self):
        if not os.path.exists(VORLAGE_NEU):
            pytest.skip('Vorlage fehlt')
        zeilen = parse_termin_xlsx(VORLAGE_NEU)
        assert zeilen is not None
        assert len(zeilen) == 6

    def test_spalten_verrutschen_nicht(self):
        if not os.path.exists(VORLAGE_NEU):
            pytest.skip('Vorlage fehlt')
        erste = parse_termin_xlsx(VORLAGE_NEU)[0]
        assert erste['referenz'] == 'P03 NRA'      # nicht die Nummer, nicht die Art
        assert erste['typ'] == 'wartung'
        assert erste['start'].isoformat() == '2026-11-02'
        assert erste['titel'] == 'Jahreswartung Hydraulik'

    def test_info_zeile_bekommt_einen_titel(self):
        if not os.path.exists(VORLAGE_NEU):
            pytest.skip('Vorlage fehlt')
        zeilen = parse_termin_xlsx(VORLAGE_NEU)
        ohne_info = [z for z in zeilen if not z['titel']]
        assert ohne_info == []


class TestAltesFormat:
    """Das alte Fünf-Spalten-Format wird nicht mehr gelesen.

    Es würde spaltenweise verrutschen (Nummer fehlt vorne) und falsche Termine
    anzeigen. Statt stumm leer zu bleiben, gibt es eine klare Meldung.
    """

    def test_altes_format_wird_abgelehnt(self, tmp_path):
        pfad = _altes_format(str(tmp_path / 'alt.xlsx'))
        assert parse_termin_xlsx(pfad) is None

    def test_altes_format_nennt_den_grund(self, tmp_path):
        from excel_modell2 import lies_datei
        daten = lies_datei(_altes_format(str(tmp_path / 'alt.xlsx')))
        assert daten['zeilen'] == []
        assert 'Alte Vorlage' in daten['fehler'][0]['grund']


class TestFehlerfaelle:
    def test_fehlende_datei_ergibt_none(self):
        assert parse_termin_xlsx('/gibt/es/nicht.xlsx') is None


class TestExcelKonverter:
    """Der Konverter übernimmt Zeilen aus dem alten Fünf-Spalten-Format."""

    def test_alte_zeilen_landen_im_neuen_format(self, tmp_path):
        import openpyxl
        from tools_excel_konverter import konvertiere
        alt = tmp_path / 'alt.xlsx'
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Termine'
        ws.append(['Art', 'Prüfstand', 'Von', 'Bis', 'Info'])
        ws.append(['Wartung', 'P03 NRA', '02.11.2026', '02.11.2026', 'Jahreswartung'])
        ws.append(['Kalibrierung', 'P10 PTU TESTFUCHS', '16.11.2026', '21.11.2026', 'Messkette'])
        wb.save(alt)

        ziel = tmp_path / 'neu.xlsx'
        ergebnis = konvertiere(str(alt), str(ziel))

        assert ergebnis['uebernommen'] == 2
        assert ergebnis['uebersprungen'] == []

        neu = openpyxl.load_workbook(ziel)
        ws2 = neu['Termine']
        kopf = [c.value for c in ws2[1]]
        assert kopf[:7] == ['Nr', 'Art', 'Prüfstand', 'Von', 'Bis', 'Info', 'Status']
        zeile1 = [c.value for c in ws2[2]]
        assert zeile1[0] == 1
        assert zeile1[1] == 'Wartung'
        assert zeile1[2] == 'P03 NRA'
        assert zeile1[6] == 'offen'

    def test_fehlende_zeilen_werden_gemeldet(self, tmp_path):
        import openpyxl
        from tools_excel_konverter import konvertiere
        alt = tmp_path / 'alt.xlsx'
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Termine'
        ws.append(['Art', 'Prüfstand', 'Von', 'Bis', 'Info'])
        ws.append(['Wartung', 'P03 NRA', '02.11.2026', '02.11.2026', 'ok'])
        ws.append(['', 'P04 NRA', '03.11.2026', '', 'ohne Art'])
        ws.append(['Wartung', '', '04.11.2026', '', 'ohne Prüfstand'])
        wb.save(alt)

        ergebnis = konvertiere(str(alt), str(tmp_path / 'neu.xlsx'))
        assert ergebnis['uebernommen'] == 1
        assert len(ergebnis['uebersprungen']) == 2

    def test_blaetter_der_neuen_vorlage_entstehen(self, tmp_path):
        import openpyxl
        from tools_excel_konverter import konvertiere
        alt = tmp_path / 'alt.xlsx'
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Termine'
        ws.append(['Art', 'Prüfstand', 'Von', 'Bis', 'Info'])
        ws.append(['Wartung', 'P03 NRA', '02.11.2026', '02.11.2026', 'ok'])
        wb.save(alt)

        ziel = tmp_path / 'neu.xlsx'
        konvertiere(str(alt), str(ziel))
        neu = openpyxl.load_workbook(ziel)
        for blatt in ('Termine', 'Zeiten', 'Prüfstände', 'Archiv', 'Anleitung'):
            assert blatt in neu.sheetnames, blatt
