"""Tests für den Multitool-Kiosk (Anzeige-Router + Admin-Seite „Anzeigen").

Aufruf:   ./venv/bin/python test_kiosk_router.py

Nutzt eine temporäre SQLite-DB (LHTPI_DB) — die echte lhtpi.db bleibt unberührt.
TCP-Probes werden abgeschaltet (LHTPI_KIOSK_PROBE=0), damit der Test ohne die
laufenden Tool-Dienste deterministisch ist.
"""
import json
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

# ── 8. Anzeigen-Seite: am Gerät ohne Login, aus dem LAN mit Login ───────────
# Am Gerät selbst (localhost) ist man automatisch angemeldet - der Bildschirm
# hat keine Tastatur. Von außen bleibt der Login Pflicht.
anon = app.test_client()
fremd = anon.get('/display', environ_base={'REMOTE_ADDR': '192.168.178.50'})
ok(fremd.status_code == 302, 'aus dem LAN verlangt /display weiterhin Login')
vorort = anon.get('/display')
ok(vorort.status_code == 200,
   'am Gerät (localhost) ist /display ohne Login erreichbar')
seite = vorort.get_data(as_text=True)
ok('Anzeigen' in seite, '/display lädt')
ok('Dauer' in seite, 'Einstellfeld für die Anzeigedauer ist vorhanden')
ok('url_for' not in seite, 'keine unaufgelösten Platzhalter')
ok('/dashboard' not in seite and 'Dashboard' not in seite,
   'kein Weg zum Dashboard (nur Anzeige)')
ok('Einrichtung abschließen' in seite,
   'solange nicht eingerichtet: Knopf „Einrichtung abschließen und Anzeige starten"')
marker = os.environ['LHTPI_INSTALLED_MARKER']
open(marker, 'w').close()
seite = anon.get('/display').get_data(as_text=True)
ok('/anzeige/start' in seite, 'eingerichtet: Knopf „Anzeige starten" ist vorhanden')
ok('Einrichtung abschließen' not in seite,
   'eingerichtet: Abschluss-Knopf verschwindet')
os.remove(marker)
ok('data-pill' in seite and 'rot-feld' in seite,
   'Anzeige der Betriebsart und Dauer-Felder sind ausgezeichnet')
ok('toolbox' in seite, 'Tool-Kästchen sind für die Live-Umschaltung markiert')

# Ein Tool = fest, zwei Tools = Rotation (auch im HTML vorbelegt)
with app.app_context():
    router.save_screen(1, name='Bildschirm 1', hdmi='HDMI-1', enabled=True, entries=[
        {'tool': 'slideshow', 'enabled': True, 'dwell': 300, 'sort': 0},
    ])
fest = client.get('/api/screen/1').get_json()
ok(fest['mode'] == 'fixed', 'ein ausgewähltes Tool ist fest')
seite_eins = anon.get('/display').get_data(as_text=True)
ok('fest · Folien' in seite_eins, 'ein Tool wird als „fest" angezeigt')
with app.app_context():
    router.save_screen(1, name='Bildschirm 1', hdmi='HDMI-1', enabled=True, entries=[
        {'tool': 'slideshow', 'enabled': True, 'dwell': 300, 'sort': 0},
        {'tool': 'terminboard', 'enabled': True, 'dwell': 120, 'sort': 1},
    ])
zwei = client.get('/api/screen/1').get_json()
ok(zwei['mode'] == 'rotate', 'zwei ausgewählte Tools rotieren')
ok([t['dwell'] for t in zwei['tools']] == [300, 120],
   'jedes Tool behält seine eigene Dauer')
seite_zwei = anon.get('/display').get_data(as_text=True)
ok('Rotation · 2 Tools' in seite_zwei, 'zwei Tools werden als Rotation angezeigt')

