from conftest import make_event

from tapinion import db, stats


def test_nps_definition():
    r = stats.nps_stats(["10", "9", "8", "7", "6", "0"])
    assert [g["count"] for g in r["groups"]] == [2, 2, 2]
    assert r["score"] == 0
    assert stats.nps_stats(["10", "10", "3"])["score"] == 33
    assert stats.nps_stats([])["score"] is None


def test_organizer_sees_aggregate_only(client_for):
    open_ev = make_event("Open", responses=[("happy", "2026-11-10 08:01:00"), ("neutral", "2026-11-10 08:02:00")])
    closed = make_event("Closed", active=0)
    c, token = client_for("orga")
    page = c.get(f"/dashboard?event_id={open_ev['id']}").text
    assert "Satisfied" in page and 'id="datapoints"' not in page and "08:01" not in page
    assert "export.csv" not in page and ".pdf" not in page
    assert c.get(f"/dashboard/responses?event_id={open_ev['id']}").status_code == 403
    assert c.get(f"/dashboard/export.csv?event_id={open_ev['id']}").status_code == 403
    assert c.get("/reports").status_code == 403
    assert c.get(f"/reports/event/{open_ev['id']}.pdf").status_code == 403
    assert c.get("/settings").status_code == 403
    # only open events
    assert "Closed" not in c.get("/events").text
    assert c.get(f"/dashboard?event_id={closed['id']}").status_code == 200
    assert "Closed" not in c.get(f"/dashboard?event_id={closed['id']}").text
    # may create and see the PIN, may not edit or delete
    r = c.post("/events", data={"name": "Orga event", "mode": "nps", "pin": "1357", "event_date": "2026-11-12"},
               headers={"X-CSRF-Token": token})
    assert r.status_code == 200 and "Orga event" in r.text
    assert "2468" in c.get(f"/events/{open_ev['id']}/pin").text
    assert c.get(f"/events/{open_ev['id']}/edit").status_code == 403
    assert c.post(f"/events/{open_ev['id']}/delete", headers={"X-CSRF-Token": token}).status_code == 403


def test_analyst_edits_but_cannot_delete(client_for):
    ev = make_event("Ana", mode="nps", responses=[("9", "2026-11-10 08:01:00")])
    c, token = client_for("ana")
    page = c.get(f"/dashboard?event_id={ev['id']}").text
    assert 'id="datapoints"' in page and "export.csv" in page
    dp = c.get(f"/dashboard/responses?event_id={ev['id']}").text
    assert "08:01:00" in dp and "/delete" not in dp
    r = c.post(f"/events/{ev['id']}", data={"name": "Renamed", "mode": "nps", "event_date": "2026-11-11",
                                           "kiosk_lang": "de", "question_en": "Better?"},
               headers={"X-CSRF-Token": token})
    assert r.status_code == 200 and "Renamed" in r.text
    r = c.post(f"/events/{ev['id']}", data={"name": "X", "mode": "smiley", "event_date": "2026-11-11"},
               headers={"X-CSRF-Token": token})
    assert r.status_code == 422  # mode locked once ratings exist
    assert c.post(f"/events/{ev['id']}/delete", headers={"X-CSRF-Token": token}).status_code == 403
    with db.session() as conn:
        rid = db.responses_for(conn, ev["id"])[0]["id"]
    assert c.post(f"/responses/{rid}/delete", headers={"X-CSRF-Token": token}).status_code == 403
    assert c.get("/settings").status_code == 403


def test_admin_deletes_single_rating_and_events(client_for):
    ev = make_event("Adm", responses=[("happy", "2026-11-10 08:01:00"), ("unhappy", "2026-11-10 08:02:00")])
    c, token = client_for("admin")
    with db.session() as conn:
        rid = db.responses_for(conn, ev["id"])[0]["id"]
    assert "/delete" in c.get(f"/dashboard/responses?event_id={ev['id']}").text
    r = c.post(f"/responses/{rid}/delete", headers={"X-CSRF-Token": token})
    assert r.status_code == 200 and r.headers["HX-Trigger"] == "responses-changed"
    with db.session() as conn:
        assert db.get_event(conn, ev["id"])["n_responses"] == 1
    assert c.post(f"/events/{ev['id']}/delete", headers={"X-CSRF-Token": token}).status_code == 200
    with db.session() as conn:
        assert db.get_event(conn, ev["id"]) is None


def test_admin_manages_users(client_for):
    c, token = client_for("admin")
    r = c.post("/settings/users", data={"username": "helper", "password": "helper-password-1", "role": "organizer"},
               headers={"X-CSRF-Token": token})
    assert r.status_code == 200 and "helper" in r.text
    with db.session() as conn:
        uid = db.get_user_by_name(conn, "helper")["id"]
        me = db.get_user_by_name(conn, "admin")["id"]
    assert c.post(f"/settings/users/{uid}/role", data={"role": "analyst"}, headers={"X-CSRF-Token": token}).status_code == 200
    assert c.post(f"/settings/users/{me}/role", data={"role": "analyst"}, headers={"X-CSRF-Token": token}).status_code == 400
    assert c.post(f"/settings/users/{me}/delete", headers={"X-CSRF-Token": token}).status_code == 400
    assert c.post(f"/settings/users/{uid}/delete", headers={"X-CSRF-Token": token}).status_code == 200


def test_post_without_csrf_rejected(client_for):
    c, _ = client_for("admin")
    assert c.post("/events", data={"name": "x", "mode": "nps", "pin": "1234"}).status_code == 400
