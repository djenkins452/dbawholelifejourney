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

        is_current = bucket["key"] == current_key
        is_past = _bucket_index(bucket["key"]) < _bucket_index(current_key)

        # Interaction mode — drives template rendering. Derived from
        # canonical state only (no UI flags):
        #   full    → current rhythm, full checkboxes + group-complete buttons
        #   summary → past rhythm, collapsed to header line; click to expand
        #   preview → future rhythm with items, compact "Coming Later" view
        #   empty   → future rhythm with no items, minimal placeholder
        if is_current:
            interaction_mode = "full"
        elif is_past:
            interaction_mode = "summary"
        elif total > 0:
            interaction_mode = "preview"
        else:
            interaction_mode = "empty"

        open_count = total - completed

        # Default expanded state mirrors mode, with one trust-preserving
        # exception: a past rhythm that still has open items stays
        # expanded so unfinished work (especially meds/supplements)
        # remains visible — never hide accountability behind a collapse.
        expanded = (
            interaction_mode in ("full", "preview")
            or (interaction_mode == "summary" and open_count > 0)
        )
        block_start_time = _earliest_scheduled_time(bucket_items)

        # Contextual label for the open-items list — phrasing depends on
        # whether the block is current, past, or future. Empty / completed
        # blocks show nothing for this slot (handled in the template).
        if is_current:
            open_label = "Still Open" if open_count else ""
        elif is_past:
            open_label = "Still Open (recoverable)" if open_count else ""
        else:
            open_label = "Coming Later" if open_count else ""

        sections.append({
            "key": bucket["key"],
            "label": bucket["label"],
            "icon": bucket["icon"],
            "items": bucket_items,
            "is_current": is_current,
            "is_past": is_past,
            "expanded": expanded,
            "status": status,
            "interaction_mode": interaction_mode,
            "open_count": open_count,
            "open_label": open_label,
            "block_start_time": block_start_time,
            # Group-complete buttons (full mode only) — one per
            # (intake_type, time_of_day) cluster of doses.
            "dose_groups": (
                _build_dose_groups(bucket_items) if is_current else []
            ),
            # Compact preview groups (preview mode only) — list of doses
            # and tasks grouped by scheduled_time, no checkboxes.
            "preview_groups": (
                _build_preview_groups(bucket_items)
                if interaction_mode == "preview" else []
            ),
            "completion": {
                "completed": completed,
                "total": total,
                "at_risk": at_risk,
                "overdue": overdue,
            },
            "momentum": _momentum_label(
                completed, total, at_risk, overdue,
                is_current, is_past,
                block_start_time=block_start_time,
                bucket_label=bucket["label"],
            ),
        })

    # Preview key — the rhythm immediately AFTER the current one. Surfaced
    # so Beth can describe "coming next" consistently with the dashboard's
    # preview tile (same canonical timing logic, no parallel definitions).
    _bucket_keys = [b["key"] for b in RHYTHM_BUCKETS]
    try:
        _ci = _bucket_keys.index(current_key)
        preview_key = _bucket_keys[_ci + 1] if _ci + 1 < len(_bucket_keys) else None
    except ValueError:
        preview_key = None

    return {
        "current_key": current_key,
        "preview_key": preview_key,
        "sections": sections,
        "totals": totals,
    }


# ── Helpers for dose grouping (used by full mode group-complete buttons) ──


def _build_dose_groups(items: list[dict]) -> list[dict]:
    """Group medication / supplement doses by (intake_type, time_of_day) so
    the template can render a 'Complete morning medications' button per
    cluster while preserving the meds-vs-supplements workflow separation.

    Keys read are canonical fields already on the execution item dict —
    no hardcoded medicine names, no hardcoded windows.

    Returns a list of dicts:
        {
          "kind":          "medication" | "supplement",
          "time_of_day":   window key (morning/afternoon/evening/nightly/...),
          "label":         "Morning Medications" | "Morning Supplements" | …
          "count":         total doses in the group
          "completed":     count completed today
          "all_completed": bool
        }
    """
    from apps.core.time_windows import WINDOW_DISPLAY_NAMES

    groups: dict[tuple, dict] = {}
    for item in items:
        stype = item.get("source_type")
        if stype not in ("medication_dose", "supplement_dose"):
            continue
        intake_type = (item.get("intake_type")
                       or ("supplement" if stype == "supplement_dose" else "medication"))
        tod = (item.get("time_of_day") or "").strip().lower()
        if not tod or intake_type not in ("medication", "supplement"):
            continue
        key = (intake_type, tod)
        g = groups.setdefault(key, {
            "kind": intake_type,
            "time_of_day": tod,
            "count": 0,
            "completed": 0,
        })
        g["count"] += 1
        if item.get("completed_today"):
            g["completed"] += 1

    out = []
    for (kind, tod), g in groups.items():
        window_name = WINDOW_DISPLAY_NAMES.get(tod, tod.title())
        noun = "Medications" if kind == "medication" else "Supplements"
        g["label"] = f"{window_name} {noun}"
        g["all_completed"] = g["count"] > 0 and g["completed"] >= g["count"]
        out.append(g)
    # Stable order: medication before supplement, then by canonical window order.
    from apps.core.time_windows import WINDOW_ORDER
    out.sort(key=lambda g: (
        0 if g["kind"] == "medication" else 1,
        WINDOW_ORDER.index(g["time_of_day"]) if g["time_of_day"] in WINDOW_ORDER else 99,
    ))
    return out


