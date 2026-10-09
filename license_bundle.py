"""Hardware-Lizenz für das Multitool-Kiosk-Bundle.

Idee
----
Eine Lizenz gilt für **genau ein Gerät** und schaltet **genau die gebuchten
Tools** und **die gebuchte Anzahl Bildschirme** frei.

  * Geräte-ID  = Seriennummer des Raspberry Pi (``/proc/cpuinfo``), sonst
    ``/etc/machine-id``, sonst erste MAC-Adresse.
  * Lizenz: ``LHTPI-<Nutzlast>-<Signatur>``. Die Nutzlast (3 Zeichen) trägt
    Tools + Bildschirme + Kurzkennung des Geräts, dahinter steht eine
    **RSA-2048-Signatur** (SHA-256, PKCS#1 v1.5) über Nutzlast **und** volle
    Geräte-ID.
  * Eine Kopie der SD-Karte auf einem anderen Pi hat eine andere Seriennummer →
    Signatur passt nicht → Lizenz ungültig.
  * Signiert wird mit dem **privaten** Schlüssel. Der liegt **außerhalb** dieses
    Repos (``LHTPI_SIGN_KEY_FILE``, Standard ``~/.lhtpi/lizenz-privat.json``).
    Im Code steht nur der **öffentliche** Schlüssel. Wer den Code liest, kann
    deshalb keine Lizenz erzeugen — er hat den privaten Schlüssel nicht.

Werkzeuge
---------
    python3 license_bundle.py --info                       # Geräte-ID + Schalter
    python3 license_bundle.py --make-key --tools=1,3 --screens=2
    python3 license_bundle.py --install --tools=1,2,3 --screens=2   # für DIESES Gerät
    python3 license_bundle.py --check                      # installierte Lizenz prüfen

``--make-key`` und ``--install`` brauchen den privaten Schlüssel — auf dem
ausgelieferten Gerät sind sie damit wirkungslos (Werkzeuge nur zum Nachweis).
"""
import functools
import hashlib
import hmac
import json
import os
import re
import sys

PREFIX = 'LHTPI'
# Alphabet ohne I, O, 0, 1 – verhindert Verwechslungen beim Abtippen.
ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
PAYLOAD_CHARS = 3    # Nutzlast (Tools, Bildschirme, Kurzkennung)
SIG_HEX_BREITE = 64  # Signatur in 64er-Blöcken umbrechen (nur Optik)

# Öffentlicher Schlüssel (RSA-2048). Der private Teil liegt außerhalb des Repos.
PUBLIC_KEY_N_HEX = 'ba1695e5bc50c81881a133069cc2584fa6fc4a928c7d3ce547635ea570a8d4cda9ac49d3a3af77a3d1388d3a82734459f30b6cb34763560d178c5d2d48cb2b1823c88cfaffd22c57229ccafda0492f4bd14e2fbce34969442b159e7e1ba99ec2d2d2bc54eff2da0febcd5f2d8a19be1d165a1677c4bc88f5c13947e77a8a4774d84a3b29e1b4e6ee7841fe5f9fadec30e633fd44d4bcbe3e5dc268fbfb580319da41a1e1ab72408a2ced1a7ec7dfdd1245277a4e275a5999c374018fedc0433847c0422e0b3d2099776429823957aca61e6f9ba6ad64c1870004a8a8abc012cc12385fc59540264e2d9686d320bb00c6c30fd60ecafb360f0b42b2a5998fd1bb'
PUBLIC_KEY_E = 65537

PRIVATE_KEY_FILE = os.environ.get(
    'LHTPI_SIGN_KEY_FILE', os.path.expanduser('~/.lhtpi/lizenz-privat.json'))

TOOLS_FILE = os.environ.get('LHTPI_TOOLS_FILE', '/etc/lhtpi/tools')
LICENSE_FILE = os.environ.get('LHTPI_LICENSE_FILE', '/etc/lhtpi/license.key')
MARKER_FILE = os.environ.get('LHTPI_INSTALLED_MARKER', '/etc/lhtpi/installed')

TOOL_ORDER = ['slideshow', 'terminboard', 'safetycross']
TOOL_BITS = {'slideshow': 1, 'terminboard': 2, 'safetycross': 4}
TOOL_INDEX = {'1': 'slideshow', '2': 'terminboard', '3': 'safetycross',
              'slideshow': 'slideshow', 'terminboard': 'terminboard',
              'safetycross': 'safetycross', 'safety-cross': 'safetycross'}

