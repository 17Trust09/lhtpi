"""LHTPi Konfiguration.

Daten (Datenbank, Uploads) liegen NICHT im Programmverzeichnis, sondern unter
DATA_DIR – damit ein Update den Programmstand austauschen kann, ohne Daten zu
verlieren. Standard: /var/lib/lhtpi, überschreibbar mit LHTPI_DATA_DIR.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Zentrales Datenverzeichnis (überlebt Updates)
DATA_DIR = os.environ.get('LHTPI_DATA_DIR', '/var/lib/lhtpi')


def daten_datei(unterordner, name, alt=None):
    """Pfad für eine Datendatei.

    Reihenfolge:
      1. Datei existiert unter DATA_DIR  -> nehmen
      2. Datei existiert am alten Ort    -> nehmen (Migration noch nicht gelaufen)
      3. sonst                           -> neuer Pfad (Ordner wird angelegt)
    """
    neu = os.path.join(DATA_DIR, unterordner, name)
    if os.path.exists(neu):
        return neu
    if alt and os.path.exists(alt):
        return alt
    ordner = os.path.dirname(neu)
    if ordner:
        os.makedirs(ordner, exist_ok=True)
    return neu


def daten_ordner(unterordner, alt=None):
    """Pfad für ein Datenverzeichnis (z. B. uploads)."""
    neu = os.path.join(DATA_DIR, unterordner) if unterordner else DATA_DIR
    if os.path.isdir(neu) and os.listdir(neu):
        return neu
    if alt and os.path.isdir(alt):
        return alt
    os.makedirs(neu, exist_ok=True)
    return neu


SECRET_KEY = os.environ.get('LHTPI_SECRET', 'lhtpi-dev-secret-change-me')
SQLALCHEMY_DATABASE_URI = 'sqlite:///' + daten_datei(
    'app', 'lhtpi.db', os.path.join(BASE_DIR, 'lhtpi.db'))
SQLALCHEMY_TRACK_MODIFICATIONS = False
UPLOAD_FOLDER = daten_ordner('uploads', os.path.join(BASE_DIR, 'uploads'))
MAX_CONTENT_LENGTH = 500 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4'}
