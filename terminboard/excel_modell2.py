"""Excel-Vorlage „Modell 2" lesen.

Blätter:
  * ``Termine``   – Nr | Art | Prüfstand | Von | Bis | Info | Status
    (Von und Bis sind **Datum ohne Uhrzeit**; Uhrzeiten stehen im Blatt
    ``Zeiten``, ein Block je Zeitraum.)
  * ``Zeiten``    – Termin | Von | Bis | Notiz   (optional, für Blöcke)
  * ``Prüfstände``– Kennung | Bezeichnung | Auswahl

Der Parser liefert nur Rohdaten (Dicts mit ``datetime``). Bewertet wird im
Import (:mod:`historie`), damit Fehler gesammelt und gemeldet werden können,
statt den ganzen Import zu verhindern.
"""
import os
from datetime import date, datetime, time

SPALTE_NR = 0
SPALTE_ART = 1
SPALTE_PRUEFSTAND = 2
SPALTE_VON = 3
SPALTE_BIS = 4
SPALTE_INFO = 5
SPALTE_STATUS = 6

TAGESENDE = time(23, 59)

# Schutz gegen riesige Dateien / Zip-Bomben (ein Stick ist kein Vertrauensbeweis)
MAX_BYTES = 20 * 1024 * 1024

FORMATE = (
    '%d.%m.%Y %H:%M',
    '%d.%m.%Y %H:%M:%S',
    '%Y-%m-%d %H:%M',
    '%Y-%m-%d %H:%M:%S',
    '%d.%m.%Y',
    '%Y-%m-%d',
)


def _zu_datetime(wert, als_ende=False):
    """Wandelt einen Zellwert in ``datetime``.

    Ein reines Datum wird zu 00:00 (Von) bzw. 23:59 (Bis) – so ist eine Zeile
    ohne Uhrzeit ein ganzer Tag statt eines Nullzeitraums.
    """
    if wert is None or (isinstance(wert, str) and not wert.strip()):
        return None
    if isinstance(wert, datetime):
        # Eine reine Datumszelle kommt aus openpyxl als datetime mit 00:00
        # zurueck. Ohne diese Unterscheidung waere "Bis" ebenfalls Mitternacht
        # und der Termin damit null Stunden lang.
        if als_ende and wert.time() == time(0, 0):
            return datetime.combine(wert.date(), TAGESENDE)
        return wert
    if isinstance(wert, date):
        return datetime.combine(wert, TAGESENDE if als_ende else time(0, 0))

    text = str(wert).strip()
    for fmt in FORMATE:
        try:
            geparst = datetime.strptime(text, fmt)
        except ValueError:
            continue
        # Reines Datumsformat → Tagesende für "Bis"
        if '%H' not in fmt and als_ende:
            return datetime.combine(geparst.date(), TAGESENDE)
        return geparst
    return None


def _zu_int(wert):
    if wert is None:
        return None
    try:
        return int(str(wert).strip())
    except (TypeError, ValueError):
        return None


def _text(wert):
    return '' if wert is None else str(wert).strip()


def _ist_leer(zeile):
    return zeile is None or all(c is None or str(c).strip() == '' for c in zeile)


def _ist_altes_format(zeile):
    """Kopfzeile der alten Vorlage: fünf Spalten ohne Nummer.

    Diese Fassung wird nicht mehr gelesen – sie würde spaltenweise verrutschen
    und falsche Termine anzeigen. Lieber eine klare Meldung.
    """
    return bool(zeile) and _text(zeile[0]).lower() in ('art', 'typ')


def _ist_kopfzeile(zeile):
    if not zeile:
        return False
    erste = _text(zeile[0]).lower()
    return erste in ('nr', 'nr.', 'nummer', 'art')


def lies_terminblatt(ws):
    """Liest das Blatt ``Termine``."""
    zeilen = []
    for index, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if _ist_leer(row):
            continue
        if index == 1 and _ist_kopfzeile(row):
            continue

        def zelle(spalte):
            return row[spalte] if spalte < len(row) else None

        nr = _zu_int(zelle(SPALTE_NR))
        if nr is None:
            nr = index          # fehlende Nummer → Zeilennummer als Bezug

        zeilen.append({
            'nr': nr,
            'art': _text(zelle(SPALTE_ART)),
            'pruefstand': _text(zelle(SPALTE_PRUEFSTAND)),
            'von': _zu_datetime(zelle(SPALTE_VON)),
            'bis': _zu_datetime(zelle(SPALTE_BIS), als_ende=True),
            'info': _text(zelle(SPALTE_INFO)),
            'status': _text(zelle(SPALTE_STATUS)) or 'offen',
            'excel_zeile': index,
        })
    return zeilen


