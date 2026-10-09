"""Hardware-Lizenz für das Multitool-Kiosk-Bundle.

Idee
----
Eine Lizenz gilt für **genau ein Gerät** und schaltet **genau die gebuchten
Tools** und **die gebuchte Anzahl Bildschirme** frei.

  * Geräte-ID  = Seriennummer des Raspberry Pi (``/proc/cpuinfo``), sonst
    ``/etc/machine-id``, sonst erste MAC-Adresse.
  * Lizenzschlüssel = ``LHTPI-XXXX-XXXX-XXXX-XXXX``. Die ersten drei Zeichen
    tragen die Nutzlast (Tools + Bildschirme + Kurzkennung des Geräts), die
    restlichen 13 eine HMAC-Signatur darüber.
  * Eine Kopie der SD-Karte auf einem anderen Pi hat eine andere Seriennummer →
    Signatur passt nicht → die Lizenz ist ungültig. Nichts ist „einfach
    kopierbar".

Grenze der Ehrlichkeit: Wer den Signaturschlüssel (``SECRET``) aus dem Image
holt, kann sich selbst Lizenzen erzeugen. Deshalb gehört der Schlüssel im
ausgelieferten Image verschleiert (siehe Skill ``python-source-protection``).

Werkzeuge
---------
    python3 license_bundle.py --info                       # Geräte-ID anzeigen
    python3 license_bundle.py --make-key --tools=1,3 --screens=2
    python3 license_bundle.py --install --tools=1,2,3 --screens=2   # für DIESES Gerät
    python3 license_bundle.py --check                      # installierte Lizenz prüfen
"""
import hashlib
import hmac
import os
import re
import sys

# Signaturschlüssel (siehe Hinweis oben: im Image verschleiern).
SECRET = b'LHTPI-Bundle-2026-7f3a91c4e8b25d60-key-v1'
PREFIX = 'LHTPI'
# Alphabet ohne I, O, 0, 1 – verhindert Verwechslungen beim Abtippen.
ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
GROUPS = 4          # 4 Zeichen je Gruppe
CHARS = 16          # Nutzlast 3 + Signatur 13

TOOLS_FILE = os.environ.get('LHTPI_TOOLS_FILE', '/etc/lhtpi/tools')
LICENSE_FILE = os.environ.get('LHTPI_LICENSE_FILE', '/etc/lhtpi/license.key')
MARKER_FILE = os.environ.get('LHTPI_INSTALLED_MARKER', '/etc/lhtpi/installed')

TOOL_ORDER = ['slideshow', 'terminboard', 'safetycross']
TOOL_BITS = {'slideshow': 1, 'terminboard': 2, 'safetycross': 4}
TOOL_INDEX = {'1': 'slideshow', '2': 'terminboard', '3': 'safetycross',
              'slideshow': 'slideshow', 'terminboard': 'terminboard',
              'safetycross': 'safetycross', 'safety-cross': 'safetycross'}


# ── Geräte-ID ─────────────────────────────────────────────────────────────

def _pi_serial():
    try:
        with open('/proc/cpuinfo') as f:
            for line in f:
                if line.lower().startswith('serial'):
                    return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return ''


def _machine_id():
    try:
        with open('/etc/machine-id') as f:
            return f.read().strip()
    except OSError:
        return ''


def _first_mac():
    import glob
    for path in sorted(glob.glob('/sys/class/net/*/address')):
        try:
            with open(path) as f:
                mac = f.read().strip()
        except OSError:
            continue
        if mac and mac != '00:00:00:00:00:00' and not mac.startswith('00:00:00'):
            return mac
    return ''


def hardware_id(hwid=None):
    """Eindeutige Kennung dieses Geräts (überschreibbar mit LHTPI_HWID)."""
    if hwid:
        return hwid
    forced = os.environ.get('LHTPI_HWID')
    if forced:
        return forced
    serial = _pi_serial()
    if serial:
        return 'piserial:%s' % serial
    mid = _machine_id()
    if mid:
        return 'machine:%s' % mid
    mac = _first_mac()
    if mac:
        return 'mac:%s' % mac
    import socket
    return 'host:%s' % socket.gethostname()


