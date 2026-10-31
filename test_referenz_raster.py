"""Tests für die Referenz-Aufloesung (proportionale Skalierung).

Prüft ohne Hardware das Verhalten von
``bildschirm_info.physische_groesse_mm``, ``bildschirm_info.dpi``,
``bildschirm_info.aktuelle_aufloesung`` und ``anzeige_fein.skalierungs_faktor``.

Aufruf:  ./venv/bin/python -m pytest test_referenz_raster.py
"""
import pytest

import anzeige_fein
import bildschirm_info


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


# ── Skalierungsfaktor (proportional zur Aufloesung) ──────────────────────────

def test_faktor_full_hd_ist_1(monkeypatch):
    monkeypatch.setattr(bildschirm_info, 'aktuelle_aufloesung',
                        lambda ausgang: '1920x1080')
    assert anzeige_fein.skalierungs_faktor('HDMI-1') == 1.0


def test_faktor_kleiner_bildschirm_verkleinert(monkeypatch):
    monkeypatch.setattr(bildschirm_info, 'aktuelle_aufloesung',
                        lambda ausgang: '1366x768')
    assert anzeige_fein.skalierungs_faktor('HDMI-1') == pytest.approx(
        min(1366 / 1920, 768 / 1080), rel=1e-9)


def test_faktor_4k_vergroessert(monkeypatch):
    monkeypatch.setattr(bildschirm_info, 'aktuelle_aufloesung',
                        lambda ausgang: '3840x2160')
    assert anzeige_fein.skalierungs_faktor('HDMI-1') == pytest.approx(2.0, rel=1e-9)


def test_faktor_unbekannte_aufloesung_ist_1(monkeypatch):
    monkeypatch.setattr(bildschirm_info, 'aktuelle_aufloesung',
                        lambda ausgang: None)
    assert anzeige_fein.skalierungs_faktor('HDMI-1') == 1.0


def test_faktor_ist_begrenzt(monkeypatch):
    monkeypatch.setattr(bildschirm_info, 'aktuelle_aufloesung',
                        lambda ausgang: '20000x20000')
    assert anzeige_fein.skalierungs_faktor('HDMI-1') == anzeige_fein.FAKTOR_MAX
    monkeypatch.setattr(bildschirm_info, 'aktuelle_aufloesung',
                        lambda ausgang: '1x1')
    assert anzeige_fein.skalierungs_faktor('HDMI-1') == anzeige_fein.FAKTOR_MIN


def test_faktor_abweichendes_seitenverhaeltnis(monkeypatch):
    """Bei abweichendem Seitenverhaeltnis zaehlt das kleinere Verhaeltnis."""
    # 1920x1200 (16:10): Breite = 1.0, Hoehe = 1200/1080 -> min = 1.0 (Breite).
    monkeypatch.setattr(bildschirm_info, 'aktuelle_aufloesung',
                        lambda ausgang: '1920x1200')
    assert anzeige_fein.skalierungs_faktor('HDMI-1') == 1.0
