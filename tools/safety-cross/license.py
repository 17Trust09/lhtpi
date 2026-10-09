"""Hardware-Lizenz: bindet die Installation an den Raspberry Pi.

So funktioniert's:
  - `license.key` = HMAC-SHA256(seriennummer, secret)
  - Die Seriennummer (/proc/cpuinfo) ist hardware-gebrannt und pro Pi eindeutig.
  - Beim App-Start prüft die App: passt der hinterlegte Key zur Seriennummer DIESES Pi?

Fälle:
  - Gleicher Pi (Backup/Klon auf denselben Pi)  -> läuft
  - Anderer Pi (SD-Karte/Image kopiert)         -> gesperrt (Lock-Screen)
  - Kein Pi (Dev/VM, kein /proc/cpuinfo)        -> erlaubt

Secret-Handling (install.sh, PRIORITÄT):
  1. Umgebungsvariable SAFETY_SECRET
  2. Datei /boot/safety-secret.txt  (bzw. /boot/firmware/safety-secret.txt)
  3. sonst: zufälliges Secret -> Basis-Schutz (Secret liegt dann auf dem Pi)

WICHTIG (ehrliche Grenze): Eine Offline-Lizenz ist kein unknackbarer Schutz,
sondern ein Deterrent. Wer Secret + Quellcode hat, kann Keys fälschen. Das
Secret NIEMALS ins Git-Repo legen. Für echten Schutz: Secret nur bei dir
aufbewahren und install.sh über SAFETY_SECRET bzw. die Datei bereitstellen.
"""
import hashlib
import hmac
import os

APP_DIR = "/opt/safety-cross"


def _license_path():
    return os.environ.get("SAFETY_LICENSE", os.path.join(APP_DIR, "license.key"))


def _secret_path():
    return os.environ.get("SAFETY_SECRET_FILE", os.path.join(APP_DIR, ".secret"))


def get_serial():
    """Seriennummer des Pi (None, wenn kein Pi / VM)."""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("serial"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def compute_key(serial, secret):
    return hmac.new(secret.encode(), serial.encode(), hashlib.sha256).hexdigest()


def read_secret():
    """Secret aus Datei oder Umgebungsvariable (None, wenn keins)."""
    try:
        v = open(_secret_path()).read().strip()
        if v:
            return v
    except OSError:
        pass
    return os.environ.get("SAFETY_SECRET", "").strip() or None


def is_valid():
    """True, wenn die Lizenz zur Hardware passt (oder Dev-Modus)."""
    serial = get_serial()
    if not serial:
        return True  # Kein Pi (Dev/VM) -> nicht sperren
    if not os.path.exists(_license_path()):
        return False
    secret = read_secret()
    if not secret:
        return False
    try:
        with open(_license_path()) as f:
            stored = f.read().strip()
    except OSError:
        return False
    if not stored:
        return False
    return hmac.compare_digest(stored, compute_key(serial, secret))


def make_key(secret):
    """Erzeugt license.key aus Seriennummer + Secret. Gibt den Key zurück (None ohne Pi)."""
    serial = get_serial()
    if not serial:
        return None
    key = compute_key(serial, secret)
    with open(_license_path(), "w") as f:
        f.write(key + "\n")
    os.chmod(_license_path(), 0o600)
    return key


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--make-key":
        secret = read_secret()
        if not secret:
            sys.stderr.write("Kein Secret gefunden (SAFETY_SECRET / .secret).\n")
            sys.exit(1)
        key = make_key(secret)
        if not key:
            sys.stderr.write("Kein Pi erkannt (keine Seriennummer in /proc/cpuinfo).\n")
            sys.exit(1)
        print(key)
    else:
        print("valid" if is_valid() else "invalid")
