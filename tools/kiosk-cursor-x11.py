#!/usr/bin/env python3
"""Blendet den Mauszeiger am X-Server aus, sobald er nicht bewegt wird.

Warum nicht per CSS? Chromium zeichnet den Mauszeiger erst beim naechsten
Mausereignis neu. Setzt die Seite das Ausblenden per CSS, waehrend die Maus
still steht, bleibt der Zeiger sichtbar, bis jemand klickt - genau der Fehler,
den Tim am Geraet gesehen hat.

Dieser Helfer arbeitet direkt am X-Server (XFixes) und blendet den Zeiger nach
RUHE Sekunden Stillstand aus. Bei der naechsten Bewegung wird er sofort wieder
gezeigt. Er laeuft in der X-Sitzung des Kiosk-Geraets (siehe install.sh) und
braucht nur python-xlib - kein root, keine Systempakete.

Der Zeiger wird auf dem Fenster versteckt, ueber dem er gerade steht (bei der
Kiosk-Anzeige ist das das Chromium-Fenster). Waehrend der Ruhe wird das
Verstecken jede Sekunde erneuert, damit ein Fenster, das beim Ueberfahren
wieder einen Zeiger setzt, ihn nicht zurueckbringt.

Aufruf:  kiosk-cursor-x11.py [--ruhe 3] [--display :0] [--test]
"""
from __future__ import annotations

import argparse
import sys
import time

TAKT = 0.25  # Sekunden zwischen zwei Positionsabfragen


def verbinde(display_name: str | None):
    """Verbindet zum X-Server und liefert Fenster + zwei kleine Helfer."""
    from Xlib import display
    from Xlib.ext import xfixes

    d = display.Display(display_name)
    root = d.screen().root
    opcode = d.get_extension_major('XFIXES')

    def verstecken(fenster):
        xfixes.HideCursor(display=d, opcode=opcode, window=fenster)
        d.sync()

    def zeigen(fenster):
        xfixes.ShowCursor(display=d, opcode=opcode, window=fenster)
        d.sync()

    return d, root, verstecken, zeigen


def testlauf(root, verstecken, zeigen) -> int:
    """Versteckt den Zeiger kurz und zeigt ihn wieder - reiner Selbsttest."""
    p = root.query_pointer()
    fenster = p.child or root
    verstecken(fenster)
    print("Zeiger versteckt auf Fenster %s" % hex(fenster.id))
    time.sleep(2)
    zeigen(fenster)
    print("Zeiger wieder sichtbar")
    return 0


def wache(root, verstecken, zeigen, ruhe: float) -> int:
    versteckt = None            # Fenster, auf dem der Zeiger versteckt ist
    letzte_pos = None
    letzte_bewegung = time.time()
    letztes_verstecken = 0.0

    while True:
        try:
            p = root.query_pointer()
            fenster = p.child or root
            pos = (p.root_x, p.root_y)

            if pos != letzte_pos:
                letzte_pos = pos
                letzte_bewegung = time.time()
                if versteckt is not None:
                    zeigen(versteckt)
                    versteckt = None
            elif time.time() - letzte_bewegung >= ruhe and \
                    time.time() - letztes_verstecken >= 1.0:
                verstecken(fenster)
                versteckt = fenster
                letztes_verstecken = time.time()
        except Exception as fehler:      # niemals still sterben
            print("Zeiger-Wache: %s" % fehler, file=sys.stderr, flush=True)
            versteckt = None
            time.sleep(2)
        time.sleep(TAKT)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ruhe', type=float, default=3.0,
                    help='Sekunden Stillstand bis der Zeiger verschwindet')
    ap.add_argument('--display', default=None, help='z. B. :0')
    ap.add_argument('--test', action='store_true',
                    help='Zeiger einmal kurz verstecken und wieder zeigen')
    a = ap.parse_args()

    try:
        _d, root, verstecken, zeigen = verbinde(a.display)
    except Exception as fehler:
        print("Kein Zugang zum X-Server: %s" % fehler, file=sys.stderr)
        return 1

    if a.test:
        return testlauf(root, verstecken, zeigen)
    return wache(root, verstecken, zeigen, a.ruhe)


if __name__ == '__main__':
    raise SystemExit(main())
