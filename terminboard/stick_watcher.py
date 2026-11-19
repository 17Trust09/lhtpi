"""Stick-Verarbeitung: Excel importieren und Berichte auslösen.

Läuft im Hintergrund, während das Board am Prüfstand steht. Aufgaben:

1. **Import** – liegt eine ``termine.xlsx`` auf dem Stick, wird sie in die
   Historie übernommen (Modell 3 mit Betriebsmittel-Abgleich, Terminen und
   News; Modell 2 als Fallback). Erkannt wird eine neue Fassung am Datei-Hash.
2. **Writeback/Archiv** – beim Modell 3 werden vergebene BM-Kennungen und die
   ausgeblendete BM-ID in die Datei zurückgeschrieben und abgeschlossene
   Zeilen archiviert. Nach dem Schreiben wird der neue Datei-Hash registriert,
   damit der Watcher seine eigene Änderung nicht erneut importiert.
3. **Bericht** – liegt zusätzlich ``LHTPi-Bericht.jetzt`` auf dem Stick,
   werden Monats- und Jahresbericht erzeugt und auf den Stick geschrieben.

Beides ist unschädlich, wenn kein Stick steckt. Ein nicht beschreibbarer
Stick lässt Import/Lesen weiter zu; der Writeback-Fehler wird gemeldet und
beim nächsten Durchlauf erneut versucht.
"""
import hashlib
import os
import subprocess
import threading
import time

from models import db
from historie import ImportLauf, importiere, importiere_modell3
from betriebsmittel_sync import sync_betriebsmittel
from archiv import verschiebe_abgeschlossene
from excel_writeback import wende_an
from excel_modell2 import lies_datei
from usb_source import find_usb_termin_dir, USB_XLSX_FILENAME, FIXED_MOUNT, _ist_modell3
from bericht import pruefe_stick_befehl, erstelle_berichte_automatisch

STANDARD_INTERVALL = 20      # Sekunden


def datei_hash(pfad):
    """SHA256 einer Datei ('' wenn nicht lesbar)."""
    h = hashlib.sha256()
    try:
        with open(pfad, 'rb') as fh:
            for block in iter(lambda: fh.read(65536), b''):
                h.update(block)
    except OSError:
        return ''
    return h.hexdigest()


def _zuletzt_importiert(dateiname, hashwert):
    """True, wenn genau dieser Dateiinhalt schon importiert wurde."""
    if not hashwert:
        return False
    treffer = (ImportLauf.query
               .filter_by(dateiname=dateiname, datei_hash=hashwert)
               .first())
    return treffer is not None


def _registriere_hash(dateiname, hashwert):
    """Merkt den aktuellen Dateiinhalt als verarbeitet (nach Writeback)."""
    lauf = ImportLauf(dateiname=dateiname, datei_hash=hashwert, zeilen=0,
                      bericht='writeback')
    db.session.add(lauf)
    db.session.commit()


def _usb_schreibrecht(schalten):
    """Schaltet den Stick beschreibbar bzw. wieder nur lesend."""
    helfer = '/usr/local/bin/lhtpi-usb-rw.sh'
    if not os.path.exists(helfer):
        return False
    try:
        lauf = subprocess.run(['sudo', '-n', helfer, schalten],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=30)
        return lauf.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _schreibbar(mount):
    """True, wenn in ``mount`` geschrieben werden darf.

    Pfade außerhalb des festen Mounts (z. B. Tests) gelten als beschreibbar;
    der echte Stick wird über den root-Helfer kurz auf rw geschaltet.
    """
    if os.path.abspath(mount) != FIXED_MOUNT:
        return True
    return _usb_schreibrecht('rw')


def _archiviere(mount, pfad):
    """Modell 2: verschiebt abgeschlossene Zeilen, wenn der Stick schreibbar ist."""
    probe = verschiebe_abgeschlossene(pfad, trocken=True)
    if not probe['verschoben']:
        return probe
    if not _usb_schreibrecht('rw'):
        return {'verschoben': [], 'fehler': 'Stick nicht beschreibbar', 'sicherung': None}
    try:
        return verschiebe_abgeschlossene(pfad)
    finally:
        _usb_schreibrecht('ro')


def _writeback_modell3(mount, pfad, writeback):
    """Modell 3: IDs/Archiv zurückschreiben, wenn der Stick beschreibbar ist."""
    probe = wende_an(pfad, writeback, trocken=True)
    if not probe['geaendert']:
        return probe
    if not _schreibbar(mount):
        return {'geaendert': False, 'verschoben': [],
                'fehler': 'Stick nicht beschreibbar', 'sicherung': None}
    try:
        return wende_an(pfad, writeback)
    finally:
        if os.path.abspath(mount) == FIXED_MOUNT:
            _usb_schreibrecht('ro')


