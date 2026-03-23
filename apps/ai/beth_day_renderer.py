"""
Deterministic Day Agenda Renderer — Pure Truth, Time-Bucketed

Renders a full day view organized by Foundation + time buckets.
The LLM is NOT involved. Every item is a real named item from
execution truth.

DATA SOURCES (exclusively):
- Execution Truth Engine (get_execution_truth)
- Locked Next Action (build_locked_next_action)
- Current time (timezone-aware, for bucket assignment)

RULES:
- NO aggregation (no counts, no grouping, no "X items")
- NO coaching, commentary, or interpretation
- Foundation items appear in Foundation AND their time bucket
- Items without scheduled_time are EXCLUDED from time buckets
- Each item appears ONCE per time bucket
- Sorting within each bucket = ascending by scheduled time
"""

import logging
from datetime import datetime, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Only show "coming up" items within this window from now
COMING_UP_WINDOW_MINUTES = 90

# Banned words — output must never contain these
_BANNED_WORDS = frozenset({"items", "tasks", "routines"})

_SAFE_FALLBACK = (
    "Today\n\n"
    "Foundation:\n• None\n\n"
    "Overdue now:\n• None\n\n"
    "Coming up next:\n• None\n\n"
    "Later today:\n• None\n\n"
    "Completed:\n• None\n\n"
    "Next: Start with your next planned item."
)


def render_day_agenda(user) -> str:
    """Render a deterministic day agenda from execution truth.

    Returns a structured, factual day view with:
    - Foundation items
    - Overdue / Coming up / Later time buckets
    - Completed items
    - Next action

    This output is FINAL — it is NOT passed to an LLM for rephrasing.
    """
    try:
        return _render_day_from_truth(user)
    except Exception:
        logger.error(
            "[DAY RENDERER] Failed for user=%s, returning safe fallback",
            user.id, exc_info=True,
        )
        return _SAFE_FALLBACK


# ---------------------------------------------------------------------------
# Core renderer
# ---------------------------------------------------------------------------

def _render_day_from_truth(user) -> str:
    """Build the day agenda from execution truth."""
    from apps.ai.cos_fact_statements import build_locked_facts
    from apps.core.execution.execution_truth_engine import get_execution_truth
    from apps.core.utils import get_user_now

    facts = build_locked_facts(user)
    truth = get_execution_truth(user)

    try:
        user_now = get_user_now(user)
    except Exception:
        user_now = timezone.localtime()

    window_end = user_now + timedelta(minutes=COMING_UP_WINDOW_MINUTES)

    # Collect all routine items with parsed times
    all_items = _collect_all_items(truth, user_now)

    # Partition into buckets
    foundation = []
    overdue = []
    coming_up = []
    later = []
    completed = []

    seen_in_bucket = set()  # track (name, time_str) to prevent dupes

    for item in all_items:
        name = item["name"]
        time_str = item["time_str"]
        item_time = item["item_time"]  # datetime or None
        is_completed = item["is_completed"]
        is_foundational = item["is_foundational"]

        # Completed items go to completed section
        if is_completed:
            label = f"{name} ({time_str})" if time_str else name
            if label not in completed:
                completed.append(label)
            continue

        # Foundation section (always, regardless of time bucket)
        if is_foundational:
            f_label = f"{name} ({time_str})" if time_str else name
            if f_label not in foundation:
                foundation.append(f_label)

        # Time bucket assignment (only if scheduled_time exists)
        if item_time is None:
            continue

        bucket_key = (name, time_str)
        if bucket_key in seen_in_bucket:
            continue
        seen_in_bucket.add(bucket_key)

        label = f"{name} ({time_str})"

        if item_time < user_now:
            overdue.append((item_time, label))
        elif item_time <= window_end:
            coming_up.append((item_time, label))
        else:
            later.append((item_time, label))

    # Sort each bucket by time ascending
    overdue.sort(key=lambda x: x[0])
    coming_up.sort(key=lambda x: x[0])
    later.sort(key=lambda x: x[0])

    # Also add domain-level completed items (Prayer, Bible, etc.)
    raw = facts.get("_raw", {})
    _add_domain_completed(raw, completed)

    # Build output sections
    def _fmt_bucket(items_with_time):
        if not items_with_time:
            return "• None"
        return "\n".join(f"• {label}" for _, label in items_with_time)

    def _fmt_list(items):
        if not items:
            return "• None"
        return "\n".join(f"• {item}" for item in items)

    # Next action (from system, no modification)
    next_action = facts.get("next_action", "")
    if not next_action or next_action == "Unable to determine.":
        next_action = "Start with your next planned item."

    lines = [
        "Today",
        "",
        "Foundation:",
        _fmt_list(foundation),
        "",
        "Overdue now:",
        _fmt_bucket(overdue),
        "",
        "Coming up next:",
        _fmt_bucket(coming_up),
        "",
        "Later today:",
        _fmt_bucket(later),
        "",
        "Completed:",
        _fmt_list(completed),
        "",
        f"Next: {next_action}",
    ]

    output = "\n".join(lines)
    _validate_output(output)
    return output


# ---------------------------------------------------------------------------
# Item collection
# ---------------------------------------------------------------------------

def _collect_all_items(truth: dict, user_now) -> list:
    """Collect all routine items from execution truth with parsed times.

    Returns list of dicts:
        {"name": str, "time_str": str|None, "item_time": datetime|None,
         "is_completed": bool, "is_foundational": bool}
    """
    items = []
    raw_items = truth.get("routines", {}).get("_raw_items", {})

    for _window, window_items in raw_items.items():
        for item in window_items:
            name = (item.get("item_name") or "").strip()
            if not name:
                continue

            time_str = item.get("scheduled_time")  # e.g. "6:15 AM" or None
            item_time = None
            if time_str:
                item_time = _parse_time_today(time_str, user_now)

            importance = (item.get("importance") or "flexible").lower()
            is_foundational = importance == "foundational"

            items.append({
                "name": name,
                "time_str": time_str,
                "item_time": item_time,
                "is_completed": bool(item.get("is_completed")),
                "is_foundational": is_foundational,
            })

    return items


def _add_domain_completed(raw: dict, completed: list):
    """Add domain-level completed items (Prayer, Bible, etc.) if not already listed."""
    if raw.get("prayer_done") and "Prayer" not in completed:
        completed.append("Prayer")
    if raw.get("bible_done") and "Bible reading" not in completed:
        completed.append("Bible reading")
    if raw.get("workout_done") and "Workout" not in completed:
        completed.append("Workout")
    if raw.get("journal_done") and "Journal entry" not in completed:
        completed.append("Journal entry")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_time_today(time_str: str, now) -> datetime:
    """Parse a time string like '6:15 AM' into a datetime for today."""
    try:
        parsed = datetime.strptime(time_str.strip(), "%I:%M %p")
        return now.replace(
            hour=parsed.hour, minute=parsed.minute,
            second=0, microsecond=0,
        )
    except (ValueError, AttributeError):
        return None


def _validate_output(output: str):
    """Validate that output contains no aggregation language."""
    output_lower = output.lower()
    for word in _BANNED_WORDS:
        if word in output_lower:
            logger.warning(
                "[DAY RENDERER] VALIDATION: banned word '%s' found in output",
                word,
            )
