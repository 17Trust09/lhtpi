"""Prüft: Mauszeiger-Verhalten ist in allen Tools identisch.

Aufruf:  ./venv/bin/python test_cursor_unified.py

Regel (Tim): Cursor wird bei Inaktivität ausgeblendet und kommt bei Bewegung
sofort wieder. Das darf NICHT auf OS-Ebene (transparentes Cursor-Thema,
`unclutter -idle 0`, Chromium-Extension) passieren — sonst kann er nicht
wiederkommen. Ein Snippet in jeder Kiosk-Seite macht es; diese Datei hält die
drei Fassungen zusammen.
"""
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))

REFERENCE = os.path.join(BASE, 'tools', 'kiosk-cursor.js')
TARGETS = [
    os.path.join(BASE, 'templates', 'kiosk.html'),                       # Folien
    os.path.join(BASE, 'terminboard', 'templates', 'board.html'),        # Termine
    os.path.join(BASE, 'tools', 'safety-cross', 'templates', 'base.html'),  # Safety Cross
]
INSTALL = os.path.join(BASE, 'install.sh')

checks = []


def ok(cond, msg):
    checks.append((bool(cond), msg))
    assert cond, 'FEHLER: ' + msg


def snippet_of(text):
    """Den Snippet-Block ab dem Marker aus einer Datei holen."""
    marker = text.find('Kiosk-Mauszeiger')
    assert marker >= 0, 'Marker-Kommentar fehlt'
    start = text.index('(function () {', marker)
    end = text.index('})();', start) + len('})();')
    return text[start:end]


def norm(text):
    return ' '.join(text.split())


ok(os.path.exists(REFERENCE), 'Referenz-Datei tools/kiosk-cursor.js vorhanden')
reference = snippet_of(open(REFERENCE).read())
ok('mousemove' in reference, 'Referenz: Mausbewegung schaltet den Zeiger ein')
ok('setTimeout(hide' in reference, 'Referenz: Inaktivität schaltet ihn wieder aus')

for path in TARGETS:
    rel = os.path.relpath(path, BASE)
    ok(os.path.exists(path), rel + ' vorhanden')
    text = open(path).read()
    ok('Kiosk-Mauszeiger' in text, rel + ': Snippet eingebunden')
    ok(norm(snippet_of(text)) == norm(reference),
       rel + ': Snippet ist identisch mit der Referenz')
    ok("'mousemove'" in snippet_of(text), rel + ': reagiert auf Mausbewegung')

# ── Dauerhaftes Ausblenden darf es nicht mehr geben ──────────────────────────
install = open(INSTALL).read()
ok(not re.search(r'^\s*unclutter\b', install, re.M),
   'install.sh startet unclutter nicht mehr (blendet den Zeiger dauerhaft aus)')
ok('hidecursor' not in install, 'install.sh installiert keine Cursor-Hide-Extension mehr')
ok('Transparent/cursors' not in install, 'install.sh legt kein transparentes Cursor-Thema mehr an')
ok('XCURSOR_THEME=Transparent' not in install, 'install.sh setzt kein transparentes Cursor-Thema mehr')

kiosk = open(os.path.join(BASE, 'templates', 'kiosk.html')).read()
ok('body{cursor:url(' not in kiosk, 'Folien: kein dauerhaft unsichtbarer Cursor im CSS')
ok('cursor:none!important' not in re.sub(r"textContent = '[^']*'", '', kiosk),
   'Folien: statisches CSS blendet den Cursor nicht mehr dauerhaft aus')
ok("'mousemove', block" not in kiosk, 'Folien: Mausbewegung wird nicht mehr blockiert')

board = open(os.path.join(BASE, 'terminboard', 'templates', 'board.html')).read()
ok('*{margin:0;padding:0;box-sizing:border-box}' in board,
   'Termine: keine pauschale Cursor-Regel mehr im Kopf-CSS')

sc = open(os.path.join(BASE, 'tools', 'safety-cross', 'templates', 'base.html')).read()
ok('<body>' in sc and 'class="hide-cursor"' not in sc,
   'Safety Cross: keine Vorab-Ausblendung mehr am body')
ok('HIDE_MS = 30000' not in sc, 'Safety Cross: alte 30-Sekunden-Logik ersetzt')

print('OK – %d Prüfungen bestanden' % len(checks))
for passed, msg in checks:
    print('  ✓', msg)
