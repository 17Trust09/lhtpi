#!/usr/bin/env python3
"""Screenshot der Ersteinrichtung (Anzeigen-Seite mit Hinweis-Kasten)."""
import os
from playwright.sync_api import sync_playwright

CH = '/tmp/cft/chrome-headless-shell-linux64/chrome-headless-shell'
OUT = '/opt/data/projects/lhtpi/docs/multitool-kiosk/screenshots'
L = 'http://127.0.0.1:8900'

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CH, headless=True)
    ctx = browser.new_context(viewport={'width': 1920, 'height': 1080},
                              device_scale_factor=1, locale='de-DE')
    page = ctx.new_page()
    page.goto(L + '/login', wait_until='networkidle')
    page.fill('input[name=username]', 'admin')
    page.fill('input[name=password]', 'admin')
    page.click('button[type=submit]')
    page.wait_for_load_state('networkidle')
    page.goto(L + '/display', wait_until='networkidle')
    page.wait_for_timeout(1200)
    ziel = os.path.join(OUT, '10-ersteinrichtung.png')
    page.screenshot(path=ziel, full_page=True)
    print('%s (%.0f kB)' % (ziel, os.path.getsize(ziel) / 1024))
    browser.close()
