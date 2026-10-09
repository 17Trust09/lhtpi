#!/usr/bin/env python3
"""Prüft den Betrieb mit EINEM Bildschirm.

Startet die echte App (Flask-Testclient, echte Routen) in einem frischen
Zustand und prüft, was bei einem bzw. zwei erkannten Ausgängen ausgeliefert
wird — inklusive Lizenz als Obergrenze.

Aufruf:  ./venv/bin/python tools/test-einbildschirm-live.py
"""
import os
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

TMP = tempfile.mkdtemp(prefix='lhtpi-1screen-')
os.environ.update({
    'LHTPI_DB': os.path.join(TMP, 'app.db'),
    'LHTPI_TOOLS': 'slideshow,terminboard,safetycross',
    'LHTPI_LICENSE_FILE': os.path.join(TMP, 'license.key'),
    'LHTPI_INSTALLED_MARKER': os.path.join(TMP, 'installed'),
    'LHTPI_SCREENS_FILE': os.path.join(TMP, 'screens'),
    'LHTPI_LICENSE_ENFORCE': '0',
    'LHTPI_HWID': 'piserial:10000000einbildschirm',
})

import test_keys                       # Testschlüssel (kein echtes Geheimnis)
test_keys.install_env()

import license_bundle as lic
import app as app_mod
import kiosk_router as router
import kiosk_tools as tools

# Kontext für direkte Datenbank-Zugriffe außerhalb einer Anfrage
_kontext = app_mod.app.app_context()
_kontext.push()
app_mod.db.create_all()

fehler = []


def pruefe(cond, text):
    print(('  OK   ' if cond else '  FEHL ') + text)
    if not cond:
        fehler.append(text)


# Lizenz: Obergrenze 2 Bildschirme (wie bei Tim) – ein Bildschirm ist erlaubt
lic.write_license(lic.make_key('1,2,3', screens=2, hwid=os.environ['LHTPI_HWID']))
print('Lizenz:', lic.current()['valid'], '| erlaubt bis',
      tools.licensed_screen_limit(), 'Bildschirme')

client = app_mod.app.test_client()

print('\n1) Ein Ausgang angeschlossen (LHTPI_SCREEN_COUNT=1)')
os.environ['LHTPI_SCREEN_COUNT'] = '1'
router.set_setting(router.SETTING_SCREEN_COUNT, '')
daten = client.get('/api/screens').get_json()
pruefe(daten.get('count') == 1, 'ausgeliefert wird genau 1 Bildschirm')
schirme = daten.get('screens', [])
pruefe(any(s.get('idx') == 1 and s.get('enabled') for s in schirme),
       'Bildschirm 1 ist aktiv')
pruefe(not any(s.get('idx') == 2 and s.get('enabled') for s in schirme),
       'kein zweiter Bildschirm aktiv')
marke2 = os.path.join(os.path.dirname(tools.SCREENS_FILE), 'screen2')
pruefe(not os.path.exists(marke2),
       'Merkmal für Bildschirm 2 fehlt (zweiter Kiosk startet nicht)')
router.set_screen_count(1)          # so speichert die Einrichtungs-Seite
pruefe(open(tools.SCREENS_FILE).read().strip() == '1',
       'Datei "screens" steht nach dem Speichern auf 1')
pruefe(not os.path.exists(marke2), 'auch nach dem Speichern kein zweiter Kiosk')

client.post('/login', data={'username': 'admin', 'password': 'admin'})
seite = client.get('/display').get_data(as_text=True)
pruefe('Erkannte Ausgänge: <b>1</b>' in seite, 'Seite nennt den einen Ausgang')
pruefe('erkannt ist aber nur' not in seite, 'kein Warnhinweis nötig')

print('\n2) Zwei Ausgänge angeschlossen (LHTPI_SCREEN_COUNT=2)')
os.environ['LHTPI_SCREEN_COUNT'] = '2'
router.set_setting(router.SETTING_SCREEN_COUNT, '')
daten = client.get('/api/screens').get_json()
pruefe(daten.get('count') == 2, 'ausgeliefert werden 2 Bildschirme')
router.set_screen_count(2)          # so speichert die Einrichtungs-Seite
pruefe(os.path.exists(marke2),
       'Merkmal für Bildschirm 2 vorhanden (zweiter Kiosk startet)')

print('\n3) Bewusste Einstellung 2, aber nur 1 Ausgang erkannt')
router.set_setting(router.SETTING_SCREEN_COUNT, '')
router.set_screen_count(2)                      # bewusst gespeichert
os.environ['LHTPI_SCREEN_COUNT'] = '1'
pruefe(router.screen_count() == 2, 'die eigene Einstellung bleibt erhalten')
seite = client.get('/display').get_data(as_text=True)
pruefe('erkannt ist aber nur' in seite,
       'Warnhinweis: 2 eingestellt, nur 1 Ausgang erkannt')

print('\n4) Lizenz ist die Obergrenze')
lic.write_license(lic.make_key('1,2,3', screens=1, hwid=os.environ['LHTPI_HWID']))
router.set_setting(router.SETTING_SCREEN_COUNT, '')
os.environ['LHTPI_SCREEN_COUNT'] = '2'
pruefe(router.screen_count() == 1,
       'Lizenz für 1 Bildschirm begrenzt auch bei 2 Ausgängen')

print('\n' + ('ALLES GRÜN – Ein-Bildschirm-Betrieb läuft' if not fehler
              else 'FEHLER: %d Prüfung(en)' % len(fehler)))
sys.exit(1 if fehler else 0)
