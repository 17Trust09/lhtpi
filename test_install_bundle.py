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
ok('ConditionPathExists=!${MARKER_FILE}' in text,
   'Ersteinrichtung läuft nur, solange nicht eingerichtet')
ok('ConditionPathExists=${MARKER_FILE}' in text,
   'Kiosk startet erst nach der Einrichtung')
ok('SCREEN2_FILE' in text and 'screen2' in text,
   'zweiter Bildschirm hat ein eigenes Merkmal')
ok('lhtpi-anzeige.path' in text and 'PathChanged=${SCREENS_FILE}' in text,
   'Pfad-Wächter reagiert auf Änderungen der Bildschirm-Anzahl')
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

print('\n13d) Autologin (Kiosk startet ohne Anmeldung)')

ok('configure_autologin' in text, 'Autologin-Schritt ist im Skript vorhanden')
ok('configure_autologin' in text.split('main()')[1],
   'Autologin ist in den Ablauf eingehängt')
ok('lhtpi-kiosk.desktop' in text,
   'Installer legt eine eigene Sitzung an (Name kann nicht falsch sein)')

LD = os.path.join(LZ, 'lightdm')
XS = os.path.join(LZ, 'xsessions')
os.makedirs(os.path.join(LD, 'lightdm.conf.d'), exist_ok=True)
os.makedirs(XS, exist_ok=True)
# So sieht es auf Raspberry Pi OS aus: Sitzung "rpd-x" (= "Raspberry Pi OS")
open(os.path.join(XS, 'rpd-x.desktop'), 'w').write(
    '[Desktop Entry]\nName=Raspberry Pi OS\nExec=/usr/bin/startlxde-pi\n')
CONF = os.path.join(LD, 'lightdm.conf')
open(CONF, 'w').write('[Seat:*]\n#autologin-user=\ngreeter-session=pi-greeter\n'
                      'autologin-user=falschernutzer\nautologin-session=wayland\n')
LDU = dict(UMG, LHTPI_LIGHTDM_DIR=LD, LHTPI_LIGHTDM_CONF=CONF,
           LHTPI_XSESSIONS_DIR=XS)
r = schritt('configure_autologin', env=LDU)
ok(r.returncode == 0, 'Autologin-Schritt bricht nicht ab')
inhalt = open(CONF).read()
ok('autologin-user=pi' in inhalt, 'Autologin-Benutzer steht in lightdm.conf')
ok('autologin-user=falschernutzer' not in inhalt.replace('#autologin-user=falschernutzer', ''),
   'widersprechende Benutzer-Zeile wurde auskommentiert')
ok('#autologin-session=wayland' in inhalt,
   'widersprechende Sitzung (wayland) wurde auskommentiert')
ok('user-session=rpd-x' in inhalt and 'autologin-session=rpd-x' in inhalt,
   'Sitzung wird aus den vorhandenen Sitzungsdateien übernommen (rpd-x)')
ok(inhalt.index('autologin-user=pi') < inhalt.index('greeter-session'),
   'Werte stehen in der [Seat:*]-Sektion (nicht am Dateiende)')
ok(inhalt.count('[Seat:*]') == 1, 'keine doppelte Sektion angelegt')
ok('user-session=rpd-x' in open(os.path.join(
    LD, 'lightdm.conf.d', '50-lhtpi-autologin.conf')).read(),
   'Drop-in steht auf derselben Sitzung')
ok('Sitzungsdatei vorhanden' in r.stdout,
   'Kontrolle bestätigt die Sitzungsdatei')
ok('LightDM verwendet' in r.stdout or 'Kontrolle nicht möglich' in r.stdout,
   'Ergebnis der LightDM-Kontrolle steht im Protokoll')

# Auf dem Pi ist openbox installiert -> der Installer nutzt seine EIGENE Sitzung
BIN = os.path.join(LZ, 'bin')
os.makedirs(BIN, exist_ok=True)
open(os.path.join(BIN, 'openbox-session'), 'w').write('#!/bin/sh\nexec openbox\n')
os.chmod(os.path.join(BIN, 'openbox-session'), 0o755)
CONF3 = os.path.join(LD, 'mit-openbox.conf')
open(CONF3, 'w').write('[Seat:*]\n#autologin-user=\n')
r = schritt('configure_autologin',
            env=dict(LDU, PATH=BIN + os.pathsep + LDU['PATH'],
                     LHTPI_LIGHTDM_CONF=CONF3))
ok('Eigene Sitzung angelegt: lhtpi-kiosk' in r.stdout,
   'mit openbox entsteht die eigene Sitzung lhtpi-kiosk')
ok('user-session=lhtpi-kiosk' in open(CONF3).read(),
   'lightdm.conf verweist auf die eigene Sitzung')
sitzungsdatei = os.path.join(XS, 'lhtpi-kiosk.desktop')
ok(os.path.exists(sitzungsdatei) and 'Exec=' in open(sitzungsdatei).read(),
   'Sitzungsdatei lhtpi-kiosk.desktop wurde angelegt')

# Ohne [Seat:*]-Sektion wird eine angelegt
CONF2 = os.path.join(LD, 'leer.conf')
open(CONF2, 'w').write('# noch nichts konfiguriert\n')
r = schritt('configure_autologin', env=dict(LDU, LHTPI_LIGHTDM_CONF=CONF2))
ok(r.returncode == 0 and 'autologin-user=pi' in open(CONF2).read(),
   'ohne Sektion wird [Seat:*] angelegt')

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

print('\n12) Knopf in der Safety-Cross-Admin-Seite')
sc_admin = os.path.join(BASE, 'tools/safety-cross/templates/admin.html')
if os.path.exists(sc_admin):
    inhalt = open(sc_admin).read()
    ok('Anzeigen-Einstellungen öffnen' in inhalt, 'SC-Admin hat einen Anzeigen-Knopf')
    ok(':8000/display' in inhalt, 'Knopf zeigt auf die Anzeigen-Seite')
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

print('\n%s%d Prüfungen bestanden, %d fehlgeschlagen'
      % ('OK – ' if failed == 0 else 'FEHLER – ', passed, failed))
sys.exit(1 if failed else 0)
