"""Tests für den Multitool-Kiosk (Anzeige-Router + Admin-Seite „Anzeigen").

Aufruf:   ./venv/bin/python test_kiosk_router.py

Nutzt eine temporäre SQLite-DB (LHTPI_DB) — die echte lhtpi.db bleibt unberührt.
TCP-Probes werden abgeschaltet (LHTPI_KIOSK_PROBE=0), damit der Test ohne die
laufenden Tool-Dienste deterministisch ist.
"""
import os
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

TMP = tempfile.mkdtemp(prefix='lhtpi-kiosk-test-')
os.environ['LHTPI_DB'] = os.path.join(TMP, 'test.db')
os.environ['LHTPI_KIOSK_PROBE'] = '0'
os.environ['LHTPI_TOOLS'] = 'slideshow,terminboard,safetycross'

from app import app                        # noqa: E402
import kiosk_router as router              # noqa: E402

ALL_TOOLS = 'slideshow,terminboard,safetycross'
checks = []


def ok(cond, msg):
    checks.append((bool(cond), msg))
    assert cond, 'FEHLER: ' + msg


client = app.test_client()

# ── 1. Werkseinstellung: 1 Bildschirm, Folien fest ───────────────────────────
with app.app_context():
    router.ensure_defaults()
    ok(router.screen_count() == 1, 'Standard = 1 Bildschirm')
cfg = client.get('/api/screen/1').get_json()
ok(cfg['mode'] == 'fixed', 'Bildschirm 1 startet als festes Tool')
ok([t['tool'] for t in cfg['tools']] == ['slideshow'], 'Standard-Tool ist die Slideshow')
ok(cfg['tools'][0]['dwell'] == 60, 'Standard-Anzeigedauer 60 s')
ok(cfg['cursor_idle'] == 3, 'Cursor-Idle standardmäßig 3 s')

# ── 2. Router-Seite: ohne Login erreichbar, mit Cursor- und Rotationslogik ───
r = client.get('/screen/1')
ok(r.status_code == 200, '/screen/1 ohne Login erreichbar')
html = r.data.decode()
ok('present/kiosk' in html, 'Tool-URL steht im Router-HTML')
ok('cursor:none!important' in html, 'Cursor-Ausblenden ist eingebaut')
ok("'mousemove'" in html, 'Mausbewegung blendet den Cursor wieder ein')
ok('screen' in html and 'iframe' in html.lower(), 'Router arbeitet mit iframes')

# ── 3. Zweiter Bildschirm: aktivieren und prüfen ─────────────────────────────
client.post('/login', data={'username': 'admin', 'password': 'admin'},
            follow_redirects=True)
with app.app_context():
    router.set_screen_count(2)
    router.ensure_defaults()
cfg2 = client.get('/api/screen/2').get_json()
ok(cfg2['mode'] == 'fixed', 'Bildschirm 2 startet als festes Tool')
ok([t['tool'] for t in cfg2['tools']] == ['terminboard'], 'Bildschirm 2 zeigt Termine')
ok(len(client.get('/api/screens').get_json()['screens']) == 2, 'zwei Bildschirme aktiv')

# ── 4. Speichern über die Admin-Seite: Rotation mit eigenen Dauern ───────────
#     Beispiel Tim: Projekt 1 für 5 min, Projekt 2 für 2 min
resp = client.post('/display/save', data={
    'screen_count': '2',
    'cursor_idle': '5',
    'reload_minutes': '15',
    'screen_1_present': '1', 'screen_1_active': '1',
    'name_1': 'Eingang', 'hdmi_1': 'HDMI-1',
    'tool_1_slideshow_present': '1', 'tool_1_slideshow_active': '1',
    'tool_1_slideshow_dwell': '300', 'tool_1_slideshow_sort': '0',
    'tool_1_safetycross_present': '1', 'tool_1_safetycross_active': '1',
    'tool_1_safetycross_dwell': '120', 'tool_1_safetycross_sort': '1',
    'tool_1_terminboard_present': '1', 'tool_1_terminboard_dwell': '30',
    'screen_2_present': '1', 'screen_2_active': '1',
    'name_2': 'Werkstatt', 'hdmi_2': 'HDMI-2',
    'tool_2_terminboard_present': '2', 'tool_2_terminboard_active': '1',
    'tool_2_terminboard_dwell': '30', 'tool_2_terminboard_sort': '0',
}, follow_redirects=True)
ok(resp.status_code == 200, 'Speichern liefert Seite zurück')