# DigestInfo für SHA-256 (RFC 8017, PKCS#1 v1.5)
SHA256_DIGESTINFO = bytes.fromhex('3031300d060960864801650304020105000420')


class SignaturschluesselFehlt(Exception):
    """Der private Signaturschlüssel ist nicht vorhanden (Kundenimage)."""


# ── Schlüssel ─────────────────────────────────────────────────────────────

def public_key():
    """Öffentlicher Schlüssel — ``LHTPI_PUBKEY=n:e`` (hex) überschreibt ihn."""
    override = os.environ.get('LHTPI_PUBKEY')
    if override:
        n_hex, _, e = override.partition(':')
        return {'n': int(n_hex, 16), 'e': int(e) if e else PUBLIC_KEY_E}
    return {'n': int(PUBLIC_KEY_N_HEX, 16), 'e': PUBLIC_KEY_E}


def private_key(path=None):
    """Privaten Schlüssel laden — ``None``, wenn keiner hinterlegt ist."""
    pfad = path or os.environ.get('LHTPI_SIGN_KEY_FILE') or PRIVATE_KEY_FILE
    try:
        with open(pfad) as f:
            daten = json.load(f)
    except (OSError, ValueError):
        return None
    if not daten.get('n') or not daten.get('d'):
        return None
    return {'n': int(daten['n'], 16), 'e': int(daten.get('e', PUBLIC_KEY_E)),
            'd': int(daten['d'], 16), 'quelle': pfad}


def _schluessel_laenge(n):
    return (n.bit_length() + 7) // 8


def _encoded_message(digest, k):
    """EM nach PKCS#1 v1.5: 00 01 FF..FF 00 DigestInfo Digest."""
    ps = k - 3 - len(SHA256_DIGESTINFO) - len(digest)
    if ps < 8:
        raise ValueError('Schlüssel zu kurz für die Signatur')
    return b'\x00\x01' + b'\xff' * ps + b'\x00' + SHA256_DIGESTINFO + digest


def rsa_verify(nachricht, signatur, schluessel=None):
    """Signatur prüfen (nur mit dem öffentlichen Schlüssel)."""
    schluessel = schluessel or public_key()
    n, e = schluessel['n'], schluessel['e']
    k = _schluessel_laenge(n)
    if len(signatur) != k:
        return False
    wert = int.from_bytes(signatur, 'big')
    if wert >= n:
        return False
    em = pow(wert, e, n).to_bytes(k, 'big')
    erwartet = _encoded_message(hashlib.sha256(nachricht).digest(), k)
    return hmac.compare_digest(em, erwartet)


def rsa_sign(nachricht, schluessel):
    """Signieren (nur mit dem privaten Schlüssel)."""
    n = schluessel['n']
    k = _schluessel_laenge(n)
    em = _encoded_message(hashlib.sha256(nachricht).digest(), k)
    signatur = pow(int.from_bytes(em, 'big'), schluessel['d'], n)
    return signatur.to_bytes(k, 'big')


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
    """Schlüssel in die reine Zeichenform bringen (Trenner, Präfix, Zeilen weg)."""
    if not key:
        return ''
    raw = re.sub(r'[^A-Za-z0-9]', '', key).upper()
    if raw.startswith(PREFIX):
        raw = raw[len(PREFIX):]
    return raw


def format_key(raw, breite=SIG_HEX_BREITE):
    """Lesbare Form: Kopfzeile mit Nutzlast, Signatur in Blöcken darunter."""
    payload, sig = raw[:PAYLOAD_CHARS], raw[PAYLOAD_CHARS:]
    zeilen = ['%s-%s-%s' % (PREFIX, payload, sig[:breite])]
    for i in range(breite, len(sig), breite):
        zeilen.append(sig[i:i + breite])
    return '\n'.join(zeilen)


def _message(payload_chars, hwid=None):
    """Was signiert wird: Nutzlast UND volle Geräte-ID."""
    return ('%s|%s' % (payload_chars, hardware_id(hwid))).encode()


def signatur_hex(payload_chars, hwid=None, schluessel=None):
    """Signatur erzeugen (braucht den privaten Schlüssel)."""
    schluessel = schluessel or private_key()
    if schluessel is None:
        raise SignaturschluesselFehlt(
            'Privater Signaturschlüssel fehlt (%s). Ohne ihn lassen sich keine '
            'Lizenzen erzeugen.' % PRIVATE_KEY_FILE)
    return rsa_sign(_message(payload_chars, hwid), schluessel).hex().upper()


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
    payload = _encode(value, PAYLOAD_CHARS)
    return format_key(payload + signatur_hex(payload, hwid))


