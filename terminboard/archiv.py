"""Abgeschlossene Termine/News ins Archiv verschieben.

Warum das Geraet das selbst macht: Wer jeden Monat von Hand Zeilen verschiebt,
vergisst es irgendwann - und dann stehen erledigte Kalibrierungen weiter als
offen im Kiosk.

Regeln (für beide Modelle):

* Eine Zeile wandert nur, wenn der Status ``abgeschlossen`` ist.
* Die Nummer bleibt - der Pi erkennt Einträge an der Nummer, nicht an der Zeile.
* Vorausgefüllte Leerzeilen (nur Nummer, sonst nichts) werden übersprungen.
* Die Zeile wird aus dem Quell-Blatt geloescht, es bleiben keine Luecken.
* Vor dem Schreiben entsteht eine Sicherung ``<datei>.bak``.
* Schlaegt etwas fehl, bleibt die Datei unveraendert.

Modell 2 verschiebt ``Termine`` → ``Archiv`` (7 Spalten A–G), Modell 3
verschiebt ``Termine`` → ``Archiv Termine`` (9 Spalten A–I) und
``News & Audits`` → ``Archiv News & Audits`` (7 Spalten A–G).
"""
import os
import shutil

# Modell 2
TERMINE_BLATT = 'Termine'
ARCHIV_BLATT = 'Archiv'
SPALTE_STATUS = 7            # G
SPALTE_NR = 1                # A
SPALTEN_TERMINE = 7          # A-G

# Modell 3
TERMINE_BLATT_M3 = 'Termine'
ARCHIV_TERMINE_M3 = 'Archiv Termine'
NEWS_BLATT_M3 = 'News & Audits'
ARCHIV_NEWS_M3 = 'Archiv News & Audits'
SPALTE_STATUS_M3 = 8         # H (Termine) / G (News)
SPALTE_STATUS_NEWS = 7       # G
SPALTEN_TERMINE_M3 = 9       # A-I (I = ausgeblendete Betriebsmittel-ID)
SPALTEN_NEWS = 7             # A-G


def _wert_gefuehlt(wert):
    return wert is not None and str(wert).strip() != ''


def _hat_inhalt(ws, zeile, spalten, spalte_nr):
    """True, wenn die Zeile echten Inhalt (mehr als nur die Nummer) hat."""
    for spalte in range(1, spalten + 1):
        if spalte == spalte_nr:
            continue
        if _wert_gefuehlt(ws.cell(row=zeile, column=spalte).value):
            return True
    return False


def _verschiebe_im_wb(wb, quelle, ziel, spalten, spalte_status, spalte_nr,
                      trocken=False):
    """Verschiebt abgeschlossene Zeilen eines Blatts ins Ziel-Blatt (in-memory).

    Kopiert genau ``spalten`` Spalten, überspringt vorausgefüllte Leerzeilen
    und vermeidet Duplikate. Liefert die Liste der verschobenen Nummern.
    """
    if quelle not in wb.sheetnames:
        return []
    ws = wb[quelle]
    if ziel in wb.sheetnames:
        archiv = wb[ziel]
    else:
        archiv = wb.create_sheet(ziel)
        archiv.append([ws.cell(row=1, column=spalte).value
                       for spalte in range(1, spalten + 1)])

    # Nummern, die schon im Archiv stehen (nur Zeilen mit echtem Inhalt).
    schon_archiviert = set()
    for zeile in range(2, archiv.max_row + 1):
        if not _hat_inhalt(archiv, zeile, spalten, spalte_nr):
            continue
        nr = archiv.cell(row=zeile, column=spalte_nr).value
        if _wert_gefuehlt(nr):
            schon_archiviert.add(str(nr).strip())

    zu_loeschen = []
    for zeile in range(2, ws.max_row + 1):
        if not _hat_inhalt(ws, zeile, spalten, spalte_nr):
            continue
        status = ws.cell(row=zeile, column=spalte_status).value
        if str(status or '').strip().lower() != 'abgeschlossen':
            continue
        nr = ws.cell(row=zeile, column=spalte_nr).value
        if not _wert_gefuehlt(nr) or str(nr).strip() in schon_archiviert:
            continue
        zu_loeschen.append(zeile)

    if not zu_loeschen:
        return []

    # Erste freie Zeile im Ziel (direkt unter der Kopfzeile bzw. der ersten
    # vorausgefüllten Leerzeile). NICHT ``append`` – die Vorlage hat viele
    # vorformatierte Leerzeilen.
    ziel_zeile = 2
    for zeile in range(2, archiv.max_row + 1):
        if not _hat_inhalt(archiv, zeile, spalten, spalte_nr):
            ziel_zeile = zeile
            break
    else:
        ziel_zeile = archiv.max_row + 1

    verschoben = []
    for zeile in zu_loeschen:
        werte = [ws.cell(row=zeile, column=spalte).value
                 for spalte in range(1, spalten + 1)]
        for spalte, wert in enumerate(werte, start=1):
            archiv.cell(row=ziel_zeile, column=spalte, value=wert)
        ziel_zeile += 1
        verschoben.append(werte[spalte_nr - 1])

    if trocken:
        return verschoben

    # Von unten nach oben: Loeschen verschiebt sonst die Indizes darunter.
    for zeile in reversed(zu_loeschen):
        ws.delete_rows(zeile, 1)
    return verschoben


