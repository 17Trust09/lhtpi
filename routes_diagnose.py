"""Diagnose am Gerät: Zustand der Dienste, Anzeigen, Logs — als reiner Text.

Aufruf: ``http://<IP>:8000/diagnose`` (mit Login, Standard admin/admin).

Die Seite ist absichtlich schlicht (text/plain): sie ist der Blick in die
Eingeweide des Geräts, kein Kiosk-Inhalt. Sie zeigt nur Zustände, ändert
nichts — damit man aus der Ferne sieht, warum eine Anzeige schwarz bleibt.
"""
import os
import subprocess
import urllib.error
import urllib.request

from flask import Response
from flask_login import login_required

import app as app_modul
import kiosk_router as router
import kiosk_tools as tools
import license_bundle as lic

app = app_modul.app


def _lauf(befehl, timeout=6):
    try:
        p = subprocess.run(befehl, capture_output=True, text=True, timeout=timeout)
        return ((p.stdout or '') + (p.stderr or '')).strip()
    except FileNotFoundError:
        return '(nicht vorhanden: %s)' % befehl[0]
    except subprocess.SubprocessError as e:
        return '(Fehler: %s)' % e


def _dienst(name):
    return '%-32s active=%-10s enabled=%s' % (
        name, _lauf(['systemctl', 'is-active', name]) or '?',
        _lauf(['systemctl', 'is-enabled', name]) or '?')


def _tail(pfad, zeilen=15):
    if not os.path.exists(pfad):
        return '(fehlt: %s)' % pfad
    try:
        with open(pfad, errors='replace') as f:
            return ''.join(f.readlines()[-zeilen:]).strip() or '(leer)'
    except OSError as e:
        return '(nicht lesbar: %s)' % e


def _http(url, timeout=4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as a:
            text = a.read(600).decode('utf-8', 'replace')
            return 'HTTP %s · %r' % (a.status, text[:160])
    except urllib.error.HTTPError as e:
        return 'HTTP %s' % e.code
    except Exception as e:                                   # noqa: BLE001
        return 'nicht erreichbar (%s)' % type(e).__name__


@app.route('/diagnose')
@login_required
def diagnose():
    """Zustandsbericht des Geräts als Text (nur lesend)."""
    zeilen = []

    def sag(text=''):
        zeilen.append(text)

    info = lic.read_license()
    sag('LHTPi Diagnose')
    sag('=' * 60)
    sag('Gerät            : %s' % lic.hardware_id())
    sag('Eingerichtet     : %s' % ('ja' if router.ist_eingerichtet() else 'nein'))
    sag('Bildschirm-Datei : %s -> %r' % (tools.SCREENS_FILE, _tail(tools.SCREENS_FILE, 2)))
    sag('Bildschirme      : eingestellt %s / erkannt %s'
        % (tools.configured_screen_count(), tools.detected_screen_count()))
    sag('Tools (Datei)    : %r' % (_tail(tools.TOOLS_FILE, 3),))
    sag('Lizenz           : %s' % ('vorhanden' if info else 'keine'))

    sag()
    sag('Dienste')
    sag('-' * 60)
    for name in ('lhtpi.service', 'lhtpi-setup.service', 'lhtpi-anzeige.path',
                 'lhtpi-anzeige.service', 'kiosk-screen1.service',
                 'kiosk-screen2.service', 'lhtpi-lizenz-import.service',
                 'lightdm.service'):
        sag(_dienst(name))

    sag()
    sag('Anzeigen laut Router')
    sag('-' * 60)
    for idx in (1, 2):
        cfg = router.screen_config(idx)
        if cfg is None:
            sag('Bildschirm %d: nicht eingestellt' % idx)
            continue
        sag('Bildschirm %d: mode=%s · aktiv=%s · Ausgang=%s'
            % (idx, cfg.get('mode'), cfg.get('enabled'), cfg.get('hdmi')))
        for t in cfg.get('tools') or []:
            sag('   %-14s %s  (%s s)' % (t['tool'], t['url'], t['dwell']))
        if not cfg.get('tools'):
            sag('   (kein Tool aktiv)')

    sag()
    sag('Tool-Dienste direkt abgefragt')
    sag('-' * 60)
    for tool in tools.tool_ids():
        url = tools.default_url(tool)
        sag('%-14s %s' % (tool, url))
        sag('   %s' % _http(url))

    sag()
    sag('Logs')
    sag('-' * 60)
    for pfad in ('/home/pi/kiosk-screen1.log', '/home/pi/kiosk-screen2.log',
                 '/home/pi/setup.log'):
        sag('--- %s (letzte Zeilen) ---' % pfad)
        sag(_tail(pfad))
        sag()

    sag('--- journalctl -u kiosk-screen1.service ---')
    sag(_lauf(['journalctl', '-u', 'kiosk-screen1.service', '-n', '15',
               '--no-pager'], timeout=10) or '(keine Ausgabe)')
    sag()
    sag('--- X / Bildschirme ---')
    sag(_lauf(['xrandr', '--current'], timeout=6) or '(keine Ausgabe)')

    return Response('\n'.join(zeilen) + '\n',
                    mimetype='text/plain; charset=utf-8')
