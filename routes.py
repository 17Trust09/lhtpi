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

    sort_col = getattr(Media, sort_by, Media.uploaded_at)
    if order == 'asc':
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    media = query.all()
    return render_template('media.html', media=media, sort_by=sort_by, order=order, search=search)


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt', 'error')
        return redirect(url_for('media_list'))

    files = request.files.getlist('file')
    uploaded = 0
    for file in files:
        if file and file.filename and allowed_file(file.filename):
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
    flash(f'{uploaded} Datei(en) erfolgreich hochgeladen', 'success')
    return redirect(url_for('media_list'))


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
    flash('Medium gelöscht', 'success')
    return redirect(url_for('media_list'))


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ── Playlists ───────────────────────────────────────────────────────────

@app.route('/playlists')
@login_required
def playlist_list():
    playlists = Playlist.query.order_by(Playlist.created_at.desc()).all()
    all_media = Media.query.order_by(Media.uploaded_at.desc()).all()
    return render_template('playlists.html', playlists=playlists, all_media=all_media)


@app.route('/playlists/create', methods=['POST'])
@login_required
def create_playlist():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Bitte einen Namen eingeben', 'error')
        return redirect(url_for('playlist_list'))
    if Playlist.query.filter_by(name=name).first():
        flash('Eine Playlist mit diesem Namen existiert bereits', 'error')
        return redirect(url_for('playlist_list'))
    playlist = Playlist(name=name)
    db.session.add(playlist)
    db.session.commit()
    flash(f'Playlist "{name}" erstellt', 'success')
    return redirect(url_for('playlist_list'))


@app.route('/playlists/<int:id>/delete', methods=['POST'])
@login_required
def delete_playlist(id):
    playlist = Playlist.query.get_or_404(id)
    db.session.delete(playlist)
    db.session.commit()
    flash('Playlist gelöscht', 'success')
    return redirect(url_for('playlist_list'))


@app.route('/playlists/<int:id>/rename', methods=['POST'])
@login_required
def rename_playlist(id):
    playlist = Playlist.query.get_or_404(id)
    name = request.form.get('name', '').strip()
    if name and name != playlist.name:
        if Playlist.query.filter_by(name=name).first():
            flash('Eine Playlist mit diesem Namen existiert bereits', 'error')
            return redirect(url_for('playlist_list'))
        playlist.name = name
        db.session.commit()
    return redirect(url_for('playlist_list'))


@app.route('/playlists/<int:id>/activate', methods=['POST'])
@login_required
def activate_playlist(id):
    Playlist.query.update({Playlist.is_active: False})
    playlist = Playlist.query.get_or_404(id)
    playlist.is_active = True
    db.session.commit()
    flash(f'Playlist "{playlist.name}" ist jetzt aktiv', 'success')
    return redirect(url_for('playlist_list'))


@app.route('/playlists/<int:id>/add_media', methods=['POST'])
@login_required
def add_media_to_playlist(id):
    playlist = Playlist.query.get_or_404(id)
    media_id = request.form.get('media_id')
    if media_id:
        media = Media.query.get(int(media_id))
        if media:
            max_pos = db.session.query(db.func.max(PlaylistItem.position))\
                .filter_by(playlist_id=playlist.id).scalar() or 0
            item = PlaylistItem(
                playlist_id=playlist.id,
                media_id=media.id,
                position=max_pos + 1
            )
            db.session.add(item)
            db.session.commit()
    return redirect(url_for('playlist_list'))


@app.route('/playlists/<int:playlist_id>/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_from_playlist(playlist_id, item_id):
    item = PlaylistItem.query.get_or_404(item_id)
    if item.playlist_id != playlist_id:
        abort(403)
    db.session.delete(item)
    # Reorder positions
    remaining = PlaylistItem.query.filter_by(playlist_id=playlist_id)\
        .order_by(PlaylistItem.position).all()
    for i, rem in enumerate(remaining):
        rem.position = i
    db.session.commit()
    return redirect(url_for('playlist_list'))


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
    """Öffentliche API für den Kiosk (ohne Login)"""
    active = Playlist.query.filter_by(is_active=True).first()
    if not active or not active.items:
        return jsonify({
            'active': False,
            'current_media': None,
            'remaining': 0,
            'status': 'Keine aktive Playlist'
        })

    items = []
    for item in active.items:
        items.append({
            'id': item.id,
            'media_id': item.media_id,
            'filename': item.media.filename,
            'file_type': item.media.file_type,
            'display_duration': item.display_duration,
            'original_name': item.media.original_name,
        })

    return jsonify({
        'active': True,
        'playlist_name': active.name,
        'items': items,
        'status': 'Bereit'
    })


@app.route('/present/status')
@login_required
def present_status():
    active = Playlist.query.filter_by(is_active=True).first()
    if not active or not active.items:
        return jsonify({
            'active': False,
            'current_media': None,
            'remaining': 0,
            'status': 'Keine aktive Playlist'
        })

    # Return playlist info for frontend to control playback
    items = []
    for item in active.items:
        items.append({
            'id': item.id,
            'media_id': item.media_id,
            'filename': item.media.filename,
            'file_type': item.media.file_type,
            'display_duration': item.display_duration,
            'original_name': item.media.original_name,
        })

    return jsonify({
        'active': True,
        'playlist_name': active.name,
        'items': items,
        'status': 'Bereit'
    })


@app.route('/present/kiosk')
def kiosk():
    return render_template('kiosk.html')
