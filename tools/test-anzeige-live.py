#!/usr/bin/env python3
"""Live-Prüfung: Anzeigen-Seite ohne Login, Knopf „Anzeige starten" wirkt.

Startet die App auf einem eigenen Port mit eigener Datenbank und prüft über
echtes HTTP:

  1. /display  ohne Login      -> 200 (am Gerät gilt man als angemeldet)
  2. /display  aus dem LAN     -> Weiterleitung zur Anmeldung
  3. /anzeige/start            -> schreibt die Bildschirm-Datei neu (Wächter)
  4. Seite hat keinen Weg zum Dashboard, aber Start-Knopf + Countdown

Aufruf:  ./venv/bin/python tools/test-anzeige-live.py
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

ORDNER = '/tmp/lhtpi-anzeige-live'
PORT = 8099
fehler = []


def pruefe(bedingung, text):
    print('  %s %s' % ('OK  ' if bedingung else 'FEHL', text))
    if not bedingung:
        fehler.append(text)


def lan_ip():
    """Eigene LAN-Adresse (nicht 127.0.0.1) für den Fremdzugriff-Test."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def hole(pfad, adresse='127.0.0.1', port=None):
    url = 'http://%s:%d%s' % (adresse, port or PORT, pfad)
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as a:
            return a.status, a.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def sende(pfad):
    """POST ohne Weiterleitung - wir wollen den Status und das Ziel sehen."""
    class KeineWeiterleitung(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None          # Weiterleitung nicht ausführen

    anfrage = urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, pfad),
                                     data=b'')
    oeffner = urllib.request.build_opener(KeineWeiterleitung)
    try:
        with oeffner.open(anfrage, timeout=10) as a:
            return a.status, a.headers.get('Location', '')
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Location', '')


shutil.rmtree(ORDNER, ignore_errors=True)
os.makedirs(ORDNER, exist_ok=True)
umgebung = dict(os.environ)
umgebung.update({
    'LHTPI_DB': os.path.join(ORDNER, 'anzeige.db'),
    'LHTPI_PORT': str(PORT),
    'LHTPI_HOST': '0.0.0.0',
    'LHTPI_HWID': 'piserial:10000000demo',
    'LHTPI_KIOSK_PROBE': '0',
    'LHTPI_TOOLS': 'slideshow,terminboard,safetycross',
    'LHTPI_SCREENS_FILE': os.path.join(ORDNER, 'screens'),
    'LHTPI_SCREEN2_FILE': os.path.join(ORDNER, 'screen2'),
    'LHTPI_INSTALLED_MARKER': os.path.join(ORDNER, 'installed'),
    'LHTPI_LICENSE_FILE': os.path.join(ORDNER, 'license.key'),
    'LHTPI_LICENSE_ENFORCE': '0',
})

lauf = subprocess.Popen([sys.executable, os.path.join(BASE, 'app.py')],
                        env=umgebung, cwd=BASE,
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
try:
    print('1) Anzeigen-Seite am Gerät (ohne Anmeldung)')
    status = None
    for _ in range(40):
        try:
            status, seite = hole('/display')
            break
        except Exception:
            if lauf.poll() is not None:
                raise SystemExit('App ist beendet: %s'
                                 % lauf.stderr.read().decode()[-400:])
            time.sleep(0.5)
    if status is None:
        raise SystemExit('App wurde nicht erreichbar')

    pruefe(status == 200, '/display ohne Login erreichbar (HTTP %d)' % status)
    pruefe('Einrichtung abschließen' in seite,
           'Hinweis „Erste Einrichtung" mit Abschluss-Knopf ist da')
    pruefe('Dashboard' not in seite and '/dashboard' not in seite,
           'kein Link zum Dashboard auf der Anzeigen-Seite')

    print('2) Aus dem LAN bleibt der Login Pflicht')
    # Vom selben Rechner aus sieht der Server die Anfrage immer als lokal -
    # der Fremdzugriff wird deshalb im Unit-Test mit gesetzter Quelladresse
    # geprüft (test_kiosk_router.py: „aus dem LAN verlangt /display Login").
    eigene = lan_ip()
    print('     (über %s geprüft im Unit-Test - vom selben Rechner aus '
          'erscheint jede Anfrage lokal)' % (eigene or 'LAN-Adresse'))

    print('3) Knopf „Anzeige starten" (Pfad-Wächter auslösen)')
    open(umgebung['LHTPI_INSTALLED_MARKER'], 'w').close()
    pfad = umgebung['LHTPI_SCREENS_FILE']
    vorher = os.stat(pfad).st_mtime_ns if os.path.exists(pfad) else 0
    time.sleep(0.05)
    status, ziel = sende('/anzeige/start')
    nachher = os.stat(pfad).st_mtime_ns if os.path.exists(pfad) else 0
    pruefe(status == 302, 'Anzeige starten antwortet mit Weiterleitung (HTTP %d)' % status)
    pruefe(ziel.endswith('/display'), 'leitet zurück auf die Anzeigen-Seite')
    pruefe(nachher > vorher,
           'Bildschirm-Datei neu geschrieben -> Wächter startet die Fenster')
    inhalt = open(pfad).read().strip()
    pruefe(re.match(r'^[12]$', inhalt) is not None,
           'Bildschirm-Anzahl bleibt gültig (%r)' % inhalt)

    print('4) Eingerichtet: Start-Knopf und Countdown auf der Seite')
    status, seite = hole('/display')
    pruefe(status == 200, 'Anzeigen-Seite lädt weiter')
    pruefe('Anzeige jetzt starten' in seite, 'Start-Knopf ist da')
    pruefe('restsekunden' in seite, 'Countdown ist eingebaut (startet von selbst)')
    pruefe('Einrichtung abschließen' not in seite,
           'Abschluss-Knopf ist verschwunden')
    pruefe('data-pill' in seite and 'rot-feld' in seite,
           'Betriebsart und Dauer-Felder sind für die Live-Umschaltung markiert')
finally:
    lauf.terminate()
    lauf.wait(timeout=10)

print('\n%s' % ('ALLES GRÜN' if not fehler else 'FEHLER: ' + ', '.join(fehler)))
sys.exit(1 if fehler else 0)
