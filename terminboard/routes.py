import os
from datetime import date, datetime
from flask import (render_template, request, redirect, url_for,
                   jsonify, flash, send_from_directory)
from flask_login import login_user, logout_user, login_required, current_user

from app import app
from models import db, User, Termin
from usb_source import (find_usb_termin_dir, usb_termine, parse_date,
                        get_mode, get_manual_source, set_setting,
                        SETTING_MODE, SETTING_MANUAL_SOURCE, ALLOWED_TYPES,
                        find_azubi_dir, find_azubi_images, AZUBI_IMAGE_EXTS,
                        get_azubi_start, get_azubi_weeks, azubi_is_active,
                        SETTING_AZUBI_START, SETTING_AZUBI_WEEKS)


def is_ajax():
    return (request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.args.get('format') == 'json')


def ajax_or_redirect(success_message, error_message=None, redirect_to='dashboard'):
    if is_ajax():
        if error_message:
            return jsonify({'ok': False, 'message': error_message}), 400
        return jsonify({'ok': True, 'message': success_message})
    if error_message:
        flash(error_message, 'error')
    else:
        flash(success_message, 'success')
    return redirect(url_for(redirect_to))


def _iso(d):
    if isinstance(d, datetime):
        return d.date().isoformat()
    if isinstance(d, date):
        return d.isoformat()
    return d


def db_termin_to_dict(t):
    return {
        'id': t.id,
        'typ': t.typ,
        'titel': t.titel,
        'referenz': t.referenz,
        'start': _iso(t.start),
        'ende': _iso(t.ende),
        'text': t.text,
    }


def usb_termin_to_dict(t, idx):
    return {
        'id': 'usb-%d' % idx,
        'typ': t['typ'],
        'titel': t['titel'],
        'referenz': t['referenz'],
        'start': _iso(t['start']),
        'ende': _iso(t['ende']),
        'text': t['text'],
    }


def _sort_key(t):
    return (t['start'] is None, t['start'] or '')


def active_termine():
    """Bestimmt die aktive Quelle (auto/manual) und liefert alle Termine."""
    mode = get_mode()
    manual_source = get_manual_source()
    usb_dir = find_usb_termin_dir()
    usb_present = usb_dir is not None

    if mode == 'manual':
        source = manual_source
    else:
        source = 'usb' if usb_dir is not None else 'web'

    if source == 'usb':
        if usb_dir is not None:
            termine = [usb_termin_to_dict(t, i)
                       for i, t in enumerate(usb_termine(usb_dir))]
        else:
            termine = []  # manuell USB gewählt, aber kein Stick vorhanden
    else:
        termine = [db_termin_to_dict(t)
                   for t in Termin.query.order_by(Termin.start).all()]

    termine.sort(key=_sort_key)
    return {
        'source': source,
        'mode': mode,
        'manual_source': manual_source,
        'usb_present': usb_present,
        'termine': termine,
        'kalibrierungen': [t for t in termine if t['typ'] in ('kalibrierung', 'wartung')],
        'news': [t for t in termine if t['typ'] not in ('kalibrierung', 'wartung')],
    }


def azubi_image_urls():
    """Anzuzeigende Azubi-Bild-URLs vom Stick (nur im Zeitfenster)."""
    if not azubi_is_active():
        return []
    return [url_for('board_azubi_image', filename=f) for f in find_azubi_images()]


# ── Login ─────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Ungültige Anmeldedaten', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ── Dashboard ─────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    termine = [db_termin_to_dict(t)
               for t in Termin.query.order_by(Termin.start).all()]
    termine.sort(key=_sort_key)
    status = active_termine()
    azubi_start = get_azubi_start()
    azubi = {
        'start': azubi_start.isoformat() if azubi_start else '',
        'weeks': get_azubi_weeks(),
    }
    return render_template('dashboard.html', termine=termine, status=status, azubi=azubi)


@app.route('/termine')
@login_required
def termine_list():
    termine = [db_termin_to_dict(t)
               for t in Termin.query.order_by(Termin.start).all()]
    termine.sort(key=_sort_key)
    if is_ajax():
        return jsonify({'termine': termine})
    return redirect(url_for('dashboard'))


# ── Termin CRUD ──────────────────────────────────────────────────────

def _parse_form():
    typ = (request.form.get('typ') or '').strip().lower()
    if typ not in ALLOWED_TYPES:
        typ = 'info'
    titel = (request.form.get('titel') or '').strip()
    referenz = (request.form.get('referenz') or '').strip()
    start = parse_date(request.form.get('start'))
    ende = parse_date(request.form.get('ende'))
    text = (request.form.get('text') or '').strip() or None
    return typ, titel, referenz, start, ende, text


