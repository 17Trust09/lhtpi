#!/usr/bin/env python3
"""Einmal-Token für den Admin-Zugang ansehen oder neu setzen.

    ./venv/bin/python setup_token.py            # wo liegt das Token?
    ./venv/bin/python setup_token.py --neu      # neues Token, Wechsel erzwungen

``--neu`` ist der Weg zurück, wenn das Passwort unbekannt ist: das Token wird
neu erzeugt, ``admin`` bekommt es als Passwort und muss es beim nächsten Login
ändern. Das alte Passwort wird dabei ersetzt — das Gerät ist danach nur noch
mit dem neuen Token erreichbar.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def main(argv):
    neu = '--neu' in argv[1:]

    # Import der App legt Tabellen an und prüft das Secret (LHTPI_SECRET)
    from app import app                                   # noqa: F401  (Seiteneffekt)
    from models import db, User
    import auth_setup

    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        if admin is None:
            print('Benutzer "admin" fehlt — beim nächsten Start legt die App ihn an.')
            return 0

        if neu:
            token = auth_setup.neues_token()
            pfad = auth_setup.token_schreiben(token)
            admin.set_password(token)
            admin.must_change_password = True
            db.session.commit()
            print('Neues Einmal-Token gesetzt (Datei %s, Rechte 0600):' % pfad)
            print('    %s' % token)
            print('Benutzer: admin — beim Anmelden wird sofort ein eigenes Passwort verlangt.')
            return 0

        token = auth_setup.token_lesen()
        if admin.must_change_password and token:
            print('Einmal-Token liegt in %s:' % auth_setup.token_datei())
            print('    %s' % token)
        elif admin.must_change_password:
            print('Ein Passwortwechsel ist offen, aber kein Token gefunden.')
            print('Neu setzen mit: %s %s --neu' % (sys.executable, os.path.basename(__file__)))
        else:
            print('Kein offener Setup-Vorgang: der Zugang hat ein eigenes Passwort.')
            print('Neu setzen mit: %s %s --neu' % (sys.executable, os.path.basename(__file__)))
        return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
