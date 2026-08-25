import os
from flask import Flask
from flask_login import LoginManager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.secret_key = os.environ.get('TERMINBOARD_SECRET', 'terminboard-dev-secret-change-me')

_db_name = os.environ.get('TERMINBOARD_DB', 'terminboard.db')
_db_path = _db_name if os.path.isabs(_db_name) else os.path.join(BASE_DIR, _db_name)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + _db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
    from models import User
    if not User.query.filter_by(username='admin').first():
        user = User(username='admin')
        user.set_password('admin')
        db.session.add(user)
        db.session.commit()

from routes import *

if __name__ == '__main__':
    port = int(os.environ.get('TERMINBOARD_PORT', 8001))
    host = os.environ.get('TERMINBOARD_HOST', '0.0.0.0')
    app.run(host=host, port=port, debug=False, use_reloader=False)