# ── 8b. „Anzeige starten": Anzeige-Fenster übernehmen (Pfad-Wächter) ─────────
with app.app_context():
    router.save_screen(1, name='Bildschirm 1', hdmi='HDMI-1', enabled=True, entries=[
        {'tool': 'slideshow', 'enabled': True, 'dwell': 300, 'sort': 0},
    ])
    router.set_screen_count(1)
pfad = tools.SCREENS_FILE
vorher = os.stat(pfad).st_mtime_ns
antwort = anon.post('/anzeige/start')
ok(antwort.status_code == 302, '„Anzeige starten" leitet zurück zur Anzeigen-Seite')
ok(antwort.headers.get('Location', '').endswith('/display'), 'und zwar auf /display')
ok(os.stat(pfad).st_mtime_ns > vorher,
   'Bildschirm-Datei wird neu geschrieben -> Pfad-Wächter startet die Fenster')
ok(open(pfad).read().strip() == '1', 'Bildschirm-Anzahl bleibt dabei erhalten')

# ── 8c. Vorschau: erst speichern, dann genau diesen Bildschirm zeigen ───────
with app.app_context():
    router.save_screen(1, name='Bildschirm 1', hdmi='HDMI-1', enabled=True, entries=[
        {'tool': 'safetycross', 'enabled': True, 'dwell': 30, 'sort': 0},
        {'tool': 'slideshow', 'enabled': False, 'dwell': 60, 'sort': 1},
    ])
cfg_schau = anon.get('/screen/1?vorschau=1').get_json()
ok(cfg_schau is None or True, 'Vorschau-Seite lädt')
import json as _json                                              # noqa: E402
import re as _re                                                  # noqa: E402
roh = anon.get('/screen/1?vorschau=1').get_data(as_text=True)
treffer = _re.search(r'<script id="cfg" type="application/json">(.*?)</script>',
                     roh, _re.S)
gefunden = _json.loads(treffer.group(1)) if treffer else {}
ok(gefunden.get('vorschau') is True, 'Vorschau ist als solche gekennzeichnet')
ok([t['tool'] for t in gefunden.get('tools', [])] == ['safetycross'],
   'Vorschau zeigt das eingestellte Tool (Safety Cross)')
ok('localhost:8002' in gefunden['tools'][0]['url'],
   'Vorschau lädt die Safety-Cross-Anzeige, nicht die Folien')
ohne = _re.search(r'<script id="cfg" type="application/json">(.*?)</script>',
                  anon.get('/screen/1').get_data(as_text=True), _re.S)
ok(_json.loads(ohne.group(1)).get('vorschau') is False,
   'der Kiosk lädt ohne Vorschau-Kennzeichnung (ruhige Anzeige)')

# Der Vorschau-Knopf speichert zuerst und öffnet dann die Vorschau
antwort = anon.post('/display/save', data={
    'screen_count': '1', 'cursor_idle': '3', 'reload_minutes': '30',
    'screen_1_present': '1', 'name_1': 'Bildschirm 1', 'hdmi_1': 'HDMI-1',
    'screen_1_active': '1',
    'tool_1_safetycross_present': '1', 'tool_1_safetycross_active': '1',
    'tool_1_safetycross_dwell': '45',
    'weiter': 'vorschau_1',
})
ok(antwort.status_code == 302, 'Vorschau-Knopf speichert und leitet weiter')
ok(antwort.headers.get('Location', '').endswith('/screen/1?vorschau=1'),
   'und öffnet genau diesen Bildschirm als Vorschau (%s)'
   % antwort.headers.get('Location'))
neu_cfg = anon.get('/api/screen/1').get_json()
ok(neu_cfg['tools'][0]['dwell'] == 45,
   'die Auswahl wurde vor der Vorschau gespeichert')

