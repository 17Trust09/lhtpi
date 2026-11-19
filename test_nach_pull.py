"""Fokussierte Tests für scripts/nach-pull.sh (eine git-pull-Aktualisierung).

Ohne echtes systemd/sudo: die Systemkommandos ``sudo`` und ``curl`` werden
durch Stubs in einem eigenen ``bin/``-Ordner ersetzt. Git läuft echt, damit
``git diff HEAD@{1} HEAD`` wie im post-merge-Haken funktioniert.

Die DB-Sicherung läuft seit dem Umbau über den Root-Helfer
``/usr/local/sbin/lhtpi-terminboard-backup`` (via ``sudo -n``). Hier wird
geprüft, DASS der Helfer aufgerufen wird (und bei dessen Fehlschlag kein
Neustart erfolgt) - die Sicherungslogik selbst testet
``test_terminboard_db_backup.py``.

Die DB-Erkennung verwendet feste Produktionspfade (kein TERMINBOARD_DB, kein
LHTPI_DATA_DIR). Da diese Pfade (/var/lib/lhtpi, /home/pi) hier nicht
beschreibbar sind, wird eine temporäre Kopie des Skripts erzeugt, in der die
beiden festen Pfade auf Test-Pfade umgeschrieben werden - die Logik selbst
(primär → legacy → keine DB) bleibt unverändert.

Aufruf:
    python3 test_nach_pull.py
"""
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SKRIPT = REPO_ROOT / 'scripts' / 'nach-pull.sh'
HELFER_PFAD = '/usr/local/sbin/lhtpi-terminboard-backup'

# Feste Produktionspfade - identisch zu nach-pull.sh und zum Root-Helfer.
PRIMAER_PROD = '/var/lib/lhtpi/terminboard/terminboard.db'
LEGACY_PROD = '/home/pi/lhtpi/terminboard/terminboard.db'

passed = 0
failed = 0


