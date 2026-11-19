"""Schema-Migration ohne Alembic: eine bestehende Terminboard-DB auf den
Modell-3-Stand heben.

Die App nutzt ``db.create_all()``, das **nur fehlende Tabellen** anlegt, aber
bestehenden Tabellen keine Spalten hinzufügt. Diese Migration ergänzt deshalb
gezielt die Modell-3-Erweiterungen und überführt die alten Prüfstands-Daten in
die neue ``betriebsmittel``-Tabelle – ohne Datenverlust.

Ablauf (idempotent, mit Sicherung und Rollback):

1. Altes Schema erkennen (``betriebsmittel`` fehlt oder ``vorgang`` hat die
   neuen Spalten noch nicht).
2. Sicherung ``<datei>.bak`` anlegen.
3. ``betriebsmittel`` anlegen, ``vorgang`` um ``vorgangsnummer``,
   ``betriebsmittel_id`` und ``titel`` erweitern.
4. Deterministische BM-Kennungen vergeben: Die Reihenfolge der Vorlage
   (``tools_vorlage_modell3_bauen.BETRIEBSMITTEL``) hat Vorrang, damit die
   Kennungen mit der Excel-Vorlage übereinstimmen. Namen, die dort nicht
   stehen, bekommen die nächste freie ``BM-NNN``.
5. ``vorgang.betriebsmittel_id`` anhand des Prüfstands-Namens setzen.

In-Memory-Datenbanken (``sqlite://``) werden übersprungen – dort erzeugt
``create_all()`` das neue Schema direkt.
"""
import os
import re
import shutil
import sqlite3

VORGANG_NEUE_SPALTEN = {
    'vorgangsnummer': 'VARCHAR(20)',
    'betriebsmittel_id': 'INTEGER',
    'titel': 'VARCHAR(200)',
}

BETRIEBSMITTEL_DDL = """
CREATE TABLE IF NOT EXISTS betriebsmittel (
    id INTEGER NOT NULL PRIMARY KEY,
    kennung VARCHAR(20) NOT NULL UNIQUE,
    typ VARCHAR(20) NOT NULL,
    bezeichnung VARCHAR(80) NOT NULL,
    in_excel_aktiv BOOLEAN NOT NULL DEFAULT 1,
    merge_ziel_id INTEGER,
    sortierung INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(merge_ziel_id) REFERENCES betriebsmittel (id)
)
"""

_KENNUNG = re.compile(r'BM-(\d{3})')


def _table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _column_exists(conn, table, column):
    zeilen = conn.execute('PRAGMA table_info(%s)' % table).fetchall()
    return any(zeile[1] == column for zeile in zeilen)


def _braucht_migration(conn):
    if not _table_exists(conn, 'vorgang'):
        return False            # frisch/ohne Historie: create_all legt alles an
    if not _table_exists(conn, 'betriebsmittel'):
        return True
    return any(not _column_exists(conn, 'vorgang', spalte)
               for spalte in VORGANG_NEUE_SPALTEN)


def _vorlagen_zuordnung():
    """``{name.casefold(): (kennung, typ)}`` in der Reihenfolge der Vorlage."""
    from tools_vorlage_modell3_bauen import BETRIEBSMITTEL
    zuordnung = {}
    for kennung, typ, name in BETRIEBSMITTEL:
        zuordnung.setdefault(str(name).casefold(), (kennung, typ))
    return zuordnung


def _max_nummer(conn):
    """Höchste vergebene BM-Nummer (aus Tabelle und Vorlage)."""
    vorlage = _vorlagen_zuordnung()
    maximum = 0
    for (kennung,) in conn.execute('SELECT kennung FROM betriebsmittel'):
        treffer = _KENNUNG.fullmatch(kennung or '')
        if treffer:
            maximum = max(maximum, int(treffer.group(1)))
    for kennung, _ in vorlage.values():
        treffer = _KENNUNG.fullmatch(kennung)
        if treffer:
            maximum = max(maximum, int(treffer.group(1)))
    return maximum


