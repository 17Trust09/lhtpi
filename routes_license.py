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
import os

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
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


@app.route('/setup/abschluss', methods=['POST'])
@login_required
def setup_abschluss():
    """Ersteinrichtung abschließen.

    Setzt das Merkmal: ab jetzt startet die Anzeige (systemd-Pfad-Wächter) und
    die Lizenzprüfung ist aktiv.
    """
    # Ohne Lizenz würde sich das Gerät mit dem Merkmal sofort selbst sperren –
    # das fangen wir hier ab.
    if not lic.read_license() and os.environ.get('LHTPI_LICENSE_ENFORCE') != '0':
        flash('Ohne Lizenz wäre die Anzeige sofort gesperrt. Bitte lizenz.key auf '
              'die Boot-Partition der SD-Karte legen (oder nach '
              + lic.LICENSE_FILE + ' kopieren) und das Gerät neu starten.')
        return redirect(url_for('display'))
    pfad = lic.MARKER_FILE
    try:
        ordner = os.path.dirname(pfad)
        if ordner:
            os.makedirs(ordner, exist_ok=True)
        open(pfad, 'w').close()
    except OSError:
        flash('Einrichtung konnte nicht abgeschlossen werden (kein Schreibrecht).')
        return redirect(url_for('display'))

    # Auswahl aus der Anzeigen-Seite zuerst übernehmen: die Anzeige soll mit
    # genau dieser Belegung starten, nicht mit dem alten Stand.
    if request.method == 'POST' and request.form.get('screen_1_present') is not None:
        try:
            from routes_kiosk import belegung_speichern
            belegung_speichern()
        except Exception as fehler:                      # noqa: BLE001
            import traceback
            print('Belegung konnte nicht übernommen werden: %s' % fehler)
            traceback.print_exc()

    import kiosk_router as router
    router.set_screen_count(router.screen_count())   # Dateien für die Anzeige
    flash('Einrichtung abgeschlossen – die Anzeige startet jetzt automatisch.')
    return redirect(url_for('display'))
