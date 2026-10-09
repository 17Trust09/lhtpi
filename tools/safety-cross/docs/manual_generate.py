#!/usr/bin/env python3
"""Erzeugt die druckbare Bedienungsanleitung (PDF) für das Safety Cross."""
from fpdf import FPDF

# Lufthansa-Farbwelt
NAVY = (5, 22, 77)
NAVY2 = (26, 58, 107)
YELLOW = (255, 226, 0)
GOLD = (240, 185, 11)
GREEN = (34, 139, 34)
AMBER = (240, 170, 20)
RED = (200, 40, 40)
GRAY = (120, 120, 120)
LIGHT = (243, 245, 250)
INK = (40, 40, 40)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_M = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

DOC = "/opt/data/projects/safety-cross/docs/Safety-Cross-Bedienungsanleitung.pdf"


class Manual(FPDF):
    def __init__(self):
        super().__init__("P", "mm", "A4")
        self.add_font("D", "", FONT)
        self.add_font("D", "B", FONT_B)
        self.add_font("DM", "", FONT_M)
        self.alias_nb_pages()
        self.set_auto_page_break(auto=True, margin=16)
        self.set_margins(16, 16, 16)
        self._cover = False

    def header(self):
        if self._cover:
            return
        self.set_font("D", "B", 8)
        self.set_text_color(*GRAY)
        self.cell(0, 6, "Safety Cross  ·  Bedienungsanleitung", align="R",
                  new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*NAVY)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(6)

    def footer(self):
        if self._cover:
            return
        self.set_y(-14)
        self.set_font("D", "", 8)
        self.set_text_color(*GRAY)
        self.cell(0, 8, f"Seite {self.page_no()} / {{nb}}", align="C")

    # ---- Helfer ----
    def section(self, title):
        self.set_fill_color(*NAVY)
        self.set_text_color(255, 255, 255)
        self.set_font("D", "B", 12)
        self.cell(0, 9, "   " + title, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*INK)
        self.ln(5)

    def body(self, text, size=9.5, color=INK):
        self.set_font("D", "", size)
        self.set_text_color(*color)
        self.multi_cell(0, 5.3, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(2.5)

    def bold_body(self, text, size=9.5):
        self.set_font("D", "B", size)
        self.set_text_color(*NAVY)
        self.multi_cell(0, 5.3, text, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*INK)
        self.ln(2)

    def bullet(self, text, size=9.5):
        self.set_font("D", "", size)
        self.set_text_color(*INK)
        self.multi_cell(0, 5.3, "   •  " + text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def step(self, n, text):
        x0 = self.l_margin
        self.set_x(x0)
        self.set_font("D", "B", 9.5)
        self.set_text_color(*NAVY)
        self.cell(11, 5.5, f"{n}.", new_x="RIGHT")
        self.set_font("D", "", 9.5)
        self.set_text_color(*INK)
        self.multi_cell(self.w - self.r_margin - x0 - 11, 5.5, text,
                        new_x="LMARGIN", new_y="NEXT")
        self.ln(1.5)

    def legend_item(self, label, rgb):
        self.set_font("D", "", 9.5)
        x = self.get_x()
        y = self.get_y()
        self.set_fill_color(*rgb)
        self.rect(x, y + 0.5, 4.5, 4.5, "F")
        self.set_x(x + 8)
        self.set_text_color(*INK)
        self.cell(0, 5.5, label, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def shot(self, path, caption, w=178):
        self.image(path, x=self.l_margin, w=w)
        self.ln(2)
        self.set_font("D", "", 8)
        self.set_text_color(*GRAY)
        self.multi_cell(0, 4.2, caption, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*INK)
        self.ln(4)

    def code(self, text):
        self.set_font("DM", "", 9)
        self.set_fill_color(*LIGHT)
        self.set_text_color(*NAVY2)
        self.set_x(self.l_margin + 4)
        self.multi_cell(self.w - self.r_margin - self.l_margin - 8, 5.3, text,
                        new_x="LMARGIN", new_y="NEXT", border=0, fill=True)
        self.set_text_color(*INK)
        self.ln(3)


def cover(pdf):
    pdf._cover = True
    pdf.add_page()
    # Navy-Vollfläche
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, pdf.w, pdf.h, "F")
    # Gelber Akzentstreifen
    pdf.set_fill_color(*YELLOW)
    pdf.rect(0, 0, pdf.w, 6, "F")
    pdf.rect(0, pdf.h - 6, pdf.w, 6, "F")

    # Kreuz
    cx, cy, s = pdf.w / 2, 88, 26
    pdf.set_fill_color(*RED)
    pdf.rect(cx - s / 6, cy - s / 2, s / 3, s, "F")
    pdf.rect(cx - s / 2, cy - s / 6, s, s / 3, "F")

    # Titel
    pdf.set_font("D", "B", 40)
    pdf.set_text_color(255, 255, 255)
    pdf.set_y(cy + s / 2 + 12)
    pdf.cell(0, 18, "Safety Cross", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("D", "B", 17)
    pdf.set_text_color(*YELLOW)
    pdf.cell(0, 10, "Bedienungsanleitung", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(pdf.h - 32)
    pdf.set_font("D", "", 11)
    pdf.set_text_color(200, 205, 225)
    pdf.cell(0, 7, "Arbeitssicherheit  ·  Lufthansa Technik", align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("D", "", 8.5)
    pdf.set_text_color(150, 158, 185)
    pdf.cell(0, 6, "Stand: August 2026  ·  v1.1", align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf._cover = False


def build():
    pdf = Manual()
    cover(pdf)

    # ---- Einführung ----
    pdf.add_page()
    pdf.section("Was ist das Safety Cross?")
    pdf.body(
        "Das Safety Cross ist eine digitale Anzeigetafel für Arbeitssicherheit. "
        "Sie zeigt auf einen Blick, wie viele Tage ein Bereich unfallfrei arbeitet, "
        "und dokumentiert Unfälle sowie Beinahe-Unfälle farblich im Monatsverlauf."
    )
    pdf.body(
        "Das System läuft autark auf einem Raspberry Pi – ganz ohne Internetverbindung. "
        "Eingaben erfolgen direkt am Gerät; es ist keine separate Fernbedienung nötig."
    )

    pdf.section("Die Farben auf einen Blick")
    pdf.legend_item("Grün  –  unfallfreier Tag", GREEN)
    pdf.legend_item("Gelb  –  Beinahe-Unfall (Near Miss)", AMBER)
    pdf.legend_item("Rot  –  Unfall", RED)
    pdf.legend_item("Weiß  –  zukünftiger Tag (noch nicht erreicht)", (180, 180, 180))
    pdf.ln(2)

    pdf.section("Die Anzeige")
    pdf.body(
        "Die Anzeige gliedert sich in drei Bereiche:"
    )
    pdf.bullet("Hauptbereich: das Monats-Kreuz mit den farbigen Tagen.")
    pdf.bullet("Linke Seite: Abteilung, Meister, die Ersthelfer und Notrufnummern.")
    pdf.bullet("Rechts oben: der große Zähler „Tage unfallfrei“.")
    pdf.ln(1)
    pdf.shot(
        "/opt/data/projects/safety-cross/docs/screenshots/anzeige.png",
        "Abb. 1: Die Safety-Cross-Anzeige – Kreuz mit Monatsverlauf, Zähler und Seitenleiste.",
        w=178,
    )

    # ---- Zähler + Admin-Zugriff ----
    pdf.add_page()
    pdf.section("Der Zähler „Tage unfallfrei“")
    pdf.body(
        "Der große Zähler oben rechts zeigt, wie viele Kalendertage in Folge ohne "
        "Unfall vergangen sind. Wird ein Unfall eingetragen, startet der Zähler "
        "automatisch wieder neu. Ein Beinahe-Unfall (gelb) setzt den Zähler nicht zurück."
    )

    pdf.section("Zugriff auf die Administration")
    pdf.body("Den Admin-Bereich erreicht man direkt am Bildschirm des Geräts:")
    pdf.step(1, "Oben im Menü den Tab „Admin“ wählen.")
    pdf.step(2, "Das Passwort eingeben und mit „Anmelden“ bestätigen.")
    pdf.body("Standard-Login (bitte beim ersten Mal ändern):", size=9.5)
    pdf.code("Benutzer:  admin")
    pdf.code("Passwort:  admin")
    pdf.ln(2)

    pdf.section("Die Verwaltung")
    pdf.body(
        "Nach der Anmeldung erscheint die Verwaltung mit sieben Karten: "
        "Abteilung & Meister, Ersthelfer, Notruf & wichtige Nummern, "
        "Tage unfallfrei / Zählung, Unfall melden, System und Passwort ändern."
    )
    pdf.shot(
        "/opt/data/projects/safety-cross/docs/screenshots/admin.png",
        "Abb. 2: Die Administration – alle Karten und Formulare auf einen Blick.",
        w=160,
    )

    # ---- Die Karten ----
    pdf.add_page()
    pdf.section("Abteilung & Meister ändern")
    pdf.bullet("Text in das jeweilige Feld schreiben.")
    pdf.bullet("Mit „Übernehmen“ speichern – die Anzeige aktualisiert sich sofort.")

    pdf.section("Ersthelfer verwalten")
    pdf.bullet("Name eintippen und mit „Hinzufügen“ übernehmen.")
    pdf.bullet("Entfernen: auf das rote ✕ am jeweiligen Eintrag klicken.")

    pdf.section("Notruf & wichtige Nummern verwalten")
    pdf.bullet("Bezeichnung (z. B. „Feuerwehr“) und Nummer bzw. Ort (z. B. „112“) eintragen.")
    pdf.bullet("Mit „Hinzufügen“ übernehmen – die Nummern erscheinen auf der Anzeige.")
    pdf.bullet("Entfernen: auf das rote ✕ am jeweiligen Eintrag klicken.")

    pdf.section("Tage unfallfrei / Zählung einstellen")
    pdf.body(
        "Es gibt zwei Wege, den Zähler zu starten. Beide führen zum selben Ergebnis:"
    )
    pdf.step(1, "Anzahl der Tage eintragen (z. B. 465) – das Startdatum wird automatisch berechnet.")
    pdf.step(2, "Alternativ direkt ein Startdatum wählen.")
    pdf.body(
        "Ohne Eintrag zählt das System automatisch ab Monatsanfang bzw. seit dem "
        "letzten Unfall."
    )

    pdf.section("Einen Unfall oder Beinahe-Unfall melden")
    pdf.step(1, "In der Karte „Unfall melden“ das Datum wählen.")
    pdf.step(2, "Typ wählen: „Unfall“ (rot) oder „Beinahe-Unfall“ (gelb).")
    pdf.step(3, "Betroffene Person eintragen (optional).")
    pdf.step(4, "Kurze Beschreibung ergänzen.")
    pdf.step(5, "„Eintragen“ klicken.")
    pdf.body(
        "Der Tag wird farblich markiert; bei einem Unfall startet der Zähler neu. "
        "Alle Einträge erscheinen in der ausklappbaren Liste „Letzte Einträge“."
    )

    # ---- Historie + System + Hardware ----
    pdf.add_page()
    pdf.section("Vergangene Monate ansehen")
    pdf.body(
        "Über die Pfeile ‹  › im Monatstitel der Anzeige blättert man durch "
        "vergangene Monate – so bleibt die Historie nachvollziehbar."
    )

    pdf.section("System: Neustart & Herunterfahren")
    pdf.body(
        "In der Karte „System“ lässt sich der Raspberry Pi sicher neu starten oder "
        "herunterfahren. Wichtig: Das Gerät immer über diese Schaltflächen ausschalten "
        "– niemals einfach den Strom ziehen. Das kann die SD-Karte beschädigen."
    )

    pdf.section("Passwort ändern")
    pdf.bullet("Neues Passwort eingeben (mindestens 4 Zeichen).")
    pdf.bullet("Mit „Speichern“ übernehmen.")
    pdf.body("Das Standard-Passwort „admin“ unbedingt durch ein eigenes ersetzen.")

    pdf.section("Hardware & Uhr")
    pdf.body(
        "Das System läuft auf einem Raspberry Pi (empfohlen: Modell 3 B). Die Zeit "
        "wird über eine Echtzeituhr (DS3231-RTC) gehalten, falls eine angeschlossen "
        "ist. Ohne RTC übernimmt „fake-hwclock“ die letzte bekannte Zeit über einen "
        "Neustart oder Stromausfall hinweg – die Genauigkeit reicht für die "
        "Tagesanzeige völlig aus."
    )

    pdf.section("Fehlerbehebung")
    pdf.bullet("Bildschirm schwarz: Strom kurz trennen und neu starten. Läuft der Pi, aber der Kiosk fehlt, hilft ein Neustart des Dienstes (per SSH):")
    pdf.code("sudo systemctl restart safety-cross-kiosk")
    pdf.bullet("Uhrzeit falsch: RTC prüfen bzw. die Zeit einmal manuell setzen.")
    pdf.bullet("Daten sichern: regelmäßig ein Image der SD-Karte ziehen (dd), damit Unfall-Historie und Zähler nicht verloren gehen.")

    pdf.output(DOC)
    print(f"OK: {DOC}")


if __name__ == "__main__":
    build()
