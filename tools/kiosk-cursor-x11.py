#!/usr/bin/env python3
"""Erzwingt, dass Chromium einen ausgeblendeten Mauszeiger auch wirklich zeichnet.

Warum ueberhaupt? Die Kiosk-Seite blendet den Mauszeiger nach 3 s Ruhe per CSS
aus. Chromium zeichnet den Zeiger aber erst beim naechsten Mausereignis neu -
steht die Maus still, bleibt der Zeiger also sichtbar, bis jemand klickt. Genau
das hat Tim am Geraet gesehen.

Dieser Helfer bewegt den Zeiger im Ruhezustand alle RUHE Sekunden um genau
einen Bildpunkt hin und her (ueber XTest, also als echte Eingabe). Chromium
zeichnet daraufhin neu - und weil zu diesem Zeitpunkt "kein Zeiger" gesetzt
ist, verschwindet der Zeiger. Es entsteht kein Versatz, weil sich die
Bewegungen abwechseln.

Bewusst kein XFixes: die Fassung von python-xlib auf dem Geraet kann
hide_cursor/show_cursor nicht (ihr fehlen send_request und get_extension_major,
und die Erweiterung laest sich nicht erneut einrichten).
Bewusst kein unclutter: das blendet den Zeiger dauerhaft aus.

Aufruf:  kiosk-cursor-x11.py [--ruhe 4] [--display :0] [--test]
"""
from __future__ import annotations

import argparse
import sys
import time

TAKT = 0.3  # Sekunden zwischen zwei Positionsabfragen


def verbinde(display_name: str | None):
    from Xlib import display
    from Xlib.ext import xtest

    d = display.Display(display_name)
    return d, d.screen().root, xtest


def stups(d, xtest, richtung: int) -> None:
    """Eine relative Mini-Bewegung (1 Bildpunkt) als echte Eingabe senden."""
    from Xlib import X

    xtest.fake_input(d, X.MotionNotify, 1, x=richtung, y=0)
    d.sync()


def testlauf(d, root, xtest) -> int:
    """Drei Stupser senden und zeigen, dass der Zeiger sich minimal bewegt."""
    p = root.query_pointer()
    vorher = (p.root_x, p.root_y)
    for i in range(3):
        stups(d, xtest, 1 if i % 2 == 0 else -1)
        time.sleep(0.4)
    p = root.query_pointer()
    print("Stupser gesendet: vorher %s, jetzt %s" % (vorher, (p.root_x, p.root_y)))
    print("Zeiger steht wieder auf der Ausgangsposition" if
          vorher == (p.root_x, p.root_y) else "Hinweis: Position hat sich verschoben")
    return 0


def wache(d, root, xtest, ruhe: float) -> int:
    letzte_pos = None
    letzte_bewegung = time.time()
    richtung = 1

    while True:
        try:
            p = root.query_pointer()
            pos = (p.root_x, p.root_y)
            if pos != letzte_pos:
                letzte_pos = pos
                letzte_bewegung = time.time()
            elif time.time() - letzte_bewegung >= ruhe:
                stups(d, xtest, richtung)
                richtung = -richtung
                letzte_bewegung = time.time()
        except Exception as fehler:      # niemals still sterben
            print("Zeiger-Wache: %s" % fehler, file=sys.stderr, flush=True)
            time.sleep(2)
        time.sleep(TAKT)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ruhe', type=float, default=4.0,
                    help='Sekunden Stillstand bis der Zeiger neu gezeichnet wird '
                         '(muss groesser sein als die Ruhezeit der Kiosk-Seite, '
                         'Standard dort 3 s)')
    ap.add_argument('--display', default=None, help='z. B. :0')
    ap.add_argument('--test', action='store_true',
                    help='drei Stupser senden und die Position pruefen')
    a = ap.parse_args()

    try:
        d, root, xtest = verbinde(a.display)
    except Exception as fehler:
        print("Kein Zugang zum X-Server: %s" % fehler, file=sys.stderr)
        return 1

    if a.test:
        return testlauf(d, root, xtest)
    return wache(d, root, xtest, a.ruhe)


if __name__ == '__main__':
    raise SystemExit(main())
