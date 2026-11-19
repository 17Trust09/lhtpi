"""Excel-Vorlage „Modell 3" lesen.

Blätter (feste Spaltenanzahl je Schema):

  * ``Termine``            – Nr | Art | Typ | Betriebsmittel | Von | Bis | Info
                             | Status | Betriebsmittel-ID (ausgeblendet)
  * ``News & Audits``      – Nr | Art | Titel | Von | Bis | Info | Status
  * ``Betriebsmittel``     – ID | Typ | Bezeichnung | Zusammenführen mit | Hinweis
  * ``Zeiten``             – Termin-Nr. | Von | Bis | Notiz
  * ``Archiv Termine``     – Schema wie ``Termine``
  * ``Archiv News & Audits`` – Schema wie ``News & Audits``

Nummern sind Zeichenketten mit festem Muster: ``T-001`` … ``T-500`` (Termine/
Zeiten), ``N-001`` … ``N-500`` (News) und ``BM-001`` … (Betriebsmittel). Art,
Typ und Status haben feste Wertemengen; Verstöße werden als Fehler gemeldet, die
Zeile bleibt aber erhalten (nur strukturell kaputte Zeilen werden übersprungen).

Rückgabe von :func:`lies_datei` (immer ein Dict mit allen Schlüsseln)::

    {
        'termine': [ {
            'nr', 'art', 'typ', 'betriebsmittel', 'betriebsmittel_id',
            'von', 'bis', 'info', 'status', 'excel_zeile'
        }, ... ],
        'news': [ {
            'nr', 'art', 'titel', 'von', 'bis', 'info', 'status', 'excel_zeile'
        }, ... ],
        'bloecke': { 'T-001': [(von_datetime, bis_datetime), ...], ... },
        'betriebsmittel': [ {
            'id', 'typ', 'bezeichnung', 'zusammenfuehren_mit', 'hinweis',
            'excel_zeile'
        }, ... ],
        'archiv_termine': [ ... wie 'termine' ... ],
        'archiv_news':    [ ... wie 'news' ... ],
        'fehler': [ {'grund': str, 'blatt': str?, 'excel_zeile': int?}, ... ],
        'dateiname': str,
    }

Datumsverhalten wie Modell 2: ``Von`` ist Tagesbeginn, ``Bis`` ist Tagesende;
ein leeres ``Bis`` bei Terminen bedeutet „endet am selben Tag". Bei News bleibt
ein leeres ``Bis`` ``None`` (für Hinweise nicht relevant). ``betriebsmittel_id``
ist die ausgeblendete ID (bei einer per Formel ermittelten Zelle der von Excel
gespeicherte Wert, sonst ``None``).

Der Parser meldet Fehler, statt den Import abzubrechen:

  * ungültige/fehlende Nummer (Termine/News) → Zeile übersprungen
  * fehlendes oder unlesbares ``Von`` → Zeile übersprungen
  * ungültige Art/Typ/Status → Zeile bleibt, Fehler gemeldet
  * unbekanntes Betriebsmittel → Zeile bleibt, Fehler gemeldet
  * doppelte T-/N-Nummer über aktiv+Archiv → Fehler gemeldet
  * doppeltes Betriebsmittel (Typ+Bezeichnung normalisiert) → Fehler gemeldet
  * ``Zeiten``: keine gültige T-Nummer, unbekannte Nummer oder Bis vor Von
    → Block übersprungen, Fehler gemeldet
"""
import os
import re
from datetime import date, datetime, time

# ── Spaltenpositionen (0-basiert) ─────────────────────────────────────────────
SPALTE_NR = 0
SPALTE_ART = 1
SPALTE_TYP = 2
SPALTE_BETRIEBSMITTEL = 3
SPALTE_VON = 4
SPALTE_BIS = 5
SPALTE_INFO = 6
SPALTE_STATUS = 7
SPALTE_BM_ID = 8

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

NUMMER_T = re.compile(r'T-\d{3}')
NUMMER_N = re.compile(r'N-\d{3}')
NUMMER_BM = re.compile(r'BM-\d{3}')

