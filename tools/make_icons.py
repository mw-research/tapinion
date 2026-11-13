# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Render the app icons (PWA, Apple, Windows .ico, Android launcher) from the logo geometry.

    python tools/make_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BRAND = (14, 116, 144)
ACCENT = (249, 115, 22)
WHITE = (255, 255, 255)


def draw_mark(size: int, background=None, pad=0.0) -> Image.Image:
    """The speech-bubble mark on a 64-unit grid, scaled to `size` pixels (4x supersampled)."""
    s = size * 4
    img = Image.new("RGBA", (s, s), background or (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = s * (1 - 2 * pad) / 64
    o = s * pad

    def p(x, y):
        return (o + x * k, o + y * k)

    d.rounded_rectangle([p(2, 4), p(62, 48)], radius=8 * k, fill=BRAND)
    d.polygon([p(16, 46), p(30, 46), p(16, 60)], fill=BRAND)
    for cx in (22, 42):
        d.ellipse([p(cx - 4, 17), p(cx + 4, 25)], fill=WHITE)
    d.arc([p(19, 18), p(45, 40)], start=25, end=155, fill=WHITE, width=int(4.5 * k))
    d.ellipse([p(47, 3), p(61, 17)], fill=ACCENT, outline=WHITE, width=int(2.5 * k))
    return img.resize((size, size), Image.LANCZOS)


def main():
    icons = ROOT / "tapinion" / "static" / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        draw_mark(size, background=WHITE + (255,), pad=0.12).save(icons / f"icon-{size}.png")
    draw_mark(180, background=WHITE + (255,), pad=0.12).save(icons / "apple-touch-icon.png")
    draw_mark(256).save(ROOT / "packaging" / "pyinstaller" / "tapinion.ico",
                        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    res = ROOT / "android" / "app" / "src" / "main" / "res"
    for folder, size in {"mipmap-mdpi": 48, "mipmap-hdpi": 72, "mipmap-xhdpi": 96,
                         "mipmap-xxhdpi": 144, "mipmap-xxxhdpi": 192}.items():
        (res / folder).mkdir(parents=True, exist_ok=True)
        draw_mark(size, background=WHITE + (255,), pad=0.1).save(res / folder / "ic_launcher.png")
    print("icons written")


if __name__ == "__main__":
    main()
