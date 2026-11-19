"""Konvertiert eine Modell-2-Arbeitsmappe in eine Modell-3-Arbeitsmappe.

Modell 2 trennte noch nicht zwischen Terminen und News/Audits und hatte keine
Betriebsmittel-IDs. Modell 3 führt diese Trennung ein:

* Termine (Kalibrierung/Wartung/Ausfall) → Blatt ``Termine`` mit ``T-NNN``,
* Audit/Info → Blatt ``News & Audits`` mit ``N-NNN``,
* Betriebsmittel erhalten stabile ``BM-NNN``-IDs,
* ``Zeiten``-Blöcke werden über die neue T-Nummer zugeordnet.

Der Konverter arbeitet **trocken-sicher**: die Quelldatei wird nie verändert,
solange nicht ausdrücklich ``--ersetzen`` gesetzt ist. Vor dem Ersetzen wird
die Quelle als ``<datei>.<zeitstempel>.bak`` gesichert (Zeitstempel statt einer
einzigen überschriebenen ``.bak`` – frühere Sicherungen bleiben erhalten), und
das Ersetzen geschieht erst, wenn die erzeugte Modell-3-Mappe die Validierung
**fehlerfrei** besteht. Schlägt die Validierung fehl, bleibt die Quelle
unverändert; die erzeugte Datei bleibt für die Diagnose stehen. Zeilen, die
sich nicht übernehmen lassen, werden gemeldet – nie stillschweigend verworfen.

Bewusst **kein** automatischer Konverter-Aufruf im Stick-Watcher: die Umstellung
auf Modell 3 ist ein bewusster, manueller Schritt.

Aufruf:

    python3 tools_modell2_zu_modell3.py --quelle alt.xlsx --ziel neu.xlsx
    python3 tools_modell2_zu_modell3.py --quelle alt.xlsx --ersetzen   # in place
    python3 tools_modell2_zu_modell3.py --ziel neu.xlsx --pruefen      # nur prüfen
    python3 tools_modell2_zu_modell3.py --pruefen neu.xlsx             # nur prüfen
"""
import argparse
import os
import re
import shutil
import sys
from collections import Counter
from datetime import date, datetime, time

ART_LABEL = {
    'kalibrierung': 'Kalibrierung',
    'wartung': 'Wartung',
    'ausfall': 'Ausfall',
    'audit': 'Audit',
    'info': 'Info',
}

TERMIN_ARTEN = {'kalibrierung', 'wartung', 'ausfall'}
NEWS_ARTEN = {'audit', 'info'}

# Konsolen-Namen: nur diese exakten Präfixe werden als Konsole erkannt. Die
# TESTTUCHS-Schreibweise gilt ausschließlich als ihr eigener, exakt so
# eingetragener Name – es wird nichts unscharf korrigiert oder umbenannt.
KONSOLE_PRAEFIXE = ('TESTFUCHS KONSOLE', 'TESTTUCHS KONSOLE')


def ist_konsole(bezeichnung):
    """True, wenn die Bezeichnung eindeutig eine Konsole ist (exakter Präfix)."""
    name = ' '.join(str(bezeichnung or '').split()).upper()
    return any(name.startswith(p) for p in KONSOLE_PRAEFIXE)


def _art_norm(art):
    return str(art or '').strip().lower()


def _name_norm(wert):
    return ' '.join(str(wert or '').split())


def _zu_int(wert):
    if wert is None:
        return None
    try:
        return int(str(wert).strip())
    except (TypeError, ValueError):
        return None


def _zeitwert(wert):
    """Wandelt einen Zeitwert in ``datetime``, ohne die Uhrzeit zu verwerfen.

    Ein reines ``date`` wird zum Tagesbeginn; ``None`` bleibt ``None``. Jeder
    Wert, der sich nicht abbilden lässt (z. B. ein String, der den Parser
    durchlaufen hat), liefert ``None`` – der Aufrufer meldet ihn dann, statt ihn
    stillschweigend zu verändern.
    """
    if isinstance(wert, datetime):
        return wert
    if isinstance(wert, date):
        return datetime.combine(wert, time(0, 0))
    return None


