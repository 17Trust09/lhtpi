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

# ── Referenz-Aufloesung: proportionale Skalierung auf JEDE Bildschirmgroesse ──
# Ziel: Die Anzeige ist auf jedem Bildschirm vollstaendig sichtbar und gleich
# proportioniert - sie skaliert proportional zur AUFLOESUNG, nicht zur
# physischen Groesse. Der Faktor ist min(breite/1920, hoehe/1080): das Layout
# ist fuer Full HD (1920x1080) gebaut, dort gilt Zoom 1.0 = "so wie jetzt",
# egal welche Zollgroesse der Full-HD-Bildschirm hat. Auf 4K wird groesser,
# auf kleineren Aufloesungen kleiner skaliert - immer vollstaendig sichtbar.
# (Der fruehere DPI-basierte Ansatz hielt die physische Groesse konstant und
#  schnitt dadurch auf kleineren Bildschirmen mit hoher DPI ab.)
REFERENZ_BREITE = 1920
REFERENZ_HOEHE = 1080
FAKTOR_MIN = 0.25
FAKTOR_MAX = 8.0


def skalierungs_faktor(ausgang=None):
    """Faktor, der das Layout proportional zur Aufloesung skaliert.

    min(breite/1920, hoehe/1080) - das kleinere Verhaeltnis zaehlt, damit
    nichts abgeschnitten wird (bei abweichendem Seitenverhaeltnis bleibt
    Rand). Ohne bekannte Aufloesung (kein xrandr, z. B. im Test) gilt 1.0.
    Der Faktor ist auf einen sinnvollen Bereich begrenzt.
    """
    aufloesung = bildschirm_info.aktuelle_aufloesung(ausgang) if ausgang else None
    if not aufloesung:
        return 1.0
    try:
        breite, hoehe = aufloesung.split('x', 1)
        breite, hoehe = int(breite), int(hoehe)
    except (ValueError, IndexError):
        return 1.0
    if breite <= 0 or hoehe <= 0:
        return 1.0
    faktor = min(breite / REFERENZ_BREITE, hoehe / REFERENZ_HOEHE)
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
