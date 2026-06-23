import os
import uuid
from datetime import datetime
from flask import (render_template, request, redirect, url_for,
                   send_from_directory, jsonify, abort, flash)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from app import app
from models import db, User, Media, Playlist, PlaylistItem

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4'}


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_mime(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return {
        'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
        'gif': 'image/gif', 'mp4': 'video/mp4',
    }.get(ext, 'application/octet-stream')


def get_type(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return 'video' if ext == 'mp4' else 'image'


def media_to_dict(media):
    """Serialisiert ein Medium für die Vanilla-JS-Oberfläche."""
    return {
        'id': media.id,
        'filename': media.filename,
        'original_name': media.original_name,
        'file_type': media.file_type,
        'mime_type': media.mime_type,
        'file_size': media.file_size,
        'uploaded_at': media.uploaded_at.isoformat() if media.uploaded_at else None,
        'url': url_for('uploaded_file', filename=media.filename),
    }


def playlist_item_to_dict(item):
    media = item.media
    return {
        'id': item.id,
        'media_id': item.media_id,
        'position': item.position,
        'display_duration': item.display_duration,
        'filename': media.filename,
        'file_type': media.file_type,
        'original_name': media.original_name,
        'url': url_for('uploaded_file', filename=media.filename),
    }


def playlist_to_dict(playlist):
    return {
        'id': playlist.id,
        'name': playlist.name,
        'is_active': playlist.is_active,
        'created_at': playlist.created_at.isoformat() if playlist.created_at else None,
        'items': [playlist_item_to_dict(item) for item in playlist.items],
    }


def is_ajax():
    """Prüft, ob die Anfrage per AJAX/Fetch erfolgt."""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('format') == 'json'


def ajax_or_redirect(success_message, error_message=None, redirect_to='playlist_list', status_code=200):
    """Ajax-Response mit Erfolgs-/Fehlermeldung oder Redirect."""
    if is_ajax():
        if error_message:
            return jsonify({'ok': False, 'message': error_message}), 400
        return jsonify({'ok': True, 'message': success_message})
    if error_message:
        flash(error_message, 'error')
    else:
        flash(success_message, 'success')
    return redirect(url_for(redirect_to))


def active_playlist_status():
    """Gemeinsamer Status für Dashboard und Kiosk.

    Der Kiosk hält seinen Player-Zustand im Browser. Für das Dashboard wird der
    aktuelle Index deshalb deterministisch aus den Item-Dauern berechnet. So ist
    der Status aussagekräftig, ohne eine Datenbank-Migration für Player-State zu
    benötigen.
    """
    active = Playlist.query.filter_by(is_active=True).first()
    if not active or not active.items:
        return {
            'active': False,
            'playlist_name': None,
            'items': [],
            'current_media': None,
            'current_item_index': None,
            'current_item': None,
            'remaining': 0,
            'status': 'Keine aktive Playlist'
        }

    items = [playlist_item_to_dict(item) for item in active.items]
    durations = [max(1, int(item.get('display_duration') or 10)) for item in items]
    total_duration = sum(durations) or 1
    elapsed = int(datetime.utcnow().timestamp()) % total_duration
    current_index = 0
    remaining = durations[0]
    passed = 0
    for idx, duration in enumerate(durations):
        if elapsed < passed + duration:
            current_index = idx
            remaining = (passed + duration) - elapsed
            break
        passed += duration

    return {
        'active': True,
        'playlist_name': active.name,
        'items': items,
        'current_media': items[current_index]['original_name'],
        'current_item_index': current_index,
        'current_item': items[current_index],
        'remaining': remaining,
        'status': 'Bereit'
    }


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


@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html')


# ── Medien ──────────────────────────────────────────────────────────────

@app.route('/media')
@login_required
def media_list():
    sort_by = request.args.get('sort', 'uploaded_at')
    order = request.args.get('order', 'desc')
    search = request.args.get('search', '').strip()

    query = Media.query
    if search:
        query = query.filter(Media.original_name.ilike(f'%{search}%'))

    allowed_sorts = {
        'uploaded_at': Media.uploaded_at,
        'original_name': Media.original_name,
        'file_type': Media.file_type,
    }
    sort_col = allowed_sorts.get(sort_by, Media.uploaded_at)
    if order == 'asc':
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    media = query.all()
    if request.args.get('format') == 'json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'media': [media_to_dict(item) for item in media],
            'count': len(media),
            'sort': sort_by,
            'order': order,
            'search': search,
        })
    return render_template('media.html', media=media, sort_by=sort_by, order=order, search=search)


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'file' not in request.files:
        return ajax_or_redirect('', 'Keine Datei ausgewählt', 'media_list')

    files = request.files.getlist('file')
    uploaded = 0
    errors = []
    for file in files:
        if file and file.filename:
            if not allowed_file(file.filename):
                errors.append(f'"{file.filename}": Nicht unterstütztes Format')
                continue
            ext = file.filename.rsplit('.', 1)[1].lower()
            unique_name = f"{uuid.uuid4()}.{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
            file.save(filepath)

            media = Media(
                filename=unique_name,
                original_name=secure_filename(file.filename),
                file_type=get_type(file.filename),
                mime_type=get_mime(file.filename),
                file_size=os.path.getsize(filepath),
                uploaded_at=datetime.utcnow()
            )
            db.session.add(media)
            uploaded += 1

    db.session.commit()
    parts = []
    if uploaded:
        parts.append(f'{uploaded} Datei(en) erfolgreich hochgeladen')
    for err in errors:
        parts.append(err)
    msg = '; '.join(parts)
    is_error = not uploaded
    return ajax_or_redirect(msg if not is_error else '', msg if is_error else None, 'media_list')


