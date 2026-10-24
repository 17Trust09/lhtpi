import os
from flask import Flask, redirect, url_for, request
from flask_login import LoginManager

app = Flask(__name__)


def _secret_key():
    """Sitzungs-Schlüssel aus der Umgebung — ohne Rückfall auf einen bekannten Wert.

    Ein fest eingebautes Secret wäre öffentlich bekannt (das Repo ist offen):
    damit ließen sich Anmelde-Cookies fremder Geräte fälschen.
    """
    wert = (os.environ.get('LHTPI_SECRET') or '').strip()
    if wert and wert != 'lhtpi-dev-secret-change-me':
        return wert
    raise SystemExit(
        'FEHLER: LHTPI_SECRET ist nicht gesetzt.\n'
        'Ohne eigenes Secret startet LHTPi nicht (sonst wären alle Anmelde-Cookies '
        'mit einem öffentlich bekannten Schlüssel signiert).\n'
        'Abhilfe: install.sh erneut ausführen, oder in der Dienst-Datei\n'
        '    EnvironmentFile=/etc/lhtpi/lhtpi.env\n'
        'mit LHTPI_SECRET=<mindestens 32 Zeichen> hinterlegen.'
    )


app.secret_key = _secret_key()
# DB-Pfad überschreibbar (Tests/mehrere Instanzen): LHTPI_DB=/pfad/datei.db
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.environ.get(
    'LHTPI_DB', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lhtpi.db')
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'mp4'}

from models import db
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))


# ── Zugang direkt am Gerät ───────────────────────────────────────────────────
# Der Kiosk-Bildschirm hat keine Tastatur. Aufrufe vom Gerät selbst (localhost,
# 127.0.0.1, ::1) gelten deshalb als angemeldet: die Anzeigen-Seite ist dort
# ohne Login erreichbar. Aus dem LAN bleibt der Login erforderlich.
# Abschaltbar über LHTPI_LOKAL_LOGIN=0.
LOKAL_LOGIN = os.environ.get('LHTPI_LOKAL_LOGIN', '1') != '0'


@app.before_request
def zugang_am_geraet():
    """Lokale Aufrufe ohne Anmeldung durchlassen (Anzeige am Bildschirm)."""
    from flask import request
    from flask_login import current_user, login_user
    from models import User
    if not LOKAL_LOGIN or current_user.is_authenticated:
        return None
    if request.remote_addr not in ('127.0.0.1', '::1'):
        return None
    user = User.query.filter_by(username='admin').first()
    if user is not None:
        login_user(user)
    return None


# Seiten, die auch mit offenem Passwortwechsel erreichbar bleiben
OFFENE_ENDPUNKTE = ('login', 'logout', 'passwort_aendern', 'static')


@app.before_request
def passwortwechsel_erzwingen():
    """Wer noch das Einmal-Token als Passwort hat, kommt nur zum Passwortwechsel.

    Am Gerät selbst (Anzeige, kein Tastatur-Anschluss) wird nicht eingegriffen —
    dort läuft der Kiosk mit dem lokalen Zugang.
    """
    from flask_login import current_user
    if not current_user.is_authenticated:
        return None
    if not getattr(current_user, 'must_change_password', False):
        return None
    if request.endpoint in OFFENE_ENDPUNKTE:
        return None
    if request.remote_addr in ('127.0.0.1', '::1'):
        return None
    return redirect(url_for('passwort_aendern'))


def _schema_ergaenzen():
    """Neue Spalten in bestehenden Datenbanken nachrüsten (create_all kann das nicht)."""
    from sqlalchemy import text
    with db.engine.connect() as verbindung:
        spalten = [zeile[1] for zeile in
                   verbindung.execute(text('PRAGMA table_info("user")'))]
        if spalten and 'must_change_password' not in spalten:
            verbindung.execute(text(
                'ALTER TABLE "user" ADD COLUMN must_change_password '
                'BOOLEAN NOT NULL DEFAULT 0'
            ))
            verbindung.commit()


with app.app_context():
    db.create_all()
    _schema_ergaenzen()
    # Zugang vorbereiten: kein Standardpasswort, sondern ein Einmal-Token
    from models import User
    import auth_setup
    _zugang = auth_setup.benutzer_vorbereiten(db, User)
    if _zugang.get('meldung'):
        print(_zugang['meldung'], flush=True)

from routes import *
from routes_kiosk import *          # Multitool-Kiosk: /screen/N, /display, /api/screens
from routes_license import *        # Lizenz: /lizenz + Sperrseite
from routes_diagnose import *       # Diagnose: /diagnose (nur mit Login, nur lesend)

with app.app_context():
    # Bildschirme beim Start sicherstellen (legt Default-Belegung an, wenn leer)
    import kiosk_router
    kiosk_router.ensure_defaults()

# Beim Start einmal aufräumen: Chromium soll keine alten Seiten wiederherstellen
# (sonst legt sich ein Fenster mit Browserleiste über die Anzeige). Darf den
# Start nie verhindern.
try:
    kiosk_router.sitzungen_verwerfen()
except Exception as fehler:                                  # noqa: BLE001
    print('Hinweis: Sitzungs-Aufräumen übersprungen (%s)' % fehler)

if __name__ == '__main__':
    import os
    port = int(os.environ.get('LHTPI_PORT', 8000))
    host = os.environ.get('LHTPI_HOST', '0.0.0.0')
    app.run(host=host, port=port, debug=False, use_reloader=False)