# ── Lesen (Modell 2) ──────────────────────────────────────────────────

def _lese_zeiten(ws):
    """Liest das Modell-2-Blatt ``Zeiten`` inklusive Notiz.

    Liefert ``[{'nr', 'von', 'bis', 'notiz', 'excel_zeile'}, ...]``; unlesbare
    Zeilen werden separat als Fehler gemeldet, damit nichts still verschwindet.
    """
    from excel_modell2 import _zu_datetime, _ist_leer

    zeilen = []
    fehler = []
    for index, row in enumerate(
            ws.iter_rows(min_col=1, max_col=4, values_only=True), start=1):
        if _ist_leer(row):
            continue
        if index == 1 and str(row[0] or '').strip().lower() in \
                ('termin', 'termin (nr)', 'nr', 'nr.'):
            continue
        nr = _zu_int(row[0])
        von = _zu_datetime(row[1])
        bis = _zu_datetime(row[2], als_ende=True)
        notiz = str(row[3] or '').strip() if len(row) > 3 else ''
        if nr is None or von is None or bis is None:
            fehler.append({'excel_zeile': index,
                           'grund': 'Zeiten-Zeile unlesbar (Termin/Von/Bis)'})
            continue
        if bis < von:
            fehler.append({'excel_zeile': index,
                           'grund': 'Zeiten: Bis liegt vor Von'})
            continue
        zeilen.append({'nr': nr, 'von': von, 'bis': bis, 'notiz': notiz,
                       'excel_zeile': index})
    return zeilen, fehler


def _lese_modell2(pfad):
    """Liest die Modell-2-Quelle (Termine, Archiv, Zeiten, Prüfstände)."""
    from openpyxl import load_workbook
    from excel_modell2 import lies_terminblatt, lies_pruefstandblatt

    try:
        wb = load_workbook(pfad, data_only=True)
    except Exception as fehler:
        raise ValueError(
            'Quelle %r nicht lesbar (kein gültiges XLSX?): %s' % (pfad, fehler))

    ergebnis = {
        'termine': [], 'archiv': [], 'zeiten': [], 'pruefstaende': [],
        'fehler': [],
    }
    try:
        if 'Termine' in wb.sheetnames:
            ergebnis['termine'] = lies_terminblatt(wb['Termine'])
        elif wb.worksheets:
            ergebnis['termine'] = lies_terminblatt(wb.worksheets[0])

        if 'Archiv' in wb.sheetnames:
            ergebnis['archiv'] = lies_terminblatt(wb['Archiv'])

        if 'Zeiten' in wb.sheetnames:
            ergebnis['zeiten'], zf = _lese_zeiten(wb['Zeiten'])
            ergebnis['fehler'].extend(zf)

        for name in wb.sheetnames:
            if name.lower().startswith(('prüfst', 'pruefst')):
                ergebnis['pruefstaende'] = lies_pruefstandblatt(wb[name])
                break
    finally:
        wb.close()
    return ergebnis


# ── Schreiben (Modell 3) ──────────────────────────────────────────────

def _bestehende_bms(wb):
    """Liest die vorhandenen Betriebsmittel des Modell-3-Template-Blattes."""
    ws = wb['Betriebsmittel']
    bms = {}
    max_num = 0
    for row in ws.iter_rows(min_row=2, max_col=5, values_only=True):
        name = _name_norm(row[2])
        if not name:
            continue
        bm_id = str(row[0] or '').strip()
        typ = str(row[1] or '').strip()
        bms[name.casefold()] = {'id': bm_id, 'typ': typ, 'name': name}
        m = re.fullmatch(r'BM-(\d{3})', bm_id or '')
        if m:
            max_num = max(max_num, int(m.group(1)))
    return bms, max_num


def _bm_typ(bezeichnung):
    return 'Konsole' if ist_konsole(bezeichnung) else 'Prüfstand'


