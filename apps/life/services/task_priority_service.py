# ==============================================================================
# File: apps/life/services/task_priority_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic task priority summary — no DB, no LLM, pure function
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-24
# ==============================================================================
"""
Deterministic Task Priority Summary.

Converts canonical task state into a short ordered summary of what
matters right now. Follows proven Health architecture.

Architecture: raw data → canonical state → THIS → coaching → UI / CoS

Public API:
    build_task_priority_summary(task_state, current_dt) -> dict

Rules:
    - Pure function: no DB queries, no user object, no cache writes, no LLM
    - Min 2, max 4 items
    - Overdue always dominates (forced to index 0)
    - Deterministic, time-aware
"""

import logging

logger = logging.getLogger(__name__)

# ── Priority levels ──────────────────────────────────────────────────────────

HIGH = "high"
MEDIUM = "medium"
LOW = "low"

_PRIORITY_ORDER = {HIGH: 0, MEDIUM: 1, LOW: 2}

MAX_ITEMS = 4
MIN_ITEMS = 2

_HEADLINES = {
    HIGH: "Tasks need attention",
    MEDIUM: "A few things to focus on",
    LOW: "You're on track",
}


def _item(key, priority, message, icon="task"):
    return {
        "key": key,
        "priority": priority,
        "message": message,
        "icon": icon,
    }


# ── Item evaluators ─────────────────────────────────────────────────────────

def _eval_overdue(task_state):
    """Overdue tasks. Always current from state."""
    items = []
    overdue_count = task_state.get("overdue_count", 0)
    if overdue_count > 0:
        s = "s" if overdue_count != 1 else ""
        items.append(_item(
            "tasks_overdue", HIGH,
            f"{overdue_count} task{s} overdue", "alert",
        ))

    # Foundational overdue escalation
    nn_overdue = task_state.get("overdue_nn_count", 0)
    if nn_overdue > 0 and overdue_count > nn_overdue:
        # Only add if there's a meaningful distinction
        s = "s" if nn_overdue != 1 else ""
        items.append(_item(
            "foundational_overdue", HIGH,
            f"{nn_overdue} foundational task{s} overdue", "alert",
        ))

    return items


def _eval_next_task(task_state):
    """Next actionable task."""
    next_up = task_state.get("next_up_task")
    if not next_up:
        return []

    title = next_up.get("title", "")
    scheduled = next_up.get("scheduled_time")
    reason = next_up.get("reason", "")

    if not title:
        return []

    # Format message based on reason
    if reason in ("past_due_date", "missed_scheduled_time"):
        msg = f"Next: {title} (overdue)"
        return [_item("next_task_overdue", HIGH, msg, "next")]
    elif scheduled:
        msg = f"Next: {title} at {scheduled}"
        return [_item("next_task", MEDIUM, msg, "next")]
    else:
        msg = f"Next: {title}"
        return [_item("next_task", MEDIUM, msg, "next")]


def _eval_due_today(task_state):
    """Tasks due today count."""
    today_detail = task_state.get("due_today_tasks_detail", [])
    count = len(today_detail) if today_detail else 0

    if count == 0:
        return []

    # Check how many are due_now or due_soon
    urgent = [t for t in today_detail
              if t.get("time_proximity") in ("due_now", "due_soon")]

    if urgent:
        n = len(urgent)
        s = "s" if n != 1 else ""
        return [_item("tasks_due_soon", MEDIUM,
                       f"{n} task{s} due soon", "clock")]

    s = "s" if count != 1 else ""
    return [_item("tasks_due_today", MEDIUM,
                   f"{count} task{s} due today", "clock")]


def _eval_upcoming(task_state):
    """Tomorrow's tasks."""
    tomorrow_count = task_state.get("due_tomorrow_count", 0)
    if tomorrow_count > 0:
        s = "s" if tomorrow_count != 1 else ""
        return [_item("tasks_tomorrow", LOW,
                       f"{tomorrow_count} task{s} due tomorrow", "calendar")]
    return []


