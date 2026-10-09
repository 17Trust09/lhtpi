"""Lizenz: Sperrseite (wenn die Lizenz nicht gilt) und Statusseite.

Wird von app.py nach ``routes`` und ``routes_kiosk`` importiert.

Regeln
------
* Ohne Lizenz und ohne Installationsmerkmal läuft die App im Entwicklungsmodus
  (keine Sperre) — sonst könnte man auf dem eigenen Gerät nicht arbeiten.
* Sobald eine Lizenz hinterlegt ist (oder das Gerät als installiert markiert
  wurde), muss sie gültig sein: sonst zeigen alle Seiten die Sperrseite.
* ``/lizenz`` bleibt immer erreichbar — dort steht die Geräte-ID, die man zum
  Erzeugen des Schlüssels braucht.
"""
from flask import render_template, request
from app import app
import license_bundle as lic

# Diese Pfade bleiben ohne gültige Lizenz erreichbar
FREI = ('/lizenz', '/login', '/logout', '/static', '/favicon.ico')


@app.before_request
def lizenz_wache():
    """Sperrt die App, wenn eine Lizenz vorhanden, aber ungültig ist."""
    if request.path.startswith(FREI):
        return None
    if not lic.enforced():
        return None
    info = lic.current()
    if info is not None and info['valid']:
        return None
    return render_template('gesperrt.html', info=info,
                           hwid=lic.hardware_id(),
                           key=lic.read_license()), 403


@app.route('/lizenz')
def lizenz_status():
    """Statusseite: Geräte-ID, hinterlegter Schlüssel, freigeschaltete Tools."""
    info = lic.current()
    return render_template('lizenz.html', info=info,
                           hwid=lic.hardware_id(),
                           key=lic.read_license(),
                           enforced=lic.enforced(),
                           datei=lic.LICENSE_FILE)
