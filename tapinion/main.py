# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tapinion web app: kiosk, evaluation, reports, events, users and settings."""
import csv
import html
import io
import ipaddress
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import __version__, branding, db, i18n, netinfo, stats
from .perms import can
from .security import Throttle, csrf_token, hash_secret, verify_secret

BASE = Path(__file__).parent
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
PIN_RE = re.compile(r"\d{4,8}")
USERNAME_RE = re.compile(r"[A-Za-z0-9._@-]{3,64}")
MIN_PASSWORD = 10


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    bootstrap_admin()
    yield


app = FastAPI(title="Tapinion", version=__version__, docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=lifespan)


@app.middleware("http")
async def no_store(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith(("/static/", "/branding/")):
        response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY") or "dev-only-change-me",
    session_cookie="tapinion_session",
    max_age=12 * 3600,
    same_site="lax",
    https_only=os.environ.get("COOKIE_SECURE", "0") == "1",
)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.globals.update(version=__version__, languages=i18n.languages)

login_throttle = Throttle(limit=5, window=300)
pin_throttle = Throttle(limit=5, window=120)


def bootstrap_admin():
    """Create the first admin from ADMIN_USER / ADMIN_PASSWORD if there are no users yet."""
    user, pw = os.environ.get("ADMIN_USER"), os.environ.get("ADMIN_PASSWORD")
    if not (user and pw):
        return
    with db.session() as conn:
        if not db.count_users(conn):
            db.create_user(conn, user, hash_secret(pw), "admin")


# --- request helpers -------------------------------------------------------

class Redirect(Exception):
    def __init__(self, url):
        self.url = url


@app.exception_handler(Redirect)
def redirect_handler(request: Request, exc: Redirect):
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": exc.url})
    return RedirectResponse(exc.url, status_code=303)


def current_user(request):
    uid = request.session.get("uid")
    if not uid:
        return None
    with db.session() as conn:
        return db.get_user(conn, uid)


def lang_of(request, user=None) -> str:
    user = user if user is not None else current_user(request)
    for candidate in ((user["lang"] if user else None), request.session.get("lang"),
                      i18n.from_accept_language(request.headers.get("accept-language"))):
        if candidate in i18n.languages():
            return candidate
    return i18n.default_lang()


def tr(request, key, **kw):
    return i18n.translate(lang_of(request), key, **kw)


def render(request, name, status_code=200, **ctx):
    user = ctx["user"] if "user" in ctx else current_user(request)
    lang = ctx.pop("lang", None) or lang_of(request, user)
    with db.session() as conn:
        brand = branding.get(conn)
    ctx.update(
        user=user, lang=lang, brand=brand, csrf=csrf_token(request.session),
        t=lambda key, **kw: i18n.translate(lang, key, **kw),
        can=lambda perm: can(user, perm),
    )
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def require(request, perm=None):
    user = current_user(request)
    if not user:
        raise Redirect("/login?next=" + request.url.path)
    if perm and not can(user, perm):
        raise HTTPException(403, tr(request, "error.forbidden"))
    return user


async def checked_form(request):
    """Read the form and verify the CSRF token (form field or HX header)."""
    form = await request.form()
    sent = request.headers.get("X-CSRF-Token") or form.get("csrf")
    if not sent or not secrets.compare_digest(str(sent), str(request.session.get("csrf", ""))):
        raise HTTPException(400, tr(request, "error.session_expired"))
    return form


def form_errors(request, errors, target="#form-errors"):
    resp = render(request, "_form_errors.html", 422, errors=errors)
    resp.headers.update({"HX-Retarget": target, "HX-Reswap": "innerHTML"})
    return resp


def is_loopback(request) -> bool:
    host = request.client.host if request.client else ""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in ("localhost", "testclient")


def visible_event(request, user, event_id):
    """An event the user may see; organizers only see open events."""
    with db.session() as conn:
        event = db.get_event(conn, event_id)
    if not event or (not can(user, "events.view_all") and not event["active"]):
        raise HTTPException(404, tr(request, "error.event_not_found"))
    return event


templates.env.globals["question_of"] = i18n.question_of


# --- setup, login, language ------------------------------------------------

@app.get("/", include_in_schema=False)
def index(request: Request):
    with db.session() as conn:
        if not db.count_users(conn):
            return RedirectResponse("/setup", status_code=303)
    return RedirectResponse("/dashboard" if current_user(request) else "/login", status_code=303)