ARTEN_TERMINE = {'Kalibrierung', 'Wartung', 'Ausfall'}
ARTEN_NEWS = {'Audit', 'Info'}
TYPEN = {'Prüfstand', 'Konsole'}
STATUS = {'offen', 'abgeschlossen'}

# Nur diese Spalten gehören zu den Daten – rechts daneben darf nichts als
# Datensatz gelesen werden (Legenden o. Ä.).
SPALTEN_TERMINE = 9           # A–I (I = ausgeblendete Betriebsmittel-ID)
SPALTEN_NEWS = 7              # A–G
SPALTEN_BM = 5                # A–E
SPALTEN_ZEITEN = 4            # A–D


def _zu_datetime(wert, als_ende=False):
    """Wandelt einen Zellwert in ``datetime``.

    Ein reines Datum wird zu 00:00 (Von) bzw. 23:59 (Bis) – so ist eine Zeile
    ohne Uhrzeit ein ganzer Tag statt eines Nullzeitraums.
    """
    if wert is None or (isinstance(wert, str) and not wert.strip()):
        return None
    if isinstance(wert, datetime):
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
        if '%H' not in fmt and als_ende:
            return datetime.combine(geparst.date(), TAGESENDE)
        return geparst
    return None


def _text(wert):
    return '' if wert is None else str(wert).strip()


def _ist_leer(zeile):
    return zeile is None or all(c is None or str(c).strip() == '' for c in zeile)


def _ist_kopfzeile(zeile):
    if not zeile:
        return False
    erste = _text(zeile[0]).lower()
    return erste in ('nr', 'nr.', 'nummer', 'art', 'id', 'termin-nr.')


def _duplikate(paare, fehler):
    """Meldet doppelte Nummern. ``paare``: ``[(nr, blatt, zeile), ...]``."""
    gesehen = {}
    for nr, blatt, zeile in paare:
        if nr in gesehen:
            fehler.append({
                'blatt': blatt,
                'excel_zeile': zeile,
                'grund': 'Doppelte Nummer %s (bereits in %s)' % (nr, gesehen[nr]),
            })
        else:
            gesehen[nr] = '%s Zeile %d' % (blatt, zeile)


