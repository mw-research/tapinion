import re

import pytest
from fastapi.testclient import TestClient

from tapinion import db
from tapinion.main import app, login_throttle, pin_throttle
from tapinion.security import hash_secret

PASSWORDS = {"admin": "admin-pass-123", "ana": "analyst-pass-1", "orga": "organizer-pass"}


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.delenv("ADMIN_USER", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    login_throttle._fails.clear()
    pin_throttle._fails.clear()
    db.init_db()
    return tmp_path


@pytest.fixture()
def users(fresh_db):
    with db.session() as conn:
        db.create_user(conn, "admin", hash_secret(PASSWORDS["admin"]), "admin", "en")
        db.create_user(conn, "ana", hash_secret(PASSWORDS["ana"]), "analyst", "en")
        db.create_user(conn, "orga", hash_secret(PASSWORDS["orga"]), "organizer", "en")
    return PASSWORDS


def csrf_of(client, path="/login"):
    return re.search(r'name="csrf" value="([^"]+)"', client.get(path).text).group(1)


def login(client, user):
    token = csrf_of(client)
    r = client.post("/login", data={"username": user, "password": PASSWORDS[user], "csrf": token, "next": "/dashboard"},
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    return csrf_of(client, "/account")


@pytest.fixture()
def client_for(users):
    clients = []

    def make(user=None):
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        token = login(c, user) if user else None
        return c, token

    yield make
    for c in clients:
        c.__exit__(None, None, None)


def make_event(name="Event", mode="smiley", pin="2468", active=1, responses=()):
    with db.session() as conn:
        eid = db.create_event(conn, name, "2026-11-10", mode, "", "", "en", pin, None, active)
        for value, when in responses:
            db.add_response(conn, eid, value, when)
        return db.get_event(conn, eid)
