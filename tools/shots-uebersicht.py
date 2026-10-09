#!/usr/bin/env python3
"""Übersichtstafel: alle Screenshots als eine Grafik (HTML -> PNG)."""
import os
import subprocess

CH = '/tmp/cft/chrome-headless-shell-linux64/chrome-headless-shell'
DIR = '/opt/data/projects/lhtpi/docs/multitool-kiosk/screenshots'

TILES = [
    ('01-dashboard.png', '1 · Dashboard (Menü mit „Anzeigen" und „Lizenz")'),
    ('02-anzeigen-einstellungen.png', '2 · Einstellungen: welches Tool auf welchem Schirm, wie lange'),
    ('03-lizenz.png', '3 · Lizenz: Geräte-ID, Schlüssel, freigeschaltete Tools'),
    ('04-anzeige-schirm1-rotation.png', '4 · Anzeige Schirm 1: Folien ↔ Safety Cross (300 s / 120 s)'),
    ('05-anzeige-schirm2-termine.png', '5 · Anzeige Schirm 2: Terminboard fest'),
    ('06-tool-folien.png', '6 · Tool Folien (Slideshow)'),
    ('07-tool-terminboard.png', '7 · Tool Terminboard'),
    ('08-tool-safety-cross.png', '8 · Tool Safety Cross'),
    ('09-gesperrt.png', '9 · Lizenz fehlt/fremd → Sperrseite mit Geräte-ID'),
    ('10-ersteinrichtung.png', '10 · Erster Start: Gerät fragt selbst nach der Einrichtung'),
]

html = ["""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><style>
body{margin:0;background:#0b0f14;font-family:system-ui,"Segoe UI",sans-serif;color:#e8eef4;
     padding:34px 34px 40px}
h1{font-size:34px;margin:0 0 6px;font-weight:700}
p.sub{color:#8ea0b0;font-size:19px;margin:0 0 26px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:26px 24px}
.tile{background:#121821;border:1px solid #222c37;border-radius:14px;overflow:hidden}
.tile img{display:block;width:100%;height:auto}
.cap{padding:10px 14px 12px;font-size:17px;color:#b9c6d2;line-height:1.35}
</style></head><body>
<h1>Multitool-Kiosk — so sieht es aus</h1>
<p class="sub">LHT-Bundle · ein Gerät, bis zu drei Tools, ein oder zwei Bildschirme · echte Screenshots (Dezember 2026)</p>
<div class="grid">"""]
for datei, cap in TILES:
    html.append('<div class="tile"><img src="file://%s/%s"><div class="cap">%s</div></div>'
                % (DIR, datei, cap))
html.append('</div></body></html>')

pfad = '/tmp/shots/uebersicht.html'
open(pfad, 'w').write('\n'.join(html))
out = os.path.join(DIR, '00-uebersicht.png')
subprocess.run([CH, '--headless', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
                '--allow-file-access-from-files', '--force-device-scale-factor=1.25',
                '--window-size=2200,1500', '--virtual-time-budget=6000',
                '--screenshot=' + out, 'file://' + pfad],
               check=True, capture_output=True)
print('Tafel: %s (%.0f kB)' % (out, os.path.getsize(out) / 1024))
