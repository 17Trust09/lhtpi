"""Termin-Historie: Datenmodell und Import-Logik.

Zwei Regeln tragen das ganze Modul:

1. **Keine Doppelbuchung.** Jeder Vorgang hat einen natürlichen Schlüssel aus
   ``Art + Prüfstand + Von``. Ein erneuter Import derselben Zeile legt nichts
   Neues an. Ändert sich der Inhalt, wird der bestehende Vorgang zur nächsten
   Revision – er bleibt derselbe Vorgang.
2. **Auswertung rechnet auf Vorgängen, nicht auf Importen.** Ein viermal
   importierter Termin zählt genau einmal.

Die Zeitrechnung selbst steckt in :mod:`betriebszeit`.
"""
import hashlib
from datetime import datetime

from models import db

ARTEN = ('kalibrierung', 'wartung', 'ausfall', 'audit', 'info')
STATUS_WERTE = ('offen', 'abgeschlossen', 'storniert', 'entfernt')


class Pruefstand(db.Model):
    """Stammliste der Prüfstände (Dropdown-Quelle)."""
    __tablename__ = 'pruefstand'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    aktiv = db.Column(db.Boolean, nullable=False, default=True)
    sortierung = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f'<Pruefstand {self.name}>'


class Vorgang(db.Model):
    """Ein Termin – einmalig, mit Revision und Status."""
    __tablename__ = 'vorgang'

    id = db.Column(db.Integer, primary_key=True)
    nr = db.Column(db.Integer)                       # Nummer aus der Excel (nur Info)
    art = db.Column(db.String(20), nullable=False)
    pruefstand = db.Column(db.String(80), nullable=False)
    von = db.Column(db.DateTime, nullable=False)
    bis = db.Column(db.DateTime)
    info = db.Column(db.String(500))

    status = db.Column(db.String(20), nullable=False, default='offen')
    natural_key = db.Column(db.String(200), unique=True, nullable=False)
    revision = db.Column(db.Integer, nullable=False, default=1)
    inhalt_hash = db.Column(db.String(64), nullable=False)
    quelle = db.Column(db.String(10), nullable=False, default='usb')

    abgeschlossen_am = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    zeiten = db.relationship(
        'VorgangZeit', backref='vorgang',
        cascade='all, delete-orphan',
        order_by='VorgangZeit.von',
    )

    @property
    def zaehlt_als_ausfall(self):
        """True, wenn der Vorgang in die Ausfallstatistik eingeht."""
        return self.status in ('offen', 'abgeschlossen') and self.art in (
            'kalibrierung', 'wartung', 'ausfall')

    def __repr__(self):
        return f'<Vorgang {self.id} {self.art} {self.pruefstand} {self.von}>'


class VorgangZeit(db.Model):
    """Ein Block, in dem der Prüfstand tatsächlich nicht nutzbar war."""
    __tablename__ = 'vorgang_zeit'

    id = db.Column(db.Integer, primary_key=True)
    vorgang_id = db.Column(db.Integer, db.ForeignKey('vorgang.id'), nullable=False)
    von = db.Column(db.DateTime, nullable=False)
    bis = db.Column(db.DateTime, nullable=False)
    notiz = db.Column(db.String(200))

    def __repr__(self):
        return f'<VorgangZeit {self.von}–{self.bis}>'


class ImportLauf(db.Model):
    """Protokoll jedes USB-Imports."""
    __tablename__ = 'import_lauf'

    id = db.Column(db.Integer, primary_key=True)
    zeitpunkt = db.Column(db.DateTime, default=datetime.now, nullable=False)
    dateiname = db.Column(db.String(200))
    datei_hash = db.Column(db.String(64))
    zeilen = db.Column(db.Integer, default=0)
    neu = db.Column(db.Integer, default=0)
    geaendert = db.Column(db.Integer, default=0)
    unveraendert = db.Column(db.Integer, default=0)
    entfernt = db.Column(db.Integer, default=0)
    fehler = db.Column(db.Integer, default=0)
    bericht = db.Column(db.Text)


