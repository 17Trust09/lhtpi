"""Anzeige-Einstellungen je Bildschirm: Aufloesung und Groesse.

Warum das eine eigene Datei ist: In der Beobachtung am Geraet war das Bild auf
einem Bildschirm gut lesbar und auf dem anderen nicht. Beides muss getrennt
einstellbar sein - eine globale Einstellung kann immer nur einem von beiden
passen.

Zwei Werte, absichtlich getrennt:

* **Aufloesung** (xrandr): welches Bild der Rechner ausgibt. Sie muss zu dem
  passen, was der Bildschirm kann. 720x400 auf einem 4K-Fernseher ergibt ein
  riesiges, hochgerechnetes Bild - deshalb der Zoom auf 33 %.
* **Skalierung** (CSS-Zoom auf der Kiosk-Seite): wie gross die Inhalte gezeichnet
  werden. 1.0 heisst: so gross, wie die Seite es nativ hergibt. Der Wert bleibt
  scharf, weil die Aufloesung nativ bleibt und nur die Elemente groesser/kleiner
  gerendert werden.

Der Zoom im Browser (Strg +/-) ist NICHT dasselbe: Der Browser zoomt eine
fertig gezeichnete Seite (weich), die Skalierung hier zeichnet in der richtigen
Groesse und bleibt scharf. Deshalb ist Strg +/- ueberfluessig.
"""
import json
import math
import os

import bildschirm_info

# Skalierung der Anzeige (CSS-Zoom auf der Kiosk-Seite). Absichtlich ein weiter
# Bereich: Auf einem 4K-Fernseher ist selbst 150 % noch klein, dort braucht man
# oft 200-300 %. CSS-Zoom ist verlustfrei (die Aufloesung bleibt nativ, nur die
# Elemente werden groesser neu gerendert) - deshalb darf der Bereich weit sein.
# Frueher stand hier 0.8-1.5, weil der Wert an --force-device-scale-factor
# ging, der bei != 1.0 Resampling und Unschaerfe einleitete.
SKALA_MIN = 0.5
SKALA_MAX = 3.0
SKALA_STANDARD = 1.0

# ── Referenz-Raster: konstante physische Groesse ─────────────────────────────
# Das Ziel: Safety Cross & Co. erscheinen auf JEDEM Bildschirm in derselben
# physischen Groesse - genauso gross wie das Referenzbild "Safety Cross bei
# 150 % CSS-Zoom auf einem 4096x2160-Bildschirm".
#
# Herleitung der Referenz-DPI:
#   * Das Referenzbild zeigt die Anzeige in FESTEN Pixelwerten (die natuerliche
#     Groesse in tools/safety-cross/static/style.css) bei 150 % CSS-Zoom.
#     150 % heisst: 1,5 Geraetepixel je CSS-Pixel.
#   * Die physische Groesse des Referenzbildes = Groesse_in_CSS_px * 1,5 /
#     DPI_des_Referenzbildschirms. Dieselbe physische Groesse ergibt sich bei
#     100 % Zoom (1 Geraetepixel je CSS-Pixel) auf einem fiktiven Bildschirm
#     mit DPI = DPI_des_Referenzbildschirms / 1,5. Das ist die Referenz-DPI.
#   * Referenzbildschirm 4096x2160: Diagonale in Pixeln =
#     sqrt(4096^2 + 2160^2) = 4630,6 px. Als Nenngroesse wird ein 55-Zoll-
#     Display angenommen (die uebliche grosse Anzeige-/TV-Flaeche, die in
#     bildschirm_info.py als "4K-Fernseher" beschrieben wird):
#       DPI_Referenzbildschirm = 4630,6 / 55 = 84,2 DPI
#       REFERENZ_DPI          = 84,2 / 1,5 = 56,1 DPI
#   * Skalierungsfaktor = aktuelle_DPI / REFERENZ_DPI. Auf dem Referenz-
#     Bildschirm selbst: 84,2 / 56,1 = 1,5 -> exakt der 150 %-Zoom des
#     Referenzbildes. Auf jedem anderen Geraet bleibt die physische Groesse
#     konstant (auch wenn dann auf grossen Bildschirmen Rand bleibt).
#   * Anpassbar, falls das Referenz-Display eine andere Diagonale hat:
#     LHTPI_REFERENZ_DPI (direkter Wert) oder LHTPI_REFERENZ_ZOLL (Diagonale
#     in Zoll, Standard 55).
REFERENZ_BREITE = 4096
REFERENZ_HOEHE = 2160
REFERENZ_ZOOM = 1.5
FAKTOR_MIN = 0.25
FAKTOR_MAX = 8.0


def referenz_dpi():
    """DPI des Referenz-Rasters (siehe Modul-Doku oben)."""
    wert = os.environ.get('LHTPI_REFERENZ_DPI')
    if wert:
        try:
            return float(wert)
        except ValueError:
            pass
    zoll = float(os.environ.get('LHTPI_REFERENZ_ZOLL', '55'))
    diagonale_px = math.hypot(REFERENZ_BREITE, REFERENZ_HOEHE)
    return (diagonale_px / zoll) / REFERENZ_ZOOM