def lies_terminblatt(ws, bm_namen, bm_nach_id, blatt='Termine'):
    """Liest ein Blatt im Termine-Schema (``Termine`` / ``Archiv Termine``).

    ``bm_namen``: Menge normalisierter Bezeichnungen, ``bm_nach_id``: Abbildung
    ``id (casefold) → Betriebsmittel-Eintrag``. Eine vorhandene Betriebsmittel-ID
    (Spalte I) ist die primäre Identität: sie muss in den Stammdaten existieren
    und zu Name/Typ der Zeile passen. Eine leere ID bleibt für neue Zeilen
    erlaubt (dann zählt der Name).
    """
    zeilen = []
    fehler = []

    def zelle(spalte, row):
        return row[spalte] if spalte < len(row) else None

    for index, row in enumerate(
            ws.iter_rows(min_col=1, max_col=SPALTEN_TERMINE, values_only=True),
            start=1):
        if _ist_leer(row):
            continue
        if index == 1 and _ist_kopfzeile(row):
            continue

        nr = _text(zelle(SPALTE_NR, row))
        art = _text(zelle(SPALTE_ART, row))
        typ = _text(zelle(SPALTE_TYP, row))
        bm = _text(zelle(SPALTE_BETRIEBSMITTEL, row))
        info = _text(zelle(SPALTE_INFO, row))
        status = _text(zelle(SPALTE_STATUS, row))
        bm_id = _text(zelle(SPALTE_BM_ID, row))
        von_wert = _zu_datetime(zelle(SPALTE_VON, row))
        bis_wert = _zu_datetime(zelle(SPALTE_BIS, row), als_ende=True)

        # Nur die vorausgefüllte Nummer, sonst nichts → keine Zeile (Einladung
        # zum Ausfüllen, kein Termin).
        if not any((art, typ, bm, info, status, bm_id)) and \
                von_wert is None and bis_wert is None:
            continue

        if not NUMMER_T.fullmatch(nr):
            fehler.append({'blatt': blatt, 'excel_zeile': index,
                           'grund': 'Ungültige Nummer %r' % nr})
            continue

        von = von_wert
        bis = bis_wert
        if von is None:
            fehler.append({'blatt': blatt, 'excel_zeile': index,
                           'grund': 'Von fehlt oder ist ungültig'})
            continue
        if bis is None:
            bis = datetime.combine(von.date(), TAGESENDE)

        if art and art not in ARTEN_TERMINE:
            fehler.append({'blatt': blatt, 'excel_zeile': index,
                           'grund': 'Ungültige Art %r' % art})
        if typ and typ not in TYPEN:
            fehler.append({'blatt': blatt, 'excel_zeile': index,
                           'grund': 'Ungültiger Typ %r' % typ})
        if status and status not in STATUS:
            fehler.append({'blatt': blatt, 'excel_zeile': index,
                           'grund': 'Ungültiger Status %r' % status})
        # Betriebsmittel-ID (Spalte I) ist, wenn vorhanden, die primäre Identität:
        # sie muss in den Stammdaten existieren und zu Name/Typ der Zeile passen.
        # Eine leere ID bleibt für neue, noch nicht zugeordnete Zeilen erlaubt –
        # dann zählt der Name wie bisher.
        if bm_id:
            if not NUMMER_BM.fullmatch(bm_id):
                fehler.append({'blatt': blatt, 'excel_zeile': index,
                               'grund': 'Ungültige Betriebsmittel-ID %r' % bm_id})
            elif bm_id.casefold() not in bm_nach_id:
                fehler.append({'blatt': blatt, 'excel_zeile': index,
                               'grund': 'Unbekannte Betriebsmittel-ID %r' % bm_id})
            else:
                eintrag = bm_nach_id[bm_id.casefold()]
                if bm and eintrag['bezeichnung'] and \
                        bm.casefold() != eintrag['bezeichnung'].casefold():
                    fehler.append({
                        'blatt': blatt, 'excel_zeile': index,
                        'grund': 'Betriebsmittel-ID %s gehört zu %r, nicht zu %r'
                                 % (bm_id, eintrag['bezeichnung'], bm)})
                if typ and eintrag['typ'] and typ != eintrag['typ']:
                    fehler.append({
                        'blatt': blatt, 'excel_zeile': index,
                        'grund': 'Betriebsmittel-ID %s hat Typ %r, nicht %r'
                                 % (bm_id, eintrag['typ'], typ)})
        elif bm and bm.casefold() not in bm_namen:
            fehler.append({'blatt': blatt, 'excel_zeile': index,
                           'grund': 'Unbekanntes Betriebsmittel %r' % bm})

        zeilen.append({
            'nr': nr,
            'art': art,
            'typ': typ,
            'betriebsmittel': bm,
            'betriebsmittel_id': bm_id or None,
            'von': von,
            'bis': bis,
            'info': info,
            'status': status or 'offen',
            'excel_zeile': index,
        })
    return zeilen, fehler


def lies_newsblatt(ws, blatt='News & Audits'):
    """Liest ein Blatt im News-Schema (``News & Audits`` / Archiv)."""
    zeilen = []
    fehler = []

    def zelle(spalte, row):
        return row[spalte] if spalte < len(row) else None

    for index, row in enumerate(
            ws.iter_rows(min_col=1, max_col=SPALTEN_NEWS, values_only=True),
            start=1):
        if _ist_leer(row):
            continue
        if index == 1 and _ist_kopfzeile(row):
            continue

        nr = _text(zelle(0, row))
        art = _text(zelle(1, row))
        titel = _text(zelle(2, row))
        info = _text(zelle(5, row))
        status = _text(zelle(6, row))
        von_wert = _zu_datetime(zelle(3, row))
        bis_wert = _zu_datetime(zelle(4, row), als_ende=True)

        if not any((art, titel, info, status)) and \
                von_wert is None and bis_wert is None:
            continue

        if not NUMMER_N.fullmatch(nr):
            fehler.append({'blatt': blatt, 'excel_zeile': index,
                           'grund': 'Ungültige Nummer %r' % nr})
            continue

        von = von_wert
        if von is None:
            fehler.append({'blatt': blatt, 'excel_zeile': index,
                           'grund': 'Von fehlt oder ist ungültig'})
            continue
        # Leeres Bis bleibt bei News None (für Hinweise nicht relevant).
        bis = bis_wert

        if art and art not in ARTEN_NEWS:
            fehler.append({'blatt': blatt, 'excel_zeile': index,
                           'grund': 'Ungültige Art %r' % art})
        if status and status not in STATUS:
            fehler.append({'blatt': blatt, 'excel_zeile': index,
                           'grund': 'Ungültiger Status %r' % status})

        zeilen.append({
            'nr': nr,
            'art': art,
            'titel': titel,
            'von': von,
            'bis': bis,
            'info': info,
            'status': status or 'offen',
            'excel_zeile': index,
        })
    return zeilen, fehler


