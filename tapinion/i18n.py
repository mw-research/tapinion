# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Translations. One JSON file per language in locales/; add a language by adding a file."""
import json
import os
from functools import lru_cache
from pathlib import Path

LOCALES = Path(__file__).parent / "locales"


@lru_cache(maxsize=None)
def catalog(lang: str) -> dict:
    path = LOCALES / f"{lang}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def languages() -> list[str]:
    return sorted(p.stem for p in LOCALES.glob("*.json"))


def default_lang() -> str:
    lang = os.environ.get("DEFAULT_LANG", "en")
    return lang if lang in languages() else "en"


def translate(lang: str, key: str, **kw) -> str:
    text = catalog(lang).get(key) or catalog("en").get(key) or key
    return text.format(**kw) if kw else text


def from_accept_language(header: str | None) -> str | None:
    """Pick the best supported language from an Accept-Language header."""
    if not header:
        return None
    weighted = []
    for part in header.split(","):
        bits = part.strip().split(";q=")
        code = bits[0].strip().lower()[:2]
        try:
            q = float(bits[1]) if len(bits) > 1 else 1.0
        except ValueError:
            q = 0.0
        weighted.append((q, code))
    for _, code in sorted(weighted, reverse=True):
        if code in languages():
            return code
    return None


def question_of(event, lang: str) -> str:
    """The kiosk question of an event in the given language, or the default question."""
    q = event["question_" + lang] if lang in ("de", "en") else ""
    return q or translate(lang, f"question.default.{event['mode']}")
