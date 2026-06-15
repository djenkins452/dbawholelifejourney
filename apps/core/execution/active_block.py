"""
Active Execution Block Resolver.

Determines the user's currently active execution block (e.g., morning,
mid_morning, lunch) from today's scheduled items, with the canonical
WINDOW_HOURS map as fallback when the user has no items in a window.

Single source of truth for "what window are we in?" used by:
  - build_locked_next_action() — gate "Start with X" eligibility
  - prioritize_execution_items() — gate non-active-block items to "upcoming"

Design rules (per CoS Time/Sequence Integrity contract):
  - Per-user block bounds are derived from min/max scheduled_time of items
    tagged with that window for *this* user, today.
  - Static WINDOW_HOURS is the fallback when no items are tagged.
  - A small lead-in (LEAD_IN_MINUTES) into the next block is allowed so
    that items at the very front of the next block can become "now"
    once the current block's items are done.
  - A future block NEVER overrides an unfinished current-block item.
    The lead-in only relaxes eligibility — the prioritizer is still
    expected to surface the unfinished current-block item first.

This module is PURE: no DB writes, no side effects beyond reads.
"""

import datetime
import logging

logger = logging.getLogger(__name__)

# How early before the next block starts we begin treating its items
# as eligible. Keep this conservative — too large reintroduces the bug
# we are fixing.
LEAD_IN_MINUTES = 15


def _parse_time(time_str):
    """Parse 'HH:MM' (24h) or 'h:MM AM/PM' to datetime.time, or None."""
    if not time_str:
        return None
    if isinstance(time_str, datetime.time):
        return time_str
    s = str(time_str).strip()
    for fmt in ('%H:%M', '%I:%M %p'):
        try:
            return datetime.datetime.strptime(s, fmt).time()
        except (ValueError, TypeError):
            continue
    return None


def _time_to_minutes(t):
    if t is None:
        return None
    return t.hour * 60 + t.minute