@functools.lru_cache(maxsize=16)
def _pruefe(key, hwid, _pub_n):
    return _pruefe_ohne_cache(key, hwid)


def _pruefe_ohne_cache(key, hwid=None):
    raw = normalize(key)
    out = {'valid': False, 'reason': '', 'tools': [], 'screens': 0}
    if len(raw) <= PAYLOAD_CHARS:
        out['reason'] = 'Schlüssel ist unvollständig'
        return out
    payload, sig_hex = raw[:PAYLOAD_CHARS], raw[PAYLOAD_CHARS:]
    bad = [c for c in payload if c not in ALPHABET]
    if bad:
        out['reason'] = 'Ungültige Zeichen in der Nutzlast: %s' % ' '.join(sorted(set(bad)))
        return out
    erwartet = _schluessel_laenge(public_key()['n']) * 2
    if len(sig_hex) != erwartet:
        out['reason'] = ('Schlüssel ist unvollständig (Signatur %d von %d Zeichen)'
                         % (len(sig_hex), erwartet))
        return out
    if not re.fullmatch(r'[0-9A-F]+', sig_hex):
        out['reason'] = 'Signatur ist keine Hex-Zahl (Schlüssel verändert?)'
        return out
    try:
        signatur = bytes.fromhex(sig_hex)
    except ValueError:
        out['reason'] = 'Signatur unlesbar'
        return out
    if not rsa_verify(_message(payload, hwid), signatur):
        value = _decode(payload)
        hinweis = (value >> 4) & 0x3FF if value is not None else None
        if hinweis is not None and hinweis != hardware_short(hwid):
            out['reason'] = 'Lizenz gehört zu einem anderen Gerät'
        else:
            out['reason'] = 'Signatur stimmt nicht (Lizenz verändert oder fremd)'
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


def verify(key, hwid=None):
    """Lizenz prüfen (mit Zwischenspeicher — die Prüfung läuft je Anfrage).

    Rückgabe: ``{'valid': bool, 'reason': str, 'tools': [...], 'screens': int}``
    """
    return _pruefe(normalize(key), hardware_id(hwid), public_key()['n'])


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
    ordner = os.path.dirname(path)
    if ordner:
        os.makedirs(ordner, exist_ok=True)
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
    arg_key_file = _arg('key-file') or None

    if '--info' in sys.argv:
        schluessel = private_key(arg_key_file)
        print('Geräte-ID:    %s' % hardware_id())
        print('Kurzkennung:  %d' % hardware_short(arg_hwid))
        print('Lizenzdatei:  %s' % LICENSE_FILE)
        print('Öffentlich:   RSA-%d' % public_key()['n'].bit_length())
        print('Signierschlüssel: %s' % (
            schluessel['quelle'] if schluessel else
            'nicht vorhanden (%s) – Lizenzen können hier nicht erzeugt werden'
            % PRIVATE_KEY_FILE))
        return 0

    if '--make-key' in sys.argv or '--install' in sys.argv:
        try:
            key = make_key(arg_tools, arg_screens, hwid=arg_hwid)
        except SignaturschluesselFehlt as exc:
            print('Fehler: %s' % exc, file=sys.stderr)
            return 3
        except ValueError as exc:
            print('Fehler: %s' % exc, file=sys.stderr)
            return 2
        if '--make-key' in sys.argv:
            print(key)
            return 0
        path = write_license(key)
        info = verify(key, hwid=arg_hwid)
        print('Lizenz geschrieben: %s' % path)
        print('  Tools:       %s' % ', '.join(info['tools']))
        print('  Bildschirme: %d' % info['screens'])
        return 0

    if '--check' in sys.argv:
        info = current(hwid=arg_hwid)
        if info is None:
            print('Keine Lizenz hinterlegt (%s)' % LICENSE_FILE)
            return 1
        if info['valid']:
            print('Lizenz gültig für dieses Gerät')
            print('  Tools:       %s' % ', '.join(info['tools']))
            print('  Bildschirme: %d' % info['screens'])
            return 0
        print('Lizenz ungültig: %s' % info['reason'])
        return 1

    print(__doc__)
    return 0


if __name__ == '__main__':
    sys.exit(main())
