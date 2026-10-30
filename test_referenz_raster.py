"""Tests für das Referenz-Raster (konstante physische Groesse).

Prüft ohne Hardware die Herleitung und das Verhalten von
``anzeige_fein.referenz_dpi()``, ``bildschirm_info.physische_groesse_mm``,
``bildschirm_info.dpi`` und ``anzeige_fein.skalierungs_faktor``.

Aufruf:  ./venv/bin/python -m pytest test_referenz_raster.py
"""
import math

import pytest

import anzeige_fein
import bildschirm_info


# ── Referenz-DPI ─────────────────────────────────────────────────────────────

def test_referenz_dpi_standard():
    # 55-Zoll-Display, 4096x2160, 150 % Zoom -> DPI_des_Schirms / 1,5.
    diagonale_px = math.hypot(anzeige_fein.REFERENZ_BREITE, anzeige_fein.REFERENZ_HOEHE)
    erwartet = (diagonale_px / 55.0) / anzeige_fein.REFERENZ_ZOOM
    assert anzeige_fein.referenz_dpi() == pytest.approx(erwartet, rel=1e-9)


def test_referenz_dpi_env_override(monkeypatch):
    monkeypatch.setenv('LHTPI_REFERENZ_DPI', '60.0')
    assert anzeige_fein.referenz_dpi() == 60.0


def test_referenz_dpi_env_zoll(monkeypatch):
    monkeypatch.delenv('LHTPI_REFERENZ_DPI', raising=False)
    monkeypatch.setenv('LHTPI_REFERENZ_ZOLL', '43')
    diagonale_px = math.hypot(anzeige_fein.REFERENZ_BREITE, anzeige_fein.REFERENZ_HOEHE)
    assert anzeige_fein.referenz_dpi() == pytest.approx(
        (diagonale_px / 43.0) / anzeige_fein.REFERENZ_ZOOM, rel=1e-9)


# ── EDID / DPI ───────────────────────────────────────────────────────────────

def _edid_bytes(breite_cm, hoehe_cm):
    roh = bytearray(128)
    roh[:8] = b'\x00\xff\xff\xff\xff\xff\xff\x00'
    roh[21] = breite_cm
    roh[22] = hoehe_cm
    return bytes(roh)


def test_physische_groesse_aus_edid(tmp_path, monkeypatch):
    edid = tmp_path / 'edid'
    edid.write_bytes(_edid_bytes(120, 68))  # 1200 x 680 mm
    monkeypatch.setattr(bildschirm_info, '_edid_datei', lambda ausgang: str(edid))
    monkeypatch.setattr(bildschirm_info, '_mm_aus_xrandr',
                        lambda ausgang: (None, None))
    assert bildschirm_info.physische_groesse_mm('HDMI-1') == (1200, 680)


def test_physische_groesse_fallback_xrandr(monkeypatch):
    monkeypatch.setattr(bildschirm_info, '_edid_datei', lambda ausgang: None)
    monkeypatch.setattr(bildschirm_info, '_mm_aus_xrandr',
                        lambda ausgang: (697, 392))
    assert bildschirm_info.physische_groesse_mm('HDMI-1') == (697, 392)


def test_edid_ohne_groesse_faellt_zurueck(tmp_path, monkeypatch):
    edid = tmp_path / 'edid'
    edid.write_bytes(_edid_bytes(0, 0))  # 0 = nicht gemeldet
    monkeypatch.setattr(bildschirm_info, '_edid_datei', lambda ausgang: str(edid))
    monkeypatch.setattr(bildschirm_info, '_mm_aus_xrandr',
                        lambda ausgang: (800, 450))
    assert bildschirm_info.physische_groesse_mm('HDMI-1') == (800, 450)


def test_dpi_berechnung(monkeypatch):
    monkeypatch.setattr(bildschirm_info, 'physische_groesse_mm',
                        lambda ausgang: (1200.0, 680.0))
    monkeypatch.setattr(bildschirm_info, 'aktuelle_aufloesung',
                        lambda ausgang: '4096x2160')
    # 4096 px auf 1200 mm = 4096 / (1200/25.4) = 86.7 DPI
    assert bildschirm_info.dpi('HDMI-1') == pytest.approx(4096 * 25.4 / 1200.0)


def test_dpi_unbekannt(monkeypatch):
    monkeypatch.setattr(bildschirm_info, 'physische_groesse_mm',
                        lambda ausgang: (None, None))
    assert bildschirm_info.dpi('HDMI-1') is None


# ── Skalierungsfaktor ────────────────────────────────────────────────────────

def test_faktor_bei_referenz_dpi_ist_150_prozent(monkeypatch):
    dpi_ref = math.hypot(anzeige_fein.REFERENZ_BREITE, anzeige_fein.REFERENZ_HOEHE) / 55.0
    monkeypatch.setattr(bildschirm_info, 'dpi', lambda ausgang: dpi_ref)
    assert anzeige_fein.skalierungs_faktor('HDMI-1') == pytest.approx(1.5, rel=1e-9)


def test_faktor_unbekannte_dpi_ist_1(monkeypatch):
    monkeypatch.setattr(bildschirm_info, 'dpi', lambda ausgang: None)
    assert anzeige_fein.skalierungs_faktor('HDMI-1') == 1.0


def test_faktor_ist_begrenzt(monkeypatch):
    monkeypatch.setattr(bildschirm_info, 'dpi', lambda ausgang: 1_000_000.0)
    assert anzeige_fein.skalierungs_faktor('HDMI-1') == anzeige_fein.FAKTOR_MAX
    monkeypatch.setattr(bildschirm_info, 'dpi', lambda ausgang: 0.1)
    assert anzeige_fein.skalierungs_faktor('HDMI-1') == anzeige_fein.FAKTOR_MIN


def test_physische_groesse_bleibt_konstant(monkeypatch):
    """Kern-Zusage: CSS_px * Faktor / DPI ist unabhaengig von der DPI."""
    referenz = anzeige_fein.referenz_dpi()
    breite_css = 320.0  # z. B. die Sidebar
    groessen = set()
    for dpi in (84.193, 91.8, 138.0, 50.0):
        monkeypatch.setattr(bildschirm_info, 'dpi', lambda ausgang, d=dpi: d)
        faktor = anzeige_fein.skalierungs_faktor('HDMI-1')
        # physische Breite in Zoll
        groessen.add(breite_css * faktor / dpi)
    # alle identisch (bis auf Rundung durch Faktor-Clamping irrelevant hier)
    assert len(groessen) == 1
    # und gleich der Referenz-Groesse breite_css / referenz_dpi
    assert groessen.pop() == pytest.approx(breite_css / referenz, rel=1e-9)
