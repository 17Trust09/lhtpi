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

Leer- und Kommentarzeilen (``#``) werden ignoriert.
"""
import os
from datetime import datetime

from models import db, Setting

ALLOWED_TYPES = {'kalibrierung', 'audit', 'info', 'wartung'}

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
    """Parst CSV-Text in eine Liste von Termin-Dicts (``date``-Objekte)."""
    rows = []
    header_seen = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = [p.strip() for p in line.split(';')]
        if not header_seen:
            header_seen = True  # erste Nicht-Kommentarzeile = Header
            continue
        while len(parts) < 6:
            parts.append('')
        typ = parts[0].lower() if len(parts) > 0 else ''
        titel = parts[1] if len(parts) > 1 else ''
        referenz = parts[2] if len(parts) > 2 else ''
        start = parse_date(parts[3] if len(parts) > 3 else '')
        ende = parse_date(parts[4] if len(parts) > 4 else '')
        text = parts[5] if len(parts) > 5 else ''
        if not titel:
            continue
        if typ not in ALLOWED_TYPES:
            typ = 'info'
        rows.append({
            'typ': typ,
            'titel': titel,
            'referenz': referenz or None,
            'start': start,
            'ende': ende,
            'text': text or None,
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
    row = Setting.query.get(key)
    return row.value if row else default


def set_setting(key, value):
    row = Setting.query.get(key)
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