def setup_allowed(request, token=None) -> bool:
    expected = os.environ.get("SETUP_TOKEN")
    if expected and token and secrets.compare_digest(token, expected):
        return True
    return is_loopback(request)


@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request, token: str | None = None, step: int = 1):
    """Wizard steps 1 (language) and 2 (administrator account), before anyone exists."""
    with db.session() as conn:
        if db.count_users(conn):
            return RedirectResponse("/login", status_code=303)
    return render(request, "setup.html", user=None, allowed=setup_allowed(request, token), token=token or "",
                  step=2 if step == 2 else 1, error=None)


@app.post("/setup", response_class=HTMLResponse)
async def setup_save(request: Request):
    form = await checked_form(request)
    token = form.get("token") or None
    with db.session() as conn:
        if db.count_users(conn):
            return RedirectResponse("/login", status_code=303)
    if not setup_allowed(request, token):
        raise HTTPException(403, tr(request, "setup.not_allowed"))
    username, password = form.get("username", "").strip(), form.get("password", "")
    lang = lang_of(request)
    error = None
    if not USERNAME_RE.fullmatch(username):
        error = i18n.translate(lang, "users.error_username")
    elif len(password) < MIN_PASSWORD:
        error = i18n.translate(lang, "error.password_short", n=MIN_PASSWORD)
    elif password != form.get("password2", ""):
        error = i18n.translate(lang, "error.password_mismatch")
    if error:
        return render(request, "setup.html", 400, user=None, allowed=True, token=token or "", step=2, error=error)
    with db.session() as conn:
        uid = db.create_user(conn, username, hash_secret(password), "admin", lang)
    request.session.clear()
    request.session.update(uid=uid, lang=lang)
    return RedirectResponse("/welcome?step=3", status_code=303)


@app.get("/welcome", response_class=HTMLResponse)
def welcome(request: Request, step: int = 3, event_id: int | None = None):
    """Wizard steps 3 (look), 4 (first event) and 5 (connect a tablet), for administrators."""
    user = require(request, "settings.manage")
    step = step if step in (3, 4, 5) else 3
    ctx = {"step": step, "errors": [], "suggested_pin": f"{secrets.randbelow(9000) + 1000}",
           "today": date.today().isoformat()}
    if step == 5:
        with db.session() as conn:
            event = db.get_event(conn, event_id) if event_id else None
        if event:
            url = f"{netinfo.public_base(request)}/k/{event['kiosk_token']}"
            ctx.update(event=event, url=url, svg=netinfo.qr_svg(url))
    return render(request, "welcome.html", user=user, **ctx)


@app.post("/welcome/appearance", response_class=HTMLResponse)
async def welcome_appearance(request: Request):
    user = require(request, "settings.manage")
    form = await checked_form(request)
    errors = []
    color = form.get("color_primary", "").strip()
    if not branding.COLOR_RE.fullmatch(color):
        errors.append(tr(request, "settings.error_color", value=color))
    upload = form.get("logo")
    logo_data = None
    if upload is not None and getattr(upload, "filename", ""):
        logo_data = await upload.read()
        if len(logo_data) > branding.MAX_LOGO_BYTES:
            errors.append(tr(request, "settings.error_logo_size"))
        elif not branding.sniff_image(logo_data):
            errors.append(tr(request, "settings.error_logo_type"))
    if errors:
        return render(request, "welcome.html", 400, user=user, step=3, errors=errors)
    with db.session() as conn:
        db.set_setting(conn, "brand_name", form.get("brand_name", "").strip()[:60])
        db.set_setting(conn, "color_primary", color.lower())
        if logo_data:
            db.set_asset(conn, "logo", branding.sniff_image(logo_data), logo_data)
    return RedirectResponse("/welcome?step=4", status_code=303)


@app.post("/welcome/event", response_class=HTMLResponse)
async def welcome_event(request: Request):
    user = require(request, "settings.manage")
    form = await checked_form(request)
    data, errors = read_event_form(request, form, require_pin=True)
    if errors:
        return render(request, "welcome.html", 400, user=user, step=4, errors=errors,
                      suggested_pin=form.get("pin", ""), today=date.today().isoformat())
    with db.session() as conn:
        eid = db.create_event(conn, data["name"], data["event_date"], data["mode"], "", "", data["kiosk_lang"],
                              data["kiosk_pin"], user["id"])
    return RedirectResponse(f"/welcome?step=5&event_id={eid}", status_code=303)


