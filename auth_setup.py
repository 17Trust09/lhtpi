"""Erstinbetriebnahme und Zugangsschutz für LHTPi.

Die App bringt **kein Standardpasswort** mehr mit. Beim ersten Start bekommt
der Benutzer ``admin`` ein zufälliges Einmal-Token. Es liegt auf dem Gerät in
``/etc/lhtpi/setup-token`` (Pfad über ``LHTPI_SETUP_TOKEN_FILE`` änderbar, Wert
auch direkt über ``LHTPI_SETUP_TOKEN``). Mit diesem Token meldet man sich
einmal an und setzt dabei ein eigenes Passwort; danach ist das Token wertlos
und die Datei wird entfernt.

Steht in der Datenbank noch das alte Standardpasswort (``admin``), ersetzt die
App es beim Start durch ein Einmal-Token. Damit ist der alte Zugang auch auf
schon installierten Geräten dicht, ohne dass ein bekanntes Passwort bleibt.
"""
import os
import secrets

STANDARD_TOKEN_DATEI = '/etc/lhtpi/setup-token'
TOKEN_BYTES = 24                       # token_urlsafe(24) -> 32 Zeichen
MIN_PASSWORT_LAENGE = 12

# Passwörter, die früher als Standard gesetzt wurden und nie wieder gelten
BEKANNTE_STANDARDPASSWOERTER = ('admin', 'lhtpi', 'passwort', 'password')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def token_pfade():
    """Mögliche Ablageorte für das Einmal-Token, in dieser Reihenfolge."""
    pfade = [os.environ.get('LHTPI_SETUP_TOKEN_FILE') or STANDARD_TOKEN_DATEI]
    pfade.append(os.path.join(BASE_DIR, '.setup-token'))
    return pfade


def token_datei():
    """Der vorgesehene Ablageort (erster Pfad)."""
    return token_pfade()[0]


def token_aus_umgebung():
    return (os.environ.get('LHTPI_SETUP_TOKEN') or '').strip()


def token_lesen():
    """Vorhandenes Token aus Umgebung oder Datei; ``None``, wenn keins da ist."""
    token = token_aus_umgebung()
    if token:
        return token
    for pfad in token_pfade():
        try:
            with open(pfad, 'r', encoding='utf-8') as datei:
                wert = datei.read().strip()
        except OSError:
            continue
        if wert:
            return wert
    return None


def token_schreiben(token, pfad=None):
    """Legt das Token mit Rechten 0600 ab und gibt den Pfad zurück."""
    kandidaten = [pfad] if pfad else token_pfade()
    letzter_fehler = None
    for ziel in kandidaten:
        try:
            ordner = os.path.dirname(ziel)
            if ordner:
                os.makedirs(ordner, mode=0o750, exist_ok=True)
            # erst mit 0600 anlegen, damit das Token nie offen auf der Platte liegt
            dateinummer = os.open(ziel, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(dateinummer, 'w', encoding='utf-8') as datei:
                datei.write(token + '\n')
            os.chmod(ziel, 0o600)
            return ziel
        except OSError as fehler:      # noqa: PERF203 — nächster Ort versuchen
            letzter_fehler = fehler
    raise OSError('Kein Ort für das Einmal-Token beschreibbar: %s' % letzter_fehler)


def token_entfernen():
    """Löscht das Einmal-Token (nach dem ersten Passwortwechsel)."""
    entfernt = False
    for pfad in token_pfade():
        try:
            os.remove(pfad)
            entfernt = True
        except OSError:
            continue
    return entfernt


def neues_token():
    return secrets.token_urlsafe(TOKEN_BYTES)


def passwort_pruefen(passwort, token=None):
    """Prüft ein neues Passwort. Gibt eine Fehlermeldung oder ``None`` zurück."""
    passwort = passwort or ''
    if passwort != passwort.strip():
        return 'Das Passwort darf nicht mit Leerzeichen beginnen oder enden'
    if passwort.lower() in BEKANNTE_STANDARDPASSWOERTER:
        return 'Dieses Passwort ist ein bekannter Standardwert'
    if token and passwort == token:
        return 'Das Einmal-Token taugt nicht als dauerhaftes Passwort'
    if len(passwort) < MIN_PASSWORT_LAENGE:
        return 'Das Passwort braucht mindestens %d Zeichen' % MIN_PASSWORT_LAENGE
    return None


def benutzer_vorbereiten(db, User):
    """Sorgt beim Start für einen ``admin`` ohne bekanntes Passwort.

    Rückgabe: ``{'aktion': 'neu'|'token_ersetzt'|'unveraendert',
    'token_datei': <pfad oder None>, 'meldung': <Textzeile fürs Journal>}``.
    """
    admin = User.query.filter_by(username='admin').first()
    if admin is not None and not any(
            admin.check_password(p) for p in BEKANNTE_STANDARDPASSWOERTER):
        return {'aktion': 'unveraendert', 'token_datei': token_datei(), 'meldung': ''}

    aktion = 'neu' if admin is None else 'token_ersetzt'
    if admin is None:
        admin = User(username='admin')
        db.session.add(admin)

    # Ein von außen vorgegebenes Token (install.sh) hat Vorrang
    token = token_lesen()
    pfad = token_datei() if token else None
    if not token:
        token = neues_token()
        pfad = token_schreiben(token)

    admin.set_password(token)
    admin.must_change_password = True
    db.session.commit()

    if aktion == 'neu':
        meldung = ('Erstinbetriebnahme: Benutzer "admin" angelegt. Einmal-Token in %s — '
                   'damit einmal anmelden und ein eigenes Passwort setzen.' % pfad)
    else:
        meldung = ('Sicherheit: das Standardpasswort von "admin" wurde ersetzt. '
                   'Einmal-Token in %s — damit einmal anmelden und ein eigenes '
                   'Passwort setzen.' % pfad)
    return {'aktion': aktion, 'token_datei': pfad, 'meldung': meldung}
