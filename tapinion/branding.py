# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-installation look: name, logo and colours, edited by admins under Settings."""
import re

from . import db

DEFAULTS = {
    "brand_name": "",  # the default logo already carries the word mark
    "color_primary": "#0e7490",
    "color_accent": "#f97316",
    "show_open_events": "1",
}
COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")
LOGO_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/svg+xml": "svg", "image/webp": "webp"}
MAX_LOGO_BYTES = 1024 * 1024


def get(conn) -> dict:
    s = {**DEFAULTS, **db.get_settings(conn)}
    logo = conn.execute("SELECT mime, updated_at FROM assets WHERE name = 'logo'").fetchone()
    return {
        "name": s["brand_name"],
        "primary": s["color_primary"],
        "accent": s["color_accent"],
        "on_primary": readable_on(s["color_primary"]),
        "on_accent": readable_on(s["color_accent"]),
        "show_open_events": s["show_open_events"] == "1",
        "logo_url": "/branding/logo" + (f"?v={logo['updated_at'].replace(' ', 'T')}" if logo else ""),
        "custom_logo": bool(logo),
        "logo_mime": logo["mime"] if logo else None,
    }


def readable_on(hex_color: str) -> str:
    """Black or white text, whichever contrasts better with the given background (WCAG luminance)."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))

    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#111111" if (lum + 0.05) / 0.05 > 1.05 / (lum + 0.05) else "#ffffff"


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def sniff_image(data: bytes) -> str | None:
    """Detect the image type from its content, not from the file name."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    head = data[:512].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:2048].lower()):
        return "image/svg+xml"
    return None