def skalierungs_faktor(ausgang=None):
    """Faktor, der die physische Groesse konstant haelt: DPI / Referenz-DPI.

    Ohne bekannte DPI (kein EDID/xrandr, z. B. im Test) gilt 1.0 - die
    Anzeige bleibt in ihrer natuerlichen Groesse scharf. Der Faktor ist auf
    einen sinnvollen Bereich begrenzt, damit eine fehlerhafte EDID nicht ins
    Extreme zoomt.
    """
    dpi_wert = bildschirm_info.dpi(ausgang) if ausgang else None
    if not dpi_wert:
        return 1.0
    faktor = dpi_wert / referenz_dpi()
    return max(FAKTOR_MIN, min(FAKTOR_MAX, faktor))


def effektiver_zoom(idx, ausgang=None):
    """Der tatsaechliche Zoom fuer Bildschirm idx.

    Automatik (Standard): DPI-basierter Faktor (konstante physische Groesse).
    Manuell (Groesse-Regler bewegt): der feste Nutzerwert - die Automatik wird
    dadurch abgeschaltet, aber nicht zerstoert; 'automatisch' reaktiviert sie.
    """
    if not skala_auto(idx):
        return skala(idx)
    return skalierungs_faktor(ausgang)


def _pfad():
    basis = os.environ.get('LHTPI_CONFIG_DIR') or '/etc/lhtpi'
    return os.path.join(basis, 'anzeige-fein.json')


def _lesen():
    try:
        with open(_pfad(), encoding='utf-8') as datei:
            daten = json.load(datei)
        return daten if isinstance(daten, dict) else {}
    except (OSError, ValueError):
        return {}


def _schreiben(daten):
    ziel = _pfad()
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    temp = ziel + '.neu'
    with open(temp, 'w', encoding='utf-8') as datei:
        json.dump(daten, datei, indent=1, sort_keys=True)
    os.replace(temp, ziel)


def skala(idx):
    """Skalierung fuer Bildschirm idx (1-basiert), immer im erlaubten Bereich."""
    wert = _lesen().get(str(idx), {}).get('skala', SKALA_STANDARD)
    try:
        wert = float(wert)
    except (TypeError, ValueError):
        return SKALA_STANDARD
    return max(SKALA_MIN, min(SKALA_MAX, wert))


def setze_skala(idx, wert):
    """Setzt die Skalierung. Liefert (ok, meldung)."""
    try:
        wert = round(float(str(wert).replace(',', '.')), 2)
    except (TypeError, ValueError):
        return False, 'Kein Zahlenwert.'
    if not SKALA_MIN <= wert <= SKALA_MAX:
        return False, ('Skalierung muss zwischen %.2f und %.2f liegen '
                       '(darunter ist es Zoom, darueber abgeschnitten).'
                       % (SKALA_MIN, SKALA_MAX))
    daten = _lesen()
    eintrag = daten.setdefault(str(int(idx)), {})
    eintrag['skala'] = wert
    eintrag['skala_auto'] = False  # manueller Eingriff schaltet die Automatik ab
    try:
        _schreiben(daten)
    except OSError as fehler:
        return False, 'Nicht speicherbar: %s' % fehler
    return True, 'Skalierung fuer Bildschirm %d: %.2f' % (int(idx), wert)


def aufloesung(idx):
    """Zuletzt gesetzte Aufloesung fuer Bildschirm idx, oder None."""
    return _lesen().get(str(idx), {}).get('aufloesung')


def skala_auto(idx):
    """Ob Bildschirm idx die Groesse automatisch fuellt (Standard: ja).

    Im Automatik-Modus skaliert die Kiosk-Seite mit ``zoom = Bildschirmbreite /
    Referenzbreite``. Erst wenn der Nutzer den Groesse-Regler selbst bewegt,
    wird auf 'manuel' umgeschaltet.
    """
    wert = _lesen().get(str(idx), {}).get('skala_auto', True)
    return bool(wert)


def setze_skala_auto(idx, wert):
    """Setzt Automatik (True) oder manuell (False). Liefert (ok, meldung)."""
    daten = _lesen()
    eintrag = daten.setdefault(str(int(idx)), {})
    eintrag['skala_auto'] = bool(wert)
    try:
        _schreiben(daten)
        return True, 'Groesse fuer Bildschirm %d: %s' % (
            int(idx), 'automatisch' if wert else 'manuell')
    except OSError as fehler:
        return False, 'Nicht speicherbar: %s' % fehler


def setze_aufloesung(idx, modus):
    daten = _lesen()
    eintrag = daten.setdefault(str(int(idx)), {})
    eintrag['aufloesung'] = modus
    try:
        _schreiben(daten)
        return True
    except OSError:
        return False


def alle():
    """Alles auf einmal, fuer die Verwaltungsseite."""
    daten = _lesen()
    return {idx: {'skala': skala(idx), 'aufloesung': aufloesung(idx)}
            for idx in (1, 2)}