def _build_preview_groups(items: list[dict]) -> list[dict]:
    """Compact 'Coming Later' grouping by scheduled_time — no checkboxes,
    no individual interactivity. Eliminates blank space in future rhythm
    tiles while preserving visibility of what's coming.

    Returns:
        [{"time": "1:00 PM", "titles": ["10X Optimize", "Fish Oil"]}, …]

    Unscheduled items collapse under "Anytime" so nothing is hidden.
    """
    by_time: dict[str, list[str]] = {}
    order: list[str] = []
    for item in items:
        if item.get("completed_today"):
            continue
        st = item.get("scheduled_time") or ""
        display = _format_time_12h(st) if st else "Anytime"
        if display not in by_time:
            by_time[display] = []
            order.append(display)
        title = item.get("title") or ""
        if title:
            by_time[display].append(title)
    return [{"time": t, "titles": by_time[t]} for t in order if by_time[t]]


def _format_time_12h(hhmm: str) -> str:
    try:
        from datetime import datetime as _dt
        return _dt.strptime(hhmm, "%H:%M").strftime("%-I:%M %p")
    except (ValueError, TypeError):
        return hhmm


def _momentum_label(
    completed, total, at_risk, overdue,
    is_current, is_past,
    block_start_time: str | None = None,
    bucket_label: str | None = None,
) -> str:
    """One-line deterministic "feel" of a rhythm block.

    Pure function of completion-state + a couple of block-context fields.
    No new metric, no recompute — just naming a status the user can
    already see by counting items. For *future* blocks with items, names
    the block start time so the tile never feels empty.
    """
    if total == 0:
        return "Nothing scheduled."

    pct = completed / total if total else 0
    is_future = not is_current and not is_past

    if pct >= 1.0:
        return "Complete — great execution."
    if overdue >= 2:
        return f"{overdue} past due — let's recover the rhythm."
    if overdue == 1:
        return "1 past due — close the loop."
    if at_risk >= 2:
        return f"{at_risk} at risk — small actions now."

    if is_future:
        # The single most important rule: future blocks with items must
        # never feel empty. Tell the user when the block opens.
        if block_start_time:
            return f"Begins at {block_start_time}. Stay focused on the current block first."
        return "Coming up later today."

    if pct >= 0.75:
        return "Strong execution so far." if is_current or is_past else "Set up well."
    if pct >= 0.5:
        return "Good progress." if is_current else "Building."
    if pct >= 0.25:
        return "Building momentum." if is_current else "Just started."
    if completed > 0:
        return "Slow start — pick one and go."
    return "Not started yet." if is_current else "Coming up."


def _earliest_scheduled_time(items: list[dict]) -> str | None:
    """Return the earliest scheduled_time (HH:MM string) in an items list,
    or None if no item has one. Pre-formatted for direct display."""
    times = [i.get("scheduled_time") for i in items if i.get("scheduled_time")]
    if not times:
        return None
    earliest = min(times)
    # scheduled_time is stored as "HH:MM" 24h. Convert to 12h for display.
    try:
        from datetime import datetime as _dt
        return _dt.strptime(earliest, "%H:%M").strftime("%-I:%M %p")
    except (ValueError, TypeError):
        return earliest


def _bucket_index(key: str) -> int:
    for i, bucket in enumerate(RHYTHM_BUCKETS):
        if bucket["key"] == key:
            return i
    return -1
