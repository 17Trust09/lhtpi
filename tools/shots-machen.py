#!/usr/bin/env python3
"""Screenshots der Kiosk-Seiten erzeugen (echte Seiten, echte Daten).

Startet nichts selbst — erwartet die Demo-Instanzen:
    lhtpi        http://127.0.0.1:8900   (2 Bildschirme, 3 Tools)
    Terminboard  http://127.0.0.1:8901
    Safety Cross http://127.0.0.1:8902
    gesperrte Instanz http://127.0.0.1:8903 (ungültige Lizenz)
"""
import os
from playwright.sync_api import sync_playwright

CH = '/tmp/cft/chrome-headless-shell-linux64/chrome-headless-shell'
OUT = '/opt/data/projects/lhtpi/docs/multitool-kiosk/screenshots'
L = 'http://127.0.0.1:8900'      # Verteiler-App (Demo)
GESPERRT = 'http://127.0.0.1:8903'

os.makedirs(OUT, exist_ok=True)


def schuss(page, name, full=False, ruhe=1200):
    page.wait_for_timeout(ruhe)
    pfad = os.path.join(OUT, name)
    page.screenshot(path=pfad, full_page=full)
    groesse = os.path.getsize(pfad)
    print('  %-34s %6.0f kB' % (name, groesse / 1024))
    return pfad


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CH, headless=True)

    # ── Desktop-Ansicht (Admin) ────────────────────────────────────────────
    ctx = browser.new_context(viewport={'width': 1920, 'height': 1080},
                              device_scale_factor=1, locale='de-DE')
    page = ctx.new_page()
    page.goto(L + '/login', wait_until='networkidle')
    page.fill('input[name=username]', 'admin')
    page.fill('input[name=password]', 'admin')
    page.click('button[type=submit]')
    page.wait_for_load_state('networkidle')
    print('angemeldet, mache Screenshots:')
    schuss(page, '01-dashboard.png', full=True)

    page.goto(L + '/display', wait_until='networkidle')
    schuss(page, '02-anzeigen-einstellungen.png', full=True, ruhe=1500)

    page.goto(L + '/lizenz', wait_until='networkidle')
    schuss(page, '03-lizenz.png')

    # ── Anzeige-Seiten (Kiosk, ohne Login) ─────────────────────────────────
    page.goto(L + '/screen/1', wait_until='networkidle')
    schuss(page, '04-anzeige-schirm1-rotation.png', ruhe=3500)

    page.goto(L + '/screen/2', wait_until='networkidle')
    schuss(page, '05-anzeige-schirm2-termine.png', ruhe=2500)

    page.goto(L + '/present/kiosk', wait_until='networkidle')
    schuss(page, '06-tool-folien.png', ruhe=3000)
    ctx.close()

    # ── Terminboard + Safety Cross einzeln ─────────────────────────────────
    ctx2 = browser.new_context(viewport={'width': 1920, 'height': 1080},
                               device_scale_factor=1, locale='de-DE')
    p2 = ctx2.new_page()
    p2.goto('http://127.0.0.1:8901/board/kiosk', wait_until='networkidle')
    schuss(p2, '07-tool-terminboard.png', ruhe=2000)

    p3 = ctx2.new_page()
    p3.goto('http://127.0.0.1:8902/', wait_until='networkidle')
    schuss(p3, '08-tool-safety-cross.png', ruhe=2000)
    ctx2.close()

    # ── Gesperrte Anzeige (ungültige Lizenz) ───────────────────────────────
    ctx3 = browser.new_context(viewport={'width': 1920, 'height': 1080},
                               device_scale_factor=1, locale='de-DE')
    p4 = ctx3.new_page()
    p4.goto(GESPERRT + '/screen/1', wait_until='networkidle')
    schuss(p4, '09-gesperrt.png', ruhe=800)
    ctx3.close()

    browser.close()

print('fertig:', OUT)
