import sqlite3

from conftest import csrf_of, make_event
from fastapi.testclient import TestClient

from tapinion import db
from tapinion.main import app

PNG_1PX = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                        "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082")


def test_first_setup(fresh_db):
    with TestClient(app) as t:
        assert t.get("/", follow_redirects=False).headers["location"] == "/setup"
        token = csrf_of(t, "/setup")
        r = t.post("/setup", data={"csrf": token, "username": "boss", "password": "a-long-password",
                                   "password2": "a-long-password", "lang": "de", "brand_name": "Meine Firma"},
                   follow_redirects=False)
        assert r.headers["location"] == "/settings"
        page = t.get("/settings").text
        assert "Darstellung" in page and "Meine Firma" in page
        assert t.get("/setup", follow_redirects=False).headers["location"] == "/login"


def test_language_switch_and_accept_language(users):
    with TestClient(app) as t:
        assert "Log in" in t.get("/login").text
        assert "Anmelden" in t.get("/login", headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.5"}).text
        token = csrf_of(t)
        t.post("/lang", data={"csrf": token, "lang": "de", "back": "/login"})
        assert "Anmelden" in t.get("/login").text


def test_appearance_and_logo(client_for):
    c, token = client_for("admin")
    r = c.post("/settings/appearance", data={"brand_name": "ACME", "color_primary": "nope", "color_accent": "#000000"},
               headers={"X-CSRF-Token": token})
    assert r.status_code == 400
    r = c.post("/settings/appearance",
               data={"brand_name": "ACME", "color_primary": "#ffcc00", "color_accent": "#112233", "show_open_events": "1"},
               files={"logo": ("logo.png", PNG_1PX, "image/png")}, headers={"X-CSRF-Token": token})
    assert r.status_code == 200
    page = c.get("/dashboard").text
    assert "--brand: #ffcc00" in page and "--on-brand: #111111" in page and "ACME" in page
    logo = c.get("/branding/logo")
    assert logo.headers["content-type"] == "image/png" and logo.content == PNG_1PX
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    c.post("/settings/appearance", data={"brand_name": "ACME", "color_primary": "#ffcc00", "color_accent": "#112233"},
           files={"logo": ("x.svg", svg, "image/svg+xml")}, headers={"X-CSRF-Token": token})
    assert "default-src 'none'" in c.get("/branding/logo").headers["content-security-policy"]
    bad = c.post("/settings/appearance", data={"brand_name": "", "color_primary": "#ffcc00", "color_accent": "#112233"},
                 files={"logo": ("x.png", b"not an image", "image/png")}, headers={"X-CSRF-Token": token})
    assert bad.status_code == 400
    c.post("/settings/appearance/reset", headers={"X-CSRF-Token": token})
    assert "image/svg+xml" in c.get("/branding/logo").headers["content-type"]  # default logo again


def test_pdf_reports_in_both_languages(client_for):
    ev = make_event("PDF – „Test“ ÄÖÜ", mode="nps", responses=[("9", "2026-11-10 09:00:00"), ("3", "2026-11-10 10:00:00")])
    c, token = client_for("ana")
    for lang in ("en", "de"):
        c.post("/lang", data={"lang": lang, "back": "/"}, headers={"X-CSRF-Token": token})
        r = c.get(f"/reports/event/{ev['id']}.pdf")
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        r = c.get("/reports/overview.pdf?details=1")
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert "Bericht" in c.get(f"/reports/event/{ev['id']}.pdf").headers["content-disposition"]


def test_migration_from_schema_1(tmp_path, monkeypatch):
    path = tmp_path / "old.sqlite3"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, pw_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'organizer', 'viewer')), created_at TEXT NOT NULL);
        CREATE TABLE events (id INTEGER PRIMARY KEY, name TEXT NOT NULL, event_date TEXT NOT NULL,
            mode TEXT NOT NULL, question TEXT NOT NULL, kiosk_token TEXT NOT NULL UNIQUE, kiosk_pin_hash TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1, created_by INTEGER, created_at TEXT NOT NULL);
        CREATE TABLE responses (id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL, value TEXT NOT NULL);
        INSERT INTO users VALUES (1, 'a', 'x', 'admin', '2026-01-01'), (2, 'v', 'x', 'viewer', '2026-01-01');
        INSERT INTO events VALUES (1, 'Old', '2026-01-02', 'smiley', 'Frage?', 'tok', 'hash', 0, 1, '2026-01-02');
        INSERT INTO responses VALUES (1, 1, '2026-01-02 10:00:00', 'happy');
    """)
    old.commit()
    old.close()
    monkeypatch.setenv("DB_PATH", str(path))
    db.init_db()
    with db.session() as conn:
        assert [u["role"] for u in db.list_users(conn)] == ["admin", "analyst"]
        ev = db.get_event(conn, 1)
        assert ev["question_de"] == "Frage?" and ev["kiosk_pin"] is None and ev["n_responses"] == 1
    db.init_db()  # idempotent
