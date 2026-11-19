"""Tests für den Modell-2→Modell-3-Konverter (tools_modell2_zu_modell3)."""
import os
from datetime import date, datetime
from pathlib import Path

import openpyxl
import pytest

from tools_modell2_zu_modell3 import (
    konvertiere,
    pruefe_erzeugt,
    ist_konsole,
    main,
    _zeitwert,
)


def _quelle(pfad):
    """Baut eine Modell-2-Mappe mit Terminen, News, Archiv und Zeiten."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Termine'
    ws.append(['Nr', 'Art', 'Prüfstand', 'Von', 'Bis', 'Info', 'Status'])
    ws.append([1, 'Kalibrierung', 'P31 THSA', date(2026, 11, 2),
               date(2026, 11, 2), 'Jahreswartung', 'offen'])
    ws.append([2, 'Wartung', 'TESTFUCHS KONSOLE 1', date(2026, 11, 3),
               date(2026, 11, 3), 'Konsolenwartung', 'offen'])
    ws.append([3, 'Audit', '', date(2026, 11, 16), None, 'Audit LH', 'offen'])
    ws.append([4, 'Info', '', date(2026, 11, 17), None, 'Meldung', 'offen'])
    ws.append([5, 'Ausfall', 'TESTTUCHS KONSOLE 9', date(2026, 11, 4),
               date(2026, 11, 4), 'Defekt', 'offen'])

    arch = wb.create_sheet('Archiv')
    arch.append(['Nr', 'Art', 'Prüfstand', 'Von', 'Bis', 'Info', 'Status'])
    arch.append([6, 'Kalibrierung', 'P31 THSA', date(2026, 10, 5),
                 date(2026, 10, 5), 'Alte Kalibrierung', 'abgeschlossen'])

    zeiten = wb.create_sheet('Zeiten')
    zeiten.append(['Termin (Nr)', 'Von', 'Bis', 'Notiz'])
    zeiten.append([1, datetime(2026, 11, 2, 7, 0), datetime(2026, 11, 2, 15, 0),
                   'Block A'])
    zeiten.append([6, datetime(2026, 10, 5, 8, 0), datetime(2026, 10, 5, 12, 0),
                   'Archiv-Block'])
    zeiten.append([3, datetime(2026, 11, 16, 9, 0), datetime(2026, 11, 16, 10, 0),
                   'gehört zu einem Audit'])

    ps = wb.create_sheet('Prüfstände')
    ps.append(['Kennung', 'Bezeichnung', 'Auswahl (für Dropdown)'])
    ps.append(['P31', 'THSA', 'P31 THSA'])
    ps.append(['K1', 'KONSOLE', 'TESTFUCHS KONSOLE 1'])
    ps.append(['T1', 'TUCHS', 'TESTTUCHS KONSOLE 9'])
    wb.save(pfad)


class TestKlassifikation:
    def test_ist_konsole_exakte_praefixe(self):
        assert ist_konsole('TESTFUCHS KONSOLE 1') is True
        assert ist_konsole('TESTFUCHS KONSOLE 42') is True
        assert ist_konsole('testfuchs konsole 2') is True
        assert ist_konsole('TESTTUCHS KONSOLE 9') is True     # exakt so eingetragen
        assert ist_konsole('P31 THSA') is False
        assert ist_konsole('TESTFUCHS PRÜFSTAND') is False

    def test_kein_fuzzy_umbenennen(self):
        # Die TESTTUCHS-Schreibweise bleibt ihr eigener Name, wird aber als
        # Konsole erkannt – es gibt keine unscharfe Korrektur zu TESTFUCHS.
        assert ist_konsole('TESTTUCHS KONSOLE 9') is True


class TestKonvertierung:
    def test_konvertiere_erzeugt_modell3_und_laesst_quelle_an(self, tmp_path):
        quelle = tmp_path / 'alt.xlsx'
        ziel = tmp_path / 'neu.xlsx'
        _quelle(quelle)
        vorher = quelle.read_bytes()

        bericht = konvertiere(str(quelle), str(ziel))

        assert bericht['uebernommen_termine'] == 4     # 3 aktiv + 1 Archiv
        assert bericht['uebernommen_news'] == 2        # Audit + Info
        assert bericht['maengel'] == []
        assert quelle.read_bytes() == vorher           # Quelle unverändert

        from excel_modell3 import lies_datei
        daten = lies_datei(str(ziel))
        assert daten['fehler'] == []

        termine = {t['nr']: t for t in daten['termine']}
        assert set(termine) == {'T-001', 'T-002', 'T-003'}
        assert termine['T-001']['art'] == 'Kalibrierung'
        assert termine['T-001']['betriebsmittel'] == 'P31 THSA'
        assert termine['T-002']['art'] == 'Wartung'
        assert termine['T-002']['betriebsmittel'] == 'TESTFUCHS KONSOLE 1'
        assert termine['T-003']['art'] == 'Ausfall'
        assert termine['T-003']['betriebsmittel'] == 'TESTTUCHS KONSOLE 9'

        assert [t['nr'] for t in daten['archiv_termine']] == ['T-004']

        news = {n['nr']: n for n in daten['news']}
        assert set(news) == {'N-001', 'N-002'}
        assert news['N-001']['art'] == 'Audit'
        assert news['N-002']['art'] == 'Info'

    def test_betriebsmittel_typen_und_stabile_ids(self, tmp_path):
        quelle = tmp_path / 'alt.xlsx'
        ziel = tmp_path / 'neu.xlsx'
        _quelle(quelle)
        bericht = konvertiere(str(quelle), str(ziel))

        from excel_modell3 import lies_datei
        bms = {b['bezeichnung']: b for b in lies_datei(str(ziel))['betriebsmittel']}
        assert bms['P31 THSA']['typ'] == 'Prüfstand'
        assert bms['TESTFUCHS KONSOLE 1']['typ'] == 'Konsole'
        assert bms['TESTTUCHS KONSOLE 9']['typ'] == 'Konsole'

        neue = {b['bezeichnung']: b['kennung'] for b in bericht['neue_betriebsmittel']}
        assert 'TESTTUCHS KONSOLE 9' in neue
        assert neue['TESTTUCHS KONSOLE 9'].startswith('BM-')

    def test_zeiten_werden_abgebildet_und_unmappbares_gemeldet(self, tmp_path):
        quelle = tmp_path / 'alt.xlsx'
        ziel = tmp_path / 'neu.xlsx'
        _quelle(quelle)
        bericht = konvertiere(str(quelle), str(ziel))

        from excel_modell3 import lies_datei
        bloecke = lies_datei(str(ziel))['bloecke']
        assert 'T-001' in bloecke             # Nr 1 → T-001
        assert 'T-004' in bloecke             # Nr 6 (Archiv) → T-004
        assert len(bloecke['T-001']) == 1

        unmappbar = {z['nr'] for z in bericht['unmappbare_zeiten']}
        assert 3 in unmappbar                 # Nr 3 gehört zu einem Audit

    def test_ersetzen_sichert_und_ersetzt_quelle(self, tmp_path):
        quelle = tmp_path / 'alt.xlsx'
        _quelle(quelle)
        vorher = quelle.read_bytes()

        bericht = konvertiere(str(quelle), str(quelle), ersetzen=True)

        # Zeitgestempelte Sicherung (kein einzelnes festes .bak), Inhalt = Quelle.
        sicherung = Path(bericht['sicherung'])
        assert sicherung.exists()
        assert sicherung.read_bytes() == vorher
        assert bericht['ersetzt'] is True
        assert bericht['ziel'] == str(quelle)
        assert bericht['maengel'] == []

        # Die Quelle ist jetzt eine gültige Modell-3-Mappe.
        assert _ist_modell3(str(quelle)) is True
        assert pruefe_erzeugt(str(quelle)) == []

    def test_ersetzen_bei_maengel_laesst_quelle_unangetastet(self, tmp_path,
                                                            monkeypatch):
        quelle = tmp_path / 'alt.xlsx'
        _quelle(quelle)
        vorher = quelle.read_bytes()

        # Erzwungener Validierungsmangel: die erzeugte Mappe ist "defekt".
        monkeypatch.setattr('tools_modell2_zu_modell3.pruefe_erzeugt',
                            lambda pfad: ['Generator: erzwungener Defekt'])

        bericht = konvertiere(str(quelle), str(quelle), ersetzen=True)

        assert bericht['maengel'] == ['Generator: erzwungener Defekt']
        assert bericht['ersetzt'] is False
        assert bericht['sicherung'] is None
        assert bericht['ziel'] == str(quelle)
        assert quelle.read_bytes() == vorher          # Quelle unverändert
        assert _ist_modell2(str(quelle)) is True      # weiterhin Modell 2
        assert list(tmp_path.glob('*.bak')) == []     # nichts gesichert
        # Die fehlerhafte Mappe bleibt für die Diagnose stehen.
        assert bericht['diagnose'] is not None
        assert os.path.exists(bericht['diagnose'])

    def test_sicherung_pfad_ueberschreibt_nie_vorhandenes_bak(self, tmp_path,
                                                             monkeypatch):
        from tools_modell2_zu_modell3 import _sicherung_pfad
        quelle = str(tmp_path / 'alt.xlsx')

        # Festen Zeitstempel erzwingen, damit der Kollisionsfall eintritt.
        class _Fest:
            @staticmethod
            def now():
                return datetime(2026, 1, 1, 0, 0, 0, 0)

        monkeypatch.setattr('tools_modell2_zu_modell3.datetime', _Fest)

        p1 = _sicherung_pfad(quelle)
        Path(p1).write_bytes(b'bereits vorhanden')
        p2 = _sicherung_pfad(quelle)
        assert p1 != p2
        assert Path(p1).read_bytes() == b'bereits vorhanden'  # nicht überschrieben
        assert not Path(p2).exists()

    def test_storniert_wird_gemeldet_nicht_uebernommen(self, tmp_path):
        quelle = tmp_path / 'alt.xlsx'
        _quelle(quelle)
        wb = openpyxl.load_workbook(quelle)
        wb['Termine'].append([7, 'Kalibrierung', 'P31 THSA', date(2026, 12, 1),
                              date(2026, 12, 1), 'versehentlich', 'storniert'])
        wb.save(quelle)

        ziel = tmp_path / 'neu.xlsx'
        bericht = konvertiere(str(quelle), str(ziel))
        assert bericht['uebernommen_termine'] == 4       # storniert nicht mitgezählt
        assert any('storniert' in s['grund']
                   for s in bericht['uebersprungen'])
        assert bericht['maengel'] == []


def _ist_modell3(pfad):
    wb = openpyxl.load_workbook(pfad, read_only=True)
    namen = set(wb.sheetnames)
    wb.close()
    return 'Betriebsmittel' in namen or 'News & Audits' in namen


def _ist_modell2(pfad):
    wb = openpyxl.load_workbook(pfad, read_only=True)
    namen = set(wb.sheetnames)
    wb.close()
    return 'Termine' in namen and 'News & Audits' not in namen


class TestCLI:
    def test_cli_konvertiert(self, tmp_path):
        quelle = tmp_path / 'alt.xlsx'
        ziel = tmp_path / 'neu.xlsx'
        _quelle(quelle)
        code = main(['--quelle', str(quelle), '--ziel', str(ziel)])
        assert code == 0
        assert ziel.exists()
        assert _ist_modell3(str(ziel)) is True

    def test_cli_pruefen(self, tmp_path):
        quelle = tmp_path / 'alt.xlsx'
        ziel = tmp_path / 'neu.xlsx'
        _quelle(quelle)
        konvertiere(str(quelle), str(ziel))
        code = main(['--ziel', str(ziel), '--pruefen'])
        assert code == 0

    def test_cli_pruefen_positional(self, tmp_path):
        quelle = tmp_path / 'alt.xlsx'
        ziel = tmp_path / 'neu.xlsx'
        _quelle(quelle)
        konvertiere(str(quelle), str(ziel))
        code = main(['--pruefen', str(ziel)])
        assert code == 0

    def test_cli_pruefen_mit_quelle_wird_abgelehnt(self, tmp_path):
        quelle = tmp_path / 'alt.xlsx'
        _quelle(quelle)
        code = main(['--quelle', str(quelle), '--pruefen'])
        assert code == 2

    def test_cli_pruefen_ohne_datei_fehlschlaegt(self):
        assert main(['--pruefen']) == 2

    def test_cli_ersetzen_mit_abweichendem_ziel_wird_abgelehnt(self, tmp_path):
        quelle = tmp_path / 'alt.xlsx'
        ziel = tmp_path / 'neu.xlsx'
        _quelle(quelle)
        code = main(['--quelle', str(quelle), '--ersetzen', '--ziel', str(ziel)])
        assert code == 2
        assert _ist_modell2(str(quelle))          # Quelle unverändert
        assert not ziel.exists()


class TestSicherheit:
    def test_quelle_gleich_ziel_ohne_ersetzen_wird_abgelehnt(self, tmp_path):
        quelle = tmp_path / 'alt.xlsx'
        _quelle(quelle)
        vorher = quelle.read_bytes()
        with pytest.raises(ValueError):
            konvertiere(str(quelle), str(quelle))
        assert quelle.read_bytes() == vorher       # nichts überschrieben

    def test_korrupte_quelle_wirft_klare_fehler(self, tmp_path):
        quelle = tmp_path / 'kaputt.xlsx'
        quelle.write_bytes(b'kein zip, sondern m\xc3\xbcll')
        with pytest.raises(ValueError) as info:
            konvertiere(str(quelle), str(tmp_path / 'neu.xlsx'))
        assert 'nicht lesbar' in str(info.value)

    def test_cli_korrupte_quelle_meldet_fehler_statt_traceback(self, tmp_path,
                                                               capsys):
        quelle = tmp_path / 'kaputt.xlsx'
        quelle.write_bytes(b'kein zip')
        code = main(['--quelle', str(quelle),
                     '--ziel', str(tmp_path / 'neu.xlsx')])
        assert code == 1
        assert 'FEHLER' in capsys.readouterr().out


class TestPraezision:
    def test_zeitwert_erhaelt_uhrzeit(self):
        assert _zeitwert(datetime(2026, 11, 2, 7, 0)) == \
            datetime(2026, 11, 2, 7, 0)
        assert _zeitwert(date(2026, 11, 2)) == datetime(2026, 11, 2, 0, 0)
        assert _zeitwert(None) is None
        assert _zeitwert('unsinn') is None

    def test_intraday_zeiten_bleiben_erhalten(self, tmp_path):
        quelle = tmp_path / 'alt.xlsx'
        ziel = tmp_path / 'neu.xlsx'
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Termine'
        ws.append(['Nr', 'Art', 'Prüfstand', 'Von', 'Bis', 'Info', 'Status'])
        ws.append([1, 'Kalibrierung', 'P31 THSA',
                   datetime(2026, 11, 2, 7, 0), datetime(2026, 11, 2, 15, 0),
                   'Block', 'offen'])
        ps = wb.create_sheet('Prüfstände')
        ps.append(['Kennung', 'Bezeichnung', 'Auswahl (für Dropdown)'])
        ps.append(['P31', 'THSA', 'P31 THSA'])
        wb.save(quelle)

        bericht = konvertiere(str(quelle), str(ziel))
        assert bericht['maengel'] == []

        from excel_modell3 import lies_datei
        daten = lies_datei(str(ziel))
        assert daten['fehler'] == []
        t = daten['termine'][0]
        assert t['von'] == datetime(2026, 11, 2, 7, 0)
        assert t['bis'] == datetime(2026, 11, 2, 15, 0)

    def test_blanke_auswahl_verwendet_nur_bezeichnung(self):
        from excel_modell2 import lies_pruefstandblatt
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['Kennung', 'Bezeichnung', 'Auswahl (für Dropdown)'])
        ws.append(['P31', 'THSA', None])
        ws.append(['K1', 'KONSOLE', 'TESTFUCHS KONSOLE 1'])
        namen = lies_pruefstandblatt(ws)
        assert namen == ['THSA', 'TESTFUCHS KONSOLE 1']
        assert 'P31 THSA' not in namen

    def test_doppelte_alte_nummer_wird_gemeldet_und_zeiten_bleiben_unmappbar(
            self, tmp_path):
        quelle = tmp_path / 'alt.xlsx'
        ziel = tmp_path / 'neu.xlsx'
        _quelle(quelle)
        wb = openpyxl.load_workbook(quelle)
        # Alte Nummer 1 taucht zusätzlich im Archiv auf → mehrdeutig.
        wb['Archiv'].append([1, 'Kalibrierung', 'P31 THSA',
                             date(2026, 9, 1), date(2026, 9, 1),
                             'Duplikat', 'abgeschlossen'])
        wb.save(quelle)

        bericht = konvertiere(str(quelle), str(ziel))

        mehrdeutig = {z['nr'] for z in bericht['mehrdeutige_nummern']}
        assert 1 in mehrdeutig
        # Zeiten, die auf Nr 1 verweisen, werden nicht stillschweigend
        # dem letzten Treffer zugewiesen, sondern gemeldet.
        unmappbar = {z['nr'] for z in bericht['unmappbare_zeiten']}
        assert 1 in unmappbar
