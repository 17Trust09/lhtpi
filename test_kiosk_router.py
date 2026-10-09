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
# Lizenz: künstliches Gerät, Lizenzen im Testordner, keine Zwangssperre
os.environ['LHTPI_HWID'] = 'piserial:10000000testgeraet'
os.environ['LHTPI_LICENSE_FILE'] = os.path.join(TMP, 'license.key')
os.environ['LHTPI_INSTALLED_MARKER'] = os.path.join(TMP, 'installed')
os.environ['LHTPI_LICENSE_ENFORCE'] = '0'

# Lizenzprüfung mit dem Test-Schlüssel (siehe test_keys.py)
import test_keys                                        # noqa: E402
test_keys.install_env()
os.environ['LHTPI_SCREENS_FILE'] = os.path.join(TMP, 'screens')

from app import app                        # noqa: E402
import kiosk_router as router              # noqa: E402
import kiosk_tools as tools                # noqa: E402

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

# ── 9. Vorbelegung aus der Installations-Auswahl ─────────────────────────────
#     Abteilung mit nur einem Tool: Bildschirm 1 zeigt das verfügbare Tool.
with app.app_context():
    os.environ['LHTPI_TOOLS'] = 'safetycross'
    ok(router.default_entries(1) == [('safetycross', None)],
       'nur Safety Cross installiert -> Bildschirm 1 zeigt Safety Cross')
    ok(router.default_entries(2) == [],
       'nur ein Tool installiert -> zweiter Bildschirm bleibt leer')
    os.environ['LHTPI_TOOLS'] = 'slideshow,safetycross'
    ok(router.default_entries(1) == [('slideshow', None)],
       'Folien installiert -> Bildschirm 1 bleibt bei den Folien')
    ok(router.default_entries(2) == [('safetycross', None)],
       'zweiter Bildschirm bekommt das übrige Tool')
    os.environ['LHTPI_TOOLS'] = ALL_TOOLS
    ok([t for t, _ in router.default_entries(1)] == ['slideshow'],
       'Werkseinstellung bleibt: Bildschirm 1 = Folien')
    ok([t for t, _ in router.default_entries(2)] == ['terminboard'],
       'Werkseinstellung bleibt: Bildschirm 2 = Termine')

# ── 10. Bildschirm-Anzahl kommt aus der Installation ─────────────────────────
with app.app_context():
    import kiosk_tools as tools_mod
    from models import db, Setting
    old = Setting.query.filter_by(key=router.SETTING_SCREEN_COUNT).first()
    if old is not None:
        db.session.delete(old)
        db.session.commit()
    ok(router.get_setting(router.SETTING_SCREEN_COUNT) is None,
       'keine Bildschirm-Einstellung in der Datenbank')
    os.environ['LHTPI_SCREEN_COUNT'] = '2'
    ok(router.screen_count() == 2,
       'Bildschirm-Anzahl aus der Installation (2) wird übernommen')
    os.environ.pop('LHTPI_SCREEN_COUNT')
    ok(router.screen_count() == 1, 'ohne Installer-Angabe bleibt es bei 1')
    # Die Datei entsteht durch Speichern in der Anzeigen-Seite – hier entfernen,
    # damit der Fall "Gerät ohne Eintrag" geprüft wird.
    if os.path.exists(tools_mod.SCREENS_FILE):
        os.remove(tools_mod.SCREENS_FILE)
    ok(tools_mod.configured_screen_count() is None,
       'ohne Datei/Umgebungsvariable meldet der Installer-Wert nichts')

# ── 11. Hardware-Lizenz begrenzt Tools, Bildschirme und sperrt die App ──────
with app.app_context():
    import license_bundle as lic
    from models import Setting, db as _db

    key = lic.make_key('1,3', screens=1)          # nur Folien + Safety Cross, 1 Schirm
    lic.write_license(key)
    ok(lic.verify(lic.read_license())['valid'], 'Lizenz für dieses Gerät gültig')
    ok(tools.installed_tools() == ['slideshow', 'safetycross'],
       'nur lizenzierte Tools zählen als installiert (Termine gesperrt)')

    alt = Setting.query.filter_by(key=router.SETTING_SCREEN_COUNT).first()
    if alt is not None:
        _db.session.delete(alt)
        _db.session.commit()
    os.environ['LHTPI_SCREEN_COUNT'] = '2'        # Gerät hat zwei Bildschirme
    ok(router.screen_count() == 1,
       'Installation will 2 Bildschirme, Lizenz erlaubt nur 1 -> 1')

    lic.write_license(lic.make_key('1,2,3', screens=2))
    ok(router.screen_count() == 2, 'Lizenz für 2 Bildschirme -> 2 erlaubt')
    os.environ.pop('LHTPI_SCREEN_COUNT')

    # Ungültige Lizenz + erzwungene Prüfung -> Sperrseite, /lizenz bleibt offen
    lic.write_license('LHTPI-QQQQ-QQQQ-QQQQ-QQQQ')
    os.environ['LHTPI_LICENSE_ENFORCE'] = '1'
    c = app.test_client()
    r = c.get('/screen/1')
    ok(r.status_code == 403 and 'nicht freigeschaltet' in r.data.decode(),
       'ungültige Lizenz -> Anzeige gesperrt')
    r = c.get('/lizenz')
    ok(r.status_code == 200 and lic.hardware_id() in r.data.decode(),
       'Lizenzseite bleibt erreichbar und zeigt die Geräte-ID')
    os.environ['LHTPI_LICENSE_ENFORCE'] = '0'
    os.remove(lic.LICENSE_FILE)
    ok(not lic.enforced() and tools.installed_tools() == ALL_TOOLS.split(','),
       'ohne Lizenz wieder Entwicklungsmodus mit allen Tools')

