"""Bildschirme lesen und setzen - fuer die Seite „Anzeigen".

Warum das in die App gehoert: Welcher Bildschirm haengt dran und in welcher
Aufloesung er laeuft, liess sich bisher nur ueber ein Skript im Terminal
sehen. Wer das Bild einstellen will, steht aber vor der Verwaltungsseite -
deshalb steht es hier, mit Knopf.

Zwei Ebenen, und das ist wichtig zu verstehen:

* **Jetzt** (xrandr): gilt sofort, bis zum naechsten Neustart.
* **Dauerhaft** (Kernel-Zeile): gilt ab dem naechsten Start, auch wenn der
  Bildschirm beim Hochfahren noch aus ist. Ohne das faellt das Geraet nach
  einem Neustart auf eine kleine Aufloesung zurueck.
"""
import os
import re
import subprocess

AUSGAENGE = ('HDMI-1', 'HDMI-2')

# Aufloesungen, die bei einem Fernseher fast nie passen: 4096 ist Kinoformat
# (21:9-Beschnitt), kein 16:9-Panel. Wird hinten angestellt, nicht versteckt -
# wenn der Bildschirm sie wirklich braucht, bleibt sie waehlbar.
UNUEBLICH = ('4096x2160',)


def _drm_name(ausgang):
    """X-Ausgangsname -> Kernel-/DRM-Name (HDMI-1 -> HDMI-A-1).

    xrandr nennt die Ausgaenge HDMI-1/HDMI-2, der Kernel legt sie als
    HDMI-A-1/HDMI-A-2 an. Die /sys/class/drm/card*-<name>/modes-Dateien tragen
    den Kernel-Namen - ohne diese Umrechnung findet man dort nichts.
    """
    nummer = ausgang.rsplit('-', 1)[-1]
    return 'HDMI-A-%s' % nummer


def _modi(zeilen, index):
    """Modi aus dem Block eines Ausgangs, groesster zuerst."""
    modi = []
    for zeile in zeilen[index + 1:]:
        if zeile and not zeile.startswith(' '):
            break
        treffer = re.match(r'\s+(\d+x\d+)', zeile)
        if treffer and treffer.group(1) not in modi:
            modi.append(treffer.group(1))

    def groesse(modus):
        breite, hoehe = modus.split('x')
        return int(breite) * int(hoehe)

    # Unuebliche Formate nach hinten, sonst absteigend nach Flaeche.
    modi.sort(key=lambda m: (m in UNUEBLICH, -groesse(m)))
    return modi


def _edid_modi(ausgang):
    """Nur die Aufloesungen, die der Bildschirm selbst meldet.

    xrandr listet neben den EDID-Modi des Bildschirms auch eine lange
    Standard-Liste (1280x720, 1024x768, ...), die der X-Server immer anbietet.
    Ein Fernseher kann davon nur einen Bruchteil anzeigen - eine dort gewaehlte
    Aufloesung quittiert er mit 'kein Signal'. Die EDID-Modi stehen im Kernel
    unter /sys/class/drm/card*-<AUSGANG>/modes und sind genau die, die das
    Geraet wirklich unterstuetzt.

    Der ERSTE Eintrag ist der, den der Bildschirm als bevorzugten (preferred)
    Modus meldet - also die native Aufloesung.
    """
    import glob
    modi = []
    for pfad in glob.glob('/sys/class/drm/card*-%s/modes' % _drm_name(ausgang)):
        try:
            with open(pfad, encoding='utf-8') as datei:
                for zeile in datei:
                    wert = zeile.strip()
                    if wert and wert not in modi:
                        modi.append(wert)
        except OSError:
            continue
    return _sortiere_nativ(modi)


def _sortiere_nativ(modi):
    """Sortiert so, dass der natuerliche native Modus vorn steht.

    Ein 4K-Fernseher meldet oft zuerst 4096x2160 (DCI-Kino) und erst danach
    3840x2160, obwohl sein Panel 16:9 ist. Auch ein 30-Hz-Eintrag kann vor dem
    60-Hz-Eintrag stehen. Deshalb: 16:9-Modi ohne Kinoformat zuerst, nach
    Flaeche absteigend. Innerhalb gleicher Flaeche bleibt die EDID-Reihenfolge.
    """

    def schluessel(modus):
        try:
            breite, hoehe = modus.split('x')
            breite, hoehe = int(breite), int(hoehe)
        except (ValueError, AttributeError):
            return (1, 0)
        h = hoehe if hoehe > 0 else 1
        ist_16_zu_9 = abs(breite / h - 16 / 9) < 0.05
        kinoformat = modus in UNUEBLICH or br_gt(breite, h)
        if kinoformat:
            gruppe = 2
        elif ist_16_zu_9:
            gruppe = 0
        else:
            gruppe = 1
        return (gruppe, -(breite * hoehe))
    return sorted(modi, key=schluessel)


def br_gt(breite, hoehe):
    """True, wenn das Seitenverhaeltnis breiter als 16:9 ist (Kino)."""
    return breite / hoehe > 1.79


