import os
_inst = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'install.sh'), encoding='utf-8').read()
"""Prüft den Bundle-Installer (install.sh) ohne Raspberry Pi.

Aufruf:  ./venv/bin/python test_install_bundle.py

Getestet wird, was ohne Hardware prüfbar ist:
  * Syntax und --help
  * Auswahl von Tools und Bildschirmen (nicht-interaktiv)
  * erzeugtes Kiosk-Startskript je Bildschirm (aus dem Skript gerendert)
  * Kiosk-Service je Bildschirm, keine Kiosk-Services je Tool mehr
  * /etc/lhtpi/tools enthält genau die gewählten Tools
"""
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(BASE, 'install.sh')

passed = failed = 0


def ok(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print('  \u2713 %s' % msg)
    else:
        failed += 1
        print('  \u2717 %s' % msg)


def bash(code, cwd=BASE):
    """Führt ein Bash-Snippet in BASE aus."""
    return subprocess.run(['bash', '-c', code], cwd=cwd, capture_output=True, text=True)


def sourced(stmts):
    """Sourct install.sh und führt stmts aus (main läuft dabei NICHT)."""
    return bash('set -e\nsource ./install.sh\n' + stmts)


text = open(INSTALL, encoding='utf-8').read()

print('\n1) Syntax und Hilfe')
r = bash('bash -n install.sh')
ok(r.returncode == 0, 'install.sh Syntax ok')
r = bash('bash install.sh --help')
ok(r.returncode == 0 and '--tools=' in r.stdout,
   '--help gibt die Hilfe aus (ohne root, exit 0)')

print('\n2) Auswahl der Tools (nicht-interaktiv)')
r = sourced('select_components "1,3" "2"\n'
            'echo "T=$TOOL_SLIDESHOW$TOOL_TERMIN$TOOL_SC S=$SCREEN_COUNT"\n'
            'echo "IDS=$(tools_file_content | tr \'\\n\' \',\')"')
ok(r.returncode == 0 and 'T=101 S=2' in r.stdout,
   'Tools 1,3 + 2 Bildschirme -> Folien & Safety Cross (Terminboard aus)')
ok('IDS=slideshow,safetycross,' in r.stdout,
   '/etc/lhtpi/tools-Inhalt: slideshow + safetycross')

r = sourced('select_components "3" "1"\necho "T=$TOOL_SLIDESHOW$TOOL_TERMIN$TOOL_SC"\n'
            'echo "IDS=$(tools_file_content | tr \'\\n\' \',\')"')
ok(r.returncode == 0 and 'T=001' in r.stdout, 'nur Safety Cross (Abteilung mit einem Tool)')
ok('IDS=safetycross,' in r.stdout, 'Tools-Datei enthält nur safetycross')

r = sourced('select_components "slideshow,terminboard,safetycross" "2"\n'
            'echo "T=$TOOL_SLIDESHOW$TOOL_TERMIN$TOOL_SC"')
ok(r.returncode == 0 and 'T=111' in r.stdout, 'Namen statt Ziffern (alle drei Tools)')

r = sourced('select_components "1,2,3" "2"')
ok(r.returncode == 0, 'alle drei Tools auf zwei Bildschirmen')

r = sourced('select_components "9" "1"')
ok(r.returncode != 0 and 'Ungültige Tool-Auswahl' in r.stderr + r.stdout,
   'unbekanntes Tool wird abgelehnt')
r = sourced('select_components "1" "5"')
ok(r.returncode != 0 and 'Bildschirm-Anzahl' in r.stderr + r.stdout,
   'ungültige Bildschirm-Anzahl wird abgelehnt')

print('\n3) Kiosk-Startskript je Bildschirm')
r = sourced('render_screen_kiosk_script 1 > /tmp/kiosk-screen1.sh\n'
            'bash -n /tmp/kiosk-screen1.sh\n'
            'cat /tmp/kiosk-screen1.sh')
s1 = r.stdout
ok(r.returncode == 0, 'Skript für Bildschirm 1 ist syntaktisch gültig')
ok('__IDX__' not in s1 and '__APP_URL__' not in s1, 'keine Platzhalter im Skript')
ok('/screen/1' in s1, 'Bildschirm 1 zeigt den Anzeige-Router /screen/1')
ok('MON="HDMI-1"' in s1 and 'chromium-screen1' in s1,
   'Bildschirm 1: HDMI-1, eigenes Chromium-Profil')
ok('unclutter' not in s1, 'kein unclutter mehr (Cursor macht die Seite)')

print('\n3b) Bildschirm bleibt wach und wird nach spaetem Einschalten aktiviert')
r = sourced('render_display_guard > /tmp/lhtpi-display-guard.sh\n'
            'bash -n /tmp/lhtpi-display-guard.sh\n'
            'cat /tmp/lhtpi-display-guard.sh')
guard = r.stdout
ok(r.returncode == 0, 'Display-Waechter ist syntaktisch gueltig')
ok('xset s off' in guard and 'xset -dpms' in guard and
   'xset s noblank' in guard and 'xset dpms force on' in guard,
   'Bildschirmschoner, Blanking und DPMS bleiben dauerhaft aus')
ok(guard.index('xset dpms force on') < guard.index('xset -dpms'),
   'DPMS wird erst aufgeweckt und danach deaktiviert')
ok('while true' in guard and 'xrandr --query' in guard,
   'Waechter erkennt einen erst spaeter eingeschalteten Monitor')
ok("{print $0}" in guard and "{print $1, $2, $3}" not in guard,
   'Waechter erkennt auch einen verbundenen, aber deaktivierten Ausgang')
ok('HDMI-1 HDMI-2' in guard and '--primary --auto --pos 0x0' in guard,
   'erster angeschlossener HDMI-Port wird automatisch als Hauptanzeige aktiviert')
ok('configure_display_guard' in text.split('main()')[1],
   'Display-Waechter wird vom Installer eingerichtet')
ok('WantedBy=multi-user.target' in text and 'lhtpi-display-guard.service' in text,
   'Display-Waechter startet bei jedem Boot')

r = sourced('render_screen_kiosk_script 2 > /tmp/kiosk-screen2.sh\n'
            'bash -n /tmp/kiosk-screen2.sh\n'
            'cat /tmp/kiosk-screen2.sh')
s2 = r.stdout
ok(r.returncode == 0, 'Skript für Bildschirm 2 ist syntaktisch gültig')
ok('/screen/2' in s2 and 'MON="HDMI-2"' in s2 and 'chromium-screen2' in s2,
   'Bildschirm 2: /screen/2 auf HDMI-2, eigenes Profil')

print('\n4) Services: einer je Bildschirm, keiner je Tool')
r = sourced('echo "$(kiosk_service_name 1) $(kiosk_service_name 2)"')
ok('kiosk-screen1.service kiosk-screen2.service' in r.stdout,
   'Service-Namen je Bildschirm')
ok('configure_screens()' in text and 'SCREEN_COUNT' in text,
   'configure_screens legt so viele Kiosks an, wie Bildschirme vorhanden sind')
ok('lhtpi-kiosk.service' in text and 'cleanup_old_kiosks' in text,
   'alte Kiosk-Services (je Tool) werden beim Installieren entfernt')

print('\n5) Sicherheit Cross als Teil des Bundles')
ok('SC_PORT="8002"' in text, 'Safety Cross auf Port 8002')
ok('tools/safety-cross' in text, 'Installer holt den Code aus tools/safety-cross')
ok('hardware' in text.lower() and 'license' in text.lower(),
   'Hardware-Lizenz wird bei der Installation erzeugt')
ok('SERVICE_SC_APP' in text and 'safetycross.service' in text,
   'eigener systemd-Service für Safety Cross')
ok('/etc/lhtpi/tools' in text, 'gewählte Tools landen in /etc/lhtpi/tools')

print('\n7) Hardware-Lizenz wird mitinstalliert')
ok('configure_license()' in text, 'Installer hat einen Lizenz-Schritt')
ok('/etc/sudoers.d/020_lhtpi-kiosk' in text and 'visudo -c -f' in text,
   'install.sh erlaubt Neustart/Herunterfahren (sudoers, nur diese Befehle)')
ok('/usr/bin/systemctl reboot' in text and '/usr/bin/systemctl poweroff' in text,
   'die Freigabe deckt systemctl mit Unterbefehl ab (Symlink /sbin/reboot greift nicht)')
ok('! -s "${tmp}"' in text,
   'install.sh prueft, dass die Freigabe wirklich Inhalt hat')
r = sourced('render_anzeige_steuerung')
ok(r.returncode == 0, 'das Steuer-Skript laesst sich erzeugen')
ok('020_lhtpi-kiosk' not in r.stdout,
   'die Freigabe steckt NICHT im erzeugten Steuer-Skript (sonst wird sie leer geschrieben)')
ok('configure_sudoers_kiosk() {' in text,
   'install.sh definiert einen eigenen Schritt fuer die Freigabe')
ok('\n    configure_sudoers_kiosk\n' in text,
   'der Hauptteil ruft den Freigabe-Schritt auf (nicht im Steuer-Skript)')
ok('--install' in text and 'license_bundle.py' in text,
   'Lizenz wird beim Installieren für dieses Gerät erzeugt')
ok('MARKER_FILE' in text and '/etc/lhtpi/installed' in text,
   'Installationsmerkmal schaltet die Lizenzprüfung scharf')
r = sourced('select_components "1,3" "2"; echo "ARG=$(tools_file_content | paste -sd, -)"')
ok('ARG=slideshow,safetycross' in r.stdout,
   'Lizenz erhält die gewählten Tools und die Bildschirm-Anzahl')

print('\n8) Tool-URLs per Umgebung überschreibbar (Demo/Test)')
r = subprocess.run(
    [sys.executable, '-c', 'import kiosk_tools as t; print(t.default_url("slideshow"))'],
    cwd=BASE, capture_output=True, text=True,
    env=dict(os.environ, LHTPI_TOOL_URLS='slideshow=http://localhost:8900/present/kiosk'))
ok('8900' in r.stdout, 'LHTPI_TOOL_URLS ersetzt die Tool-URL')
r = subprocess.run(
    [sys.executable, '-c', 'import kiosk_tools as t; print(t.default_url("slideshow"))'],
    cwd=BASE, capture_output=True, text=True)
ok(':8000' in r.stdout, 'ohne Override gilt die Standard-URL')

print('\n9) Kein Access Point mehr')
ok('con add type wifi' not in text and 'AP_SSID' not in text,
   'kein WLAN-Access-Point wird mehr eingerichtet')
ok('mode ap' not in text, 'kein AP-Modus im Installer')
ok('wlan0: bleibt unangetastet' in text, 'WLAN bleibt unberührt')

print('\n10) Ersteinrichtung auf dem Bildschirm')
ok('lhtpi-setup.service' in text, 'Service für die Ersteinrichtung')
ok('ConditionPathExists=${MARKER_FILE}' in text,
   'Kiosk-Fenster starten erst nach der Einrichtung')
ok('systemctl enable lhtpi-anzeige.service' in text,
   'Boot-Steuerung ist für spätere Neustarts aktiviert')
ok('systemctl disable lhtpi-setup.service' in text,
   'Einrichtungsfenster startet nicht ungefragt bei jedem Boot')
ok('if [ ! -f "${INSTALLED}" ]; then' in text
   and 'systemctl start lhtpi-setup.service' in text,
   'Boot-Steuerung öffnet die Einrichtung nur ohne Installationsmerkmal')
ok('SCREEN2_FILE' in text and 'screen2' in text,
   'zweiter Bildschirm hat ein eigenes Merkmal')
ok('lhtpi-anzeige.path' in text
   and 'PathChanged=${MARKER_FILE}' in text
   and 'PathChanged=${SCREENS_FILE}' in text,
   'Pfad-Wächter reagiert flankengesteuert auf Abschluss und Bildschirm-Anzahl')
ok('PathExists=${MARKER_FILE}' not in text.split('cat > /etc/systemd/system/lhtpi-anzeige.path', 1)[1],
   'dauerhaft vorhandenes Merkmal löst keine systemd-Startschleife aus')
ok('localhost:${APP_PORT}/display' in text or '/display' in text,
   'Ersteinrichtung zeigt die Anzeigen-Seite')
ok('chmod 775' in text, 'Konfigurationsordner ist für die App schreibbar')
setup_skript = sourced('render_setup_script')
ok('http://localhost:8000/display' in setup_skript.stdout
   and '__APP_URL__' not in setup_skript.stdout,
   'Skript der Ersteinrichtung zeigt die Anzeigen-Seite (ohne Platzhalter)')
ok('xrandr --auto' in setup_skript.stdout,
   'Ersteinrichtung schaltet alle angeschlossenen Ausgänge ein')
steuerung = sourced('render_anzeige_steuerung')
ok('kiosk-screen2.service' in steuerung.stdout and '/etc/lhtpi/screens' in steuerung.stdout,
   'Anzeige-Steuerung kennt Bildschirm 2 und die Anzahl-Datei')
ok('__MAX__' not in steuerung.stdout, 'keine Platzhalter in der Anzeige-Steuerung')
ok('configure_screens_file\n' not in text,
   'Anzahl der Bildschirme wird nicht mehr beim Installieren festgeschrieben')

print('\n11) Keine Rückfragen beim Installieren')
r = sourced('select_components "" ""\necho "T=$TOOL_SLIDESHOW$TOOL_TERMIN$TOOL_SC"\n'
            'echo "S=$SCREEN_COUNT"')
ok('T=111' in r.stdout, 'ohne Angabe werden alle Tools installiert')
ok('S=2' in r.stdout, 'Bildschirm-Anzahl kommt aus der Ersteinrichtung')
ok('Bildschirme: bis ${SCREEN_COUNT} möglich' in text,
   'Installer nennt die Anzahl als Obergrenze (ein Bildschirm genügt')

print('\n13b) Lizenz-Schritt läuft unter "set -u" wirklich durch')

import tempfile
LZ = tempfile.mkdtemp(prefix='lhtpi-inst-')
UMG = dict(os.environ)
UMG.update({
    'LHTPI_LICENSE_FILE': os.path.join(LZ, 'license.key'),
    'LHTPI_INSTALLED_MARKER': os.path.join(LZ, 'installed'),
    'LHTPI_TOOLS_FILE': os.path.join(LZ, 'tools'),
    'LHTPI_SCREENS_FILE': os.path.join(LZ, 'screens'),
    'LHTPI_SCREEN2_FILE': os.path.join(LZ, 'screen2'),
})


def schritt(stmts, env=None):
    return subprocess.run(['bash', '-c', 'set -e\nsource ./install.sh\n' + stmts],
                          cwd=BASE, env=env or UMG, capture_output=True, text=True)


# Das war der Fehler auf dem echten Pi: ohne --license= brach der Schritt mit
# "LICENSE_ARG: unbound variable" ab und die Installation endete vorzeitig.
print('\n18) Bildschirmzahl: --screens gewinnt, sonst bleibt die Geräte-Wahl')
_scr = os.path.join(LZ, 'screens-arg')
for _expl, _vorher, _erwartet in ((1, '1', '2'), (0, '1', '1')):
    with open(_scr, 'w') as f:
        f.write(_vorher)
    _env = dict(UMG)
    _env['LHTPI_SCREENS_FILE'] = _scr
    _r = schritt(
        'SCREENS_EXPLIZIT=%d; SCREEN_COUNT=2; LHTPI_FORCE_SCREENS=0; configure_screens_file'
        % _expl, env=_env)
    _ist = open(_scr).read().strip()
    ok(_ist == _erwartet,
       '--screens ausdrücklich=%d, Datei %s -> %s' % (_expl, _vorher, _ist))

# Mit --screens=2 muss die Marke für Bildschirm 2 entstehen
_scr2 = os.path.join(LZ, 'screens-arg2')
_s2 = os.path.join(LZ, 'screen2-arg2')
for _p in (_scr2, _s2):
    if os.path.exists(_p):
        os.remove(_p)
with open(_scr2, 'w') as f:
    f.write('1')
_env = dict(UMG)
_env['LHTPI_SCREENS_FILE'] = _scr2
_env['LHTPI_SCREEN2_FILE'] = _s2
_r = schritt('configure_screen_kiosk() { :; }; SCREENS_EXPLIZIT=1; SCREEN_COUNT=2; configure_screens', env=_env)
ok(os.path.exists(_s2), 'Marke fuer Bildschirm 2 wird angelegt')

r = schritt('configure_license')
ok(r.returncode == 0, 'configure_license ohne --license bricht nicht ab')
ok('unbound variable' not in r.stderr, 'keine ungebundene Variable (set -u)')
ok('bleibt gesperrt' in r.stdout, 'ohne Lizenz wird deutlich gewarnt')
ok(not os.path.exists(UMG['LHTPI_LICENSE_FILE']), 'ohne Lizenz wird nichts angelegt')

# Mit mitgelieferter Lizenz (so kommt sie beim Kunden an)
geliefert = os.path.join(LZ, 'geliefert.key')
open(geliefert, 'w').write('LHTPI-TEST-LIZENZ\n')
r = schritt('LICENSE_ARG="%s"; configure_license' % geliefert)
ok(r.returncode == 0 and os.path.exists(UMG['LHTPI_LICENSE_FILE']),
   'mitgelieferte Lizenz (--license=) wird übernommen')
ok(open(UMG['LHTPI_LICENSE_FILE']).read().startswith('LHTPI-TEST'),
   'übernommene Datei hat den richtigen Inhalt')

# Ohne Signierschlüssel wird auf dem Gerät nichts erzeugt
leer = dict(UMG, LHTPI_LICENSE_FILE=os.path.join(LZ, 'frisch', 'license.key'))
r = schritt('LICENSE_ARG=""; configure_license', env=leer)
ok('make-key' in r.stdout and 'bleibt gesperrt' in r.stdout,
   'ohne Signierschlüssel nur Hinweis, kein Selbst-Erzeugen')
ok(not os.path.exists(leer['LHTPI_LICENSE_FILE']),
   'auf dem Gerät entsteht keine Lizenz von selbst')

print('\n13d) Kein Anmeldebildschirm (Anzeige startet ohne Login)')

ok('configure_autologin' in text, 'Autologin-Schritt ist im Skript vorhanden')
ok('configure_autologin' in text.split('main()')[1],
   'Autologin ist in den Ablauf eingehängt')
ok('systemctl disable lightdm.service' in text,
   'Anmeldebildschirm (LightDM) wird abgeschaltet')
ok('WantedBy=graphical.target' not in text,
   'kein Dienst hängt mehr am graphischen Ziel (kein Anmeldedienst)')
ok('WantedBy=multi-user.target' in text, 'Dienste hängen am normalen Startziel')
ok('autologin ${PI_USER} --noclear' in text,
   'tty1 meldet den Benutzer automatisch an')

# Ablauf wirklich ausführen (mit Testordnern statt /home/pi und /etc)
BIN = os.path.join(LZ, 'bin')
os.makedirs(BIN, exist_ok=True)
open(os.path.join(BIN, 'startx'), 'w').write('#!/bin/sh\nexec xinit "$@"\n')
open(os.path.join(BIN, 'raspi-config'), 'w').write('#!/bin/sh\nexit 0\n')
for _b in ('startx', 'raspi-config'):
    os.chmod(os.path.join(BIN, _b), 0o755)
HAUS = os.path.join(LZ, 'home', 'pi')
UD = os.path.join(LZ, 'units')
os.makedirs(HAUS, exist_ok=True)
os.makedirs(UD, exist_ok=True)
AUT = dict(UMG, LHTPI_PI_HOME=HAUS, LHTPI_UNIT_DIR=UD,
           PATH=BIN + os.pathsep + UMG['PATH'])
r = schritt('configure_autologin', env=AUT)
ok(r.returncode == 0, 'Autologin-Schritt bricht nicht ab (set -u)')
profil = open(os.path.join(HAUS, '.bash_profile')).read()
ok('exec startx' in profil, 'Anzeige startet automatisch über startx')
ok('"/dev/tty1"' in profil, 'startx nur auf tty1 (SSH bleibt normal)')
ok('DISPLAY' in profil, 'startet nur ohne laufende Anzeige (kein Doppelstart)')
xinitrc = os.path.join(HAUS, '.xinitrc')
ok(os.path.exists(xinitrc) and 'exec openbox-session' in open(xinitrc).read(),
   'X-Sitzung: openbox ohne Desktop')
gotty = os.path.join(UD, 'getty@tty1.service.d', 'lhtpi-autologin.conf')
ok(os.path.exists(gotty) and '--autologin pi' in open(gotty).read(),
   'automatische Anmeldung auf tty1 hinterlegt')

# Zweiter Lauf darf nichts doppeln
r = schritt('configure_autologin', env=AUT)
profil2 = open(os.path.join(HAUS, '.bash_profile')).read()
ok(profil2.count('exec startx') == 1, 'zweiter Lauf doppelt nichts')
ok('war schon eingerichtet' in r.stdout, 'zweiter Lauf erkennt den Zustand')

# Wartezeiten: ohne Anmeldedienst startet X gleichzeitig
ok(text.count('xset q >/dev/null 2>&1 && break') >= 2,
   'Kiosk- und Einrichtungsskript warten auf den Bildschirm (X)')

print('\n13c) Alle Schritte nennen ihre Variablen (Schutz vor set -u)')
from_a = open(INSTALL).read()
import re as _re
# Funktionen, die im Ablauf vorkommen, müssen unter set -u aufrufbar sein:
# grob prüfen, ob groß geschriebene Variablen benutzt werden, die nirgends
# vorbelegt sind.
vorbelegt = set(_re.findall(r'^([A-Z][A-Z0-9_]*)="', from_a, _re.M))
vorbelegt |= set(_re.findall(r'^([A-Z][A-Z0-9_]*)=', from_a, _re.M))
benutzt = set(_re.findall(r'\$\{([A-Z][A-Z0-9_]*)\}', from_a))
unbekannt = {v for v in benutzt - vorbelegt if v not in {'BASH_SOURCE', 'HOME', 'PATH', 'EUID', 'UID', 'USER'}}
ok(not unbekannt, 'keine unvorbelegten Variablen benutzt (%s)' % (sorted(unbekannt) or 'keine'))

print('\n13) Lizenz kommt vom Hersteller (kein Schlüssel auf dem Gerät)')
ok('nur der ÖFFENTLICHE Schlüssel' in text,
   'Kommentar stellt klar: privater Schlüssel bleibt beim Hersteller')
ok('--license=' in text and 'LICENSE_ARG' in text,
   'Option --license=<datei> vorhanden')
ok('/boot/firmware/lizenz.key' in text and '/boot/lizenz.key' in text,
   'Lizenz wird von der Boot-Partition übernommen')
ok('${LHTPI_SIGN_KEY_FILE:-}' in text,
   'Selbst erzeugen nur mit Signierschlüssel (Hersteller-Rechner)')
ok('lhtpi-lizenz-import' in text and 'lhtpi-lizenz-import.sh' in text,
   'Dienst holt eine später gelieferte Lizenz beim Start nach')
ok('${LICENSE_STATUS}' in text, 'Abschluss-Ausgabe nennt den Lizenzstand')

print('\n12) Safety-Cross-Admin verweist nicht auf die Anzeigen-Seite')
sc_admin = os.path.join(BASE, 'tools/safety-cross/templates/admin.html')
if os.path.exists(sc_admin):
    inhalt = open(sc_admin).read()
    ok('Anzeigen-Einstellungen öffnen' not in inhalt,
       'SC-Admin hat keinen Anzeigen-Knopf mehr (Tim: "Anzeigen Optionen raus")')
    ok(':8000/display' not in inhalt, 'kein Verweis auf die Anzeigen-Seite')
else:
    ok(False, 'SC-Admin-Vorlage gefunden')

print('\n9) Altlasten')
ok('INSTALL_LHTPI' not in text and 'INSTALL_TERMIN' not in text,
   'keine alte Auswahl-Logik (INSTALL_LHTPI/INSTALL_TERMIN) mehr')
ok('SERVICE_KIOSK=' not in text and 'KIOSK_SCRIPT=' not in text,
   'keine alten Kiosk-Variablen mehr')
ok('start_lhtpi_kiosk.sh' in text, 'alte Kiosk-Skripte werden aufgeräumt')
ok('main "$@"' in text and 'BASH_SOURCE' in text,
   'Aufruf-Guard vorhanden (Tests können install.sh sourcen)')

print('\n14) Vom Knopf zum Kiosk-Fenster (Anzeige-Kette)')

# Die Anzeigen-Steuerung beendet die Einrichtungs-Seite und startet die Fenster.
r = schritt('render_anzeige_steuerung')
steuer = r.stdout
ok(r.returncode == 0, 'Anzeigen-Steuerung lässt sich erzeugen')
ok('systemctl stop lhtpi-setup.service' in steuer,
   'Anzeige starten beendet die Einrichtungs-Seite (kein Fenster übereinander)')
ok('systemctl start kiosk-screen1.service' in steuer,
   'Anzeige starten öffnet das Kiosk-Fenster für Bildschirm 1')
ok('systemctl start kiosk-screen2.service' in steuer,
   'bei zwei Bildschirmen auch das zweite Fenster')
ok('/etc/lhtpi/installed' in steuer,
   'Fenster starten erst nach abgeschlossener Einrichtung')

# Die Boot-Seite ist die Anzeigen-Seite - nicht das Dashboard.
r = schritt('render_setup_script')
setup_skript = r.stdout
ok('/display' in setup_skript, 'Boot landet auf der Anzeigen-Seite')
ok('localhost:8000/"' not in setup_skript and "localhost:8000/'" not in setup_skript,
   'nicht auf der Startseite (Dashboard)')

print('\n15) Altlasten: kein alter Kiosk mit Dashboard')

UD2 = os.path.join(LZ, 'units2')
os.makedirs(UD2, exist_ok=True)
alte = {
    'lhtpi-kiosk.service': '[Service]\nExecStart=/home/pi/start_lhtpi_kiosk.sh\n',
    'lhtpi-dashboard.service': '[Service]\nExecStart=/usr/bin/chromium-browser http://localhost:8000/\n',
    'lhtpi-display.service': '[Service]\nExecStart=/home/pi/start_dashboard.sh\n',
}
for name, inhalt in alte.items():
    open(os.path.join(UD2, name), 'w').write(inhalt)
bleiben = {
    'lhtpi.service': '[Service]\nExecStart=/home/pi/app.py\n',
    'lhtpi-setup.service': '[Service]\nExecStart=/home/pi/start_setup.sh\n',
    'lhtpi-anzeige.service': '[Service]\nExecStart=/usr/local/bin/lhtpi-anzeige-steuern.sh\n',
    'kiosk-screen1.service': '[Service]\nExecStart=/home/pi/kiosk-screen1.sh\n',
    'kiosk-screen2.service': '[Service]\nExecStart=/home/pi/kiosk-screen2.sh\n',
    'sshd.service': '[Service]\nExecStart=/usr/sbin/sshd\n',
}
for name, inhalt in bleiben.items():
    open(os.path.join(UD2, name), 'w').write(inhalt)
r = schritt('cleanup_old_kiosks', env=dict(UMG, LHTPI_UNIT_DIR=UD2))
ok(r.returncode == 0, 'Aufräumen bricht nicht ab')
for name in alte:
    ok(not os.path.exists(os.path.join(UD2, name)),
       'alte Einheit entfernt: %s' % name)
for name in bleiben:
    ok(os.path.exists(os.path.join(UD2, name)),
       'aktuelle/fremde Einheit bleibt: %s' % name)
ok('alte Einheit entfernt' in r.stdout, 'Aufräumen wird im Protokoll gemeldet')

print('\n16) Aufräumen lässt die eigenen Einheiten in Ruhe')

UD3 = os.path.join(LZ, 'units3')
os.makedirs(UD3, exist_ok=True)
EIGENE = ['lhtpi.service', 'lhtpi-setup.service', 'lhtpi-anzeige.service',
          'lhtpi-anzeige.path', 'lhtpi-display-guard.service',
          'kiosk-screen1.service', 'kiosk-screen2.service',
          'lhtpi-lizenz-import.service', 'lhtpi-fake-hwclock.service',
          'lhtpi-fake-hwclock-save.service', 'lhtpi-fake-hwclock-save.timer']
FREMDE = ['sshd.service', 'display-manager.service', 'cups.service']
ALTE = ['lhtpi-dashboard.service', 'terminboard-kiosk.service',
        'safety-cross-kiosk.service']
for n in EIGENE + FREMDE + ALTE:
    with open(os.path.join(UD3, n), 'w') as f:
        f.write('[Unit]\nDescription=%s\n' % n)

schritt('cleanup_old_kiosks', env=dict(UMG, LHTPI_UNIT_DIR=UD3))
weg = [n for n in EIGENE + FREMDE if not os.path.exists(os.path.join(UD3, n))]
ok(not weg, 'eigene und fremde Einheiten bleiben erhalten (%s)' % (weg or 'alle da'))
rest = [n for n in ALTE if os.path.exists(os.path.join(UD3, n))]
ok(not rest, 'alte Anzeige-Einheiten sind entfernt (%s)' % (rest or 'alle weg'))

# Jede Einheit, die install.sh selbst anlegt, muss auf der Behalten-Liste stehen
angelegt = set(re.findall(r'UNIT_DIR\}/([A-Za-z0-9_.-]+\.(?:service|path|timer))',
                          text))
angelegt |= set(re.findall(r'/etc/systemd/system/([A-Za-z0-9_.-]+\.(?:service|path|timer))',
                           text))
angelegt |= {'lhtpi.service', 'lhtpi-lizenz-import.service'}   # aus Variablen
# display-manager.service gehört dem System (Anmeldedienst) - die Einrichtung
# schaltet ihn nur ab und darf ihn nie löschen.
angelegt.discard('display-manager.service')
liste = re.search(r'local behalten="([^"]+)"', text, re.S).group(1).split()
fehlt = sorted(n for n in angelegt if n.endswith('.service') and n not in liste)
ok(not fehlt, 'jede selbst angelegte Einheit steht auf der Behalten-Liste (%s)'
   % (fehlt or 'alle'))

print('\n17) Steuerung: Bildschirm bleibt nie schwarz')

# Stub-systemctl: schreibt nur mit, was aufgerufen wurde
STUB = os.path.join(LZ, 'stub'); os.makedirs(STUB, exist_ok=True)
with open(os.path.join(STUB, 'systemctl'), 'w') as f:
    f.write('#!/bin/bash\necho "$@" >> "$SYSTEMCTL_LOG"\n'
            '[ "$1" = "is-active" ] && echo "${SYSTEMCTL_ZUSTAND:-active}"\n')
os.chmod(os.path.join(STUB, 'systemctl'), 0o755)

steuer_pfad = os.path.join(LZ, 'steuern.sh')
with open(steuer_pfad, 'w') as f:
    f.write(schritt('render_anzeige_steuerung').stdout)
os.chmod(steuer_pfad, 0o755)

MARKER_DA = os.path.join(LZ, 'installed')


def steuere(marker_da, zustand='active'):
    log = os.path.join(LZ, 'systemctl.log')
    if os.path.exists(log):
        os.remove(log)
    if marker_da:
        open(MARKER_DA, 'w').close()
    elif os.path.exists(MARKER_DA):
        os.remove(MARKER_DA)
    env = dict(os.environ, PATH=STUB + ':' + os.environ['PATH'],
               SYSTEMCTL_LOG=log, SYSTEMCTL_ZUSTAND=zustand,
               LHTPI_INSTALLED=MARKER_DA, LHTPI_SCREENS=os.path.join(LZ, 'screens'),
               LHTPI_STEUER_WARTE='1', LHTPI_STEUER_WARTE2='1')
    subprocess.run(['bash', steuer_pfad], env=env, capture_output=True, timeout=60)
    try:
        with open(log) as f:
            return f.read()
    except OSError:
        return ''


with open(os.path.join(LZ, 'screens'), 'w') as f:
    f.write('1\n')

rufe = steuere(marker_da=False)
ok('start lhtpi-setup.service' in rufe,
   'ohne Abschluss startet die Ersteinrichtung statt eines schwarzen Bildschirms')
ok('kiosk-screen1.service' not in rufe, 'und es wird kein Kiosk gestartet')

rufe = steuere(marker_da=True)
ok('stop lhtpi-setup.service' in rufe,
   'nach dem Abschluss wird die Anzeigen-Seite geschlossen')
ok('start kiosk-screen1.service' in rufe, 'und das Kiosk-Fenster gestartet')
ok('start lhtpi-setup.service' not in rufe,
   'die Seite wird nicht doppelt gestartet, wenn der Kiosk läuft')

rufe = steuere(marker_da=True, zustand='inactive')
ok('start lhtpi-setup.service' in rufe,
   'kommt der Kiosk nicht hoch, kommt die Anzeigen-Seite zurück (Selbstheilung)')

zwei = steuere(marker_da=True)
with open(os.path.join(LZ, 'screens'), 'w') as f:
    f.write('2\n')
zwei = steuere(marker_da=True)
ok('start kiosk-screen2.service' in zwei,
   'bei zwei Bildschirmen startet auch das zweite Fenster')
with open(os.path.join(LZ, 'screens'), 'w') as f:
    f.write('1\n')

print('\n18) Einheiten: Startgrenze im richtigen Abschnitt')

# StartLimitIntervalSec/Burst gehören in [Unit]. In [Service] meckert systemd
# ("Unknown key ... ignoring") und die Grenze wirkt nicht.
falsch = []
for treffer in re.finditer(r'StartLimit(?:IntervalSec|Burst)', text):
    vor = text[:treffer.start()]
    einheit = vor.rfind('[Unit]')
    dienst = vor.rfind('[Service]')
    if einheit < 0 or dienst > einheit:
        falsch.append(text[vor.rfind('\n', 0, treffer.start()) + 1:
                           text.find('\n', treffer.start())].strip())
ok(not falsch, 'Startgrenzen stehen in [Unit] (%s)' % (falsch or 'alle richtig'))

print('\n19) Kiosk-Fenster: keine fremden Tabs aus alter Sitzung')

kiosk_skript = schritt('render_screen_kiosk_script 1').stdout
ok('Alte Sitzung verwerfen' in kiosk_skript,
   'Kiosk-Skript verwirft die alte Chromium-Sitzung')
ok('Current Session' in kiosk_skript and 'Last Tabs' in kiosk_skript,
   'und zwar die Sitzungsdateien selbst')
# Seit der Überwachung startet Chromium in einer Funktion (starte_chromium)
# statt per exec – die Reihenfolge bleibt dieselbe.
_ces = kiosk_skript.index('Current Session')
# Der Aufruf steht in der Funktion starte_chromium – gesucht ist die Stelle,
# an der Chromium zum ersten Mal gestartet wird (nicht die Pfadprüfung oben).
_start = kiosk_skript.index('starte_chromium() {')
ok(_ces < _start, 'das passiert vor dem Start von Chromium')
ok('--hide-crash-restore-bubble' in kiosk_skript,
   'Restore-Hinweis ist zusätzlich abgeschaltet')

ok('kiosk-cursor-x11.py' in _inst, 'install.sh richtet die Zeiger-Wache ein')
ok('unclutter -idle' not in _inst and 'unclutter\\n' not in _inst,
   'kein unclutter-Aufruf (das blendet den Zeiger dauerhaft aus)')
ok(os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'tools', 'kiosk-cursor-x11.py')),
   'Helfer tools/kiosk-cursor-x11.py ist vorhanden')

