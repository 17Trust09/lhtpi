"""Betriebsmittel-Abgleich mit der Excel-Stammliste (Modell 3).

Nimmt die gelesenen Zeilen des Blatts ``Betriebsmittel`` und hält die
``betriebsmittel``-Tabelle damit synchron:

* **Leere ID** → nächste freie ``BM-NNN`` wird vergeben (und zum Zurückschreiben
  vorgemerkt).
* **Vorhandene ID** → derselbe Datensatz wird aktualisiert (Umbenennen und
  Typwechsel ändern denselben Datensatz, die Kennung bleibt).
* **Exakt gleiche** (Typ, Bezeichnung) nach Normalisierung → Fehler.
  Ähnliche Namen bleiben getrennt.
* **Zusammenführen** → Ziel muss existieren, eine andere Kennung haben und darf
  keinen Zyklus erzeugen. Vorgänge werden atomar umgehängt, die Quelle bleibt
  als Alias erhalten.
* **Fehlende frühere ID** → ``in_excel_aktiv=False``, die Historie bleibt.

Liefert einen Report inklusive Änderungen und Schreibanweisungen für die Excel.
"""
from sqlalchemy import func

from historie import (
    Betriebsmittel,
    Vorgang,
    KENNUNG_RE,
    _norm_typ,
    _norm_kennung,
    _norm_bezeichnung,
    _aufloesen_final,
)
from models import db


def _finde_nach_name(bezeichnung):
    name = _norm_bezeichnung(bezeichnung)
    if not name:
        return None
    return (Betriebsmittel.query
            .filter(func.lower(Betriebsmittel.bezeichnung) == name.casefold())
            .first())


def _max_nummer(kennungen):
    maximum = 0
    for kennung in kennungen:
        if KENNUNG_RE.fullmatch(kennung or ''):
            maximum = max(maximum, int(kennung[3:]))
    return maximum


def _naechste_nummer(bestehend, explizit=None):
    """Nächste freie BM-Nummer.

    Berücksichtigt vorhandene DB-Kennungen und **alle** expliziten Kennungen
    der aktuellen Eingabe (die Vorlagen-Seeds erscheinen dort als explizite
    IDs). So kann eine leere ID-Zeile, die vor einer expliziten ID steht, nie
    mit dieser kollidieren.
    """
    return max(_max_nummer(bestehend), _max_nummer(explizit or [])) + 1


def _hat_zyklus(target, source_id):
    """True, wenn das Umhängen von ``source_id`` auf ``target`` einen Zyklus ergibt.

    Läuft über ``merge_ziel_id`` (FK), damit innerhalb derselben Transaktion
    keine veraltete ORM-Relation gelesen wird.
    """
    gesehen = {target.id}
    aktuell = target
    while aktuell.merge_ziel_id is not None:
        nxt_id = aktuell.merge_ziel_id
        if nxt_id == source_id or nxt_id in gesehen:
            return True
        gesehen.add(nxt_id)
        aktuell = db.session.get(Betriebsmittel, nxt_id)
        if aktuell is None:
            break
    return False


