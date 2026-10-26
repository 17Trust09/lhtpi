"""Tests für die Betriebszeit-Rechnung (Terminboard-Historie).

Regeln (festgelegt 2026-10-26):
  * Ein Betriebstag ist 06:00–22:45 (16,75 h), Montag bis Freitag.
  * Samstag, Sonntag und Hamburger Feiertage zählen nicht.
  * Ausfallstunden und Ausfalltage zählen nur innerhalb des Betriebsfensters.
"""
from datetime import date, datetime

import pytest

from betriebszeit import (
    BETRIEB_STUNDEN_PRO_TAG,
    betriebsstunden,
    betriebstage,
    ausfalltage,
    ausfalldauer,
    ist_betriebstag,
    feiertage_hamburg,
    osterdatum,
)


class TestFeiertage:
    def test_ostern_2026(self):
        assert osterdatum(2026) == date(2026, 4, 5)

    def test_ostern_2027(self):
        assert osterdatum(2027) == date(2027, 3, 28)

    def test_ostern_2024(self):
        assert osterdatum(2024) == date(2024, 3, 31)

    def test_hamburger_feiertage_2026(self):
        f = feiertage_hamburg(2026)
        assert date(2026, 1, 1) in f        # Neujahr
        assert date(2026, 4, 3) in f        # Karfreitag
        assert date(2026, 4, 6) in f        # Ostermontag
        assert date(2026, 5, 1) in f        # Tag der Arbeit
        assert date(2026, 5, 14) in f       # Himmelfahrt
        assert date(2026, 5, 25) in f       # Pfingstmontag
        assert date(2026, 10, 3) in f       # Deutsche Einheit
        assert date(2026, 10, 31) in f      # Reformationstag
        assert date(2026, 12, 25) in f
        assert date(2026, 12, 26) in f
        assert len(f) == 10

    def test_kein_fronleichnam_in_hamburg(self):
        f = feiertage_hamburg(2026)
        assert date(2026, 6, 4) not in f


class TestBetriebstag:
    def test_montag_ist_betriebstag(self):
        assert ist_betriebstag(date(2026, 10, 26)) is True   # Montag

    def test_samstag_ist_kein_betriebstag(self):
        assert ist_betriebstag(date(2026, 10, 24)) is False  # Samstag

    def test_sonntag_ist_kein_betriebstag(self):
        assert ist_betriebstag(date(2026, 10, 25)) is False  # Sonntag

    def test_feiertag_ist_kein_betriebstag(self):
        assert ist_betriebstag(date(2026, 10, 3)) is False   # Samstag + Feiertag
        assert ist_betriebstag(date(2026, 12, 25)) is False  # Freitag, Weihnachten


class TestBetriebsstunden:
    def test_ganzer_betriebstag(self):
        h = betriebsstunden(datetime(2026, 10, 26, 6, 0), datetime(2026, 10, 26, 22, 45))
        assert h == pytest.approx(16.75)

    def test_vor_und_nach_dem_fenster_zaehlt_nicht(self):
        h = betriebsstunden(datetime(2026, 10, 26, 0, 0), datetime(2026, 10, 27, 0, 0))
        assert h == pytest.approx(16.75)

    def test_halber_tag(self):
        h = betriebsstunden(datetime(2026, 10, 26, 8, 0), datetime(2026, 10, 26, 12, 0))
        assert h == pytest.approx(4.0)

    def test_wochenende_zaehlt_nicht(self):
        # Freitag 14:00 bis Montag 08:00
        h = betriebsstunden(datetime(2026, 10, 23, 14, 0), datetime(2026, 10, 26, 8, 0))
        assert h == pytest.approx(8.75 + 2.0)

    def test_block_nur_am_samstag(self):
        h = betriebsstunden(datetime(2026, 10, 24, 10, 0), datetime(2026, 10, 24, 12, 0))
        assert h == pytest.approx(0.0)

    def test_block_am_feiertag(self):
        h = betriebsstunden(datetime(2026, 12, 25, 8, 0), datetime(2026, 12, 25, 16, 0))
        assert h == pytest.approx(0.0)

    def test_mehrere_tage_mit_luecke(self):
        # Mo 08-12, Di 08-16, Do 07-11
        h = (betriebsstunden(datetime(2026, 10, 26, 8, 0), datetime(2026, 10, 26, 12, 0))
             + betriebsstunden(datetime(2026, 10, 27, 8, 0), datetime(2026, 10, 27, 16, 0))
             + betriebsstunden(datetime(2026, 10, 29, 7, 0), datetime(2026, 10, 29, 11, 0)))
        assert h == pytest.approx(4.0 + 8.0 + 4.0)

    def test_bis_vor_von_ist_null(self):
        h = betriebsstunden(datetime(2026, 10, 26, 12, 0), datetime(2026, 10, 26, 8, 0))
        assert h == pytest.approx(0.0)


