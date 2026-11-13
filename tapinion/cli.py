# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command line tools.

    tapinion serve [--host 0.0.0.0] [--port 8000]   run the server
    tapinion desktop                               desktop app with window and browser
    tapinion create-user NAME --role admin         create a user (password asked)
    tapinion import-csv FILE [--dry-run]           import ratings from CSV
    tapinion demo                                  add demo events with ratings
"""
import argparse
import csv
import getpass
import random
import secrets
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

from . import db
from .security import hash_secret


def cmd_create_user(args):
    pw = getpass.getpass("Password (min. 10 characters): ")
    if len(pw) < 10 or pw != getpass.getpass("Repeat: "):
        sys.exit("Password too short or not identical.")
    db.init_db()
    with db.session() as conn:
        if db.get_user_by_name(conn, args.username):
            sys.exit("User exists already.")
        db.create_user(conn, args.username, hash_secret(pw), args.role, args.lang)
    print(f"User {args.username} ({args.role}) created.")


def _value(raw):
    raw = (raw or "").strip().lower()
    if raw.isdigit() and 0 <= int(raw) <= 10:
        return "nps", str(int(raw))
    aliases = {"happy": "happy", "neutral": "neutral", "unhappy": "unhappy",
               "zufrieden": "happy", "unzufrieden": "unhappy", "good": "happy", "bad": "unhappy"}
    return ("smiley", aliases[raw]) if raw in aliases else (None, None)


def cmd_import_csv(args):
    """CSV with the columns event;date;time;rating (header row; ',' or ';' as separator).

    Ratings: 0-10, or happy / neutral / unhappy. One closed event is created per
    event name and rating type.
    """
    with open(args.file, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(2048)
        fh.seek(0)
        rows = list(csv.reader(fh, dialect=csv.Sniffer().sniff(sample, delimiters=";,")))
    groups, skipped = defaultdict(list), 0
    for row in rows[1:]:
        if len(row) < 4:
            skipped += 1
            continue
        name, day, time_, raw = (c.strip() for c in row[:4])
        mode, value = _value(raw)
        try:
            when = datetime.fromisoformat(f"{day} {time_ or '00:00:00'}")
        except ValueError:
            mode = None
        if not (name and mode):
            skipped += 1
            continue
        groups[(name, mode)].append((when.isoformat(sep=" "), value))
    db.init_db()
    with db.session() as conn:
        for (name, mode), items in sorted(groups.items()):
            first_day = min(w for w, _ in items)[:10]
            print(f"{first_day}  {mode:7} {len(items):5} ratings  -> {name}")
            if args.dry_run:
                continue
            eid = db.create_event(conn, name, first_day, mode, "", "", "de", None, None, active=0)
            for when, value in items:
                db.add_response(conn, eid, value, when)
    total = sum(len(v) for v in groups.values())
    note = " (dry run, nothing written)" if args.dry_run else ""
    print(f"{total} ratings in {len(groups)} events{note}; {skipped} rows skipped.")


def cmd_demo(args):
    """Two demo events with plausible ratings, for trying things out."""
    db.init_db()
    rnd = random.Random(7)
    today = date.today()
    with db.session() as conn:
        for name, mode, offset, n in (("Demo: Workshop", "nps", 3, 60), ("Demo: Open day", "smiley", 1, 80)):
            day = today - timedelta(days=offset)
            eid = db.create_event(conn, name, day.isoformat(), mode, "", "", "de", "1234", None)
            for _ in range(n):
                when = datetime.combine(day, datetime.min.time()) + timedelta(
                    hours=rnd.choice([9, 10, 10, 11, 13, 14, 14, 15]), minutes=rnd.randrange(60), seconds=rnd.randrange(60))
                if mode == "nps":
                    value = str(min(10, max(0, round(rnd.gauss(8, 2)))))
                else:
                    value = rnd.choices(["happy", "neutral", "unhappy"], weights=[6, 3, 1])[0]
                db.add_response(conn, eid, value, when.isoformat(sep=" "))
    print("Demo events created (kiosk PIN 1234).")


def cmd_serve(args):
    import uvicorn

    uvicorn.run("tapinion.main:app", host=args.host, port=args.port, proxy_headers=True,
                forwarded_allow_ips=args.forwarded_allow_ips)


def cmd_desktop(_args):
    from .desktop import main as desktop_main

    desktop_main()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tapinion", description="Tapinion – tap your opinion.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the server")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--forwarded-allow-ips", default="127.0.0.1",
                   help="proxies whose X-Forwarded-* headers are trusted ('*' behind a reverse proxy)")
    s.set_defaults(func=cmd_serve)
    sub.add_parser("desktop", help="desktop app (window, browser, LAN access)").set_defaults(func=cmd_desktop)
    u = sub.add_parser("create-user", help="create a user")
    u.add_argument("username")
    u.add_argument("--role", choices=db.ROLES, default="organizer")
    u.add_argument("--lang", choices=["de", "en"])
    u.set_defaults(func=cmd_create_user)
    i = sub.add_parser("import-csv", help="import ratings from CSV (event;date;time;rating)")
    i.add_argument("file")
    i.add_argument("--dry-run", action="store_true")
    i.set_defaults(func=cmd_import_csv)
    sub.add_parser("demo", help="add demo events").set_defaults(func=cmd_demo)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