print('\n20) DS3231-Hardware-Uhr mit automatischem Fallback')
ok('dtparam=i2c_arm=on' in text and 'dtoverlay=i2c-rtc,ds3231' in text,
   'Installer aktiviert I2C und das DS3231-Overlay idempotent')
ok('RTC_DEVICE=/dev/rtc0' in text and 'hwclock --hctosys --utc' in text,
   'beim Boot wird eine erkannte Hardware-Uhr automatisch gelesen')
ok('hwclock --systohc --utc' in text,
   'korrekte Systemzeit wird in eine erkannte Hardware-Uhr geschrieben')
ok('SAVE=/etc/fake-hwclock.data' in text and 'date -s' in text,
   'ohne RTC bleibt die bisherige fake-hwclock-Rückfallebene erhalten')
ok('rtc_plausibel' in text and 'minimum_epoch' in text and 'ersatz_epoch' in text,
   'uninitialisierte oder unplausible RTC wird nicht blind übernommen')
ok('DS3231 aus gespeicherter Ersatzzeit initialisiert' in text,
   'eine uninitialisierte RTC wird aus der Ersatzzeit initialisiert')
ok('RTC nicht bereit' in text or 'RTC nicht erkannt' in text,
   'Uhr-Helfer protokolliert den Fallback verständlich')
