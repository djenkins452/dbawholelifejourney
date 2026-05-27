"""
Rhythm Grouping — presentation-only collapse of canonical time windows.

Maps canonical WINDOW_ORDER (morning, mid_morning, lunch, afternoon, evening,
nightly) into the four rhythm buckets dashboard_v3 displays:

    ☀️ morning   ← morning + mid_morning
    🌤 day       ← lunch + afternoon
    🌙 evening   ← evening
    🌑 night     ← nightly

NO new truth is produced. Items, statuses, and counts are taken verbatim
from build_today_execution(). This file only buckets and decorates.

The Visual Truth Contract is honored: only items with completed == True
count toward the "X / Y complete" headline. Past-window items that were
*not* completed remain visible with their status badge.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.core.time_windows import WINDOW_HOURS

logger = logging.getLogger(__name__)


# ── Rhythm bucket definitions ──────────────────────────────────────────
# Ordered. Each maps to a set of canonical windows and a display hour range.
RHYTHM_BUCKETS: list[dict[str, Any]] = [
    {
        "key": "morning",
        "label": "Morning Rhythm",
        "icon": "☀️",
        "windows": ("morning", "mid_morning"),
        # 5:00 – 12:00
        "hours": (WINDOW_HOURS["morning"][0], WINDOW_HOURS["mid_morning"][1]),
    },
    {
        "key": "day",
        "label": "Day Rhythm",
        "icon": "🌤",
        "windows": ("lunch", "afternoon"),
        # 12:00 – 17:00
        "hours": (WINDOW_HOURS["lunch"][0], WINDOW_HOURS["afternoon"][1]),
    },
    {
        "key": "evening",
        "label": "Evening Rhythm",
        "icon": "🌙",
        "windows": ("evening",),
        # 17:00 – 21:00
        "hours": WINDOW_HOURS["evening"],
    },
    {
        "key": "night",
        "label": "Night Reset",
        "icon": "🌑",
        "windows": ("nightly",),
        # 21:00 – 24:00
        "hours": WINDOW_HOURS["nightly"],
    },
]

RHYTHM_BUCKET_FOR_WINDOW = {
    w: b["key"] for b in RHYTHM_BUCKETS for w in b["windows"]
}


def _classify_item(item: dict) -> str:
    """Map an execution item's scheduled_time / time_of_day to a rhythm key.

    Falls back to 'day' if no time information is present (unscheduled items
    drift into the active day bucket rather than being lost).
    """
    # Prefer explicit time_of_day if the item provided one (medications).
    tod = (item.get("time_of_day") or "").lower().strip()
    if tod and tod in RHYTHM_BUCKET_FOR_WINDOW:
        return RHYTHM_BUCKET_FOR_WINDOW[tod]

    # Else derive from scheduled_time HH:MM string.
    sched = item.get("scheduled_time")
    if sched:
        try:
            hour = int(str(sched).split(":")[0])
        except (ValueError, AttributeError):
            hour = None
        if hour is not None:
            for bucket in RHYTHM_BUCKETS:
                start, end = bucket["hours"]
                if start <= hour < end:
                    return bucket["key"]

    return "day"


def _current_rhythm_key(current_hour: int) -> str:
    """Which rhythm bucket is the user inside *right now*."""
    for bucket in RHYTHM_BUCKETS:
        start, end = bucket["hours"]
        if start <= current_hour < end:
            return bucket["key"]
    # Pre-dawn (< 5am) — show morning. Post-midnight overflow — show night.
    return "morning" if current_hour < 5 else "night"


def build_rhythm_sections(user, execution_contract: dict | None = None) -> dict:
    """Group today's execution items into the four rhythm buckets.

    Args:
        user: Django User.
        execution_contract: Optional pre-fetched dict from
            ``build_today_execution(user)``. If omitted, it will be fetched
            here — passing in avoids a duplicate compute on the request path.

    Returns:
        {
            "current_key": "morning" | "day" | "evening" | "night",
            "sections": [ {key, label, icon, items, completion, status, expanded}, ... ],
            "totals": {"total": int, "completed": int, "at_risk": int, "overdue": int},
        }

    Each section.items entry is the *original* execution item dict — no
    fields are renamed or recomputed, so consumers can still rely on
    execution_status / task_class / urgency / source_type.
    """
    from apps.core.utils import get_user_now

    if execution_contract is None:
        try:
            from apps.core.execution.today_execution import build_today_execution
            execution_contract = build_today_execution(user)
        except Exception:
            logger.warning("rhythm: today_execution fetch failed", exc_info=True)
            execution_contract = {"items": [], "summaries": {}}

    items: list[dict] = execution_contract.get("items", []) or []

    # Bucket items by rhythm key.
    by_bucket: dict[str, list[dict]] = {b["key"]: [] for b in RHYTHM_BUCKETS}
    for item in items:
        bucket = _classify_item(item)
        by_bucket.setdefault(bucket, []).append(item)

    try:
        now = get_user_now(user)
        current_hour = now.time().hour
    except Exception:
        current_hour = 12  # safe default
    current_key = _current_rhythm_key(current_hour)

    sections: list[dict] = []
    totals = {"total": 0, "completed": 0, "at_risk": 0, "overdue": 0}

    for bucket in RHYTHM_BUCKETS:
        bucket_items = by_bucket.get(bucket["key"], [])
        # Sort by scheduled_time, unscheduled last.
        bucket_items = sorted(
            bucket_items,
            key=lambda i: (i.get("scheduled_time") is None, i.get("scheduled_time") or ""),
        )

        # Visual Truth Contract: only actual completion counts as complete.
        completed = sum(1 for i in bucket_items if i.get("completed_today"))
        total = len(bucket_items)
        at_risk = sum(
            1 for i in bucket_items
            if (i.get("execution_status") == "AT_RISK")
            and not i.get("completed_today")
        )
        overdue = sum(
            1 for i in bucket_items
            if i.get("urgency") == "overdue" and not i.get("completed_today")
        )

        totals["total"] += total
        totals["completed"] += completed
        totals["at_risk"] += at_risk
        totals["overdue"] += overdue

        # Status label — drives the small headline on the collapsed card.
        if total == 0:
            status = "empty"
        elif completed == total:
            status = "complete"
        elif overdue or at_risk:
            status = "attention"
        elif bucket["key"] == current_key:
            status = "in_progress"
        else:
            status = "pending"

        # Time-aware default expansion:
        #   - current bucket: expanded
        #   - past bucket fully complete: collapsed
        #   - past bucket with leftovers: expanded (accountability)
        #   - future bucket: collapsed
        is_current = bucket["key"] == current_key
        is_past = _bucket_index(bucket["key"]) < _bucket_index(current_key)
        if is_current:
            expanded = True
        elif is_past:
            expanded = status != "complete"
        else:
            expanded = False

        sections.append({
            "key": bucket["key"],
            "label": bucket["label"],
            "icon": bucket["icon"],
            "items": bucket_items,
            "is_current": is_current,
            "is_past": is_past,
            "expanded": expanded,
            "status": status,
            "completion": {
                "completed": completed,
                "total": total,
                "at_risk": at_risk,
                "overdue": overdue,
            },
        })

    return {
        "current_key": current_key,
        "sections": sections,
        "totals": totals,
    }


def _bucket_index(key: str) -> int:
    for i, bucket in enumerate(RHYTHM_BUCKETS):
        if bucket["key"] == key:
            return i
    return -1
