#!/usr/bin/env python3
"""Live-Prüfung: zeigt jede Anzeige wirklich ihr eigenes Tool?

Startet Safety Cross und Terminboard als echte Dienste auf eigenen Ports, ruft
ihre Anzeige-Adressen ab und prüft:

  1. Jede Anzeige-Adresse antwortet (HTTP 200).
  2. Jede Anzeige liefert ihren EIGENEN Inhalt (nicht die Folien-App).
  3. Die Router-Seite /screen/N bettet genau die Tools ein, die eingestellt
     sind — und keine anderen.

Aufruf:  ./venv/bin/python tools/test-anzeige-tools-live.py
"""
import json
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

ORDNER = '/tmp/lhtpi-tools-live'
ROUTER_PORT = 8199
TERMIN_PORT = 8101
SC_PORT = 8102
fehler = []


def pruefe(bedingung, text):
    print('  %s %s' % ('OK  ' if bedingung else 'FEHL', text))
    if not bedingung:
        fehler.append(text)


def hole(url, timeout=10):
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as a:
            return a.status, a.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:
        return None, str(e)


def frei(port):
    with socket.socket() as s:
        return s.connect_ex(('127.0.0.1', port)) != 0


def warte(url, prozesse, sekunden=25):
    for _ in range(sekunden * 2):
        status, text = hole(url)
        if status:
            return status, text
        for p in prozesse:
            if p.poll() is not None and p.stderr:
                rest = p.stderr.read().decode('utf-8', 'replace').strip()
                if rest:
                    print('     (Dienst beendet: %s)' % rest.splitlines()[-1][:160])
                return None, 'Dienst beendet'
        time.sleep(0.5)
    return None, 'nicht erreichbar'


shutil.rmtree(ORDNER, ignore_errors=True)
os.makedirs(ORDNER, exist_ok=True)
PY = os.path.join(BASE, 'venv', 'bin', 'python')
dienste = []

print('1) Safety Cross direkt (:8102/)')
sc_dir = os.path.join(BASE, 'tools', 'safety-cross')
sc_env = dict(os.environ, PORT=str(SC_PORT), DB_PFAD=os.path.join(ORDNER, 'sc.db'),
              LHTPI_HWID='piserial:10000000demo', LHTPI_LICENSE_ENFORCE='0')
