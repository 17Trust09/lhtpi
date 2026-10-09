from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)


class Media(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    original_name = db.Column(db.String(200), nullable=False)
    file_type = db.Column(db.String(10), nullable=False)  # image / video
    mime_type = db.Column(db.String(50), nullable=False)
    file_size = db.Column(db.Integer, default=0)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class Playlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('PlaylistItem', back_populates='playlist',
                            order_by='PlaylistItem.position', cascade='all, delete-orphan')


class PlaylistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    playlist_id = db.Column(db.Integer, db.ForeignKey('playlist.id'), nullable=False)
    media_id = db.Column(db.Integer, db.ForeignKey('media.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    display_duration = db.Column(db.Integer, default=10)  # seconds
    playlist = db.relationship('Playlist', back_populates='items')
    media = db.relationship('Media')


class Setting(db.Model):
    """Einfacher Key/Value-Speicher für App-weite Einstellungen."""
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.String(200), nullable=False, default='')


class KioskScreen(db.Model):
    """Ein Bildschirm-Ausgang (HDMI) des Geräts.

    ``idx`` bestimmt die Router-URL ``/screen/<idx>`` und entspricht dem
    Kiosk-Service ``kiosk-screen<idx>.service``.
    """
    __tablename__ = 'kiosk_screen'
    id = db.Column(db.Integer, primary_key=True)
    idx = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(80), default='')
    hdmi = db.Column(db.String(20), default='')
    enabled = db.Column(db.Boolean, default=True)
    tools = db.relationship('KioskScreenTool', back_populates='screen',
                            order_by='KioskScreenTool.sort',
                            cascade='all, delete-orphan')


class KioskScreenTool(db.Model):
    """Belegung eines Bildschirms mit einem Tool (mit Anzeigedauer).

    Ein Eintrag pro Bildschirm = festes Tool, mehrere Einträge = Rotation.
    """
    __tablename__ = 'kiosk_screen_tool'
    __table_args__ = (db.UniqueConstraint('screen_id', 'tool', name='uq_screen_tool'),)
    id = db.Column(db.Integer, primary_key=True)
    screen_id = db.Column(db.Integer, db.ForeignKey('kiosk_screen.id'), nullable=False)
    tool = db.Column(db.String(40), nullable=False)
    dwell_seconds = db.Column(db.Integer, default=20)
    sort = db.Column(db.Integer, default=0)
    enabled = db.Column(db.Boolean, default=True)
    screen = db.relationship('KioskScreen', back_populates='tools')