def lies_betriebsmittelblatt(ws):
    """Liest das Blatt ``Betriebsmittel`` → ``(zeilen, fehler)``."""
    zeilen = []
    fehler = []

    def zelle(spalte, row):
        return row[spalte] if spalte < len(row) else None

    for index, row in enumerate(
            ws.iter_rows(min_col=1, max_col=SPALTEN_BM, values_only=True),
            start=1):
        if _ist_leer(row):
            continue
        if index == 1 and _ist_kopfzeile(row):
            continue

        bm_id = _text(zelle(0, row))
        typ = _text(zelle(1, row))
        bezeichnung = _text(zelle(2, row))
        zusammen = _text(zelle(3, row))
        hinweis = _text(zelle(4, row))

        if bm_id and not NUMMER_BM.fullmatch(bm_id):
            fehler.append({'blatt': 'Betriebsmittel', 'excel_zeile': index,
                           'grund': 'Ungültige ID %r' % bm_id})
        if zusammen and not NUMMER_BM.fullmatch(zusammen):
            fehler.append({'blatt': 'Betriebsmittel', 'excel_zeile': index,
                           'grund': 'Ungültiges Zusammenführen-Ziel %r' % zusammen})
        if typ and typ not in TYPEN:
            fehler.append({'blatt': 'Betriebsmittel', 'excel_zeile': index,
                           'grund': 'Ungültiger Typ %r' % typ})

        zeilen.append({
            'id': bm_id or None,
            'typ': typ,
            'bezeichnung': bezeichnung,
            'zusammenfuehren_mit': zusammen or None,
            'hinweis': hinweis,
            'excel_zeile': index,
        })

    # Exakt gleiche (Typ, Bezeichnung) nach Normalisierung → Doppelung melden.
    gesehen = {}
    for e in zeilen:
        if not e['bezeichnung']:
            continue
        schluessel = (e['typ'].strip().casefold(), e['bezeichnung'].strip().casefold())
        if schluessel in gesehen:
            fehler.append({'blatt': 'Betriebsmittel', 'excel_zeile': e['excel_zeile'],
                           'grund': 'Doppeltes Betriebsmittel (Typ+Bezeichnung '
                                    'identisch), siehe Zeile %d' % gesehen[schluessel]})
        else:
            gesehen[schluessel] = e['excel_zeile']
    return zeilen, fehler


def lies_zeitenblatt(ws, gueltige_nummern):
    """Liest ``Zeiten`` → ``(bloecke, fehler)`` mit ``{nr: [(von, bis), ...]}``."""
    bloecke = {}
    fehler = []

    def zelle(spalte, row):
        return row[spalte] if spalte < len(row) else None

    for index, row in enumerate(
            ws.iter_rows(min_col=1, max_col=SPALTEN_ZEITEN, values_only=True),
            start=1):
        if _ist_leer(row):
            continue
        if index == 1 and _text(zelle(0, row)).lower() in \
                ('termin-nr.', 'termin', 'termin (nr)', 'nr', 'nr.'):
            continue

        ref = _text(zelle(0, row))
        von = _zu_datetime(zelle(1, row))
        bis = _zu_datetime(zelle(2, row), als_ende=True)

        if not NUMMER_T.fullmatch(ref):
            fehler.append({'blatt': 'Zeiten', 'excel_zeile': index,
                           'grund': 'Keine gültige Termin-Nr %r' % ref})
            continue
        if von is None or bis is None:
            fehler.append({'blatt': 'Zeiten', 'excel_zeile': index,
                           'grund': 'Von/Bis unvollständig'})
            continue
        if bis < von:
            fehler.append({'blatt': 'Zeiten', 'excel_zeile': index,
                           'grund': 'Bis liegt vor Von'})
            continue
        if ref not in gueltige_nummern:
            fehler.append({'blatt': 'Zeiten', 'excel_zeile': index,
                           'grund': 'Unbekannte Termin-Nr %s' % ref})
            continue
        bloecke.setdefault(ref, []).append((von, bis))
    return bloecke, fehler


