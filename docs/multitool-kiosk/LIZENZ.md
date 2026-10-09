# Hardware-Lizenz (signiert)

Stand: 09.10.2026 · ersetzt die frühere HMAC-Lösung

## Warum umgestellt

Vorher steckte ein gemeinsamer Geheimschlüssel (`SECRET`) in `license_bundle.py`.
Weil das Repository öffentlich ist, konnte damit jeder für **jede** Seriennummer
eine gültige Lizenz erzeugen — der Kopierschutz war wertlos.

Jetzt gilt: **signiert, asymmetrisch.**

* Im Code steht nur der **öffentliche** Schlüssel (RSA-2048).
* Signiert wird mit dem **privaten** Schlüssel, der ausschließlich beim
  Hersteller liegt — nicht im Repo, nicht auf dem Gerät.
* Wer den Code liest, kann deshalb keine Lizenz erzeugen. Das öffentliche
  Repository ist damit unproblematisch.
* Verfahren: RSA-2048, SHA-256, PKCS#1 v1.5 — die Signatur lässt sich
  unabhängig mit `openssl` nachrechnen (Gegenprobe im Test).

## Was in der Lizenz steht

Signiert wird die Nutzlast **und** die volle Geräte-ID:

| Teil | Bedeutung |
|---|---|
| Geräte-ID | Seriennummer des Pi (`/proc/cpuinfo`), sonst `/etc/machine-id`, sonst MAC |
| Nutzlast (3 Zeichen) | welche Tools (Folien/Termine/Safety Cross) + Bildschirm-Anzahl (1/2) + Kurzkennung des Geräts |
| Signatur | 256 Byte → 512 Hex-Zeichen |

Dateiformat `license.key` (Kopfzeile + Blöcke, ~530 Byte):

```text
LHTPI-MXR-1A2B3C…   ← Nutzlast + Anfang der Signatur
4D5E6F…             ← Rest der Signatur, 64 Zeichen je Zeile
```

Eine Kopie der SD-Karte auf einem anderen Pi hat eine andere Seriennummer → die
Signatur passt nicht → die Lizenz ist ungültig.

## Der private Schlüssel

| Datei | Zweck |
|---|---|
| `/opt/data/lhtpi-lizenz/privat.pem` | PEM, für `openssl` (Gegenproben) |
| `/opt/data/lhtpi-lizenz/privat.json` | dasselbe als `n`/`e`/`d` für das Werkzeug |

Rechte `600`, **außerhalb** des Repos. Das Werkzeug findet ihn über
`LHTPI_SIGN_KEY_FILE` (Standard `~/.lhtpi/lizenz-privat.json`).

⚠️ **Backup ist Pflicht.** Geht der private Schlüssel verloren, lassen sich
**keine neuen Lizenzen** mehr erzeugen (bestehende Geräte laufen weiter, weil sie
nur den öffentlichen Schlüssel brauchen). Ein Schlüsselwechsel würde alle
bestehenden Lizenzen ungültig machen.

## Lizenz für ein Gerät erzeugen

```bash
# 1) auf dem Pi: Geräte-ID ablesen
python3 license_bundle.py --info

# 2) auf dem Hersteller-Rechner: Lizenz erzeugen
export LHTPI_SIGN_KEY_FILE=/opt/data/lhtpi-lizenz/privat.json
python3 license_bundle.py --make-key --tools=1,2,3 --screens=2 \
        --hwid=piserial:1000000012345678 > lizenz.key

# 3) auf das Gerät bringen (drei Wege)
#    a) lizenz.key auf die Boot-Partition der SD-Karte legen (geht vom PC aus)
#    b) vorab: sudo bash install.sh --license=/pfad/lizenz.key
#    c) nachträglich: Datei nach /etc/lhtpi/license.key kopieren
```

Weg (a) ist der bequemste: die Boot-Partition ist FAT-formatiert und lässt sich
an jedem PC beschreiben. Der Dienst `lhtpi-lizenz-import.service` holt die Datei
beim Start automatisch nach `/etc/lhtpi/license.key` — auch später, ohne
Neuinstallation.

## Prüfen

```bash
python3 license_bundle.py --check     # gültig / Grund
python3 license_bundle.py --info      # Geräte-ID, Lizenzdatei, Signierschlüssel
```

Auf der Anzeige-Seite zeigt `/lizenz` (und die Sperrseite) den Zustand; die
Geräte-ID steht dort zum Weitergeben. Der komplette Kopierschutz lässt sich
über HTTP durchprüfen:

```bash
LHTPI_SIGN_KEY_FILE=/opt/data/lhtpi-lizenz/privat.json bash tools/test-lizenz-live.sh
```

Der Lauf zeigt: ohne Lizenz 403 · eigenes Gerät 200 · fremdes Gerät 403 ·
veränderte Lizenz 403.

## Grenzen (ehrlich)

* Wer die **Prüfung im Code** entfernt (Software patcht), hebelt jede
  Lizenzprüfung aus. Dagegen hilft nur Verschleierung des Lizenzmoduls im
  ausgelieferten Image (Skill `python-source-protection`) — Verzögerung, keine
  Garantie.
* Ein Angreifer könnte den **öffentlichen** Schlüssel im Image durch seinen
  eigenen ersetzen und sich passende Lizenzen signieren. Dafür muss er aber das
  Image verändern — dann ist es ohnehin nicht mehr das Auslieferungs-Image.
* Der Lizenzschlüssel ist nicht mehr abtippbar (512 Hex-Zeichen) — er wird als
  Datei ausgeliefert, nicht diktiert.
* Auf dem Gerät sind `--make-key`/`--install` wirkungslos (kein privater
  Schlüssel) und beenden sich mit Fehlercode 3.

## Vorherige Lizenzen

Die alte 20-Zeichen-Form (`LHTPI-XXXX-XXXX-XXXX-XXXX`) wird **nicht** mehr
akzeptiert. Das ist unkritisch, solange kein Gerät mit alter Lizenz im Feld ist —
sonst vorher neue Lizenzen erzeugen.
