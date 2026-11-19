"""Tests für den Root-Helfer scripts/terminboard-db-backup.py.

Der Helfer läuft in Produktion über sudo als root. Hier wird er als Modul
importiert und seine festen Pfad-Konstanten (PRIMAER_DB/LEGACY_DB) werden auf
temporäre Verzeichnisse gepatcht - kein sudo, kein root, kein Schreiben nach
/var/lib/lhtpi oder /home/pi und keine Umgebungsvariablen.

Aufruf:
    python3 test_terminboard_db_backup.py
"""
import contextlib
import importlib.util
import io
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
HELFER = REPO_ROOT / 'scripts' / 'terminboard-db-backup.py'


def _lade_helfer():
    spec = importlib.util.spec_from_file_location('terminboard_db_backup',
                                                  str(HELFER))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


helfer = _lade_helfer()

passed = 0
failed = 0


def ok(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print('  ok  %s' % msg)
    else:
        failed += 1
        print('  FEHLER  %s' % msg)


def _lauf(primaer=None, legacy=None):
    """Führt helfer.main() mit gepatchten Pfaden aus; liefert (rc, out, err)."""
    out, err = io.StringIO(), io.StringIO()
    alt_primaer, alt_legacy = helfer.PRIMAER_DB, helfer.LEGACY_DB
    # Unerreichbare Dummies, damit Tests nicht versehentlich Produktionspfade
    # anfassen (und --falls vorhanden-- kein echter Kandidat getroffen wird).
    helfer.PRIMAER_DB = primaer if primaer is not None else os.path.join(
        tempfile.gettempdir(), 'lhtpi-dbbackup-nix', 'terminboard', 'terminboard.db')
    helfer.LEGACY_DB = legacy if legacy is not None else os.path.join(
        tempfile.gettempdir(), 'lhtpi-dbbackup-nix-legacy', 'terminboard', 'terminboard.db')
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = helfer.main()
    finally:
        helfer.PRIMAER_DB, helfer.LEGACY_DB = alt_primaer, alt_legacy
    return rc, out.getvalue(), err.getvalue()


def _wal_db(db, zeilen=3):
    """Legt die SQLite-DB ``db`` im WAL-Modus mit Inhalt an."""
    db = Path(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db))
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('CREATE TABLE t (id INTEGER PRIMARY KEY, wert TEXT)')
    for i in range(zeilen):
        con.execute('INSERT INTO t (wert) VALUES (?)', ('wert-%d' % i,))
    con.commit()
    return con


def _zeilen(db):
    con = sqlite3.connect(str(db))
    try:
        return [r[0] for r in con.execute('SELECT wert FROM t ORDER BY rowid')]
    finally:
        con.close()


# ── Shebang: fester Interpreter, kein PATH-lookup ────────────────────────

ok(HELFER.read_text(encoding='utf-8').splitlines()[0] == '#!/usr/bin/python3',
   'Shebang ist #!/usr/bin/python3 (kein /usr/bin/env, kein PATH-lookup)')

# ── Keine DB -> kein Fehler ─────────────────────────────────────────────

basis = tempfile.mkdtemp(prefix='dbbackup-')
rc, out, err = _lauf(primaer=str(Path(basis) / 'p' / 'terminboard.db'),
                     legacy=str(Path(basis) / 'l' / 'terminboard.db'))
ok(rc == 0 and 'keine DB' in out,
   'fehlende DB ist kein Fehler (exit 0, "keine DB")')

# ── Umgebungsvariablen werden ignoriert ─────────────────────────────────
# TERMINBOARD_DB / LHTPI_DATA_DIR dürfen die Pfadwahl nicht mehr beeinflussen.

basis = tempfile.mkdtemp(prefix='dbbackup-')
env_db = Path(basis) / 'via-env' / 'terminboard.db'
_wal_db(env_db, zeilen=1)
alt_env = {}
for name in ('TERMINBOARD_DB', 'LHTPI_DATA_DIR'):
    alt_env[name] = os.environ.get(name)
os.environ['TERMINBOARD_DB'] = str(env_db)
os.environ['LHTPI_DATA_DIR'] = str(Path(basis) / 'via-env-data')
try:
    rc, out, err = _lauf(primaer=str(Path(basis) / 'p' / 'terminboard.db'),
                         legacy=str(Path(basis) / 'l' / 'terminboard.db'))
finally:
    for name, wert in alt_env.items():
        if wert is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = wert
ok(rc == 0 and 'keine DB' in out,
   'TERMINBOARD_DB/LHTPI_DATA_DIR werden ignoriert (feste Pfade zählen)')

# ── Konsistenter Snapshot einer WAL-DB (primärer Pfad) ──────────────────

basis = tempfile.mkdtemp(prefix='dbbackup-')
db = Path(basis) / 'terminboard' / 'terminboard.db'
con = _wal_db(db, zeilen=5)
rc, out, err = _lauf(primaer=str(db))
ok(rc == 0, 'Sicherung einer WAL-DB endet erfolgreich (%s)' % rc)
sicherungen = sorted((db.parent / 'backups').glob('*.bak'))
ok(len(sicherungen) == 1, 'genau eine Sicherung angelegt')
ok(sicherungen and sicherungen[0].read_bytes().startswith(b'SQLite format 3'),
   'Sicherung ist eine echte SQLite-Datei')