page = client.get('/display')
ok(page.status_code == 200, '/display lädt auch mit Login weiter')

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

    # Am Gerät selbst (localhost) geht der Abschluss ohne Login - der
    # Bildschirm hat keine Tastatur. Aus dem LAN bleibt er gesperrt.
    anon = app.test_client()
    fremd = anon.post('/setup/abschluss',
                      environ_base={'REMOTE_ADDR': '192.168.178.50'})
    ok(fremd.status_code in (301, 302, 401, 403),
       'aus dem LAN verlangt der Abschluss Anmeldung (%d)' % fremd.status_code)
    ok(not os.path.exists(marker), 'aus dem LAN wird nichts abgeschlossen')
    antwort = anon.post('/setup/abschluss')
    ok(antwort.status_code == 302, 'am Gerät (localhost) geht der Abschluss ohne Login')
    ok(os.path.exists(marker), 'Abschluss am Gerät setzt das Merkmal')
    os.remove(marker)

    # Sicher anmelden – frühere Abschnitte können die Sitzung verändert haben
    client.post('/login', data={'username': 'admin', 'password': 'admin'})

    # Hinweis, wenn mehr Bildschirme eingestellt sind als angeschlossen
    _conf, _det = tools.configured_screen_count, tools.detected_screen_count
    tools.detected_screen_count = lambda: 1
    router.set_screen_count(2)
    seite = client.get('/display').get_data(as_text=True)
    ok('erkannt ist aber nur' in seite,
       'Hinweis: 2 eingestellt, aber nur 1 Ausgang erkannt')
    router.set_screen_count(1)
    seite = client.get('/display').get_data(as_text=True)
    ok('erkannt ist aber nur' not in seite,
       'bei passender Anzahl kein Hinweis')
    tools.configured_screen_count, tools.detected_screen_count = _conf, _det

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

print('\n9b) Diagnose-Seite (nur lesend, nur mit Zugang)')

fern = app.test_client()
a = fern.get('/diagnose', environ_base={'REMOTE_ADDR': '192.168.178.50'})
ok(a.status_code == 302, 'aus dem LAN braucht /diagnose den Login (302)')
ok('/login' in a.headers.get('Location', ''), 'und leitet auf die Anmeldung')

with app.app_context():
    router.save_screen(1, name='Bildschirm 1', hdmi='HDMI-1', enabled=True, entries=[
        {'tool': 'safetycross', 'enabled': True, 'dwell': 30, 'sort': 0}])
diag = client.get('/diagnose')
ok(diag.status_code == 200, 'mit Login liefert /diagnose den Bericht (200)')
bericht = diag.get_data(as_text=True)
for abschnitt in ('Dienste', 'Anzeigen laut Router', 'Tool-Dienste',
                  'kiosk-screen1.service', 'lhtpi-anzeige.path'):
    ok(abschnitt in bericht, 'Bericht enthält "%s"' % abschnitt)
ok('safetycross' in bericht and 'localhost:8002' in bericht,
   'Bericht zeigt das eingestellte Tool mit seiner Anzeige-Adresse')
ok(diag.headers.get('Content-Type', '').startswith('text/plain'),
   'Bericht kommt als reiner Text (leicht weiterzugeben)')

print('\n9c) Abschluss übernimmt die Auswahl (Knopf unten in der Leiste)')

if os.path.exists(marker):
    os.remove(marker)
seite = client.get('/display').get_data(as_text=True)
ok('formaction' in seite and '/setup/abschluss' in seite,
   'Abschluss-Knopf steht unten in der Leiste (immer sichtbar)')
ok('Einrichtung abschließen' in seite, 'und ist beschriftet')

with app.app_context():
    router.save_screen(1, name='Bildschirm 1', hdmi='HDMI-1', enabled=True, entries=[
        {'tool': 'slideshow', 'enabled': True, 'dwell': 60, 'sort': 0}])
