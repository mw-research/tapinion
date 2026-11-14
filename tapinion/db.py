# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite storage: users, events, responses, settings and uploaded branding assets."""
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    pw_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'analyst', 'organizer')),
    lang TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    event_date TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('nps', 'smiley')),
    question_de TEXT NOT NULL DEFAULT '',
    question_en TEXT NOT NULL DEFAULT '',
    kiosk_lang TEXT NOT NULL DEFAULT 'de' CHECK (kiosk_lang IN ('de', 'en')),
    kiosk_token TEXT NOT NULL UNIQUE,
    kiosk_pin TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    secret_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_seen TEXT,
    revoked INTEGER NOT NULL DEFAULT 0,
    revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    value TEXT NOT NULL,
    device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
    client_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_responses_event ON responses(event_id, created_at);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
    name TEXT PRIMARY KEY,
    mime TEXT NOT NULL,
    data BLOB NOT NULL,
    updated_at TEXT NOT NULL
);
"""

NPS_VALUES = [str(i) for i in range(11)]
SMILEY_VALUES = ["happy", "neutral", "unhappy"]
ROLES = ("admin", "analyst", "organizer")


def db_path() -> str:
    return os.environ.get("DB_PATH") or os.path.join(os.getcwd(), "data", "tapinion.sqlite3")


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def connect() -> sqlite3.Connection:
    path = db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL needs shared memory and does not work on network file systems (NFS): set SQLITE_WAL=0 there.
    conn.execute("PRAGMA journal_mode = " + ("DELETE" if os.environ.get("SQLITE_WAL", "1") == "0" else "WAL"))
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with session() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if version < 2 and "events" in tables:
            _migrate_v1(conn)
        conn.executescript(SCHEMA)
        columns = {r[1] for r in conn.execute("PRAGMA table_info(responses)")}
        if "device_id" not in columns:  # schema 2 -> 3
            conn.execute("ALTER TABLE responses ADD COLUMN device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL")
        if "client_id" not in columns:  # schema 3 -> 4
            conn.execute("ALTER TABLE responses ADD COLUMN client_id TEXT")
        # a rating sent twice by a device (e.g. a sync interrupted halfway) is stored once
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_responses_client "
                     "ON responses(device_id, client_id) WHERE client_id IS NOT NULL")
        if not conn.execute("SELECT 1 FROM settings WHERE key = 'instance_id'").fetchone():
            conn.execute("INSERT INTO settings (key, value) VALUES ('instance_id', ?)", (secrets.token_hex(8),))
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _migrate_v1(conn) -> None:
    """Schema 1 -> 2: three roles, questions per language, readable kiosk PIN, settings."""
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript("""
        ALTER TABLE users RENAME TO users_v1;
        ALTER TABLE events RENAME TO events_v1;
    """)
    conn.executescript(SCHEMA)
    conn.execute("""INSERT INTO users (id, username, pw_hash, role, lang, created_at)
                    SELECT id, username, pw_hash,
                           CASE role WHEN 'admin' THEN 'admin' WHEN 'organizer' THEN 'organizer' ELSE 'analyst' END,
                           NULL, created_at FROM users_v1""")
    # The old PIN was stored as a hash only; migrated events need a new PIN (kiosk_pin NULL).
    conn.execute("""INSERT INTO events (id, name, event_date, mode, question_de, question_en, kiosk_lang,
                                        kiosk_token, kiosk_pin, active, created_by, created_at)
                    SELECT id, name, event_date, mode, question, '', 'de', kiosk_token, NULL, active,
                           created_by, created_at FROM events_v1""")
    conn.executescript("DROP TABLE events_v1; DROP TABLE users_v1;")
    conn.execute("PRAGMA foreign_keys = ON")


def new_token() -> str:
    return secrets.token_urlsafe(16)


# --- settings and assets ---------------------------------------------------

def get_settings(conn) -> dict:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}


def set_setting(conn, key, value) -> None:
    if value is None:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
    else:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))


def get_asset(conn, name):
    return conn.execute("SELECT * FROM assets WHERE name = ?", (name,)).fetchone()


def set_asset(conn, name, mime, data) -> None:
    conn.execute("INSERT INTO assets (name, mime, data, updated_at) VALUES (?, ?, ?, ?) "
                 "ON CONFLICT(name) DO UPDATE SET mime = excluded.mime, data = excluded.data, "
                 "updated_at = excluded.updated_at", (name, mime, data, now_iso()))


def delete_asset(conn, name) -> None:
    conn.execute("DELETE FROM assets WHERE name = ?", (name,))


# --- users -----------------------------------------------------------------

def get_user(conn, user_id):
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_name(conn, username):
    return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def list_users(conn):
    return conn.execute("SELECT * FROM users ORDER BY username").fetchall()


def count_users(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def count_admins(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]


def create_user(conn, username, pw_hash, role, lang=None):
    cur = conn.execute(
        "INSERT INTO users (username, pw_hash, role, lang, created_at) VALUES (?, ?, ?, ?, ?)",
        (username, pw_hash, role, lang, now_iso()),
    )
    return cur.lastrowid


# --- events ----------------------------------------------------------------

_EVENT_SELECT = """SELECT e.*, (SELECT COUNT(*) FROM responses r WHERE r.event_id = e.id) AS n_responses,
                          (SELECT COUNT(*) FROM devices d WHERE d.event_id = e.id AND d.revoked = 0) AS n_devices
                   FROM events e"""


def list_events(conn, only_active=False):
    where = " WHERE e.active = 1" if only_active else ""
    return conn.execute(_EVENT_SELECT + where + " ORDER BY e.event_date DESC, e.id DESC").fetchall()


def get_event(conn, event_id):
    return conn.execute(_EVENT_SELECT + " WHERE e.id = ?", (event_id,)).fetchone()


def get_event_by_token(conn, token):
    return conn.execute(_EVENT_SELECT + " WHERE e.kiosk_token = ?", (token,)).fetchone()


def create_event(conn, name, event_date, mode, question_de, question_en, kiosk_lang, pin, user_id, active=1):
    cur = conn.execute(
        """INSERT INTO events (name, event_date, mode, question_de, question_en, kiosk_lang, kiosk_token,
                               kiosk_pin, active, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, event_date, mode, question_de, question_en, kiosk_lang, new_token(), pin, active, user_id, now_iso()),
    )
    return cur.lastrowid