def lies_zeitenblatt(ws):
    """Liest das Blatt ``Zeiten`` → ``({nr: [(von, bis), ...]}, [fehler])``."""
    bloecke = {}
    fehler = []
    for index, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if _ist_leer(row):
            continue
        if index == 1 and _text(row[0]).lower() in ('termin', 'termin (nr)', 'nr'):
            continue

        def zelle(spalte):
            return row[spalte] if spalte < len(row) else None

        nr = _zu_int(zelle(0))
        von = _zu_datetime(zelle(1))
        bis = _zu_datetime(zelle(2), als_ende=True)

        if nr is None or von is None or bis is None:
            fehler.append({'excel_zeile': index, 'grund': 'Termin/Von/Bis unvollständig'})
            continue
        if bis < von:
            fehler.append({'excel_zeile': index, 'grund': 'Bis liegt vor Von'})
            continue
        bloecke.setdefault(nr, []).append((von, bis))
    return bloecke, fehler


def lies_pruefstandblatt(ws):
    """Liest das Blatt ``Prüfstände`` → Liste der Auswahl-Strings."""
    namen = []
    for index, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if _ist_leer(row):
            continue
        if index == 1 and _text(row[0]).lower() in ('kennung', 'name', 'nr'):
            continue
        auswahl = _text(row[2]) if len(row) > 2 and row[2] is not None else ''
        if not auswahl:
            kennung = _text(row[0])
            bezeichnung = _text(row[1]) if len(row) > 1 else ''
            auswahl = f'{kennung} {bezeichnung}'.strip()
        if auswahl and auswahl not in namen:
            namen.append(auswahl)
    return namen


def lies_datei(pfad):
    """Liest eine Excel-Datei im Modell-2-Format.

    Liefert ``{'zeilen', 'bloecke', 'pruefstaende', 'fehler', 'dateiname'}``.
    """
    from openpyxl import load_workbook

    ergebnis = {
        'zeilen': [],
        'bloecke': {},
        'pruefstaende': [],
        'fehler': [],
        'dateiname': os.path.basename(pfad),
    }

    try:
        groesse = os.path.getsize(pfad)
    except OSError as fehler:
        ergebnis['fehler'].append({'grund': f'Datei nicht lesbar: {fehler}'})
        return ergebnis
    if groesse > MAX_BYTES:
        ergebnis['fehler'].append(
            {'grund': f'Datei zu groß ({groesse / 1024 / 1024:.1f} MB, erlaubt 20 MB)'})
        return ergebnis

    try:
        wb = load_workbook(pfad, data_only=True, read_only=True)
    except Exception as fehler:
        ergebnis['fehler'].append({'grund': f'Datei nicht lesbar: {fehler}'})
        return ergebnis

    # Formatprüfung an der Kopfzeile des Terminblatts
    blatt = wb['Termine'] if 'Termine' in wb.sheetnames else wb.worksheets[0]
    for zeile in blatt.iter_rows(values_only=True):
        if _ist_leer(zeile):
            continue
        if _ist_altes_format(zeile):
            wb.close()
            ergebnis['fehler'].append({
                'grund': 'Alte Vorlage erkannt (Spalte "Nr" fehlt). Bitte die '
                         'neue Vorlage verwenden – das alte Format wird nicht '
                         'mehr eingelesen.'})
            return ergebnis
        break
    try:
        if 'Termine' in wb.sheetnames:
            ergebnis['zeilen'] = lies_terminblatt(wb['Termine'])
        else:
            ws = wb.worksheets[0]
            ergebnis['zeilen'] = lies_terminblatt(ws)

        if 'Zeiten' in wb.sheetnames:
            bloecke, fehler = lies_zeitenblatt(wb['Zeiten'])
            ergebnis['bloecke'] = bloecke
            ergebnis['fehler'].extend(fehler)

        for name in wb.sheetnames:
            klein = name.lower()
            if klein.startswith('prüfst') or klein.startswith('pruefst'):
                ergebnis['pruefstaende'] = lies_pruefstandblatt(wb[name])
                break
    finally:
        wb.close()

    return ergebnis
