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
import re
from datetime import datetime

from models import db

ARTEN = ('kalibrierung', 'wartung', 'ausfall', 'audit', 'info')
STATUS_WERTE = ('offen', 'abgeschlossen', 'storniert', 'entfernt')

# Modell 3 kennt kein "storniert" mehr – nur offen/abgeschlossen/entfernt.
MODELL3_STATUS = ('offen', 'abgeschlossen')
# Betriebsmittel-Typen (intern kleingeschrieben).
TYPEN = ('pruefstand', 'konsole')
KENNUNG_RE = re.compile(r'BM-\d{3}')


class Pruefstand(db.Model):
    """Stammliste der Prüfstände (Dropdown-Quelle)."""
    __tablename__ = 'pruefstand'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    aktiv = db.Column(db.Boolean, nullable=False, default=True)
    sortierung = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f'<Pruefstand {self.name}>'


class Betriebsmittel(db.Model):
    """Stabiles Betriebsmittel (Prüfstand oder Konsole) für Modell 3.

    Die ``kennung`` (``BM-001`` …) ist die unveränderliche Identität, an der
    Vorgänge hängen. ``bezeichnung`` und ``typ`` dürfen sich ändern, die
    Kennung bleibt. ``in_excel_aktiv`` beschreibt nur, ob das Betriebsmittel
    (noch) in der Excel-Stammliste steht – die Historie bleibt erhalten, auch
    wenn es dort gelöscht wurde. ``merge_ziel`` ist der optionale Alias/
    Zusammenführungs-Verweis auf ein anderes Betriebsmittel.
    """
    __tablename__ = 'betriebsmittel'

    id = db.Column(db.Integer, primary_key=True)
    kennung = db.Column(db.String(20), unique=True, nullable=False)
    typ = db.Column(db.String(20), nullable=False, default='pruefstand')
    bezeichnung = db.Column(db.String(80), nullable=False)
    in_excel_aktiv = db.Column(db.Boolean, nullable=False, default=True)
    merge_ziel_id = db.Column(db.Integer, db.ForeignKey('betriebsmittel.id'))
    sortierung = db.Column(db.Integer, nullable=False, default=0)

    merge_ziel = db.relationship(
        'Betriebsmittel', remote_side='Betriebsmittel.id',
        foreign_keys=[merge_ziel_id])

    # Kompatibilitäts-Aliase für alten Code, der von ``name``/``aktiv`` liest.
    @property
    def name(self):
        return self.bezeichnung

    @property
    def aktiv(self):
        return self.in_excel_aktiv

    def __repr__(self):
        return f'<Betriebsmittel {self.kennung} {self.bezeichnung}>'


