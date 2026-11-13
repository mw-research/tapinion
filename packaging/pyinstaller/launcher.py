# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Entry point of the packaged desktop app: without arguments the desktop window starts."""
import sys

from tapinion.cli import main

if __name__ == "__main__":
    main(sys.argv[1:] or ["desktop"])