sc = subprocess.Popen([PY, 'app.py'], cwd=sc_dir, env=sc_env,
                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
dienste.append(sc)
status, seite = warte('http://127.0.0.1:%d/' % SC_PORT, [sc])
pruefe(status == 200, 'Safety Cross antwortet auf / (HTTP %s)' % status)
if status == 200:
    pruefe('Safety Cross' in seite, 'Seite zeigt den Safety Cross (eigener Inhalt)')
    pruefe('Playlist' not in seite, 'keine Folien-Inhalte auf der SC-Anzeige')

print('2) Terminboard direkt (:8101/board/kiosk)')
ter_dir = os.path.join(BASE, 'terminboard')
ter_env = dict(os.environ, TERMINBOARD_PORT=str(TERMIN_PORT),
               TERMINBOARD_HOST='127.0.0.1',
               TERMINBOARD_DB=os.path.join(ORDNER, 'ter.db'),
               LHTPI_HWID='piserial:10000000demo', LHTPI_LICENSE_ENFORCE='0')
ter = subprocess.Popen([PY, 'app.py'], cwd=ter_dir, env=ter_env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
dienste.append(ter)
status, seite = warte('http://127.0.0.1:%d/board/kiosk' % TERMIN_PORT, [ter])
pruefe(status == 200, 'Terminboard antwortet auf /board/kiosk (HTTP %s)' % status)
if status == 200:
    pruefe('Playlist' not in seite, 'keine Folien-Inhalte auf der Termin-Anzeige')

print('3) Router-Seite bettet genau das eingestellte Tool ein')
umgebung = dict(os.environ)
umgebung.update({
    'LHTPI_DB': os.path.join(ORDNER, 'router.db'),
    'LHTPI_PORT': str(ROUTER_PORT),
    'LHTPI_HWID': 'piserial:10000000demo',
    'LHTPI_KIOSK_PROBE': '0',
    'LHTPI_TOOLS': 'slideshow,terminboard,safetycross',
    'LHTPI_SCREENS_FILE': os.path.join(ORDNER, 'screens'),
    'LHTPI_SCREEN2_FILE': os.path.join(ORDNER, 'screen2'),
    'LHTPI_INSTALLED_MARKER': os.path.join(ORDNER, 'installed'),
    'LHTPI_LICENSE_FILE': os.path.join(ORDNER, 'license.key'),
    'LHTPI_LICENSE_ENFORCE': '0',
    # Anzeige-Adressen auf die Testports umbiegen
    'LHTPI_TOOL_URLS': 'slideshow=http://localhost:%d/present/kiosk,'
                       'terminboard=http://localhost:%d/board/kiosk,'
                       'safetycross=http://localhost:%d/'
                       % (ROUTER_PORT, TERMIN_PORT, SC_PORT),
})
router = subprocess.Popen([PY, os.path.join(BASE, 'app.py')], cwd=BASE,
                          env=umgebung, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE)
dienste.append(router)
status, _ = warte('http://127.0.0.1:%d/lizenz' % ROUTER_PORT, [router])
pruefe(status == 200, 'Verteiler-App läuft (HTTP %s)' % status)

import urllib.parse                                    # noqa: E402


def speichere(tools_liste):
    """Belegung über die Anzeigen-Seite setzen (am Gerät ohne Login)."""
    daten = {'screen_count': '1', 'cursor_idle': '3', 'reload_minutes': '30',
             'screen_1_present': '1', 'name_1': 'Bildschirm 1',
             'hdmi_1': 'HDMI-1', 'screen_1_active': '1'}
    for i, (t, d) in enumerate(tools_liste):
        daten['tool_1_%s_present' % t] = '1'
        daten['tool_1_%s_active' % t] = '1'
        daten['tool_1_%s_dwell' % t] = str(d)
        daten['tool_1_%s_sort' % t] = str(i)
    anfrage = urllib.request.Request(
        'http://127.0.0.1:%d/display/save' % ROUTER_PORT,
        data=urllib.parse.urlencode(daten).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'})
    urllib.request.urlopen(anfrage, timeout=10).read()


def router_seite(idx=1):
    status, text = hole('http://127.0.0.1:%d/screen/%d' % (ROUTER_PORT, idx))
    if status != 200:
        return status, {}
    roh = re.search(r'<script id="cfg" type="application/json">(.*?)</script>',
                    text, re.S)
    return status, json.loads(roh.group(1)) if roh else {}


for tool, erwartet in (('safetycross', ':%d/' % SC_PORT),
                       ('terminboard', ':%d/board/kiosk' % TERMIN_PORT),
                       ('slideshow', ':%d/present/kiosk' % ROUTER_PORT)):
    speichere([(tool, 30)])
    status, cfg = router_seite()
    namen = [t['tool'] for t in cfg.get('tools', [])]
    urls = [t['url'] for t in cfg.get('tools', [])]
    pruefe(namen == [tool], 'nur %s ist eingestellt (gefunden: %s)' % (tool, namen))
    pruefe(bool(urls) and erwartet in urls[0],
           '%s zeigt auf seine eigene Adresse (%s)' % (tool, urls[0] if urls else '-'))

# Zwei Tools gemischt: beide Adressen müssen vorkommen
speichere([('safetycross', 30), ('terminboard', 30)])
status, cfg = router_seite()
namen = sorted(t['tool'] for t in cfg.get('tools', []))
urls = ' '.join(t['url'] for t in cfg.get('tools', []))
pruefe(namen == ['safetycross', 'terminboard'],
       'bei zwei Tools stehen beide in der Rotation (%s)' % namen)
pruefe(':%d/' % SC_PORT in urls and ':%d/board/kiosk' % TERMIN_PORT in urls,
       'jedes Tool behält seine eigene Anzeige-Adresse')
pruefe('present/kiosk' not in urls,
       'die Folien-App wird nicht eingeschlichen, wenn sie nicht gewählt ist')

# Und andersherum: mit gewählten Folien zeigt die Anzeige auf die Folien
speichere([('slideshow', 60)])
status, cfg = router_seite()
pruefe('/present/kiosk' in [t['url'] for t in cfg.get('tools', [])][0],
       'mit gewählten Folien zeigt die Anzeige auf die Folien-App')
pruefe([t['tool'] for t in cfg.get('tools', [])] == ['slideshow'],
       'und auf nichts anderes')

for p in dienste:
    p.terminate()
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()

print('\n%s' % ('ALLES GRÜN' if not fehler else 'FEHLER: ' + '; '.join(fehler)))
sys.exit(1 if fehler else 0)