# ── Schlüssel und Hashes ──────────────────────────────────────────────

def _norm_art(art):
    return str(art or '').strip().lower()


def _norm_pruefstand(pruefstand):
    return ' '.join(str(pruefstand or '').split())


def _iso(wert):
    if wert is None:
        return ''
    return wert.strftime('%Y-%m-%dT%H:%M')


def natural_key(art, pruefstand, von):
    """Eindeutiger Schlüssel: Art + Prüfstand + Startzeitpunkt."""
    return f'{_norm_art(art)}|{_norm_pruefstand(pruefstand)}|{_iso(von)}'


def inhalt_hash(art, pruefstand, von, bis, info, zeiten, status='offen'):
    """Prüfsumme über alle inhaltlichen Felder inklusive Blöcke und Status."""
    teile = [
        _norm_art(art),
        _norm_pruefstand(pruefstand),
        _iso(von),
        _iso(bis),
        ' '.join(str(info or '').split()),
        str(status or '').strip().lower(),
    ]
    for z_von, z_bis in sorted(zeiten or [], key=lambda p: (p[0], p[1])):
        teile.append(f'{_iso(z_von)}>{_iso(z_bis)}')
    return hashlib.sha256('|'.join(teile).encode('utf-8')).hexdigest()


# ── Import ────────────────────────────────────────────────────────────

def _pruefstand_sicherstellen(name, report):
    """Legt einen unbekannten Prüfstand an und vermerkt ihn im Report."""
    p = Pruefstand.query.filter_by(name=name).first()
    if p is not None:
        return p
    p = Pruefstand(name=name, aktiv=True)
    db.session.add(p)
    db.session.flush()
    report['neue_pruefstaende'].append(name)
    return p


def _bloecke_fuer(nr, bloecke):
    """Blöcke einer Excel-Zeile als sortierte Liste von (von, bis)."""
    if not bloecke or nr is None:
        return []
    eintraege = bloecke.get(nr) or bloecke.get(str(nr)) or []
    return sorted(eintraege, key=lambda p: (p[0], p[1]))


def _wirkungszeitraeume(vorgang):
    """Zeiträume, in denen der Vorgang tatsächlich wirkt (Blöcke oder Von–Bis)."""
    if vorgang.zeiten:
        return [(z.von, z.bis) for z in vorgang.zeiten]
    return [(vorgang.von, vorgang.bis or vorgang.von)]


def _ueberlappungen_pruefen(report):
    """Warnt bei sich überschneidenden Vorgängen desselben Prüfstands.

    Verglichen werden die tatsächlichen Zeiträume (Blöcke, wenn vorhanden) –
    nicht die Von–Bis-Hülle, sonst warnt es bei unterbrochenen Kalibrierungen
    grundlos.
    """
    vorgaenge = (Vorgang.query
                 .filter(Vorgang.status.in_(('offen', 'abgeschlossen')))
                 .filter(Vorgang.art.in_(('kalibrierung', 'wartung', 'ausfall')))
                 .all())
    nach_pruefstand = {}
    for v in vorgaenge:
        nach_pruefstand.setdefault(v.pruefstand, []).append(v)

    for name, liste in nach_pruefstand.items():
        zeitfenster = []
        for v in liste:
            for von, bis in _wirkungszeitraeume(v):
                zeitfenster.append((von, bis, v))
        zeitfenster.sort(key=lambda e: e[0])
        for (a_von, a_bis, a), (b_von, b_bis, b) in zip(zeitfenster, zeitfenster[1:]):
            if a.id == b.id:
                continue
            if a_bis > b_von:
                report['ueberlappungen'].append({
                    'pruefstand': name,
                    'a': a_von.strftime('%d.%m.%Y %H:%M'),
                    'b': b_von.strftime('%d.%m.%Y %H:%M'),
                })


