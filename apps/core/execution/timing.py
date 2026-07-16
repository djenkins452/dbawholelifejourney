# ==============================================================================
# File: apps/core/execution/timing.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Execution timing — deterministic CALCULATIONS (facts, never judgments).
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-10
# ==============================================================================
"""
Execution Timing — the deterministic clock/calendar arithmetic behind "the situation".

BOUNDARY (the architectural rule): WLJ owns CALCULATIONS; the conversational model owns
JUDGMENT.

  Calculation (here, deterministic, must always be correct):
    minutes late · minutes until the next anchor · buffer · estimated duration ·
    earliest completion · latest safe start · fits-before-anchor · required pace.

  Judgment (NOT here — the model's job, from these facts):
    "you're behind" · "you can still recover" · "act now" · "plan is at serious risk".

This module emits numbers, times, and booleans ONLY — never a label, verdict, level, or
directive. It exists so the model NEVER performs date/duration arithmetic itself (the
"6:15 AM tonight" fabrication class): we hand it the computed RESULTS and let it interpret
what they mean. Pure and request-path-safe: no DB writes, no LLM, no mutation.
"""
from __future__ import annotations

import datetime as _dt
import logging

logger = logging.getLogger(__name__)

# Duration estimates (minutes) by name keyword. Kept in lockstep with the renderer's map
# during the transition; when the renderer is retired this module is the sole source.
_DEFAULT_DURATIONS = {
    'bible reading': 15, 'prayer': 15, 'prayer time': 15, 'quiet time': 15,
    'devotion': 15, 'workout': 45, 'exercise': 45, 'shower': 15, 'journal': 10,
    'journaling': 10, 'meditation': 10,
    'amino': 2, 'perfect amino': 2, 'creatine': 2, 'protein shake': 3, 'shake': 3,
    'vitamin': 2, 'supplement': 2, 'medication': 2, 'metformin': 2, 'atorvastatin': 2,
    'lantus': 3, 'mounjaro': 3, 'ozempic': 3, 'fish oil': 2, 'magnesium': 2,
    'probiotic': 2, 'zinc': 2,
}
_DEFAULT_DURATION_FALLBACK = 5  # minutes

# Fixed-time commitments that act as a deadline the rest of the plan must fit before.
_ANCHOR_KEYWORDS = (
    'medication', 'medicine', 'mounjaro', 'shower', 'meeting',
    'appointment', 'call', 'class',
)
_ANCHOR_SOURCE_TYPES = ('medication_dose', 'supplement_dose')

_RESOLVED = frozenset({'completed', 'completed_late', 'skipped', 'rescheduled'})


def estimate_duration(item_name) -> int:
    """Deterministic minutes estimate for an activity name. Never raises."""
    name = (item_name or '').lower().strip()
    for key, minutes in _DEFAULT_DURATIONS.items():
        if key in name:
            return minutes
    return _DEFAULT_DURATION_FALLBACK


def _fmt(dt) -> str:
    return dt.strftime('%I:%M %p').lstrip('0') if dt else None


