"""Safety Cross – Flask-App (offline Kiosk).

Anzeigetafel für Arbeitssicherheit: Monats-Kreuz (grün/gelb/rot), Ersthelfer,
Abteilung + Meister, „Tage unfallfrei"-Zähler, Unfall-Meldung, Historie.
"""
import calendar
import os
import subprocess
from datetime import date, timedelta

from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import auth
import db
import license

app = Flask(__name__)


def _session_secret():
    k = db.get_config("session_secret")
    if not k:
        k = os.urandom(24).hex()
        db.set_config("session_secret", k)
    return k


db.init_db()
auth.init_admin_password()
app.secret_key = _session_secret()

LICENSED = license.is_valid()

MONTHS_DE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]
WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
STATUS_LABEL = {"green": "Unfallfrei", "yellow": "Beinahe-Unfall", "red": "Unfall"}


# ---------- Lizenz-Gate ----------

@app.before_request
def license_gate():
    if not LICENSED and not request.path.startswith("/static"):
        return render_template("locked.html"), 403


# ---------- Helfer ----------

def cross_cells(year, month):
    """7x7-Kreuz (Plus-Form), 3 Zellen dick. Liefert Zellen in Reihenfolge."""
    cells = []
    N, C, HALF = 7, 3, 1
    today = date.today()
    dim = calendar.monthrange(year, month)[1]
    days_map = db.month_days(year, month)
    daynum = 1
    for r in range(N):
        for c in range(N):
            in_cross = abs(r - C) <= HALF or abs(c - C) <= HALF
            if r == C and c == C:
                cells.append({"cls": "center", "day": None})
            elif in_cross:
                if daynum <= dim:
                    d = daynum
                    if date(year, month, d) > today:
                        cls = "future"
                    else:
                        cls = days_map.get(d, {}).get("status", "green")
                    cells.append({"cls": cls, "day": d})
                else:
                    cells.append({"cls": "ghost", "day": None})
                daynum += 1
            else:
                cells.append({"cls": "empty", "day": None})
    return cells


def recent_entries(limit=6):
    entries = [d for d in db.all_days() if d[1] != "green"]
    entries.sort(key=lambda x: x[0], reverse=True)
    return entries[:limit]


def _format_de(key):
    d = db.parse_key(key)
    return d.strftime("%d.%m.%Y") if d else key


def _month_context():
    today = date.today()
    y = int(request.args.get("y", today.year))
    m = int(request.args.get("m", today.month))
    prev_y, prev_m = (y, m - 1) if m > 1 else (y - 1, 12)
    next_y, next_m = (y, m + 1) if m < 12 else (y + 1, 1)
    return {
        "year": y,
        "month": m,
        "month_name": MONTHS_DE[m - 1],
        "days_in_month": calendar.monthrange(y, m)[1],
        "prev": (prev_y, prev_m),
        "next": (next_y, next_m),
        "cells": cross_cells(y, m),
        "is_current": (y, m) == (today.year, today.month),
    }


# ---------- Anzeige ----------

@app.route("/")
def board():
    ctx = _month_context()
    t = date.today()
    ctx.update({
        "abteilung": db.get_config("abteilung") or "",
        "meister": db.get_config("meister") or "",
        "ersthelfer": db.list_ersthelfer(),
        "notruf": db.list_notruf(),
        "safe_days": db.count_safe_days(),
        "today_str": "%s, %d. %s %d" % (WEEKDAYS_DE[t.weekday()], t.day, MONTHS_DE[t.month - 1], t.year),
    })
    return render_template("board.html", active_tab="anzeige", **ctx)


# ---------- Admin ----------

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if auth.check_login(request.form.get("password", "")):
            session["logged_in"] = True
            return redirect(url_for("admin"))
        error = "Falsches Passwort."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    nxt = request.args.get("next", "")
    # nur interne relative Pfade erlauben (Schutz vor Open Redirect)
    if nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    return redirect(url_for("login"))


