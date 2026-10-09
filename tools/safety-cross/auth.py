"""Passwort-Hashing und Login-Schutz (Admin-Bereich)."""
from functools import wraps

from flask import request, session, redirect, url_for
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


LOKALE_ADRESSEN = {"127.0.0.1", "::1", "localhost"}


def ist_lokal():
    """Zugriff vom Geraet selbst (Kiosk) - dort ist keine Anmeldung moeglich.

    Am Bildschirm gibt es keine Tastatur. Aus dem Netzwerk bleibt die
    Anmeldung Pflicht, am Geraet selbst gilt der Zugriff als angemeldet.
    """
    return (request.remote_addr or "") in LOKALE_ADRESSEN


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if ist_lokal() or session.get("logged_in"):
            return view(*args, **kwargs)
        return redirect(url_for("login"))

    return wrapped