ok('After=systemd-modules-load.service systemd-udev-trigger.service' in text,
   'Boot-Service wartet auf Modulladen und udev-Geräteerzeugung')
ok('DefaultDependencies=no' in text and 'Before=shutdown.target' in text,
   'Uhr wird beim Herunterfahren vor shutdown.target gesichert')

# Den tatsächlich erzeugten Helfer mit einer simulierten RTC ausführen.
rtc_match = re.search(
    r"cat > /usr/local/sbin/lhtpi-hwclock <<'EOF'\n(.*?)\nEOF", text, re.S)
ok(rtc_match is not None, 'RTC-Helfer lässt sich vollständig aus dem Installer extrahieren')
if rtc_match:
    RTC_TEST = tempfile.mkdtemp(prefix='lhtpi-rtc-')
    RTC_DEV = os.path.join(RTC_TEST, 'rtc0')
    RTC_SYS = os.path.join(RTC_TEST, 'sys-rtc0')
    RTC_SAVE = os.path.join(RTC_TEST, 'fake-hwclock.data')
    RTC_BIN = os.path.join(RTC_TEST, 'bin')
    RTC_LOG = os.path.join(RTC_TEST, 'hwclock.log')
    DATE_LOG = os.path.join(RTC_TEST, 'date-set.log')
    os.makedirs(RTC_SYS)
    os.makedirs(RTC_BIN)
    open(RTC_DEV, 'w').close()
    helper = rtc_match.group(1)
    helper = helper.replace('/sys/class/rtc/rtc0', RTC_SYS)
    helper = helper.replace('/etc/fake-hwclock.data', RTC_SAVE)
    helper = helper.replace('/dev/rtc0', RTC_DEV)
    helper_path = os.path.join(RTC_TEST, 'lhtpi-hwclock')
    open(helper_path, 'w').write(helper + '\n')
    os.chmod(helper_path, 0o755)
    open(os.path.join(RTC_BIN, 'hwclock'), 'w').write(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$HWCLOCK_LOG"\nexit 0\n')
    open(os.path.join(RTC_BIN, 'date'), 'w').write(
        '#!/bin/sh\nif [ "${1:-}" = "-s" ]; then printf "%s\\n" "$*" >> "$DATE_SET_LOG"; exit 0; fi\n'
        'exec /usr/bin/date "$@"\n')
    for prog in ('hwclock', 'date'):
        os.chmod(os.path.join(RTC_BIN, prog), 0o755)
    rtc_env = dict(os.environ, PATH=RTC_BIN + os.pathsep + os.environ['PATH'],
                   HWCLOCK_LOG=RTC_LOG, DATE_SET_LOG=DATE_LOG)

    open(RTC_SAVE, 'w').write('2026-10-10 10:00:00\n')
    open(os.path.join(RTC_SYS, 'date'), 'w').write('2026-10-11\n')
    open(os.path.join(RTC_SYS, 'time'), 'w').write('11:00:00\n')
    r = subprocess.run([helper_path, 'load'], env=rtc_env,
                       capture_output=True, text=True)
    hwlog = open(RTC_LOG).read() if os.path.exists(RTC_LOG) else ''
    ok(r.returncode == 0 and '--hctosys --utc' in hwlog and '--systohc' not in hwlog,
       'plausible RTC wird beim Boot tatsächlich als Systemzeit übernommen')

    open(RTC_LOG, 'w').close()
    open(os.path.join(RTC_SYS, 'date'), 'w').write('2000-01-01\n')
    r = subprocess.run([helper_path, 'load'], env=rtc_env,
                       capture_output=True, text=True)
    hwlog = open(RTC_LOG).read()
    ok(r.returncode == 0 and '--hctosys' not in hwlog and '--systohc --utc' in hwlog,
       'uninitialisierte RTC wird abgelehnt und aus dem Fallback initialisiert')
    datelog = open(DATE_LOG).read() if os.path.exists(DATE_LOG) else ''
    ok('-s 2026-10-10 10:00:00' in datelog,
       'Fallback-Pfad setzt vor der RTC-Initialisierung wirklich die Ersatzzeit')

    open(RTC_LOG, 'w').close()
    open(RTC_SAVE, 'w').write('ALT\n')
    r = subprocess.run([helper_path, 'save'], env=rtc_env,
                       capture_output=True, text=True)
    hwlog = open(RTC_LOG).read()
    ersatz = open(RTC_SAVE).read().strip()
    ok(r.returncode == 0 and '--systohc --utc' in hwlog and ersatz != 'ALT',
       'Speichern aktualisiert gleichzeitig DS3231 und SD-Fallback')

# ── Waechter, Rettung und Freigaben muessen im Bundle liegen ─────────────
# Diese Fehler waren stumm: ein Waechter, der den Ausfall nicht bemerkt, ein
# Speichern ohne Wirkung, ein Neustart ohne Recht. Bei einer frischen
# Installation muessen alle Teile von selbst ankommen.
for datei, beschreibung in [
        ('scripts/hdmi-wache.sh', 'Bildschirm-Waechter'),
        ('scripts/anzeige-rettung.sh', 'Anzeige-Rettung ohne Reboot'),
        ('scripts/sudoers-regeln.sh', 'Freigaben an einer Stelle'),
        ('scripts/selbsttest.sh', 'Selbsttest nach der Installation'),
        ('scripts/hdmi-fixieren.sh', 'Ausgaenge bleiben nach Standby aktiv'),
        ('scripts/kiosk-neu.sh', 'Nachziehen der Kiosk-Teile'),
        ('scripts/nach-pull.sh', 'Nachziehen nach git pull'),
]:
    ok(os.path.isfile(os.path.join(BASE, datei)),
       '%s liegt im Bundle (%s)' % (beschreibung, datei))

# install.sh muss die Freigaben aus der gemeinsamen Datei holen, nicht selbst
# welche schreiben - sonst laufen Installer und Update wieder auseinander.
ok('sudoers-regeln.sh' in _inst,
   'install.sh nutzt die gemeinsamen sudo-Regeln')
ok('selbsttest.sh' in _inst,
   'install.sh prueft sich zum Schluss selbst')

# Der Waechter muss den Fall kennen, der den Reboot gekostet hat.
_wache = open(os.path.join(BASE, 'scripts', 'hdmi-wache.sh'), encoding='utf-8').read()
ok("meldet nicht 'connected'" in _wache,
   'Waechter handelt auch, wenn der Ausgang sich abmeldet')
ok('sudo -n systemctl restart kiosk-screen2' in _wache,
   'Waechter startet den Kiosk mit Recht (sudo -n)')

print('\n%s%d Prüfungen bestanden, %d fehlgeschlagen'
      % ('OK – ' if failed == 0 else 'FEHLER – ', passed, failed))
sys.exit(1 if failed else 0)
