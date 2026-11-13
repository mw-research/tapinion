from datetime import datetime, timedelta

from conftest import make_event
from fastapi.testclient import TestClient

from tapinion import db
from tapinion.main import app


def test_kiosk_needs_pin_and_votes(client_for):
    ev = make_event("Kiosk", mode="nps")
    k = ev["kiosk_token"]
    with TestClient(app) as t:
        page = t.get(f"/k/{k}").text
        assert "Enter PIN to start the kiosk" in page and "nps-btn" not in page
        assert t.post(f"/k/{k}/vote", data={"value": "9"}).status_code == 403
        assert "Wrong PIN" in t.post(f"/k/{k}/unlock", data={"pin": "0000"}).text
        r = t.post(f"/k/{k}/unlock", data={"pin": "2468"})
        assert r.status_code == 204 and r.headers["HX-Redirect"].startswith(f"/k/{k}")
        assert "nps-btn" in t.get(f"/k/{k}").text
        assert "Thank you" in t.post(f"/k/{k}/vote", data={"value": "9", "lang": "en"}).text
        assert "Vielen Dank" in t.post(f"/k/{k}/vote", data={"value": "10", "lang": "de"}).text
        assert t.post(f"/k/{k}/vote", data={"value": "happy"}).status_code == 400
        # shortening the URL leads to the login page, never into a dashboard
        r = t.get("/", follow_redirects=False)
        assert r.headers["location"] == "/login"
        # once on the login page, getting back into the kiosk needs the PIN again
        assert t.get("/login").status_code == 200
        assert "Enter PIN to start the kiosk" in t.get(f"/k/{k}").text
        t.post(f"/k/{k}/unlock", data={"pin": "2468"})
        # leaving needs the PIN
        assert "Wrong PIN" in t.post(f"/k/{k}/exit", data={"pin": "1111"}).text
        r = t.post(f"/k/{k}/exit", data={"pin": "2468"})
        assert r.headers["HX-Redirect"] == "/login"
        assert t.post(f"/k/{k}/vote", data={"value": "9"}).status_code == 403
    with db.session() as conn:
        assert db.get_event(conn, ev["id"])["n_responses"] == 2


def test_starting_kiosk_logs_out(client_for):
    ev = make_event("Start")
    c, _ = client_for("orga")
    r = c.get(f"/events/{ev['id']}/kiosk")
    assert r.url.path == f"/k/{ev['kiosk_token']}" and "smiley-btn" in r.text  # unlocked, no PIN prompt
    assert c.get("/dashboard", follow_redirects=False).headers["location"].startswith("/login")
    assert c.get("/", follow_redirects=False).headers["location"] == "/login"


def test_login_page_lists_open_kiosks(client_for):
    make_event("Listed")
    make_event("Hidden closed", active=0)
    make_event("No pin yet", pin=None)
    with TestClient(app) as t:
        page = t.get("/login").text
        assert "Listed" in page and "Hidden closed" not in page and "No pin yet" not in page
    c, token = client_for("admin")
    c.post("/settings/appearance", data={"brand_name": "X", "color_primary": "#123456", "color_accent": "#abcdef"},
           headers={"X-CSRF-Token": token})
    with TestClient(app) as t:
        assert "Listed" not in t.get("/login").text


def test_offline_votes_keep_their_time(client_for):
    ev = make_event("Offline")
    k = ev["kiosk_token"]
    earlier = (datetime.now() - timedelta(hours=2)).replace(microsecond=0)
    with TestClient(app) as t:
        t.post(f"/k/{k}/unlock", data={"pin": "2468"})
        r = t.post(f"/k/{k}/vote", data={"value": "happy", "ts": earlier.isoformat(), "queued": "1"})
        assert r.status_code == 204
        t.post(f"/k/{k}/vote", data={"value": "happy", "ts": "1999-01-01T10:00:00", "queued": "1"})
    with db.session() as conn:
        times = [r["created_at"] for r in db.responses_for(conn, ev["id"])]
    assert earlier.isoformat(sep=" ") in times
    assert not any(t.startswith("1999") for t in times)  # too old: server time used instead


def test_closed_event_takes_no_votes(client_for):
    ev = make_event("Closed", active=0)
    with TestClient(app) as t:
        t.post(f"/k/{ev['kiosk_token']}/unlock", data={"pin": "2468"})
        assert "closed" in t.post(f"/k/{ev['kiosk_token']}/vote", data={"value": "happy"}).text
    with db.session() as conn:
        assert db.get_event(conn, ev["id"])["n_responses"] == 0


def test_qr_code(client_for):
    ev = make_event("QR")
    c, _ = client_for("orga")
    r = c.get(f"/events/{ev['id']}/qr")
    assert r.status_code == 200 and "<svg" in r.text and f"/k/{ev['kiosk_token']}" in r.text
