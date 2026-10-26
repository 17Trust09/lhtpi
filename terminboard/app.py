import os
from flask import Flask
from flask_login import LoginManager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Daten liegen außerhalb des Programmverzeichnisses (überleben Updates)
DATA_DIR = os.environ.get('LHTPI_DATA_DIR', '/var/lib/lhtpi')

app = Flask(__name__)
app.secret_key = os.environ.get('TERMINBOARD_SECRET', 'terminboard-dev-secret-change-me')


def _db_pfad():
    env = os.environ.get('TERMINBOARD_DB')
    if env:
        return env if os.path.isabs(env) else os.path.join(BASE_DIR, env)
    neu = os.path.join(DATA_DIR, 'terminboard', 'terminboard.db')
    alt = os.path.join(BASE_DIR, 'terminboard.db')
    if os.path.exists(neu):
        return neu
    if os.path.exists(alt):
        return alt          # Migration noch nicht gelaufen
    os.makedirs(os.path.dirname(neu), exist_ok=True)
    return neu


app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + _db_pfad()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Web-Requests und Stick-Import schreiben parallel: lieber warten als
# sofort mit "database is locked" abzubrechen.
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': {'timeout': 30}}
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True

from models import db
import historie  # noqa: F401 – registriert die Historien-Tabellen für create_all
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    from models import User
    return db.session.get(User, int(user_id))


with app.app_context():
    db.create_all()
    from models import User
    if not User.query.filter_by(username='admin').first():
        user = User(username='admin')
        user.set_password('admin')
        db.session.add(user)
        db.session.commit()

from routes import *

# Stick-Verarbeitung im Hintergrund: importiert eine neue termine.xlsx und
# löst Berichte aus, wenn LHTPi-Bericht.jetzt auf dem Stick liegt.
# Abschaltbar für Tests und Sonderfälle: TERMINBOARD_WATCHER=0
if os.environ.get('TERMINBOARD_WATCHER', '1') != '0':
    from stick_watcher import starte_hintergrundpruefung
    starte_hintergrundpruefung(app)

if __name__ == '__main__':
    port = int(os.environ.get('TERMINBOARD_PORT', 8001))
    host = os.environ.get('TERMINBOARD_HOST', '0.0.0.0')
    app.run(host=host, port=port, debug=False, use_reloader=False)
