"""Test: kein Standardpasswort mehr — Einmal-Token, Wechselzwang, Secret-Pflicht.

Aufruf:   ./venv/bin/python test_zugang.py

Die Tests laufen auf einer Wegwerf-Datenbank (LHTPI_DB) im temporären Ordner;
die echte lhtpi.db bleibt unberührt. Der lokale Zugang am Gerät
(LHTPI_LOKAL_LOGIN) wird abgeschaltet, damit sich die App wie aus dem LAN
verhält.
"""
import os
import sqlite3
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

TMP = tempfile.mkdtemp(prefix='lhtpi-zugang-test-')
SECRET = 'test-secret-nur-fuer-diesen-test-32-plus-zeichen'
TOKEN_DATEI = os.path.join(TMP, 'setup-token')

os.environ['LHTPI_DB'] = os.path.join(TMP, 'test.db')
os.environ['LHTPI_SECRET'] = SECRET
os.environ['LHTPI_SETUP_TOKEN_FILE'] = TOKEN_DATEI
os.environ.pop('LHTPI_SETUP_TOKEN', None)
os.environ['LHTPI_LOKAL_LOGIN'] = '0'          # Verhalten wie aus dem LAN
os.environ['LHTPI_KIOSK_PROBE'] = '0'
os.environ['LHTPI_TOOLS'] = 'slideshow'
os.environ['LHTPI_LICENSE_ENFORCE'] = '0'
os.environ['LHTPI_HWID'] = 'piserial:10000000testgeraet'
os.environ['LHTPI_LICENSE_FILE'] = os.path.join(TMP, 'license.key')
os.environ['LHTPI_INSTALLED_MARKER'] = os.path.join(TMP, 'installed')
os.environ['LHTPI_SCREENS_FILE'] = os.path.join(TMP, 'screens')

import test_keys                                        # noqa: E402
test_keys.install_env()

from werkzeug.security import check_password_hash, generate_password_hash  # noqa: E402

from app import app                                     # noqa: E402
from models import db, User                             # noqa: E402
import auth_setup                                      # noqa: E402

LAN = {'REMOTE_ADDR': '192.168.178.50'}
NEUES_PASSWORT = 'Korallenriff-2026-rot'

checks = []


def ok(cond, msg):
    checks.append((bool(cond), msg))
    assert cond, 'FEHLER: ' + msg


client = app.test_client()


def text(antwort):
    return antwort.get_data(as_text=True)


# ── 1. Frische Datenbank: Benutzer ohne bekanntes Passwort ───────────────────
with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    ok(admin is not None, 'frische Datenbank legt den Benutzer admin an')
    ok(admin.must_change_password is True, 'admin muss das Passwort wechseln')
    ok(not admin.check_password('admin'), 'admin/admin ist kein gültiges Passwort mehr')

ok(os.path.exists(TOKEN_DATEI), 'Einmal-Token wurde als Datei abgelegt')
token = open(TOKEN_DATEI, encoding='utf-8').read().strip()
ok(len(token) >= 32, 'Einmal-Token ist lang genug (%d Zeichen)' % len(token))
ok((os.stat(TOKEN_DATEI).st_mode & 0o777) == 0o600, 'Token-Datei hat Rechte 0600')

# ── 2. Login mit dem alten Standardpasswort scheitert ────────────────────────
antwort = client.post('/login', data={'username': 'admin', 'password': 'admin'},
                      environ_base=LAN)
ok(antwort.status_code == 200, 'Login mit admin/admin bleibt auf der Anmeldeseite')
ok('Ungültige Anmeldedaten' in text(antwort), 'Login mit admin/admin wird abgelehnt')

client.get('/logout', environ_base=LAN)
antwort = client.get('/', environ_base=LAN)
ok(antwort.status_code == 302 and '/login' in antwort.headers['Location'],
   'ohne Anmeldung ist das Dashboard gesperrt')

# ── 3. Anmeldung mit dem Einmal-Token führt zum Passwortwechsel ──────────────
antwort = client.post('/login', data={'username': 'admin', 'password': token},
                      environ_base=LAN)
ok(antwort.status_code == 302 and '/passwort' in antwort.headers['Location'],
   'das Einmal-Token führt zum Passwortwechsel')

antwort = client.get('/', environ_base=LAN)
ok(antwort.status_code == 302 and '/passwort' in antwort.headers['Location'],
   'ohne Passwortwechsel bleibt das Dashboard gesperrt (aus dem LAN)')

antwort = client.get('/passwort', environ_base=LAN)
ok(antwort.status_code == 200, 'die Seite /passwort ist erreichbar')
ok('Erstinbetriebnahme' in text(antwort), 'die Seite erklärt die Erstinbetriebnahme')

# Die Anzeige am Gerät darf der offene Wechsel nicht stören (Kiosk, keine Tastatur)
antwort = client.get('/', environ_base={'REMOTE_ADDR': '127.0.0.1'})
ok(antwort.status_code == 200, 'am Gerät selbst (localhost) stört der Wechselzwang nicht')

# ── 4. Regelprüfung beim neuen Passwort ─────────────────────────────────────
antwort = client.post('/passwort', data={'alt': token, 'neu': 'kurz', 'wieder': 'kurz'},
                      environ_base=LAN)
ok('mindestens 12 Zeichen' in text(antwort), 'zu kurzes Passwort wird abgelehnt')

