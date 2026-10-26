"""Wandelt eine Termin-Excel vom alten ins neue Format.

Das alte Format hatte fünf Spalten ohne Nummer:

    Art | Prüfstand | Von | Bis | Info

Das neue braucht sieben, weil die Nummer der Bezug zu den Zeitblöcken ist:

    Nr | Art | Prüfstand | Von | Bis | Info | Status

Der Konverter liest die alten Zeilen und schreibt eine vollständige Datei mit
allen Blättern der aktuellen Vorlage. Zeilen, die sich nicht übernehmen lassen,
werden gemeldet statt stillschweigend verworfen.

Aufruf:
    python3 tools_excel_konverter.py alt.xlsx neu.xlsx
"""
import os
import sys
from datetime import datetime, date, time

VORLAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'vorlagen', 'termine_modell2.xlsx')

# Schreibweise der alten Datei → neue Art
ARTEN = {
    'wartung': 'Wartung',
    'kalibrierung': 'Kalibrierung',
    'ausfall': 'Ausfall',
    'audit': 'Audit',
    'info': 'Info',
}

TAGESENDE = time(23, 59)


def _datum(wert, ende=False):
    """Wandelt Zelleninhalt in ein datetime (ohne Zeit → 00:00 bzw. 23:59)."""
    if wert is None or (isinstance(wert, str) and not wert.strip()):
        return None
    if isinstance(wert, datetime):
        return wert
    if isinstance(wert, date):
        return datetime.combine(wert, TAGESENDE if ende else time(0, 0))
    text = str(wert).strip()
    for muster in ('%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M', '%d.%m.%Y', '%Y-%m-%d',
                   '%d.%m.%y', '%d/%m/%Y'):
        try:
            return datetime.strptime(text, muster)
        except ValueError:
            continue
    return None


def lies_alt(pfad):
    """Liest die alte Datei → (zeilen, uebersprungen)."""
    from openpyxl import load_workbook

    wb = load_workbook(pfad, data_only=True)
    ws = wb['Termine'] if 'Termine' in wb.sheetnames else wb.worksheets[0]

    zeilen, uebersprungen = [], []
    for nummer, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row is None or all(c is None or str(c).strip() == '' for c in row):
            continue
        erste = str(row[0] or '').strip().lower()
        if nummer == 1 and erste in ('art', 'typ'):
            continue      # Kopfzeile

        werte = list(row[:5])
        while len(werte) < 5:
            werte.append(None)

        art_text = str(werte[0] or '').strip().lower()
        art = ARTEN.get(art_text)
        pruefstand = str(werte[1] or '').strip()
        von = _datum(werte[2])
        bis = _datum(werte[3], ende=True)
        info = str(werte[4] or '').strip()

        grund = None
        if art is None:
            grund = f'unbekannte Art "{werte[0]}"'
        elif not pruefstand:
            grund = 'Prüfstand fehlt'
        elif von is None:
            grund = f'Von nicht lesbar ("{werte[2]}")'

        if grund:
            uebersprungen.append({'zeile': nummer, 'grund': grund,
                                  'inhalt': [str(w) if w is not None else '' for w in werte]})
            continue

        zeilen.append({'art': art, 'pruefstand': pruefstand, 'von': von,
                       'bis': bis, 'info': info, 'excel_zeile': nummer})

    wb.close()
    return zeilen, uebersprungen


