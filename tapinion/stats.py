# Copyright (C) 2026 Markus Wilhelm, mw-research
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evaluation logic.

NPS: promoters 9-10, passives 7-8, detractors 0-6; NPS = %promoters - %detractors.
Smileys: score = %happy - %unhappy, on the same -100..+100 scale.
Group labels are translated in the templates via the group key.
"""
from collections import Counter, defaultdict


def nps_stats(values):
    nums = [int(v) for v in values if v.isdigit()]
    n = len(nums)
    promoters = sum(1 for v in nums if v >= 9)
    passives = sum(1 for v in nums if v in (7, 8))
    detractors = sum(1 for v in nums if v <= 6)
    dist = Counter(nums)
    return {
        "n": n,
        "groups": [
            {"key": "promoters", "count": promoters, "share": _share(promoters, n)},
            {"key": "passives", "count": passives, "share": _share(passives, n)},
            {"key": "detractors", "count": detractors, "share": _share(detractors, n)},
        ],
        "score": round((promoters - detractors) / n * 100) if n else None,
        "mean": round(sum(nums) / n, 1) if n else None,
        "distribution": [{"value": i, "count": dist.get(i, 0), "share": _share(dist.get(i, 0), n)} for i in range(11)],
    }


def smiley_stats(values):
    c = Counter(v for v in values if v in ("happy", "neutral", "unhappy"))
    n = sum(c.values())
    return {
        "n": n,
        "groups": [{"key": k, "count": c[k], "share": _share(c[k], n)} for k in ("happy", "neutral", "unhappy")],
        "score": round((c["happy"] - c["unhappy"]) / n * 100) if n else None,
    }


def result_for(mode, values):
    return nps_stats(values) if mode == "nps" else smiley_stats(values)


def hourly(rows):
    """Responses per hour of day."""
    c = Counter(r["created_at"][11:13] for r in rows)
    if not c:
        return []
    hours = sorted(c)
    lo, hi = int(hours[0]), int(hours[-1])
    peak = max(c.values())
    return [{"hour": f"{h:02d}", "count": c.get(f"{h:02d}", 0), "rel": c.get(f"{h:02d}", 0) / peak}
            for h in range(lo, hi + 1)]


def per_day(mode, rows):
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["created_at"][:10]].append(r["value"])
    return [(d, result_for(mode, vals)) for d, vals in sorted(by_day.items())]


def _share(part, total):
    return round(part / total * 100, 1) if total else 0.0
