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
# Vom Installer geschriebene Anzahl der Bildschirme dieses Geräts.
SCREENS_FILE = os.environ.get('LHTPI_SCREENS_FILE', '/etc/lhtpi/screens')


def _apply_url_overrides():
    """Tool-URLs per Umgebung überschreiben (Test/Demo):

    ``LHTPI_TOOL_URLS="slideshow=http://localhost:8900/present/kiosk,terminboard=..."``
    Im Normalbetrieb nicht gesetzt, dann gelten die URLs oben.
    """
    raw = os.environ.get('LHTPI_TOOL_URLS', '')
    for part in raw.split(','):
        if '=' not in part:
            continue
        tool, url = part.split('=', 1)
        tool, url = tool.strip(), url.strip()
        if tool in TOOLS and url:
            TOOLS[tool]['url'] = url


_apply_url_overrides()


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
    """Welche Tools sind auf DIESEM Gerät installiert UND lizenziert?

    Quelle ist ``/etc/lhtpi/tools`` (vom Installer geschrieben) oder die
    Umgebungsvariable ``LHTPI_TOOLS``. Ohne Angabe (Entwicklung) gelten alle
    Tools als installiert. Ist eine Hardware-Lizenz hinterlegt, werden
    zusätzlich nur die darin freigegebenen Tools ausgeliefert.
    """
    raw = os.environ.get('LHTPI_TOOLS')
    if raw is None:
        try:
            with open(TOOLS_FILE) as f:
                raw = f.read()
        except OSError:
            raw = None
    if raw is None:
        ids = list(TOOLS)
    else:
        ids = [x.strip() for x in raw.replace('\n', ',').split(',') if x.strip()]
        ids = [t for t in ids if t in TOOLS]
    lizenziert = licensed_tools()
    if lizenziert is not None:
        ids = [t for t in ids if t in lizenziert]
    return ids


def licensed_tools():
    """Tool-IDs laut Hardware-Lizenz (``None``, wenn keine hinterlegt ist)."""
    try:
        import license_bundle
    except ImportError:
        return None
    return license_bundle.licensed_tools()


def licensed_screen_limit():
    """Anzahl Bildschirme laut Lizenz (``None``, wenn keine hinterlegt ist)."""
    try:
        import license_bundle
    except ImportError:
        return None
    return license_bundle.licensed_screens()


def is_installed(tool):
    return tool in installed_tools()


def configured_screen_count():
    """Bildschirm-Anzahl, die der Installer auf diesem Gerät eingetragen hat.

    Quelle ist ``/etc/lhtpi/screens`` bzw. ``LHTPI_SCREEN_COUNT``. Ist nichts
    eingetragen (Entwicklung), wird ``None`` geliefert und der Aufrufer
    entscheidet selbst.
    """
    raw = os.environ.get('LHTPI_SCREEN_COUNT')
    if raw is None:
        try:
            with open(SCREENS_FILE) as f:
                raw = f.read()
        except OSError:
            return None
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


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