ok(sicherungen and _zeilen(sicherungen[0]) == ['wert-%d' % i for i in range(5)],
   'Sicherung enthält die committeten Zeilen der WAL-DB')
ok(out.strip().endswith('.bak'), 'Pfad der Sicherung steht auf stdout')

# Nachträglich geschriebene, noch nicht checkpointete Zeilen sind drin.
con.execute('INSERT INTO t (wert) VALUES (?)', ('nach-WAL',))
con.commit()
rc, out, err = _lauf(primaer=str(db))
sicherungen = sorted((db.parent / 'backups').glob('*.bak'))
ok(len(sicherungen) == 2 and _zeilen(sicherungen[-1])[-1] == 'nach-WAL',
   'noch nicht checkpointete WAL-Zeilen sind in der Sicherung')
con.close()

# ── Legacy-Pfad: Sicherung landet NEBEN der Legacy-DB ───────────────────

basis = tempfile.mkdtemp(prefix='dbbackup-')
legacy_db = Path(basis) / 'legacy' / 'terminboard' / 'terminboard.db'
con = _wal_db(legacy_db, zeilen=2)
con.close()
# Primärer Pfad existiert hier bewusst NICHT - nur der Legacy-Pfad.
primaer = Path(basis) / 'primaer' / 'terminboard' / 'terminboard.db'
rc, out, err = _lauf(primaer=str(primaer), legacy=str(legacy_db))
ok(rc == 0, 'Legacy-DB wird gesichert, wenn der primäre Pfad fehlt (%s)' % rc)
sicherungen = sorted((legacy_db.parent / 'backups').glob('*.bak'))
ok(len(sicherungen) == 1 and _zeilen(sicherungen[0]) == ['wert-0', 'wert-1'],
   'Sicherung wird neben der Legacy-DB angelegt')
ok(not primaer.parent.exists(),
   'am primären Pfad entsteht nichts (Legacy-Fall)')

# ── Primär hat Vorrang vor Legacy ───────────────────────────────────────

basis = tempfile.mkdtemp(prefix='dbbackup-')
primaer = Path(basis) / 'terminboard' / 'terminboard.db'
legacy_db = Path(basis) / 'legacy' / 'terminboard' / 'terminboard.db'
_p1 = _wal_db(primaer, zeilen=1)
_p1.close()
_l = _wal_db(legacy_db, zeilen=2)
_l.close()
rc, out, err = _lauf(primaer=str(primaer), legacy=str(legacy_db))
ok(rc == 0, 'primärer Pfad wird genutzt, wenn beide existieren')
sicherungen_prim = sorted((primaer.parent / 'backups').glob('*.bak'))
sicherungen_legacy = sorted((legacy_db.parent / 'backups').glob('*.bak'))
ok(len(sicherungen_prim) == 1 and _zeilen(sicherungen_prim[0]) == ['wert-0'],
   'Sicherung liegt beim primären Pfad')
ok(sicherungen_legacy == [], 'keine Sicherung beim Legacy-Pfad (primär hat Vorrang)')

# ── Alte Sicherungen auf 10 begrenzen ───────────────────────────────────

basis = tempfile.mkdtemp(prefix='dbbackup-')
db = Path(basis) / 'terminboard' / 'terminboard.db'
con = _wal_db(db, zeilen=1)
con.close()
backup_dir = db.parent / 'backups'
backup_dir.mkdir(parents=True, exist_ok=True)
for i in range(12):
    p = backup_dir / ('terminboard.db.20200101-%06d.bak' % i)
    p.write_text('ALT')
    # Ältere Dateien mit älterer mtime versehen (Pruning nutzt mtime).
    t = time.time() - (1000 - i)
    os.utime(str(p), (t, t))
rc, out, err = _lauf(primaer=str(db))
rest = sorted(backup_dir.glob('*.bak'))
ok(rc == 0 and len(rest) == 10,
   'alte Sicherungen werden auf 10 begrenzt (%d)' % len(rest))
ok(any(p.read_bytes().startswith(b'SQLite format 3') for p in rest),
   'die neueste Sicherung (echte DB) bleibt erhalten')

# ── Kaputte DB -> Fehler (exit != 0) ────────────────────────────────────

basis = tempfile.mkdtemp(prefix='dbbackup-')
dbfile = Path(basis) / 'terminboard' / 'terminboard.db'
dbfile.parent.mkdir(parents=True, exist_ok=True)
dbfile.write_text('KEINE SQLITE DATEI\n')
rc, out, err = _lauf(primaer=str(dbfile))
ok(rc != 0 and 'FEHLER' in err,
   'kaputte DB führt zu Fehlschlag (exit %s)' % rc)


print('\n%s%d Prüfungen bestanden, %d fehlgeschlagen'
      % ('OK – ' if failed == 0 else 'FEHLER – ', passed, failed))
sys.exit(1 if failed else 0)