def sync_betriebsmittel(rows):
    """Gleicht die Betriebsmittel-Tabelle mit den Excel-Zeilen ab.

    ``rows`` ist ``excel_modell3.lies_datei(...)['betriebsmittel']``.
    Liefert einen Report-Dict.
    """
    report = {
        'neu': [],
        'geaendert': [],
        'id_vergeben': [],
        'zusammengefuehrt': [],
        'inaktiv': [],
        'fehler': [],
        'writeback': [],
    }

    # ── Normalisieren + Duplikate melden ────────────────────────────────
    normalisiert = []
    gesehen_dup = {}
    for z in rows:
        typ = _norm_typ(z.get('typ'))
        bezeichnung = _norm_bezeichnung(z.get('bezeichnung'))
        kennung = _norm_kennung(z.get('id'))
        zusammen = _norm_kennung(z.get('zusammenfuehren_mit'))
        excel_zeile = z.get('excel_zeile')
        if not bezeichnung:
            continue                # vorausgefüllte/leere Zeile ohne Namen
        schluessel = (typ.casefold(), bezeichnung.casefold())
        if schluessel in gesehen_dup:
            report['fehler'].append({
                'excel_zeile': excel_zeile,
                'grund': 'Doppeltes Betriebsmittel (Typ+Bezeichnung identisch), '
                         'siehe Zeile %d' % gesehen_dup[schluessel],
            })
        else:
            gesehen_dup[schluessel] = excel_zeile
        normalisiert.append({
            'typ': typ, 'bezeichnung': bezeichnung, 'kennung': kennung,
            'zusammen': zusammen, 'excel_zeile': excel_zeile,
        })

    # ── IDs vergeben / Datensätze aktualisieren ────────────────────────
    bestehend_nach_kennung = {b.kennung: b for b in Betriebsmittel.query.all()}
    explizite = [z['kennung'] for z in normalisiert if z['kennung']]
    naechste = _naechste_nummer(bestehend_nach_kennung, explizite)
    zeilen_mit_bm = []
    praesent = set()

    for z in normalisiert:
        bm = None
        if z['kennung']:
            bm = bestehend_nach_kennung.get(z['kennung'])
            if bm is None:
                bm = Betriebsmittel(kennung=z['kennung'], typ=z['typ'],
                                    bezeichnung=z['bezeichnung'],
                                    in_excel_aktiv=True)
                db.session.add(bm)
                db.session.flush()
                bestehend_nach_kennung[z['kennung']] = bm
                report['neu'].append({'kennung': bm.kennung, 'typ': bm.typ,
                                      'bezeichnung': bm.bezeichnung})
            else:
                aenderungen = {}
                if bm.bezeichnung != z['bezeichnung']:
                    aenderungen['bezeichnung'] = (bm.bezeichnung, z['bezeichnung'])
                    bm.bezeichnung = z['bezeichnung']
                if bm.typ != z['typ']:
                    aenderungen['typ'] = (bm.typ, z['typ'])
                    bm.typ = z['typ']
                if not bm.in_excel_aktiv:
                    aenderungen['in_excel_aktiv'] = (False, True)
                    bm.in_excel_aktiv = True
                if aenderungen:
                    report['geaendert'].append(
                        {'kennung': bm.kennung, 'aenderungen': aenderungen})
        else:
            # Leere ID: vorhandenen Namen wiederverwenden, sonst neu anlegen.
            bm = _finde_nach_name(z['bezeichnung'])
            if bm is None:
                kennung = 'BM-%03d' % naechste
                naechste += 1
                bm = Betriebsmittel(kennung=kennung, typ=z['typ'],
                                    bezeichnung=z['bezeichnung'],
                                    in_excel_aktiv=True)
                db.session.add(bm)
                db.session.flush()
                bestehend_nach_kennung[kennung] = bm
                report['id_vergeben'].append({
                    'excel_zeile': z['excel_zeile'],
                    'bezeichnung': z['bezeichnung'], 'kennung': kennung})
                report['writeback'].append({
                    'blatt': 'Betriebsmittel', 'excel_zeile': z['excel_zeile'],
                    'kennung': kennung})
            else:
                if bm.typ != z['typ']:
                    bm.typ = z['typ']
                if not bm.in_excel_aktiv:
                    bm.in_excel_aktiv = True
        praesent.add(bm.id)
        zeilen_mit_bm.append((z, bm))

    # ── Zusammenführen ──────────────────────────────────────────────────
    for z, bm in zeilen_mit_bm:
        if not z['zusammen']:
            continue
        ziel = bestehend_nach_kennung.get(z['zusammen'])
        if ziel is None:
            report['fehler'].append({
                'excel_zeile': z['excel_zeile'],
                'grund': 'Zusammenführen-Ziel %s unbekannt' % z['zusammen']})
            continue
        if ziel.id == bm.id:
            report['fehler'].append({
                'excel_zeile': z['excel_zeile'],
                'grund': 'Zusammenführen-Ziel ist das Betriebsmittel selbst'})
            continue
        if _hat_zyklus(ziel, bm.id):
            report['fehler'].append({
                'excel_zeile': z['excel_zeile'],
                'grund': 'Zusammenführen erzeugt einen Zyklus'})
            continue
        # Endgültiges Ziel auflösen, unabhängig von der Zeilenreihenfolge:
        # A→B→C hängt A's Vorgänge direkt an C, egal ob A oder C zuerst kommt.
        ziel = _aufloesen_final(ziel)
        if _aufloesen_final(bm).id == ziel.id:
            continue                # bereits (transitiv) zusammengeführt
        bm.merge_ziel_id = ziel.id
        # Vorgänge atomar umhängen; Anzeigename gleich mitziehen.
        Vorgang.query.filter_by(betriebsmittel_id=bm.id).update(
            {'betriebsmittel_id': ziel.id, 'pruefstand': ziel.bezeichnung},
            synchronize_session=False)
        report['zusammengefuehrt'].append(
            {'quelle': bm.kennung, 'ziel': ziel.kennung})

    # ── Fehlende frühere Excel-IDs als inaktiv markieren ───────────────
    for bm in Betriebsmittel.query.filter_by(in_excel_aktiv=True).all():
        if bm.id in praesent:
            continue
        bm.in_excel_aktiv = False
        report['inaktiv'].append(
            {'kennung': bm.kennung, 'bezeichnung': bm.bezeichnung})

    db.session.commit()
    return report