def open_kiosks(conn):
    return [e for e in db.list_events(conn, only_active=True) if e["kiosk_pin"]]


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/dashboard"):
    with db.session() as conn:
        if not db.count_users(conn):
            return RedirectResponse("/setup", status_code=303)
        kiosks = open_kiosks(conn) if branding.get(conn)["show_open_events"] else []
    # Whoever leaves a kiosk for the login page needs the PIN to get back in.
    request.session.pop("kiosks", None)
    return render(request, "login.html", user=None, next=next, error=None, kiosks=kiosks)


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request):
    form = await checked_form(request)
    username, password = form.get("username", "").strip(), form.get("password", "")
    nxt = form.get("next") or "/dashboard"
    if not nxt.startswith("/") or nxt.startswith("//") or nxt.startswith("/\\"):
        nxt = "/dashboard"
    key = request.client.host if request.client else "?"
    with db.session() as conn:
        kiosks = open_kiosks(conn) if branding.get(conn)["show_open_events"] else []
        user = db.get_user_by_name(conn, username)
    if login_throttle.blocked(key):
        return render(request, "login.html", 429, user=None, next=nxt, kiosks=kiosks,
                      error=tr(request, "login.error_throttled"))
    if not user or not verify_secret(password, user["pw_hash"]):
        login_throttle.fail(key)
        return render(request, "login.html", 401, user=None, next=nxt, kiosks=kiosks,
                      error=tr(request, "login.error_credentials"))
    login_throttle.reset(key)
    lang = request.session.get("lang")
    request.session.clear()
    request.session["uid"] = user["id"]
    if lang:
        request.session["lang"] = lang
    return RedirectResponse(nxt, status_code=303)


@app.post("/logout")
async def logout(request: Request):
    await checked_form(request)
    lang = request.session.get("lang")
    request.session.clear()
    if lang:
        request.session["lang"] = lang
    raise Redirect("/login")


@app.post("/lang")
async def set_language(request: Request):
    form = await checked_form(request)
    lang = form.get("lang")
    if lang in i18n.languages():
        request.session["lang"] = lang
        user = current_user(request)
        if user:
            with db.session() as conn:
                conn.execute("UPDATE users SET lang = ? WHERE id = ?", (lang, user["id"]))
    back = form.get("back") or "/"
    if not back.startswith("/") or back.startswith("//") or back.startswith("/\\"):
        back = "/"
    raise Redirect(back)


@app.get("/account", response_class=HTMLResponse)
def account_page(request: Request):
    require(request)
    return render(request, "account.html", message=None, error=None)


@app.post("/account", response_class=HTMLResponse)
async def account_change(request: Request):
    user = require(request)
    form = await checked_form(request)
    if not verify_secret(form.get("old", ""), user["pw_hash"]):
        return render(request, "account.html", 400, message=None, error=tr(request, "account.error_old"))
    new = form.get("new", "")
    if len(new) < MIN_PASSWORD:
        return render(request, "account.html", 400, message=None,
                      error=tr(request, "error.password_short", n=MIN_PASSWORD))
    with db.session() as conn:
        conn.execute("UPDATE users SET pw_hash = ? WHERE id = ?", (hash_secret(new), user["id"]))
    return render(request, "account.html", message=tr(request, "account.changed"), error=None)


# --- branding --------------------------------------------------------------

