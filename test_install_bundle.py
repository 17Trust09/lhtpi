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

print('\n8) Altlasten')
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
