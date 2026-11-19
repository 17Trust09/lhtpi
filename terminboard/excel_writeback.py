"""Sicheres Zurückschreiben in die Excel-Datei (Modell 3).

Fasst die Schreiboperationen des Geräts in **einer** atomaren Änderung zusammen:

* BM-Kennungen in ``Betriebsmittel!A`` (für Zeilen mit bisher leerer ID),
* das Archivieren abgeschlossener Zeilen (nutzt die Archiv-Logik aus
  :mod:`archiv`, statt einen zweiten Schreiber zu pflegen).

Die ausgeblendete BM-ID-Spalte ``Termine!I`` / ``Archiv Termine!I`` wird
**bewusst nicht** beschrieben: dort stehen INDEX/VERGLEICH-Formeln, die ein
statischer Wert zerstören würde. Der Parser löst eine leere Formel-Zelle über
Name/Typ auf, ein Schreibauftrag für Spalte I entfällt.

Ablauf: in eine temporäre Datei schreiben → neu laden und prüfen → erst dann
atomar ersetzen. Vor dem Ersetzen entsteht ``<datei>.bak``; schlägt irgendetwas
fehl, wird zurückgerollt. Ist nichts zu ändern, bleibt die Datei unberührt
(kein Selbst-Auslösen des Import-Hash-Wechsels).
"""
import os
import shutil

from archiv import verschiebe_modell3_im_wb

BM_ID_SPALTE = 1            # Betriebsmittel!A


def _spalte_fuer(blatt):
    if blatt == 'Betriebsmittel':
        return BM_ID_SPALTE
    return None


def _pruefen(pfad):
    """Lädt eine Datei neu und meldet nur strukturelle (fatale) Fehler."""
    from excel_modell3 import lies_datei
    daten = lies_datei(pfad)
    for fehler in daten.get('fehler', []):
        grund = fehler.get('grund', '')
        if 'Datei nicht lesbar' in grund or 'Datei zu groß' in grund:
            return grund
    return None


def wende_an(pfad, writeback=None, trocken=False):
    """Wendet ``writeback`` (Liste von ``{blatt, excel_zeile, kennung}``) und
    die Archivierung auf eine Modell-3-Datei an.

    Liefert ``{'geaendert', 'verschoben', 'fehler', 'sicherung'}``.
    """
    ergebnis = {'geaendert': False, 'verschoben': [], 'fehler': None,
                'sicherung': None}
    writeback = writeback or []

    if not os.path.isfile(pfad):
        ergebnis['fehler'] = 'Datei nicht gefunden'
        return ergebnis

    try:
        from openpyxl import load_workbook
        wb = load_workbook(pfad)
    except Exception as fehler:                      # noqa: BLE001
        ergebnis['fehler'] = 'Datei nicht lesbar: %s' % fehler
        return ergebnis

    try:
        geaendert = False

        # 1. BM-Kennungen schreiben (nur Betriebsmittel!A).
        for eintrag in writeback:
            kennung = eintrag.get('kennung')
            blatt = eintrag.get('blatt')
            spalte = _spalte_fuer(blatt)
            if spalte is None or blatt not in wb.sheetnames:
                continue
            zelle = wb[blatt].cell(row=eintrag.get('excel_zeile'), column=spalte)
            if zelle.value != kennung:
                zelle.value = kennung
                geaendert = True

        # 2. Archivieren (abgeschlossene Zeilen verschieben).
        verschoben = verschiebe_modell3_im_wb(wb, trocken=trocken)
        ergebnis['verschoben'] = verschoben
        if verschoben:
            geaendert = True

        if trocken or not geaendert:
            ergebnis['geaendert'] = geaendert
            return ergebnis

        # 3. In eine temporäre Datei schreiben und prüfen.
        tmp = pfad + '.tmp.xlsx'
        wb.save(tmp)
        fatal = _pruefen(tmp)
        if fatal:
            ergebnis['fehler'] = 'Prüfung fehlgeschlagen: %s' % fatal
            try:
                os.remove(tmp)
            except OSError:
                pass
            return ergebnis

        # 4. Sichern und atomar ersetzen.
        sicherung = pfad + '.bak'
        try:
            shutil.copy2(pfad, sicherung)
            ergebnis['sicherung'] = sicherung
            os.replace(tmp, pfad)
            ergebnis['geaendert'] = True
        except OSError as fehler:
            # Rollback auf die Sicherung, falls schon gesichert wurde.
            if os.path.isfile(sicherung):
                try:
                    shutil.copy2(sicherung, pfad)
                except OSError:
                    pass
            ergebnis['fehler'] = 'Schreiben fehlgeschlagen: %s' % fehler
            try:
                os.remove(tmp)
            except OSError:
                pass
    finally:
        try:
            wb.close()
        except Exception:                            # noqa: BLE001
            pass
    return ergebnis
