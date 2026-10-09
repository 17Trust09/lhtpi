#!/usr/bin/env python3
"""Demo-Inhalte für Screenshots des Multitool-Kiosk-Bundles erzeugen.

Legt eine eigene, wegwerfbare Datenbank an (/tmp/shots) und füllt sie mit
plausiblen Inhalten, damit die Screenshots echte Seiten mit echten Daten zeigen.
Die echte lhtpi.db bleibt unberührt.
"""
import os
import subprocess
import sys

SHOTS = '/tmp/shots'
BASE = '/opt/data/projects/lhtpi'
CH = '/tmp/cft/chrome-headless-shell-linux64/chrome-headless-shell'

os.makedirs(SHOTS, exist_ok=True)

# ── 1. Titelbilder für die Slideshow rendern (echtes HTML -> PNG) ───────────
CARDS = [
    ('card1', 'Sicherheitsunterweisung', 'Montag, 07:30 Uhr · Halle 2',
     'Unterweisung PSA – Teilnahme für alle Schichtmitarbeiter'),
    ('card2', 'Neue Kalibrier-Anweisung', 'gültig ab 01.11.',
     'Messmittel vor der Nutzung an Station 3 abgleichen'),
    ('card3', 'Willkommen im Team', 'Abteilung Montage',
     'Neue Kollegin ab Montag · Einweisung durch den Meister'),
]
TEMPLATE = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><style>
 html,body{{margin:0;width:1280px;height:720px;overflow:hidden;
   background:#0d1117;font-family:system-ui,"Segoe UI",sans-serif;color:#f2f6fa}}
 .wrap{{display:flex;flex-direction:column;justify-content:center;height:100%;padding:0 96px}}
 .bar{{width:120px;height:10px;border-radius:6px;background:#38bdf8;margin-bottom:38px}}
 h1{{font-size:64px;line-height:1.1;margin:0 0 22px;font-weight:700}}
 p.sub{{font-size:34px;color:#7dd3fc;margin:0 0 46px;font-weight:600}}
 p.txt{{font-size:27px;color:#9fb0c0;margin:0;max-width:1000px;line-height:1.45}}
 .foot{{position:absolute;bottom:44px;left:96px;font-size:22px;color:#5f6f7f;letter-spacing:.06em}}
</style></head><body><div class="wrap">
 <div class="bar"></div><h1>{title}</h1><p class="sub">{sub}</p><p class="txt">{txt}</p>
</div><div class="foot">LHTPi · Abteilung Montage</div></body></html>"""

uploads = os.path.join(BASE, 'uploads')
os.makedirs(uploads, exist_ok=True)
card_files = []
for name, title, sub, txt in CARDS:
    html = os.path.join(SHOTS, name + '.html')
    png = os.path.join(uploads, name + '.png')
    with open(html, 'w') as f:
        f.write(TEMPLATE.format(title=title, sub=sub, txt=txt))
    subprocess.run([CH, '--headless', '--no-sandbox', '--disable-gpu',
                    '--hide-scrollbars', '--force-device-scale-factor=1',
                    '--window-size=1280,720', '--virtual-time-budget=3000',
                    '--screenshot=' + png, 'file://' + html],
                   check=True, capture_output=True)
    card_files.append((os.path.basename(png), title))
print('Titelbilder:', ', '.join(f for f, _ in card_files))

# ── 2. lhtpi füllen ─────────────────────────────────────────────────────────
sys.path.insert(0, BASE)
os.environ.update(
    LHTPI_DB=os.path.join(SHOTS, 'lhtpi.db'),
    LHTPI_TOOLS='slideshow,terminboard,safetycross',
    LHTPI_KIOSK_PROBE='0',
    LHTPI_HWID='piserial:10000000demo',
    LHTPI_SCREEN_COUNT='2',
    LHTPI_LICENSE_FILE=os.path.join(SHOTS, 'license.key'),
    LHTPI_INSTALLED_MARKER=os.path.join(SHOTS, 'installed'),
    LHTPI_LICENSE_ENFORCE='0',
)
import license_bundle as lic                            # noqa: E402
lic.write_license(lic.make_key('1,2,3', screens=2))

from app import app                                     # noqa: E402
from models import db, Media, Playlist, PlaylistItem    # noqa: E402
import kiosk_router as router                           # noqa: E402

with app.app_context():
    db.drop_all()
    db.create_all()
    from models import User
    u = User(username='admin')
    u.set_password('admin')
    db.session.add(u)

    media = []
    for i, (fname, title) in enumerate(card_files, start=1):
        path = os.path.join(uploads, fname)
        m = Media(filename=fname, original_name=title,
                  file_type='image', mime_type='image/png',
                  file_size=os.path.getsize(path))
        db.session.add(m)
        db.session.flush()
        media.append(m)
    db.session.commit()

    pl = Playlist(name='Unterweisung', is_active=True)
    db.session.add(pl)
    db.session.flush()
    for pos, m in enumerate(media):
        db.session.add(PlaylistItem(playlist_id=pl.id, media_id=m.id,
                                    position=pos, display_duration=8))
    db.session.commit()

    router.set_screen_count(2)
    router.set_cursor_idle_seconds(3)
    router.set_iframe_reload_minutes(30)
    router.save_screen(1, name='Halle 2 – Eingang', hdmi='HDMI-1', entries=[
        {'tool': 'slideshow', 'enabled': True, 'dwell': 300, 'sort': 0},
        {'tool': 'safetycross', 'enabled': True, 'dwell': 120, 'sort': 1},
    ])
    router.save_screen(2, name='Werkstatt', hdmi='HDMI-2', entries=[
        {'tool': 'terminboard', 'enabled': True, 'dwell': 30, 'sort': 0},
    ])
    print('lhtpi-DB: %d Medien, %d Bildschirme' % (len(media), router.screen_count()))

# ── 3. Terminboard füllen ───────────────────────────────────────────────────
sys.path.insert(0, os.path.join(BASE, 'terminboard'))
os.environ['TERMINBOARD_DB'] = os.path.join(SHOTS, 'terminboard.db')
for mod in [m for m in list(sys.modules) if m in ('app', 'models', 'routes', 'usb_source')]:
    del sys.modules[mod]
import datetime                                         # noqa: E402
import app as termin_app                                # noqa: E402
from models import db as tdb, Termin, User as TUser     # noqa: E402

with termin_app.app.app_context():
    tdb.drop_all()
    tdb.create_all()
    tu = TUser(username='admin')
    tu.set_password('admin')
    tdb.session.add(tu)
    heute = datetime.date.today()
    rows = [
        ('kalibrierung', 'Drehmomentschlüssel 40–200 Nm', 'KAL-2026-114',
         heute, heute + datetime.timedelta(days=4), 'Prüfung durch externen Dienstleister'),
        ('schulung', 'Kran- und Hebetechnik', 'SCH-2026-07',
         heute + datetime.timedelta(days=2), heute + datetime.timedelta(days=3),
         'Schulung für alle Staplerfahrer, Raum 1'),
        ('info', 'Inventur Halle 2', 'INV-2026-11',
         heute + datetime.timedelta(days=9), heute + datetime.timedelta(days=10),
         'Bestandsaufnahme – Produktion ruht ab 06:00'),
        ('kalibrierung', 'Waage Station 3', 'KAL-2026-115',
         heute + datetime.timedelta(days=16), None, 'Intervallprüfung alle 12 Monate'),
        ('info', 'Betriebsversammlung', 'BV-2026-04',
         heute + datetime.timedelta(days=21), None, 'Alle Abteilungen, 14:00 Uhr Kantine'),
    ]
    for typ, titel, ref, start, ende, text in rows:
        tdb.session.add(Termin(typ=typ, titel=titel, referenz=ref, start=start, ende=ende, text=text))
    tdb.session.commit()
    print('Terminboard-DB: %d Termine' % Termin.query.count())

print('FERTIG')
