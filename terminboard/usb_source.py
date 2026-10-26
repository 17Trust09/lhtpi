"""Terminboard – USB-Stick mit ``termine.xlsx`` (oder ``termine.csv``) als Terminquelle.

Konvention
----------
Der Stick-Root enthält eine Datei ``termine.xlsx`` (bevorzugt) oder ``termine.csv``
(Fallback). Beide liefern Termine mit denselben sechs Feldern.

Excel-Vorlage (``USB/termine.xlsx``), Spalten::

    Art | Prüfstand | Von | Bis | Info

* ``Art``      – Kalibrierung | Audit | Wartung | Info (sonst → info)
* ``Prüfstand``– Pflicht (z. B. ``P3``)
* ``Von``      – Startdatum ``TT.MM.JJJJ`` oder ``JJJJ-MM-TT`` (Pflicht)
* ``Bis``      – optional, gleiche Datumsformate
* ``Info``     – Beschreibung (Pflicht)

CSV-Variante (``termine.csv``), Semikolon-getrennt, Header-Zeile::

    typ;titel;referenz;start;ende;text

Leer- und Kommentarzeilen (``#``) werden ignoriert. Zeilen ohne gültiges
Startdatum, ohne Titel oder mit zu wenigen Spalten werden übersprungen.
"""
import csv
import os
from datetime import date, datetime, timedelta

from models import db, Setting

ALLOWED_TYPES = {'kalibrierung', 'audit', 'info', 'wartung'}

EXPECTED_HEADER = ['typ', 'titel', 'referenz', 'start', 'ende', 'text']

USB_CSV_FILENAME = 'termine.csv'
USB_XLSX_FILENAME = 'termine.xlsx'
USB_TERMIN_FILENAMES = (USB_XLSX_FILENAME, USB_CSV_FILENAME)  # xlsx hat Vorrang
FIXED_MOUNT = '/mnt/lhtpi-usb'  # gemeinsamer Mount-Point mit LHTPi (ein Stick für beide Apps)

# Erste Spalte einer Kopfzeile („Art“) — erkennt die Kopfzeile zuverlässig.
# Wichtig: bewusst NICHT über alle Spalten geprüft, weil „Info“ sowohl
# Spaltenname (Spalte F) als auch gültiger Art-Wert ist.
HEADER_TYPE_KEYS = ('art', 'typ', 'type')

# Einstellungs-Keys
SETTING_MODE = 'player_mode'            # 'auto' | 'manual'
SETTING_MANUAL_SOURCE = 'manual_source'  # 'web' | 'usb'
SETTING_AZUBI_START = 'azubi_start'     # Startdatum 'JJJJ-MM-TT' (leer = dauerhaft aktiv)
SETTING_AZUBI_WEEKS = 'azubi_weeks'     # Anzeigedauer in Wochen (Default 2)

# Azubi-Info-Flyer: Bilder liegen im Ordner 'azubi' auf dem Stick (z. B. /mnt/lhtpi-usb/azubi/).
AZUBI_DIR_NAME = 'azubi'
AZUBI_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
# Optionale Einstellungs-Datei im azubi-Ordner (Startdatum + Anzeigedauer). Hat Vorrang vor dem Dashboard.
AZUBI_SETTINGS_FILENAME = 'azubi.txt'


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


def normalize_type(value):
    """Normalisiert die Art auf ``kalibrierung|audit|wartung|info`` (sonst ``info``)."""
    t = str(value or '').strip().lower()
    return t if t in ALLOWED_TYPES else 'info'


