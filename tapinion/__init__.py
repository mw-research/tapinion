# Tapinion - tap your opinion. Feedback kiosk with evaluation.
# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tapinion: feedback kiosk (smileys or 0-10 scale) with evaluation, reports and roles."""
import os
from pathlib import Path

__version__ = "1.0.0"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines); real environment variables take precedence."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(Path.cwd() / ".env")
