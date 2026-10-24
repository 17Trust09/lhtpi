"""LHTPi Konfiguration."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Das Secret kommt ausschließlich aus der Umgebung (/etc/lhtpi/lhtpi.env, von
# install.sh geschrieben). Ein eingebauter Ersatzwert wäre im öffentlichen Repo
# nachlesbar — damit ließen sich Sitzungs-Cookies fälschen.
SECRET_KEY = (os.environ.get('LHTPI_SECRET') or '').strip()
if not SECRET_KEY or SECRET_KEY == 'lhtpi-dev-secret-change-me':
    raise SystemExit(
        'FEHLER: LHTPI_SECRET ist nicht gesetzt.\n'
        'Bitte in /etc/lhtpi/lhtpi.env hinterlegen (install.sh macht das) — '
        'siehe README, Abschnitt "Erstinbetriebnahme".'
    )

SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'lhtpi.db')
SQLALCHEMY_TRACK_MODIFICATIONS = False
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
MAX_CONTENT_LENGTH = 500 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4'}