def _cell_to_date(value):
    """Wandelt einen Excel-Zellenwert (``date``/``datetime``/String) in ``date``."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return parse_date(value)


SPALTEN_ALIASE = {
    'nr': 'nr', 'nummer': 'nr',
    'art': 'art', 'typ': 'art',
    'pruefstand': 'pruefstand', 'prüfstand': 'pruefstand',
    'von': 'von', 'start': 'von',
    'bis': 'bis', 'ende': 'bis',
    'info': 'info', 'titel': 'info', 'bemerkung': 'info',
    'status': 'status',
}


def _header_map(cells):
    """Ordnet Spaltennamen ihrer Position zu.

    Nötig, weil zwei Formate im Umlauf sind: das alte mit fünf Spalten
    (Art, Prüfstand, Von, Bis, Info) und das neue mit Nummer und Status. Ohne
    diese Erkennung würde das neue Format spaltenweise verrutschen.
    """
    if not cells:
        return None
    namen = {}
    for position, zelle in enumerate(cells):
        name = str(zelle or '').strip().lower()
        if name in SPALTEN_ALIASE:
            namen[SPALTEN_ALIASE[name]] = position
    if 'pruefstand' in namen and 'von' in namen:
        return namen
    return None


def _looks_like_header(cells):
    """True, wenn die erste Zelle eine Kopfzeilen-Spalte (Art) ist."""
    if not cells:
        return False
    return str(cells[0] or '').strip().lower() in HEADER_TYPE_KEYS


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
        typ = normalize_type(parts[0])
        titel = parts[1].strip()
        referenz = parts[2].strip() or None
        start = parse_date(parts[3].strip())
        ende = parse_date(parts[4].strip())
        text = parts[5].strip() or None
        if not titel:
            continue
        if start is None:
            continue  # Pflicht-Startdatum fehlt oder ist ungültig
        rows.append({
            'typ': typ,
            'titel': titel,
            'referenz': referenz,
            'start': start,
            'ende': ende,
            'text': text,
        })
    return rows


def parse_azubi_settings(text):
    """Parst den Inhalt von ``azubi.txt`` in ``{'start': ..., 'weeks': ...}``.

    Format: eine Einstellung pro Zeile als ``key=wert``; ``#``-Zeilen sind Kommentare.
    * ``start`` – Startdatum ``TT.MM.JJJJ`` oder ``JJJJ-MM-TT`` (fehlt/leer → ``None`` = dauerhaft)
    * ``weeks`` – Anzeigedauer in Wochen (fehlt/leer → ``None`` = Default 2)
    """
    result = {'start': None, 'weeks': None}
    for line in (x.strip() for x in text.splitlines()):
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip().lower()
        value = value.strip()
        if key in ('start', 'startdatum', 'von'):
            result['start'] = value
        elif key in ('weeks', 'wochen', 'dauer'):
            result['weeks'] = value
    return result


def parse_termin_xlsx(file_path):
    """Liest ``termine.xlsx`` über den einheitlichen Excel-Leser.

    Es gibt nur noch **einen** Excel-Leser (``excel_modell2``). Diese Funktion
    übersetzt dessen Ergebnis in die Dict-Form, die die Anzeige erwartet.
    Dateien im alten Fünf-Spalten-Format werden abgelehnt.

    Liefert ``None``, wenn die Datei nicht gelesen werden kann.
    """
    if not os.path.isfile(file_path):
        return None
    try:
        from excel_modell2 import lies_datei
    except ImportError:
        return None

    daten = lies_datei(file_path)
    if daten['fehler']:
        return None

    rows = []
    for zeile in daten['zeilen']:
        if not zeile['pruefstand'] or zeile['von'] is None:
            continue
        titel = zeile['info'] or f"{zeile['art']} {zeile['pruefstand']}".strip()
        rows.append({
            'typ': normalize_type(zeile['art']),
            'titel': titel,
            'referenz': zeile['pruefstand'],
            'start': zeile['von'].date(),
            'ende': zeile['bis'].date() if zeile['bis'] else None,
            'text': None,
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


def read_termin_from_dir(mount_dir):
    """Liest Termine aus ``mount_dir`` — bevorzugt ``termine.xlsx``, sonst ``termine.csv``.

    Ist die ``termine.xlsx`` vorhanden, aber nicht lesbar (kaputt oder
    ``openpyxl`` fehlt), wird auf eine vorhandene ``termine.csv`` zurückgefallen.
    """
    xlsx = os.path.join(mount_dir, USB_XLSX_FILENAME)
    if os.path.isfile(xlsx):
        rows = parse_termin_xlsx(xlsx)
        if rows is not None:
            return rows
    return read_csv_from_dir(mount_dir)


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


def get_azubi_start():
    """Startdatum des Azubi-Flyers (``date`` oder ``None``).

    Liegt eine ``azubi.txt`` auf dem Stick vor, bestimmt sie die Einstellung;
    sonst gilt die DB-Einstellung aus dem Dashboard.
    """
    usb = read_azubi_settings()
    if usb:
        return parse_date(usb.get('start'))
    return parse_date(get_setting(SETTING_AZUBI_START, ''))


def _parse_weeks(raw):
    try:
        weeks = int(raw)
    except (TypeError, ValueError):
        return None
    return weeks if weeks >= 0 else None


def get_azubi_weeks():
    """Anzeigedauer des Azubi-Flyers in Wochen (Default 2).

    Liegt eine ``azubi.txt`` auf dem Stick vor, bestimmt sie die Einstellung;
    sonst gilt die DB-Einstellung aus dem Dashboard.
    """
    usb = read_azubi_settings()
    if usb:
        w = _parse_weeks(usb.get('weeks'))
        return 2 if w is None else w
    w = _parse_weeks(get_setting(SETTING_AZUBI_WEEKS, '2'))
    return 2 if w is None else w


def azubi_is_active(today=None):
    """True, wenn der Azubi-Flyer aktuell angezeigt werden darf.

    Ohne Startdatum ist er dauerhaft aktiv. Mit Startdatum gilt:
    Startdatum <= heute <= Startdatum + Wochen.
    """
    today = today or date.today()
    start = get_azubi_start()
    if start is None:
        return True
    end = start + timedelta(weeks=get_azubi_weeks())
    return start <= today <= end


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
    """Mögliche Pfade, unter denen ein Stick (mit ``termine.xlsx``/``termine.csv``) liegen kann.

    Unter ``/media`` und ``/run/media`` wird zusätzlich eine Ebene tiefer
    gesucht (Auto-Mount-Layout ``/media/<user>/<label>``). Unter ``/mnt``
    liegen Mount-Points direkt als Kinder (z. B. ``/mnt/lhtpi-usb``) — hier
    wird nicht tiefer gesucht, damit die Termin-Datei nicht fälschlich aus
    Unterordnern wie ``slides/`` erkannt wird.
    """
    seen = {FIXED_MOUNT}
    yield FIXED_MOUNT
    for root, deep in (('/media', True), ('/run/media', True), ('/mnt', False)):
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
            if not deep:
                continue
            try:
                subs = os.listdir(userdir)
            except OSError:
                continue
            for sub in subs:
                cand = os.path.join(userdir, sub)
                if not os.path.isdir(cand):
                    continue
                if cand not in seen:
                    yield cand
                    seen.add(cand)


def find_usb_termin_dir():
    """Liefert den Ordner mit ``termine.xlsx`` oder ``termine.csv`` (oder ``None``)."""
    for cand in _iter_mount_candidates():
        if not _is_valid_dir(cand):
            continue
        for fname in USB_TERMIN_FILENAMES:
            if os.path.isfile(os.path.join(cand, fname)):
                return cand
    return None


def usb_termine(mount_dir=None):
    """Liefert die Termin-Dicts vom Stick (oder ``[]`` wenn keiner erkannt)."""
    mount_dir = mount_dir or find_usb_termin_dir()
    if not mount_dir:
        return []
    return read_termin_from_dir(mount_dir)


def find_azubi_dir():
    """Liefert den ``azubi``-Ordner auf dem Stick (oder ``None``).

    Groß-/Kleinschreibung des Ordnernamens wird ignoriert (``azubi``/``Azubi``).
    """
    for cand in _iter_mount_candidates():
        if not _is_valid_dir(cand):
            continue
        try:
            entries = os.listdir(cand)
        except OSError:
            continue
        for name in entries:
            if name.lower() == AZUBI_DIR_NAME:
                p = os.path.join(cand, name)
                if os.path.isdir(p):
                    return p
    return None


def find_azubi_images():
    """Liefert sortierte Bild-Dateinamen im ``azubi``-Ordner (oder ``[]``)."""
    d = find_azubi_dir()
    if not d:
        return []
    try:
        entries = os.listdir(d)
    except OSError:
        return []
    return sorted(
        f for f in entries
        if os.path.isfile(os.path.join(d, f))
        and os.path.splitext(f)[1].lower() in AZUBI_IMAGE_EXTS
    )


def find_azubi_settings_file():
    """Liefert den Pfad zur ``azubi.txt`` im ``azubi``-Ordner (oder ``None``)."""
    d = find_azubi_dir()
    if not d:
        return None
    p = os.path.join(d, AZUBI_SETTINGS_FILENAME)
    if os.path.isfile(p):
        return p
    return None


def read_azubi_settings():
    """Liest die Azubi-Settings vom Stick (``azubi.txt``).

    Fehlt die Datei (oder ist sie nicht lesbar), wird ``{}`` geliefert —
    dann gelten die DB-Einstellungen aus dem Dashboard.
    """
    p = find_azubi_settings_file()
    if not p:
        return {}
    try:
        with open(p, encoding='utf-8', errors='ignore') as fh:
            return parse_azubi_settings(fh.read())
    except OSError:
        return {}

