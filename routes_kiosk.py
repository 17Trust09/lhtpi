"""Multitool-Kiosk: Anzeige-Router (/screen/N) und Admin-Seite „Anzeigen".

Wird von app.py nach ``routes`` importiert, damit die Kern-Routen unverändert
bleiben.
"""
from flask import (render_template, request, redirect, url_for, jsonify, abort,
                   flash)
from flask_login import login_required
from app import app
import kiosk_router as router
import kiosk_tools as tools
import license_bundle as lic


# ── Anzeige (Kiosk, ohne Login) ──────────────────────────────────────────────

@app.route('/screen/<int:idx>')
def screen(idx):
    """Router-Seite: zeigt die Tools dieses Bildschirms (fest oder rotierend)."""
    cfg = router.screen_config(idx)
    if cfg is None:
        abort(404)
    # Vorschau (aus der Verwaltung): zeigt an, welches Tool gerade dran ist.
    # Der Kiosk lädt die Seite ohne diesen Zusatz - dort bleibt alles ruhig.
    cfg['vorschau'] = request.args.get('vorschau') == '1'
    return render_template('screen.html', cfg=cfg)


@app.route('/api/screens')
def api_screens():
    """Alle Bildschirme inkl. Belegung (Diagnose)."""
    return jsonify({
        'count': router.screen_count(),
        'installed': tools.installed_tools(),
        'screens': router.all_screen_configs(),
    })


@app.route('/api/screen/<int:idx>')
def api_screen(idx):
    cfg = router.screen_config(idx)
    if cfg is None:
        return jsonify({'error': 'Bildschirm %d nicht aktiv' % idx}), 404
    return jsonify(cfg)


# ── Admin-Seite „Anzeigen" ───────────────────────────────────────────────────

LOKALE_ADRESSEN = ('127.0.0.1', '::1')
AUTOSTART_SEKUNDEN = 30       # eingerichtetes Gerät: Anzeige startet von selbst


def _ist_lokal():
    """Kommt der Aufruf vom Gerät selbst? (Kiosk-Bildschirm, ohne Login)"""
    return request.remote_addr in LOKALE_ADRESSEN


@app.route('/display')
@login_required
def display():
    eingerichtet = router.ist_eingerichtet()
    return render_template(
        'display.html', o=router.display_overview(),
        eingerichtet=eingerichtet,
        erkannte_schirme=tools.detected_screen_count(),
        lizenz_da=bool(lic.read_license()),
        lokal=_ist_lokal(),
        # Von selbst starten nur bei der Ersteinrichtung. Ist das Gerät fertig,
        # bleibt die Seite stehen, bis Tim 'Anzeige jetzt starten' drückt -
        # sonst nimmt ihm der Selbststart nach 30 s die Seite unter den Füßen weg.
        autostart_sekunden=0 if eingerichtet else AUTOSTART_SEKUNDEN)


@app.route('/anzeige/start', methods=['POST'])
def anzeige_start():
    """Anzeige starten: die Kiosk-Fenster übernehmen den Bildschirm.

    Schreibt die Bildschirm-Datei neu - der Pfad-Wächter startet daraufhin die
    Kiosk-Fenster und beendet die Einrichtungs-Seite.
    """
    router.set_screen_count(router.screen_count())
    flash('Anzeige gestartet – die Fenster öffnen sich in wenigen Sekunden.')
    return redirect(url_for('display'))


def belegung_speichern():
    """Bildschirm-Anzahl, Tool-Belegung, Anzeigedauern und Cursor übernehmen.

    Eigene Funktion, weil auch "Einrichtung abschließen" die Auswahl zuerst
    sichern muss — sonst startet die Anzeige mit dem alten Stand.
    """
    router.set_screen_count(request.form.get('screen_count', router.screen_count()))

    for idx in range(1, router.MAX_SCREENS + 1):
        if request.form.get('screen_%d_present' % idx) is None:
            continue
        entries = []
        for position, tool in enumerate(tools.installed_tools()):
            if request.form.get('tool_%d_%s_present' % (idx, tool)) is None:
                continue
            entries.append({
                'tool': tool,
                'enabled': request.form.get('tool_%d_%s_active' % (idx, tool)) is not None,
                'dwell': request.form.get('tool_%d_%s_dwell' % (idx, tool)),
                'sort': request.form.get('tool_%d_%s_sort' % (idx, tool), position),
            })
        router.save_screen(
            idx,
            name=request.form.get('name_%d' % idx),
            hdmi=request.form.get('hdmi_%d' % idx),
            entries=entries,
            enabled=request.form.get('screen_%d_active' % idx) is not None,
        )

    router.set_cursor_idle_seconds(request.form.get('cursor_idle',
                                                     router.cursor_idle_seconds()))
    router.set_iframe_reload_minutes(request.form.get('reload_minutes',
                                                       router.iframe_reload_minutes()))
    # Nur ändern, wenn das Feld dabei ist (ältere Seiten senden es nicht)
    if request.form.get('wartung_knopf') is not None:
        router.set_wartung_knopf(request.form.get('wartung_knopf') == '1')


@app.route('/display/save', methods=['POST'])
@login_required
def display_save():
    """Belegung speichern (Knopf "Speichern")."""
    belegung_speichern()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True})

    # Knopf "Vorschau": die Auswahl wird zuerst gespeichert, damit man genau
    # das sieht, was gleich auf dem Bildschirm läuft (nicht den alten Stand).
    weiter = (request.form.get('weiter') or '').strip()
    if weiter.startswith('vorschau_'):
        try:
            idx = int(weiter.split('_', 1)[1])
        except (IndexError, ValueError):
            idx = 0
        if idx:
            flash('Gespeichert – die Vorschau zeigt diesen Bildschirm.')
            return redirect(url_for('screen', idx=idx, vorschau=1))

    flash('Anzeige-Einstellungen gespeichert')
    return redirect(url_for('display'))


# ── Mauszeiger ──────────────────────────────────────────────────────────────

@app.route('/zeiger/klick', methods=['POST'])
def zeiger_klick():
    """Anzeige meldet: der Zeiger soll jetzt verschwinden.

    Die Kiosk-Seite blendet den Zeiger nach der Ruhezeit per CSS aus und loest
    danach diesen Aufruf aus - nur so zeichnet Chromium den Zeiger auch
    tatsaechlich aus (siehe kiosk_router.zeiger_klick). Nur vom Geraet selbst.
    """
    if not _ist_lokal():
        return ('', 403)
    router.zeiger_klick()
    return ('', 204)
