# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""`python -m tapinion` – command line; without arguments the desktop app starts."""
import sys

from .cli import main

if __name__ == "__main__":
    main(sys.argv[1:] or ["desktop"])