def importiere(zeilen, bloecke=None, quelle='usb', dateiname=None, datei_hash=None):
    """Importiert Excel-Zeilen in die Historie.

    ``zeilen``  – Liste von Dicts mit ``nr, art, pruefstand, von, bis, info, status``
    ``bloecke`` – optional ``{nr: [(von, bis), ...]}`` aus dem Blatt „Zeiten"

    Liefert einen Report mit Zählern, Fehlern, neuen Prüfständen und
    Überlappungswarnungen.
    """
    report = {
        'neu': 0,
        'geaendert': 0,
        'unveraendert': 0,
        'entfernt': 0,
        'fehler': [],
        'neue_pruefstaende': [],
        'ueberlappungen': [],
    }
    gesehen = set()          # natural keys der verarbeiteten Zeilen
    gesehen_basis = set()    # (Prüfstand, Von) – auch aus fehlerhaften Zeilen

    for z in zeilen:
        nr = z.get('nr')
        art = _norm_art(z.get('art'))
        pruefstand = _norm_pruefstand(z.get('pruefstand'))
        von = z.get('von')
        bis = z.get('bis') or von
        info = (z.get('info') or '').strip()
        status = str(z.get('status') or 'offen').strip().lower() or 'offen'

        # Basis-Merker schon vor der Prüfung: Eine Zeile mit Tippfehler in der
        # Art oder im Datum darf den bisher gültigen Vorgang nicht entfernen.
        if pruefstand and isinstance(von, datetime):
            gesehen_basis.add((pruefstand, _iso(von)))

        if art not in ARTEN:
            report['fehler'].append({'nr': nr, 'grund': f'unbekannte Art: {z.get("art")!r}'})
            continue
        if not pruefstand:
            report['fehler'].append({'nr': nr, 'grund': 'Prüfstand fehlt'})
            continue
        if not isinstance(von, datetime):
            report['fehler'].append({'nr': nr, 'grund': 'Von fehlt oder ungültig'})
            continue
        if bis < von:
            report['fehler'].append({'nr': nr, 'grund': 'Bis liegt vor Von'})
            continue
        if status not in STATUS_WERTE:
            report['fehler'].append({'nr': nr, 'grund': f'unbekannter Status: {status!r}'})
            continue

        key = natural_key(art, pruefstand, von)
        if key in gesehen:
            report['fehler'].append({'nr': nr, 'grund': 'doppelte Zeile in der Datei'})
            continue
        gesehen.add(key)

        bloecke_zeile = _bloecke_fuer(nr, bloecke)
        h = inhalt_hash(art, pruefstand, von, bis, info, bloecke_zeile, status)

        _pruefstand_sicherstellen(pruefstand, report)

        vorgang = Vorgang.query.filter_by(natural_key=key).first()

        if vorgang is None:
            vorgang = Vorgang(
                nr=nr, art=art, pruefstand=pruefstand, von=von, bis=bis,
                info=info, status=status, natural_key=key, revision=1,
                inhalt_hash=h, quelle=quelle,
                abgeschlossen_am=datetime.now() if status == 'abgeschlossen' else None,
            )
            db.session.add(vorgang)
            db.session.flush()
            _zeiten_setzen(vorgang, bloecke_zeile)
            report['neu'] += 1
            continue

        if vorgang.inhalt_hash == h:
            report['unveraendert'] += 1
            continue

        # Inhalt geändert → neue Revision desselben Vorgangs
        vorgang.nr = nr
        vorgang.art = art
        vorgang.pruefstand = pruefstand
        vorgang.von = von
        vorgang.bis = bis
        vorgang.info = info
        vorgang.quelle = quelle
        if status != vorgang.status:
            vorgang.status = status
            if status == 'abgeschlossen' and vorgang.abgeschlossen_am is None:
                vorgang.abgeschlossen_am = datetime.now()
        vorgang.revision = (vorgang.revision or 1) + 1
        vorgang.inhalt_hash = h
        _zeiten_setzen(vorgang, bloecke_zeile)
        report['geaendert'] += 1

    # Zeilen, die nicht mehr in der Datei stehen.
    # Sicherheitsregel: Enthält die Datei Fehler, wird nichts entfernt – eine
    # kaputte Zeile ist kein Beweis, dass ein Termin gelöscht wurde.
    if report['fehler']:
        report['hinweis'] = ('Datei enthält Fehler – keine Termine als entfernt '
                             'markiert. Bitte Zeilen korrigieren und erneut importieren.')
    else:
        _entfernte_markieren(gesehen, gesehen_basis, report)

    _ueberlappungen_pruefen(report)

    lauf = ImportLauf(
        dateiname=dateiname,
        datei_hash=datei_hash,
        zeilen=len(zeilen),
        neu=report['neu'],
        geaendert=report['geaendert'],
        unveraendert=report['unveraendert'],
        entfernt=report['entfernt'],
        fehler=len(report['fehler']),
        bericht=str(report['fehler']) if report['fehler'] else None,
    )
    db.session.add(lauf)
    db.session.commit()
    report['import_id'] = lauf.id
    return report