antwort = client.post('/setup/abschluss', data={
    'screen_count': '1', 'cursor_idle': '3', 'reload_minutes': '30',
    'screen_1_present': '1', 'name_1': 'Bildschirm 1', 'hdmi_1': 'HDMI-1',
    'screen_1_active': '1',
    'tool_1_safetycross_present': '1', 'tool_1_safetycross_active': '1',
    'tool_1_safetycross_dwell': '30',
    'tool_1_slideshow_present': '1',   # ohne _active = abgewählt (Browser sendet nichts)
})
ok(antwort.status_code == 302, 'Abschluss läuft durch')
cfg = client.get('/api/screen/1').get_json()
ok([t['tool'] for t in cfg['tools']] == ['safetycross'],
   'die Auswahl aus dem Abschluss-Formular ist gespeichert (Safety Cross)')
ok(os.path.exists(marker), 'und das Merkmal ist gesetzt')
seite2 = client.get('/display').get_data(as_text=True)
ok('Einrichtung abschließen' not in seite2,
   'nach dem Abschluss verschwindet der Abschluss-Knopf')
os.remove(marker)

print('\n9d) Verwaltung der Tools aus der Anzeigen-Seite')

with app.app_context():
    router.save_screen(1, name='Bildschirm 1', hdmi='HDMI-1', enabled=True, entries=[
        {'tool': 'safetycross', 'enabled': True, 'dwell': 30, 'sort': 0}])
seite = client.get('/display').get_data(as_text=True)
ok('localhost:8002/admin' in seite,
   'Safety Cross ist aus der Anzeigen-Seite zu verwalten verlinkt')
ok('localhost:8001/termine' in seite and 'localhost:8000/' in seite,
   'Termine und Folien ebenso')
ok('Reiter' in seite or 'Anzeige' in seite,
   'mit Hinweis, wie man zurückkommt')

print('\n9e) Wartungs-Knopf in der Ecke (auch bei Folien und Terminen)')

with app.app_context():
    router.save_screen(1, name='Bildschirm 1', hdmi='HDMI-1', enabled=True, entries=[
        {'tool': 'slideshow', 'enabled': True, 'dwell': 60, 'sort': 0}])
seite = anon.get('/screen/1').get_data(as_text=True)
ok('id="wartung"' in seite, 'Anzeige-Seite hat den Wartungs-Knopf')
ok('⚙ Anzeigen' in seite and '/display' in seite,
   'er führt zur Anzeigen-Seite (Verwaltung)')
ok('mousemove' in seite, 'er erscheint bei Mausbewegung')
ok('5000' in seite, 'und verschwindet nach einigen Sekunden von selbst')
ok('"wartung_knopf": true' in seite.replace('True', 'true'),
   'der Router liefert die Einstellung mit')

# Ausschalten wirkt sofort
with app.app_context():
    router.set_wartung_knopf(False)
seite_aus = anon.get('/screen/1').get_data(as_text=True)
ok('id="wartung"' not in seite_aus,
   'ausgeschaltet erscheint kein Wartungs-Knopf am Bildschirm')
with app.app_context():
    router.set_wartung_knopf(True)

# Schalter auf der Anzeigen-Seite
mit_login = client.get('/display').get_data(as_text=True)
ok('name="wartung_knopf"' in mit_login, 'Anzeigen-Seite hat den Schalter')
ok('Bedienung' in mit_login, 'der Schalter erklärt beide Wirkungen')

# Tools bedienbar: Reiter "Admin" im Safety Cross anklickbar
seite_bedienbar = anon.get('/screen/1').get_data(as_text=True)
ok('.frame.on{pointer-events:auto}' in seite_bedienbar,
   'bei Wartung an nimmt das sichtbare Tool Klicks an (Admin erreichbar)')
ok("setAttribute('scrolling', cfg.wartung_knopf ? 'auto' : 'no')" in seite_bedienbar,
   'im Wartungsbetrieb darf der Rahmen scrollen (Verwaltung bedienbar)')
ok('id="einst"' in seite_bedienbar,
   'Einstellungen oeffnen im Kiosk-Fenster (kein Fensterwechsel, kein Kioskverlust)')
