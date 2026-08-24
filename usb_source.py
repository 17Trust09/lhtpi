"""LHTPi – USB-Stick als Präsentationsquelle.

Erkennt einen angeschlossenen USB-Stick, der im Root einen Ordner
``slides/`` enthält, und liefert dessen Medien als Playlist.

Konvention
----------
* Ordner ``slides/`` im Stick-Root enthält die Medien (Bilder/Videos).
* Dateien werden alphabetisch (case-insensitive) sortiert abgespielt.
* Optional ``slides/settings.txt`` für Anzeigedauern::

      # Kommentar
      default=10          # Standarddauer pro Bild in Sekunden (Default: 10)
      bild.jpg=8          # Dauer für ein einzelnes Bild
      video.mp4=0         # 0 = volle Videolänge

Erlaubte Endungen: png, jpg, jpeg, gif, mp4.
Unterordner werden ignoriert (nur Dateien direkt in ``slides/``).
"""
import os

from models import db, Setting

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4'}

# Name des Ordners auf dem Stick, der die Medien enthält.
USB_SLIDES_FOLDER = 'slides'

# Einstellungs-Keys
SETTING_MODE = 'player_mode'          # 'auto' | 'manual'
SETTING_MANUAL_SOURCE = 'manual_source'  # 'web' | 'usb'

DEFAULT_IMAGE_DURATION = 10  # Sekunden, falls nichts konfiguriert


# ── Einstellungs-Helfer ────────────────────────────────────────────────

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


# ── USB-Erkennung ──────────────────────────────────────────────────────

def _is_slides_dir(path):
    """True, wenn `path` ein lesbarer Ordner ist, der als Slides-Quelle taugt.

    Prüft zusätzlich per ``listdir``, ob der Mount noch gültig ist. So wird ein
    bereits herausgezogener Stick (verwaister Mount-Punkt) nicht fälschlich als
    vorhanden erkannt – ``listdir`` wirft dann einen OSError.
    """
    if not os.path.isdir(path):
        return False
    try:
        os.listdir(path)
        return True
    except OSError:
        return False


def _iter_mount_candidates():
    """Liefert mögliche Pfade, unter denen ein Stick-Slides-Ordner liegen kann.

    Deckt die üblichen Auto-Mount-Ziele ab:
    * Raspberry Pi OS Desktop: /media/<user>/<LABEL>
    * udisks2/systemd:         /run/media/<user>/<LABEL>
    * usbmount:                /media/usb0..usbN
    * festes udev-Ziel:        /mnt/lhtpi-usb
    """
    roots = ['/media', '/run/media', '/mnt']
    seen = set()

    # Fester Mount-Punkt zuerst (falls via udev dorthin gemountet wird).
    fixed = os.path.join('/mnt', 'lhtpi-usb', USB_SLIDES_FOLDER)
    yield fixed
    seen.add(fixed)

    for root in roots:
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
            # usbmount-Stil: /media/usb0 direkt
            if name.startswith('usb') and name[3:].isdigit():
                cand = os.path.join(userdir, USB_SLIDES_FOLDER)
                if cand not in seen:
                    yield cand
                    seen.add(cand)
                continue
            # Direkt unter dem Benutzerordner
            cand = os.path.join(userdir, USB_SLIDES_FOLDER)
            if cand not in seen:
                yield cand
                seen.add(cand)
            # Eine Ebene tiefer (Mount-Label unterhalb des Benutzers)
            try:
                subentries = os.listdir(userdir)
            except OSError:
                continue
            for sub in subentries:
                cand = os.path.join(userdir, sub, USB_SLIDES_FOLDER)
                if cand not in seen:
                    yield cand
                    seen.add(cand)


def find_usb_slides_dir():
    """Liefert den Pfad zum Slides-Ordner eines Stick oder None."""
    for cand in _iter_mount_candidates():
        if _is_slides_dir(cand):
            return cand
    return None


def read_usb_settings(slides_dir):
    """Liest ``settings.txt`` aus dem Slides-Ordner.

    Liefert ein dict mit ``default`` (int) sowie Dateiname -> Dauer (int).
    """
    result = {}
    path = os.path.join(slides_dir, 'settings.txt')
    if not os.path.isfile(path):
        return result
    try:
        with open(path, encoding='utf-8', errors='ignore') as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' not in line:
                    continue
                key, _, val = line.partition('=')
                key = key.strip()
                val = val.split('#', 1)[0].strip()  # Inline-Kommentare entfernen
                if not key:
                    continue
                try:
                    result[key] = int(val)
                except ValueError:
                    # Nicht-numerische Werte (z. B. Kommentar nach '=') ignorieren
                    continue
    except OSError:
        pass
    return result


def list_usb_files(slides_dir):
    """Liefert die sortierte Liste der Medien-Dateinamen im Slides-Ordner."""
    files = []
    try:
        names = os.listdir(slides_dir)
    except OSError:
        return files
    for name in names:
        path = os.path.join(slides_dir, name)
        if not os.path.isfile(path):
            continue
        ext = name.rsplit('.', 1)[1].lower() if '.' in name else ''
        if ext in ALLOWED_EXTENSIONS:
            files.append(name)
    files.sort(key=str.lower)
    return files


def usb_items(slides_dir, url_builder):
    """Baut die Item-Liste für den Kiosk aus dem Stick-Inhalt.

    ``url_builder(filename)`` erzeugt die Ausliefer-URL für eine Datei.
    """
    settings = read_usb_settings(slides_dir)
    default_duration = settings.get('default', DEFAULT_IMAGE_DURATION)
    items = []
    for idx, filename in enumerate(list_usb_files(slides_dir)):
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        file_type = 'video' if ext == 'mp4' else 'image'
        if filename in settings:
            duration = settings[filename]
        elif file_type == 'video':
            duration = 0  # volle Länge
        else:
            duration = default_duration
        items.append({
            'id': 'usb-%d' % idx,
            'media_id': 'usb-%d' % idx,
            'position': idx,
            'display_duration': max(0, duration),
            'filename': filename,
            'file_type': file_type,
            'original_name': filename,
            'url': url_builder(filename),
        })
    return items