@app.route('/termine/create', methods=['POST'])
@login_required
def create_termin():
    typ, titel, referenz, start, ende, text = _parse_form()
    if not referenz:
        return ajax_or_redirect('', 'Bitte einen Prüfstand eingeben')
    if not titel:
        return ajax_or_redirect('', 'Bitte eine Info eingeben')
    if start is None:
        return ajax_or_redirect('', 'Bitte ein gültiges Startdatum angeben (TT.MM.JJJJ oder JJJJ-MM-TT)')
    t = Termin(typ=typ, titel=titel, referenz=referenz,
               start=start, ende=ende, text=text)
    db.session.add(t)
    db.session.commit()
    return ajax_or_redirect(f'Termin „{titel}“ angelegt')


@app.route('/termine/<int:id>/update', methods=['POST'])
@login_required
def update_termin(id):
    t = Termin.query.get_or_404(id)
    typ, titel, referenz, start, ende, text = _parse_form()
    if not referenz:
        return ajax_or_redirect('', 'Bitte einen Prüfstand eingeben')
    if not titel:
        return ajax_or_redirect('', 'Bitte eine Info eingeben')
    if start is None:
        return ajax_or_redirect('', 'Bitte ein gültiges Startdatum angeben (TT.MM.JJJJ oder JJJJ-MM-TT)')
    t.typ = typ
    t.titel = titel
    t.referenz = referenz
    t.start = start
    t.ende = ende
    t.text = text
    db.session.commit()
    return ajax_or_redirect(f'Termin „{titel}“ aktualisiert')


@app.route('/termine/<int:id>/delete', methods=['POST'])
@login_required
def delete_termin(id):
    t = Termin.query.get_or_404(id)
    db.session.delete(t)
    db.session.commit()
    return ajax_or_redirect('Termin gelöscht')


# ── Quelle (Auto/Manuell + Web/USB) ──────────────────────────────────

@app.route('/settings/source', methods=['GET', 'POST'])
@login_required
def settings_source():
    if request.method == 'POST':
        mode = (request.form.get('mode') or 'auto').strip()
        manual_source = (request.form.get('manual_source') or 'web').strip()
        if mode not in ('auto', 'manual'):
            mode = 'auto'
        if manual_source not in ('web', 'usb'):
            manual_source = 'web'
        set_setting(SETTING_MODE, mode)
        set_setting(SETTING_MANUAL_SOURCE, manual_source)
        return ajax_or_redirect('Quelle aktualisiert')
    return jsonify({'mode': get_mode(), 'manual_source': get_manual_source()})


@app.route('/settings/azubi', methods=['GET', 'POST'])
@login_required
def settings_azubi():
    if request.method == 'POST':
        start = (request.form.get('azubi_start') or '').strip()
        weeks = (request.form.get('azubi_weeks') or '2').strip()
        if start and parse_date(start) is None:
            return ajax_or_redirect('', 'Ungültiges Startdatum (TT.MM.JJJJ oder JJJJ-MM-TT)')
        try:
            w = int(weeks)
            if w < 0 or w > 104:
                raise ValueError
        except ValueError:
            return ajax_or_redirect('', 'Ungültige Wochenanzahl (0–104)')
        set_setting(SETTING_AZUBI_START, start)
        set_setting(SETTING_AZUBI_WEEKS, str(w))
        return ajax_or_redirect('Azubi-Einstellungen gespeichert')

    start = get_azubi_start()
    return jsonify({
        'start': start.isoformat() if start else '',
        'weeks': get_azubi_weeks(),
    })


# ── Kiosk (öffentlich) ───────────────────────────────────────────────

@app.route('/board/kiosk')
def board_kiosk():
    return render_template('board.html')


@app.route('/board/api/status')
def board_api_status():
    """Öffentliche API für den Kiosk (ohne Login)."""
    data = active_termine()
    data['azubi'] = azubi_image_urls()
    return jsonify(data)


@app.route('/board/azubi/<path:filename>')
def board_azubi_image(filename):
    """Liefert ein Azubi-Info-Bild vom Stick (nur Bild-Extensions, kein Pfad-Traversal)."""
    d = find_azubi_dir()
    if not d:
        return ('', 404)
    if os.path.splitext(filename)[1].lower() not in AZUBI_IMAGE_EXTS:
        return ('', 404)
    return send_from_directory(d, filename)