def _parse_sched(s, now_dt):
    """Parse an execution item's scheduled_time ('HH:MM' or 'h:MM AM/PM') to a datetime
    on `now_dt`'s date (preserving tzinfo). Returns None when absent/unparseable."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ('%H:%M', '%I:%M %p'):
        try:
            t = _dt.datetime.strptime(s, fmt).time()
            return now_dt.replace(hour=t.hour, minute=t.minute,
                                  second=0, microsecond=0)
        except (ValueError, TypeError):
            continue
    return None


def _minutes(a, b) -> int:
    return int((a - b).total_seconds() // 60)


def _is_anchor(item) -> bool:
    name = (item.get('name') or item.get('title') or '').lower()
    if item.get('source_type') in _ANCHOR_SOURCE_TYPES or item.get('source') == 'medication':
        return True
    return any(k in name for k in _ANCHOR_KEYWORDS)


def _title(item) -> str:
    return (item.get('title') or item.get('name') or '').strip()


def compute_execution_timing(state, now) -> dict:
    """Compute the deterministic timing facts for today's remaining execution.

    Args:
        state: the dict from build_execution_state (uses state['items']).
        now:   the user's current datetime (from build_execution_state). A time-only value
               is tolerated by combining it with today's date.

    Returns a FACTS-ONLY dict (no labels/verdicts):
        {
          "now": "6:18 AM",
          "next_anchor": {"title","time","minutes_until"} | None,
          "buffer_minutes": int | None,          # now → next anchor
          "remaining": [ {title, scheduled_time, minutes_late, duration_estimate_min,
                          earliest_start, earliest_completion, latest_safe_start,
                          fits_before_next_anchor} ],
          "remaining_total_min": int,
          "required_pace": {work_min, window_min, slack_min} | None,
          "as_of": iso,
        }
    Never raises: returns {"status": "pending"} on any failure so a consumer never
    fabricates its own timing.
    """
    try:
        if not isinstance(now, _dt.datetime):
            today = _dt.date.today()
            now = _dt.datetime.combine(today, now) if isinstance(now, _dt.time) else _dt.datetime.now()

        items = (state or {}).get('items', []) or []

        # Remaining actionable work (not done, not resolved), earliest scheduled first.
        remaining_items = []
        for it in items:
            if not it.get('is_actionable') or it.get('completed_today'):
                continue
            if it.get('completion_status') in _RESOLVED:
                continue
            remaining_items.append(it)
        remaining_items.sort(
            key=lambda it: (_parse_sched(it.get('scheduled_time'), now) or now.replace(
                hour=23, minute=59)),
        )

        # Next anchor: earliest FUTURE fixed-time commitment.
        anchor = None
        anchor_dt = None
        for it in remaining_items:
            sched = _parse_sched(it.get('scheduled_time'), now)
            if sched is not None and sched > now and _is_anchor(it):
                anchor, anchor_dt = it, sched
                break
        next_anchor = None
        buffer_minutes = None
        if anchor is not None:
            buffer_minutes = _minutes(anchor_dt, now)
            next_anchor = {"title": _title(anchor), "time": _fmt(anchor_dt),
                           "minutes_until": buffer_minutes}

        # Per-task calculations along the critical path (execution order from `now`).
        cursor = now
        remaining = []
        work_min = 0
        for it in remaining_items:
            if anchor is not None and it is anchor:
                continue  # the anchor is the deadline, not work to fit before it
            title = _title(it)
            sched = _parse_sched(it.get('scheduled_time'), now)
            dur = estimate_duration(title)
            work_min += dur
            minutes_late = (_minutes(now, sched)
                            if (sched is not None and sched < now
                                and it.get('time_status') == 'overdue') else 0)
            earliest_start = cursor
            earliest_completion = cursor + _dt.timedelta(minutes=dur)
            cursor = earliest_completion
            latest_safe_start = (anchor_dt - _dt.timedelta(minutes=dur)
                                 if anchor_dt is not None else None)
            fits = (earliest_completion <= anchor_dt) if anchor_dt is not None else True
            remaining.append({
                "title": title,
                "scheduled_time": _fmt(sched),
                "minutes_late": minutes_late,
                "duration_estimate_min": dur,
                "earliest_start": _fmt(earliest_start),
                "earliest_completion": _fmt(earliest_completion),
                "latest_safe_start": _fmt(latest_safe_start),
                "fits_before_next_anchor": fits,
            })

        required_pace = None
        if buffer_minutes is not None:
            required_pace = {
                "work_min": work_min,          # total remaining work before the anchor
                "window_min": buffer_minutes,  # time available before the anchor
                "slack_min": buffer_minutes - work_min,  # negative = over-committed
            }

        return {
            "now": _fmt(now),
            "next_anchor": next_anchor,
            "buffer_minutes": buffer_minutes,
            "remaining": remaining,
            "remaining_total_min": work_min,
            "required_pace": required_pace,
            "as_of": now.isoformat(),
        }
    except Exception:  # pragma: no cover - defensive; never fabricate timing
        logger.warning("execution timing: compute failed", exc_info=True)
        return {"status": "pending"}


def earliest_future_commitment(items, now) -> dict | None:
    """The day's first STILL-PENDING scheduled commitment relative to ``now``.

    A FACT for "the day hasn't begun yet — your first commitment is at X." Scans the
    actionable, not-yet-completed items, keeps those with a scheduled time at or after
    ``now``, and returns the earliest as:

        {"title": str, "time": "5:30 AM", "minutes_until": int}

    Returns None when there is no future scheduled commitment (empty/clear day, or the
    day's scheduled work is already behind/done). Never raises — timing is the single
    calculation authority; a consumer must never re-parse clocks itself.
    """
    try:
        if not isinstance(now, _dt.datetime):
            today = _dt.date.today()
            now = _dt.datetime.combine(today, now) if isinstance(now, _dt.time) else _dt.datetime.now()
        best, best_dt = None, None
        for it in (items or []):
            if not it.get('is_actionable') or it.get('completed_today'):
                continue
            if it.get('completion_status') in _RESOLVED:
                continue
            sched = _parse_sched(it.get('scheduled_time'), now)
            if sched is None or sched < now:
                continue
            if best_dt is None or sched < best_dt:
                best, best_dt = it, sched
        if best is None:
            return None
        return {
            "title": _title(best),
            "time": _fmt(best_dt),
            "minutes_until": _minutes(best_dt, now),
        }
    except Exception:  # pragma: no cover - defensive; never fabricate timing
        logger.warning("earliest_future_commitment: compute failed", exc_info=True)
        return None


def completed_ahead_of_schedule(items, now) -> int:
    """Count of commitments completed today whose scheduled time is LATER than ``now`` —
    i.e. future work knocked out early. The deterministic proof behind an "ahead of
    schedule" read (a FACT, not the verdict; the narrator interprets it). Never raises."""
    try:
        if not isinstance(now, _dt.datetime):
            today = _dt.date.today()
            now = _dt.datetime.combine(today, now) if isinstance(now, _dt.time) else _dt.datetime.now()
        count = 0
        for it in (items or []):
            if not it.get('completed_today'):
                continue
            sched = _parse_sched(it.get('scheduled_time'), now)
            if sched is not None and sched > now:
                count += 1
        return count
    except Exception:  # pragma: no cover - defensive
        logger.warning("completed_ahead_of_schedule: compute failed", exc_info=True)
        return 0
