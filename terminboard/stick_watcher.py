"""Stick-Verarbeitung: Excel importieren und Berichte auslösen.

Läuft im Hintergrund, während das Board am Prüfstand steht. Zwei Aufgaben:

1. **Import** – liegt eine ``termine.xlsx`` auf dem Stick, wird sie in die
   Historie übernommen. Erkannt wird eine neue Fassung am Datei-Hash, damit
   nicht bei jedem Durchlauf derselbe Stand verarbeitet wird.
2. **Bericht** – liegt zusätzlich ``LHTPi-Bericht.jetzt`` auf dem Stick,
   werden Monats- und Jahresbericht erzeugt und auf den Stick geschrieben.

Beides ist unschädlich, wenn kein Stick steckt.
"""
import hashlib
import os
import threading
import time

from models import db
from historie import ImportLauf, importiere
from excel_modell2 import lies_datei
from usb_source import find_usb_termin_dir, USB_XLSX_FILENAME
from bericht import pruefe_stick_befehl

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
        hashwert = datei_hash(xlsx)
        if erzwinge or not _zuletzt_importiert(USB_XLSX_FILENAME, hashwert):
            daten = lies_datei(xlsx)
            report = importiere(
                daten['zeilen'],
                bloecke=daten['bloecke'],
                dateiname=USB_XLSX_FILENAME,
                datei_hash=hashwert,
            )
            # Parser-Fehler (z. B. kaputte Zeile im Blatt „Zeiten") mitgeben
            report['parser_fehler'] = daten['fehler']
            ergebnis['importiert'] = True
            ergebnis['report'] = report

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
                # Session auch nach einem Fehler schließen, sonst bleibt die
                # thread-lokale Session vergiftet und der Watcher läuft nie
                # wieder an.
                try:
                    db.session.remove()
                except Exception:
                    pass
                ctx.pop()
            time.sleep(intervall)

    thread = threading.Thread(target=schleife, name='stick-watcher', daemon=True)
    thread.start()
    return thread