def ok(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print('  ok  %s' % msg)
    else:
        failed += 1
        print('  FEHLER  %s' % msg)


def _schreibe_stub(ordner, name, body):
    p = ordner / name
    p.write_text(body)
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def _installkopie(basis, primaer, legacy):
    """Temporäre Kopie von nach-pull.sh mit auf Test-Pfade umgeschriebenen DB-Pfaden."""
    text = SKRIPT.read_text(encoding='utf-8')
    # Regression: die Produktion MUSS die festen Pfade verwenden.
    assert PRIMAER_PROD in text, 'primärer Produktionspfad fehlt im Skript'
    assert LEGACY_PROD in text, 'Legacy-Produktionspfad fehlt im Skript'
    text = text.replace(PRIMAER_PROD, str(primaer))
    text = text.replace(LEGACY_PROD, str(legacy))
    kopie = basis / 'nach-pull.sh'
    kopie.write_text(text)
    kopie.chmod(kopie.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return kopie


def _buehne():
    """Baut ein temporäres Git-Repo mit zwei Commits plus Kommando-Stubs."""
    basis = Path(tempfile.mkdtemp(prefix='nachpull-'))
    repo = basis / 'repo'
    repo.mkdir()
    (repo / 'terminboard').mkdir()
    (repo / 'terminboard' / 'app.py').write_text('# ALT\n')
    (repo / 'terminboard' / 'requirements.txt').write_text('flask\n')
    (repo / 'scripts').mkdir()
    # nach-pull.sh wird nicht ins Repo kopiert – die temporäre Kopie wird
    # direkt aufgerufen, aber REPO muss auf das temporäre Repo zeigen. Deshalb
    # rufen wir das Skript mit cwd=repo auf; git rev-parse liefert dann repo.
    subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.email', 't@t'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.name', 't'], cwd=repo, check=True)
    subprocess.run(['git', 'add', '-A'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-qm', 'init'], cwd=repo, check=True)

    # Stubs für sudo/curl (pip wird im venv des temporären Repos angelegt).
    bin_dir = basis / 'bin'
    bin_dir.mkdir()
    sudo_log = basis / 'sudo.log'
    curl_log = basis / 'curl.log'
    _schreibe_stub(bin_dir, 'sudo', '''#!/bin/bash\necho "$*" >> "$SUDO_LOG"\nexit "${SUDO_EXIT:-0}"\n''')
    # curl zählt Aufrufe mit und kann die ersten N fehlschlagen lassen (für den
    # Healthcheck-Retry-Test), sonst gilt CURL_EXIT.
    _schreibe_stub(bin_dir, 'curl', '''#!/bin/bash\necho "$*" >> "$CURL_LOG"\nn=$(wc -l < "$CURL_LOG" 2>/dev/null || echo 0)\nif [ -n "${CURL_FAIL_BIS:-}" ] && [ "$n" -le "${CURL_FAIL_BIS}" ]; then exit 1; fi\nexit "${CURL_EXIT:-0}"\n''')

    venv_bin = repo / 'terminboard' / 'venv' / 'bin'
    venv_bin.mkdir(parents=True)
    pip_log = basis / 'pip.log'
    _schreibe_stub(venv_bin, 'pip', '''#!/bin/bash\necho "$*" >> "$PIP_LOG"\nexit "${PIP_EXIT:-0}"\n''')

    logs = {'sudo': sudo_log, 'curl': curl_log, 'pip': pip_log}

    # Temporäre Installations-Kopie mit Test-Pfaden für die DB-Erkennung.
    primaer = basis / 'primär' / 'terminboard' / 'terminboard.db'
    legacy = basis / 'legacy' / 'terminboard' / 'terminboard.db'
    skript = _installkopie(basis, primaer, legacy)

    return basis, repo, bin_dir, logs, skript, primaer, legacy


def _lege_db_an(pfad):
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text('LIVE-DB-INHALT\n')


def _umgebung(basis, bin_dir, logs, curl_exit='0', sudo_exit='0', pip_exit='0'):
    env = dict(os.environ)
    env['PATH'] = str(bin_dir) + os.pathsep + env['PATH']
    env['SUDO_LOG'] = str(logs['sudo'])
    env['CURL_LOG'] = str(logs['curl'])
    env['PIP_LOG'] = str(logs['pip'])
    env['CURL_EXIT'] = curl_exit
    env['SUDO_EXIT'] = sudo_exit
    env['PIP_EXIT'] = pip_exit
    return env


def _aenderung(repo, dateien):
    """Zweiter Commit: die genannten Dateien ändern/ergänzen."""
    for rel, inhalt in dateien.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(inhalt)
    subprocess.run(['git', 'add', '-A'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-qm', 'change'], cwd=repo, check=True)


def _sudo_aufrufe(logs):
    return logs['sudo'].read_text() if os.path.exists(logs['sudo']) else ''


def _curl_aufrufe(logs):
    return logs['curl'].read_text() if os.path.exists(logs['curl']) else ''


# ── Syntax ─────────────────────────────────────────────────────────────

r = subprocess.run(['bash', '-n', str(SKRIPT)], capture_output=True)
ok(r.returncode == 0, 'nach-pull.sh ist syntaktisch gültig')


# ── Ablauf: requirements → Sicherung (sudo-Helfer) → Neustart → Healthcheck ─

basis, repo, bin_dir, logs, skript, primaer, legacy = _buehne()
_lege_db_an(primaer)
_aenderung(repo, {
    'terminboard/requirements.txt': 'flask\nfpdf2\n',
    'terminboard/app.py': '# NEU\n',
})
env = _umgebung(basis, bin_dir, logs)
r = subprocess.run(['bash', str(skript)], cwd=repo, env=env,
                   capture_output=True, text=True)
ok(r.returncode == 0, 'Pull-Nachzug endet erfolgreich (%s)' % r.returncode)

pip_aufruf = logs['pip'].read_text() if os.path.exists(logs['pip']) else ''
ok('install -r' in pip_aufruf and 'requirements.txt' in pip_aufruf,
   'Abhängigkeiten werden nach requirements-Änderung installiert')

sudo_aufruf = _sudo_aufrufe(logs)
ok(HELFER_PFAD in sudo_aufruf,
   'DB-Sicherung wird über den Root-Helfer aufgerufen (sudo -n)')
ok('systemctl restart terminboard.service' in sudo_aufruf,
   'Terminboard-Dienst wird neu gestartet')

curl_aufruf = _curl_aufrufe(logs)
ok('/login' in curl_aufruf and '/board/api/status' in curl_aufruf,
   'Healthcheck prüft /login und /board/api/status')


# ── Ohne requirements-Änderung wird pip übersprungen ───────────────────

basis, repo, bin_dir, logs, skript, primaer, legacy = _buehne()
_lege_db_an(primaer)
_aenderung(repo, {'terminboard/app.py': '# NUR APP\n'})
env = _umgebung(basis, bin_dir, logs)
r = subprocess.run(['bash', str(skript)], cwd=repo, env=env,
                   capture_output=True, text=True)
pip_log = logs['pip'].read_text() if os.path.exists(logs['pip']) else ''
ok(r.returncode == 0 and pip_log == '',
   'Ohne requirements-Änderung wird pip nicht aufgerufen')
ok(HELFER_PFAD in _sudo_aufrufe(logs),
   'DB-Sicherung läuft trotzdem (auch ohne requirements-Änderung)')


# ── Fehlschlag der DB-Sicherung verhindert den Neustart ────────────────

basis, repo, bin_dir, logs, skript, primaer, legacy = _buehne()
_lege_db_an(primaer)
_aenderung(repo, {'terminboard/app.py': '# NEU\n'})
env = _umgebung(basis, bin_dir, logs, sudo_exit='1')
r = subprocess.run(['bash', str(skript)], cwd=repo, env=env,
                   capture_output=True, text=True)
ok(r.returncode != 0, 'Fehlschlag der DB-Sicherung bricht den Pull ab (rc=%s)'
   % r.returncode)
ok('systemctl restart terminboard.service' not in _sudo_aufrufe(logs),
   'bei fehlgeschlagener Sicherung wird nicht neu gestartet')


# ── Keine Live-DB: kein Sicherungs-Aufruf, Neustart trotzdem ───────────

basis, repo, bin_dir, logs, skript, primaer, legacy = _buehne()
_aenderung(repo, {'terminboard/app.py': '# NEU\n'})
env = _umgebung(basis, bin_dir, logs)
r = subprocess.run(['bash', str(skript)], cwd=repo, env=env,
                   capture_output=True, text=True)
ok(r.returncode == 0, 'ohne Live-DB endet der Nachzug trotzdem erfolgreich')
ok(HELFER_PFAD not in _sudo_aufrufe(logs),
   'ohne Live-DB wird der Sicherungs-Helfer nicht aufgerufen')
ok('systemctl restart terminboard.service' in _sudo_aufrufe(logs),
   'der Neustart erfolgt auch ohne Sicherung')


# ── Nur Legacy-DB vorhanden: Sicherung läuft trotzdem ──────────────────

basis, repo, bin_dir, logs, skript, primaer, legacy = _buehne()
_lege_db_an(legacy)          # primärer Pfad bleibt leer
_aenderung(repo, {'terminboard/app.py': '# NEU\n'})
env = _umgebung(basis, bin_dir, logs)
r = subprocess.run(['bash', str(skript)], cwd=repo, env=env,
                   capture_output=True, text=True)
ok(r.returncode == 0 and HELFER_PFAD in _sudo_aufrufe(logs),
   'Legacy-DB (primärer Pfad fehlt) wird erkannt - Sicherung läuft')
ok('systemctl restart terminboard.service' in _sudo_aufrufe(logs),
   'nach Legacy-Sicherung wird neu gestartet')


# ── Abhängigkeits-Fehlschlag bricht ab, kein Neustart ──────────────────

basis, repo, bin_dir, logs, skript, primaer, legacy = _buehne()
_lege_db_an(primaer)
_aenderung(repo, {'terminboard/requirements.txt': 'flask\nneu\n'})
env = _umgebung(basis, bin_dir, logs, pip_exit='1')
r = subprocess.run(['bash', str(skript)], cwd=repo, env=env,
                   capture_output=True, text=True)
ok(r.returncode != 0, 'Abhängigkeits-Fehlschlag bricht den Pull ab (rc=%s)'
   % r.returncode)
ok('systemctl restart terminboard.service' not in _sudo_aufrufe(logs),
   'bei Abhängigkeits-Fehlschlag wird nicht neu gestartet')


# ── Healthcheck-Fehlschlag bricht mit Nicht-Null ab ────────────────────

basis, repo, bin_dir, logs, skript, primaer, legacy = _buehne()
_lege_db_an(primaer)
_aenderung(repo, {'terminboard/app.py': '# NEU\n'})
env = _umgebung(basis, bin_dir, logs, curl_exit='1')
env['TERMINBOARD_HEALTHCHECK_SEKUNDEN'] = '0'   # sofort abbrechen (Test schnell)
r = subprocess.run(['bash', str(skript)], cwd=repo, env=env,
                   capture_output=True, text=True)
ok(r.returncode != 0, 'Healthcheck-Fehlschlag macht den Pull sichtbar (rc=%s)'
   % r.returncode)


# ── Healthcheck versucht es erneut, bevor er aufgibt ───────────────────

basis, repo, bin_dir, logs, skript, primaer, legacy = _buehne()
_lege_db_an(primaer)
_aenderung(repo, {'terminboard/app.py': '# NEU\n'})
env = _umgebung(basis, bin_dir, logs)
env['CURL_FAIL_BIS'] = '2'                        # zwei Fehlschläge, dann ok
env['TERMINBOARD_HEALTHCHECK_SEKUNDEN'] = '60'
r = subprocess.run(['bash', str(skript)], cwd=repo, env=env,
                   capture_output=True, text=True)
curl_aufruf = _curl_aufrufe(logs)
ok(r.returncode == 0, 'Healthcheck gibt nach kurzem Fehlschlag nicht sofort auf')
ok(len(curl_aufruf.splitlines()) >= 3,
   'Healthcheck fragt mehrfach an (%d Versuche)' % len(curl_aufruf.splitlines()))
ok('/login' in curl_aufruf and '/board/api/status' in curl_aufruf,
   'beide Seiten werden trotz Retry geprüft')


# ── TERMINBOARD_DB/LHTPI_DATA_DIR beeinflussen die Erkennung NICHT ─────

basis, repo, bin_dir, logs, skript, primaer, legacy = _buehne()
_lege_db_an(primaer)          # DB liegt am festen Test-Pfad (primär)
_aenderung(repo, {'terminboard/app.py': '# NEU\n'})
env = _umgebung(basis, bin_dir, logs)
# Umlenkversuche über die Umgebung dürfen die Erkennung nicht ändern.
env['TERMINBOARD_DB'] = str(basis / 'umgeleitet.db')
env['LHTPI_DATA_DIR'] = str(basis / 'umgeleitet-data')
r = subprocess.run(['bash', str(skript)], cwd=repo, env=env,
                   capture_output=True, text=True)
ok(r.returncode == 0 and HELFER_PFAD in _sudo_aufrufe(logs),
   'feste Pfade zählen - TERMINBOARD_DB/LHTPI_DATA_DIR werden ignoriert')


print('\n%s%d Prüfungen bestanden, %d fehlgeschlagen'
      % ('OK – ' if failed == 0 else 'FEHLER – ', passed, failed))
sys.exit(1 if failed else 0)