class Vorgang(db.Model):
    """Ein Termin – einmalig, mit Revision und Status."""
    __tablename__ = 'vorgang'

    id = db.Column(db.Integer, primary_key=True)
    nr = db.Column(db.Integer)                       # Nummer aus der Excel (nur Info)
    vorgangsnummer = db.Column(db.String(20), unique=True, nullable=True)  # T-NNN/N-NNN (Modell 3)
    art = db.Column(db.String(20), nullable=False)
    pruefstand = db.Column(db.String(80), nullable=False)
    betriebsmittel_id = db.Column(db.Integer, db.ForeignKey('betriebsmittel.id'))
    titel = db.Column(db.String(200))                # Titel für News (Modell 3)
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

    betriebsmittel = db.relationship(
        'Betriebsmittel', foreign_keys=[betriebsmittel_id])

    zeiten = db.relationship(
        'VorgangZeit', backref='vorgang',
        cascade='all, delete-orphan',
        order_by='VorgangZeit.von',
    )

    @property
    def zaehlt_als_ausfall(self):
        """True, wenn der Vorgang in die Ausfallstatistik eingeht."""
        # Nur abgeschlossene zählen: ein noch offener Termin ist kein
        # bestätigter Ausfall, sondern erst eine Ankündigung.
        return self.status == 'abgeschlossen' and self.art in (
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


# ── Normalisierung Modell 3 ───────────────────────────────────────────

def _norm_typ(typ):
    """'Prüfstand'→'pruefstand', 'Konsole'→'konsole' (sonst kleingeschrieben)."""
    t = str(typ or '').strip().lower()
    if t == 'prüfstand':
        return 'pruefstand'
    return t


def _norm_kennung(kennung):
    """Normalisiert eine BM-Kennung zu 'BM-001' oder liefert '' wenn ungültig."""
    wert = str(kennung or '').strip().upper()
    if KENNUNG_RE.fullmatch(wert):
        return wert
    return ''


def _norm_bezeichnung(bezeichnung):
    return ' '.join(str(bezeichnung or '').split())


def _norm_status_m3(status):
    wert = str(status or '').strip().lower()
    return wert if wert in MODELL3_STATUS else ''


def _norm_art_m3(art):
    return str(art or '').strip().lower()


def _bm_name(vorgang):
    """Aktueller Betriebsmittel-Name eines Vorgangs (FK zuerst, sonst String).

    Folgt der Zusammenführungs-Kette bis zum endgültigen Ziel – ein Vorgang an
    einem Alias zählt unter dem Namen des Ziels.
    """
    if vorgang.betriebsmittel is not None:
        return _aufloesen_final(vorgang.betriebsmittel).bezeichnung
    return vorgang.pruefstand


def _bm_typ(vorgang):
    if vorgang.betriebsmittel is not None:
        return _aufloesen_final(vorgang.betriebsmittel).typ
    return 'pruefstand'


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
    """Markiert offene Vorgänge, die in der Datei nicht mehr vorkommen.

    Betrifft nur Modell-2-Vorgänge (ohne ``vorgangsnummer``) – Modell-3-Zeilen
    verwaltet ``importiere_modell3`` eigenständig.
    """
    for vorgang in Vorgang.query.filter_by(status='offen').all():
        if vorgang.vorgangsnummer:
            continue
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


# ── Import Modell 3 ───────────────────────────────────────────────────

def _aufloesen_final(bm):
    """Folgt der Zusammenführungs-Kette bis zum endgültigen Ziel.

    Läuft über die FK-Spalte ``merge_ziel_id`` (nicht über die ORM-Relation),
    damit auch innerhalb einer laufenden Transaktion kein veralteter
    Relationship-Cache gelesen wird – ``merge_ziel_id`` wird direkt gesetzt
    und ist daher immer aktuell.
    """
    gesehen = {bm.id}
    aktuell = bm
    while aktuell is not None and aktuell.merge_ziel_id is not None:
        if aktuell.merge_ziel_id in gesehen:
            break
        gesehen.add(aktuell.merge_ziel_id)
        nxt = db.session.get(Betriebsmittel, aktuell.merge_ziel_id)
        if nxt is None:
            break
        aktuell = nxt
    return aktuell


def _bm_aufloesen(typ, bezeichnung, kennung):
    """Löst ein Betriebsmittel auf: Kennung zuerst, sonst exakt Typ+Name.

    Liefert ``(Betriebsmittel|None, fehler|None)``. Eine vorhandene, aber
    ungültige oder unbekannte Kennung ist ein Fehler – der Name ist nur der
    Fallback für eine **leere** Kennung. Zusammenführungs-Aliase werden bis zum
    endgültigen Ziel aufgelöst.
    """
    typ_norm = _norm_typ(typ)
    name_norm = _norm_bezeichnung(bezeichnung)
    roh = str(kennung or '').strip()
    if roh:
        kennung_norm = _norm_kennung(roh)
        if not kennung_norm:
            return None, 'Ungültige Betriebsmittel-ID %r' % roh
        bm = Betriebsmittel.query.filter_by(kennung=kennung_norm).first()
        if bm is None:
            return None, 'Unbekannte Betriebsmittel-ID %r' % roh
        return _aufloesen_final(bm), None
    if not name_norm:
        return None, 'Betriebsmittel fehlt'
    from sqlalchemy import func
    bm = (Betriebsmittel.query
          .filter_by(typ=typ_norm)
          .filter(func.lower(Betriebsmittel.bezeichnung) == name_norm.casefold())
          .first())
    if bm is None:
        return None, 'Unbekanntes Betriebsmittel %r' % bezeichnung
    return _aufloesen_final(bm), None


def _modell3_hash(nr, art, bm_kennung, bm_name, titel, von, bis, info, status,
                  bloecke):
    teile = [
        str(nr or ''),
        _norm_art_m3(art),
        bm_kennung or '',
        _norm_bezeichnung(bm_name),
        _norm_bezeichnung(titel or ''),
        _iso(von),
        _iso(bis),
        ' '.join(str(info or '').split()),
        status,
    ]
    for z_von, z_bis in sorted(bloecke or [], key=lambda p: (p[0], p[1])):
        teile.append(f'{_iso(z_von)}>{_iso(z_bis)}')
    return hashlib.sha256('|'.join(teile).encode('utf-8')).hexdigest()


def importiere_modell3(daten, quelle='usb', dateiname=None, datei_hash=None):
    """Importiert Termine und News aus dem Modell-3-Ergebnis.

    ``daten`` ist der Rückgabewert von :func:`excel_modell3.lies_datei`.
    Identität ist die ``vorgangsnummer`` (T-NNN bzw. N-NNN), nicht mehr
    Art+Name+Von. Aktive und Archiv-Blätter werden gemeinsam gelesen.

    Parser-Fehler aus ``daten['fehler']`` fließen in den Report ein
    (``report['parser_fehler']``) und verhindern – wie Import-Fehler – dass
    irgendein bestehender Vorgang als ``entfernt`` markiert wird. Eine kaputte
    oder übersprungene Zeile ist kein Beweis, dass ein Termin gelöscht wurde.

    Die ausgeblendete BM-ID-Spalte (Termine!I) wird **nicht** zurückgeschrieben:
    dort stehen INDEX/VERGLEICH-Formeln, die nicht durch statische Werte
    zerstört werden dürfen. Der Parser löst leere Formel-Werte über Name/Typ
    auf, ein separater Schreibauftrag entfällt.
    """
    parser_fehler = list(daten.get('fehler') or [])
    report = {
        'neu': 0, 'geaendert': 0, 'unveraendert': 0, 'entfernt': 0,
        'fehler': [], 'parser_fehler': parser_fehler, 'import_id': None,
    }

    termine = list(daten.get('termine') or []) + \
        list(daten.get('archiv_termine') or [])
    news = list(daten.get('news') or []) + list(daten.get('archiv_news') or [])
    bloecke = daten.get('bloecke') or {}

    gesehen = set()

    def speichere(nr, art, bm, titel, von, bis, info, status, bloecke_zeile):
        h = _modell3_hash(nr, art, bm.kennung if bm else None,
                          bm.bezeichnung if bm else '', titel,
                          von, bis, info, status, bloecke_zeile)
        name = bm.bezeichnung if bm else ''
        vorgang = Vorgang.query.filter_by(vorgangsnummer=nr).first()
        if vorgang is None:
            vorgang = Vorgang(
                nr=None, vorgangsnummer=nr, art=art, pruefstand=name,
                betriebsmittel_id=bm.id if bm else None, titel=titel,
                von=von, bis=bis, info=info, status=status,
                natural_key='v3|' + nr, revision=1, inhalt_hash=h,
                quelle=quelle,
                abgeschlossen_am=datetime.now() if status == 'abgeschlossen' else None,
            )
            db.session.add(vorgang)
            db.session.flush()
            _zeiten_setzen(vorgang, bloecke_zeile)
            report['neu'] += 1
        elif vorgang.inhalt_hash == h:
            report['unveraendert'] += 1
        else:
            vorgang.art = art
            vorgang.pruefstand = name
            vorgang.betriebsmittel_id = bm.id if bm else None
            vorgang.titel = titel
            vorgang.von = von
            vorgang.bis = bis
            vorgang.info = info
            if status != vorgang.status:
                vorgang.status = status
                if status == 'abgeschlossen' and vorgang.abgeschlossen_am is None:
                    vorgang.abgeschlossen_am = datetime.now()
            vorgang.revision = (vorgang.revision or 1) + 1
            vorgang.inhalt_hash = h
            _zeiten_setzen(vorgang, bloecke_zeile)
            report['geaendert'] += 1
        return vorgang

    for z in termine:
        nr = str(z.get('nr') or '').strip()
        art = _norm_art_m3(z.get('art'))
        typ = _norm_typ(z.get('typ'))
        bm_name = _norm_bezeichnung(z.get('betriebsmittel'))
        von = z.get('von')
        bis = z.get('bis')
        info = (z.get('info') or '').strip()
        status = _norm_status_m3(z.get('status'))

        if not nr:
            report['fehler'].append({'nr': None, 'grund': 'Vorgangsnummer fehlt'})
            continue
        gesehen.add(nr)
        if art not in ('kalibrierung', 'wartung', 'ausfall'):
            report['fehler'].append(
                {'nr': nr, 'grund': 'unbekannte Art: %r' % z.get('art')})
            continue
        if not status:
            report['fehler'].append(
                {'nr': nr, 'grund': 'unzulässiger Status: %r' % z.get('status')})
            continue
        if not isinstance(von, datetime):
            report['fehler'].append({'nr': nr, 'grund': 'Von fehlt oder ungültig'})
            continue
        bm, fehler = _bm_aufloesen(typ, bm_name, z.get('betriebsmittel_id'))
        if bm is None:
            report['fehler'].append({'nr': nr, 'grund': fehler})
            continue

        speichere(nr, art, bm, None, von, bis, info, status,
                  _bloecke_fuer(nr, bloecke))

    for z in news:
        nr = str(z.get('nr') or '').strip()
        art = _norm_art_m3(z.get('art'))
        titel = _norm_bezeichnung(z.get('titel'))
        von = z.get('von')
        bis = z.get('bis')
        info = (z.get('info') or '').strip()
        status = _norm_status_m3(z.get('status'))

        if not nr:
            report['fehler'].append({'nr': None, 'grund': 'Vorgangsnummer fehlt'})
            continue
        gesehen.add(nr)
        if art not in ('audit', 'info'):
            report['fehler'].append(
                {'nr': nr, 'grund': 'unbekannte Art: %r' % z.get('art')})
            continue
        if not status:
            report['fehler'].append(
                {'nr': nr, 'grund': 'unzulässiger Status: %r' % z.get('status')})
            continue
        if not titel:
            report['fehler'].append({'nr': nr, 'grund': 'Titel fehlt'})
            continue
        if not isinstance(von, datetime):
            report['fehler'].append({'nr': nr, 'grund': 'Von fehlt oder ungültig'})
            continue

        speichere(nr, art, None, titel, von, bis, info, status, [])

    # Offene Modell-3-Vorgänge, deren Nummer nicht mehr vorkommt, gelten als
    # entfernt. Sicherheitsregel wie beim Modell-2-Import: bei Import- ODER
    # Parser-Fehlern wird nichts entfernt – eine kaputte/übersprungene Zeile
    # ist kein Beweis, dass der Termin gelöscht wurde.
    if not report['fehler'] and not parser_fehler:
        for vorgang in Vorgang.query.filter_by(status='offen').all():
            if not vorgang.vorgangsnummer:
                continue
            if vorgang.vorgangsnummer in gesehen:
                continue
            vorgang.status = 'entfernt'
            report['entfernt'] += 1

    alle_fehler = report['fehler'] + parser_fehler
    lauf = ImportLauf(
        dateiname=dateiname,
        datei_hash=datei_hash,
        zeilen=len(termine) + len(news),
        neu=report['neu'],
        geaendert=report['geaendert'],
        unveraendert=report['unveraendert'],
        entfernt=report['entfernt'],
        fehler=len(alle_fehler),
        bericht=str(alle_fehler) if alle_fehler else None,
    )
    db.session.add(lauf)
    db.session.commit()
    report['import_id'] = lauf.id
    return report


# ── Auswertung ────────────────────────────────────────────────────────

def ausfall_je_pruefstand(jahr=None):
    """Ausfallstunden und -tage je Prüfstand – eine Summe, keine Aufteilung.

    Rechnet ausschließlich auf Vorgängen (eine Zeile je Termin), nie auf
    Import-Läufen – damit mehrfach importierte Termine nicht doppelt zählen.
    """
    query = Vorgang.query.filter(Vorgang.status == 'abgeschlossen')
    ergebnis = {}

    for v in query.all():
        if not v.zaehlt_als_ausfall:
            continue
        if jahr and not _beruehrt_jahr(v, jahr):
            continue

        name = _bm_name(v)
        eintrag = ergebnis.setdefault(name, {
            'pruefstand': name,
            'typ': _bm_typ(v),
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
    for v in Vorgang.query.filter(Vorgang.status == 'abgeschlossen').all():
        if not v.zaehlt_als_ausfall:
            continue
        if not _beruehrt_jahr(v, jahr):
            continue

        name = _bm_name(v)
        eintrag = ergebnis.setdefault(name, {
            'pruefstand': name,
            'typ': _bm_typ(v),
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


def ausfall_je_pruefstand_im_monat(jahr, monat):
    """Ausfallstunden und -tage je Prüfstand für einen einzelnen Monat.

    Wie ``ausfall_je_pruefstand``, aber auf einen Kalendermonat begrenzt –
    für den Monatsbericht. Die Jahres-Summe bleibt im Jahresbericht.
    """
    from betriebszeit import betriebstage

    ergebnis = {}
    for v in Vorgang.query.filter(Vorgang.status == 'abgeschlossen').all():
        if not v.zaehlt_als_ausfall:
            continue
        stunden = stunden_je_monat(v.von, v.bis or v.von).get((jahr, monat), 0.0)
        if stunden <= 0:
            continue

        if v.zeiten:
            zeitraeume = [(z.von, z.bis) for z in v.zeiten]
        else:
            zeitraeume = [(v.von, v.bis or v.von)]

        tage = set()
        for von, bis in zeitraeume:
            tage.update(t for t in betriebstage(von, bis)
                        if t.year == jahr and t.month == monat)

        name = _bm_name(v)
        eintrag = ergebnis.setdefault(name, {
            'pruefstand': name,
            'typ': _bm_typ(v),
            'stunden': 0.0,
            'tage': set(),
            'vorgaenge': 0,
        })
        eintrag['stunden'] += stunden
        eintrag['tage'].update(tage)
        eintrag['vorgaenge'] += 1

    for eintrag in ergebnis.values():
        eintrag['stunden'] = round(eintrag['stunden'], 2)
        eintrag['tage'] = len(eintrag['tage'])
    return ergebnis