class TestAusfalltag:
    def test_zwei_tage_freitag_bis_montag(self):
        tage = ausfalltage(datetime(2026, 10, 23, 14, 0), datetime(2026, 10, 26, 8, 0))
        assert tage == 2   # Freitag + Montag

    def test_samstag_zaehlt_nicht(self):
        tage = ausfalltage(datetime(2026, 10, 24, 10, 0), datetime(2026, 10, 24, 12, 0))
        assert tage == 0

    def test_ganze_woche(self):
        # Mo 26.10. bis Fr 30.10., durchgehend
        tage = ausfalltage(datetime(2026, 10, 26, 0, 0), datetime(2026, 10, 30, 23, 59))
        assert tage == 5


class TestAusfalldauer:
    def test_liefert_stunden_und_tage(self):
        dauer = ausfalldauer(datetime(2026, 10, 23, 14, 0), datetime(2026, 10, 26, 8, 0))
        assert dauer['stunden'] == pytest.approx(10.75)
        assert dauer['tage'] == 2

    def test_wochenende_ergibt_null(self):
        dauer = ausfalldauer(datetime(2026, 10, 24, 0, 0), datetime(2026, 10, 25, 23, 59))
        assert dauer['stunden'] == pytest.approx(0.0)
        assert dauer['tage'] == 0

    def test_konstante(self):
        assert BETRIEB_STUNDEN_PRO_TAG == pytest.approx(16.75)


class TestRandfaelle:
    def test_block_ueber_mitternacht(self):
        # Mo 22:00 bis Di 02:00 → nur 22:00–22:45 am Montag
        h = betriebsstunden(datetime(2026, 10, 26, 22, 0), datetime(2026, 10, 27, 2, 0))
        assert h == pytest.approx(0.75)

    def test_exakt_auf_den_grenzen(self):
        h = betriebsstunden(datetime(2026, 10, 26, 6, 0), datetime(2026, 10, 26, 22, 45))
        assert h == pytest.approx(16.75)

    def test_eine_minute_vor_und_nach_dem_fenster(self):
        h = betriebsstunden(datetime(2026, 10, 26, 5, 59), datetime(2026, 10, 26, 22, 46))
        assert h == pytest.approx(16.75)

    def test_schalttag_zaehlt_als_betriebstag(self):
        # 29.02.2028 ist ein Dienstag
        assert ist_betriebstag(date(2028, 2, 29)) is True
        h = betriebsstunden(datetime(2028, 2, 29, 6, 0), datetime(2028, 2, 29, 22, 45))
        assert h == pytest.approx(16.75)

    def test_jahreswechsel(self):
        # Do 31.12.2026 08:00 bis Mo 04.01.2027 12:00
        h = betriebsstunden(datetime(2026, 12, 31, 8, 0), datetime(2027, 1, 4, 12, 0))
        # 31.12.: 8–22:45 = 14,75 h; 1.1. Feiertag; 2./3.1. Wochenende; 4.1.: 6–12 = 6 h
        assert h == pytest.approx(20.75)

    def test_mehrere_bloecke_am_selben_tag_ergeben_einen_tag(self):
        from betriebszeit import ausfalldauer_bloecke
        dauer = ausfalldauer_bloecke([
            (datetime(2026, 10, 26, 8, 0), datetime(2026, 10, 26, 10, 0)),
            (datetime(2026, 10, 26, 14, 0), datetime(2026, 10, 26, 16, 0)),
        ])
        assert dauer['stunden'] == pytest.approx(4.0)
        assert dauer['tage'] == 1
