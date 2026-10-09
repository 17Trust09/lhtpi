"""Anzeige-Router: welcher Bildschirm zeigt welche Tools — fest oder rotierend.

Regeln:
  * Ein Tool auf einem Bildschirm  -> ``mode = 'fixed'``  (kein Timer)
  * Mehrere Tools                 -> ``mode = 'rotate'`` (Rotation mit Anzeigedauer)
  * Kein aktives Tool             -> ``mode = 'empty'``  (Hinweis statt Schwarz)

Nicht installierte (und damit nicht lizenzierte) Tools werden nie ausgeliefert.
"""
import glob
import json
import shutil
import os
from models import db, KioskScreen, KioskScreenTool
from usb_source import get_setting, set_setting
import kiosk_tools as tools

SETTING_SCREEN_COUNT = 'kiosk_screen_count'
SETTING_CURSOR_IDLE = 'kiosk_cursor_idle_seconds'
SETTING_IFRAME_RELOAD = 'kiosk_iframe_reload_minutes'
SETTING_LAYOUT_TOUCHED = 'kiosk_layout_touched'   # Admin hat die Belegung gespeichert
SETTING_WARTUNG_KNOPF = 'kiosk_wartung_knopf'    # Wartungs-Knopf in der Ecke

DEFAULT_SCREEN_COUNT = 1
DEFAULT_CURSOR_IDLE = 3          # Sekunden ohne Mausbewegung -> Cursor aus
DEFAULT_IFRAME_RELOAD = 30       # Minuten bis ein Tool-Frame neu geladen wird
MAX_SCREENS = 2
HDMI_NAMES = ['HDMI-1', 'HDMI-2']

# Werkseinstellung: Bildschirm 1 = Folien fest, Bildschirm 2 = Termine fest
DEFAULT_LAYOUT = {
    1: [('slideshow', None)],
    2: [('terminboard', None)],
}


# ── Einstellungen ────────────────────────────────────────────────────────────

def _as_int(value, default, low, high):
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, n))


def cursor_idle_seconds():
    return _as_int(get_setting(SETTING_CURSOR_IDLE, DEFAULT_CURSOR_IDLE),
                   DEFAULT_CURSOR_IDLE, 1, 120)


def set_cursor_idle_seconds(value):
    set_setting(SETTING_CURSOR_IDLE, str(_as_int(value, DEFAULT_CURSOR_IDLE, 1, 120)))


def wartung_knopf():
    """Darf am Bildschirm ein Wartungs-Knopf erscheinen (Mausbewegung)?"""
    return str(get_setting(SETTING_WARTUNG_KNOPF, '1')).strip() != '0'


def set_wartung_knopf(value):
    set_setting(SETTING_WARTUNG_KNOPF, '1' if value else '0')


def iframe_reload_minutes():
    return _as_int(get_setting(SETTING_IFRAME_RELOAD, DEFAULT_IFRAME_RELOAD),
                   DEFAULT_IFRAME_RELOAD, 1, 240)


def set_iframe_reload_minutes(value):
    set_setting(SETTING_IFRAME_RELOAD,
                str(_as_int(value, DEFAULT_IFRAME_RELOAD, 1, 240)))


def screen_count():
    """Anzahl der Bildschirme: Einstellung, sonst Installer-Wert, sonst Erkennung.

    Die Hardware-Lizenz ist die Obergrenze — mehr Bildschirme als lizenziert
    werden nie ausgeliefert. Solange nichts eingestellt wurde, gilt der
    KLEINERE Wert aus Installation und Erkennung: hängt nur ein Monitor am
    Gerät, soll kein zweiter Kiosk auf demselben Schirm aufgehen.
    """
    werte = [w for w in (tools.configured_screen_count(),
                         tools.detected_screen_count()) if w]
    default = min(werte) if werte else DEFAULT_SCREEN_COUNT
    n = _as_int(get_setting(SETTING_SCREEN_COUNT, default), default, 1, MAX_SCREENS)
    grenze = tools.licensed_screen_limit()
    if grenze is not None:
        n = min(n, grenze)
    return max(1, n)


