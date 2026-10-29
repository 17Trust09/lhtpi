"""Anzeige-Einstellungen je Bildschirm: Aufloesung und Groesse.

Warum das eine eigene Datei ist: In der Beobachtung am Geraet war das Bild auf
einem Bildschirm gut lesbar und auf dem anderen nicht. Beides muss getrennt
einstellbar sein - eine globale Einstellung kann immer nur einem von beiden
passen.

Zwei Werte, absichtlich getrennt:

* **Aufloesung** (xrandr): welches Bild der Rechner ausgibt. Sie muss zu dem
  passen, was der Bildschirm kann. 720x400 auf einem 4K-Fernseher ergibt ein
  riesiges, hochgerechnetes Bild - deshalb der Zoom auf 33 %.
* **Skalierung** (Chromium): wie gross die Seite im Verhaeltnis zur Flaeche
  gezeichnet wird. 1.0 heisst: so gross wie der Bildschirm es hergibt.

Der Zoom im Browser ist NICHT dasselbe wie die Skalierung hier: Der Browser
zoomt eine fertig gezeichnete Seite (weich), die Skalierung zeichnet klein und
scharf. Deshalb bleibt die Seite bei 1.0 scharf, auch wenn du die Aufloesung
aenderst.
"""
import json
import os

# Chromium: --force-device-scale-factor. Erlaubt ist ein enger Bereich - wer
# 0.33 eintraegt, will zoomen, und genau das soll hier nicht passieren.
SKALA_MIN = 0.8
SKALA_MAX = 1.5
SKALA_STANDARD = 1.0


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
    try:
        _schreiben(daten)
    except OSError as fehler:
        return False, 'Nicht speicherbar: %s' % fehler
    return True, 'Skalierung fuer Bildschirm %d: %.2f' % (int(idx), wert)


def aufloesung(idx):
    """Zuletzt gesetzte Aufloesung fuer Bildschirm idx, oder None."""
    return _lesen().get(str(idx), {}).get('aufloesung')


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
