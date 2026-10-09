#!/bin/bash
# Alle Tests des Multitool-Kiosk-Bundles laufen lassen.
#
#   bash run-tests.sh
#
# Hinweis: Die Safety-Cross-Tests brauchen pytest im venv (siehe PLAN.md).
set -u
cd "$(dirname "$0")"

PY=./venv/bin/python
[ -x "$PY" ] || PY=python3

fehler=0
for t in test_kiosk_router.py test_install_bundle.py test_license_bundle.py \
         test_cursor_unified.py test_usb_source.py \
         tools/test-einbildschirm-live.py; do
    printf '%-26s ' "$t"
    if out=$("$PY" "$t" 2>&1); then
        echo "$(echo "$out" | grep -oE '(OK – [0-9]+ Prüfungen bestanden|ALLES GRÜN|[0-9]+ passed)' | tail -1)"
    else
        echo "FEHLER"
        echo "$out" | tail -8
        fehler=1
    fi
done

if [ -d tools/safety-cross/tests ]; then
    printf '%-26s ' 'tools/safety-cross'
    # Die Safety-Cross-Tests erwarten ihr eigenes Verzeichnis als Arbeitsordner
    if out=$(cd tools/safety-cross && "$OLDPWD/$PY" -m pytest tests -q 2>&1); then
        echo "$(echo "$out" | grep -oE '[0-9]+ passed' | tail -1)"
    else
        echo "FEHLER"
        echo "$out" | tail -6
        fehler=1
    fi
fi

exit "$fehler"