def _schreibe_screen_dateien(count):
    """Bildschirm-Anzahl für die Anzeige-Steuerung (systemd) hinterlegen.

    ``screens`` enthält die Anzahl; die Datei ``screen2`` existiert nur bei zwei
    Bildschirmen. Der zweite Kiosk prüft das beim Start, der Pfad-Wächter
    reagiert auf Änderungen — so startet/stoppt die Anzeige ohne Neustart.
    """
    # Alte Sitzung wegwerfen, damit kein fremder Tab über der Anzeige landet
    sitzungen_verwerfen()
    pfad = tools.SCREENS_FILE
    ordner = os.path.dirname(pfad)
    try:
        if ordner:
            os.makedirs(ordner, exist_ok=True)
        with open(pfad, 'w') as f:
            f.write('%d\n' % count)
    except OSError:
        pass  # ohne Schreibrecht gilt weiter die Einstellung in der Datenbank
    marke = os.path.join(ordner or '.', 'screen2')
    try:
        if count >= 2:
            open(marke, 'w').close()
        elif os.path.exists(marke):
            os.remove(marke)
    except OSError:
        pass


def ist_eingerichtet():
    """Hat die Ersteinrichtung auf diesem Gerät schon stattgefunden?"""
    try:
        import license_bundle
    except ImportError:
        return True
    return os.path.exists(license_bundle.MARKER_FILE)


def _ohne_wiederherstellung(profil):
    """Im Chromium-Profil dauerhaft abschalten, dass Seiten wiederhergestellt
    werden.

    Sonst bringt Chromium nach einem Neustart die zuletzt offene Seite als
    normales Fenster mit Tab- und Adressleiste - und legt sich damit ueber die
    Anzeige (typisch: die Anzeigen-Seite). Die Einstellung liegt in der Datei
    ``Default/Preferences`` und bleibt erhalten.
    """
    pfad = os.path.join(profil, 'Default', 'Preferences')
    daten = {}
    try:
        with open(pfad, encoding='utf-8') as fh:
            daten = json.load(fh) or {}
    except (OSError, ValueError):
        daten = {}
    if not isinstance(daten, dict):
        daten = {}
    daten['session'] = dict(daten.get('session') or {}, restore_on_startup=4,
                            startup_urls=[])
    daten['profile'] = dict(daten.get('profile') or {}, exit_type='Normal',
                            exited_cleanly=True)
    try:
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, 'w', encoding='utf-8') as fh:
            json.dump(daten, fh)
    except OSError:
        pass


def sitzungen_verwerfen():
    """Alte Chromium-Sitzung der Kiosk-Fenster verwerfen.

    Chromium stellt nach einem Abbruch die zuletzt offene Seite wieder her -
    als normales Fenster mit Browserleiste. Das legt sich dann über die Anzeige
    (typisch: die Anzeigen-Seite). Darum die Sitzungsdateien vor jedem Neustart
    der Fenster wegwerfen. Inhalte der Tools bleiben unberührt.
    """
    basis = os.path.join(os.path.expanduser('~'), '.config')
    for muster in ('chromium-screen*', 'chromium-setup'):
        for profil in glob.glob(os.path.join(basis, muster)):
            for name in ('Current Session', 'Current Tabs',
                         'Last Session', 'Last Tabs'):
                try:
                    os.remove(os.path.join(profil, 'Default', name))
                except OSError:
                    pass
            shutil.rmtree(os.path.join(profil, 'Default', 'Sessions'),
                          ignore_errors=True)
            _ohne_wiederherstellung(profil)


def set_screen_count(count):
    """Anzahl der Bildschirme setzen (1 oder 2). Bildschirm > count wird deaktiviert."""
    count = _as_int(count, DEFAULT_SCREEN_COUNT, 1, MAX_SCREENS)
    set_setting(SETTING_SCREEN_COUNT, str(count))
    _schreibe_screen_dateien(count)
    for idx in range(1, MAX_SCREENS + 1):
        screen = get_screen(idx)
        if screen is None:
            continue
        screen.enabled = idx <= count
    db.session.commit()
    return count


# ── Bildschirme ──────────────────────────────────────────────────────────────

def get_screen(idx):
    return KioskScreen.query.filter_by(idx=idx).first()


def active_screens():
    """Bildschirme, die laut Einstellung aktiv sind (1..screen_count)."""
    count = screen_count()
    out = []
    for idx in range(1, count + 1):
        screen = get_screen(idx)
        if screen is not None and screen.enabled:
            out.append(screen)
    return out


