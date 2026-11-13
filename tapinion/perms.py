# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Roles and what each may do.

organizer  runs the kiosk: sees open events, creates events, starts the kiosk, sees the
           aggregated result (counts per group, score) but no individual ratings, no export.
analyst    additionally sees all events and full evaluations, edits events, exports CSV/PDF;
           cannot delete events or ratings.
admin      everything: delete events and single ratings, manage users and settings.
"""

PERMISSIONS = {
    "organizer": {
        "events.view", "events.create", "kiosk.start", "pin.view", "pin.edit", "dashboard.view",
    },
    "analyst": {
        "events.view", "events.view_all", "events.create", "events.edit", "kiosk.start", "pin.view", "pin.edit",
        "dashboard.view", "dashboard.details", "export", "reports",
    },
    "admin": {
        "events.view", "events.view_all", "events.create", "events.edit", "events.delete", "kiosk.start",
        "pin.view", "pin.edit", "dashboard.view", "dashboard.details", "export", "reports",
        "responses.delete", "users.manage", "settings.manage",
    },
}


def can(user, perm: str) -> bool:
    return bool(user) and perm in PERMISSIONS.get(user["role"], set())
