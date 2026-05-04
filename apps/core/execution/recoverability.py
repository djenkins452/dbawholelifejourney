"""
Deterministic recoverability check for the WLJ recovery contract.

Given an annotated ExecutionItem (with task_class + recovery_grace_minutes)
and the current time, decide whether the item is still meaningfully
completable. PURE module — no DB, no LLM.

Per-class rules:

    HARD_EXPIRED   recoverable iff now <= scheduled_time + grace
                   (grace is 0; once past scheduled it is gone)

    WINDOWED       recoverable iff now < cutoff, where
                   cutoff = MIN(scheduled + grace, next_anchor_block_start)
                   The next-anchor cap prevents "morning recovery drift" —
                   a 6:45 AM protein shake cannot be recommended at 2:10 PM
                   even if grace alone would still allow it.

    SOFT_EXPIRED   recoverable for the rest of the day.

    FLEXIBLE       recoverable any time the day is open.

Items with no scheduled_time are always considered recoverable for the
class they were assigned (only WINDOWED depends on scheduled_time;
others fall through unchanged).
"""

import datetime as _dt

from apps.core.time_windows import WINDOW_HOURS, WINDOW_ORDER

from .task_classifier import (
    FLEXIBLE,
    HARD_EXPIRED,
    SOFT_EXPIRED,
    WINDOWED,
)


def _parse_time(value):
    """Parse 'HH:MM' (24h), 'h:MM AM/PM', or a time object. Else None."""
    if value is None:
        return None
    if isinstance(value, _dt.time):
        return value
    s = str(value).strip()
    for fmt in ("%H:%M", "%I:%M %p"):
        try:
            return _dt.datetime.strptime(s, fmt).time()
        except (ValueError, TypeError):
            continue
    return None


def _to_minutes(t):
    return t.hour * 60 + t.minute


def _next_anchor_block_start_after(scheduled):
    """Return the start time of the canonical block immediately AFTER
    the one containing `scheduled`. Returns None if `scheduled` is in
    the last block of the day or unmappable.
    """
    if scheduled is None:
        return None
    hour = scheduled.hour
    containing = None
    for key, (sh, eh) in WINDOW_HOURS.items():
        if sh <= hour < eh:
            containing = key
            break
    if containing is None:
        return None
    try:
        idx = WINDOW_ORDER.index(containing)
    except ValueError:
        return None
    if idx + 1 >= len(WINDOW_ORDER):
        return None
    next_key = WINDOW_ORDER[idx + 1]
    nsh, _ = WINDOW_HOURS[next_key]
    return _dt.time(nsh, 0)


def is_recoverable(item, now):
    """Decide whether an annotated ExecutionItem is still recoverable.

    Args:
        item: dict with 'task_class', 'recovery_grace_minutes',
              'scheduled_time' (optional).
        now: datetime.time OR datetime.datetime (time-portion is used).

    Returns:
        bool
    """
    if isinstance(now, _dt.datetime):
        now_time = now.time()
    else:
        now_time = now or _dt.time(12, 0)

    cls = item.get("task_class") or FLEXIBLE
    grace = item.get("recovery_grace_minutes")
    scheduled = _parse_time(item.get("scheduled_time"))

    if cls == FLEXIBLE:
        return True

    if cls == SOFT_EXPIRED:
        # Rest-of-day. Still recoverable.
        return True

    if cls == HARD_EXPIRED:
        if scheduled is None:
            # No schedule means we cannot determine expiry — treat as
            # still recoverable (caller can override via shutdown rule).
            return True
        # grace is 0 for HARD_EXPIRED; allow exact match.
        return _to_minutes(now_time) <= _to_minutes(scheduled)

    if cls == WINDOWED:
        if scheduled is None:
            # Unscheduled WINDOWED: caller-supplied grace is meaningless;
            # treat as always recoverable.
            return True
        sched_min = _to_minutes(scheduled)
        grace_min = grace if isinstance(grace, int) else 0
        grace_cutoff_min = sched_min + grace_min
        anchor_start = _next_anchor_block_start_after(scheduled)
        if anchor_start is not None:
            anchor_min = _to_minutes(anchor_start)
            cutoff_min = min(grace_cutoff_min, anchor_min)
        else:
            cutoff_min = grace_cutoff_min
        return _to_minutes(now_time) < cutoff_min

    # Unknown class — fail safe and treat as recoverable.
    return True


def recovery_cutoff(item):
    """Return the cutoff time for an item, for diagnostics / display.

    Returns datetime.time or None when the cutoff is "rest of day" /
    unbounded.
    """
    cls = item.get("task_class") or FLEXIBLE
    if cls in (FLEXIBLE, SOFT_EXPIRED):
        return None
    scheduled = _parse_time(item.get("scheduled_time"))
    if scheduled is None:
        return None
    if cls == HARD_EXPIRED:
        return scheduled
    if cls == WINDOWED:
        sched_min = _to_minutes(scheduled)
        grace = item.get("recovery_grace_minutes") or 0
        grace_cutoff_min = sched_min + grace
        anchor_start = _next_anchor_block_start_after(scheduled)
        if anchor_start is None:
            cap_min = grace_cutoff_min
        else:
            cap_min = min(grace_cutoff_min, _to_minutes(anchor_start))
        cap_min = max(0, min(23 * 60 + 59, cap_min))
        return _dt.time(cap_min // 60, cap_min % 60)
    return None
