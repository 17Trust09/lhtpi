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


# ── Anzeige (Kiosk, ohne Login) ──────────────────────────────────────────────

@app.route('/screen/<int:idx>')
def screen(idx):
    """Router-Seite: zeigt die Tools dieses Bildschirms (fest oder rotierend)."""
    cfg = router.screen_config(idx)
    if cfg is None:
        abort(404)
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

@app.route('/display')
@login_required
def display():
    return render_template('display.html', o=router.display_overview())


@app.route('/display/save', methods=['POST'])
@login_required
def display_save():
    """Bildschirm-Anzahl, Tool-Belegung, Anzeigedauern und Cursor speichern."""
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

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True})
    flash('Anzeige-Einstellungen gespeichert')
    return redirect(url_for('display'))