def _speichere_sicher(pfad, wb, ergebnis):
    """Sichert die Datei, speichert und rollt bei Fehlern zurück."""
    sicherung = pfad + '.bak'
    try:
        shutil.copy2(pfad, sicherung)
        ergebnis['sicherung'] = sicherung
    except OSError as fehler:
        ergebnis['fehler'] = 'Sicherung nicht moeglich: %s' % fehler
        return False
    try:
        wb.save(pfad)
        return True
    except Exception as fehler:                      # noqa: BLE001
        try:
            shutil.copy2(sicherung, pfad)
            ergebnis['fehler'] = ('Schreiben fehlgeschlagen, zurueckgerollt: '
                                  '%s' % fehler)
        except OSError:
            ergebnis['fehler'] = 'Schreiben fehlgeschlagen: %s' % fehler
        ergebnis['verschoben'] = []
        return False


def verschiebe_abgeschlossene(pfad, trocken=False):
    """Modell 2: verschiebt abgeschlossene Zeilen ``Termine`` → ``Archiv``."""
    ergebnis = {'verschoben': [], 'fehler': None, 'sicherung': None}

    if not os.path.isfile(pfad):
        ergebnis['fehler'] = 'Datei nicht gefunden'
        return ergebnis

    try:
        from openpyxl import load_workbook
        wb = load_workbook(pfad)
    except Exception as fehler:                      # noqa: BLE001
        ergebnis['fehler'] = 'Datei nicht lesbar: %s' % fehler
        return ergebnis

    if TERMINE_BLATT not in wb.sheetnames:
        ergebnis['fehler'] = 'Blatt "Termine" fehlt'
        return ergebnis

    ergebnis['verschoben'] = _verschiebe_im_wb(
        wb, TERMINE_BLATT, ARCHIV_BLATT, SPALTEN_TERMINE,
        SPALTE_STATUS, SPALTE_NR, trocken=trocken)

    if trocken or not ergebnis['verschoben']:
        return ergebnis

    _speichere_sicher(pfad, wb, ergebnis)
    return ergebnis


def verschiebe_modell3_im_wb(wb, trocken=False):
    """Modell 3: verschiebt beide Paare in der offenen Arbeitsmappe.

    ``Termine`` → ``Archiv Termine`` (9 Spalten) und
    ``News & Audits`` → ``Archiv News & Audits`` (7 Spalten). Liefert die
    Liste der verschobenen Nummern (T-… und N-…).
    """
    verschoben = []
    verschoben += _verschiebe_im_wb(
        wb, TERMINE_BLATT_M3, ARCHIV_TERMINE_M3, SPALTEN_TERMINE_M3,
        SPALTE_STATUS_M3, SPALTE_NR, trocken=trocken)
    verschoben += _verschiebe_im_wb(
        wb, NEWS_BLATT_M3, ARCHIV_NEWS_M3, SPALTEN_NEWS,
        SPALTE_STATUS_NEWS, SPALTE_NR, trocken=trocken)
    return verschoben


def verschiebe_modell3(pfad, trocken=False):
    """Modell 3: verschiebt beide Paare in der Datei (mit Sicherung/Rollback)."""
    ergebnis = {'verschoben': [], 'fehler': None, 'sicherung': None}

    if not os.path.isfile(pfad):
        ergebnis['fehler'] = 'Datei nicht gefunden'
        return ergebnis

    try:
        from openpyxl import load_workbook
        wb = load_workbook(pfad)
    except Exception as fehler:                      # noqa: BLE001
        ergebnis['fehler'] = 'Datei nicht lesbar: %s' % fehler
        return ergebnis

    ergebnis['verschoben'] = verschiebe_modell3_im_wb(wb, trocken=trocken)

    if trocken or not ergebnis['verschoben']:
        return ergebnis

    _speichere_sicher(pfad, wb, ergebnis)
    return ergebnis
