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
import bildschirm_info
import anzeige_fein
import rollback
import license_bundle as lic


# ── Anzeige (Kiosk, ohne Login) ──────────────────────────────────────────────

@app.route('/screen/<int:idx>')
def screen(idx):
    """Router-Seite: zeigt die Tools dieses Bildschirms (fest oder rotierend)."""
    # Fehlende Bildschirme anlegen, statt 404 zu liefern: Nach einer Neu-
    # installation ist die Datenbank leer, bis jemand die Seite "Anzeigen"
    # oeffnet. Der Kiosk laedt /screen/N aber sofort - ohne diesen Aufruf
    # erschiene "Not Found", obwohl das Geraet gesund ist.
    router.ensure_defaults()
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
        autostart_sekunden=0 if eingerichtet else AUTOSTART_SEKUNDEN,
        # Welcher Bildschirm haengt dran, worauf laeuft er, was waere moeglich.
        # Ohne das muss man fuer eine Aufloesung ins Terminal.
        bildschirme=bildschirm_info.bildschirme(),
        # Groesse der Seite je Bildschirm (kein Zoom): 1.00 = so gross, wie
        # der Bildschirm es hergibt, also scharf.
        skalen={idx: anzeige_fein.skala(idx) for idx in (1, 2)},
        skala_min=anzeige_fein.SKALA_MIN,
        skala_max=anzeige_fein.SKALA_MAX)


@app.route('/display/aufloesung', methods=['POST'])
@login_required
def display_aufloesung():
    """Aufloesung setzen - sofort, mit 30-Sekunden-Rollback.

    Der Wechsel ist ein Versuch: Ein Fernseher kann die gewaehlte Aufloesung
    mit 'kein Signal' quittieren. Deshalb wird der VORHERIGE Zustand gespeichert
    und ein 30-s-Fenster gestartet. Bestaetigt der Nutzer ('passt'), wird die
    Wahl dauerhaft uebernommen. Sonst setzt der HDMI-Waechter nach 30 s den
    vorherigen Zustand zurueck.
    """
    ausgang = (request.form.get('ausgang') or '').strip()
    modus = (request.form.get('modus') or '').strip()
    dauerhaft = request.form.get('dauerhaft') == '1'

    # Vorherigen Zustand merken (fuer den Rollback), dann sofort setzen.
    vorher = {b['ausgang']: b.get('aktuell') for b in bildschirm_info.bildschirme()
              if b.get('angeschlossen') and b.get('aktuell')}

    ok, meldung = bildschirm_info.setze_aufloesung(ausgang, modus)
    if not ok:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': False, 'meldung': meldung})
        flash(meldung, 'fehler')
        return redirect(url_for('display'))

    # Rollback-Fenster starten. Wichtig: die dauerhafte Speicherung (anzeige-
    # fein.json + Kernel-Zeile) passiert ERST bei Bestaetigung - so bleibt der
    # Rollback sauber, ohne dass eine unbrauchbare Aufloesung in die Startzeile
    # geschrieben wird.
    rollback.start(vorher)

    # Fenster neu starten, damit die neue Groesse sichtbar wird.
    neu = router.anzeige_neu_starten()
    if neu:
        meldung = meldung + ' Anzeige neu gestartet.'

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True, 'meldung': meldung, 'neu': neu,
                        'rollback': True, 'ausgang': ausgang, 'modus': modus,
                        'dauerhaft': dauerhaft})

    flash(meldung, 'ok')
    return redirect(url_for('display'))


@app.route('/display/aufloesung/bestaetigen', methods=['POST'])
@login_required
def display_aufloesung_bestaetigen():
    """'Passt' - die gewaehlte Aufloesung wird dauerhaft uebernommen."""
    ausgang = (request.form.get('ausgang') or '').strip()
    modus = (request.form.get('modus') or '').strip()
    dauerhaft = request.form.get('dauerhaft') == '1'

    rollback.bestaetigen()

    # Jetzt erst dauerhaft merken: in anzeige-fein.json (fuer Waechter/Retter/
    # Startskript) und, auf Wunsch, in der Kernel-Zeile.
    meldung = 'Aufloesung uebernommen.'
    try:
        idx = int(ausgang.rsplit('-', 1)[-1])
        anzeige_fein.setze_aufloesung(idx, modus)
    except (ValueError, AttributeError):
        pass

    if dauerhaft:
        ok2, meldung2 = bildschirm_info.dauerhaft_setzen(ausgang, modus)
        meldung = meldung + ' ' + meldung2 if ok2 else meldung + ' Dauerhaft: ' + meldung2

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True, 'meldung': meldung})
    flash(meldung, 'ok')
    return redirect(url_for('display'))


@app.route('/display/aufloesung/abbrechen', methods=['POST'])
@login_required
def display_aufloesung_abbrechen():
    """Sofort zuruecksetzen (statt auf den 30-s-Timer zu warten)."""
    vorher = rollback.vorher_zustand()
    for ausgang, modus in vorher.items():
        if modus:
            bildschirm_info.setze_aufloesung(ausgang, modus)
    rollback.abbrechen()
    router.anzeige_neu_starten()

    meldung = 'Zurueckgesetzt auf den vorherigen Zustand.'
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True, 'meldung': meldung})
    flash(meldung, 'ok')
    return redirect(url_for('display'))


@app.route('/display/skala', methods=['POST'])
@login_required
def display_skala():
    """Skalierung eines Bildschirms setzen (Groesse der Seite, kein Zoom)."""
    try:
        idx = int(request.form.get('idx') or 0)
    except ValueError:
        idx = 0
    wert = request.form.get('skala')

    ok, meldung = anzeige_fein.setze_skala(idx, wert)
    if not ok:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': False, 'meldung': meldung})
        flash(meldung, 'fehler')
        return redirect(url_for('display'))

    # Die Skalierung wird beim Start des Fensters uebergeben. Sie wirkt deshalb
    # erst nach einem Neustart der Anzeige - dafuer ist sie dann scharf, weil
    # Chromium von Anfang an in dieser Groesse zeichnet.
    neu = False
    if request.form.get('neu_starten') == '1':
        neu = router.anzeige_neu_starten()
        meldung = meldung + (' Anzeige neu gestartet.' if neu
                             else ' Anzeige konnte nicht neu starten.')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True, 'meldung': meldung, 'neu': neu})
    flash(meldung, 'ok')
    return redirect(url_for('display'))


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
        # Die Anzeige soll die neue Belegung sofort zeigen: Fenster sauber
        # neu starten. Vorher blieb der Bildschirm nach dem Speichern schwarz
        # oder zeigte weiter die alte Seite.
        router.anzeige_neu_starten()
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


# ── Gerät: Neustart und Herunterfahren ──────────────────────────────────────

def _systembefehl(ziel):
    """Nur vom Gerät selbst - dann Befehl auslösen."""
    if not _ist_lokal():
        return ('', 403)
    if not router.systembefehl(ziel):
        # Die Kiosk-Fenster sind schon geschlossen: Anzeige wieder hochfahren
        # (derselbe Weg wie „Anzeige starten" - der Pfad-Wächter übernimmt).
        router.anzeige_neu_starten()
        return ('', 500)
    return ('', 204)


@app.route('/system/neustart', methods=['POST'])
def system_neustart():
    """Gerät neu starten (Knopf an der Anzeige)."""
    return _systembefehl('reboot')


@app.route('/system/herunterfahren', methods=['POST'])
def system_herunterfahren():
    """Gerät herunterfahren (Knopf an der Anzeige)."""
    return _systembefehl('poweroff')
