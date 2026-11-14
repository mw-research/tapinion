import hashlib
from datetime import datetime, timedelta

from conftest import make_event
from fastapi.testclient import TestClient

from tapinion import db
from tapinion.main import app


def device_key(event, name="Tablet"):
    with db.session() as conn:
        _, secret = db.create_device(conn, event["id"], name)
    return secret


def ts(**delta):
    return (datetime.now() - timedelta(**delta)).replace(microsecond=0).isoformat()


def test_bundle_has_everything_for_offline(fresh_db):
    ev = make_event("Offline fair", mode="nps", pin="4711")
    key = device_key(ev)
    with TestClient(app) as t:
        assert t.get(f"/api/kiosk/{ev['kiosk_token']}").status_code == 403
        b = t.get(f"/api/kiosk/{ev['kiosk_token']}", headers={"X-Kiosk-Device": key}).json()
        health = t.get("/healthz").json()
    assert b["event"]["name"] == "Offline fair" and b["event"]["mode"] == "nps" and b["event"]["active"]
    assert b["event"]["question"]["de"].startswith("Wie wahrscheinlich")
    pin = b["event"]["pin"]
    assert hashlib.sha256((pin["salt"] + "4711").encode()).hexdigest() == pin["sha256"]
    assert "4711" not in str(b)
    assert b["brand"]["logo"].startswith("data:image/")
    assert b["texts"]["de"]["kiosk.thanks"].startswith("Vielen Dank")
    assert b["server"]["instance"] == health["instance"] and len(health["instance"]) == 16
    assert b["device"]["name"] == "Tablet"


def test_votes_sync_once_even_if_sent_twice(fresh_db):
    ev = make_event("Sync")
    key = device_key(ev)
    votes = [{"id": "a1", "value": "happy", "ts": ts(days=10), "lang": "de"},
             {"id": "a2", "value": "unhappy", "ts": ts(days=9)},
             {"id": "bad", "value": "7", "ts": ts(days=1)},           # not a smiley value
             {"id": "old", "value": "happy", "ts": ts(days=200)}]     # older than 90 days
    with TestClient(app) as t:
        url, h = f"/api/kiosk/{ev['kiosk_token']}/votes", {"X-Kiosk-Device": key}
        r = t.post(url, json={"votes": votes}, headers=h).json()
        assert r["accepted"] == ["a1", "a2"] and set(r["rejected"]) == {"bad", "old"}
        again = t.post(url, json={"votes": votes[:2]}, headers=h).json()  # sync interrupted, sent again
        assert again["accepted"] == ["a1", "a2"]
        assert t.post(url, json={"nope": 1}, headers=h).status_code == 400
    with db.session() as conn:
        assert db.get_event(conn, ev["id"])["n_responses"] == 2


def test_offline_votes_count_after_event_closed_and_device_switched_off(fresh_db):
    ev = make_event("Closed later")
    key = device_key(ev)
    with db.session() as conn:
        db.update_event(conn, ev["id"], active=0)  # organizer closed the event before the tablet synced
        did = db.list_devices(conn, ev["id"])[0]["id"]
        db.revoke_device(conn, did)
    with TestClient(app) as t:
        r = t.post(f"/api/kiosk/{ev['kiosk_token']}/votes", headers={"X-Kiosk-Device": key},
                   json={"votes": [{"id": "x1", "value": "happy", "ts": ts(hours=3)},
                                   {"id": "x2", "value": "happy", "ts": ts(hours=-1)}]}).json()
        assert r["accepted"] == ["x1"] and r["rejected"] == ["x2"]
        assert r["event_active"] is False and r["device_active"] is False
        assert t.get(f"/api/kiosk/{ev['kiosk_token']}", headers={"X-Kiosk-Device": key}).status_code == 403


def test_queued_web_vote_counts_after_event_closed(fresh_db):
    ev = make_event("Web queue")
    key = device_key(ev)
    with db.session() as conn:
        db.update_event(conn, ev["id"], active=0)
    with TestClient(app) as t:
        r = t.post(f"/k/{ev['kiosk_token']}/vote", headers={"X-Kiosk-Device": key},
                   data={"value": "happy", "queued": "1", "ts": ts(hours=2)})
        assert r.status_code == 204
        assert "closed" in t.post(f"/k/{ev['kiosk_token']}/vote", headers={"X-Kiosk-Device": key},
                                  data={"value": "happy"}).text
    with db.session() as conn:
        assert db.get_event(conn, ev["id"])["n_responses"] == 1


def test_pairing_gives_the_app_its_own_key_and_the_overall_result(fresh_db):
    ev = make_event("Pair", responses=[("happy", "2026-11-10 10:00:00"), ("unhappy", "2026-11-10 10:01:00")])
    web_key = device_key(ev, "Kiosk tablet")
    with TestClient(app) as t:
        assert t.post(f"/api/kiosk/{ev['kiosk_token']}/pair", json={}).status_code == 403
        r = t.post(f"/api/kiosk/{ev['kiosk_token']}/pair", json={}, headers={"X-Kiosk-Device": web_key}).json()
        offline_key = r["device"]
        assert r["name"] == "Kiosk tablet (offline)" and offline_key != web_key
        # leaving the web kiosk switches the web key off – the offline copy keeps working
        with db.session() as conn:
            web = db.device_for(conn, ev["id"], web_key)
            db.revoke_device(conn, web["id"])
        b = t.get(f"/api/kiosk/{ev['kiosk_token']}", headers={"X-Kiosk-Device": offline_key}).json()
        assert b["result"]["n"] == 2 and [g["count"] for g in b["result"]["groups"]] == [1, 0, 1]
        assert "created_at" not in str(b["result"])