def _schreibe_ziel(daten, ziel, bericht):
    """Erzeugt die Modell-3-Mappe aus den gelesenen Modell-2-Daten."""
    from tools_vorlage_modell3_bauen import baue_vorlage
    from openpyxl import load_workbook

    baue_vorlage(ziel)
    wb = load_workbook(ziel)

    try:
        # ── Betriebsmittel: vorhandene Seeds + neue Zeilen mit stabilen IDs ──
        bms, max_num = _bestehende_bms(wb)
        neue_bms = {}
        # Deterministische Reihenfolge: erst die Stammliste, dann Termine/Archiv.
        namen_in_quelle = list(daten.get('pruefstaende') or [])
        for z in list(daten.get('termine') or []) + list(daten.get('archiv') or []):
            name = _name_norm(z.get('pruefstand'))
            if name and name not in namen_in_quelle:
                namen_in_quelle.append(name)

        bm_ws = wb['Betriebsmittel']
        for name in namen_in_quelle:
            name = _name_norm(name)
            if not name or name.casefold() in bms:
                continue
            max_num += 1
            kennung = 'BM-%03d' % max_num
            typ = _bm_typ(name)
            bm_ws.append([kennung, typ, name, None, None])
            bms[name.casefold()] = {'id': kennung, 'typ': typ, 'name': name}
            neue_bms[name.casefold()] = kennung
            bericht['neue_betriebsmittel'].append(
                {'kennung': kennung, 'typ': typ, 'bezeichnung': name})

        # ── Nummern deterministisch vergeben ──────────────────────────────
        # Termine (aktiv) → T-001…, dann Archiv → weiterzählen. News ebenso.
        t_nummer = 1
        n_nummer = 1
        nr_zu_t = {}          # alte Modell-2-Nummer → T-NNN

        # Mehrdeutige alte Nummern früh erkennen: kommt eine Modell-2-Nummer in
        # Termine UND Archiv vor, ist die Zuordnung der Zeiten nicht eindeutig.
        # Statt still dem letzten Treffer zu folgen, wird die Nummer gemeldet
        # und ihre Zeiten bleiben unmappbar (landen im Bericht).
        alle_nummern = [z.get('nr') for z in (list(daten.get('termine') or [])
                        + list(daten.get('archiv') or []))
                        if z.get('nr') is not None]
        mehrdeutig = {nr for nr, anzahl in Counter(alle_nummern).items()
                      if anzahl > 1}
        for nr in sorted(mehrdeutig):
            bericht['mehrdeutige_nummern'].append({
                'nr': nr,
                'grund': 'alte Nummer %r kommt mehrfach vor (Termine/Archiv)'
                         % nr})

        def schreibe_termin(z, ws):
            nonlocal t_nummer
            nr = z.get('nr')
            t = 'T-%03d' % t_nummer
            t_nummer += 1
            if nr is not None and nr not in mehrdeutig:
                nr_zu_t[nr] = t
            name = _name_norm(z.get('pruefstand'))
            bm = bms.get(name.casefold(), {})
            zeile = [t, ART_LABEL[_art_norm(z.get('art'))],
                     bm.get('typ') or _bm_typ(name),
                     name,
                     _zeitwert(z.get('von')),
                     _zeitwert(z.get('bis')),
                     _name_norm(z.get('info')) or None,
                     str(z.get('status') or 'offen').strip().lower() or 'offen',
                     None]
            for spalte, wert in enumerate(zeile, start=1):
                if spalte == 9:
                    continue          # Spalte I bleibt Formel
                ws.cell(row=t_nummer, column=spalte, value=wert)

        def schreibe_news(z, ws):
            nonlocal n_nummer
            n = 'N-%03d' % n_nummer
            n_nummer += 1
            art = _art_norm(z.get('art'))
            titel = _name_norm(z.get('info')) or _name_norm(z.get('pruefstand')) \
                or ART_LABEL.get(art, art)
            zeile = [n, ART_LABEL.get(art, art), titel,
                     _zeitwert(z.get('von')),
                     _zeitwert(z.get('bis')),
                     None,
                     str(z.get('status') or 'offen').strip().lower() or 'offen']
            for spalte, wert in enumerate(zeile, start=1):
                ws.cell(row=n_nummer, column=spalte, value=wert)

        ws_termine = wb['Termine']
        ws_archiv_t = wb['Archiv Termine']
        ws_news = wb['News & Audits']
        ws_archiv_n = wb['Archiv News & Audits']

        def uebernehme(z, termin_ws, news_ws):
            art = _art_norm(z.get('art'))
            status = str(z.get('status') or 'offen').strip().lower() or 'offen'
            if status == 'storniert':
                bericht['uebersprungen'].append(
                    {'zeile': z.get('excel_zeile'),
                     'grund': 'Status „storniert“ wird in Modell 3 nicht übernommen'})
                return
            if art in TERMIN_ARTEN:
                if not _name_norm(z.get('pruefstand')) or \
                        _zeitwert(z.get('von')) is None:
                    bericht['uebersprungen'].append(
                        {'zeile': z.get('excel_zeile'),
                         'grund': 'Termin unvollständig (Betriebsmittel/Von '
                                  'fehlt oder nicht abbildbar)'})
                    return
                schreibe_termin(z, termin_ws)
                bericht['uebernommen_termine'] += 1
            elif art in NEWS_ARTEN:
                if _zeitwert(z.get('von')) is None:
                    bericht['uebersprungen'].append(
                        {'zeile': z.get('excel_zeile'),
                         'grund': 'News/Audit ohne gültiges/abbildbares Von'})
                    return
                schreibe_news(z, news_ws)
                bericht['uebernommen_news'] += 1
            else:
                bericht['uebersprungen'].append(
                    {'zeile': z.get('excel_zeile'),
                     'grund': 'unbekannte Art %r' % z.get('art')})

        for z in daten.get('termine') or []:
            uebernehme(z, ws_termine, ws_news)
        for z in daten.get('archiv') or []:
            uebernehme(z, ws_archiv_t, ws_archiv_n)

        # ── Zeiten: alte Nummern auf T-NNN abbilden ───────────────────────
        ws_zeiten = wb['Zeiten']
        zeilen_zeiten = 2
        for z in daten.get('zeiten') or []:
            t = nr_zu_t.get(z['nr'])
            if t is None:
                if z['nr'] in mehrdeutig:
                    grund = ('Nummer %r ist mehrdeutig (Termine und Archiv)'
                             % z['nr'])
                else:
                    grund = 'keine Termin-Nummer %r in Termine/Archiv' % z['nr']
                bericht['unmappbare_zeiten'].append(
                    {'excel_zeile': z['excel_zeile'], 'nr': z['nr'],
                     'grund': grund})
                continue
            ws_zeiten.cell(row=zeilen_zeiten, column=1, value=t)
            ws_zeiten.cell(row=zeilen_zeiten, column=2, value=z['von'])
            ws_zeiten.cell(row=zeilen_zeiten, column=3, value=z['bis'])
            ws_zeiten.cell(row=zeilen_zeiten, column=4,
                           value=z['notiz'] or None)
            zeilen_zeiten += 1

        wb.save(ziel)
    finally:
        try:
            wb.close()
        except Exception:                       # noqa: BLE001
            pass