def hardware_short(hwid=None, bits=10):
    """Kurzkennung des Geräts für die Nutzlast (Standard: 10 Bit)."""
    h = hashlib.sha256((hwid or hardware_id()).encode()).hexdigest()
    return int(h[:12], 16) & ((1 << bits) - 1)


# ── Kodierung ─────────────────────────────────────────────────────────────

def _encode(num, width):
    out = ''
    for _ in range(width):
        out = ALPHABET[num & 31] + out
        num >>= 5
    return out


def _decode(text):
    num = 0
    for ch in text:
        idx = ALPHABET.find(ch)
        if idx < 0:
            return None
        num = num * 32 + idx
    return num


def normalize(key):
    """Schlüssel in die reine Zeichenform bringen (Trenner und Präfix weg)."""
    if not key:
        return ''
    raw = re.sub(r'[^A-Za-z0-9]', '', key).upper()
    if raw.startswith(PREFIX):
        raw = raw[len(PREFIX):]
    return raw


def format_key(raw):
    return PREFIX + '-' + '-'.join(raw[i:i + GROUPS] for i in range(0, len(raw), GROUPS))


def _signature(payload_chars, hwid=None):
    """Signatur über Nutzlast UND volle Geräte-ID.

    Dadurch gilt ein Schlüssel nur auf dem Gerät, für das er erzeugt wurde –
    eine kopierte SD-Karte (andere Seriennummer) hat eine andere Signatur.
    """
    msg = '%s|%s' % (payload_chars, hardware_id(hwid))
    mac = hmac.new(SECRET, msg.encode(), hashlib.sha256).hexdigest()
    return _encode(int(mac[:16], 16), CHARS - len(payload_chars))


# ── Schlüssel erzeugen und prüfen ─────────────────────────────────────────

def tool_ids(argv_tools):
    """Aus ``1,3`` bzw. ``slideshow,safetycross`` die Tool-IDs machen."""
    ids = []
    for part in re.split(r'[,\s]+', (argv_tools or '')):
        part = part.strip().lower()
        if not part:
            continue
        tool = TOOL_INDEX.get(part)
        if tool is None:
            raise ValueError('Unbekanntes Tool: %s' % part)
        if tool not in ids:
            ids.append(tool)
    return ids


def make_key(tools, screens=1, hwid=None):
    """Lizenzschlüssel für ein Gerät erzeugen. ``tools`` = Liste oder '1,3'."""
    if isinstance(tools, str):
        tools = tool_ids(tools)
    mask = 0
    for tool in tools:
        if tool not in TOOL_BITS:
            raise ValueError('Unbekanntes Tool: %s' % tool)
        mask |= TOOL_BITS[tool]
    if mask == 0:
        raise ValueError('Mindestens ein Tool muss lizenziert sein')
    screens = max(1, min(2, int(screens)))
    value = mask | ((screens - 1) << 3) | (hardware_short(hwid) << 4)
    payload = _encode(value, 3)
    return format_key(payload + _signature(payload, hwid))


def verify(key, hwid=None):
    """Lizenz prüfen.

    Rückgabe: ``{'valid': bool, 'reason': str, 'tools': [...], 'screens': int}``
    """
    raw = normalize(key)
    out = {'valid': False, 'reason': '', 'tools': [], 'screens': 0}
    bad = [c for c in raw if c not in ALPHABET]
    if bad:
        out['reason'] = 'Ungültige Zeichen im Schlüssel: %s' % ' '.join(sorted(set(bad)))
        return out
    if len(raw) != CHARS:
        out['reason'] = 'Länge passt nicht (erwartet %d Zeichen)' % CHARS
        return out
    payload, sig = raw[:3], raw[3:]
    if not hmac.compare_digest(sig, _signature(payload, hwid)):
        value = _decode(payload)
        hint = (value >> 4) & 0x3FF if value is not None else None
        if hint is not None and hint != hardware_short(hwid):
            out['reason'] = 'Lizenz gehört zu einem anderen Gerät'
        else:
            out['reason'] = 'Signatur stimmt nicht (Schlüssel falsch abgetippt oder verändert)'
        return out
    value = _decode(payload)
    if value is None:
        out['reason'] = 'Nutzlast unlesbar'
        return out
    mask = value & 0x7
    screens = ((value >> 3) & 0x1) + 1
    hw = (value >> 4) & 0x3FF
    if hw != hardware_short(hwid):
        out['reason'] = 'Lizenz gehört zu einem anderen Gerät'
        return out
    tools = [t for t in TOOL_ORDER if mask & TOOL_BITS[t]]
    if not tools:
        out['reason'] = 'Kein Tool lizenziert'
        return out
    out.update(valid=True, tools=tools, screens=screens)
    return out


