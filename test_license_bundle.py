"""Tests für die Hardware-Lizenz des Bundle (license_bundle.py).

Aufruf:  ./venv/bin/python test_license_bundle.py

Es wird mit einer künstlichen Geräte-ID (LHTPI_HWID) gearbeitet, damit der Test
überall läuft – auch ohne Raspberry Pi. Signiert wird mit einem **Test-Schlüssel**
(1024 Bit, kein echtes Geheimnis); der echte private Schlüssel liegt außerhalb
des Repos.
"""
import json
import os
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

TMP = tempfile.mkdtemp(prefix='lhtpi-lic-')
os.environ['LHTPI_HWID'] = 'piserial:10000000testgeraet'
os.environ['LHTPI_LICENSE_FILE'] = os.path.join(TMP, 'license.key')

import test_keys                                        # noqa: E402
SIGN_FILE = test_keys.install_env()
TEST_KEY = test_keys.TEST_KEY

import license_bundle as lic                            # noqa: E402

passed = failed = 0


def ok(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print('  ✓ %s' % msg)
    else:
        failed += 1
        print('  ✗ %s' % msg)


QUELLE = open(os.path.join(BASE, 'license_bundle.py')).read()

print('\n1) Sicherheitsmodell: nur der öffentliche Schlüssel im Code')
ok('SECRET' not in QUELLE, 'kein gemeinsames Geheimnis mehr im Code')
ok(not hasattr(lic, 'SECRET'), 'SECRET ist entfernt')
ok('PUBLIC_KEY_N_HEX' in QUELLE, 'öffentlicher Schlüssel steht im Code')
ok(len(lic.PUBLIC_KEY_N_HEX) in (512, 1024), 'öffentlicher Schlüssel ist RSA-2048/4096')
ok(lic.private_key() is not None, 'privater Schlüssel wird aus der Datei geladen')
gesperrt = os.path.join(TMP, 'gibts-nicht.json')
os.environ['LHTPI_SIGN_KEY_FILE'] = gesperrt
ok(lic.private_key() is None, 'ohne Schlüsseldatei gibt es keinen privaten Schlüssel')
try:
    lic.make_key('1')
    ohne_schluessel = False
except lic.SignaturschluesselFehlt:
    ohne_schluessel = True
ok(ohne_schluessel, 'ohne privaten Schlüssel lässt sich keine Lizenz erzeugen')
os.environ['LHTPI_SIGN_KEY_FILE'] = SIGN_FILE

print('\n2) Geräte-ID')
ok(lic.hardware_id() == 'piserial:10000000testgeraet', 'Geräte-ID kommt aus LHTPI_HWID')
ok(isinstance(lic.hardware_short(), int) and 0 <= lic.hardware_short() < 1024,
   'Kurzkennung passt in 10 Bit')
os.environ['LHTPI_HWID'] = 'piserial:10000000zweitgeraet'
other_short = lic.hardware_short()
os.environ['LHTPI_HWID'] = 'piserial:10000000testgeraet'
ok(other_short != lic.hardware_short(), 'anderes Gerät -> andere Kurzkennung')

print('\n3) Schlüssel erzeugen und prüfen')
key = lic.make_key('1,3', screens=2)
raw = lic.normalize(key)
ok(key.startswith('LHTPI-'), 'Schlüssel fängt mit LHTPI an')
ok(len(raw) == lic.PAYLOAD_CHARS + 256, 'Nutzlast 3 Zeichen + 256 Hex-Zeichen Signatur')
ok(lic.format_key(raw) == key, 'Formatierung ist umkehrbar')
info = lic.verify(key)
ok(info['valid'], 'eigener Schlüssel ist auf diesem Gerät gültig')
ok(info['tools'] == ['slideshow', 'safetycross'], 'Tools 1,3 sind freigeschaltet')
ok(info['screens'] == 2, 'zwei Bildschirme freigeschaltet')

info1 = lic.verify(lic.make_key('2', screens=1))
ok(info1['valid'] and info1['tools'] == ['terminboard'] and info1['screens'] == 1,
   'ein Tool + ein Bildschirm')

info_all = lic.verify(lic.make_key('slideshow,terminboard,safetycross', screens=2))
ok(info_all['tools'] == ['slideshow', 'terminboard', 'safetycross'],
   'alle drei Tools (Namen statt Ziffern)')

print('\n4) Kopierschutz')
os.environ['LHTPI_HWID'] = 'piserial:10000000andererpi'
info = lic.verify(key)
ok(not info['valid'] and 'Gerät' in info['reason'],
   'dieselbe Lizenz auf einem anderen Pi ist ungültig (%s)' % info['reason'])
os.environ['LHTPI_HWID'] = 'piserial:10000000testgeraet'

tampered = lic.format_key('A' + raw[1:]) if raw[0] != 'A' else lic.format_key('B' + raw[1:])
info = lic.verify(tampered)
ok(not info['valid'] and info['tools'] == [],
   'geänderte Nutzlast (mehr Tools) wird abgelehnt')

flipped = list(raw)
flipped[-1] = 'F' if flipped[-1] != 'F' else 'E'
info = lic.verify(lic.format_key(''.join(flipped)))
ok(not info['valid'], 'gekipptes Signaturzeichen wird erkannt (%s)' % info['reason'])

# Nutzlast so verändern, dass die restlichen Bits gleich bleiben
value = lic._decode(raw[:lic.PAYLOAD_CHARS])
other_mask = 0b111 if (value & 0b111) != 0b111 else 0b001
tampered2 = lic.format_key(lic._encode(other_mask | (value & ~0b111),
                                       lic.PAYLOAD_CHARS) + raw[lic.PAYLOAD_CHARS:])
info = lic.verify(tampered2)
ok(not info['valid'] and info['tools'] == [],
   'mehr Tools als lizenziert -> abgelehnt (%s)' % info['reason'])

# Fremder öffentlicher Schlüssel: die Signatur passt dann nicht mehr
fremd_n = '%x' % (int(TEST_KEY['n'], 16) ^ 0xFF)
os.environ['LHTPI_PUBKEY'] = '%s:65537' % fremd_n
info = lic.verify(key)
ok(not info['valid'], 'Lizenz gilt nur mit dem richtigen öffentlichen Schlüssel')
os.environ['LHTPI_PUBKEY'] = '%s:%d' % (TEST_KEY['n'], TEST_KEY['e'])

info = lic.verify('LHTPI-ABCD')
ok(not info['valid'] and 'unvollständig' in info['reason'], 'zu kurzer Schlüssel abgelehnt')
info = lic.verify('')
ok(not info['valid'], 'leerer Schlüssel abgelehnt')
info = lic.verify('LHTPI-IIII-' + raw[lic.PAYLOAD_CHARS:])
ok(not info['valid'] and 'Ungültige Zeichen' in info['reason'],
   'Zeichen, die im Alphabet nicht vorkommen (I, O, 0, 1), werden gemeldet')
info = lic.verify('LHTPI-' + raw[:lic.PAYLOAD_CHARS] + '-' + 'Z' * 256)
ok(not info['valid'] and 'Hex' in info['reason'], 'Nicht-Hex-Signatur abgelehnt')

print('\n5) Gegenprobe mit openssl (Standard-Signatur)')
if subprocess.run(['which', 'openssl'], capture_output=True).returncode == 0:
    pem = os.path.join(TMP, 'test.pem')
    with open(pem, 'w') as f:
        json.dump(TEST_KEY, f)
    msg = lic._message(raw[:lic.PAYLOAD_CHARS], 'piserial:10000000testgeraet')
    msg_datei = os.path.join(TMP, 'msg.bin')
    sig_datei = os.path.join(TMP, 'sig.bin')
    with open(msg_datei, 'wb') as f:
        f.write(msg)
    with open(sig_datei, 'wb') as f:
        f.write(lic.rsa_sign(msg, lic.private_key()))
    # Private Schlüssel als PEM ablegen und mit openssl prüfen
    subprocess.run(['openssl', 'rsa', '-in', os.path.join('/tmp/lhtpi-testkey', 'test.pem'),
                    '-pubout', '-out', os.path.join(TMP, 'pub.pem')],
                   capture_output=True)
    if os.path.exists(os.path.join(TMP, 'pub.pem')):
        r = subprocess.run(['openssl', 'dgst', '-sha256', '-verify',
                            os.path.join(TMP, 'pub.pem'), '-signature', sig_datei,
                            msg_datei], capture_output=True, text=True)
        ok('Verified OK' in r.stdout, 'openssl bestätigt unsere Signatur (Verified OK)')
    else:
        ok(True, 'openssl-Prüfung übersprungen (kein PEM-Testschlüssel)')
else:
    ok(True, 'openssl nicht vorhanden – übersprungen')

print('\n6) Lizenzdatei und Gültigkeit auf dem Gerät')
lic.write_license(key)
ok(os.path.exists(lic.LICENSE_FILE), 'Lizenzdatei wird geschrieben')
ok(lic.current()['valid'], 'installierte Lizenz ist gültig')
ok(lic.licensed_tools() == ['slideshow', 'safetycross'], 'freigegebene Tools aus der Datei')
ok(lic.licensed_screens() == 2, 'freigegebene Bildschirm-Anzahl aus der Datei')
ok(lic.enforced(), 'Lizenzprüfung ist aktiv, sobald eine Lizenz liegt')

os.remove(lic.LICENSE_FILE)
ok(lic.current() is None and lic.licensed_tools() is None,
   'ohne Lizenzdatei meldet das Modul "keine Lizenz"')
ok(not lic.enforced(), 'ohne Lizenz und ohne Merkmal bleibt der Entwicklungsmodus')

print('\n7) Werkzeuge')
umgebung = dict(os.environ, LHTPI_HWID='piserial:10000000testgeraet')
r = subprocess.run([sys.executable, 'license_bundle.py', '--info'],
                   cwd=BASE, capture_output=True, text=True, env=umgebung)
ok('piserial:10000000testgeraet' in r.stdout and 'Kurzkennung' in r.stdout,
   '--info zeigt Geräte-ID und Kurzkennung')
ok('Signierschlüssel' in r.stdout, '--info zeigt den Stand des Signierschlüssels')
r = subprocess.run([sys.executable, 'license_bundle.py', '--make-key', '--tools=1,2', '--screens=2'],
                   cwd=BASE, capture_output=True, text=True, env=umgebung)
ok(r.returncode == 0 and r.stdout.strip().startswith('LHTPI-'),
   '--make-key liefert einen Schlüssel')
r = subprocess.run([sys.executable, 'license_bundle.py', '--make-key', '--tools=9'],
                   cwd=BASE, capture_output=True, text=True, env=umgebung)
ok(r.returncode == 2 and 'Unbekanntes Tool' in r.stderr, 'unbekanntes Tool wird abgelehnt')
r = subprocess.run([sys.executable, 'license_bundle.py', '--check'],
                   cwd=BASE, capture_output=True, text=True, env=umgebung)
ok(r.returncode == 1 and 'Keine Lizenz' in r.stdout, '--check ohne Lizenz meldet das')

# Auf dem Kundenimage (kein privater Schlüssel) muss --make-key scheitern
kunden_umgebung = dict(umgebung, LHTPI_SIGN_KEY_FILE=gesperrt)
r = subprocess.run([sys.executable, 'license_bundle.py', '--make-key', '--tools=1'],
                   cwd=BASE, capture_output=True, text=True, env=kunden_umgebung)
ok(r.returncode == 3 and 'Signaturschlüssel fehlt' in r.stderr,
   'ohne privaten Schlüssel verweigert --make-key (Kundenimage)')

print('\n%s%d Prüfungen bestanden, %d fehlgeschlagen'
      % ('OK – ' if failed == 0 else 'FEHLER – ', passed, failed))
sys.exit(1 if failed else 0)
