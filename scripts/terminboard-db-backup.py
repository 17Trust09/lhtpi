#!/usr/bin/python3
"""LHTPi: konsistenten Snapshot der Terminboard-DB anlegen (Root-Helfer).

Wird per ``sudo -n`` aus ``scripts/nach-pull.sh`` aufgerufen und liegt
installiert als ``/usr/local/sbin/lhtpi-terminboard-backup`` (root, 0755).
Absichtlich OHNE Argumente: die sudo-Freigabe bleibt eng - es gibt kein
beliebiges Quell-/Zielziel, das ein pi-Benutzer als root missbrauchen könnte.

Der DB-Pfad ist fest verdrahtet. Es wird weder ``TERMINBOARD_DB`` noch
``LHTPI_DATA_DIR`` gelesen: der Helfer läuft als root, und jede über die
Umgebung steuerbare Pfadwahl wäre eine root-Freigabe für beliebige Dateien.
Auch der Interpreter ist über die Shebang fest auf ``/usr/bin/python3``
festgelegt (kein ``/usr/bin/env``, kein PATH-lookup). Reihenfolge:

  1. primär  ``/var/lib/lhtpi/terminboard/terminboard.db``,
  2. legacy  ``/home/pi/lhtpi/terminboard/terminboard.db`` (nur wenn primär fehlt),
  3. sonst: keine DB - kein Fehler (exit 0).

Warum die sqlite3-Backup-API: ein blosses ``cp`` der DB-Datei kann im
WAL-Modus eine halb geschriebene ``-wal``-Datei mitkopieren und so eine
unbrauchbare Sicherung hinterlassen. ``Connection.backup()`` liest über den
WAL und liefert einen konsistenten Snapshot der committeten Daten.

Ablauf:
  1. Ersten vorhandenen Kandidaten wählen.
  2. Fehlt die DB, ist das kein Fehler (exit 0, "keine DB").
  3. In eine temporäre Datei im Sicherungsordner backuppen, dann atomar
     umbenennen (``os.replace``).
  4. Ältere Sicherungen auf die letzten 10 begrenzen.
  5. Pfad der neuen Sicherung auf stdout ausgeben.
"""
import os
import sqlite3
import sys
from datetime import datetime

DB_NAME = 'terminboard.db'

# Feste Produktionspfade - bewusst als Modulkonstanten, damit Tests sie gezielt
# patchen können, ohne die Umgebung zu beeinflussen. Reihenfolge = Priorität.
PRIMAER_DB = '/var/lib/lhtpi/terminboard/terminboard.db'
LEGACY_DB = '/home/pi/lhtpi/terminboard/terminboard.db'


def _kandidaten():
    """Alle festen Kandidaten in Prioritätsreihenfolge."""
    return [PRIMAER_DB, LEGACY_DB]


def _db_pfad():
    """Ersten vorhandenen Kandidaten liefern, sonst ``None``."""
    for pfad in _kandidaten():
        if os.path.isfile(pfad):
            return pfad
    return None


def _begrenzen(backup_dir, behalten=10):
    """Nur die letzten ``behalten`` Sicherungen stehen lassen (neueste zuerst)."""
    try:
        namen = [n for n in os.listdir(backup_dir)
                 if n.startswith(DB_NAME + '.') and n.endswith('.bak')]
    except OSError:
        return
    eintraege = [os.path.join(backup_dir, n) for n in namen]
    # Neueste zuerst nach mtime; bei fehlendem mtime bleibt die Reihenfolge.
    eintraege.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for alte in eintraege[behalten:]:
        try:
            os.remove(alte)
        except OSError:
            pass


def main():
    db = _db_pfad()
    if db is None:
        print('keine DB (%s oder %s) - keine Sicherung.' % (PRIMAER_DB, LEGACY_DB))
        return 0

    backup_dir = os.path.join(os.path.dirname(db), 'backups')
    try:
        os.makedirs(backup_dir, exist_ok=True)
    except OSError as e:
        print('FEHLER: Sicherungsordner %s nicht anlegbar: %s' % (backup_dir, e),
              file=sys.stderr)
        return 1

    stempel = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    ziel = os.path.join(backup_dir, '%s.%s.bak' % (DB_NAME, stempel))
    tmp = ziel + '.tmp'

    # timeout: bei parallelem Schreiben (Stick-Import) lieber warten als sofort
    # mit "database is locked" abzubrechen - wie es auch die App selbst tut.
    quelle = sqlite3.connect(db, timeout=30)
    try:
        sicherung = sqlite3.connect(tmp)
        try:
            quelle.backup(sicherung)
        finally:
            sicherung.close()
    except Exception as e:
        quelle.close()
        try:
            os.remove(tmp)
        except OSError:
            pass
        print('FEHLER: DB-Sicherung fehlgeschlagen (%s): %s' % (db, e),
              file=sys.stderr)
        return 1
    quelle.close()

    # Atomar abschliessen: erst vollständig geschrieben, dann umbenennen.
    try:
        os.replace(tmp, ziel)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        print('FEHLER: Sicherung %s nicht abschliessbar: %s' % (ziel, e),
              file=sys.stderr)
        return 1

    _begrenzen(backup_dir)

    print(ziel)
    return 0


if __name__ == '__main__':
    sys.exit(main())