def _verarbeite_modell3(pfad, mount, ergebnis, erzwinge):
    """Modell-3-Durchlauf: Abgleich → Import → Writeback/Archiv → Hash merken."""
    from excel_modell3 import lies_datei

    hashwert = datei_hash(pfad)
    daten = lies_datei(pfad)

    # Der Betriebsmittel-Abgleich läuft bei jedem Durchlauf (idempotent), damit
    # vergebene IDs auch dann geschrieben werden, wenn der Import wegen
    # unverändertem Hash übersprungen wurde.
    sync_report = sync_betriebsmittel(daten.get('betriebsmittel') or [])

    geaendert = False
    report = None
    if erzwinge or not _zuletzt_importiert(USB_XLSX_FILENAME, hashwert):
        report = importiere_modell3(
            daten, dateiname=USB_XLSX_FILENAME, datei_hash=hashwert)
        report['sync'] = sync_report
        ergebnis['importiert'] = True
        ergebnis['report'] = report
        geaendert = (report['neu'] + report['geaendert'] +
                     report['entfernt']) > 0

    writeback = list(sync_report['writeback'])

    wb_ergebnis = _writeback_modell3(mount, pfad, writeback)
    if wb_ergebnis['geaendert'] or wb_ergebnis['verschoben'] or wb_ergebnis['fehler']:
        if ergebnis['report'] is None:
            ergebnis['report'] = {}
        ergebnis['report']['writeback'] = wb_ergebnis
        if wb_ergebnis['geaendert'] and not wb_ergebnis['fehler']:
            # Die Datei hat sich durch das Zurückschreiben geändert – der neue
            # Hash darf beim nächsten Durchlauf keinen erneuten Import auslösen.
            _registriere_hash(USB_XLSX_FILENAME, datei_hash(pfad))
            geaendert = True

    if geaendert:
        ergebnis['bericht'] = erstelle_berichte_automatisch(mount)


def _verarbeite_modell2(pfad, mount, ergebnis, erzwinge):
    """Modell-2-Durchlauf (bisheriges Verhalten)."""
    hashwert = datei_hash(pfad)
    geaendert = False
    if erzwinge or not _zuletzt_importiert(USB_XLSX_FILENAME, hashwert):
        daten = lies_datei(pfad)
        report = importiere(
            daten['zeilen'],
            bloecke=daten['bloecke'],
            dateiname=USB_XLSX_FILENAME,
            datei_hash=hashwert,
        )
        report['parser_fehler'] = daten['fehler']
        geaendert = (report['neu'] + report['geaendert'] +
                     report['entfernt']) > 0

        ergebnis['importiert'] = True
        ergebnis['report'] = report

    archiv = _archiviere(mount, pfad)
    if archiv['verschoben']:
        geaendert = True
    if archiv['verschoben'] or archiv['fehler']:
        if ergebnis['report'] is None:
            ergebnis['report'] = {}
        ergebnis['report']['archiv'] = archiv

    if geaendert:
        ergebnis['bericht'] = erstelle_berichte_automatisch(mount)


def verarbeite_stick(mount_dir=None, erzwinge=False):
    """Ein Durchlauf: importieren und Bericht auslösen.

    Liefert ``{'stick': bool, 'importiert': bool, 'report': dict|None,
    'bericht': dict|None}``.
    """
    ergebnis = {'stick': False, 'importiert': False, 'report': None, 'bericht': None}

    mount = mount_dir or find_usb_termin_dir()
    if not mount or not os.path.isdir(mount):
        return ergebnis
    ergebnis['stick'] = True

    xlsx = os.path.join(mount, USB_XLSX_FILENAME)
    if os.path.isfile(xlsx):
        if _ist_modell3(xlsx):
            _verarbeite_modell3(xlsx, mount, ergebnis, erzwinge)
        else:
            _verarbeite_modell2(xlsx, mount, ergebnis, erzwinge)

    # Manuelle Ausloese-Datei bleibt als zusätzlicher Weg erhalten.
    bericht = pruefe_stick_befehl(mount)
    if bericht['ausgeloest']:
        ergebnis['bericht'] = bericht

    return ergebnis


def starte_hintergrundpruefung(app, intervall=STANDARD_INTERVALL):
    """Startet einen Daemon-Thread, der den Stick regelmäßig prüft."""
    def schleife():
        while True:
            ctx = app.app_context()
            ctx.push()
            try:
                verarbeite_stick()
            except Exception as fehler:     # darf den Kiosk nie stoppen
                app.logger.warning('Stick-Verarbeitung fehlgeschlagen: %s', fehler)
            finally:
                try:
                    db.session.remove()
                except Exception:
                    pass
                ctx.pop()
            time.sleep(intervall)

    thread = threading.Thread(target=schleife, name='stick-watcher', daemon=True)
    thread.start()
    return thread
