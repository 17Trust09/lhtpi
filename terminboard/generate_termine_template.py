"""Erzeugt die Excel-Vorlage ``USB/termine.xlsx`` für das Terminboard.

Die Vorlage ist für Nicht-Techniker gedacht: verständliche deutsche
Spaltenüberschriften, Dropdown für die Art, Datumsfelder und Beispielzeilen.

Spalten: ``Art | Prüfstand | Von | Bis | Info``

Ausführen (aus dem Repo-Root)::

    python terminboard/generate_termine_template.py

benötigt ``openpyxl``.
"""
import os
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(REPO_ROOT, "USB", "termine.xlsx")

HEADERS = ["Art", "Prüfstand", "Von", "Bis", "Info"]

# Werte für das Dropdown in Spalte A (ohne Umlaute, damit sie 1:1 in die
# CSV-Semantik kalibrierung/audit/wartung/info gemappt werden können).
ART_TYPES = ["Kalibrierung", "Audit", "Wartung", "Info"]

# Beispielzeilen (realistisch, dürfen überschrieben/gelöscht werden).
EXAMPLE_ROWS = [
    ["Kalibrierung", "P3", date(2026, 8, 25), date(2026, 8, 30), "Druckprüfstand – jährliche Kalibrierung"],
    ["Kalibrierung", "P7", date(2026, 9, 14), date(2026, 9, 16), "Leckprüfstand"],
    ["Audit", "QS", date(2026, 9, 14), "", "ISO-Audit Qualitätssicherung"],
    ["Wartung", "Druckluft", date(2026, 9, 1), date(2026, 9, 2), "Wartung Druckluftanlage"],
    ["Info", "Alle", date(2026, 9, 1), "", "Neue Schichtregelung"],
]


def _build_legend():
    """Text für das Anleitung-Blatt."""
    return [
        ["Terminboard – Anleitung"],
        [""],
        ["So trägst du einen Termin ein:"],
        ["1. Gehe auf das Blatt „Termine“."],
        ["2. Trage pro Termin eine Zeile ein (Spalten A–E)."],
        ["3. Wähle die „Art“ über das Dropdown (Spalte A)."],
        ["4. „Prüfstand“, „Von“ und „Info“ sind Pflicht – „Bis“ darf leer bleiben."],
        ["5. Fertig – den Stick einfach wieder in den Pi stecken."],
        [""],
        ["Spalten:"],
        ["A  Art       – Kalibrierung / Audit / Wartung / Info (Dropdown)"],
        ["B  Prüfstand – z. B. P3 (Pflicht)"],
        ["C  Von       – Startdatum TT.MM.JJJJ (Pflicht)"],
        ["D  Bis       – Enddatum TT.MM.JJJJ (optional)"],
        ["E  Info      – Beschreibung / freier Einzeiler (Pflicht)"],
        [""],
        ["Hinweis: Die ersten Beispielzeilen kannst du einfach überschreiben oder löschen."],
        ["Abgelaufene Termine werden automatisch von der Anzeige entfernt."],
    ]


def main():
    wb = Workbook()

    # ── Blatt 1: Termine ──────────────────────────────────────────────
    ws = wb.active
    ws.title = "Termine"

    header_font = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="1B4B8F", end_color="1B4B8F", fill_type="solid")
    body_font = Font(name="Arial", size=11)

    # Kopfzeile
    for col, title in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Beispielzeilen
    for r, row in enumerate(EXAMPLE_ROWS, start=2):
        for c, value in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            cell.font = body_font
            if c in (3, 4) and isinstance(value, date):
                cell.number_format = "DD.MM.YYYY"

    # Datumsformat für die Datumsspalten C/D auch für leere Zellen vorbereiten
    for r in range(2, 200):
        ws.cell(row=r, column=3).number_format = "DD.MM.YYYY"
        ws.cell(row=r, column=4).number_format = "DD.MM.YYYY"
        ws.cell(row=r, column=3).font = body_font
        ws.cell(row=r, column=4).font = body_font
        for c in (1, 2, 5):
            ws.cell(row=r, column=c).font = body_font

    # Spaltenbreiten
    widths = {"A": 16, "B": 16, "C": 14, "D": 14, "E": 40}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    # Dropdown für Spalte A (Art)
    dv = DataValidation(
        type="list",
        formula1='"' + ",".join(ART_TYPES) + '"',
        allow_blank=True,
        showDropDown=False,
    )
    dv.error = "Bitte einen Wert aus der Liste wählen."
    dv.errorTitle = "Ungültige Art"
    ws.add_data_validation(dv)
    dv.add("A2:A500")

    # Kopfzeile einfrieren
    ws.freeze_panes = "A2"

    # ── Blatt 2: Anleitung ────────────────────────────────────────────
    ws2 = wb.create_sheet("Anleitung")
    legend = _build_legend()
    title_font = Font(name="Arial", bold=True, size=13, color="1B4B8F")
    normal_font = Font(name="Arial", size=11)
    for r, row in enumerate(legend, start=1):
        cell = ws2.cell(row=r, column=1, value=row[0])
        cell.font = title_font if r == 1 else normal_font
    ws2.column_dimensions["A"].width = 80

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    wb.save(OUTPUT)
    print(f"Vorlage geschrieben: {OUTPUT}")


if __name__ == "__main__":
    main()