def default_entries(idx):
    """Vorbelegung eines Bildschirms aus den auf diesem Gerät installierten Tools.

    Werkseinstellung ist Bildschirm 1 = Folien, Bildschirm 2 = Termine. Ist das
    Wunsch-Tool nicht installiert (z. B. Abteilung mit nur Safety Cross), wird
    sinnvoll ersetzt: Bildschirm 1 zeigt alles Verfügbare, weitere Bildschirme
    zeigen das letzte verfügbare Tool fest.
    """
    installed = tools.installed_tools()
    wanted = [(t, d) for (t, d) in DEFAULT_LAYOUT.get(idx, []) if t in installed]
    if wanted:
        return wanted
    if idx == 1:
        return [(t, None) for t in installed]
    if len(installed) > 1:
        return [(installed[-1], None)]
    return []


def ensure_defaults():
    """Fehlende Bildschirme anlegen und sinnvoll vorbelegen (idempotent).

    Bildschirme, die schon existieren, aber keine Tools haben, werden nur
    nachbelegt, solange die Belegung noch nie gespeichert wurde — sonst würde
    ein bewusst leer gelassener Bildschirm beim nächsten Start wieder gefüllt
    (z. B. wenn die Lizenz beim ersten Start noch fehlte).
    """
    changed = False
    nachbelegen = not layout_touched()
    for idx in range(1, MAX_SCREENS + 1):
        screen = get_screen(idx)
        if screen is None:
            screen = KioskScreen(idx=idx, name='Bildschirm %d' % idx,
                                 hdmi=HDMI_NAMES[idx - 1],
                                 enabled=idx <= screen_count())
            db.session.add(screen)
            db.session.flush()
            for position, (tool, dwell) in enumerate(default_entries(idx)):
                db.session.add(KioskScreenTool(
                    screen_id=screen.id, tool=tool, sort=position,
                    dwell_seconds=dwell or tools.default_dwell(tool), enabled=True))
            changed = True
        elif nachbelegen and not screen.tools:
            for position, (tool, dwell) in enumerate(default_entries(idx)):
                db.session.add(KioskScreenTool(
                    screen_id=screen.id, tool=tool, sort=position,
                    dwell_seconds=dwell or tools.default_dwell(tool), enabled=True))
                changed = True
    if changed:
        db.session.commit()
    return changed


def layout_touched():
    """Hat der Admin die Belegung schon einmal gespeichert?"""
    return str(get_setting(SETTING_LAYOUT_TOUCHED, '')).strip() == '1'


def mark_layout_touched():
    set_setting(SETTING_LAYOUT_TOUCHED, '1')


def screen_url(idx):
    """Router-URL, die der Kiosk für diesen Bildschirm öffnet."""
    return '/screen/%d' % idx


def save_screen(idx, name=None, hdmi=None, entries=None, enabled=True):
    """Belegung eines Bildschirms speichern.

    ``entries`` ist eine Liste von Dicts ``{'tool', 'enabled', 'dwell', 'sort'}``.
    Unbekannte oder nicht installierte Tools werden verworfen.
    """
    screen = get_screen(idx)
    if screen is None:
        ensure_defaults()
        screen = get_screen(idx)
        if screen is None:
            return None
    if name is not None:
        screen.name = (name or '').strip()[:80]
    if hdmi is not None:
        screen.hdmi = (hdmi or '').strip()[:20]
    screen.enabled = bool(enabled)

    if entries is not None:
        wanted = {}
        for position, entry in enumerate(entries):
            tool = (entry.get('tool') or '').strip()
            if not tools.is_known(tool) or not tools.is_installed(tool):
                continue
            sort = entry.get('sort')
            try:
                sort = int(sort)
            except (TypeError, ValueError):
                sort = position
            dwell = _as_int(entry.get('dwell'), tools.default_dwell(tool), 1, 3600)
            wanted[tool] = {'sort': sort, 'dwell': dwell,
                            'enabled': bool(entry.get('enabled', True))}
        # Vorhandene Einträge aktualisieren/entfernen, neue anlegen
        for existing in list(screen.tools):
            if existing.tool not in wanted:
                db.session.delete(existing)
                continue
            data = wanted.pop(existing.tool)
            existing.sort = data['sort']
            existing.dwell_seconds = data['dwell']
            existing.enabled = data['enabled']
        for tool, data in wanted.items():
            db.session.add(KioskScreenTool(
                screen_id=screen.id, tool=tool, sort=data['sort'],
                dwell_seconds=data['dwell'], enabled=data['enabled']))
        # Ab jetzt gilt die Belegung als bewusst gesetzt: ein leer gelassener
        # Bildschirm wird beim nächsten Start NICHT wieder gefüllt.
        mark_layout_touched()
    db.session.commit()
    return screen