@app.route("/admin")
@auth.login_required
def admin():
    start_date = db.get_config("start_date")
    ctx = {
        "abteilung": db.get_config("abteilung") or "",
        "meister": db.get_config("meister") or "",
        "ersthelfer": db.list_ersthelfer(),
        "notruf": db.list_notruf(),
        "safe_days": db.count_safe_days(),
        "start_date": start_date or "",
        "start_date_de": _format_de(start_date) if start_date else "",
        "today_iso": date.today().isoformat(),
        "recent": [{"date": _format_de(d), "status": s, "note": n} for (d, s, n) in recent_entries()],
    }
    return render_template("admin.html", active_tab="admin", **ctx)


@app.route("/admin/abteilung", methods=["POST"])
@auth.login_required
def admin_abteilung():
    v = request.form.get("abteilung", "").strip()
    if v:
        db.set_config("abteilung", v)
    return redirect(url_for("admin"))


@app.route("/admin/meister", methods=["POST"])
@auth.login_required
def admin_meister():
    db.set_config("meister", request.form.get("meister", "").strip())
    return redirect(url_for("admin"))


@app.route("/admin/ersthelfer-add", methods=["POST"])
@auth.login_required
def admin_ersthelfer_add():
    v = request.form.get("name", "").strip()
    if v:
        db.add_ersthelfer(v)
    return redirect(url_for("admin"))


@app.route("/admin/ersthelfer-remove", methods=["POST"])
@auth.login_required
def admin_ersthelfer_remove():
    try:
        db.remove_ersthelfer(int(request.form.get("id", "")))
    except (TypeError, ValueError):
        pass
    return redirect(url_for("admin"))


@app.route("/admin/notruf-add", methods=["POST"])
@auth.login_required
def admin_notruf_add():
    label = request.form.get("label", "").strip()
    value = request.form.get("value", "").strip()
    if label and value:
        db.add_notruf(label, value)
    return redirect(url_for("admin"))


@app.route("/admin/notruf-remove", methods=["POST"])
@auth.login_required
def admin_notruf_remove():
    try:
        db.remove_notruf(int(request.form.get("id", "")))
    except (TypeError, ValueError):
        pass
    return redirect(url_for("admin"))


@app.route("/admin/zahlung-days", methods=["POST"])
@auth.login_required
def admin_zahlung_days():
    try:
        n = int(request.form.get("days", ""))
        if n >= 0:
            db.set_config("start_date", (date.today() - timedelta(days=n - 1)).isoformat())
    except (TypeError, ValueError):
        pass
    return redirect(url_for("admin"))


@app.route("/admin/zahlung-date", methods=["POST"])
@auth.login_required
def admin_zahlung_date():
    db.set_config("start_date", request.form.get("start_date", "").strip())
    return redirect(url_for("admin"))


@app.route("/admin/unfall", methods=["POST"])
@auth.login_required
def admin_unfall():
    d = request.form.get("date", "").strip()
    typ = request.form.get("type", "red")
    person = request.form.get("person", "").strip()
    desc = request.form.get("desc", "").strip()

    if typ not in ("red", "yellow"):
        typ = "red"
    p = db.parse_key(d)
    if not p:
        return redirect(url_for("admin"))
    if p > date.today():
        return redirect(url_for("admin"))
    if not person and not desc:
        return redirect(url_for("admin"))

    note = (person + (" — " + desc if desc else "")) if person else desc
    db.set_day(p.year, p.month, p.day, typ, note)
    return redirect(url_for("admin"))


@app.route("/admin/password", methods=["POST"])
@auth.login_required
def admin_password():
    new = request.form.get("password", "").strip()
    if len(new) >= 4:
        auth.set_password(new)
    return redirect(url_for("admin"))


@app.route("/admin/reboot", methods=["POST"])
@auth.login_required
def admin_reboot():
    subprocess.run(["sudo", "-n", "reboot"], capture_output=True)
    return redirect(url_for("admin"))


@app.route("/admin/shutdown", methods=["POST"])
@auth.login_required
def admin_shutdown():
    subprocess.run(["sudo", "-n", "shutdown", "-h", "now"], capture_output=True)
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8002")), threaded=True)
