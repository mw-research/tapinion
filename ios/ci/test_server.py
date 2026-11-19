"""Tapinion for the simulator test: one smiley event (PIN 2468) on port 8752.
The database survives restarts (DB_PATH), so ratings collected offline can be synced back.
Writes the kiosk address to the file given as first argument."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DB_PATH", str(Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "tapinion-ios-test.sqlite3"))
os.environ.setdefault("SECRET_KEY", "ios-test")

from tapinion import db  # noqa: E402

db.init_db()
with db.session() as conn:
    if not db.list_events(conn):
        db.create_event(conn, "iOS-Test", "2026-11-19", "smiley", "", "", "de", "2468", None)
    token = db.list_events(conn)[0]["kiosk_token"]
Path(sys.argv[1]).write_text(f"http://127.0.0.1:8752/k/{token}\n")

import uvicorn  # noqa: E402

uvicorn.run("tapinion.main:app", host="0.0.0.0", port=8752, log_level="warning")