cfg = client.get('/api/screen/1').get_json()
ok(cfg['mode'] == 'rotate', 'Bildschirm 1 rotiert bei zwei Tools')
ok(cfg['name'] == 'Eingang', 'Bildschirmname gespeichert')
ok([t['tool'] for t in cfg['tools']] == ['slideshow', 'safetycross'],
   'Reihenfolge nach Sortierwert')
ok([t['dwell'] for t in cfg['tools']] == [300, 120],
   'Anzeigedauern wie gewünscht: 5 min und 2 min')
ok(all('cursor_idle=5' in t['url'] for t in cfg['tools']),
   'Cursor-Zeit wird an die eingebetteten Tools mitgegeben')
ok(cfg['cursor_idle'] == 5, 'Cursor-Idle gespeichert')
ok(cfg['reload_minutes'] == 15, 'Reload-Zeit gespeichert')

# ── 5. Tool abwählen -> fest; alle abwählen -> leer ──────────────────────────
client.post('/display/save', data={
    'screen_count': '1', 'cursor_idle': '3', 'reload_minutes': '30',
    'screen_1_present': '1', 'screen_1_active': '1', 'name_1': 'Eingang', 'hdmi_1': 'HDMI-1',
    'tool_1_slideshow_present': '1', 'tool_1_slideshow_active': '1',
    'tool_1_slideshow_dwell': '20', 'tool_1_slideshow_sort': '0',
    'tool_1_safetycross_present': '1', 'tool_1_safetycross_dwell': '15',
}, follow_redirects=True)
cfg = client.get('/api/screen/1').get_json()
ok(cfg['mode'] == 'fixed', 'ein verbleibendes Tool = fest')
ok(client.get('/api/screens').get_json()['count'] == 1, 'zurück auf 1 Bildschirm')
ok(client.get('/api/screen/2').status_code == 404, 'abgeschalteter Bildschirm liefert 404')

# ── 6. Nicht installierte Tools werden nie ausgeliefert ──────────────────────
with app.app_context():
    router.save_screen(1, entries=[
        {'tool': 'slideshow', 'enabled': True, 'dwell': 20, 'sort': 0},
        {'tool': 'terminboard', 'enabled': True, 'dwell': 20, 'sort': 1},
    ])
    os.environ['LHTPI_TOOLS'] = 'slideshow'          # Termine/Safety nicht installiert
    cfg = router.screen_config(1, with_probe=False)
    ok([t['tool'] for t in cfg['tools']] == ['slideshow'],
       'nicht installierte Tools fehlen in der Anzeige')
    os.environ['LHTPI_TOOLS'] = ALL_TOOLS

# ── 7. Unbekannte Tools und Unsinn werden verworfen ──────────────────────────
with app.app_context():
    router.save_screen(1, entries=[
        {'tool': 'quatsch', 'enabled': True},
        {'tool': 'slideshow', 'enabled': True, 'dwell': 'abc', 'sort': 'x'},
    ])
    cfg = router.screen_config(1, with_probe=False)
    ok([t['tool'] for t in cfg['tools']] == ['slideshow'], 'unbekanntes Tool verworfen')
    ok(cfg['tools'][0]['dwell'] == 60, 'ungültige Dauer fällt auf Standard zurück')
    ok(cfg['mode'] == 'fixed', 'ungültige Eingaben erzeugen keine Rotation')

# ── 8. Admin-Seite nur mit Login ─────────────────────────────────────────────
anon = app.test_client()
ok(anon.get('/display').status_code == 302, '/display verlangt Login')
page = client.get('/display')
ok(page.status_code == 200 and 'Anzeigen' in page.data.decode(), '/display lädt mit Login')
ok('Anzeigedauer' in page.data.decode() or 'Dauer' in page.data.decode(),
   'Einstellfeld für die Anzeigedauer ist vorhanden')

print('OK – %d Prüfungen bestanden' % len(checks))
for passed, msg in checks:
    print('  ✓', msg)
