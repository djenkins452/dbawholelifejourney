# ==============================================================================
# File: apps/core/cos_briefing/rhythm_api.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Canonical Rhythm API (P24) — one source for "today's rhythm" facts.
# ==============================================================================
"""
Canonical Rhythm API — P24 (Canonical Truth Source).

The SINGLE authoritative accessor layer for "today's rhythm" facts. Every
consumer (Dashboard, Beth, Notifications, Daily Briefings, Mobile, Widgets)
must read these — facts are computed once and consumed everywhere.

These derive from the SAME engine the Dashboard's "Today's Rhythm" renders
(`build_rhythm_sections` over the `build_today_execution` contract) — they add
NO new truth and NO independent re-computation.

    get_current_rhythm_bucket(user)   — the current rhythm bucket (section)
    get_current_rhythm_item(user)     — the next thing to do (first incomplete)
    get_next_rhythm_item(user)        — the one after the current item
    get_remaining_rhythm_items(user)  — all incomplete items, schedule-ordered

NOTE on the distinction (P24): this is the SCHEDULED "next" (rhythm). The
URGENCY "focus right now" is a DIFFERENT canonical fact computed by
`apps.core.execution.selectors.get_next_action` — do not substitute one for the
other. Consumers request the one they mean.
"""

import logging

logger = logging.getLogger(__name__)

# Canonical bucket order for "earlier in the day comes first".
_BUCKET_ORDER = {"morning": 0, "day": 1, "evening": 2, "night": 3}


def _rhythm(user):
    """The dashboard's rhythm structure ({current_key, sections, totals}) or {}."""
    try:
        from apps.core.cos_briefing.rhythm import build_rhythm_sections
        return build_rhythm_sections(user) or {}
    except Exception:
        logger.warning("rhythm_api: build_rhythm_sections failed", exc_info=True)
        return {}


def _ordered_incomplete(user):
    """Incomplete rhythm items in the order the user should do them:
    current + past buckets first (still actionable today, schedule-ordered),
    then upcoming future buckets. Items are the ORIGINAL execution dicts."""
    data = _rhythm(user)
    sections = data.get("sections") or []
    cur_idx = _BUCKET_ORDER.get(data.get("current_key"), 0)
    actionable, future = [], []
    for sec in sections:
        idx = _BUCKET_ORDER.get(sec.get("key"), 99)
        for it in (sec.get("items") or []):
            if it.get("completed_today"):
                continue                      # Visual Truth Contract — only real completion
            row = (idx, it.get("scheduled_time") or "", it)
            (actionable if idx <= cur_idx else future).append(row)
    actionable.sort(key=lambda x: (x[1] == "", x[1]))      # scheduled first, unscheduled last
    future.sort(key=lambda x: (x[0], x[1] == "", x[1]))    # earliest bucket, then time
    return [it for _, _, it in actionable] + [it for _, _, it in future]


def get_current_rhythm_bucket(user):
    data = _rhythm(user)
    ck = data.get("current_key")
    for sec in (data.get("sections") or []):
        if sec.get("key") == ck:
            return sec
    return None


def get_remaining_rhythm_items(user):
    return _ordered_incomplete(user)


def get_current_rhythm_item(user):
    items = _ordered_incomplete(user)
    return items[0] if items else None


def get_next_rhythm_item(user):
    items = _ordered_incomplete(user)
    return items[1] if len(items) > 1 else None
