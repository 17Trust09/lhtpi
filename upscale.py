"""LHTPi – Automatisches Hochskalieren von USB-/Upload-Bildern.

Ziel (Nutzerwunsch): Bilder, die aus einer PowerPoint exportiert wurden (oft nur
96 dpi ~ 1280x720) oder klein sind, sollen auf einem 4K-Bildschirm scharf und
flaechendenkend angezeigt werden, OHNE dass der Nutzer etwas hochskalieren oder
hochladen muss. Jeder soll es koennen, rein lokal, ohne Dateien zu uns zu schicken.

Ehrliche Grenzen
----------------
* Hochskalieren kann fehlende Bildinformation NICHT wirklich zurueckerfinden.
  Ein 800x600-Bild bleibt inhaltlich grob, egal was wir tun.
* Wir verwenden deshalb kein simples Nachbar-/Bilinear-Strecken, sondern
  Lanczos (ueber Pillow). Das erzeugt bei Text/Raendern deutlich sauberere
  Kanten als das grobe Browser-Upscaling. Es ist der beste verlustarme Weg,
  der ohne externe Dienste/Netzzugang auskommt.

Vorgehen
--------
* Beim Einlesen eines Bildes wird einmalig eine hochskalierte Version auf die
  Zielgroesse (Standard: 3840x2160 = 4K-Obergrenze) gebracht und in einem
  Cache-Ordner abgelegt. Die Originaldatei bleibt unberuehrt.
* Ausgeliefert wird die gecachte, scharfe Variante. So wird nur einmal gerechnet,
  nicht bei jeder Anzeige.
* Die Zielgroesse begrenzt nach oben (ein Bild wird nie ueber die Zielgroesse
  hinaus hochskaliert -> keine sinnlosen Riesen-Dateien). Kleinere Bilder werden
  nur hoch-, nie runterskaliert (Runterskalieren waere unnoetig, der Fernseher
  zeigt das Original sonst ohnehin hoch).
* ``Lanczos`` = hochwertiger Resampling-Filter; ``LANCZOS_TARGET_W``/``_H`` legen
  die Zielaufloesung fest.
"""

from __future__ import annotations

import hashlib
import os

from PIL import Image, ImageOps

# Zielgroesse: 4K (16:9). Wir skalieren nur HOCH (nie ueber diese Grenze hinaus,
# nie ein groesseres Bild runter). Bilder werden seitenverhaeltnis-treu auf die
# Zielbox skaliert.
LANCZOS_TARGET_W = 3840
LANCZOS_TARGET_H = 2160

# Resampling-Filter. LANCZOS ist fuer Text/Raender am saubersten (vs. NEAREST/
# BILINEAR/BICUBIC). Der Resampling.FILTER_NAME-Zugriff ist alt; wir nutzen den
# direkten Konstanten-Zugriff, der in Pillow 10+ weitergeht.
LANCZOS_FILTER = Image.Resampling.LANCZOS

# Erlaubte Bild-Endungen fuer den Cache (Videos werden NICHT hochskaliert).
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif'}


def _cache_dir(base_dir: str) -> str:
    """Cache-Unterordner fuer hochskalierte Bilder."""
    return os.path.join(base_dir, '.upscale-cache')


def _cache_key(src_abs_path: str) -> str:
    """Eindeutiger Cache-Name auf Basis von Pfad + Groesse + Zielaufloesung.

    Ein Hash aus Absolutpfad und Dateigroesse verhindert Kollisionen und laesst
    den Cache unguelig werden, wenn die Quelle sich aendert (gleicher Name,
    anderer Inhalt). Die Zielaufloesung fliegt ein, damit bei spaeteren Zielen
    keine veraltete Groesse serviert wird.
    """
    st = os.stat(src_abs_path)
    raw = f"{src_abs_path}|{st.st_size}|{LANCZOS_TARGET_W}x{LANCZOS_TARGET_H}".encode('utf-8')
    return hashlib.sha256(raw).hexdigest() + '.png'


def _target_size(src_w: int, src_h: int) -> tuple[int, int]:
    """Zielgroesse: hoechstens LANCZOS_TARGET_WxH, Seitenverhaeltnis bleibt.

    Liefert (None, None), wenn das Bild bereits breiter ODER hoeher ist als die
    Zielgroesse (dann ist kein Hochskalieren noetig; wir lassen das Original).
    """
    if src_w >= LANCZOS_TARGET_W or src_h >= LANCZOS_TARGET_H:
        return (None, None)

    scale = min(LANCZOS_TARGET_W / src_w, LANCZOS_TARGET_H / src_h)
    # Nur HOCHskalieren; ein Wert <= 1.0 heisst, das Bild passt schon,
    # wir koennten es ohnehin nicht sinnvoll vergroessern.
    if scale <= 1.0:
        return (None, None)
    return (int(src_w * scale), int(src_h * scale))


def upscale_image(src_abs_path: str, cache_base: str) -> str | None:
    """Hochskalierte (oder unveraenderte) Ausliefer-Version eines Bildes liefern.

    Gibt den Pfad zu einer gueltigen Bilddatei zurueck:
    * existiert bereits ein passender Cache-Eintrag -> dieser Pfad,
    * Bild ist bereits in/ueber Zielgroesse -> der Originalpfad (kein Copy),
    * sonst -> einmalig hochskaliert in den Cache geschrieben und dessen Pfad.

    Bei jedem Fehler (defektes Bild, kein Zugriff) wird ``None`` geliefert; der
    Aufrufer faellt dann auf das Original zurueck.
    """
    try:
        im = Image.open(src_abs_path)
        im.load()
    except (OSError, ValueError):
        return None

    # EXIF-Orientierung anwenden, damit Handy-Fotos nicht verdreht landen.
    im = ImageOps.exif_transpose(im)

    # Nicht-RGB (z. B. P oder RGBA mit Transparenz) sicher konvertieren.
    if im.mode not in ('RGB', 'L'):
        im = im.convert('RGB')

    width, height = im.size
    tw, th = _target_size(width, height)
    if tw is None or th is None:
        # Schon gross genug -> Original nutzen, nichts tun.
        return src_abs_path

    im = im.resize((tw, th), LANCZOS_FILTER)

    os.makedirs(_cache_dir(cache_base), exist_ok=True)
    out_path = os.path.join(_cache_dir(cache_base), _cache_key(src_abs_path))

    # Nur schreiben, wenn noch nicht vorhanden (idempotent; parallel-fest via
    # tmp + os.replace).
    if not os.path.exists(out_path):
        tmp_path = out_path + '.tmp'
        im.save(tmp_path, format='PNG')
        os.replace(tmp_path, out_path)

    return out_path


def is_image(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in IMAGE_EXTS