@app.route('/media/<int:id>/delete', methods=['POST'])
@login_required
def delete_media(id):
    media = Media.query.get_or_404(id)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], media.filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    # Remove from all playlists
    PlaylistItem.query.filter_by(media_id=id).delete()
    db.session.delete(media)
    db.session.commit()
    return ajax_or_redirect('Medium gelöscht', redirect_to='media_list')


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ── Playlists ───────────────────────────────────────────────────────────

@app.route('/playlists')
@login_required
def playlist_list():
    playlists = Playlist.query.order_by(Playlist.created_at.desc()).all()
    all_media = Media.query.order_by(Media.uploaded_at.desc()).all()
    if request.args.get('format') == 'json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'playlists': [playlist_to_dict(playlist) for playlist in playlists],
            'all_media': [media_to_dict(media) for media in all_media],
            'count': len(playlists),
        })
    return render_template('playlists.html', playlists=playlists, all_media=all_media)


@app.route('/playlists/create', methods=['POST'])
@login_required
def create_playlist():
    name = request.form.get('name', '').strip()
    if not name:
        return ajax_or_redirect('', 'Bitte einen Namen eingeben', 'playlist_list')
    if Playlist.query.filter_by(name=name).first():
        return ajax_or_redirect('', 'Eine Playlist mit diesem Namen existiert bereits', 'playlist_list')
    playlist = Playlist(name=name)
    db.session.add(playlist)
    db.session.commit()
    return ajax_or_redirect(f'Playlist "{name}" erstellt', redirect_to='playlist_list')


@app.route('/playlists/<int:id>/delete', methods=['POST'])
@login_required
def delete_playlist(id):
    playlist = Playlist.query.get_or_404(id)
    db.session.delete(playlist)
    db.session.commit()
    return ajax_or_redirect('Playlist gelöscht', redirect_to='playlist_list')


@app.route('/playlists/<int:id>/rename', methods=['POST'])
@login_required
def rename_playlist(id):
    playlist = Playlist.query.get_or_404(id)
    name = request.form.get('name', '').strip()
    if name and name != playlist.name:
        if Playlist.query.filter_by(name=name).first():
            return ajax_or_redirect('', 'Eine Playlist mit diesem Namen existiert bereits', 'playlist_list')
        playlist.name = name
        db.session.commit()
    return ajax_or_redirect('Playlist umbenannt', redirect_to='playlist_list')


@app.route('/playlists/<int:id>/activate', methods=['POST'])
@login_required
def activate_playlist(id):
    Playlist.query.update({Playlist.is_active: False})
    playlist = Playlist.query.get_or_404(id)
    playlist.is_active = True
    db.session.commit()
    return ajax_or_redirect(f'Playlist "{playlist.name}" ist jetzt aktiv', redirect_to='playlist_list')


@app.route('/playlists/<int:id>/add_media', methods=['POST'])
@login_required
def add_media_to_playlist(id):
    playlist = Playlist.query.get_or_404(id)
    media_id = request.form.get('media_id')
    if not media_id:
        return ajax_or_redirect('', 'Kein Medium ausgewählt', 'playlist_list')
    media = Media.query.get(int(media_id))
    if not media:
        return ajax_or_redirect('', 'Medium nicht gefunden', 'playlist_list')
    if PlaylistItem.query.filter_by(playlist_id=playlist.id, media_id=media.id).first():
        return ajax_or_redirect('', 'Medium ist bereits in dieser Playlist', 'playlist_list')
    max_pos = db.session.query(db.func.max(PlaylistItem.position))\
        .filter_by(playlist_id=playlist.id).scalar() or 0
    item = PlaylistItem(
        playlist_id=playlist.id,
        media_id=media.id,
        position=max_pos + 1
    )
    db.session.add(item)
    db.session.commit()
    return ajax_or_redirect('Medium hinzugefügt', redirect_to='playlist_list')


@app.route('/playlists/<int:playlist_id>/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_from_playlist(playlist_id, item_id):
    item = PlaylistItem.query.get_or_404(item_id)
    if item.playlist_id != playlist_id:
        return ajax_or_redirect('', 'Ungültiger Zugriff', 'playlist_list')
    db.session.delete(item)
    # Reorder positions
    remaining = PlaylistItem.query.filter_by(playlist_id=playlist_id)\
        .order_by(PlaylistItem.position).all()
    for i, rem in enumerate(remaining):
        rem.position = i
    db.session.commit()
    return ajax_or_redirect('Medium aus Playlist entfernt', redirect_to='playlist_list')


@app.route('/playlists/<int:id>/reorder', methods=['POST'])
@login_required
def reorder_playlist(id):
    data = request.get_json()
    if data and 'order' in data:
        order = data['order']
        for pos, item_id in enumerate(order):
            item = PlaylistItem.query.get(int(item_id))
            if item and item.playlist_id == id:
                item.position = pos
        db.session.commit()
    return jsonify({'status': 'ok'})


@app.route('/playlists/<int:id>/duration', methods=['POST'])
@login_required
def update_duration(id):
    data = request.get_json()
    if data and 'item_id' in data and 'duration' in data:
        item = PlaylistItem.query.get(int(data['item_id']))
        if item and item.playlist_id == id:
            item.display_duration = max(1, int(data['duration']))
            db.session.commit()
    return jsonify({'status': 'ok'})


# ── Präsentation / Kiosk (öffentlich) ─────────────────────────────────

@app.route('/present/api/status')
def present_api_status():
    """Öffentliche API für den Kiosk (ohne Login)."""
    return jsonify(active_playlist_status())


@app.route('/present/status')
@login_required
def present_status():
    """Authentifizierter Status für das Dashboard."""
    return jsonify(active_playlist_status())


@app.route('/present/kiosk')
def kiosk():
    return render_template('kiosk.html')