def _entfernte_markieren(gesehen, gesehen_basis, report):
    """Markiert offene Vorgänge, die in der Datei nicht mehr vorkommen."""
    for vorgang in Vorgang.query.filter_by(status='offen').all():
        if vorgang.natural_key in gesehen:
            continue
        if (_norm_pruefstand(vorgang.pruefstand), _iso(vorgang.von)) in gesehen_basis:
            continue
        vorgang.status = 'entfernt'
        report['entfernt'] += 1


def _zeiten_setzen(vorgang, zeiten):
    """Ersetzt die Blöcke eines Vorgangs vollständig."""
    for alt in list(vorgang.zeiten):
        db.session.delete(alt)
    db.session.flush()
    for von, bis in zeiten:
        db.session.add(VorgangZeit(vorgang_id=vorgang.id, von=von, bis=bis))
    db.session.flush()


# ── Auswertung ────────────────────────────────────────────────────────

def ausfall_je_pruefstand(jahr=None):
    """Ausfallstunden und -tage je Prüfstand – eine Summe, keine Aufteilung.

    Rechnet ausschließlich auf Vorgängen (eine Zeile je Termin), nie auf
    Import-Läufen – damit mehrfach importierte Termine nicht doppelt zählen.
    """
    query = Vorgang.query.filter(Vorgang.status.in_(('offen', 'abgeschlossen')))
    ergebnis = {}

    for v in query.all():
        if not v.zaehlt_als_ausfall:
            continue
        if jahr and not _beruehrt_jahr(v, jahr):
            continue

        eintrag = ergebnis.setdefault(v.pruefstand, {
            'pruefstand': v.pruefstand,
            'stunden': 0.0,
            'tage': set(),
            'vorgaenge': 0,
        })

        stunden = _stunden_im_jahr(v, jahr)
        if v.zeiten:
            tage = _betriebstage_von_bloecken(v.zeiten, jahr)
        else:
            tage = _betriebstage_von_zeitraum(v.von, v.bis or v.von, jahr)

        eintrag['stunden'] += stunden
        eintrag['tage'].update(tage)
        eintrag['vorgaenge'] += 1

    for eintrag in ergebnis.values():
        eintrag['stunden'] = round(eintrag['stunden'], 2)
        eintrag['tage'] = len(eintrag['tage'])
    return ergebnis


def _stunden_im_jahr(v, jahr):
    """Ausfallstunden eines Vorgangs – nur die Anteile des Zieljahres.

    Ohne diese Aufteilung würden jahresübergreifende Vorgänge in beiden
    Jahren mit der vollen Dauer gezählt.
    """
    zeitraeume = ([(z.von, z.bis) for z in v.zeiten] if v.zeiten
                  else [(v.von, v.bis or v.von)])
    summe = 0.0
    for von, bis in zeitraeume:
        for (mj, _mm), stunden in stunden_je_monat(von, bis).items():
            if jahr is None or mj == jahr:
                summe += stunden
    return round(summe, 4)


