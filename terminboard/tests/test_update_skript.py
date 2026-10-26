"""Tests für das Update-Skript (scripts/lhtpi-update.sh).

Der Test baut eine Sandbox: ein Stick mit Paket, eine alte Installation und
eine Konfiguration. Danach wird geprüft, dass das Programm ersetzt wurde, die
Einstellungen und Daten aber unangetastet geblieben sind.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
SKRIPT = REPO / 'scripts' / 'lhtpi-update.sh'


def _paket(basis, version='2.0.0'):
    """Baut ein minimales Update-Paket auf dem Stick."""
    paket = basis / 'stick' / 'lhtpi-update'
    for zweig, datei in (('app', 'app.py'),
                         ('terminboard', 'app.py'),
                         ('safety-cross', 'app.py')):
        ordner = paket / zweig
        ordner.mkdir(parents=True, exist_ok=True)
        (ordner / datei).write_text(f'# NEU {version} {zweig}\n')
    (paket / 'version.json').write_text(
        json.dumps({'version': version, 'notiz': 'Test'}), encoding='utf-8')
    return paket


def _altinstallation(basis):
    projekt = basis / 'projekt'
    (projekt / 'terminboard').mkdir(parents=True)
    (projekt / 'uploads').mkdir(parents=True)
    sc = basis / 'safety-cross'
    sc.mkdir()
    (projekt / 'app.py').write_text('# ALT\n')
    (projekt / 'terminboard' / 'app.py').write_text('# ALT\n')
    (sc / 'app.py').write_text('# ALT\n')
    (projekt / 'uploads' / 'foto.jpg').write_text('BILD')
    (projekt / 'lhtpi.db').write_text('DB')
    (projekt / 'terminboard' / 'terminboard.db').write_text('DB')

    etc = basis / 'etc'
    etc.mkdir()
    (etc / 'tools').write_text('safetycross\n')
    (etc / 'screens').write_text('2')
    (etc / 'license.key').write_text('LIZENZ')
    (etc / 'version').write_text('1.0.0')
    return projekt, sc, etc


def _lauf(basis, projekt, sc, etc, *argumente):
    umgebung = dict(os.environ)
    umgebung.update({
        'LHTPI_USB_MOUNT': str(basis / 'stick'),
        'LHTPI_PROJECT_DIR': str(projekt),
        'LHTPI_TERMIN_DIR': str(projekt / 'terminboard'),
        'LHTPI_SC_DIR': str(sc),
        'LHTPI_VERSION_FILE': str(etc / 'version'),
        'LHTPI_BACKUP_DIR': str(basis / 'backups'),
        'LHTPI_SKIP_SERVICES': '1',
        'LHTPI_USER': os.environ.get('USER', 'pi'),
    })
    return subprocess.run(['bash', str(SKRIPT), *argumente],
                          capture_output=True, text=True, env=umgebung, timeout=120)


@pytest.mark.skipif(not SKRIPT.exists(), reason='Update-Skript fehlt')
class TestUpdate:
    def test_programm_wird_ersetzt(self, tmp_path):
        _paket(tmp_path)
        projekt, sc, etc = _altinstallation(tmp_path)
        ergebnis = _lauf(tmp_path, projekt, sc, etc)
        assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
        assert 'NEU 2.0.0' in (projekt / 'app.py').read_text()
        assert 'NEU 2.0.0' in (projekt / 'terminboard' / 'app.py').read_text()
        assert 'NEU 2.0.0' in (sc / 'app.py').read_text()

    def test_einstellungen_bleiben(self, tmp_path):
        _paket(tmp_path)
        projekt, sc, etc = _altinstallation(tmp_path)
        _lauf(tmp_path, projekt, sc, etc)
        assert (etc / 'tools').read_text() == 'safetycross\n'
        assert (etc / 'screens').read_text() == '2'
        assert (etc / 'license.key').read_text() == 'LIZENZ'

    def test_daten_bleiben(self, tmp_path):
        _paket(tmp_path)
        projekt, sc, etc = _altinstallation(tmp_path)
        _lauf(tmp_path, projekt, sc, etc)
        assert (projekt / 'uploads' / 'foto.jpg').read_text() == 'BILD'
        assert (projekt / 'lhtpi.db').read_text() == 'DB'
        assert (projekt / 'terminboard' / 'terminboard.db').read_text() == 'DB'

    def test_version_wird_vermerkt(self, tmp_path):
        _paket(tmp_path)
        projekt, sc, etc = _altinstallation(tmp_path)
        _lauf(tmp_path, projekt, sc, etc)
        assert (etc / 'version').read_text().strip() == '2.0.0'

    def test_sicherung_wird_angelegt(self, tmp_path):
        _paket(tmp_path)
        projekt, sc, etc = _altinstallation(tmp_path)
        _lauf(tmp_path, projekt, sc, etc)
        sicherungen = list((tmp_path / 'backups').iterdir())
        assert len(sicherungen) == 1
        assert '1.0.0' in sicherungen[0].name
        assert list(sicherungen[0].glob('*.tar.gz'))

    def test_paket_wird_markiert(self, tmp_path):
        _paket(tmp_path)
        projekt, sc, etc = _altinstallation(tmp_path)
        _lauf(tmp_path, projekt, sc, etc)
        assert (tmp_path / 'stick' / 'lhtpi-update.erledigt').is_dir()

    def test_zweiter_lauf_tut_nichts(self, tmp_path):
        _paket(tmp_path)
        projekt, sc, etc = _altinstallation(tmp_path)
        _lauf(tmp_path, projekt, sc, etc)
        # Stick ist markiert – ein zweiter Lauf darf nichts mehr ersetzen
        (projekt / 'app.py').write_text('# NACH DEM ERSTEN LAUF\n')
        _lauf(tmp_path, projekt, sc, etc)
        assert (projekt / 'app.py').read_text() == '# NACH DEM ERSTEN LAUF\n'

    def test_probelauf_aendert_nichts(self, tmp_path):
        _paket(tmp_path)
        projekt, sc, etc = _altinstallation(tmp_path)
        ergebnis = _lauf(tmp_path, projekt, sc, etc, '--probe')
        assert ergebnis.returncode == 0
        assert (projekt / 'app.py').read_text() == '# ALT\n'
        assert (etc / 'version').read_text().strip() == '1.0.0'

    def test_gleiche_version_wird_uebersprungen(self, tmp_path):
        _paket(tmp_path, version='1.0.0')
        projekt, sc, etc = _altinstallation(tmp_path)
        ergebnis = _lauf(tmp_path, projekt, sc, etc)
        assert ergebnis.returncode == 0
        assert (projekt / 'app.py').read_text() == '# ALT\n'

    def test_unvollstaendiges_paket_wird_abgelehnt(self, tmp_path):
        paket = _paket(tmp_path)
        (paket / 'safety-cross' / 'app.py').unlink()
        projekt, sc, etc = _altinstallation(tmp_path)
        ergebnis = _lauf(tmp_path, projekt, sc, etc)
        assert ergebnis.returncode != 0
        assert (projekt / 'app.py').read_text() == '# ALT\n'