antwort = client.post('/passwort', data={'alt': 'falsch', 'neu': NEUES_PASSWORT,
                                        'wieder': NEUES_PASSWORT}, environ_base=LAN)
ok('bisherige Passwort stimmt nicht' in text(antwort),
   'falsches bisheriges Passwort wird abgelehnt')

antwort = client.post('/passwort', data={'alt': token, 'neu': NEUES_PASSWORT,
                                        'wieder': NEUES_PASSWORT + 'x'},
                      environ_base=LAN)
ok('nicht identisch' in text(antwort), 'abweichende Wiederholung wird abgelehnt')

antwort = client.post('/passwort', data={'alt': token, 'neu': 'admin', 'wieder': 'admin'},
                      environ_base=LAN)
ok('bekannter Standardwert' in text(antwort), 'Standardpasswörter werden abgelehnt')

# ── 5. Passwortwechsel: Token verbraucht ───────────────────────────────────
antwort = client.post('/passwort', data={'alt': token, 'neu': NEUES_PASSWORT,
                                        'wieder': NEUES_PASSWORT}, environ_base=LAN)
ok(antwort.status_code == 302, 'gültiger Wechsel wird angenommen')
ok(not os.path.exists(TOKEN_DATEI), 'das Einmal-Token wird nach dem Wechsel entfernt')

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    ok(admin.check_password(NEUES_PASSWORT), 'das neue Passwort gilt')
    ok(admin.must_change_password is False, 'der Wechselzwang ist aufgehoben')
    ok(not admin.check_password('admin'), 'admin/admin gilt weiterhin nicht')

antwort = client.get('/', environ_base=LAN)
ok(antwort.status_code == 200, 'das Dashboard ist nach dem Wechsel offen')

# ── 6. Alte Zugänge funktionieren nicht mehr ───────────────────────────────
client.get('/logout', environ_base=LAN)
for alt, name in ((token, 'Einmal-Token'), ('admin', 'admin/admin')):
    antwort = client.post('/login', data={'username': 'admin', 'password': alt},
                          environ_base=LAN)
    ok('Ungültige Anmeldedaten' in text(antwort),
       'Anmeldung mit %s wird abgelehnt' % name)

# ── 7. Start ohne LHTPI_SECRET bricht mit klarer Meldung ab ─────────────────
ohne_secret = dict(os.environ)
ohne_secret.pop('LHTPI_SECRET', None)
ohne_secret['LHTPI_DB'] = os.path.join(TMP, 'ohne-secret.db')
lauf = subprocess.run([sys.executable, '-c', 'import app'], cwd=BASE,
                      env=ohne_secret, capture_output=True, text=True)
ok(lauf.returncode != 0, 'ohne LHTPI_SECRET endet der Start mit Fehlercode')
ok('LHTPI_SECRET' in (lauf.stdout + lauf.stderr),
   'die Fehlermeldung nennt LHTPI_SECRET')
ok(not os.path.exists(os.path.join(TMP, 'ohne-secret.db')),
   'ohne Secret wird nicht einmal eine Datenbank angelegt')

# ── 8. Bestehende Datenbank mit admin/admin wird beim Start saniert ────────
alt_db = os.path.join(TMP, 'alt.db')
verbindung = sqlite3.connect(alt_db)
verbindung.execute('CREATE TABLE "user" (id INTEGER PRIMARY KEY, '
                   'username VARCHAR(80) UNIQUE NOT NULL, '
                   'password_hash VARCHAR(200) NOT NULL)')
verbindung.execute('INSERT INTO "user" (username, password_hash) VALUES (?, ?)',
                   ('admin', generate_password_hash('admin')))
verbindung.commit()
verbindung.close()

alt_token_datei = os.path.join(TMP, 'alt-token')
umgebung = dict(os.environ)
umgebung['LHTPI_DB'] = alt_db
umgebung['LHTPI_SETUP_TOKEN_FILE'] = alt_token_datei
umgebung.pop('LHTPI_SETUP_TOKEN', None)
lauf = subprocess.run([sys.executable, '-c', 'import app'], cwd=BASE,
                      env=umgebung, capture_output=True, text=True)
ok(lauf.returncode == 0, 'Start mit bestehender Datenbank klappt (%s)' % lauf.stderr[-200:])
ok('Standardpasswort' in lauf.stdout, 'der Start meldet den ersetzten Standardzugang')
ok(os.path.exists(alt_token_datei), 'auch dort wird ein Einmal-Token abgelegt')

alt_token = open(alt_token_datei, encoding='utf-8').read().strip()
verbindung = sqlite3.connect(alt_db)
hash_alt = verbindung.execute("SELECT password_hash FROM \"user\" "
                             "WHERE username = 'admin'").fetchone()[0]
zwang = verbindung.execute("SELECT must_change_password FROM \"user\"").fetchall()
verbindung.close()
ok(not check_password_hash(hash_alt, 'admin'), 'das alte Standardpasswort gilt nicht mehr')
ok(check_password_hash(hash_alt, alt_token), 'stattdessen gilt das Einmal-Token')
ok(zwang and all(z[0] == 1 for z in zwang), 'der Passwortwechsel wird erzwungen')
ok(len(alt_token) >= 32, 'auch das zweite Token ist lang genug')

print('\nOK – %d Prüfungen bestanden' % len(checks))
for passed, msg in checks:
    print('  ✓', msg)