# ── Validierung ───────────────────────────────────────────────────────

def pruefe_erzeugt(pfad):
    """Prüft die erzeugte Modell-3-Mappe gegen Parser und Generator-Vertrag.

    Liefert eine Liste von Mängeln (leer = in Ordnung). Die Prüfung der
    vorausgefüllten Nummern (T-001…T-500 fortlaufend) gilt nur für eine frische
    Vorlage, nicht für eine mit Daten gefüllte Mappe – dort sind die Nummern
    über Aktiv- und Archivblatt verteilt. Dieser Punkt wird deshalb separat
    toleriert; alles andere (Blätter, Bereiche, Dropdowns, Parser-Fehler) muss
    fehlerfrei sein.
    """
    from excel_modell3 import lies_datei
    from tools_vorlage_modell3_bauen import pruefe

    maengel = []
    daten = lies_datei(pfad)
    for fehler in daten.get('fehler') or []:
        maengel.append('Parser: %s' % fehler.get('grund'))

    for fehler in pruefe(pfad):
        if 'Nummern nicht vorausgefüllt' in fehler:
            continue
        maengel.append('Generator: %s' % fehler)
    return maengel


# ── Hauptablauf ───────────────────────────────────────────────────────

def _sicherung_pfad(quelle):
    """Eindeutiger, zeitgestempelter Sicherungspfad (überschreibt nie ein .bak).

    Frühere Sicherungen bleiben erhalten: Statt einer einzigen überschriebenen
    ``<quelle>.bak`` wird eine neue Datei mit Zeitstempel angelegt. Sollte der
    (praktisch ausgeschlossene) Kollisionsfall eintreten, wird ein Zähler
    angehängt, statt eine vorhandene Datei zu überschreiben.
    """
    stempel = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    pfad = '%s.%s.bak' % (quelle, stempel)
    n = 1
    while os.path.exists(pfad):
        pfad = '%s.%s-%d.bak' % (quelle, stempel, n)
        n += 1
    return pfad