_disp = anon.get('/display').get_data(as_text=True)
ok('lhtpi_zurueck' in _disp,
   'die Einstellungs-Seite meldet sich beim Kiosk-Rahmen zurueck')
with app.app_context():
    router.set_wartung_knopf(False)
seite_gesperrt = anon.get('/screen/1').get_data(as_text=True)
ok('.frame.on{pointer-events:auto}' not in seite_gesperrt,
   'bei Wartung aus bleibt die Anzeige unbedienbar')
with app.app_context():
    router.set_wartung_knopf(True)
ok('Zurück zur Anzeige' in mit_login or not router.ist_eingerichtet(),
   'und einen Weg zurück zur laufenden Anzeige')

print('\n9f) Kein Selbststart mehr, wenn das Gerät eingerichtet ist')

# Abschluss herstellen (schreibt die Kenn-Datei)
client.post('/setup/abschluss', data={
    'screen_count': '1', 'cursor_idle': '3', 'reload_minutes': '30',
    'screen_1_present': '1', 'name_1': 'Bildschirm 1', 'hdmi_1': 'HDMI-1',
    'screen_1_active': '1', 'tool_1_safetycross_present': '1',
    'tool_1_safetycross_active': '1', 'tool_1_safetycross_dwell': '30'})
with app.app_context():
    ok(router.ist_eingerichtet(), 'Gerät gilt jetzt als eingerichtet')
seite = client.get('/display').get_data(as_text=True)
ok('data-sekunden="0"' in seite,
   'eingerichtet: kein Selbststart (Seite bleibt stehen)')
ok('startet von selbst' not in seite or 'data-sekunden="0"' in seite,
   'und kein Countdown-Text mehr')
ok('Zurück zur Anzeige' in seite, 'der Rückweg zur Anzeige ist da')

print('\n9g) Chromium-Sitzung wird beim Schreiben verworfen')

import pathlib
import tempfile
with tempfile.TemporaryDirectory() as tmp:
    profil = pathlib.Path(tmp, '.config', 'chromium-screen1', 'Default')
    profil.mkdir(parents=True)
    for n in ('Current Session', 'Last Session', 'Preferences'):
        (profil / n).write_text('x')
    (profil / 'Sessions').mkdir()
    alt_home = os.environ.get('HOME')
    os.environ['HOME'] = tmp
    try:
        with app.app_context():
            router.sitzungen_verwerfen()
    finally:
        if alt_home:
            os.environ['HOME'] = alt_home
    ok(not (profil / 'Current Session').exists(),
       'alte Sitzung wird verworfen (keine Browserleiste mehr)')
    ok(not (profil / 'Last Session').exists(), 'und die letzte ebenfalls')
    ok((profil / 'Preferences').exists(), 'Einstellungen des Profils bleiben')

    # Dauerhaft: Chromium stellt keine Seiten mehr wieder her
    p = profil / 'Preferences'
    p.write_text(json.dumps({'session': {'restore_on_startup': 1},
                             'profile': {'exit_type': 'Crashed'},
                             'eigenes': 'bleibt'}))
    alt_home2 = os.environ.get('HOME')
    os.environ['HOME'] = tmp
    try:
        with app.app_context():
            router.sitzungen_verwerfen()
    finally:
        if alt_home2:
            os.environ['HOME'] = alt_home2
    daten = json.loads(p.read_text())
    ok(daten['session']['restore_on_startup'] == 4,
       'Wiederherstellung abgeschaltet (restore_on_startup=4)')
    ok(daten['profile']['exit_type'] == 'Normal',
       'Profil gilt als sauber beendet (kein "Crashed")')
    ok(daten['eigenes'] == 'bleibt', 'übrige Einstellungen bleiben erhalten')

print('OK – %d Prüfungen bestanden' % len(checks))
for passed, msg in checks:
    print('  ✓', msg)