def _xrandr(*args, timeout=15):
    """xrandr mit DISPLAY, weil die App als Dienst ohne Sitzung laeuft."""
    umgebung = dict(os.environ)
    umgebung.setdefault('DISPLAY', ':0')
    umgebung.setdefault('XAUTHORITY',
                        '/home/%s/.Xauthority' % os.environ.get('LHTPI_USER', 'pi'))
    try:
        return subprocess.run(['xrandr'] + list(args), capture_output=True,
                              text=True, timeout=timeout, env=umgebung)
    except (OSError, subprocess.SubprocessError) as fehler:
        return None if fehler else None


def _modi(zeilen, index):
    """Modi aus dem Block eines Ausgangs, groesster zuerst."""
    modi = []
    for zeile in zeilen[index + 1:]:
        if zeile and not zeile.startswith(' '):
            break
        treffer = re.match(r'\s+(\d+x\d+)', zeile)
        if treffer and treffer.group(1) not in modi:
            modi.append(treffer.group(1))

    def groesse(modus):
        breite, hoehe = modus.split('x')
        return int(breite) * int(hoehe)

    # Unuebliche Formate nach hinten, sonst absteigend nach Flaeche.
    modi.sort(key=lambda m: (m in UNUEBLICH, -groesse(m)))
    return modi


def _edid_modi(ausgang):
    """Nur die Aufloesungen, die der Bildschirm selbst meldet.

    xrandr listet neben den EDID-Modi des Bildschirms auch eine lange
    Standard-Liste (1280x720, 1024x768, ...), die der X-Server immer anbietet.
    Ein Fernseher kann davon nur einen Bruchteil anzeigen - eine dort gewaehlte
    Aufloesung quittiert er mit 'kein Signal'. Die EDID-Modi stehen im Kernel
    unter /sys/class/drm/card*-<AUSGANG>/modes und sind genau die, die das
    Geraet wirklich unterstuetzt.
    """
    import glob
    modi = []
    for pfad in glob.glob('/sys/class/drm/card*-%s/modes' % ausgang):
        try:
            with open(pfad, encoding='utf-8') as datei:
                for zeile in datei:
                    wert = zeile.strip()
                    if wert and wert not in modi:
                        modi.append(wert)
        except OSError:
            continue

    def groesse(modus):
        breite, hoehe = modus.split('x')
        return int(breite) * int(hoehe)

    modi.sort(key=lambda m: (m in UNUEBLICH, -groesse(m)))
    return modi


def bildschirme():
    """Was haengt dran, worauf laeuft es, was waere moeglich?

    Liefert eine Liste je Ausgang. Ist xrandr nicht erreichbar, steht in
    jedem Eintrag ``fehler`` - die Seite zeigt dann einen Hinweis statt
    einer leeren Tabelle.
    """
    lauf = _xrandr('--query')
    if lauf is None or lauf.returncode != 0:
        return [{'ausgang': a, 'angeschlossen': False, 'zustand': 'unbekannt',
                 'fehler': 'Der X-Server antwortet nicht.'} for a in AUSGAENGE]

    zeilen = lauf.stdout.splitlines()
    ergebnis = []
    for ausgang in AUSGAENGE:
        index = next((i for i, z in enumerate(zeilen)
                      if z.startswith(ausgang + ' ')), None)
        if index is None:
            ergebnis.append({'ausgang': ausgang, 'angeschlossen': False,
                             'zustand': 'nicht vorhanden', 'modi': [],
                             'aktuell': None, 'nativ': None})
            continue

        zeile = zeilen[index]
        angeschlossen = ' connected' in zeile
        treffer = re.search(r'(\d+x\d+)\+(\d+)\+(\d+)', zeile)
        aktuell = treffer.group(1) if treffer else None
        # Nur EDID-Modi (was der Bildschirm wirklich kann), mit Fallback auf die
        # xrandr-Liste, falls der Kernel sie nicht freigibt (z. B. Treiber ohne
        # /sys/class/drm-Angaben). Die Standard-Modi von xrandr gehoeren NICHT
        # in die Auswahl - ein Fernseher zeigt sie oft gar nicht an.
        modi = (_edid_modi(ausgang) if angeschlossen else [])
        if not modi and angeschlossen:
            modi = _modi(zeilen, index)

        # Ist der laufende Modus der, den der Bildschirm als seinen eigenen
        # meldet? Nicht jeder angebotene Modus zaehlt: 720x400 steht in der
        # Liste, ist aber VGA-Text - damit ist das Bild hochgerechnet.
        # Der native Modus ist der erste Eintrag der EDID-Liste (nachdem
        # Kinoformate nach hinten sortiert wurden) - das ist der, den der
        # Bildschirm als seinen bevorzugten meldet.
        nativ = modi[0] if modi else None
        passt = bool(aktuell) and aktuell == nativ

        ergebnis.append({
            'ausgang': ausgang,
            'angeschlossen': angeschlossen,
            'zustand': 'angeschlossen' if angeschlossen else 'kein Signal',
            'aktuell': aktuell,
            'nativ': nativ,
            'modi': modi,
            'unueblich': aktuell in UNUEBLICH if aktuell else False,
            'passt': passt,
            'position': (treffer.group(2), treffer.group(3)) if treffer else None,
        })
    return ergebnis


