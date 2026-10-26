#!/usr/bin/env python3
"""Vergleicht zwei Datenbanken und meldet, ob Einstellungen erhalten bleiben.

Hintergrund: Das Update sichert und überschreibt nur Programmdateien. Die
Datenbanken liegen unter /var/lib/lhtpi und werden nicht angefasst. Beim ersten
Lauf von install.sh wandern sie aber aus dem Programmverzeichnis dorthin - und
genau dabei darf nichts verloren gehen.

Aufruf (auf dem Pi, als root):
    python3 pruefe_daten.py

Ohne Argumente: vergleicht für alle drei Anwendungen alt und neu.
Mit --pip: hängt den Vergleich an eine vorhandene Ausgabe an (für das Protokoll).
"""
import os
import sqlite3
import sys

# (Name, alter Pfad im Programmverzeichnis, neuer Pfad)
QUELLEN = [
    ('Safety Cross', '/opt/safety-cross/safetycross.db',
     '/var/lib/lhtpi/safety-cross/safetycross.db'),
    ('Terminboard', '/home/pi/lhtpi/terminboard/terminboard.db',
     '/var/lib/lhtpi/terminboard/terminboard.db'),
    ('Haupt-App', '/home/pi/lhtpi/lhtpi.db',
     '/var/lib/lhtpi/app/lhtpi.db'),
]

# Tabellen, in denen Einstellungen des Nutzers liegen
EINSTELLUNGEN = {
    'Safety Cross': [('config', 'key'), ('ersthelfer', None),
                     ('notruf', None), ('days', None)],
    'Terminboard': [('setting', None), ('kiosk_screen', None),
                    ('kiosk_screen_entry', None)],
    'Haupt-App': [('setting', None), ('user', 'username')],
}


def zeilen(pfad, tabelle):
    """Anzahl Zeilen einer Tabelle (None, wenn es sie nicht gibt)."""
    try:
        with sqlite3.connect(pfad) as conn:
            return conn.execute(f'SELECT COUNT(*) FROM "{tabelle}"').fetchone()[0]
    except sqlite3.Error:
        return None


def tabellen(pfad):
    try:
        with sqlite3.connect(pfad) as conn:
            return {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.Error:
        return set()


def pruefe(name, alt, neu):
    """Liefert (ok, meldungen)."""
    meldungen = []
    ok = True

    if not os.path.exists(alt):
        meldungen.append(f'  Alt:  {alt} nicht vorhanden (nichts zu übernehmen)')
        return True, meldungen
    if not os.path.exists(neu):
        meldungen.append(f'  FEHLER: {neu} fehlt – Migration nicht gelaufen!')
        return False, meldungen

    alte_tabellen = tabellen(alt)
    neue_tabellen = tabellen(neu)
    if not neue_tabellen:
        meldungen.append('  FEHLER: neue Datenbank ist leer (keine Tabellen)')
        return False, meldungen

    for tabelle, schluessel in EINSTELLUNGEN.get(name, []):
        if tabelle not in alte_tabellen:
            continue
        alt_n = zeilen(alt, tabelle)
        neu_n = zeilen(neu, tabelle)
        if neu_n is None:
            meldungen.append(f'  FEHLER: Tabelle {tabelle} fehlt in der neuen Datei')
            ok = False
            continue
        if alt_n is None:
            continue
        if neu_n < alt_n:
            meldungen.append(
                f'  FEHLER: {tabelle}: alt {alt_n} Zeilen, neu nur {neu_n}')
            ok = False
        else:
            meldungen.append(f'  ok    {tabelle}: {alt_n} → {neu_n} Zeilen')

    return ok, meldungen


def main():
    alles_ok = True
    print('Prüfung der übernommenen Einstellungen')
    print('=' * 44)
    for name, alt, neu in QUELLEN:
        print(f'\n{name}')
        ok, meldungen = pruefe(name, alt, neu)
        for zeile in meldungen:
            print(zeile)
        if not ok:
            alles_ok = False

    print()
    if alles_ok:
        print('ERGEBNIS: alle Einstellungen sind vorhanden.')
        return 0
    print('ERGEBNIS: Es fehlen Einstellungen – Sicherung prüfen, nichts weiter tun.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
