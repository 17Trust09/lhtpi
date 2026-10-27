"""Wandelt eine Termin-Excel vom alten ins neue Format.

Das alte Format hatte fünf Spalten ohne Nummer:

    Art | Prüfstand | Von | Bis | Info

Das neue braucht sieben, weil die Nummer der Bezug zu den Zeitblöcken ist:

    Nr | Art | Prüfstand | Von | Bis | Info | Status

Zwei Regeln des neuen Modells:

* Im Blatt ``Termine`` steht **nur ein Datum**, keine Uhrzeit.
* Uhrzeiten stehen im Blatt ``Zeiten``, ein Block je Zeitraum.

Der Konverter schreibt eine vollständige Datei mit allen Blättern der
aktuellen Vorlage (samt Drop-Downs) und verschiebt Uhrzeiten automatisch ins
Blatt ``Zeiten``. Zeilen, die sich nicht übernehmen lassen, werden gemeldet
statt stillschweigend verworfen.

Aufruf:
    python3 tools_excel_konverter.py alt.xlsx neu.xlsx
"""
import os
import sys
from datetime import datetime, date, time

from tools_vorlage_bauen import baue_vorlage, PRUEFSTAENDE

# Schreibweise der alten Datei → neue Art
ARTEN = {
    'wartung': 'Wartung',
    'kalibrierung': 'Kalibrierung',
    'ausfall': 'Ausfall',
    'audit': 'Audit',
    'info': 'Info',
}

TAGESENDE = time(23, 59)
MITTERNACHT = time(0, 0)


def _datum(wert, ende=False):
    """Wandelt Zelleninhalt in ein datetime (ohne Zeit → 00:00 bzw. 23:59)."""
    if wert is None or (isinstance(wert, str) and not wert.strip()):
        return None
    if isinstance(wert, datetime):
        if ende and wert.time() == MITTERNACHT:
            return datetime.combine(wert.date(), TAGESENDE)
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


def _hat_uhrzeit(von, bis):
    """Steckt in dem Zeitraum eine Uhrzeit, die ins Blatt „Zeiten“ gehört?"""
    if von is None:
        return False
    if von.time() != MITTERNACHT:
        return True
    if bis is not None and bis.time() not in (MITTERNACHT, TAGESENDE):
        return True
    return False


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
    """Schreibt eine vollständige Datei im Aufbau der aktuellen Vorlage."""
    from openpyxl import load_workbook

    baue_vorlage(pfad)                     # Struktur samt Drop-Downs
    wb = load_workbook(pfad)

    # Beispieldaten der Vorlage entfernen, Kopfzeilen bleiben stehen.
    for blatt in ('Termine', 'Zeiten', 'Archiv'):
        ws = wb[blatt]
        if ws.max_row > 1:
            ws.delete_rows(2, ws.max_row - 1)

    termine = wb['Termine']
    zeiten = wb['Zeiten']
    bloecke = 0
    for lauf, eintrag in enumerate(zeilen, start=1):
        von, bis = eintrag['von'], eintrag['bis']
        termine.append([lauf, eintrag['art'], eintrag['pruefstand'],
                        von.date(), bis.date() if bis else None,
                        eintrag['info'] or None, 'offen'])
        for spalte in ('D', 'E'):
            termine['%s%d' % (spalte, lauf + 1)].number_format = 'DD.MM.YYYY'
        if _hat_uhrzeit(von, bis):
            zeiten.append([lauf, von, bis or von,
                           'aus alter Tabelle übernommen'])
            bloecke += 1

    # Prüfstände ergänzen, die in der alten Datei vorkommen, aber in der
    # Stammliste fehlen - ohne sie wäre der Prüfstand im Dropdown nicht wählbar.
    vorhanden = {eintrag[0] for eintrag in PRUEFSTAENDE}
    fehlend = []
    for eintrag in zeilen:
        name = eintrag['pruefstand']
        teile = name.split()
        kennung = teile[0] if teile else name
        if kennung not in vorhanden:
            bezeichnung = name[len(kennung):].strip() or '—'
            fehlend.append((kennung, bezeichnung))
            vorhanden.add(kennung)

    if fehlend:
        from openpyxl.workbook.defined_name import DefinedName
        ws = wb['Prüfstände']
        for kennung, bezeichnung in fehlend:
            ws.append([kennung, bezeichnung, '%s %s' % (kennung, bezeichnung)])
        wb.defined_names['Pruefstaende'] = DefinedName(
            'Pruefstaende', attr_text="'Prüfstände'!$C$2:$C$%d" % ws.max_row)

    wb.save(pfad)
    return {'bloecke': bloecke, 'neue_pruefstaende': fehlend}


def konvertiere(quelle, ziel):
    """Konvertiert eine alte Datei und liefert einen Bericht."""
    if not os.path.exists(quelle):
        raise FileNotFoundError(quelle)
    zeilen, uebersprungen = lies_alt(quelle)
    zusatz = schreibe_neu(ziel, zeilen)
    return {'uebernommen': len(zeilen), 'uebersprungen': uebersprungen,
            'ziel': ziel, **zusatz}


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    bericht = konvertiere(argv[1], argv[2])
    print(f'Übernommen: {bericht["uebernommen"]} Zeilen')
    if bericht['bloecke']:
        print(f'Uhrzeiten ins Blatt „Zeiten“ verschoben: {bericht["bloecke"]} Blöcke')
    if bericht['neue_pruefstaende']:
        print('Neue Prüfstände in die Stammliste aufgenommen:')
        for kennung, bezeichnung in bericht['neue_pruefstaende']:
            print(f'  {kennung} {bezeichnung}')
    if bericht['uebersprungen']:
        print(f'Übersprungen: {len(bericht["uebersprungen"])} Zeilen')
        for eintrag in bericht['uebersprungen']:
            print(f'  Zeile {eintrag["zeile"]}: {eintrag["grund"]}')
            print(f'    {eintrag["inhalt"]}')
    print(f'Neu geschrieben: {bericht["ziel"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