def _beruehrt_jahr(v, jahr):
    start = v.von
    ende = v.bis or v.von
    return start.year <= jahr <= ende.year


def _betriebstage_von_zeitraum(von, bis, jahr):
    from betriebszeit import betriebstage
    return {t for t in betriebstage(von, bis) if not jahr or t.year == jahr}


def _betriebstage_von_bloecken(zeiten, jahr):
    from betriebszeit import betriebstage
    tage = set()
    for z in zeiten:
        tage.update(t for t in betriebstage(z.von, z.bis) if not jahr or t.year == jahr)
    return tage


def _monatsabschnitte(von, bis):
    """Zerlegt einen Zeitraum in Monatsabschnitte (Start, Ende je Monat)."""
    from datetime import datetime as _dt

    abschnitte = []
    jahr, monat = von.year, von.month
    while (jahr, monat) <= (bis.year, bis.month):
        start = _dt(jahr, monat, 1)
        ende = _dt(jahr + 1, 1, 1) if monat == 12 else _dt(jahr, monat + 1, 1)
        abschnitte.append((jahr, monat, start, ende))
        monat += 1
        if monat > 12:
            monat = 1
            jahr += 1
    return abschnitte


def stunden_je_monat(von, bis):
    """Ausfallstunden eines Zeitraums, aufgeteilt auf Kalendermonate.

    Ein Vorgang, der über eine Monatsgrenze läuft, wird anteilig verteilt –
    sonst wäre die Jahresübersicht je Monat falsch.
    """
    from betriebszeit import betriebsstunden

    if bis <= von:
        return {}
    ergebnis = {}
    for jahr, monat, m_start, m_ende in _monatsabschnitte(von, bis):
        stunden = betriebsstunden(max(von, m_start), min(bis, m_ende))
        if stunden > 0:
            schluessel = (jahr, monat)
            ergebnis[schluessel] = ergebnis.get(schluessel, 0.0) + stunden
    return ergebnis


def ausfall_je_pruefstand_je_monat(jahr):
    """Ausfallstunden je Prüfstand und Monat für ein Jahr.

    Liefert ``{pruefstand: {'monate': {1: h, ...}, 'stunden': h, 'tage': n}}``.
    """
    from betriebszeit import betriebstage

    ergebnis = {}
    for v in Vorgang.query.filter(Vorgang.status.in_(('offen', 'abgeschlossen'))).all():
        if not v.zaehlt_als_ausfall:
            continue
        if not _beruehrt_jahr(v, jahr):
            continue

        eintrag = ergebnis.setdefault(v.pruefstand, {
            'pruefstand': v.pruefstand,
            'monate': {},
            'stunden': 0.0,
            'tage': set(),
        })

        if v.zeiten:
            for z in v.zeiten:
                for (mj, mm), h in stunden_je_monat(z.von, z.bis).items():
                    if mj == jahr:
                        eintrag['monate'][mm] = eintrag['monate'].get(mm, 0.0) + h
                eintrag['tage'].update(t for t in betriebstage(z.von, z.bis) if t.year == jahr)
        else:
            ende = v.bis or v.von
            for (mj, mm), h in stunden_je_monat(v.von, ende).items():
                if mj == jahr:
                    eintrag['monate'][mm] = eintrag['monate'].get(mm, 0.0) + h
            eintrag['tage'].update(t for t in betriebstage(v.von, ende) if t.year == jahr)

    for eintrag in ergebnis.values():
        eintrag['stunden'] = round(sum(eintrag['monate'].values()), 2)
        eintrag['monate'] = {m: round(h, 2) for m, h in eintrag['monate'].items()}
        eintrag['tage'] = len(eintrag['tage'])
    return ergebnis
