import os
import tempfile

# Beim Import nicht die echte DB anfassen
os.environ.setdefault("SAFETY_DB", os.path.join(tempfile.mkdtemp(), "app.db"))

import pytest

import auth
import db
import license
from app import app


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    auth.init_admin_password("admin")
    yield


def test_day_key_zero_padded():
    assert db.day_key(2026, 8, 5) == "2026-08-05"
    assert db.day_key(2026, 12, 31) == "2026-12-31"


def test_parse_key():
    from datetime import date
    assert db.parse_key("2026-08-05") == date(2026, 8, 5)
    assert db.parse_key("garbage") is None


def test_count_safe_days_default_month_start():
    from datetime import date
    today = date.today()
    expected = (today - date(today.year, today.month, 1)).days + 1
    assert db.count_safe_days() == expected


def test_count_safe_days_resets_on_red():
    from datetime import date, timedelta
    today = date.today()
    red = today - timedelta(days=3)
    db.set_day(red.year, red.month, red.day, "red", "Test")
    assert db.count_safe_days() == 3


def test_count_safe_days_start_date_overrides():
    from datetime import date, timedelta
    db.set_config("start_date", (date.today() - timedelta(days=99)).isoformat())
    assert db.count_safe_days() == 100


def test_license_compute_deterministic_and_bound():
    assert license.compute_key("abc", "secret") == license.compute_key("abc", "secret")
    assert license.compute_key("abc", "secret") != license.compute_key("xyz", "secret")


def test_license_is_valid_bound_to_serial(tmp_path, monkeypatch):
    sp = tmp_path / ".secret"
    lp = tmp_path / "license.key"
    monkeypatch.setattr(license, "_secret_path", lambda: str(sp))
    monkeypatch.setattr(license, "_license_path", lambda: str(lp))
    monkeypatch.setattr(license, "get_serial", lambda: "10000000abcdef")
    sp.write_text("geheim")
    assert license.make_key("geheim") is not None
    assert license.is_valid() is True
    # Image/SD-Karte auf einen anderen Pi kopiert -> andere Seriennummer -> gesperrt
    monkeypatch.setattr(license, "get_serial", lambda: "10000000ZZZZZZ")
    assert license.is_valid() is False


def test_board_route():
    assert app.test_client().get("/").status_code == 200


def test_login_and_admin():
    client = app.test_client()
    r = client.post("/login", data={"password": "admin"}, follow_redirects=True)
    assert r.status_code == 200
    assert client.get("/admin").status_code == 200


def test_login_wrong_password():
    client = app.test_client()
    r = client.post("/login", data={"password": "falsch"}, follow_redirects=True)
    assert "Falsches Passwort" in r.get_data(as_text=True)


def test_unfall_flow_and_counter_reset():
    from datetime import date
    client = app.test_client()
    client.post("/login", data={"password": "admin"})
    today = date.today().isoformat()
    client.post(
        "/admin/unfall",
        data={"date": today, "type": "red", "person": "Max", "desc": "Schnitt"},
        follow_redirects=True,
    )
    assert db.count_safe_days() == 0  # Unfall heute -> 0


def test_notruf_crud():
    db.add_notruf("Feuerwehr", "112")
    db.add_notruf("Werkschutz", "040 123")
    rows = db.list_notruf()
    assert len(rows) == 2
    assert rows[0]["label"] == "Feuerwehr"
    assert rows[0]["value"] == "112"
    db.remove_notruf(rows[0]["id"])
    assert len(db.list_notruf()) == 1


def test_notruf_admin_and_board():
    client = app.test_client()
    client.post("/login", data={"password": "admin"})
    client.post("/admin/notruf-add", data={"label": "Feuerwehr", "value": "112"}, follow_redirects=True)
    assert any(n["label"] == "Feuerwehr" for n in db.list_notruf())
    r = client.get("/")
    html = r.get_data(as_text=True)
    assert "Feuerwehr" in html
    assert "112" in html


def test_logout_protects_admin():
    client = app.test_client()
    client.post("/login", data={"password": "admin"})
    assert client.get("/admin").status_code == 200
    client.get("/logout")
    # Nach dem Logout ist der Admin-Bereich wieder geschützt (Redirect zum Login)
    assert client.get("/admin").status_code == 302