def setze_aufloesung(ausgang, modus):
    """Setzt die Aufloesung sofort. Liefert (ok, meldung)."""
    if ausgang not in AUSGAENGE:
        return False, 'Unbekannter Ausgang.'
    if not re.match(r'^\d+x\d+$', str(modus or '')):
        return False, 'Ungueltige Aufloesung.'

    # Erst pruefen, ob der Bildschirm sie ueberhaupt anbietet. Ein erzwungener
    # Modus, den er nicht kennt, ergibt kein Bild - und dann ist die Anzeige
    # schwarz, ohne dass jemand weiss warum.
    vorhanden = {b['ausgang']: b for b in bildschirme()}
    daten = vorhanden.get(ausgang) or {}
    if not daten.get('angeschlossen'):
        return False, '%s meldet kein Signal.' % ausgang
    if modus not in (daten.get('modi') or []):
        return False, ('%s bietet %s nicht an. Moeglich: %s'
                       % (ausgang, modus, ', '.join((daten.get('modi') or [])[:4])))

    lauf = _xrandr('--output', ausgang, '--mode', modus)
    if lauf is None:
        return False, 'xrandr liess sich nicht starten.'
    # xrandr meldet Fehler oft auf stdout und mit Rueckgabewert 0 - beides
    # pruefen, sonst gilt ein abgelehnter Modus als gesetzt.
    meldung = ' '.join((lauf.stderr or '').split() + (lauf.stdout or '').split()).strip()
    if lauf.returncode != 0 or meldung:
        return False, meldung or 'Der Bildschirm hat die Aufloesung abgelehnt.'

    # Zweiter Ausgang mitsetzen: Steht er auf derselben Flaeche, ueberlappt
    # sonst das Bild, sobald einer die Groesse wechselt.
    andere = [a for a in AUSGAENGE if a != ausgang]
    for a in andere:
        info = vorhanden.get(a) or {}
        if info.get('angeschlossen') and info.get('aktuell'):
            _xrandr('--output', a, '--auto')
            break
    return True, '%s laeuft jetzt auf %s.' % (ausgang, modus)


def dauerhaft_setzen(ausgang, modus):
    """Traegt die Aufloesung in die Kernel-Zeile ein.

    Warum das noetig ist: Beim Hochfahren, bevor X startet, gilt nur, was in
    der Kernel-Zeile steht. Ohne Eintrag faellt das Geraet dort auf eine kleine
    Aufloesung zurueck - und das Bild bleibt klein, bis jemand von Hand
    nachhilft.

    Liefert (ok, meldung).
    """
    if ausgang not in AUSGAENGE:
        return False, 'Unbekannter Ausgang.'
    if not re.match(r'^\d+x\d+$', str(modus or '')):
        return False, 'Ungueltige Aufloesung.'

    ziel = None
    for kandidat in ('/boot/firmware/cmdline.txt', '/boot/cmdline.txt'):
        if os.path.isfile(kandidat):
            ziel = kandidat
            break
    if ziel is None:
        return False, 'cmdline.txt nicht gefunden.'

    # Der Kernel heisst die Ausgaenge HDMI-A-1 und HDMI-A-2.
    nummer = ausgang.rsplit('-', 1)[-1]
    eintrag = 'video=HDMI-A-%s:%s@60D' % (nummer, modus)

    try:
        with open(ziel, encoding='utf-8') as datei:
            inhalt = datei.read()
    except OSError as fehler:
        return False, 'Nicht lesbar: %s' % fehler

    woerter = [w for w in inhalt.split()
               if not w.startswith('video=HDMI-A-%s:' % nummer)]
    woerter.append(eintrag)
    neu = ' '.join(woerter) + '\n'

    # Schreiben braucht root. Die App laeuft als pi - deshalb ein Helfer mit
    # Freigabe, kein direktes Schreiben.
    helfer = '/usr/local/bin/lhtpi-cmdline.sh'
    if not os.path.exists(helfer):
        return False, ('Kein Helfer fuer die Kernel-Zeile (%s). Bitte '
                       'scripts/kiosk-neu.sh ausfuehren.' % helfer)
    try:
        lauf = subprocess.run(['sudo', '-n', helfer, ausgang, modus],
                              capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as fehler:
        return False, 'Helfer nicht ausfuehrbar: %s' % fehler

    if lauf.returncode != 0:
        return False, (lauf.stderr or lauf.stdout or 'Fehlgeschlagen').strip()

    # Nur eine Ausnahme: bei einem Rechner ohne /boot-Schreibrecht bleibt der
    # Eintrag aus. Das faellt hier auf, nicht erst beim naechsten Neustart.
    try:
        with open(ziel, encoding='utf-8') as datei:
            if eintrag not in datei.read():
                return False, 'Eintrag steht nicht in %s.' % ziel
    except OSError:
        pass
    return True, '%s bleibt auch nach einem Neustart auf %s.' % (ausgang, modus)