def update_event(conn, event_id, **fields):
    allowed = {"name", "event_date", "mode", "question_de", "question_en", "kiosk_lang", "kiosk_pin", "active",
               "kiosk_token"}
    cols = [k for k in fields if k in allowed]
    if cols:
        conn.execute(f"UPDATE events SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?",
                     [fields[c] for c in cols] + [event_id])


def select_events(conn, date_from=None, date_to=None, mode=None, only_with_data=True):
    out = []
    for e in sorted(list_events(conn), key=lambda e: (e["event_date"], e["id"])):
        if date_from and e["event_date"] < date_from:
            continue
        if date_to and e["event_date"] > date_to:
            continue
        if mode in ("nps", "smiley") and e["mode"] != mode:
            continue
        if only_with_data and not e["n_responses"]:
            continue
        out.append(e)
    return out


# --- responses -------------------------------------------------------------

def add_response(conn, event_id, value, created_at=None, device_id=None, client_id=None) -> bool:
    """Store a rating; False if this device already sent the rating with this client_id."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO responses (event_id, created_at, value, device_id, client_id) VALUES (?, ?, ?, ?, ?)",
        (event_id, created_at or now_iso(), value, device_id, client_id),
    )
    return cur.rowcount == 1


def instance_id(conn) -> str:
    """Fixed id of this installation; lets apps find their computer again at a new address."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'instance_id'").fetchone()
    return row["value"] if row else ""


def response_days(conn, event_id):
    rows = conn.execute(
        "SELECT DISTINCT substr(created_at, 1, 10) AS d FROM responses WHERE event_id = ? ORDER BY d",
        (event_id,),
    ).fetchall()
    return [r["d"] for r in rows]


def responses_for(conn, event_id, day=None):
    sql = "SELECT * FROM responses WHERE event_id = ?"
    args = [event_id]
    if day:
        sql += " AND substr(created_at, 1, 10) = ?"
        args.append(day)
    return conn.execute(sql + " ORDER BY created_at, id", args).fetchall()


def responses_page(conn, event_id, day=None, offset=0, limit=50):
    sql = "SELECT * FROM responses WHERE event_id = ?"
    args = [event_id]
    if day:
        sql += " AND substr(created_at, 1, 10) = ?"
        args.append(day)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
    return conn.execute(sql, args + [limit + 1, offset]).fetchall()


def delete_response(conn, response_id):
    cur = conn.execute("DELETE FROM responses WHERE id = ?", (response_id,))
    return cur.rowcount


# --- kiosk devices ---------------------------------------------------------
# Every device that opens a kiosk gets its own random key (kept on the device). Votes are
# accepted with that key even when the browser session has long expired, e.g. after days
# offline, and a device can resume its kiosk after a restart without the PIN.

def _hash(secret: str) -> str:
    import hashlib

    return hashlib.sha256(secret.encode()).hexdigest()


def create_device(conn, event_id, name):
    secret = secrets.token_urlsafe(24)
    cur = conn.execute(
        "INSERT INTO devices (event_id, name, secret_hash, created_at, last_seen) VALUES (?, ?, ?, ?, ?)",
        (event_id, name, _hash(secret), now_iso(), now_iso()),
    )
    return cur.lastrowid, secret


def device_for(conn, event_id, secret, include_revoked=False):
    """The device with this key for this event (active only, unless include_revoked), or None."""
    if not secret:
        return None
    row = conn.execute("SELECT * FROM devices WHERE event_id = ? AND secret_hash = ?",
                       (event_id, _hash(secret))).fetchone()
    if row and row["revoked"] and not include_revoked:
        return None
    return row


def touch_device(conn, device_id):
    conn.execute("UPDATE devices SET last_seen = ? WHERE id = ?", (now_iso(), device_id))


def revoke_device(conn, device_id):
    conn.execute("UPDATE devices SET revoked = 1, revoked_at = ? WHERE id = ? AND revoked = 0",
                 (now_iso(), device_id))


def count_devices(conn, event_id) -> int:
    return conn.execute("SELECT COUNT(*) FROM devices WHERE event_id = ?", (event_id,)).fetchone()[0]


def responses_without_device(conn, event_id, day=None) -> int:
    sql = "SELECT COUNT(*) FROM responses WHERE event_id = ? AND device_id IS NULL"
    args = [event_id]
    if day:
        sql += " AND substr(created_at, 1, 10) = ?"
        args.append(day)
    return conn.execute(sql, args).fetchone()[0]


def list_devices(conn, event_id, day=None):
    """Devices of an event with their number of ratings (optionally for one day)."""
    day_sql = " AND substr(r.created_at, 1, 10) = ?" if day else ""
    args = [day] if day else []
    return conn.execute(
        f"""SELECT d.*, (SELECT COUNT(*) FROM responses r WHERE r.device_id = d.id{day_sql}) AS n_responses
            FROM devices d WHERE d.event_id = ? ORDER BY d.revoked, d.created_at""",
        args + [event_id],
    ).fetchall()