@app.get("/branding/logo")
def logo(request: Request):
    with db.session() as conn:
        asset = db.get_asset(conn, "logo")
    if not asset:
        return Response((BASE / "static" / "logo.svg").read_bytes(), media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=300"})
    return Response(asset["data"], media_type=asset["mime"], headers={
        "Cache-Control": "public, max-age=31536000" if request.query_params.get("v") else "public, max-age=300",
        # an uploaded SVG must never run scripts when opened directly
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
    })


@app.get("/manifest.webmanifest")
def manifest(request: Request):
    with db.session() as conn:
        brand = branding.get(conn)
    return JSONResponse({
        "name": brand["name"], "short_name": brand["name"][:12], "start_url": "/", "scope": "/",
        "display": "fullscreen", "orientation": "any", "background_color": "#ffffff",
        "theme_color": brand["primary"],
        "icons": [{"src": f"/static/icons/icon-{s}.png", "sizes": f"{s}x{s}", "type": "image/png"}
                  for s in (192, 512)],
    }, media_type="application/manifest+json")


# --- dashboard -------------------------------------------------------------

def dashboard_context(conn, user, event_id, day):
    events = db.list_events(conn, only_active=not can(user, "events.view_all"))
    event = next((e for e in events if e["id"] == event_id), None) if event_id else (events[0] if events else None)
    if not event:
        return {"events": events, "event": None}
    days = db.response_days(conn, event["id"])
    day = day if day in days else None
    rows = db.responses_for(conn, event["id"], day)
    ctx = {"events": events, "event": event, "days": days, "day": day,
           "result": stats.result_for(event["mode"], [r["value"] for r in rows])}
    if can(user, "dashboard.details"):
        ctx["hourly"] = stats.hourly(rows)
    return ctx


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, event_id: int | None = None, day: str | None = None, live: int = 0):
    user = require(request, "dashboard.view")
    with db.session() as conn:
        ctx = dashboard_context(conn, user, event_id, day)
    ctx["live"] = bool(live)
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "panel":
        return render(request, "_panel.html", user=user, **ctx)
    return render(request, "dashboard.html", user=user, **ctx)


PAGE = 50


@app.get("/dashboard/responses", response_class=HTMLResponse)
def responses_fragment(request: Request, event_id: int, day: str | None = None, offset: int = 0):
    user = require(request, "dashboard.details")
    event = visible_event(request, user, event_id)
    with db.session() as conn:
        rows = db.responses_page(conn, event_id, day if day and DATE_RE.fullmatch(day) else None,
                                 max(offset, 0), PAGE)
    return render(request, "_responses.html", user=user, event=event, rows=rows[:PAGE], more=len(rows) > PAGE,
                  next_offset=offset + PAGE, day=day or "", first=offset <= 0)


@app.post("/responses/{response_id}/delete", response_class=HTMLResponse)
async def response_delete(request: Request, response_id: int):
    require(request, "responses.delete")
    await checked_form(request)
    with db.session() as conn:
        db.delete_response(conn, response_id)
    resp = HTMLResponse("")
    resp.headers["HX-Trigger"] = "responses-changed"
    return resp


@app.get("/dashboard/export.csv")
def export_csv(request: Request, event_id: int, day: str | None = None):
    user = require(request, "export")
    event = visible_event(request, user, event_id)
    with db.session() as conn:
        rows = db.responses_for(conn, event_id, day if day and DATE_RE.fullmatch(day) else None)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([tr(request, "csv.event"), tr(request, "csv.date"), tr(request, "csv.time"), tr(request, "csv.value")])
    for r in rows:
        w.writerow([event["name"], r["created_at"][:10], r["created_at"][11:], r["value"]])
    fname = safe_filename(event["name"]) + (f"_{day}" if day else "") + ".csv"
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


def safe_filename(name):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:60] or "tapinion"


# --- PDF reports -----------------------------------------------------------

def report_filters(date_from, date_to, mode):
    date_from = date_from if date_from and DATE_RE.fullmatch(date_from) else None
    date_to = date_to if date_to and DATE_RE.fullmatch(date_to) else None
    mode = mode if mode in ("nps", "smiley") else None
    return date_from, date_to, mode


def pdf_response(content, name):
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{safe_filename(name)}.pdf"'})


@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request):
    user = require(request, "reports")
    with db.session() as conn:
        events = db.list_events(conn)
        selection = db.select_events(conn)
    return render(request, "reports.html", user=user, events=events, selection=selection)


@app.get("/reports/preview", response_class=HTMLResponse)
def reports_preview(request: Request, date_from: str | None = None, date_to: str | None = None,
                    mode: str | None = None):
    user = require(request, "reports")
    with db.session() as conn:
        selection = db.select_events(conn, *report_filters(date_from, date_to, mode))
    return render(request, "_report_preview.html", user=user, selection=selection)


@app.get("/reports/overview.pdf")
def report_overview(request: Request, date_from: str | None = None, date_to: str | None = None,
                    mode: str | None = None, details: int = 0):
    user = require(request, "reports")
    f, to, m = report_filters(date_from, date_to, mode)
    from . import reports  # loaded on demand: fpdf2/Pillow need ~37 MiB
    content = reports.overview_report(lang_of(request, user), f, to, m, details=bool(details), user=user)
    return pdf_response(content, tr(request, "report.file_overview") + (f"_{f}" if f else "") + (f"_{to}" if to else ""))


@app.get("/reports/event/{event_id}.pdf")
def report_event(request: Request, event_id: int, day: str | None = None):
    user = require(request, "reports")
    event = visible_event(request, user, event_id)
    day = day if day and DATE_RE.fullmatch(day) else None
    from . import reports
    content = reports.event_report(lang_of(request, user), event_id, day, user=user)
    return pdf_response(content, tr(request, "report.file_event") + "_" + event["name"] + (f"_{day}" if day else ""))


# --- events ----------------------------------------------------------------

def event_row(request, user, event_id, flash=None, status_code=200):
    with db.session() as conn:
        event = db.get_event(conn, event_id)
    return render(request, "_event_row.html", status_code, user=user, e=event, flash=flash)


def read_event_form(request, form, require_pin):
    lang = lang_of(request)
    data = {
        "name": form.get("name", "").strip()[:120],
        "event_date": form.get("event_date") or date.today().isoformat(),
        "mode": form.get("mode"),
        "question_de": form.get("question_de", "").strip()[:240],
        "question_en": form.get("question_en", "").strip()[:240],
        "kiosk_lang": form.get("kiosk_lang") if form.get("kiosk_lang") in ("de", "en") else lang if lang in ("de", "en") else "en",
    }
    pin = form.get("pin", "").strip()
    errors = []
    if not data["name"]:
        errors.append(i18n.translate(lang, "events.error_name"))
    if data["mode"] not in ("nps", "smiley"):
        errors.append(i18n.translate(lang, "events.error_mode"))
    if not DATE_RE.fullmatch(data["event_date"]):
        errors.append(i18n.translate(lang, "events.error_date"))
    if pin or require_pin:
        if not PIN_RE.fullmatch(pin):
            errors.append(i18n.translate(lang, "events.error_pin"))
        data["kiosk_pin"] = pin
    return data, errors


@app.get("/events", response_class=HTMLResponse)
def events_page(request: Request):
    user = require(request, "events.view")
    with db.session() as conn:
        events = db.list_events(conn, only_active=not can(user, "events.view_all"))
    return render(request, "events.html", user=user, events=events, today=date.today().isoformat())


@app.post("/events", response_class=HTMLResponse)
async def event_create(request: Request):
    user = require(request, "events.create")
    form = await checked_form(request)
    data, errors = read_event_form(request, form, require_pin=True)
    if errors:
        return form_errors(request, errors)
    with db.session() as conn:
        eid = db.create_event(conn, data["name"], data["event_date"], data["mode"], data["question_de"],
                              data["question_en"], data["kiosk_lang"], data["kiosk_pin"], user["id"])
    resp = event_row(request, user, eid, flash="new")
    resp.headers["HX-Trigger"] = "event-created"
    return resp


@app.get("/events/{event_id}/row", response_class=HTMLResponse)
def event_row_view(request: Request, event_id: int):
    user = require(request, "events.view")
    visible_event(request, user, event_id)
    return event_row(request, user, event_id)


@app.get("/events/{event_id}/edit", response_class=HTMLResponse)
def event_edit_form(request: Request, event_id: int):
    user = require(request, "events.edit")
    event = visible_event(request, user, event_id)
    return render(request, "_event_edit.html", user=user, e=event)


@app.post("/events/{event_id}", response_class=HTMLResponse)
async def event_save(request: Request, event_id: int):
    user = require(request, "events.edit")
    event = visible_event(request, user, event_id)
    form = await checked_form(request)
    data, errors = read_event_form(request, form, require_pin=False)
    if event["n_responses"] and data["mode"] != event["mode"]:
        errors.append(tr(request, "events.error_mode_locked"))
    if errors:
        return form_errors(request, errors, target=f"#edit-errors-{event_id}")
    with db.session() as conn:
        db.update_event(conn, event_id, **data)
    return event_row(request, user, event_id, flash=tr(request, "events.saved"))


@app.post("/events/{event_id}/toggle", response_class=HTMLResponse)
async def event_toggle(request: Request, event_id: int):
    user = require(request, "events.edit")
    await checked_form(request)
    event = visible_event(request, user, event_id)
    with db.session() as conn:
        db.update_event(conn, event_id, active=0 if event["active"] else 1)
    return event_row(request, user, event_id)


@app.post("/events/{event_id}/relink", response_class=HTMLResponse)
async def event_relink(request: Request, event_id: int):
    user = require(request, "events.edit")
    await checked_form(request)
    visible_event(request, user, event_id)
    with db.session() as conn:
        db.update_event(conn, event_id, kiosk_token=db.new_token())
    return event_row(request, user, event_id, flash=tr(request, "events.relinked"))


@app.post("/events/{event_id}/delete", response_class=HTMLResponse)
async def event_delete(request: Request, event_id: int):
    require(request, "events.delete")
    await checked_form(request)
    with db.session() as conn:
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    return HTMLResponse("")


@app.get("/events/{event_id}/pin", response_class=HTMLResponse)
def event_pin(request: Request, event_id: int, edit: int = 0):
    user = require(request, "pin.view")
    event = visible_event(request, user, event_id)
    return render(request, "_event_pin.html", user=user, e=event, edit=bool(edit) and can(user, "pin.edit"),
                  error=None)


@app.post("/events/{event_id}/pin", response_class=HTMLResponse)
async def event_pin_save(request: Request, event_id: int):
    user = require(request, "pin.edit")
    event = visible_event(request, user, event_id)
    pin = (await checked_form(request)).get("pin", "").strip()
    if not PIN_RE.fullmatch(pin):
        return render(request, "_event_pin.html", user=user, e=event, edit=True, error=tr(request, "events.error_pin"))
    with db.session() as conn:
        db.update_event(conn, event_id, kiosk_pin=pin)
        event = db.get_event(conn, event_id)
    return render(request, "_event_pin.html", user=user, e=event, edit=False, error=None,
                  message=tr(request, "events.pin_changed"))


@app.get("/events/{event_id}/qr", response_class=HTMLResponse)
def event_qr(request: Request, event_id: int):
    user = require(request, "kiosk.start")
    event = visible_event(request, user, event_id)
    url = f"{netinfo.public_base(request)}/k/{event['kiosk_token']}"
    return render(request, "_event_qr.html", user=user, e=event, url=url, svg=netinfo.qr_svg(url))


@app.get("/events/{event_id}/kiosk")
def event_kiosk(request: Request, event_id: int):
    """Start the kiosk on this device: the login ends, the kiosk is unlocked for this browser."""
    user = require(request, "kiosk.start")
    event = visible_event(request, user, event_id)
    lang = lang_of(request, user)
    request.session.clear()
    request.session.update(lang=lang, kiosks=[event["kiosk_token"]])
    return RedirectResponse(f"/k/{event['kiosk_token']}", status_code=303)


# --- kiosk -----------------------------------------------------------------

def kiosk_event(request, token):
    with db.session() as conn:
        event = db.get_event_by_token(conn, token)
    if not event:
        raise HTTPException(404, tr(request, "kiosk.unknown"))
    return event


def kiosk_unlocked(request, token) -> bool:
    return token in request.session.get("kiosks", [])


def kiosk_lang(request, event, lang=None):
    return lang if lang in ("de", "en") else event["kiosk_lang"]


def check_pin(request, event, pin):
    """None if the PIN is right, else an error text."""
    key = f"{event['id']}:{request.client.host if request.client else '?'}"
    if pin_throttle.blocked(key):
        return "kiosk.pin_locked"
    if not event["kiosk_pin"] or not secrets.compare_digest(pin, event["kiosk_pin"]):
        pin_throttle.fail(key)
        return "kiosk.pin_wrong"
    pin_throttle.reset(key)
    return None


@app.get("/k/{token}", response_class=HTMLResponse)
def kiosk(request: Request, token: str, lang: str | None = None):
    event = kiosk_event(request, token)
    klang = kiosk_lang(request, event, lang)
    if not kiosk_unlocked(request, token):
        return render(request, "kiosk_unlock.html", user=None, e=event, lang=klang, error=None)
    return render(request, "kiosk.html", user=None, e=event, lang=klang)


@app.post("/k/{token}/unlock", response_class=HTMLResponse)
async def kiosk_unlock(request: Request, token: str):
    event = kiosk_event(request, token)
    form = await request.form()
    klang = kiosk_lang(request, event, form.get("lang"))
    error = check_pin(request, event, form.get("pin", ""))
    if error:
        return render(request, "_kiosk_pinpad.html", user=None, e=event, lang=klang, mode="unlock",
                      error=i18n.translate(klang, error))
    request.session.pop("uid", None)  # a kiosk device is never logged in
    request.session["kiosks"] = list(dict.fromkeys(request.session.get("kiosks", []) + [token]))[-5:]
    return Response(status_code=204, headers={"HX-Redirect": f"/k/{token}?lang={klang}"})


@app.get("/k/{token}/form", response_class=HTMLResponse)
def kiosk_form(request: Request, token: str, lang: str | None = None):
    event = kiosk_event(request, token)
    if not kiosk_unlocked(request, token):
        raise Redirect(f"/k/{token}")
    return render(request, "_kiosk_vote.html", user=None, e=event, lang=kiosk_lang(request, event, lang))


def parse_client_time(ts):
    """Timestamp of a vote that was queued offline on the device; accepted within the last 14 days."""
    try:
        when = datetime.fromisoformat(ts).replace(microsecond=0, tzinfo=None)
    except (TypeError, ValueError):
        return None
    now = datetime.now()
    if now - timedelta(days=14) <= when <= now + timedelta(minutes=5):
        return when.isoformat(sep=" ")
    return None


@app.post("/k/{token}/vote", response_class=HTMLResponse)
async def kiosk_vote(request: Request, token: str):
    event = kiosk_event(request, token)
    if not kiosk_unlocked(request, token):
        raise HTTPException(403, tr(request, "kiosk.locked"))
    form = await request.form()
    klang = kiosk_lang(request, event, form.get("lang"))
    value = form.get("value", "")
    allowed = db.NPS_VALUES if event["mode"] == "nps" else db.SMILEY_VALUES
    if not event["active"]:
        return render(request, "_kiosk_vote.html", user=None, e=event, lang=klang)
    if value not in allowed:
        raise HTTPException(400, i18n.translate(klang, "kiosk.invalid"))
    with db.session() as conn:
        db.add_response(conn, event["id"], value, parse_client_time(form.get("ts")))
    if form.get("queued"):
        return Response(status_code=204)
    return render(request, "_kiosk_thanks.html", user=None, e=event, lang=klang)


@app.get("/k/{token}/exit", response_class=HTMLResponse)
def kiosk_exit_pad(request: Request, token: str, lang: str | None = None):
    event = kiosk_event(request, token)
    return render(request, "_kiosk_pinpad.html", user=None, e=event, lang=kiosk_lang(request, event, lang),
                  mode="exit", error=None)


@app.post("/k/{token}/exit", response_class=HTMLResponse)
async def kiosk_exit(request: Request, token: str):
    event = kiosk_event(request, token)
    form = await request.form()
    klang = kiosk_lang(request, event, form.get("lang"))
    error = check_pin(request, event, form.get("pin", ""))
    if error:
        return render(request, "_kiosk_pinpad.html", user=None, e=event, lang=klang, mode="exit",
                      error=i18n.translate(klang, error))
    request.session["kiosks"] = [k for k in request.session.get("kiosks", []) if k != token]
    return Response(status_code=204, headers={"HX-Redirect": "/login"})


# --- settings: appearance and users (admin) --------------------------------

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, tab: str = "appearance"):
    user = require(request, "settings.manage")
    with db.session() as conn:
        users = db.list_users(conn)
    return render(request, "settings.html", user=user, tab=tab if tab in ("appearance", "users") else "appearance",
                  users=users, message=None, errors=[])


@app.post("/settings/appearance", response_class=HTMLResponse)
async def settings_appearance(request: Request):
    user = require(request, "settings.manage")
    form = await checked_form(request)
    errors = []
    name = form.get("brand_name", "").strip()[:60]
    colors = {k: form.get(k, "").strip() for k in ("color_primary", "color_accent")}
    for key, value in colors.items():
        if not branding.COLOR_RE.fullmatch(value):
            errors.append(tr(request, "settings.error_color", value=value))
    upload = form.get("logo")
    logo_data = None
    if upload is not None and getattr(upload, "filename", ""):
        logo_data = await upload.read()
        if len(logo_data) > branding.MAX_LOGO_BYTES:
            errors.append(tr(request, "settings.error_logo_size"))
        elif not branding.sniff_image(logo_data):
            errors.append(tr(request, "settings.error_logo_type"))
    if not errors:
        with db.session() as conn:
            db.set_setting(conn, "brand_name", name)
            for key, value in colors.items():
                db.set_setting(conn, key, value.lower())
            db.set_setting(conn, "show_open_events", "1" if form.get("show_open_events") else "0")
            if form.get("remove_logo"):
                db.delete_asset(conn, "logo")
            elif logo_data:
                db.set_asset(conn, "logo", branding.sniff_image(logo_data), logo_data)
    with db.session() as conn:
        users = db.list_users(conn)
    return render(request, "settings.html", 400 if errors else 200, user=user, tab="appearance", users=users,
                  errors=errors, message=None if errors else tr(request, "settings.saved"))


@app.post("/settings/appearance/reset", response_class=HTMLResponse)
async def settings_reset(request: Request):
    require(request, "settings.manage")
    await checked_form(request)
    with db.session() as conn:
        for key in branding.DEFAULTS:
            db.set_setting(conn, key, None)
        db.delete_asset(conn, "logo")
    raise Redirect("/settings")


@app.post("/settings/users", response_class=HTMLResponse)
async def user_create(request: Request):
    user = require(request, "users.manage")
    form = await checked_form(request)
    username, password, role = form.get("username", "").strip(), form.get("password", ""), form.get("role")
    lang = form.get("lang") if form.get("lang") in i18n.languages() else None
    errors = []
    if not USERNAME_RE.fullmatch(username):
        errors.append(tr(request, "users.error_username"))
    if len(password) < MIN_PASSWORD:
        errors.append(tr(request, "error.password_short", n=MIN_PASSWORD))
    if role not in db.ROLES:
        errors.append(tr(request, "users.error_role"))
    with db.session() as conn:
        if not errors and db.get_user_by_name(conn, username):
            errors.append(tr(request, "users.error_exists"))
        if errors:
            return form_errors(request, errors)
        uid = db.create_user(conn, username, hash_secret(password), role, lang)
        u = db.get_user(conn, uid)
    resp = render(request, "_user_row.html", user=user, u=u, flash=True)
    resp.headers["HX-Trigger"] = "user-created"
    return resp


def managed_user(request, me, user_id):
    with db.session() as conn:
        u = db.get_user(conn, user_id)
    if not u:
        raise HTTPException(404)
    return u


@app.post("/settings/users/{user_id}/role", response_class=HTMLResponse)
async def user_role(request: Request, user_id: int):
    me = require(request, "users.manage")
    role = (await checked_form(request)).get("role")
    u = managed_user(request, me, user_id)
    if role not in db.ROLES:
        raise HTTPException(400, tr(request, "users.error_role"))
    with db.session() as conn:
        if u["role"] == "admin" and role != "admin" and db.count_admins(conn) <= 1:
            raise HTTPException(400, tr(request, "users.error_last_admin"))
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        u = db.get_user(conn, user_id)
    return render(request, "_user_row.html", user=me, u=u, flash=True)


@app.post("/settings/users/{user_id}/password", response_class=HTMLResponse)
async def user_password(request: Request, user_id: int):
    me = require(request, "users.manage")
    password = (await checked_form(request)).get("password", "")
    u = managed_user(request, me, user_id)
    if len(password) < MIN_PASSWORD:
        raise HTTPException(400, tr(request, "error.password_short", n=MIN_PASSWORD))
    with db.session() as conn:
        conn.execute("UPDATE users SET pw_hash = ? WHERE id = ?", (hash_secret(password), user_id))
    return render(request, "_user_row.html", user=me, u=u, flash=True)


@app.post("/settings/users/{user_id}/delete", response_class=HTMLResponse)
async def user_delete(request: Request, user_id: int):
    me = require(request, "users.manage")
    await checked_form(request)
    if user_id == me["id"]:
        raise HTTPException(400, tr(request, "users.error_self"))
    with db.session() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return HTMLResponse("")


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok", "version": __version__}


@app.exception_handler(HTTPException)
def http_error(request: Request, exc: HTTPException):
    detail = html.escape(str(exc.detail))
    if request.headers.get("HX-Request"):
        return HTMLResponse(f'<div class="toast error" role="alert">{detail}</div>', status_code=exc.status_code,
                            headers={"HX-Retarget": "#toasts", "HX-Reswap": "beforeend"})
    return render(request, "error.html", exc.status_code, detail=exc.detail, code=exc.status_code)