def _migriere(conn):
    """Führt die eigentliche Migration in der offenen Verbindung aus."""
    schritte = []

    if not _table_exists(conn, 'betriebsmittel'):
        conn.execute(BETRIEBSMITTEL_DDL)
        schritte.append('Tabelle betriebsmittel angelegt')

    # Hinweis: SQLite kann über ``ALTER TABLE … ADD COLUMN`` keine FOREIGN KEY
    # nachträglich ergänzen. ``vorgang.betriebsmittel_id`` bleibt daher ohne
    # FK-Constraint; die Referenz wird auf Anwendungsebene gepflegt
    # (SQLAlchemy-Beziehung in :mod:`historie`).
    for spalte, ddl in VORGANG_NEUE_SPALTEN.items():
        if not _column_exists(conn, 'vorgang', spalte):
            conn.execute('ALTER TABLE vorgang ADD COLUMN %s %s' % (spalte, ddl))
            schritte.append('vorgang.%s ergänzt' % spalte)

    if _column_exists(conn, 'vorgang', 'vorgangsnummer'):
        conn.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_vorgang_vorgangsnummer '
            'ON vorgang (vorgangsnummer)')
        schritte.append('Unique-Index auf vorgang.vorgangsnummer')

    if _column_exists(conn, 'vorgang', 'betriebsmittel_id'):
        conn.execute(
            'CREATE INDEX IF NOT EXISTS ix_vorgang_betriebsmittel_id '
            'ON vorgang (betriebsmittel_id)')
        schritte.append('Index auf vorgang.betriebsmittel_id')

    # ── Bestehende Namen einsammeln (Prüfstand-Tabelle + Vorgang-Spalte) ──
    namen = []
    if _table_exists(conn, 'pruefstand'):
        for name, _sortierung in conn.execute(
                'SELECT name, sortierung FROM pruefstand WHERE name IS NOT NULL'):
            namen.append(name)
    if _column_exists(conn, 'vorgang', 'pruefstand'):
        for (name,) in conn.execute(
                "SELECT DISTINCT pruefstand FROM vorgang "
                "WHERE pruefstand IS NOT NULL AND pruefstand != ''"):
            namen.append(name)

    vorlage = _vorlagen_zuordnung()
    existing = {}
    for kennung, typ, bezeichnung in conn.execute(
            'SELECT kennung, typ, bezeichnung FROM betriebsmittel'):
        existing.setdefault(str(bezeichnung).casefold(), (kennung, typ))

    # Eindeutige Namen (case-insensitiv), Reihenfolge stabil.
    distinct = []
    gesehen = set()
    for name in namen:
        cf = str(name).casefold()
        if cf in gesehen:
            continue
        gesehen.add(cf)
        distinct.append(name)

    extras = sorted(
        (n for n in distinct
         if n.casefold() not in vorlage and n.casefold() not in existing),
        key=lambda n: n.casefold())

    next_num = _max_nummer(conn) + 1
    zuordnung = {}
    for name in distinct:
        cf = name.casefold()
        if cf in existing:
            zuordnung[cf] = existing[cf]
        elif cf in vorlage:
            zuordnung[cf] = vorlage[cf]
        else:
            zuordnung[cf] = ('BM-%03d' % next_num, 'pruefstand')
            next_num += 1

    angelegt = 0
    for name in distinct:
        kennung, typ = zuordnung[name.casefold()]
        treffer = conn.execute(
            'SELECT id FROM betriebsmittel WHERE kennung=?', (kennung,)).fetchone()
        if treffer is None:
            conn.execute(
                'INSERT INTO betriebsmittel '
                '(kennung, typ, bezeichnung, in_excel_aktiv, merge_ziel_id, sortierung) '
                'VALUES (?, ?, ?, 1, NULL, 0)',
                (kennung, typ, name))
            angelegt += 1

    verknuepft = 0
    # Verknüpfung in Python über ``casefold`` – SQLite ``lower()`` behandelt nur
    # ASCII (z. B. bleibt „Ü“ unverändert) und verfehlt damit non-ASCII-Namen.
    bm_id_nach_name = {}
    for bm_id, bezeichnung in conn.execute(
            'SELECT id, bezeichnung FROM betriebsmittel'):
        bm_id_nach_name[str(bezeichnung).casefold()] = bm_id

    for vorgang_id, pruefstand in conn.execute(
            'SELECT id, pruefstand FROM vorgang '
            "WHERE pruefstand IS NOT NULL AND pruefstand != ''"):
        cf = str(pruefstand).casefold()
        if cf in bm_id_nach_name:
            conn.execute(
                'UPDATE vorgang SET betriebsmittel_id=? WHERE id=?',
                (bm_id_nach_name[cf], vorgang_id))
            verknuepft += 1

    if angelegt:
        schritte.append('%d Betriebsmittel angelegt' % angelegt)
    if verknuepft:
        schritte.append('%d Vorgänge verknüpft' % verknuepft)
    return schritte


def upgrade(db, pfad=None):
    """Führt die Migration aus (idempotent) und liefert einen Report.

    ``db`` ist die Flask-SQLAlchemy-Erweiterung (für den DB-Pfad); ``pfad``
    kann die Datei explizit angeben. Report:
    ``{'gesichert', 'migriert', 'schritte', 'fehler'}``.
    """
    ergebnis = {'gesichert': None, 'migriert': False, 'schritte': [], 'fehler': None}

    if pfad is None:
        url = db.engine.url
        if url.get_backend_name() != 'sqlite':
            return ergebnis
        pfad = url.database
        if not pfad or pfad == ':memory:':
            return ergebnis      # In-Memory: create_all erzeugt alles frisch

    if not os.path.isfile(pfad):
        return ergebnis

    conn = sqlite3.connect(pfad)
    try:
        if not _braucht_migration(conn):
            return ergebnis

        sicherung = pfad + '.bak'
        shutil.copy2(pfad, sicherung)
        ergebnis['gesichert'] = sicherung

        try:
            ergebnis['schritte'] = _migriere(conn)
            conn.commit()
            ergebnis['migriert'] = True
        except Exception as fehler:                      # noqa: BLE001
            conn.rollback()
            shutil.copy2(sicherung, pfad)                # Rollback auf die Sicherung
            ergebnis['fehler'] = str(fehler)
    finally:
        try:
            conn.close()
        except Exception:                                # noqa: BLE001
            pass
    return ergebnis


def upgrade_oder_abbrechen(db, pfad=None, logger=None):
    """Führt die Migration aus und bricht bei Fehler mit ``RuntimeError`` ab.

    Ein fehlgeschlagenes Upgrade darf die App nicht still weiterlaufen lassen –
    sonst arbeitet sie auf einem halb migrierten Schema. Ein sauberer No-op
    (keine Migration nötig) ist weiterhin erlaubt und wirft nichts.
    """
    ergebnis = upgrade(db, pfad=pfad)
    if ergebnis.get('fehler'):
        if logger is not None:
            logger.error('Schema-Migration fehlgeschlagen: %s', ergebnis['fehler'])
        raise RuntimeError('Schema-Migration fehlgeschlagen: %s' % ergebnis['fehler'])
    return ergebnis