# ── 12. Leere Bildschirme werden nachbelegt (Lizenz kam erst später) ────────
with app.app_context():
    from models import KioskScreen, KioskScreenTool, Setting
    # Zustand "App startete ohne gültige Lizenz": Bildschirm ohne Belegung,
    # Belegung noch nie gespeichert.
    old = Setting.query.filter_by(key=router.SETTING_LAYOUT_TOUCHED).first()
    if old is not None:
        _db.session.delete(old)
        _db.session.commit()
    for st in KioskScreenTool.query.all():
        _db.session.delete(st)
    _db.session.commit()
    ok(not router.layout_touched(), 'Belegung wurde noch nie gespeichert')
    ok(router.ensure_defaults() is True, 'Nachbelegung greift bei leerem Bildschirm')
    cfg = client.get('/api/screen/1').get_json()
    ok([t['tool'] for t in cfg['tools']] == ['slideshow'],
       'leerer Bildschirm 1 bekommt die Werkseinstellung (Folien)')

    # Jetzt bewusst leer speichern (Admin) -> darf nicht wieder gefüllt werden
    router.save_screen(1, entries=[])
    ok(router.layout_touched(), 'Speichern markiert die Belegung als gesetzt')
    ok(router.ensure_defaults() is False, 'keine Nachbelegung mehr nach dem Speichern')
    cfg = client.get('/api/screen/1').get_json()
    ok(cfg['mode'] == 'empty' and cfg['tools'] == [],
       'bewusst leerer Bildschirm bleibt leer')

# ── 13. Ersteinrichtung: Merkmal, Bildschirm-Dateien, Abschluss-Route ───────
with app.app_context():
    screens_datei = tools.SCREENS_FILE
    marke2 = os.path.join(os.path.dirname(screens_datei), 'screen2')
    marker = os.environ['LHTPI_INSTALLED_MARKER']

    router.set_screen_count(2)
    ok(os.path.exists(screens_datei) and open(screens_datei).read().strip() == '2',
       'Bildschirm-Anzahl wird für die Anzeige hinterlegt (screens=2)')
    ok(os.path.exists(marke2), 'zweiter Bildschirm wird markiert (screen2)')
    router.set_screen_count(1)
    ok(not os.path.exists(marke2), 'bei einem Bildschirm verschwindet die Marke')

    # Vorgabe (noch nichts eingestellt): der kleinere Wert gewinnt – mit einem
    # Monitor darf kein zweiter Kiosk auf demselben Schirm aufgehen.
    import usb_source as _us
    alt_conf, alt_det = tools.configured_screen_count, tools.detected_screen_count
    tools.configured_screen_count = lambda: 2
    tools.detected_screen_count = lambda: 1
    _us.set_setting(router.SETTING_SCREEN_COUNT, '')
    ok(router.screen_count() == 1,
       'ein Monitor erkannt -> Vorgabe 1 Bildschirm (kein zweiter Kiosk)')
    tools.detected_screen_count = lambda: 2
    _us.set_setting(router.SETTING_SCREEN_COUNT, '')
    ok(router.screen_count() == 2, 'zwei Monitore erkannt -> Vorgabe 2 Bildschirme')
    tools.configured_screen_count, tools.detected_screen_count = alt_conf, alt_det
    router.set_screen_count(1)

    ok(not router.ist_eingerichtet(), 'vor der Einrichtung: Gerät gilt als nicht eingerichtet')

    anon = app.test_client()
    antwort = anon.post('/setup/abschluss')
    ok(antwort.status_code in (301, 302, 401, 403),
       'Einrichtung abschließen verlangt Anmeldung (%d)' % antwort.status_code)
    ok(not os.path.exists(marker), 'ohne Anmeldung wird nichts abgeschlossen')

    # Sicher anmelden – frühere Abschnitte können die Sitzung verändert haben
    client.post('/login', data={'username': 'admin', 'password': 'admin'})

    # Ohne Lizenz darf die Einrichtung nicht abschließen (sonst sperrt sich das
    # Gerät mit dem Merkmal selbst). Fall 1: echter Gerätezustand – keine Lizenz,
    # noch kein Merkmal -> Seite bleibt in der Einrichtung.
    os.environ.pop('LHTPI_LICENSE_ENFORCE')
    antwort = client.post('/setup/abschluss')
    ok(antwort.status_code == 302 and not os.path.exists(marker),
       'ohne Lizenz kein Abschluss (Gerät würde sich sonst selbst sperren)')
    # Fall 2: erzwungene Lizenzprüfung -> die App ist rundherum gesperrt
    os.environ['LHTPI_LICENSE_ENFORCE'] = '1'
    antwort = client.post('/setup/abschluss')
    ok(antwort.status_code == 403 and not os.path.exists(marker),
       'mit aktiver Lizenzprüfung ist die App gesperrt (403)')
    os.environ['LHTPI_LICENSE_ENFORCE'] = '0'

    antwort = client.post('/setup/abschluss')
    ok(antwort.status_code == 302, 'Einrichtung abschließen leitet zurück')
    ok(antwort.headers.get('Location', '').endswith('/display'),
       'nach dem Abschluss landet man wieder in den Einstellungen')
    ok(os.path.exists(marker), 'Merkmal gesetzt -> Anzeige startet automatisch')
    ok(router.ist_eingerichtet(), 'App weiß: Gerät ist eingerichtet')
    os.remove(marker)

    ok(tools.detected_screen_count() >= 1, 'Bildschirm-Erkennung liefert mindestens 1')

print('OK – %d Prüfungen bestanden' % len(checks))
for passed, msg in checks:
    print('  ✓', msg)
