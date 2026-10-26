#!/usr/bin/env bash
# Daten aus dem Programmverzeichnis nach /var/lib/lhtpi verschieben.
#
# Ziel: Ein Update kann den Programmstand austauschen, ohne Daten zu verlieren.
# Die Originale bleiben als Sicherung liegen – es wird kopiert, nicht verschoben.
#
# Aufruf:
#   sudo bash scripts/migrate_data_dir.sh          # normal
#   DRY_RUN=1 bash scripts/migrate_data_dir.sh     # nur zeigen, nichts tun
#
# Variablen (für Tests überschreibbar):
#   LHTPI_DATA_DIR  Zielverzeichnis   (Standard /var/lib/lhtpi)
#   PROJECT_DIR     Programmverzeichnis (Standard /home/pi/lhtpi)
#   SC_DIR          Safety-Cross-Verzeichnis (Standard /opt/safety-cross)
#   OWNER           Besitzer der Zieldateien (Standard pi:pi)

set -euo pipefail

DATA_DIR="${LHTPI_DATA_DIR:-/var/lib/lhtpi}"
PROJECT_DIR="${PROJECT_DIR:-/home/pi/lhtpi}"
SC_DIR="${SC_DIR:-/opt/safety-cross}"
OWNER="${OWNER:-pi:pi}"
DRY_RUN="${DRY_RUN:-0}"

kopiert=0
uebersprungen=0
fehlt=0

log()  { printf '%s\n' "$*"; }
ok()   { printf '  ok    %s\n' "$*"; }
skip() { printf '  skip  %s\n' "$*"; }
warn() { printf '  offen %s\n' "$*"; }

pruefe_sqlite() {
    local datei="$1"
    if ! command -v sqlite3 >/dev/null 2>&1; then
        return 0
    fi
    local ergebnis
    ergebnis="$(sqlite3 "$datei" 'PRAGMA integrity_check;' 2>/dev/null | head -1)"
    if [ "$ergebnis" = "ok" ]; then
        ok "Integrität geprüft: $(basename "$datei")"
        return 0
    fi
    warn "Integritätsprüfung fehlgeschlagen: $datei ($ergebnis)"
    return 1
}

uebernehme_datei() {
    local quelle="$1" ziel="$2" name="$3"

    if [ ! -f "$quelle" ]; then
        warn "$name – keine Quelldatei ($quelle)"
        fehlt=$((fehlt + 1))
        return 0
    fi

    if [ -f "$ziel" ]; then
        skip "$name – bereits vorhanden ($ziel)"
        uebersprungen=$((uebersprungen + 1))
        return 0
    fi

    if [ "$DRY_RUN" = "1" ]; then
        log "  plan  $name: $quelle -> $ziel"
        kopiert=$((kopiert + 1))
        return 0
    fi

    mkdir -p "$(dirname "$ziel")"
    cp -a "$quelle" "$ziel"
    pruefe_sqlite "$ziel" || return 1
    ok "$name -> $ziel"
    kopiert=$((kopiert + 1))
}

uebernehme_ordner() {
    local quelle="$1" ziel="$2" name="$3"

    if [ ! -d "$quelle" ]; then
        warn "$name – kein Quellordner ($quelle)"
        fehlt=$((fehlt + 1))
        return 0
    fi

    if [ -d "$ziel" ] && [ -n "$(ls -A "$ziel" 2>/dev/null)" ]; then
        skip "$name – bereits vorhanden ($ziel)"
        uebersprungen=$((uebersprungen + 1))
        return 0
    fi

    if [ "$DRY_RUN" = "1" ]; then
        log "  plan  $name: $quelle -> $ziel"
        kopiert=$((kopiert + 1))
        return 0
    fi

    mkdir -p "$ziel"
    cp -a "$quelle/." "$ziel/"
    ok "$name -> $ziel ($(du -sh "$ziel" 2>/dev/null | cut -f1))"
    kopiert=$((kopiert + 1))
}

log "Datenverzeichnis: $DATA_DIR"
log "Quelle:           $PROJECT_DIR"
[ "$DRY_RUN" = "1" ] && log "DRY RUN – es wird nichts geschrieben"
log ""

if [ "$DRY_RUN" != "1" ]; then
    mkdir -p "$DATA_DIR"
fi

log "Datenbanken:"
uebernehme_datei "$PROJECT_DIR/lhtpi.db" \
                 "$DATA_DIR/app/lhtpi.db" "Haupt-App"
uebernehme_datei "$PROJECT_DIR/terminboard/terminboard.db" \
                 "$DATA_DIR/terminboard/terminboard.db" "Terminboard"

if [ -f "$SC_DIR/safetycross.db" ]; then
    uebernehme_datei "$SC_DIR/safetycross.db" \
                     "$DATA_DIR/safety-cross/safetycross.db" "Safety-Cross"
else
    uebernehme_datei "$PROJECT_DIR/tools/safety-cross/safetycross.db" \
                     "$DATA_DIR/safety-cross/safetycross.db" "Safety-Cross"
fi

log ""
log "Uploads:"
uebernehme_ordner "$PROJECT_DIR/uploads" "$DATA_DIR/uploads" "Folien/Medien"

if [ "$DRY_RUN" != "1" ]; then
    log ""
    log "Rechte:"
    if [ "$(id -u)" = "0" ]; then
        if chown -R "$OWNER" "$DATA_DIR" 2>/dev/null; then
            ok "$DATA_DIR -> $OWNER"
        else
            warn "chown auf $OWNER fehlgeschlagen – bitte von Hand setzen"
        fi
        chmod 750 "$DATA_DIR"
    else
        warn "kein root – Rechte nicht gesetzt (chown $OWNER $DATA_DIR)"
    fi
fi

log ""
log "Ergebnis: $kopiert übernommen, $uebersprungen übersprungen, $fehlt nicht gefunden"

if [ "$fehlt" -gt 0 ]; then
    log "Hinweis: fehlende Quellen sind unkritisch, wenn der Dienst sie noch nicht angelegt hat."
fi

# ── Kontrolle: Sind die Einstellungen wirklich mitgekommen? ─────────────────
PRUEFER="$(dirname "$0")/pruefe_daten.py"
if [ -f "$PRUEFER" ]; then
    log ""
    log "Kontrolle der übernommenen Einstellungen:"
    if python3 "$PRUEFER"; then
        log "Kontrolle bestanden."
    else
        log "ACHTUNG: Die Kontrolle meldet fehlende Einstellungen."
        log "Bitte nichts weiter tun und die Sicherung prüfen."
        exit 1
    fi
fi

log ""
log "Nächster Schritt: Dienste neu starten (lhtpi, terminboard, safetycross)."
log "Danach greift automatisch ${DATA_DIR} – die alten Dateien bleiben als Sicherung."