def _minutes_to_time(m):
    m = max(0, min(23 * 60 + 59, m))
    return datetime.time(m // 60, m % 60)


def _window_for_time(t, window_bounds):
    """Return the window key whose bounds contain t, else None."""
    if t is None:
        return None
    mins = _time_to_minutes(t)
    for key, bounds in window_bounds.items():
        start_m, end_m = bounds
        if start_m <= mins < end_m:
            return key
    return None


def _derive_per_user_bounds(execution_items):
    """
    Derive {window_key: (start_min, end_min)} from item scheduled_times,
    grouped by their execution_group_id (window) when present.

    Falls back to inspecting scheduled_time hour-bucket via WINDOW_HOURS
    when an item has no explicit window tag.

    Returns a dict that may be empty if no scheduled items exist.
    """
    from apps.core.time_windows import WINDOW_HOURS

    grouped = {}  # window_key -> [minutes]

    for item in (execution_items or []):
        sched = _parse_time(item.get('scheduled_time'))
        if sched is None:
            continue
        mins = _time_to_minutes(sched)

        # Prefer explicit window tag (medication windows, routine windows)
        win = item.get('execution_group_id') if (
            item.get('execution_group_type') in ('medication_window',
                                                  'supplement_window',
                                                  'routine')
        ) else None

        # Routines don't tag their window directly on the item — derive
        # from scheduled hour using static map.
        if not win or win not in WINDOW_HOURS:
            win = None
            for w, (sh, eh) in WINDOW_HOURS.items():
                if sh <= sched.hour < eh:
                    win = w
                    break
        if win is None:
            continue
        grouped.setdefault(win, []).append(mins)

    bounds = {}
    for win, minute_list in grouped.items():
        if not minute_list:
            continue
        bounds[win] = (min(minute_list), max(minute_list))
    return bounds


def _merge_with_static(per_user_bounds):
    """
    Merge per-user derived bounds with WINDOW_HOURS fallback.

    Per-user takes precedence; static fills gaps so every canonical
    window has bounds and we can locate "the next block" even when the
    user has no items in that block today.

    Returns ordered dict-like list of (key, (start_min, end_min)) pairs
    in canonical chronological order.
    """
    from apps.core.time_windows import WINDOW_HOURS, WINDOW_ORDER

    merged = {}
    for key in WINDOW_ORDER:
        if key in per_user_bounds:
            merged[key] = per_user_bounds[key]
        else:
            sh, eh = WINDOW_HOURS[key]
            merged[key] = (sh * 60, eh * 60)
    return merged


def get_active_block(user, now=None, execution_items=None):
    """
    Resolve the user's active execution block at the given time.

    Args:
        user: User instance. Used only for timezone if `now` is omitted.
        now: datetime.datetime or datetime.time. Defaults to user's
             current local time.
        execution_items: optional pre-fetched list of ExecutionItem dicts.
            If omitted, fetched via build_today_execution(user).

    Returns:
        dict:
            {
                "name": str | None,           # active window key, or None
                "start_time": datetime.time,
                "end_time": datetime.time,
                "lead_in_end_time": datetime.time, # = next_block.start - LEAD_IN
                "next_block_name": str | None,
                "next_block_start": datetime.time | None,
                "bounds": {window_key: (start_min, end_min), ...},
            }

        When no canonical window contains `now` (e.g., 4 AM), returns
        name=None with bounds populated so the caller can still compute
        "what is the next block?".
    """
    if now is None:
        from apps.core.utils import get_user_now
        try:
            now = get_user_now(user)
        except Exception:
            now = datetime.datetime.now()

    if isinstance(now, datetime.datetime):
        now_time = now.time()
    else:
        now_time = now

    if execution_items is None:
        try:
            from apps.core.execution.today_execution import build_today_execution
            execution_items = build_today_execution(user).get('items', [])
        except Exception:
            logger.warning(
                "active_block: failed to fetch execution items for user=%s",
                getattr(user, 'id', None), exc_info=True,
            )
            execution_items = []

    per_user = _derive_per_user_bounds(execution_items)
    merged = _merge_with_static(per_user)

    # Canonical chronological order
    from apps.core.time_windows import WINDOW_ORDER
    ordered_keys = [k for k in WINDOW_ORDER if k in merged]

    # Locate active block: first window whose [start, end) contains now,
    # using static WINDOW_HOURS for membership (per-user bounds may be
    # narrower than the canonical window — we still consider the user
    # to be "in" the canonical window even before the first item).
    from apps.core.time_windows import WINDOW_HOURS
    active_name = None
    now_mins = _time_to_minutes(now_time)
    for key in ordered_keys:
        sh, eh = WINDOW_HOURS[key]
        if sh * 60 <= now_mins < eh * 60:
            active_name = key
            break

    if active_name is None:
        # We are outside every canonical window (e.g., 04:30). Next block
        # is the first whose start is in the future today.
        next_name = None
        next_start = None
        for key in ordered_keys:
            sh, _ = WINDOW_HOURS[key]
            if sh * 60 > now_mins:
                next_name = key
                next_start = _minutes_to_time(sh * 60)
                break
        return {
            "name": None,
            "start_time": None,
            "end_time": None,
            "lead_in_end_time": now_time,
            "next_block_name": next_name,
            "next_block_start": next_start,
            "bounds": merged,
        }

    sh, eh = WINDOW_HOURS[active_name]
    start_time = _minutes_to_time(sh * 60)
    end_time = _minutes_to_time(eh * 60)

    # Find the next block (chronologically after active)
    idx = ordered_keys.index(active_name)
    next_name = ordered_keys[idx + 1] if idx + 1 < len(ordered_keys) else None
    next_start = None
    if next_name is not None:
        nsh, _ = WINDOW_HOURS[next_name]
        next_start = _minutes_to_time(nsh * 60)

    # Lead-in: when we are within LEAD_IN_MINUTES of the next block start,
    # the next block's earliest items become eligible too.
    if next_start is not None:
        lead_in_end_time = _minutes_to_time(
            _time_to_minutes(next_start) - LEAD_IN_MINUTES
        )
    else:
        lead_in_end_time = end_time

    return {
        "name": active_name,
        "start_time": start_time,
        "end_time": end_time,
        "lead_in_end_time": lead_in_end_time,
        "next_block_name": next_name,
        "next_block_start": next_start,
        "bounds": merged,
    }


def first_eligible_overdue(overdue_entries, active_block, now_time):
    """Earliest overdue Today-Engine entry that is still EXECUTION-eligible.

    `overdue_entries` are today_engine bucket entries ({sort_time, label,
    item}) sorted earliest-first. Returns the first entry whose item passes
    `is_item_in_active_block` (active or immediately-preceding block), or None.

    Purpose: a long-stale overdue item (e.g. a 5:30 AM routine still open at
    1:48 PM) must NEVER be presented as the "next action" — it belongs in
    Risk/Fix. This filter is the single rule both next-action selectors use so
    they cannot diverge. Never raises.
    """
    for entry in overdue_entries or []:
        if not isinstance(entry, dict):
            continue
        it = entry.get('item') or {}
        try:
            if is_item_in_active_block(
                {'scheduled_time': it.get('time_str'),
                 'time_status': 'overdue'},
                active_block, now_time,
            ):
                return entry
        except Exception:
            continue
    return None


def is_item_in_active_block(item, active_block, now_time):
    """
    Decide whether an execution item is eligible for **EXECUTION mode**.

    Execution mode rule (CoS Strict Mode Isolation contract):
      - An item is eligible if its scheduled_time falls in the active
        block's canonical window.
      - Or if its scheduled_time is in the next block AND we are within
        the lead-in window (now >= lead_in_end_time).
      - For OVERDUE items: only eligible if scheduled_time is in the
        active block OR the immediately preceding canonical block.
        Overdue items in long-past blocks (e.g. a 5:30 AM prayer at
        noon) are NOT Execution-eligible — they belong in Risk/Fix.
      - Items with no scheduled_time bypass the gate (handled elsewhere).

    Risk and Fix selectors do NOT use this function — they consume
    state['overdue_actions'] directly so behind-schedule users always
    see their stale items somewhere, just not in Execution.

    Args:
        item: dict — 'scheduled_time' (HH:MM string or time) and
              optional 'time_status' ('overdue' triggers the
              preceding-block rule).
        active_block: dict from get_active_block(). May have name=None.
        now_time: datetime.time.

    Returns:
        bool
    """
    sched = _parse_time(item.get('scheduled_time'))
    if sched is None:
        # No scheduled time — let the prioritizer decide; block gate
        # cannot evaluate.
        return True

    sched_mins = _time_to_minutes(sched)
    is_overdue = item.get('time_status') == 'overdue'

    # No active block (e.g., very early morning): only items in the
    # next block, within lead-in, are eligible.
    if active_block.get("name") is None:
        next_start = active_block.get("next_block_start")
        if next_start is None:
            return False
        next_start_mins = _time_to_minutes(next_start)
        now_mins = _time_to_minutes(now_time)
        return (
            now_mins >= next_start_mins - LEAD_IN_MINUTES
            and sched_mins < next_start_mins + 60  # only first hour of next block
        )

    from apps.core.time_windows import WINDOW_HOURS, WINDOW_ORDER
    active_name = active_block["name"]
    sh, eh = WINDOW_HOURS[active_name]

    # In active block: always eligible (overdue or not).
    if sh * 60 <= sched_mins < eh * 60:
        return True

    # Overdue items: eligible ONLY if in the immediately preceding
    # canonical block. Older items are stale and surface only in
    # Risk/Fix modes.
    if is_overdue:
        try:
            idx = WINDOW_ORDER.index(active_name)
        except ValueError:
            return False
        if idx == 0:
            return False  # No preceding block today
        prev_name = WINDOW_ORDER[idx - 1]
        psh, peh = WINDOW_HOURS[prev_name]
        return psh * 60 <= sched_mins < peh * 60

    # Non-overdue future item: next-block lead-in check.
    next_name = active_block.get("next_block_name")
    if next_name is None:
        return False
    nsh, neh = WINDOW_HOURS[next_name]
    if not (nsh * 60 <= sched_mins < neh * 60):
        return False
    lead_end = active_block.get("lead_in_end_time")
    if lead_end is None:
        return False
    now_mins = _time_to_minutes(now_time)
    return now_mins >= _time_to_minutes(lead_end)
