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


class Termin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    typ = db.Column(db.String(20), nullable=False, default='info')
    titel = db.Column(db.String(200), nullable=False)
    referenz = db.Column(db.String(100))
    start = db.Column(db.Date, nullable=False)
    ende = db.Column(db.Date)
    text = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Setting(db.Model):
    """Einfacher Key/Value-Speicher für App-weite Einstellungen."""
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.String(200), nullable=False, default='')
