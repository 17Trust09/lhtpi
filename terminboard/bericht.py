"""Monatlicher Terminbericht als PDF.

Inhalt:
  1. Aktive Termine
  2. Abgeschlossene Termine des Berichtsmonats
  3. Ausfallzeiten je Prüfstand (Jahr, Stunden und Tage als eine Summe)
  4. Letzter Import (Datei, Ergebnis, Fehler)
  5. Fußnote: Betriebstag = 06:00–22:45, Wochenende und Feiertage zählen nicht

Die Zahlen kommen aus :mod:`historie` – also aus den Vorgängen, nicht aus den
Import-Läufen. Ein mehrfach importierter Termin zählt genau einmal.
"""
import os
import subprocess
from contextlib import contextmanager
from datetime import datetime

from fpdf import FPDF
from fpdf.fonts import FontFace

from models import db
from historie import Vorgang, ImportLauf, ausfall_je_pruefstand

MONATE = ('', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
          'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember')

ART_TEXT = {
    'kalibrierung': 'Kalibrierung',
    'wartung': 'Wartung',
    'ausfall': 'Ausfall',
    'audit': 'Audit',
    'info': 'Info',
}

STATUS_TEXT = {
    'offen': 'offen',
    'abgeschlossen': 'abgeschlossen',
    'storniert': 'storniert',
    'entfernt': 'entfernt',
}

FUSSNOTE = ('Ein Betriebstag = 06:00–22:45 (16,75 h); Wochenende und Feiertage '
            'zählen nicht als Ausfall.')

SCHRIFT_ORDNER = (
    '/usr/share/fonts/truetype/dejavu',
    '/usr/share/fonts/truetype/liberation',
    '/usr/share/fonts/TTF',
)


def _schriften_finden():
    """Sucht reguläre und fette TTF mit Umlauten.

    Ohne Treffer bleibt es bei Helvetica (latin-1) – Umlaute gehen, Gedanken-
    striche und Sonderzeichen werden vorher ersetzt.
    """
    for ordner in SCHRIFT_ORDNER:
        if not os.path.isdir(ordner):
            continue
        regular = os.path.join(ordner, 'DejaVuSans.ttf')
        bold = os.path.join(ordner, 'DejaVuSans-Bold.ttf')
        if os.path.isfile(regular) and os.path.isfile(bold):
            return regular, bold
        regular = os.path.join(ordner, 'LiberationSans-Regular.ttf')
        bold = os.path.join(ordner, 'LiberationSans-Bold.ttf')
        if os.path.isfile(regular) and os.path.isfile(bold):
            return regular, bold
        if os.path.isfile(os.path.join(ordner, 'DejaVuSans.ttf')):
            # nur regulär vorhanden: fett wird nicht gebraucht
            return os.path.join(ordner, 'DejaVuSans.ttf'), None
    return None, None


ERSATZ = {
    '\u2013': '-', '\u2014': '-', '\u00b7': '-', '\u2026': '...',
    '\u201e': '"', '\u201c': '"', '\u2018': "'", '\u2019': "'",
}


def _rein(text):
    """Ersetzt Zeichen, die ohne eingebettete TTF nicht darstellbar sind."""
    if text is None:
        return ''
    wert = str(text)
    for alt, neu in ERSATZ.items():
        wert = wert.replace(alt, neu)
    return wert


def _std(wert):
    """Stunden als deutsche Zahl: 10.75 → '10,75'."""
    return f'{wert:.2f}'.replace('.', ',')


def _datum(wert):
    return wert.strftime('%d.%m.%Y %H:%M') if wert else '–'


def _kurz(wert):
    return wert.strftime('%d.%m.%Y') if wert else '–'


def sammle_daten(jahr, monat):
    """Sammelt alle Zahlen für den Bericht (ohne PDF)."""
    beginn = datetime(jahr, monat, 1)
    if monat == 12:
        ende = datetime(jahr + 1, 1, 1)
    else:
        ende = datetime(jahr, monat + 1, 1)

    aktive = (Vorgang.query
              .filter(Vorgang.status.in_(('offen', 'storniert')))
              .order_by(Vorgang.von).all())

    abgeschlossen = (Vorgang.query
                     .filter_by(status='abgeschlossen')
                     .filter(Vorgang.abgeschlossen_am >= beginn)
                     .filter(Vorgang.abgeschlossen_am < ende)
                     .order_by(Vorgang.abgeschlossen_am).all())

    letzter_import = (ImportLauf.query
                      .order_by(ImportLauf.zeitpunkt.desc()).first())

    return {
        'jahr': jahr,
        'monat': monat,
        'aktive': aktive,
        'abgeschlossen': abgeschlossen,
        'statistik': ausfall_je_pruefstand(jahr),
        'import': letzter_import,
    }


