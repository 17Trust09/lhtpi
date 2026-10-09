"""Tests für die Hardware-Lizenz des Bundle (license_bundle.py).

Aufruf:  ./venv/bin/python test_license_bundle.py

Es wird mit einer künstlichen Geräte-ID (LHTPI_HWID) gearbeitet, damit der Test
überall läuft – auch ohne Raspberry Pi.
"""
import os
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

os.environ['LHTPI_HWID'] = 'piserial:10000000testgeraet'
os.environ['LHTPI_LICENSE_FILE'] = os.path.join(tempfile.mkdtemp(prefix='lhtpi-lic-'),
                                                'license.key')

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


print('\n1) Geräte-ID')
ok(lic.hardware_id() == 'piserial:10000000testgeraet', 'Geräte-ID kommt aus LHTPI_HWID')
ok(isinstance(lic.hardware_short(), int) and 0 <= lic.hardware_short() < 1024,
   'Kurzkennung passt in 10 Bit')
os.environ['LHTPI_HWID'] = 'piserial:10000000zweitgeraet'
other_short = lic.hardware_short()
os.environ['LHTPI_HWID'] = 'piserial:10000000testgeraet'
ok(other_short != lic.hardware_short(), 'anderes Gerät -> andere Kurzkennung')

print('\n2) Schlüssel erzeugen und prüfen')
key = lic.make_key('1,3', screens=2)
ok(lic.format_key(lic.normalize(key)) == key, 'Schlüssel hat das Format LHTPI-XXXX-XXXX-XXXX-XXXX')
ok(len(lic.normalize(key)) == 16, '16 Zeichen Nutzlast+Signatur')
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

print('\n3) Kopierschutz')
os.environ['LHTPI_HWID'] = 'piserial:10000000andererpi'
info = lic.verify(key)
ok(not info['valid'] and 'Gerät' in info['reason'],
   'dieselbe Lizenz auf einem anderen Pi ist ungültig (%s)' % info['reason'])
os.environ['LHTPI_HWID'] = 'piserial:10000000testgeraet'

raw = lic.normalize(key)
tampered = lic.format_key('A' + raw[1:]) if raw[0] != 'A' else lic.format_key('B' + raw[1:])
info = lic.verify(tampered)
ok(not info['valid'] and info['tools'] == [],
   'geänderte Nutzlast (mehr Tools) wird abgelehnt')

flipped = list(raw)
flipped[15] = 'Z' if flipped[15] != 'Z' else 'Y'
info = lic.verify(lic.format_key(''.join(flipped)))
ok(not info['valid'], 'gekippte Signatur wird erkannt (%s)' % info['reason'])

# Nutzlast so verändern, dass die restlichen Bits gleich bleiben:
# ein anderes Tool einschalten -> Signatur muss brechen.
parts = lic.normalize(key)
value = lic._decode(parts[:3])
other_mask = 0b111 if (value & 0b111) != 0b111 else 0b001
tampered2 = lic.format_key(lic._encode(other_mask | (value & ~0b111), 3) + parts[3:])
info = lic.verify(tampered2)
ok(not info['valid'] and info['tools'] == [],
   'mehr Tools als lizenziert -> abgelehnt (%s)' % info['reason'])

info = lic.verify('LHTPI-ABCD')
ok(not info['valid'] and 'Länge' in info['reason'], 'zu kurzer Schlüssel abgelehnt')
info = lic.verify('')
ok(not info['valid'], 'leerer Schlüssel abgelehnt')
info = lic.verify('LHTPI-IIII-OOOO-1111-0000')
ok(not info['valid'] and 'Ungültige Zeichen' in info['reason'],
   'Zeichen, die im Alphabet nicht vorkommen (I, O, 0, 1), werden gemeldet')

print('\n4) Lizenzdatei und Gültigkeit auf dem Gerät')
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

print('\n5) Werkzeuge')
r = subprocess.run([sys.executable, 'license_bundle.py', '--info'],
                   cwd=BASE, capture_output=True, text=True,
                   env=dict(os.environ, LHTPI_HWID='piserial:10000000testgeraet'))
ok('piserial:10000000testgeraet' in r.stdout and 'Kurzkennung' in r.stdout,
   '--info zeigt Geräte-ID und Kurzkennung')
r = subprocess.run([sys.executable, 'license_bundle.py', '--make-key', '--tools=1,2', '--screens=2'],
                   cwd=BASE, capture_output=True, text=True)
ok(r.returncode == 0 and r.stdout.strip().startswith('LHTPI-'),
   '--make-key liefert einen Schlüssel')
r = subprocess.run([sys.executable, 'license_bundle.py', '--make-key', '--tools=9'],
                   cwd=BASE, capture_output=True, text=True)
ok(r.returncode == 2 and 'Unbekanntes Tool' in r.stderr, 'unbekanntes Tool wird abgelehnt')
r = subprocess.run([sys.executable, 'license_bundle.py', '--check'],
                   cwd=BASE, capture_output=True, text=True)
ok(r.returncode == 1 and 'Keine Lizenz' in r.stdout, '--check ohne Lizenz meldet das')

print('\n%s%d Prüfungen bestanden, %d fehlgeschlagen'
      % ('OK – ' if failed == 0 else 'FEHLER – ', passed, failed))
sys.exit(1 if failed else 0)


# ── Sichtprüfung (nur informativ) ────────────────────────────────────────────
