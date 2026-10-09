"""Tool-Registry für den Multitool-Kiosk.

Ein Gerät kann mehrere Tools zeigen (Folien, Termine, Safety Cross) — fest oder
rotierend. Diese Datei ist die EINE Quelle der Wahrheit für IDs, Labels, URLs und
Default-Anzeigedauern; Anzeige-Router, Admin-Seite und Installer lesen hier.
"""
import os
import socket
from urllib.parse import urlparse

TOOLS = {
    'slideshow': {
        'label': 'Folien / Playlist',
        'short': 'Folien',
        'url': 'http://localhost:8000/present/kiosk',
        'dwell': 60,
        'port': 8000,
    },
    'terminboard': {
        'label': 'Termine / Kalibrierungen',
        'short': 'Termine',
        'url': 'http://localhost:8001/board/kiosk',
        'dwell': 30,
        'port': 8001,
    },
    'safetycross': {
        'label': 'Safety Cross',
        'short': 'Safety Cross',
        'url': 'http://localhost:8002/',
        'dwell': 30,
        'port': 8002,
    },
}

DEFAULT_DWELL = 20
# Vom Installer geschriebene Liste der auf diesem Gerät installierten Tools.
TOOLS_FILE = os.environ.get('LHTPI_TOOLS_FILE', '/etc/lhtpi/tools')


def tool_ids():
    """Alle bekannten Tool-IDs (stabile Reihenfolge)."""
    return list(TOOLS)


def is_known(tool):
    return tool in TOOLS


def label(tool):
    return TOOLS.get(tool, {}).get('label', tool)


def short(tool):
    return TOOLS.get(tool, {}).get('short', tool)


def default_dwell(tool):
    return int(TOOLS.get(tool, {}).get('dwell', DEFAULT_DWELL))


def default_url(tool):
    return TOOLS.get(tool, {}).get('url', '')


def port_of(url_or_tool):
    if url_or_tool in TOOLS:
        return int(TOOLS[url_or_tool]['port'])
    p = urlparse(url_or_tool)
    return p.port or (443 if p.scheme == 'https' else 80)


def installed_tools():
    """Welche Tools sind auf DIESEM Gerät installiert?

    Quelle ist ``/etc/lhtpi/tools`` (vom Installer geschrieben) oder die
    Umgebungsvariable ``LHTPI_TOOLS``. Ohne Angabe (Entwicklung) gelten alle
    Tools als installiert.
    """
    raw = os.environ.get('LHTPI_TOOLS')
    if raw is None:
        try:
            with open(TOOLS_FILE) as f:
                raw = f.read()
        except OSError:
            raw = None
    if raw is None:
        return list(TOOLS)
    ids = [x.strip() for x in raw.replace('\n', ',').split(',') if x.strip()]
    return [t for t in ids if t in TOOLS]


def is_installed(tool):
    return tool in installed_tools()


def probe(url, timeout=0.6):
    """Kurzer TCP-Test: antwortet auf Zielhost/-port überhaupt ein Dienst?

    Wird mit ``LHTPI_KIOSK_PROBE=0`` abgeschaltet (Tests, Entwicklung).
    """
    if os.environ.get('LHTPI_KIOSK_PROBE', '1') == '0':
        return True
    p = urlparse(url)
    host = p.hostname or 'localhost'
    port = p.port or (443 if p.scheme == 'https' else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
