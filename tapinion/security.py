# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Password hashing (stdlib scrypt), CSRF tokens and a small login throttle."""
import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict

_N, _R, _P = 2**14, 8, 1


def hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(secret.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_secret(secret: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    salt = base64.b64decode(salt_b64)
    digest = hashlib.scrypt(secret.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


def csrf_token(session: dict) -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


class Throttle:
    """At most `limit` failures per key within `window` seconds."""

    def __init__(self, limit=5, window=300):
        self.limit, self.window = limit, window
        self._fails = defaultdict(list)

    def blocked(self, key: str) -> bool:
        cutoff = time.monotonic() - self.window
        self._fails[key] = [t for t in self._fails[key] if t > cutoff]
        return len(self._fails[key]) >= self.limit

    def fail(self, key: str) -> None:
        self._fails[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)
