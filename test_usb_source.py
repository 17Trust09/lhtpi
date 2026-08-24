import os, tempfile, sys
sys.path.insert(0, '/opt/data/projects/lhtpi')

# ── 1. Reine USB-Funktionen ────────────────────────────────────────────
import usb_source

tmp = tempfile.mkdtemp(prefix='lhtpi-test-')
slides = os.path.join(tmp, 'slides')
os.makedirs(slides)
open(os.path.join(slides, 'b.jpg'), 'w').write('B')
open(os.path.join(slides, 'a.png'), 'w').write('A')
open(os.path.join(slides, 'v.mp4'), 'w').write('V')
open(os.path.join(slides, 'notes.txt'), 'w').write('ignore me')
open(os.path.join(slides, 'settings.txt'), 'w').write('default=7\na.png=3\n')

files = usb_source.list_usb_files(slides)
assert files == ['a.png', 'b.jpg', 'v.mp4'], files

settings = usb_source.read_usb_settings(slides)
assert settings == {'default': 7, 'a.png': 3}, settings

items = usb_source.usb_items(slides, lambda fn: '/present/usb-file/' + fn)
assert len(items) == 3
by = {i['filename']: i for i in items}
assert by['a.png']['display_duration'] == 3
assert by['b.jpg']['display_duration'] == 7
assert by['v.mp4']['display_duration'] == 0
assert by['v.mp4']['file_type'] == 'video'
assert by['a.png']['file_type'] == 'image'
print('[OK] USB-Funktionen (Sortierung, settings.txt, Dauer)')

# ── 2. Flask-App + Status (ohne USB) ───────────────────────────────────
from app import app
app.config['TESTING'] = True
client = app.test_client()

r = client.get('/present/api/status')
d = r.get_json()
for k in ('source', 'mode', 'manual_source', 'usb_present', 'active'):
    assert k in d, k
assert d['mode'] == 'auto' and d['source'] == 'web', d
print('[OK] Status default (auto, web, kein USB):', d['source'], d['mode'], d['usb_present'])

# ── 3. Login + Settings-Endpoint ───────────────────────────────────────
r = client.post('/login', data={'username': 'admin', 'password': 'admin'})
assert r.status_code in (302, 200), r.status_code
r = client.get('/settings/source')
assert r.get_json() == {'mode': 'auto', 'manual_source': 'web'}, r.get_json()
print('[OK] Login + GET /settings/source')

# ── 4. USB vorhanden (monkeypatch) ─────────────────────────────────────
import routes
orig = routes.find_usb_slides_dir
routes.find_usb_slides_dir = lambda: slides
r = client.get('/present/api/status')
d = r.get_json()
assert d['source'] == 'usb' and d['active'] is True, d
assert d['usb_present'] is True and d['playlist_name'] == 'USB-Stick'
assert len(d['items']) == 3
print('[OK] Status mit USB:', d['playlist_name'], len(d['items']), 'Items')

# ── 5. USB-Datei-Auslieferung ──────────────────────────────────────────
r = client.get('/present/usb-file/a.png')
assert r.status_code == 200 and r.data == b'A', (r.status_code, r.data)
print('[OK] USB-Datei-Auslieferung /present/usb-file/a.png')

# ── 6. Manuell + Web (USB ignoriert) ───────────────────────────────────
client.post('/settings/source', data={'mode': 'manual', 'manual_source': 'web'})
routes.find_usb_slides_dir = lambda: slides  # Stick weiterhin "da"
r = client.get('/present/api/status')
d = r.get_json()
assert d['mode'] == 'manual' and d['source'] == 'web', d
print('[OK] Manuell Web hat Vorrang trotz USB')

# ── 7. Manuell + USB, aber kein Stick ──────────────────────────────────
routes.find_usb_slides_dir = lambda: None
client.post('/settings/source', data={'mode': 'manual', 'manual_source': 'usb'})
r = client.get('/present/api/status')
d = r.get_json()
assert d['active'] is False and d['status'] == 'Kein USB-Stick erkannt', d
print('[OK] Manuell USB ohne Stick -> "Kein USB-Stick erkannt"')

# ── 8. Leerer slides-Ordner ────────────────────────────────────────────
empty = os.path.join(tmp, 'empty')
os.makedirs(os.path.join(empty, 'slides'))
routes.find_usb_slides_dir = lambda: os.path.join(empty, 'slides')
client.post('/settings/source', data={'mode': 'auto', 'manual_source': 'web'})
r = client.get('/present/api/status')
d = r.get_json()
assert d['active'] is False and 'leer' in d['status'], d
print('[OK] Leerer slides-Ordner ->', d['status'])

routes.find_usb_slides_dir = orig
print('\nALLES GRÜN ✅')
