#!/usr/bin/env python3
"""Loest am X-Server einen Klick aus, damit Chromium den Mauszeiger neu zeichnet.

Warum? Die Kiosk-Seite blendet den Mauszeiger nach ein paar Sekunden Ruhe per
CSS aus. Chromium zeichnet den Zeiger aber erst beim naechsten Mausereignis neu:
steht die Maus still, bleibt der Zeiger sichtbar, bis jemand klickt. Genau das
war am Geraet zu sehen ("Maus bleibt. Ich muss klicken").

Deshalb loest die Anzeige nach der Ruhezeit selbst einen Klick aus - ueber
POST /zeiger/klick, das diesen Helfer startet. Der Klick geht an die Stelle, an
der der Zeiger steht (bei der Anzeige ist das die Kiosk-Seite; die eingebetteten
Tools nehmen keine Klicks an). Chromium zeichnet daraufhin neu - und weil zu
diesem Zeitpunkt "kein Zeiger" gesetzt ist, verschwindet der Zeiger von allein.

Aufruf:  kiosk-cursor-x11.py [--display :0]
"""
from __future__ import annotations

import argparse
import sys


def klick(display_name: str | None) -> int:
    from Xlib import X
    from Xlib import display
    from Xlib.ext import xtest

    d = display.Display(display_name)
    xtest.fake_input(d, X.ButtonPress, 1)
    xtest.fake_input(d, X.ButtonRelease, 1)
    d.sync()
    p = d.screen().root.query_pointer()
    print("Klick gesendet an %s" % ((p.root_x, p.root_y),))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--display', default=None, help='z. B. :0')
    a = ap.parse_args()
    try:
        return klick(a.display)
    except Exception as fehler:
        print("Kein Zugang zum X-Server: %s" % fehler, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
