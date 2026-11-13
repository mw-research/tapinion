import sqlite3
from datetime import datetime, timedelta

from conftest import make_event
from fastapi.testclient import TestClient

from tapinion import db
from tapinion.main import app


def unlock(client, event, name=""):
    r = client.post(f"/k/{event['kiosk_token']}/unlock", data={"pin": "2468", "device_name": name})
    assert r.status_code == 204
    page = client.get(f"/k/{event['kiosk_token']}")
    assert page.headers["X-Kiosk-State"] == "unlocked"
    return page.text.split('data-device="')[1].split('"')[0]


def test_each_device_has_a_key_and_its_own_count(client_for):
    ev = make_event("Multi")
    k = ev["kiosk_token"]
    with TestClient(app) as a, TestClient(app) as b:
        key_a = unlock(a, ev, "Exit north")
        key_b = unlock(b, ev)
        assert key_a and key_b and key_a != key_b
        a.post(f"/k/{k}/vote", data={"value": "happy"})
        a.post(f"/k/{k}/vote", data={"value": "happy"})
        b.post(f"/k/{k}/vote", data={"value": "unhappy"})
    with db.session() as conn:
        devices = {d["name"]: d["n_responses"] for d in db.list_devices(conn, ev["id"])}
    assert devices == {"Exit north": 2, "Device 2": 1}
    c, _ = client_for("orga")  # organizers see the per-device counts too (aggregates only)
    page = c.get(f"/dashboard?event_id={ev['id']}").text
    assert "Per device" in page and "Exit north" in page


def test_votes_arrive_after_the_session_expired(client_for):
    """Days offline: the browser session is gone, the device key still counts."""
    ev = make_event("Offline days")
    k = ev["kiosk_token"]
    with TestClient(app) as t:
        key = unlock(t, ev)
    two_days_ago = (datetime.now() - timedelta(days=2)).replace(microsecond=0)
    with TestClient(app) as fresh:  # no cookie at all
        assert fresh.post(f"/k/{k}/vote", data={"value": "happy"}).status_code == 403
        r = fresh.post(f"/k/{k}/vote", data={"value": "happy", "queued": "1", "ts": two_days_ago.isoformat()},
                       headers={"X-Kiosk-Device": key})
        assert r.status_code == 204
        assert fresh.get(f"/k/{k}/form", headers={"X-Kiosk-Device": key}).status_code == 200
    with db.session() as conn:
        assert two_days_ago.isoformat(sep=" ") in [r["created_at"] for r in db.responses_for(conn, ev["id"])]


def test_restart_resumes_without_pin_until_left_with_pin(client_for):
    ev = make_event("Resume")
    k = ev["kiosk_token"]
    with TestClient(app) as t:
        key = unlock(t, ev)
    with TestClient(app) as rebooted:
        assert "Enter PIN to start the kiosk" in rebooted.get(f"/k/{k}").text
        assert rebooted.post(f"/k/{k}/resume", data={"device": "wrong"}).status_code == 403
        assert rebooted.post(f"/k/{k}/resume", data={"device": key}).status_code == 204
        assert "smiley-btn" in rebooted.get(f"/k/{k}").text
        rebooted.post(f"/k/{k}/vote", data={"value": "happy"})
        r = rebooted.post(f"/k/{k}/exit", data={"pin": "2468"})
        assert r.headers["HX-Redirect"] == "/login"
    with TestClient(app) as later:
        assert later.post(f"/k/{k}/resume", data={"device": key}).status_code == 403
        assert later.post(f"/k/{k}/vote", data={"value": "happy"}, headers={"X-Kiosk-Device": key}).status_code == 403
        # stored on the device before the exit: still counts; after the exit: not
        before = (datetime.now() - timedelta(minutes=5)).replace(microsecond=0).isoformat()
        after = (datetime.now() + timedelta(minutes=2)).replace(microsecond=0).isoformat()
        assert later.post(f"/k/{k}/vote", data={"value": "neutral", "queued": "1", "ts": before, "device": key}).status_code == 204
        assert later.post(f"/k/{k}/vote", data={"value": "neutral", "queued": "1", "ts": after, "device": key}).status_code == 403
    with db.session() as conn:
        assert db.get_event(conn, ev["id"])["n_responses"] == 2


def test_devices_list_and_switch_off(client_for):
    ev = make_event("Admin view")
    k = ev["kiosk_token"]
    with TestClient(app) as t:
        key = unlock(t, ev, "Hall")
        assert t.post(f"/k/{k}/ping").status_code == 204
        o, otoken = client_for("orga")
        listing = o.get(f"/events/{ev['id']}/devices").text
        assert "Hall" in listing and "running now" in listing and "/revoke" not in listing
        with db.session() as conn:
            did = db.list_devices(conn, ev["id"])[0]["id"]
        assert o.post(f"/devices/{did}/revoke", headers={"X-CSRF-Token": otoken}).status_code == 403
        a, atoken = client_for("ana")
        r = a.post(f"/devices/{did}/revoke", headers={"X-CSRF-Token": atoken})
        assert r.status_code == 200 and "switched off" in r.text
        assert t.post(f"/k/{k}/ping").status_code == 403
        assert "Enter PIN to start the kiosk" in t.get(f"/k/{k}").text
        assert t.post(f"/k/{k}/vote", data={"value": "happy"}, headers={"X-Kiosk-Device": key}).status_code == 403


def test_service_worker_and_cache_marker(fresh_db):
    ev = make_event("SW")
    with TestClient(app) as t:
        sw = t.get("/sw.js")
        assert sw.status_code == 200 and sw.headers["Service-Worker-Allowed"] == "/"
        assert "X-Kiosk-State" in sw.text
        assert t.get(f"/k/{ev['kiosk_token']}").headers["X-Kiosk-State"] == "locked"


def test_migration_from_schema_2(tmp_path, monkeypatch):
    path = tmp_path / "v2.sqlite3"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, pw_hash TEXT NOT NULL,
            role TEXT NOT NULL, lang TEXT, created_at TEXT NOT NULL);
        CREATE TABLE events (id INTEGER PRIMARY KEY, name TEXT NOT NULL, event_date TEXT NOT NULL, mode TEXT NOT NULL,
            question_de TEXT NOT NULL DEFAULT '', question_en TEXT NOT NULL DEFAULT '', kiosk_lang TEXT NOT NULL DEFAULT 'de',
            kiosk_token TEXT NOT NULL UNIQUE, kiosk_pin TEXT, active INTEGER NOT NULL DEFAULT 1, created_by INTEGER,
            created_at TEXT NOT NULL);
        CREATE TABLE responses (id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL, value TEXT NOT NULL);
        INSERT INTO events VALUES (1, 'E', '2026-01-01', 'smiley', '', '', 'de', 'tok', '1234', 1, NULL, '2026-01-01');
        INSERT INTO responses VALUES (1, 1, '2026-01-01 10:00:00', 'happy');
        PRAGMA user_version = 2;
    """)
    old.commit()
    old.close()
    monkeypatch.setenv("DB_PATH", str(path))
    db.init_db()
    with db.session() as conn:
        assert "device_id" in {r[1] for r in conn.execute("PRAGMA table_info(responses)")}
        assert db.responses_without_device(conn, 1) == 1
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
