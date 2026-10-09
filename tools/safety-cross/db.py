"""SQLite-Datenschicht für das Safety Cross.

Eine lokale SQLite-Datei (`safetycross.db`) — offline, kein Server.
Alle Datums-Keys einheitlich als `YYYY-MM-DD` (mit führenden Nullen, sortierbar).
"""
import os
import sqlite3
from datetime import date, timedelta

DB_PATH = os.environ.get("SAFETY_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "safetycross.db"))


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS ersthelfer (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sort INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS days (
            date   TEXT PRIMARY KEY,       -- YYYY-MM-DD
            status TEXT NOT NULL,          -- green | yellow | red
            note   TEXT
        );
        CREATE TABLE IF NOT EXISTS notruf (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            value TEXT NOT NULL,
            sort  INTEGER DEFAULT 0
        );
        """
    )
    # Defaults (nur wenn noch nicht gesetzt)
    if get_config("abteilung") is None:
        set_config("abteilung", "Hydraulik Prüffeld")
    if get_config("meister") is None:
        set_config("meister", "")
    conn.commit()
    conn.close()


def get_config(key):
    conn = _conn()
    row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None


def set_config(key, value):
    conn = _conn()
    conn.execute(
        "INSERT INTO config (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


# ---------- Ersthelfer ----------

def list_ersthelfer():
    conn = _conn()
    rows = conn.execute("SELECT id, name FROM ersthelfer ORDER BY sort, id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_ersthelfer(name):
    conn = _conn()
    conn.execute("INSERT INTO ersthelfer (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


def remove_ersthelfer(ersthelfer_id):
    conn = _conn()
    conn.execute("DELETE FROM ersthelfer WHERE id = ?", (ersthelfer_id,))
    conn.commit()
    conn.close()


# ---------- Notruf / wichtige Nummern ----------

def list_notruf():
    conn = _conn()
    rows = conn.execute("SELECT id, label, value FROM notruf ORDER BY sort, id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_notruf(label, value):
    conn = _conn()
    conn.execute("INSERT INTO notruf (label, value) VALUES (?, ?)", (label, value))
    conn.commit()
    conn.close()


def remove_notruf(notruf_id):
    conn = _conn()
    conn.execute("DELETE FROM notruf WHERE id = ?", (notruf_id,))
    conn.commit()
    conn.close()


# ---------- Tage ----------

def day_key(y, m, d):
    return "%04d-%02d-%02d" % (y, m, d)


def month_days(year, month):
    """Alle Einträge eines Monats als {Tag(int): {"status": ..., "note": ...}}."""
    conn = _conn()
    prefix = "%04d-%02d" % (year, month)
    rows = conn.execute(
        "SELECT date, status, note FROM days WHERE date LIKE ?", (prefix + "-%",)
    ).fetchall()
    conn.close()
    out = {}
    for r in rows:
        day = int(r["date"].split("-")[2])
        out[day] = {"status": r["status"], "note": r["note"] or ""}
    return out


def set_day(y, m, d, status, note=""):
    key = day_key(y, m, d)
    conn = _conn()
    conn.execute(
        "INSERT INTO days (date, status, note) VALUES (?, ?, ?) "
        "ON CONFLICT(date) DO UPDATE SET status = excluded.status, note = excluded.note",
        (key, status, note),
    )
    conn.commit()
    conn.close()


def all_days():
    """Alle Einträge als (date, status, note) — für Zähler + Historie."""
    conn = _conn()
    rows = conn.execute("SELECT date, status, note FROM days ORDER BY date").fetchall()
    conn.close()
    return [(r["date"], r["status"], r["note"] or "") for r in rows]


def parse_key(key):
    try:
        y, m, d = key.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def count_safe_days(today=None):
    """Tage unfallfrei: seit dem letzten roten Tag ODER dem Startdatum (was später liegt)."""
    today = today or date.today()
    last_red = None
    for (key, status, _note) in all_days():
        if status == "red":
            d = parse_key(key)
            if d and d <= today and (last_red is None or d > last_red):
                last_red = d

    frm = None
    if last_red:
        frm = last_red + timedelta(days=1)

    start_date = get_config("start_date")
    if start_date:
        s = parse_key(start_date)
        if s and (frm is None or s > frm):
            frm = s

    if frm is None:
        frm = date(today.year, today.month, 1)

    return max((today - frm).days + 1, 0)