# ── Lizenz auf dem Gerät ──────────────────────────────────────────────────

def read_license(path=None):
    path = path or LICENSE_FILE
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ''


def write_license(key, path=None):
    path = path or LICENSE_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(format_key(normalize(key)) + '\n')
    os.chmod(path, 0o644)
    return path


def enforced():
    """Ist die Lizenzprüfung auf diesem Gerät aktiv?

    Aktiv, wenn eine Lizenzdatei existiert, das Installationsmerkmal gesetzt ist
    oder ``LHTPI_LICENSE_ENFORCE=1``. In der Entwicklung (nichts davon) läuft die
    App ohne Sperre, damit man arbeiten kann.
    """
    if os.environ.get('LHTPI_LICENSE_ENFORCE') == '1':
        return True
    if os.environ.get('LHTPI_LICENSE_ENFORCE') == '0':
        return False
    return bool(read_license()) or os.path.exists(MARKER_FILE)


def current(hwid=None):
    """Lizenz dieses Geräts prüfen (oder ``None``, wenn keine hinterlegt ist)."""
    key = read_license()
    if not key:
        return None
    return verify(key, hwid=hwid)


def licensed_tools(hwid=None):
    """Welche Tools die Lizenz freigibt (``None`` = keine Lizenz vorhanden)."""
    info = current(hwid=hwid)
    if info is None:
        return None
    return info['tools'] if info['valid'] else []


def licensed_screens(hwid=None):
    info = current(hwid=hwid)
    if info is None or not info['valid']:
        return None
    return info['screens']


# ── Kommandozeile ─────────────────────────────────────────────────────────

def _arg(name, default=''):
    for a in sys.argv[1:]:
        if a.startswith('--%s=' % name):
            return a.split('=', 1)[1]
    return default


def main():
    arg_tools = _arg('tools')
    arg_screens = _arg('screens', '1')
    arg_hwid = _arg('hwid') or None

    if '--info' in sys.argv:
        print('Geräte-ID:   %s' % hardware_id())
        print('Kurzkennung: %d' % hardware_short(arg_hwid))
        print('Lizenzdatei: %s' % LICENSE_FILE)
        return 0

    if '--make-key' in sys.argv:
        try:
            key = make_key(arg_tools, arg_screens, hwid=arg_hwid)
        except ValueError as exc:
            print('Fehler: %s' % exc, file=sys.stderr)
            return 2
        print(key)
        return 0

    if '--install' in sys.argv:
        try:
            key = make_key(arg_tools, arg_screens, hwid=arg_hwid)
        except ValueError as exc:
            print('Fehler: %s' % exc, file=sys.stderr)
            return 2
        path = write_license(key)
        info = verify(key, hwid=arg_hwid)
        print('Lizenz geschrieben: %s' % path)
        print('  Tools:      %s' % ', '.join(info['tools']))
        print('  Bildschirme: %d' % info['screens'])
        return 0

    if '--check' in sys.argv:
        info = current(hwid=arg_hwid)
        if info is None:
            print('Keine Lizenz hinterlegt (%s)' % LICENSE_FILE)
            return 1
        if info['valid']:
            print('Lizenz gültig für dieses Gerät')
            print('  Tools:      %s' % ', '.join(info['tools']))
            print('  Bildschirme: %d' % info['screens'])
            return 0
        print('Lizenz ungültig: %s' % info['reason'])
        return 1

    print(__doc__)
    return 0


if __name__ == '__main__':
    sys.exit(main())