# ── Konfiguration für die Anzeige ────────────────────────────────────────────

def tool_url(tool, cursor_idle=None):
    """Tool-URL, wie sie die Anzeige einbettet (Cursor-Idle wird mitgegeben)."""
    url = tools.default_url(tool)
    if not url:
        return url
    if cursor_idle is None:
        cursor_idle = cursor_idle_seconds()
    sep = '&' if '?' in url else '?'
    return '%s%scursor_idle=%d' % (url, sep, int(cursor_idle))


def screen_config(idx, with_probe=True):
    """Alles, was die Router-Seite für einen Bildschirm braucht."""
    screen = get_screen(idx)
    if screen is None or not screen.enabled:
        return None

    idle = cursor_idle_seconds()
    entries = []
    for st in sorted(screen.tools, key=lambda x: (x.sort, x.id or 0)):
        if not st.enabled or not tools.is_known(st.tool) or not tools.is_installed(st.tool):
            continue
        url = tools.default_url(st.tool)
        entries.append({
            'tool': st.tool,
            'label': tools.label(st.tool),
            'short': tools.short(st.tool),
            'url': tool_url(st.tool, idle),
            'dwell': int(st.dwell_seconds or tools.default_dwell(st.tool)),
            'alive': tools.probe(url) if with_probe else True,
        })

    active = [e for e in entries if e['alive']]
    if len(active) > 1:
        mode = 'rotate'
    elif len(active) == 1:
        mode = 'fixed'
    else:
        mode = 'empty'

    return {
        'idx': screen.idx,
        'name': screen.name or ('Bildschirm %d' % screen.idx),
        'hdmi': screen.hdmi or HDMI_NAMES[screen.idx - 1],
        'enabled': bool(screen.enabled),
        'mode': mode,
        'tools': active,            # nur lebende Tools werden angezeigt
        'all_tools': entries,       # inkl. toter Tools (Diagnose im Admin)
        'cursor_idle': cursor_idle_seconds(),
        'reload_minutes': iframe_reload_minutes(),
        'wartung_knopf': wartung_knopf(),
    }


def all_screen_configs(with_probe=True):
    configs = []
    for idx in range(1, MAX_SCREENS + 1):
        screen = get_screen(idx)
        if screen is None or not screen.enabled:
            continue
        configs.append(screen_config(idx, with_probe=with_probe))
    return configs


def display_overview():
    """Daten für die Admin-Seite „Anzeigen"."""
    ensure_defaults()
    screens = []
    for idx in range(1, MAX_SCREENS + 1):
        screen = get_screen(idx)
        if screen is None:
            continue
        rows = []
        for st in sorted(screen.tools, key=lambda x: (x.sort, x.id or 0)):
            if not tools.is_known(st.tool):
                continue
            rows.append({
                'tool': st.tool,
                'label': tools.label(st.tool),
                'enabled': bool(st.enabled),
                'dwell': int(st.dwell_seconds or tools.default_dwell(st.tool)),
                'sort': int(st.sort or 0),
                'installed': tools.is_installed(st.tool),
            })
        # installierte, aber noch nicht zugeordnete Tools mit anbieten
        for tool in tools.installed_tools():
            if not any(r['tool'] == tool for r in rows):
                rows.append({'tool': tool, 'label': tools.label(tool),
                             'enabled': False, 'dwell': tools.default_dwell(tool),
                             'sort': len(rows), 'installed': True})
        screens.append({
            'idx': screen.idx,
            'name': screen.name or ('Bildschirm %d' % screen.idx),
            'hdmi': screen.hdmi or HDMI_NAMES[screen.idx - 1],
            'enabled': bool(screen.enabled),
            'rows': rows,
        })
    return {
        'screens': screens,
        'count': screen_count(),
        'max_screens': MAX_SCREENS,
        'cursor_idle': cursor_idle_seconds(),
        'reload_minutes': iframe_reload_minutes(),
        'wartung_knopf': wartung_knopf(),
        'installed': tools.installed_tools(),
        'labels': {t: tools.label(t) for t in tools.tool_ids()},
        'admin_urls': {t: tools.admin_url(t) for t in tools.tool_ids()},
        'known': [{'id': t, 'label': tools.label(t), 'dwell': tools.default_dwell(t),
                   'installed': tools.is_installed(t)} for t in tools.tool_ids()],
    }