def schreibe_neu(pfad, zeilen):
    """Schreibt eine vollständige Datei im neuen Format."""
    from openpyxl import Workbook
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    ws = wb.active
    ws.title = 'Termine'

    kopf = ['Nr', 'Art', 'Prüfstand', 'Von', 'Bis', 'Info', 'Status']
    ws.append(kopf)
    fett = Font(bold=True)
    fuellung = PatternFill('solid', fgColor='E4EAF5')
    for zelle in ws[1]:
        zelle.font = fett
        zelle.fill = fuellung
        zelle.alignment = Alignment(horizontal='left')

    for lauf, eintrag in enumerate(zeilen, start=1):
        ws.append([lauf, eintrag['art'], eintrag['pruefstand'],
                   eintrag['von'], eintrag['bis'], eintrag['info'] or None,
                   'offen'])

    # Datumsformat setzen
    for zeile in range(2, ws.max_row + 1):
        for spalte in ('D', 'E'):
            ws[f'{spalte}{zeile}'].number_format = 'DD.MM.YYYY HH:MM'

    # Dropdowns wie in der Vorlage
    if ws.max_row >= 2:
        art = DataValidation(type='list',
                             formula1='"Wartung,Kalibrierung,Ausfall,Audit,Info"',
                             allow_blank=False)
        status = DataValidation(type='list',
                                formula1='"offen,abgeschlossen,storniert"',
                                allow_blank=False)
        ws.add_data_validation(art)
        ws.add_data_validation(status)
        art.add(f'B{2}:B{max(ws.max_row, 2)}')
        status.add(f'G{2}:G{max(ws.max_row, 2)}')

    for spalte, breite in (('A', 6), ('B', 15), ('C', 24), ('D', 18),
                           ('E', 18), ('F', 38), ('G', 15)):
        ws.column_dimensions[spalte].width = breite
    ws.freeze_panes = 'A2'

    # Zweites Blatt: Zeitblöcke (leer, für unterbrochene Kalibrierungen)
    bloecke = wb.create_sheet('Zeiten')
    bloecke.append(['Nr', 'Von', 'Bis'])
    for zelle in bloecke[1]:
        zelle.font = fett
        zelle.fill = fuellung
    bloecke.column_dimensions['A'].width = 6
    bloecke.column_dimensions['B'].width = 18
    bloecke.column_dimensions['C'].width = 18

    # Prüfstände: Stammliste aus den vorhandenen Zeilen
    staemme = wb.create_sheet('Prüfstände')
    staemme.append(['Prüfstand'])
    staemme['A1'].font = fett
    staemme['A1'].fill = fuellung
    for name in sorted({e['pruefstand'] for e in zeilen}):
        staemme.append([name])
    staemme.column_dimensions['A'].width = 28

    archiv = wb.create_sheet('Archiv')
    archiv.append(['Nr', 'Art', 'Prüfstand', 'Von', 'Bis', 'Info', 'Status'])
    for zelle in archiv[1]:
        zelle.font = fett
        zelle.fill = fuellung

    anleitung = wb.create_sheet('Anleitung')
    for text in (
        'Anleitung',
        '',
        'Dieses Blatt ist aus einer älteren Tabelle übernommen worden.',
        'Die Spalten "Nr" und "Status" sind neu – die Nummer verbindet einen',
        'Termin mit seinen Zeitblöcken auf dem Blatt "Zeiten".',
        '',
        'Wichtig:',
        '- Status "abgeschlossen" setzen, wenn der Termin vorbei ist.',
        '- Für unterbrochene Kalibrierungen auf "Zeiten" je Arbeitstag eine Zeile',
        '  eintragen (Nr aus Spalte A, Von, Bis).',
        '- Termine dürfen nach dem Abschluss gelöscht werden, die Historie bleibt.',
    ):
        anleitung.append([text])
    anleitung.column_dimensions['A'].width = 80

    wb.save(pfad)
    return pfad


def konvertiere(quelle, ziel):
    """Konvertiert eine alte Datei und liefert einen Bericht."""
    if not os.path.exists(quelle):
        raise FileNotFoundError(quelle)
    zeilen, uebersprungen = lies_alt(quelle)
    schreibe_neu(ziel, zeilen)
    return {'uebernommen': len(zeilen), 'uebersprungen': uebersprungen,
            'ziel': ziel}


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    bericht = konvertiere(argv[1], argv[2])
    print(f'Übernommen: {bericht["uebernommen"]} Zeilen')
    if bericht['uebersprungen']:
        print(f'Übersprungen: {len(bericht["uebersprungen"])} Zeilen')
        for eintrag in bericht['uebersprungen']:
            print(f'  Zeile {eintrag["zeile"]}: {eintrag["grund"]}')
            print(f'    {eintrag["inhalt"]}')
    print(f'Neu geschrieben: {bericht["ziel"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
