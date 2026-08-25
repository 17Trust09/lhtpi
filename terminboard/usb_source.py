"""Terminboard – USB-Stick mit ``termine.csv`` als Terminquelle.

Konvention
----------
Der Stick-Root enthält eine Datei ``termine.csv`` (UTF-8, Semikolon-getrennt,
mit Header-Zeile). Spalten (exakt)::

    typ;titel;referenz;start;ende;text

* ``typ``     – kalibrierung | audit | info | wartung (sonst → info)
* ``titel``   – Pflicht (Zeilen ohne Titel werden ignoriert)
* ``referenz``– optional (z. B. ``P3``)
* ``start``   – ``TT.MM.JJJJ`` oder ``JJJJ-MM-TT`` (Pflicht)
* ``ende``    – optional, gleiche Datumsformate
* ``text``    – optionaler Einzeiler

Leer- und Kommentarzeilen (``#``) werden ignoriert. Zeilen ohne gültiges
Startdatum, ohne Titel oder mit zu wenigen Spalten werden übersprungen.
"""
import csv
import os
from datetime import datetime

from models import db, Setting

ALLOWED_TYPES = {'kalibrierung', 'audit', 'info', 'wartung'}

EXPECTED_HEADER = ['typ', 'titel', 'referenz', 'start', 'ende', 'text']

USB_CSV_FILENAME = 'termine.csv'
FIXED_MOUNT = '/mnt/terminboard-usb'

# Einstellungs-Keys
SETTING_MODE = 'player_mode'            # 'auto' | 'manual'
SETTING_MANUAL_SOURCE = 'manual_source'  # 'web' | 'usb'


# ── Reine Helfer (ohne DB, gut testbar) ───────────────────────────────

def parse_date(value):
    """Parst ``TT.MM.JJJJ`` oder ``JJJJ-MM-TT``. Liefert ``date`` oder ``None``."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_termin_csv(text):
    """Parst CSV-Text in eine Liste von Termin-Dicts (``date``-Objekte).

    Verwendet das ``csv``-Modul (unterstützt Quoting), erkennt die Header-Zeile
    und überspringt Zeilen ohne gültiges Pflicht-Startdatum oder ohne Titel.
    """
    rows = []
    lines = [l for l in (x.strip() for x in text.splitlines())
             if l and not l.startswith('#')]
    if not lines:
        return rows

    reader = csv.reader(lines, delimiter=';')
    first = next(reader, None)
    if first is None:
        return rows

    is_header = [c.strip().lower() for c in first] == EXPECTED_HEADER
    records = list(reader)
    if not is_header:
        # Keine Header-Zeile vorhanden → erste Zeile ist ein Datensatz
        records.insert(0, first)

    for parts in records:
        if len(parts) < 4:
            continue  # zu wenige Spalten (mind. typ;titel;referenz;start)
        while len(parts) < 6:
            parts.append('')
        typ = parts[0].strip().lower()
        titel = parts[1].strip()
        referenz = parts[2].strip() or None
        start = parse_date(parts[3].strip())
        ende = parse_date(parts[4].strip())
        text = parts[5].strip() or None
        if not titel:
            continue
        if start is None:
            continue  # Pflicht-Startdatum fehlt oder ist ungültig
        if typ not in ALLOWED_TYPES:
            typ = 'info'
        rows.append({
            'typ': typ,
            'titel': titel,
            'referenz': referenz,
            'start': start,
            'ende': ende,
            'text': text,
        })
    return rows


def read_csv_from_dir(mount_dir):
    """Liest ``termine.csv`` aus ``mount_dir`` und liefert Termin-Dicts."""
    path = os.path.join(mount_dir, USB_CSV_FILENAME)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding='utf-8', errors='ignore') as fh:
            return parse_termin_csv(fh.read())
    except OSError:
        return []


# ── Einstellungs-Helfer (DB) ──────────────────────────────────────────

def get_setting(key, default=None):
    row = db.session.get(Setting, key)
    return row.value if row else default


def set_setting(key, value):
    row = db.session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value='')
        db.session.add(row)
    row.value = str(value)
    db.session.commit()


def get_mode():
    return get_setting(SETTING_MODE, 'auto')


def get_manual_source():
    return get_setting(SETTING_MANUAL_SOURCE, 'web')


# ── USB-Erkennung ─────────────────────────────────────────────────────

def _is_valid_dir(path):
    """True, wenn ``path`` ein lesbarer Ordner ist (schützt vor stale Mount)."""
    if not os.path.isdir(path):
        return False
    try:
        os.listdir(path)
        return True
    except OSError:
        return False


def _iter_mount_candidates():
    """Mögliche Pfade, unter denen ein Stick (mit ``termine.csv``) liegen kann."""
    seen = {FIXED_MOUNT}
    yield FIXED_MOUNT
    for root in ('/media', '/run/media', '/mnt'):
        if not os.path.isdir(root):
            continue
        try:
            entries = os.listdir(root)
        except OSError:
            continue
        for name in entries:
            userdir = os.path.join(root, name)
            if not os.path.isdir(userdir):
                continue
            if userdir not in seen:
                yield userdir
                seen.add(userdir)
            try:
                subs = os.listdir(userdir)
            except OSError:
                continue
            for sub in subs:
                cand = os.path.join(userdir, sub)
                if cand not in seen:
                    yield cand
                    seen.add(cand)


def find_usb_csv_dir():
    """Liefert den Ordner mit ``termine.csv`` eines Sticks oder ``None``."""
    for cand in _iter_mount_candidates():
        if _is_valid_dir(cand) and os.path.isfile(os.path.join(cand, USB_CSV_FILENAME)):
            return cand
    return None


def usb_termine(mount_dir=None):
    """Liefert die Termin-Dicts vom Stick (oder ``[]`` wenn keiner erkannt)."""
    mount_dir = mount_dir or find_usb_csv_dir()
    if not mount_dir:
        return []
    return read_csv_from_dir(mount_dir)