def _eval_momentum(task_state):
    """Completion momentum — reinforcement."""
    detail = task_state.get("completed_today_detail", {})
    signal = detail.get("momentum_signal", "low")
    count = detail.get("count", 0)

    if signal == "high" and count >= 5:
        return [_item("momentum_high", LOW,
                       "You're making great progress today", "check")]
    elif signal == "medium" and count >= 2:
        return [_item("momentum_moderate", LOW,
                       "Good progress so far today", "check")]

    return []


def _eval_pressure(task_state):
    """Task pressure — overdue + due today combined."""
    overdue = task_state.get("overdue_count", 0)
    today_detail = task_state.get("due_today_tasks_detail", [])
    today_count = len(today_detail) if today_detail else 0
    total = overdue + today_count

    if total == 0:
        return [_item("tasks_clear", LOW,
                       "No pressing tasks right now", "check")]
    return []


# ── Main builder ─────────────────────────────────────────────────────────────

def build_task_priority_summary(task_state, current_dt):
    """
    Build deterministic task priority summary from canonical state.

    Args:
        task_state: dict from get_module_state(user, 'tasks')
        current_dt: user's current local aware datetime

    Returns:
        dict with headline, items (min 2 / max 4), flags, generated_at
    """
    task_state = task_state or {}

    # Collect candidates
    candidates = []
    candidates.extend(_eval_overdue(task_state))
    candidates.extend(_eval_next_task(task_state))
    candidates.extend(_eval_due_today(task_state))
    candidates.extend(_eval_upcoming(task_state))
    candidates.extend(_eval_momentum(task_state))
    candidates.extend(_eval_pressure(task_state))

    # Sort by priority
    candidates.sort(key=lambda x: _PRIORITY_ORDER.get(x["priority"], 99))

    # Deduplicate by key prefix (avoid "tasks_overdue" + "next_task_overdue" both)
    seen_keys = set()
    selected = []
    for item in candidates:
        if len(selected) >= MAX_ITEMS:
            break
        # Skip foundational overdue if already have general overdue
        if item["key"] == "foundational_overdue" and "tasks_overdue" in seen_keys:
            continue
        # Skip next_task_overdue if already have tasks_overdue
        if item["key"] == "next_task_overdue" and "tasks_overdue" in seen_keys:
            # Convert to regular next_task instead
            item = _item("next_task", MEDIUM,
                         item["message"].replace(" (overdue)", ""), "next")
        seen_keys.add(item["key"])
        selected.append(item)

    # Enforce overdue at index 0
    overdue_items = [i for i in selected if i["key"] == "tasks_overdue"]
    if overdue_items:
        selected = [i for i in selected if i["key"] != "tasks_overdue"]
        selected.insert(0, overdue_items[0])

    # Minimum fill — add low items if we have < 2
    if len(selected) < MIN_ITEMS:
        # Try tasks_clear or momentum
        for item in candidates:
            if item["key"] not in seen_keys and len(selected) < MIN_ITEMS:
                selected.append(item)
                seen_keys.add(item["key"])

    # Trim to max
    selected = selected[:MAX_ITEMS]

    # Derive priority level
    if any(i["priority"] == HIGH for i in selected):
        priority_level = HIGH
    elif any(i["priority"] == MEDIUM for i in selected):
        priority_level = MEDIUM
    else:
        priority_level = LOW

    headline = _HEADLINES.get(priority_level, _HEADLINES[LOW])

    flags = {
        "has_overdue": any(i["key"] == "tasks_overdue" for i in selected),
        "has_upcoming": any(i["key"] in ("tasks_due_soon", "tasks_due_today")
                           for i in selected),
        "has_momentum": any(i["key"].startswith("momentum_") for i in selected),
    }

    return {
        "headline": headline,
        "priority_level": priority_level,
        "items": selected,
        "flags": flags,
        "generated_at": current_dt.isoformat() if current_dt else None,
    }