def lies_datei(pfad):
    """Liest eine Excel-Datei im Modell-3-Format → strukturiertes Ergebnis."""
    from openpyxl import load_workbook

    ergebnis = {
        'termine': [],
        'news': [],
        'bloecke': {},
        'betriebsmittel': [],
        'archiv_termine': [],
        'archiv_news': [],
        'fehler': [],
        'dateiname': os.path.basename(pfad),
    }

    try:
        groesse = os.path.getsize(pfad)
    except OSError as fehler:
        ergebnis['fehler'].append({'grund': 'Datei nicht lesbar: %s' % fehler})
        return ergebnis
    if groesse > MAX_BYTES:
        ergebnis['fehler'].append(
            {'grund': 'Datei zu groß (%.1f MB, erlaubt 20 MB)'
                      % (groesse / 1024 / 1024)})
        return ergebnis

    try:
        wb = load_workbook(pfad, data_only=True, read_only=True)
    except Exception as fehler:
        ergebnis['fehler'].append({'grund': 'Datei nicht lesbar: %s' % fehler})
        return ergebnis

    try:
        vorhanden = set(wb.sheetnames)

        # Betriebsmittel zuerst – die Namensmenge wird für Querverweise gebraucht.
        if 'Betriebsmittel' in vorhanden:
            ergebnis['betriebsmittel'], bm_fehler = \
                lies_betriebsmittelblatt(wb['Betriebsmittel'])
            ergebnis['fehler'].extend(bm_fehler)
        bm_namen = {e['bezeichnung'].casefold()
                    for e in ergebnis['betriebsmittel'] if e['bezeichnung']}
        bm_nach_id = {e['id'].casefold(): e
                      for e in ergebnis['betriebsmittel'] if e['id']}

        if 'Termine' in vorhanden:
            ergebnis['termine'], tf = lies_terminblatt(
                wb['Termine'], bm_namen, bm_nach_id)
            ergebnis['fehler'].extend(tf)
        if 'News & Audits' in vorhanden:
            ergebnis['news'], nf = lies_newsblatt(wb['News & Audits'])
            ergebnis['fehler'].extend(nf)
        if 'Archiv Termine' in vorhanden:
            ergebnis['archiv_termine'], atf = \
                lies_terminblatt(wb['Archiv Termine'], bm_namen, bm_nach_id,
                                 blatt='Archiv Termine')
            ergebnis['fehler'].extend(atf)
        if 'Archiv News & Audits' in vorhanden:
            ergebnis['archiv_news'], anf = \
                lies_newsblatt(wb['Archiv News & Audits'], blatt='Archiv News & Audits')
            ergebnis['fehler'].extend(anf)

        # Doppelte Nummern über aktiv + Archiv hinweg.
        _duplikate(
            [(e['nr'], 'Termine', e['excel_zeile']) for e in ergebnis['termine']] +
            [(e['nr'], 'Archiv Termine', e['excel_zeile'])
             for e in ergebnis['archiv_termine']],
            ergebnis['fehler'])
        _duplikate(
            [(e['nr'], 'News & Audits', e['excel_zeile']) for e in ergebnis['news']] +
            [(e['nr'], 'Archiv News & Audits', e['excel_zeile'])
             for e in ergebnis['archiv_news']],
            ergebnis['fehler'])

        gueltige = {e['nr'] for e in ergebnis['termine']} | \
                   {e['nr'] for e in ergebnis['archiv_termine']}
        if 'Zeiten' in vorhanden:
            bloecke, zf = lies_zeitenblatt(wb['Zeiten'], gueltige)
            ergebnis['bloecke'] = bloecke
            ergebnis['fehler'].extend(zf)
    finally:
        wb.close()

    return ergebnis
