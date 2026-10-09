import os
from flask import Flask
from flask_login import LoginManager

app = Flask(__name__)
app.secret_key = os.environ.get('LHTPI_SECRET', 'lhtpi-dev-secret-change-me')
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

with app.app_context():
    db.create_all()
    # Default-Admin-Benutzer anlegen (falls nicht vorhanden)
    from models import User
    if not User.query.filter_by(username='admin').first():
        user = User(username='admin')
        user.set_password('admin')
        db.session.add(user)
        db.session.commit()

from routes import *
from routes_kiosk import *          # Multitool-Kiosk: /screen/N, /display, /api/screens
from routes_license import *        # Lizenz: /lizenz + Sperrseite

with app.app_context():
    # Bildschirme beim Start sicherstellen (legt Default-Belegung an, wenn leer)
    import kiosk_router
    kiosk_router.ensure_defaults()

if __name__ == '__main__':
    import os
    port = int(os.environ.get('LHTPI_PORT', 8000))
    host = os.environ.get('LHTPI_HOST', '0.0.0.0')
    app.run(host=host, port=port, debug=False, use_reloader=False)
