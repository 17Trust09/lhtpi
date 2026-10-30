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

# Skalierung der Anzeige (CSS-Zoom auf der Kiosk-Seite). Absichtlich ein weiter
# Bereich: Auf einem 4K-Fernseher ist selbst 150 % noch klein, dort braucht man
# oft 200-300 %. CSS-Zoom ist verlustfrei (die Aufloesung bleibt nativ, nur die
# Elemente werden groesser neu gerendert) - deshalb darf der Bereich weit sein.
# Frueher stand hier 0.8-1.5, weil der Wert an --force-device-scale-factor
# ging, der bei != 1.0 Resampling und Unschaerfe einleitete.
SKALA_MIN = 0.5
SKALA_MAX = 3.0
SKALA_STANDARD = 1.0

# Fester Default-Zoom im Automatik-Modus. Die Kiosk-Tools (v.a. Safety Cross)
# sind inzwischen responsive: sie fuellen den Bildschirm bei 100 % (1.0) von
# selbst, unabhaengig von der Aufloesung. Ein fester Zoom > 1.0 wuerde das
# responsive Layout wieder ueber den Bildschirmrand aufblasen. Also 1.0 = keine
# zusaetzliche Vergroesserung; das Tool selbst regelt seine Groesse. Der
# Groesse-Regler bleibt als manueller Notbehelf erhalten (z. B. wenn eine
# einzelne Anzeige optisch kleiner/grösser wirken soll).
SKALA_AUTO_ZOOM = 1.0


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
