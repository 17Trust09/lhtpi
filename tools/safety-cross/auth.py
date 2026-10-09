"""Passwort-Hashing und Login-Schutz (Admin-Bereich)."""
from functools import wraps

from flask import session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

import db


def hash_password(password):
    return generate_password_hash(password)


def verify_password(password, password_hash):
    return check_password_hash(password_hash, password)


def init_admin_password(password="admin"):
    """Setzt das Admin-Passwort, falls noch keins hinterlegt ist."""
    if db.get_config("admin_password") is None:
        db.set_config("admin_password", hash_password(password))


def check_login(password):
    stored = db.get_config("admin_password")
    return bool(stored) and verify_password(password, stored)


def set_password(new_password):
    db.set_config("admin_password", hash_password(new_password))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped
