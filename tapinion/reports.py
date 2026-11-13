# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""PDF reports: one event, or an overview of many events (optionally with one page per event)."""
import io
from datetime import datetime
from pathlib import Path

from fpdf import FPDF, XPos, YPos

from . import branding, db, i18n, stats

DEFAULT_LOGO = Path(__file__).parent / "static" / "icons" / "icon-512.png"

TEXT = (23, 32, 43)
MUTED = (92, 104, 120)
LINE = (221, 227, 234)
COLORS = {
    "promoters": (46, 158, 91), "passives": (167, 177, 189), "detractors": (214, 69, 69),
    "happy": (46, 158, 91), "neutral": (240, 180, 41), "unhappy": (214, 69, 69),
}

# The built-in PDF fonts only cover Latin-1; map common typographic characters.
_TRANSLATE = str.maketrans({"–": "-", "—": "-", "„": '"', "“": '"', "”": '"', "‚": "'", "‘": "'",
                            "’": "'", "…": "...", "•": "-", "−": "-", " ": " "})


def latin1(text) -> str:
    return str(text).translate(_TRANSLATE).encode("latin-1", "replace").decode("latin-1")


class ReportPDF(FPDF):
    def __init__(self, lang, title, brand, logo):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.lang, self.report_title, self.brand, self.logo = lang, title, brand, logo
        self.accent = branding.hex_to_rgb(brand["primary"])
        self.generated = datetime.now().strftime("%d.%m.%Y %H:%M" if lang == "de" else "%Y-%m-%d %H:%M")
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(True, margin=18)
        self.set_title(latin1(title))
        self.set_creator("Tapinion")
        self.alias_nb_pages()

    def t(self, key, **kw):
        return i18n.translate(self.lang, key, **kw)

    def header(self):
        if self.logo is not None:
            try:
                self.image(self.logo, x=18, y=9, h=10)
            except Exception:  # an unusual uploaded image must not break the report
                self.logo = None
        self.set_xy(18, 10)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 8, latin1(self.report_title), align="R")
        self.set_draw_color(*self.accent)
        self.set_line_width(0.6)
        self.line(18, 21, 192, 21)
        self.set_line_width(0.2)
        self.set_y(26)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        left = self.t("report.generated", when=self.generated)
        if self.brand["name"]:
            left = self.brand["name"] + " · " + left
        self.cell(0, 5, latin1(left), align="L")
        self.set_x(18)
        self.cell(0, 5, latin1(self.t("report.page", page=self.page_no(), pages="{nb}")), align="R")

    # --- building blocks ---------------------------------------------------

    def h1(self, text):
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(*TEXT)
        self.multi_cell(0, 8, latin1(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def h2(self, text):
        self.ensure_space(20)
        self.ln(3)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*TEXT)
        self.cell(0, 7, latin1(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def muted(self, text, size=9):
        self.set_font("Helvetica", "", size)
        self.set_text_color(*MUTED)
        self.multi_cell(0, 5, latin1(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def ensure_space(self, h):
        if self.get_y() + h > self.h - self.b_margin:
            self.add_page()

    def kpis(self, items):
        """items: list of (label, value, sub, color or None)."""
        self.ensure_space(26)
        x0, y0, gap = self.l_margin, self.get_y() + 1, 4
        w = (self.epw - gap * (len(items) - 1)) / len(items)
        for i, (label, value, sub, color) in enumerate(items):
            x = x0 + i * (w + gap)
            self.set_draw_color(*LINE)
            self.rect(x, y0, w, 22)
            if i == 0:
                self.set_fill_color(*self.accent)
                self.rect(x, y0, 1.2, 22, style="F")
            self.set_xy(x + 3, y0 + 2)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*MUTED)
            self.cell(w - 6, 4, latin1(label))
            self.set_xy(x + 3, y0 + 7)
            self.set_font("Helvetica", "B", 18)
            self.set_text_color(*(color or TEXT))
            self.cell(w - 6, 9, latin1(value))
            self.set_xy(x + 3, y0 + 16)
            self.set_font("Helvetica", "", 7)
            self.set_text_color(*MUTED)
            self.cell(w - 6, 4, latin1(sub))
        self.set_y(y0 + 26)

    def stackbar(self, groups):
        self.ensure_space(12)
        x, y, w = self.l_margin, self.get_y(), self.epw
        self.set_fill_color(*LINE)
        self.rect(x, y, w, 6, style="F")
        for g in groups:
            seg = w * g["share"] / 100
            if seg > 0:
                self.set_fill_color(*COLORS[g["key"]])
                self.rect(x, y, seg, 6, style="F")
                x += seg
        self.set_y(y + 9)

    def table(self, headers, rows, widths, aligns=None, colors=None):
        aligns = aligns or ["L"] * len(headers)
        self.ensure_space(14)
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*MUTED)
        for h, w, a in zip(headers, widths, aligns):
            self.cell(w, 6, latin1(h), align=a)
        self.ln(6)
        self.set_draw_color(*LINE)
        self.line(self.l_margin, self.get_y(), self.l_margin + sum(widths), self.get_y())
        self.set_font("Helvetica", "", 9)
        for i, row in enumerate(rows):
            if self.get_y() + 6 > self.h - self.b_margin:
                self.add_page()
            y = self.get_y()
            for j, (val, w, a) in enumerate(zip(row, widths, aligns)):
                if colors and colors[i] and j == 0:
                    self.set_fill_color(*colors[i])
                    self.rect(self.get_x(), y + 2, 2.5, 2.5, style="F")
                    self.set_x(self.get_x() + 4)
                    w -= 4
                self.set_text_color(*TEXT)
                self.cell(w, 6.5, _fit(self, latin1(val), w), align=a)
            self.ln(6.5)
            self.line(self.l_margin, self.get_y(), self.l_margin + sum(widths), self.get_y())
        self.ln(2)

    def columns(self, values, labels, colors, height=42):
        self.ensure_space(height + 12)
        x0, y0, w = self.l_margin, self.get_y(), self.epw
        peak = max(values) or 1
        slot = w / len(values)
        bar = min(slot * 0.7, 14)
        base = y0 + height
        self.set_draw_color(*LINE)
        self.line(x0, base, x0 + w, base)
        for i, (v, lab, col) in enumerate(zip(values, labels, colors)):
            cx = x0 + slot * i + slot / 2
            h = (height - 6) * v / peak
            if v:
                self.set_fill_color(*col)
                self.rect(cx - bar / 2, base - h, bar, h, style="F")
                self.set_font("Helvetica", "", 7)
                self.set_text_color(*MUTED)
                self.set_xy(cx - slot / 2, base - h - 4.5)
                self.cell(slot, 4, str(v), align="C")
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*MUTED)
            self.set_xy(cx - slot / 2, base + 1)
            self.cell(slot, 4, latin1(lab), align="C")
        self.set_y(base + 8)

    def score_bars(self, items):
        """Horizontal bars from -100 to +100; items: list of (label, score, n)."""
        label_w, num_w = 70, 22
        chart_w = self.epw - label_w - num_w
        for label, score, n in items:
            self.ensure_space(7)
            y = self.get_y()
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*TEXT)
            self.cell(label_w, 6, _fit(self, latin1(label), label_w - 2))
            zero = self.l_margin + label_w + chart_w / 2
            self.set_draw_color(*LINE)
            self.line(zero, y, zero, y + 6)
            if score is not None:
                length = chart_w / 2 * abs(score) / 100
                self.set_fill_color(*(COLORS["promoters"] if score >= 0 else COLORS["detractors"]))
                self.rect(zero if score >= 0 else zero - length, y + 1.5, max(length, 0.4), 3, style="F")
            self.set_xy(self.l_margin + label_w + chart_w, y)
            self.set_text_color(*MUTED)
            self.cell(num_w, 6, f"{fmt_score(score)}  (n={n})", align="R")
            self.ln(6.5)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*MUTED)
        self.set_x(self.l_margin + label_w)
        self.cell(chart_w / 3, 4, "-100")
        self.cell(chart_w / 3, 4, "0", align="C")
        self.cell(chart_w / 3, 4, "+100", align="R")
        self.ln(6)


def _fit(pdf, text, width):
    if pdf.get_string_width(text) <= width - 1:
        return text
    while text and pdf.get_string_width(text + "...") > width - 1:
        text = text[:-1]
    return text + "..."


def fmt_score(score):
    return "-" if score is None else (f"{score:+d}" if score else "0")


def fmt_pct(lang, x):
    s = f"{x:.1f} %"
    return s.replace(".", ",") if lang == "de" else s


def fmt_date(lang, iso):
    if not iso or len(iso) < 10:
        return iso or ""
    return f"{iso[8:10]}.{iso[5:7]}.{iso[0:4]}" if lang == "de" else iso[:10]


def _brand_and_logo():
    with db.session() as conn:
        brand = branding.get(conn)
        asset = db.get_asset(conn, "logo")
    if asset:
        logo = io.BytesIO(asset["data"])
    elif DEFAULT_LOGO.is_file():
        logo = str(DEFAULT_LOGO)
    else:
        logo = None
    return brand, logo


def _event_body(pdf, event, rows, day=None):
    lang, t = pdf.lang, pdf.t
    pdf.h1(event["name"])
    meta = f"{fmt_date(lang, event['event_date'])} · {t('mode.' + event['mode'])}"
    if day:
        meta += " · " + t("report.only_day", day=fmt_date(lang, day))
    if not event["active"]:
        meta += " · " + t("events.closed")
    pdf.muted(meta)
    pdf.muted(t("report.question", q=i18n.question_of(event, lang)))
    pdf.ln(2)

    r = stats.result_for(event["mode"], [row["value"] for row in rows])
    score_color = COLORS["promoters"] if (r["score"] or 0) > 0 else (COLORS["detractors"] if (r["score"] or 0) < 0 else None)
    items = [(t("score." + event["mode"]), fmt_score(r["score"]), t("score.scale"), score_color),
             (t("dashboard.responses"), str(r["n"]), "", None)]
    if event["mode"] == "nps":
        mean = "-" if r["mean"] is None else (f"{r['mean']:.1f}".replace(".", ",") if lang == "de" else f"{r['mean']:.1f}")
        items.append((t("dashboard.mean"), mean, t("dashboard.of_ten"), None))
    pdf.kpis(items)

    if not r["n"]:
        pdf.muted(t("report.no_data"))
        return

    pdf.h2(t("dashboard.groups" if event["mode"] == "nps" else "dashboard.distribution"))
    pdf.stackbar(r["groups"])
    pdf.table([t("report.group"), t("report.count"), t("report.share")],
              [(t("group." + g["key"]), g["count"], fmt_pct(lang, g["share"])) for g in r["groups"]],
              [100, 35, 39], ["L", "R", "R"], colors=[COLORS[g["key"]] for g in r["groups"]])

    if event["mode"] == "nps":
        pdf.h2(t("dashboard.values"))
        pdf.columns([d["count"] for d in r["distribution"]], [str(d["value"]) for d in r["distribution"]],
                    [COLORS["promoters"] if d["value"] >= 9 else COLORS["passives"] if d["value"] >= 7 else COLORS["detractors"]
                     for d in r["distribution"]])

    hours = stats.hourly(rows)
    if len(hours) > 1:
        pdf.h2(t("dashboard.hourly"))
        pdf.columns([h["count"] for h in hours], [h["hour"] for h in hours], [pdf.accent] * len(hours), height=32)

    days = stats.per_day(event["mode"], rows)
    if len(days) > 1:
        pdf.h2(t("report.per_day"))
        pdf.table([t("dashboard.day"), t("dashboard.responses"), t("report.score")],
                  [(fmt_date(lang, d), res["n"], fmt_score(res["score"])) for d, res in days],
                  [100, 35, 39], ["L", "R", "R"])


def _signature(pdf, user):
    if user:
        pdf.ln(4)
        pdf.muted(pdf.t("report.created_by", user=user["username"]), size=8)


def event_report(lang, event_id, day=None, user=None) -> bytes:
    with db.session() as conn:
        event = db.get_event(conn, event_id)
        if not event:
            raise LookupError(event_id)
        rows = db.responses_for(conn, event_id, day)
    brand, logo = _brand_and_logo()
    pdf = ReportPDF(lang, i18n.translate(lang, "report.title_event", name=event["name"]), brand, logo)
    pdf.add_page()
    _event_body(pdf, event, rows, day)
    _signature(pdf, user)
    return bytes(pdf.output())


def overview_report(lang, date_from=None, date_to=None, mode=None, details=False, user=None) -> bytes:
    t = lambda key, **kw: i18n.translate(lang, key, **kw)  # noqa: E731
    with db.session() as conn:
        events = db.select_events(conn, date_from, date_to, mode)
        data = [(e, db.responses_for(conn, e["id"])) for e in events]
    brand, logo = _brand_and_logo()
    pdf = ReportPDF(lang, t("report.title_overview"), brand, logo)
    pdf.add_page()
    pdf.h1(t("report.overview_heading"))
    period = t("report.period", start=fmt_date(lang, date_from) if date_from else t("report.start"),
               end=fmt_date(lang, date_to) if date_to else t("report.today"))
    filt = {"nps": t("report.only_nps"), "smiley": t("report.only_smiley")}.get(mode, t("report.all_modes"))
    pdf.muted(f"{period} · {filt} · " + t("report.n_events", n=len(events)))
    pdf.ln(2)

    nps_all = stats.nps_stats([r["value"] for e, rows in data if e["mode"] == "nps" for r in rows])
    smiley_all = stats.smiley_stats([r["value"] for e, rows in data if e["mode"] == "smiley" for r in rows])
    items = [(t("report.events"), str(len(events)), "", None),
             (t("report.responses_total"), str(nps_all["n"] + smiley_all["n"]), "", None)]
    if nps_all["n"]:
        items.append((t("report.nps_all"), fmt_score(nps_all["score"]), t("report.n_responses", n=nps_all["n"]), None))
    if smiley_all["n"]:
        items.append((t("report.smiley_all"), fmt_score(smiley_all["score"]), t("report.n_responses", n=smiley_all["n"]), None))
    pdf.kpis(items)

    if not events:
        pdf.muted(t("report.no_events"))
        _signature(pdf, user)
        return bytes(pdf.output())

    for title, agg in ((t("report.nps_summary"), nps_all), (t("report.smiley_summary"), smiley_all)):
        if agg["n"]:
            pdf.h2(title)
            pdf.stackbar(agg["groups"])
            pdf.table([t("report.group"), t("report.count"), t("report.share")],
                      [(t("group." + g["key"]), g["count"], fmt_pct(lang, g["share"])) for g in agg["groups"]],
                      [100, 35, 39], ["L", "R", "R"], colors=[COLORS[g["key"]] for g in agg["groups"]])

    pdf.h2(t("report.all_events"))
    results = [(e, stats.result_for(e["mode"], [r["value"] for r in rows])) for e, rows in data]
    pdf.table([t("events.date"), t("events.name"), t("events.mode"), "n", t("report.score")],
              [(fmt_date(lang, e["event_date"]), e["name"], t("mode." + e["mode"] + ".short"), r["n"], fmt_score(r["score"]))
               for e, r in results],
              [22, 92, 22, 16, 22], ["L", "L", "L", "R", "R"])

    pdf.h2(t("report.score_per_event"))
    pdf.muted(t("report.score_note"), size=8)
    pdf.ln(1)
    pdf.score_bars([(f"{fmt_date(lang, e['event_date'])} {e['name']}", r["score"], r["n"]) for e, r in results])

    if details:
        for e, rows in data:
            pdf.add_page()
            _event_body(pdf, e, rows)

    _signature(pdf, user)
    return bytes(pdf.output())
