"""Anzeige-Router: welcher Bildschirm zeigt welche Tools — fest oder rotierend.

Regeln:
  * Ein Tool auf einem Bildschirm  -> ``mode = 'fixed'``  (kein Timer)
  * Mehrere Tools                 -> ``mode = 'rotate'`` (Rotation mit Anzeigedauer)
  * Kein aktives Tool             -> ``mode = 'empty'``  (Hinweis statt Schwarz)

Nicht installierte (und damit nicht lizenzierte) Tools werden nie ausgeliefert.
"""
from models import db, KioskScreen, KioskScreenTool
from usb_source import get_setting, set_setting
import kiosk_tools as tools

SETTING_SCREEN_COUNT = 'kiosk_screen_count'
SETTING_CURSOR_IDLE = 'kiosk_cursor_idle_seconds'
SETTING_IFRAME_RELOAD = 'kiosk_iframe_reload_minutes'

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


def iframe_reload_minutes():
    return _as_int(get_setting(SETTING_IFRAME_RELOAD, DEFAULT_IFRAME_RELOAD),
                   DEFAULT_IFRAME_RELOAD, 1, 240)


def set_iframe_reload_minutes(value):
    set_setting(SETTING_IFRAME_RELOAD,
                str(_as_int(value, DEFAULT_IFRAME_RELOAD, 1, 240)))


def screen_count():
    return _as_int(get_setting(SETTING_SCREEN_COUNT, DEFAULT_SCREEN_COUNT),
                   DEFAULT_SCREEN_COUNT, 1, MAX_SCREENS)


def set_screen_count(count):
    """Anzahl der Bildschirme setzen (1 oder 2). Bildschirm > count wird deaktiviert."""
    count = _as_int(count, DEFAULT_SCREEN_COUNT, 1, MAX_SCREENS)
    set_setting(SETTING_SCREEN_COUNT, str(count))
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


def ensure_defaults():
    """Fehlende Bildschirme anlegen und sinnvoll vorbelegen (idempotent)."""
    changed = False
    for idx in range(1, MAX_SCREENS + 1):
        if get_screen(idx) is None:
            screen = KioskScreen(idx=idx, name='Bildschirm %d' % idx,
                                 hdmi=HDMI_NAMES[idx - 1],
                                 enabled=idx <= screen_count())
            db.session.add(screen)
            db.session.flush()
            for position, (tool, dwell) in enumerate(DEFAULT_LAYOUT.get(idx, [])):
                if not tools.is_installed(tool):
                    continue
                db.session.add(KioskScreenTool(
                    screen_id=screen.id, tool=tool, sort=position,
                    dwell_seconds=dwell or tools.default_dwell(tool), enabled=True))
            changed = True
    if changed:
        db.session.commit()
    return changed


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
    db.session.commit()
    return screen


# ── Konfiguration für die Anzeige ────────────────────────────────────────────

def screen_config(idx, with_probe=True):
    """Alles, was die Router-Seite für einen Bildschirm braucht."""
    screen = get_screen(idx)
    if screen is None or not screen.enabled:
        return None

    entries = []
    for st in sorted(screen.tools, key=lambda x: (x.sort, x.id or 0)):
        if not st.enabled or not tools.is_known(st.tool) or not tools.is_installed(st.tool):
            continue
        url = tools.default_url(st.tool)
        entries.append({
            'tool': st.tool,
            'label': tools.label(st.tool),
            'short': tools.short(st.tool),
            'url': url,
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
        'installed': tools.installed_tools(),
        'known': [{'id': t, 'label': tools.label(t), 'dwell': tools.default_dwell(t),
                   'installed': tools.is_installed(t)} for t in tools.tool_ids()],
    }
