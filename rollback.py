"""Rollback-Zustand fuer manuelle Aufloesungswechsel.

Ein manueller Wechsel ist ein Versuch, der schiefgehen kann (Fernseher zeigt
'kein Signal'). Deshalb laeuft er in einem 30-Sekunden-Fenster:

* Beim Wechsel wird der VORHERIGE Zustand gespeichert und eine Markierung
  gesetzt (aktiv, noch nicht bestaetigt).
* Der HDMI-Waechter (laeuft ohnehin alle 10 s) prueft diese Markierung. Ist
  sie aelter als 30 s und nicht bestaetigt, setzt er den vorherigen Zustand
  zurueck - das rettet vor dem schwarzen Bildschirm.
* Bestaetigt der Nutzer ('passt'), wird die Markierung auf bestaetigt gesetzt
  und der Waechter fasst nichts mehr an.

Der Waechter ist als Timer-Owner die robuste Wahl: kein Flask-Thread, der bei
einem App-Neustart stirbt. Solange die Markierung aktiv (unbestaetigt) ist,
greifen Waechter UND Rettung nicht mit --auto ein, damit sie den manuellen
Versuch nicht in den 30 s ueberschreiben.

Datei: /etc/lhtpi/anzeige-rollback.json
{
  "aktiv": true,
  "seit": 1750000000,
  "bestaetigt": false,
  "vorher": {"HDMI-1": "3840x2160", "HDMI-2": null}
}
"""
import json
import os
import time

FENSTER_SEKUNDEN = 30


def _pfad():
    basis = os.environ.get('LHTPI_CONFIG_DIR') or '/etc/lhtpi'
    return os.path.join(basis, 'anzeige-rollback.json')


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


def start(vorher):
    """Beginnt ein Rollback-Fenster. ``vorher`` ist {ausgang: modus}."""
    _schreiben({
        'aktiv': True,
        'seit': int(time.time()),
        'bestaetigt': False,
        'vorher': vorher or {},
    })


def bestaetigen():
    """Nutzer hat 'passt' gewaehlt - Fenster beenden, nichts zuruecksetzen."""
    daten = _lesen()
    vorher = daten.get('vorher', {}) if daten.get('aktiv') else {}
    if daten.get('aktiv'):
        daten['bestaetigt'] = True
        daten['aktiv'] = False
        _schreiben(daten)
    return vorher


def abbrechen():
    """Fenster ohne Wirkung loeschen (z. B. nach Rollback)."""
    try:
        os.remove(_pfad())
    except OSError:
        pass


def aktiv_unbestaetigt():
    """Laeuft gerade ein unbestaetigtes Fenster?"""
    daten = _lesen()
    return bool(daten.get('aktiv')) and not daten.get('bestaetigt')


def abgelaufen():
    """Ist das Fenster ueber die Zeit und muss zurueckgesetzt werden?

    Liefert den gespeicherten vorher-Zustand als dict, sonst None.
    """
    daten = _lesen()
    if not daten.get('aktiv'):
        return None
    if daten.get('bestaetigt'):
        return None
    seit = daten.get('seit', 0)
    if int(time.time()) - seit >= FENSTER_SEKUNDEN:
        return daten.get('vorher', {})
    return None


def vorher_zustand():
    """Der gespeicherte vorher-Zustand (fuer den Waechter beim Rollback)."""
    daten = _lesen()
    return daten.get('vorher', {}) if daten.get('aktiv') else {}
