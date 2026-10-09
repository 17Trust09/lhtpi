#!/usr/bin/env python3
"""Screenshots der Anzeigen-Seite: ein Tool (fest) vs. Rotation, plus Startkarte.

Startet die App selbst auf Port 8901 mit eigener Datenbank, setzt die Belegung
direkt in der Datenbank und fotografiert die Seite.

Aufruf:  /tmp/shots-venv/bin/python tools/shots-anzeige.py
"""
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH = '/tmp/cft/chrome-headless-shell-linux64/chrome-headless-shell'
OUT = os.path.join(BASE, 'docs', 'multitool-kiosk', 'screenshots')
ORDNER = '/tmp/lhtpi-shots-anzeige'
VENV_PY = os.path.join(BASE, 'venv', 'bin', 'python')   # App läuft im Projekt-venv
PORT = 8901
L = 'http://127.0.0.1:%d' % PORT

shutil.rmtree(ORDNER, ignore_errors=True)
os.makedirs(ORDNER, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

umgebung = dict(os.environ)
umgebung.update({
    'LHTPI_DB': os.path.join(ORDNER, 'shots.db'),
    'LHTPI_PORT': str(PORT),
    'LHTPI_HWID': 'piserial:10000000demo',
    'LHTPI_KIOSK_PROBE': '0',
    'LHTPI_TOOLS': 'slideshow,terminboard,safetycross',
    'LHTPI_SCREENS_FILE': os.path.join(ORDNER, 'screens'),
    'LHTPI_SCREEN2_FILE': os.path.join(ORDNER, 'screen2'),
    'LHTPI_INSTALLED_MARKER': os.path.join(ORDNER, 'installed'),
    'LHTPI_LICENSE_FILE': os.path.join(ORDNER, 'license.key'),
    'LHTPI_LICENSE_ENFORCE': '0',
})
sys.path.insert(0, BASE)

# Gültige Lizenz für das Demo-Gerät erzeugen (Schlüssel liegt außerhalb des Repos)
SCHLUESSEL = '/opt/data/lhtpi-lizenz/privat.json'
if os.path.exists(SCHLUESSEL):
    erzeugt = subprocess.run(
        [VENV_PY, os.path.join(BASE, 'license_bundle.py'), '--make-key',
         '--tools=1,2,3', '--screens=2'],
        env=dict(umgebung, LHTPI_SIGN_KEY_FILE=SCHLUESSEL),
        cwd=BASE, capture_output=True, text=True)
    zeilen = erzeugt.stdout.splitlines()
    beginn = next((i for i, z in enumerate(zeilen) if z.startswith('LHTPI-')), None)
    if beginn is not None:
        # Die Lizenz besteht aus der Kennung plus Signaturzeilen
        block = [z.strip() for z in zeilen[beginn:] if z.strip()]
        open(umgebung['LHTPI_LICENSE_FILE'], 'w').write('\n'.join(block) + '\n')
        print('Lizenz für die Screenshots hinterlegt (%d Zeilen)' % len(block))

lauf = subprocess.Popen([VENV_PY, os.path.join(BASE, 'app.py')],
                        env=umgebung, cwd=BASE,
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
try:
    gestartet = False
    for _ in range(40):
        try:
            urllib.request.urlopen(L + '/lizenz', timeout=5).read()
            gestartet = True
            break
        except Exception:
            if lauf.poll() is not None:
                raise SystemExit('App beendet: %s'
                                 % lauf.stderr.read().decode()[-400:])
            time.sleep(0.5)
    if not gestartet:
        raise SystemExit('App nicht erreichbar')

    # Belegung über die Seite selbst setzen (am Gerät ohne Login möglich)
    def setze(tools_liste, bildschirme=1):
        daten = {
            'screen_count': str(bildschirme),
            'cursor_idle': '3',
            'reload_minutes': '30',
            'screen_1_present': '1',
            'name_1': 'Bildschirm 1',
            'hdmi_1': 'HDMI-1',
            'screen_1_active': '1',
        }
        for i, (t, d) in enumerate(tools_liste):
            daten['tool_1_%s_present' % t] = '1'
            daten['tool_1_%s_active' % t] = '1'
            daten['tool_1_%s_dwell' % t] = str(d)
            daten['tool_1_%s_sort' % t] = str(i)
        rumpf = urllib.parse.urlencode(daten).encode()
        anfrage = urllib.request.Request(
            L + '/display/save', data=rumpf,
            headers={'Content-Type': 'application/x-www-form-urlencoded'})
        urllib.request.urlopen(anfrage, timeout=10).read()

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CH, headless=True)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1100},
                                  device_scale_factor=1, locale='de-DE')
        page = ctx.new_page()

        def foto(name):
            seite = ctx.new_page()
            seite.goto(L + '/display', wait_until='networkidle')
            seite.wait_for_timeout(700)
            ziel = os.path.join(OUT, name)
            seite.screenshot(path=ziel, full_page=True)
            print('%s (%.0f kB)' % (ziel, os.path.getsize(ziel) / 1024))
            seite.close()

        # A) Ein Tool = fest, ohne Dauer-Felder
        setze([('slideshow', 60)])
        foto('20-anzeige-ein-tool.png')

        # Live-Umschaltung prüfen: zweites Tool anklicken, ohne Neuladen
        pruef = ctx.new_page()
        pruef.goto(L + '/display', wait_until='networkidle')
        vorher_sichtbar = pruef.locator(
            '.card[data-screen="1"] .rot-feld').first.is_visible()
        pruef.locator('.card[data-screen="1"] input.toolbox').nth(1).check()
        pruef.wait_for_timeout(400)
        nachher_sichtbar = pruef.locator(
            '.card[data-screen="1"] .rot-feld').first.is_visible()
        pille = pruef.locator(
            '.card[data-screen="1"] [data-pill]').inner_text().strip()
        pruef.close()
        print('Live-Umschaltung: Dauer vorher sichtbar=%s, nach 2. Auswahl=%s, '
              'Kasten=%r' % (vorher_sichtbar, nachher_sichtbar, pille))
        if vorher_sichtbar or not nachher_sichtbar or 'Rotation' not in pille:
            raise SystemExit('FEHLER: Live-Umschaltung greift nicht')

        # B) Drei Tools = Rotation mit Dauer je Tool
        setze([('slideshow', 300), ('terminboard', 120), ('safetycross', 120)])
        foto('21-anzeige-rotation.png')

        # C) Eingerichtet: Startkarte mit Countdown
        open(umgebung['LHTPI_INSTALLED_MARKER'], 'w').close()
        foto('22-anzeige-start.png')

        browser.close()
finally:
    lauf.terminate()
    lauf.wait(timeout=10)