def konvertiere(quelle, ziel, ersetzen=False):
    """Konvertiert ``quelle`` (Modell 2) nach ``ziel`` (Modell 3).

    Ohne ``ersetzen`` bleibt die Quelle unangetastet und ``quelle``/``ziel``
    müssen verschieden sein. Mit ``ersetzen`` wird zuerst eine zeitgestempelte
    Sicherung (``<quelle>.<zeitstempel>.bak``) angelegt und die Quelle dann
    atomar ersetzt – aber nur, wenn die erzeugte Modell-3-Mappe die Validierung
    fehlerfrei besteht. Bei Mängeln bleibt die Quelle unverändert und die
    erzeugte Datei bleibt für die Diagnose stehen (``bericht['ersetzt']`` ist
    dann ``False``).
    """
    quelle = os.path.abspath(quelle)
    if not os.path.isfile(quelle):
        raise FileNotFoundError(quelle)
    if not ersetzen and ziel is not None and os.path.abspath(ziel) == quelle:
        raise ValueError(
            'Quelle und Ziel sind identisch (%r). Zum Überschreiben '
            '--ersetzen verwenden.' % quelle)

    daten = _lese_modell2(quelle)
    bericht = {
        'quelle': quelle,
        'ziel': ziel,
        'uebernommen_termine': 0,
        'uebernommen_news': 0,
        'neue_betriebsmittel': [],
        'uebersprungen': daten.get('fehler') or [],
        'unmappbare_zeiten': [],
        'mehrdeutige_nummern': [],
        'maengel': [],
        'sicherung': None,
        'ersetzt': False,
        'diagnose': None,
    }

    if ersetzen:
        tmp = quelle + '.modell3.tmp.xlsx'
        _schreibe_ziel(daten, tmp, bericht)
        bericht['maengel'] = pruefe_erzeugt(tmp)
        if bericht['maengel']:
            # Eine fehlerhafte Modell-3-Mappe darf die Quelle nicht zerstören:
            # nicht ersetzen. Quelle und frühere .bak-Sicherungen bleiben
            # unberührt; die erzeugte Datei bleibt für die Diagnose stehen.
            bericht['ziel'] = quelle
            bericht['diagnose'] = tmp
            return bericht
        sicherung = _sicherung_pfad(quelle)
        shutil.copy2(quelle, sicherung)
        os.replace(tmp, quelle)
        bericht['sicherung'] = sicherung
        bericht['ziel'] = quelle
        bericht['ersetzt'] = True
    else:
        _schreibe_ziel(daten, ziel, bericht)
        bericht['maengel'] = pruefe_erzeugt(ziel)

    return bericht


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quelle', help='Modell-2-Quelldatei (.xlsx)')
    parser.add_argument('--ziel', help='Modell-3-Zieldatei (.xlsx)')
    parser.add_argument('--ersetzen', action='store_true',
                        help='Quelle sichern (zeitgestempeltes .bak) und nur bei '
                             'fehlerfreier Validierung atomar ersetzen')
    parser.add_argument('--pruefen', action='store_true',
                        help='Nur validieren: eine vorhandene Modell-3-Datei '
                             'prüfen (via --ziel oder als Positionsargument)')
    parser.add_argument('datei', nargs='?',
                        help='Datei für --pruefen (Positionsargument)')
    args = parser.parse_args(argv)

    # ── --pruefen: reine Validierung, keine Konvertierung ─────────────────
    if args.pruefen:
        if args.quelle:
            print('FEHLER: --pruefen validiert nur eine vorhandene '
                  'Modell-3-Datei und ist mit --quelle nicht kombinierbar.')
            return 2
        pfad = args.ziel or args.datei
        if not pfad:
            print('FEHLER: --pruefen braucht eine Datei (--ziel oder '
                  'Positionsargument).')
            return 2
        if not os.path.isfile(pfad):
            print('FEHLER: Datei %r nicht gefunden.' % pfad)
            return 1
        maengel = pruefe_erzeugt(pfad)
        if maengel:
            print('MÄNGEL:')
            for m in maengel:
                print('  -', m)
            return 1
        print('Modell-3-Datei in Ordnung:', pfad)
        return 0

    if not args.quelle:
        print('FEHLER: --quelle fehlt (Modell-2-Datei).')
        return 2

    # ── --ersetzen darf kein abweichendes --ziel bekommen ─────────────────
    if args.ersetzen:
        if args.ziel and os.path.abspath(args.ziel) != os.path.abspath(args.quelle):
            print('FEHLER: --ersetzen ist mit einem abweichenden --ziel nicht '
                  'kombinierbar (es ersetzt die Quelle selbst).')
            return 2
        ziel = args.quelle
    else:
        ziel = args.ziel or re.sub(r'\.xlsx$', '_modell3.xlsx', args.quelle,
                                   flags=re.IGNORECASE)

    try:
        bericht = konvertiere(args.quelle, ziel, ersetzen=args.ersetzen)
    except (OSError, ValueError) as fehler:
        print('FEHLER: %s' % fehler)
        return 1

    print('Übernommen: %d Termine, %d News/Audits'
          % (bericht['uebernommen_termine'], bericht['uebernommen_news']))
    if bericht['neue_betriebsmittel']:
        print('Neue Betriebsmittel:')
        for b in bericht['neue_betriebsmittel']:
            print('  %s %s %s' % (b['kennung'], b['typ'], b['bezeichnung']))
    if bericht['mehrdeutige_nummern']:
        print('Mehrdeutige Nummern (Zeiten nicht zuordenbar):')
        for z in bericht['mehrdeutige_nummern']:
            print('  Nummer %s: %s' % (z['nr'], z['grund']))
    if bericht['unmappbare_zeiten']:
        print('Nicht zuordenbare Zeitblöcke:')
        for z in bericht['unmappbare_zeiten']:
            print('  Zeile %s: %s' % (z['excel_zeile'], z['grund']))
    if bericht['uebersprungen']:
        print('Übersprungen:')
        for z in bericht['uebersprungen']:
            print('  Zeile %s: %s' % (z.get('excel_zeile'), z.get('grund')))
    if bericht['sicherung']:
        print('Sicherung:', bericht['sicherung'])
    print('Ziel:', bericht['ziel'])

    if bericht['maengel']:
        print('MÄNGEL:')
        for m in bericht['maengel']:
            print('  -', m)
        if args.ersetzen:
            print('Quelle wurde wegen der Mängel NICHT ersetzt (unverändert).')
            print('Diagnose-Datei:', bericht['diagnose'])
        return 1
    print('Validierung bestanden.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