def erstelle_bericht(pfad, jahr, monat, erzeugt_am=None):
    """Schreibt den PDF-Bericht und liefert den Pfad zurück."""
    daten = sammle_daten(jahr, monat)
    erzeugt_am = erzeugt_am or datetime.now()

    pdf = FPDF(format='A4')
    pdf.set_auto_page_break(auto=True, margin=18)

    regular, bold = _schriften_finden()
    if regular:
        pdf.add_font('Bericht', '', regular)
        if bold:
            pdf.add_font('Bericht', 'B', bold)
        schrift = 'Bericht'
    else:
        schrift = 'Helvetica'
    pdf.add_page()

    # ── Kopf
    pdf.set_font(schrift, size=16)
    pdf.cell(0, 10, f'Terminbericht {MONATE[monat]} {jahr}', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font(schrift, size=9)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(0, 6, f'Erstellt am {erzeugt_am.strftime("%d.%m.%Y um %H:%M")}',
             new_x='LMARGIN', new_y='NEXT')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # ── Aktive Termine
    _ueberschrift(pdf, schrift, f'Aktive Termine ({len(daten["aktive"])})')
    if daten['aktive']:
        _tabelle(pdf, schrift,
                 ('Von', 'Art', 'Prüfstand', 'Bis', 'Status', 'Info'),
                 [(f'{_datum(v.von)}', ART_TEXT.get(v.art, v.art), v.pruefstand,
                   _datum(v.bis), STATUS_TEXT.get(v.status, v.status), v.info or '')
                  for v in daten['aktive']],
                 breiten=(30, 22, 48, 30, 20, 40))
    else:
        _leer(pdf, schrift, 'Keine aktiven Termine.')
    pdf.ln(3)

    # ── Abgeschlossen im Monat
    _ueberschrift(pdf, schrift,
                  f'Abgeschlossen im {MONATE[monat]} ({len(daten["abgeschlossen"])})')
    if daten['abgeschlossen']:
        _tabelle(pdf, schrift,
                 ('Abgeschlossen', 'Art', 'Prüfstand', 'Zeitraum'),
                 [(v.abgeschlossen_am.strftime('%d.%m.%Y'),
                   ART_TEXT.get(v.art, v.art), v.pruefstand,
                   f'{_kurz(v.von)} – {_kurz(v.bis)}')
                  for v in daten['abgeschlossen']],
                 breiten=(26, 24, 46, 94))
    else:
        _leer(pdf, schrift, 'Nichts abgeschlossen in diesem Monat.')
    pdf.ln(3)

    # ── Ausfallzeiten
    _ueberschrift(pdf, schrift, f'Ausfallzeiten {jahr} je Prüfstand')
    if daten['statistik']:
        zeilen = []
        for eintrag in sorted(daten['statistik'].values(),
                              key=lambda e: (-e['stunden'], e['pruefstand'])):
            zeilen.append((
                eintrag['pruefstand'],
                _std(eintrag['stunden']),
                str(eintrag['tage']),
                str(eintrag['vorgaenge']),
            ))
        _tabelle(pdf, schrift,
                 ('Prüfstand', 'Ausfallstunden', 'Tage', 'Termine'),
                 zeilen,
                 breiten=(84, 40, 26, 40),
                 ausrichtung=('LEFT', 'RIGHT', 'RIGHT', 'RIGHT'))

        summe_stunden = sum(e['stunden'] for e in daten['statistik'].values())
        summe_tage = sum(e['tage'] for e in daten['statistik'].values())
        pdf.set_font(schrift, size=9, style='B')
        pdf.cell(0, 7,
                 f'Summe: {_std(summe_stunden)} h an {summe_tage} Tagen',
                 new_x='LMARGIN', new_y='NEXT')
    else:
        _leer(pdf, schrift, 'Keine Ausfallzeiten im Jahr erfasst.')
    pdf.ln(3)

    # ── Import
    _ueberschrift(pdf, schrift, 'Letzter Import')
    imp = daten['import']
    if imp:
        pdf.set_font(schrift, size=9)
        pdf.multi_cell(0, 5,
                       f'{_datum(imp.zeitpunkt)} · {imp.dateiname or "unbekannte Datei"}\n'
                       f'{imp.zeilen} Zeilen · {imp.neu} neu · {imp.geaendert} geändert · '
                       f'{imp.unveraendert} unverändert · {imp.entfernt} entfernt · '
                       f'{imp.fehler} Fehler')
    else:
        _leer(pdf, schrift, 'Noch kein Import gelaufen.')

    # ── Fußnote
    pdf.ln(6)
    pdf.set_font(schrift, size=8)
    pdf.set_text_color(110, 110, 110)
    pdf.multi_cell(0, 4, FUSSNOTE)

    ordner = os.path.dirname(os.path.abspath(pfad))
    if ordner:
        os.makedirs(ordner, exist_ok=True)
    pdf.output(pfad)
    return pfad


def _ueberschrift(pdf, schrift, text):
    pdf.set_font(schrift, size=11, style='B')
    pdf.cell(0, 8, text, new_x='LMARGIN', new_y='NEXT')
    pdf.set_font(schrift, size=9)


def _leer(pdf, schrift, text):
    pdf.set_font(schrift, size=9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, text, new_x='LMARGIN', new_y='NEXT')
    pdf.set_text_color(0, 0, 0)


def _tabelle(pdf, schrift, kopf, zeilen, breiten, ausrichtung=None):
    """Einfache Tabelle über fpdf2."""
    pdf.set_font(schrift, size=8)
    with pdf.table(
        col_widths=breiten,
        text_align=ausrichtung or 'LEFT',
        line_height=5.5,
        first_row_as_headings=True,
        headings_style=FontFace(emphasis='BOLD', fill_color=(228, 234, 245)),
    ) as tabelle:
        kopfzeile = tabelle.row()
        for spalte in kopf:
            kopfzeile.cell(_rein(spalte))
        for zeile in zeilen:
            reihe = tabelle.row()
            for wert in zeile:
                reihe.cell(_rein(wert))


def _dateiname(jahr, monat):
    return f'Terminbericht_{jahr}-{monat:02d}.pdf'


# ── Ablage: lokal und auf dem USB-Stick ───────────────────────────────

DATA_DIR = os.environ.get('LHTPI_DATA_DIR', '/var/lib/lhtpi')
BERICHT_ORDNER = 'LHTPi-Berichte'

# Der LHTPi-Stick wird absichtlich read-only gemountet (Herausziehen im Betrieb
# darf nichts beschädigen). Für Berichte wird er kurz auf rw geschaltet und
# danach sofort wieder auf ro – über einen root-Helfer, der per sudoers nur
# für genau dieses Skript freigegeben ist.
FIXED_MOUNT = '/mnt/lhtpi-usb'
RW_HELFER = '/usr/local/bin/lhtpi-usb-rw.sh'


@contextmanager
def schreibfenster(mount_dir):
    """Stellt den Stick für die Dauer des Blocks beschreibbar.

    Liefert ``True``, wenn geschrieben werden darf. Bei Pfaden außerhalb des
    festen Mounts (z. B. im Test) wird nichts umgehängt.
    """
    if os.path.abspath(mount_dir) != FIXED_MOUNT or not os.path.exists(RW_HELFER):
        yield True
        return

    try:
        ergebnis = subprocess.run(['sudo', '-n', RW_HELFER, 'rw'],
                                  capture_output=True, timeout=15)
        bereit = ergebnis.returncode == 0
    except (OSError, subprocess.SubprocessError):
        bereit = False

    try:
        yield bereit
    finally:
        try:
            subprocess.run(['sync'], timeout=15)
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            subprocess.run(['sudo', '-n', RW_HELFER, 'ro'],
                           capture_output=True, timeout=15)
        except (OSError, subprocess.SubprocessError):
            pass


def berichtsordner_lokal():
    """Lokaler Ablageort – exists auch ohne Stick."""
    ordner = os.path.join(DATA_DIR, 'berichte')
    os.makedirs(ordner, exist_ok=True)
    return ordner


def erstelle_monatsbericht(jahr, monat, erzeugt_am=None):
    """Erzeugt den Bericht lokal und liefert den Pfad."""
    pfad = os.path.join(berichtsordner_lokal(), _dateiname(jahr, monat))
    return erstelle_bericht(pfad, jahr, monat, erzeugt_am=erzeugt_am)


def kopiere_auf_stick(mount_dir):
    """Kopiert alle lokalen Berichte, die auf dem Stick fehlen.

    Die Excel wird nie angefasst – geschrieben werden ausschließlich PDFs im
    eigenen Ordner ``LHTPi-Berichte/``.
    """
    with schreibfenster(mount_dir) as bereit:
        if not bereit:
            return {'kopiert': [], 'vorhanden': [],
                    'fehler': 'Stick ließ sich nicht beschreibbar schalten'}
        return _kopiere_dateien(mount_dir)


def _kopiere_dateien(mount_dir):
    """Kopiert ohne eigenes Schreibfenster (Aufrufer hält es bereits)."""
    ziel_ordner = os.path.join(mount_dir, BERICHT_ORDNER)
    ergebnis = {'kopiert': [], 'vorhanden': [], 'fehler': None}

    if not os.path.isdir(mount_dir):
        ergebnis['fehler'] = 'Stick nicht gefunden'
        return ergebnis

    try:
        os.makedirs(ziel_ordner, exist_ok=True)
        for name in sorted(os.listdir(berichtsordner_lokal())):
            if not name.lower().endswith('.pdf'):
                continue
            quelle = os.path.join(berichtsordner_lokal(), name)
            ziel = os.path.join(ziel_ordner, name)
            if os.path.exists(ziel):
                ergebnis['vorhanden'].append(name)
                continue
            with open(quelle, 'rb') as fq, open(ziel, 'wb') as fz:
                fz.write(fq.read())
            ergebnis['kopiert'].append(name)
    except OSError as fehler:
        ergebnis['fehler'] = f'Schreiben fehlgeschlagen: {fehler}'
    return ergebnis


def bericht_fuer_jetzt():
    """Bericht für den laufenden Monat erzeugen (Menü-Knopf)."""
    jetzt = datetime.now()
    return erstelle_monatsbericht(jetzt.year, jetzt.month)


# ── Jahresübersicht ───────────────────────────────────────────────────

MONAT_KURZ = ('Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun',
              'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez')


def erstelle_jahresbericht(pfad, jahr, erzeugt_am=None):
    """Jahresübersicht im Querformat: Ausfallstunden je Prüfstand und Monat."""
    from historie import ausfall_je_pruefstand_je_monat

    erzeugt_am = erzeugt_am or datetime.now()
    daten = ausfall_je_pruefstand_je_monat(jahr)

    pdf = FPDF(orientation='L', format='A4')
    pdf.set_auto_page_break(auto=True, margin=14)

    regular, bold = _schriften_finden()
    if regular:
        pdf.add_font('Bericht', '', regular)
        if bold:
            pdf.add_font('Bericht', 'B', bold)
        schrift = 'Bericht'
    else:
        schrift = 'Helvetica'
    pdf.add_page()

    pdf.set_font(schrift, size=16)
    pdf.cell(0, 10, f'Ausfallzeiten {jahr} – Jahresübersicht',
             new_x='LMARGIN', new_y='NEXT')
    pdf.set_font(schrift, size=9)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(0, 6, f'Erstellt am {erzeugt_am.strftime("%d.%m.%Y um %H:%M")}',
             new_x='LMARGIN', new_y='NEXT')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    if not daten:
        _leer(pdf, schrift, f'Keine Ausfallzeiten in {jahr} erfasst.')
        _fussnote(pdf, schrift)
        ordner = os.path.dirname(os.path.abspath(pfad))
        if ordner:
            os.makedirs(ordner, exist_ok=True)
        pdf.output(pfad)
        return pfad

    # ── Kennzahlen
    gesamt = sum(e['stunden'] for e in daten.values())
    tage = sum(e['tage'] for e in daten.values())
    betroffen = len([e for e in daten.values() if e['stunden'] > 0])
    pdf.set_font(schrift, size=10)
    pdf.cell(0, 7,
             f'{betroffen} Prüfstände betroffen · {_std(gesamt)} Ausfallstunden · {tage} Ausfalltage',
             new_x='LMARGIN', new_y='NEXT')
    pdf.ln(2)

    # ── Monatsmatrix
    _ueberschrift(pdf, schrift, 'Ausfallstunden je Monat')
    kopf = ['Prüfstand'] + list(MONAT_KURZ) + ['Gesamt', 'Tage']
    breiten = [52] + [15] * 12 + [22, 16]
    # Monatssummen zuerst – sie stehen als letzte Tabellenzeile
    monatssummen = [0.0] * 12
    for eintrag in daten.values():
        for monat in range(1, 13):
            monatssummen[monat - 1] += eintrag['monate'].get(monat, 0.0)

    zeilen = []
    for eintrag in sorted(daten.values(), key=lambda e: (-e['stunden'], e['pruefstand'])):
        if eintrag['stunden'] <= 0:
            continue          # Prüfstand ohne Ausfallzeit gehört nicht in die Übersicht
        zeile = [eintrag['pruefstand']]
        for monat in range(1, 13):
            wert = eintrag['monate'].get(monat)
            zeile.append(_std(wert) if wert else '–')
        zeile.append(_std(eintrag['stunden']))
        zeile.append(str(eintrag['tage']))
        zeilen.append(tuple(zeile))

    summenzeile = ['Summe']
    for wert in monatssummen:
        summenzeile.append(_std(wert) if wert else '–')
    summenzeile.append(_std(gesamt))
    summenzeile.append(str(tage))
    zeilen.append(tuple(summenzeile))

    _tabelle(pdf, schrift, tuple(kopf), zeilen, breiten=tuple(breiten),
             ausrichtung=('LEFT',) + ('RIGHT',) * 14)
    pdf.ln(4)

    # ── Balken je Monat
    _monatsbalken(pdf, schrift, monatssummen)

    _fussnote(pdf, schrift)

    ordner = os.path.dirname(os.path.abspath(pfad))
    if ordner:
        os.makedirs(ordner, exist_ok=True)
    pdf.output(pfad)
    return pfad


def _monatsbalken(pdf, schrift, werte):
    """Einfache Balkengrafik der Monatssummen."""
    if not any(werte):
        return
    hoechster = max(werte)
    links = pdf.l_margin + 4
    basis = pdf.get_y() + 42
    breite = 18
    abstand = 4

    pdf.set_font(schrift, size=8)
    pdf.set_fill_color(46, 116, 181)
    for index, wert in enumerate(werte):
        x = links + index * (breite + abstand)
        hoehe = (wert / hoechster) * 34 if hoechster else 0
        if hoehe > 0:
            pdf.rect(x, basis - hoehe, breite, hoehe, style='F')
        pdf.set_text_color(90, 90, 90)
        pdf.text(x + 2, basis + 4, MONAT_KURZ[index])
        if wert:
            pdf.text(x + 2, basis - hoehe - 2, _std(wert))
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(basis + 10)


def _fussnote(pdf, schrift):
    pdf.ln(4)
    pdf.set_font(schrift, size=8)
    pdf.set_text_color(110, 110, 110)
    pdf.multi_cell(0, 4, FUSSNOTE)
    pdf.set_text_color(0, 0, 0)


def _jahresdateiname(jahr):
    return f'Terminbericht_Jahr_{jahr}.pdf'


def erstelle_jahresbericht_lokal(jahr, erzeugt_am=None):
    pfad = os.path.join(berichtsordner_lokal(), _jahresdateiname(jahr))
    return erstelle_jahresbericht(pfad, jahr, erzeugt_am=erzeugt_am)


# ── Manueller Start über den USB-Stick ────────────────────────────────

TRIGGER_NAME = 'LHTPi-Bericht.jetzt'
TRIGGER_ERLEDIGT = 'LHTPi-Bericht.erledigt'


def pruefe_stick_befehl(mount_dir):
    """Erzeugt Berichte, wenn auf dem Stick eine Auslöse-Datei liegt.

    Ablauf: Stick stecken, Datei ``LHTPi-Bericht.jetzt`` ins Stick-Haupt-
    verzeichnis legen. Der Pi erzeugt Monats- und Jahresbericht, kopiert sie
    nach ``LHTPi-Berichte/`` und benennt die Auslöse-Datei in
    ``LHTPi-Bericht.erledigt`` um.

    Liefert ``{'ausgeloest': bool, 'monat': pfad|None, 'jahr': pfad|None,
    'kopiert': [...]}``.
    """
    ergebnis = {'ausgeloest': False, 'monat': None, 'jahr': None,
                'kopiert': [], 'fehler': None}
    if not os.path.isdir(mount_dir):
        return ergebnis

    trigger = os.path.join(mount_dir, TRIGGER_NAME)
    if not os.path.exists(trigger):
        return ergebnis

    jetzt = datetime.now()
    ergebnis['monat'] = erstelle_monatsbericht(jetzt.year, jetzt.month)
    ergebnis['jahr'] = erstelle_jahresbericht_lokal(jetzt.year)

    with schreibfenster(mount_dir) as bereit:
        if not bereit:
            ergebnis['fehler'] = 'Stick ließ sich nicht beschreibbar schalten'
            return ergebnis

        kopie = _kopiere_dateien(mount_dir)
        ergebnis['kopiert'] = kopie['kopiert']
        ergebnis['fehler'] = kopie['fehler']
        ergebnis['ausgeloest'] = True

        ziel = os.path.join(mount_dir, TRIGGER_ERLEDIGT)
        try:
            os.replace(trigger, ziel)
        except OSError as fehler:
            ergebnis['erledigt_marker'] = f'konnte nicht umbenannt werden: {fehler}'
    return ergebnis
