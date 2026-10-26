"""Betriebszeit-Rechnung für das Terminboard.

Regeln (festgelegt am 2026-10-26):

  * Ein Betriebstag ist **06:00–22:45** (16,75 h), Montag bis Freitag.
  * Samstag, Sonntag und **Hamburger Feiertage** zählen nicht.
  * Ausfallstunden und Ausfalltage werden nur innerhalb dieses Fensters gezählt.
  * Eine Wartung Freitag 14:00 bis Montag 08:00 ergibt 10,75 h (8,75 h Freitag
    plus 2 h Montag) – nicht 66 h.

Das Modul ist reine Rechnung ohne Datenbank und ohne Flask, damit es ohne
laufende App getestet werden kann.
"""
from datetime import date, datetime, time, timedelta

# Betriebsfenster
BETRIEB_VON = time(6, 0)
BETRIEB_BIS = time(22, 45)
BETRIEB_STUNDEN_PRO_TAG = 16.75   # 06:00–22:45

# Feste Hamburger Feiertage (Monat, Tag)
FESTE_FEIERTAGE = (
    (1, 1),     # Neujahr
    (5, 1),     # Tag der Arbeit
    (10, 3),    # Tag der Deutschen Einheit
    (10, 31),   # Reformationstag
    (12, 25),   # 1. Weihnachtstag
    (12, 26),   # 2. Weihnachtstag
)

# Ostern-Cache: Rechnung ist billig, aber wird pro Tag oft gebraucht
_OSTERN_CACHE = {}
_FEIERTAG_CACHE = {}


def osterdatum(jahr):
    """Ostersonntag nach der anonymen gregorianischen Osterformel."""
    if jahr in _OSTERN_CACHE:
        return _OSTERN_CACHE[jahr]
    a = jahr % 19
    b = jahr // 100
    c = jahr % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat = (h + l - 7 * m + 114) // 31
    tag = ((h + l - 7 * m + 114) % 31) + 1
    ergebnis = date(jahr, monat, tag)
    _OSTERN_CACHE[jahr] = ergebnis
    return ergebnis


def feiertage_hamburg(jahr):
    """Menge aller Hamburger Feiertage eines Jahres."""
    if jahr in _FEIERTAG_CACHE:
        return _FEIERTAG_CACHE[jahr]

    ostern = osterdatum(jahr)
    tage = {date(jahr, monat, tag) for monat, tag in FESTE_FEIERTAGE}
    tage.add(ostern - timedelta(days=2))    # Karfreitag
    tage.add(ostern + timedelta(days=1))    # Ostermontag
    tage.add(ostern + timedelta(days=39))   # Christi Himmelfahrt
    tage.add(ostern + timedelta(days=50))   # Pfingstmontag

    _FEIERTAG_CACHE[jahr] = tage
    return tage


def ist_betriebstag(tag):
    """True, wenn ``tag`` ein Werktag (Mo–Fr) und kein Hamburger Feiertag ist."""
    if tag.weekday() >= 5:      # Samstag = 5, Sonntag = 6
        return False
    return tag not in feiertage_hamburg(tag.year)


def betriebstage(von, bis):
    """Alle Betriebstage im Zeitraum (jeweils als ``date``)."""
    if bis < von:
        return []
    tag = von.date()
    ende = bis.date()
    tage = []
    while tag <= ende:
        if ist_betriebstag(tag):
            tage.append(tag)
        tag += timedelta(days=1)
    return tage


def _tagesanteil(tag, von, bis):
    """Überschneidung eines Zeitraums mit dem Betriebsfenster eines Tages (in Stunden)."""
    if not ist_betriebstag(tag):
        return 0.0
    fenster_start = datetime.combine(tag, BETRIEB_VON)
    fenster_ende = datetime.combine(tag, BETRIEB_BIS)

    start = max(von, fenster_start)
    ende = min(bis, fenster_ende)
    if ende <= start:
        return 0.0
    return (ende - start).total_seconds() / 3600.0


def betriebsstunden(von, bis):
    """Ausfallstunden eines Zeitraums innerhalb des Betriebsfensters."""
    if bis <= von:
        return 0.0
    summe = 0.0
    tag = von.date()
    ende = bis.date()
    while tag <= ende:
        summe += _tagesanteil(tag, von, bis)
        tag += timedelta(days=1)
    return round(summe, 4)


def ausfalltage(von, bis):
    """Anzahl Betriebstage mit mindestens einem ausfallwirksamen Anteil."""
    if bis <= von:
        return 0
    anzahl = 0
    tag = von.date()
    ende = bis.date()
    while tag <= ende:
        if _tagesanteil(tag, von, bis) > 0:
            anzahl += 1
        tag += timedelta(days=1)
    return anzahl


def ausfalldauer(von, bis):
    """Ausfall eines Zeitraums als ``{'stunden': float, 'tage': int}``."""
    return {'stunden': betriebsstunden(von, bis), 'tage': ausfalltage(von, bis)}


def ausfalldauer_bloecke(bloecke):
    """Ausfall mehrerer Blöcke als ``{'stunden', 'tage'}``.

    ``bloecke`` ist eine Liste von ``(von, bis)``-Tupeln. Die Tage werden
    **vereinigt** – zwei Blöcke am selben Tag ergeben einen Ausfalltag.
    """
    stunden = 0.0
    tage = set()
    for von, bis in bloecke:
        if bis <= von:
            continue
        stunden += betriebsstunden(von, bis)
        for tag in betriebstage(von, bis):
            if _tagesanteil(tag, von, bis) > 0:
                tage.add(tag)
    return {'stunden': round(stunden, 4), 'tage': len(tage)}
