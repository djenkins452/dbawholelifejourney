"""
Deterministic Day Agenda Renderer — Pure Truth, Time-Bucketed

Renders a full day view organized by Foundation + time buckets.
The LLM is NOT involved. Every item is a real named item from
execution truth.

DATA SOURCES (exclusively):
- Execution Truth Engine (get_execution_truth) — routines
- Task model (due_date=today, non-routine) — tasks
- CalendarEvent model (start_dt=today, non-canceled) — calendar
- Locked Next Action (build_locked_next_action)
- Current time (timezone-aware, for bucket assignment)

All sources are normalized into a unified item format before bucketing.
No source receives preferential treatment.

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

    # Collect ALL items for today: routines + tasks + calendar
    all_items = _collect_all_today_items(user, truth, user_now)

    # Partition into buckets — all store (sort_time, label) tuples
    # sort_time = item_time if available, else datetime.max (sorts last)
    _TIME_MAX = user_now.replace(hour=23, minute=59, second=59)
    foundation = []   # (sort_time, label)
    overdue = []      # (sort_time, label)
    coming_up = []    # (sort_time, label)
    later = []        # (sort_time, label)
    completed = []    # (sort_time, label)

    seen_in_bucket = set()  # track (name, time_str) to prevent dupes
    seen_completed = set()
    seen_foundation = set()

    for item in all_items:
        name = item["name"]
        time_str = item["time_str"]
        item_time = item["item_time"]  # datetime or None
        is_completed = item["is_completed"]
        is_foundational = item["is_foundational"]
        sort_time = item_time or _TIME_MAX

        label = f"{name} ({time_str})" if time_str else name

        # Completed items go to completed section
        if is_completed:
            if label not in seen_completed:
                seen_completed.add(label)
                completed.append((sort_time, label))
            continue

        # Foundation section (always, regardless of time bucket)
        if is_foundational:
            if label not in seen_foundation:
                seen_foundation.add(label)
                foundation.append((sort_time, label))

        # Time bucket assignment (only if scheduled_time exists)
        if item_time is None:
            continue

        bucket_key = (name, time_str)
        if bucket_key in seen_in_bucket:
            continue
        seen_in_bucket.add(bucket_key)

        if item_time < user_now:
            overdue.append((item_time, label))
        elif item_time <= window_end:
            coming_up.append((item_time, label))
        else:
            later.append((item_time, label))

    # Sort ALL sections by time ascending (chronological)
    foundation = _sort_by_time(foundation)
    overdue = _sort_by_time(overdue)
    coming_up = _sort_by_time(coming_up)
    later = _sort_by_time(later)
    completed = _sort_by_time(completed)

    # Also add domain-level completed items (Prayer, Bible, etc.)
    raw = facts.get("_raw", {})
    _add_domain_completed(raw, completed, seen_completed)

    # Unified formatter — all sections are (sort_time, label) tuples
    def _fmt(bucket):
        if not bucket:
            return "• None"
        return "\n".join(f"• {label}" for _, label in bucket)

    # Next action (from system, no modification)
    next_action = facts.get("next_action", "")
    if not next_action or next_action == "Unable to determine.":
        next_action = "Start with your next planned item."

    lines = [
        "Today",
        "",
        "Foundation:",
        _fmt(foundation),
        "",
        "Overdue now:",
        _fmt(overdue),
        "",
        "Coming up next:",
        _fmt(coming_up),
        "",
        "Later today:",
        _fmt(later),
        "",
        "Completed:",
        _fmt(completed),
        "",
        f"Next: {next_action}",
    ]

    output = "\n".join(lines)
    _validate_output(output)
    return output


# ---------------------------------------------------------------------------
# Item collection
# ---------------------------------------------------------------------------

def _collect_all_today_items(user, truth: dict, user_now) -> list:
    """Collect ALL items for today: routines + tasks + calendar events.

    Returns a unified list of normalized dicts:
        {"name": str, "time_str": str|None, "item_time": datetime|None,
         "is_completed": bool, "is_foundational": bool, "source": str}

    All sources flow through the same bucketing logic — no source bias.
    """
    items = []
    items.extend(_collect_routine_items(truth, user_now))
    items.extend(_collect_task_items(user, user_now))
    items.extend(_collect_calendar_items(user, user_now))
    return items


def _collect_routine_items(truth: dict, user_now) -> list:
    """Collect routine items from execution truth."""
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

            items.append({
                "name": name,
                "time_str": time_str,
                "item_time": item_time,
                "is_completed": bool(item.get("is_completed")),
                "is_foundational": importance == "foundational",
                "source": "routine",
            })

    return items


def _collect_task_items(user, user_now) -> list:
    """Collect tasks due today from the Task model.

    Only includes non-routine tasks with a due_date of today.
    Tasks with scheduled_time get time-bucketed; others are excluded
    from time buckets (same rule as routines).
    """
    items = []
    try:
        from apps.life.models import Task

        today = user_now.date() if hasattr(user_now, 'date') else user_now
        today_tasks = (
            Task.objects
            .filter(user=user, due_date=today, is_routine=False)
            .exclude(status='deleted')
        )

        for task in today_tasks:
            time_str = None
            item_time = None
            if task.scheduled_time:
                item_time = user_now.replace(
                    hour=task.scheduled_time.hour,
                    minute=task.scheduled_time.minute,
                    second=0, microsecond=0,
                )
                time_str = task.scheduled_time.strftime("%I:%M %p").lstrip("0")

            commitment = (
                getattr(task, "commitment_level", "") or "flexible"
            ).lower()

            items.append({
                "name": (task.title or "").strip(),
                "time_str": time_str,
                "item_time": item_time,
                "is_completed": task.completion_status == "completed",
                "is_foundational": commitment == "foundational",
                "source": "task",
            })
    except ImportError:
        pass
    except Exception:
        logger.warning("[DAY RENDERER] Task collection failed", exc_info=True)

    return items


def _collect_calendar_items(user, user_now) -> list:
    """Collect calendar events for today.

    Only includes non-canceled events whose start_dt falls today.
    Excludes events sourced from routines/tasks to prevent duplication
    (those are already collected from their primary source).
    """
    items = []
    try:
        from apps.calendar_engine.models import CalendarEvent

        today = user_now.date() if hasattr(user_now, 'date') else user_now
        # Exclude sources that are already collected via routines/tasks
        _EXCLUDED_SOURCES = {
            CalendarEvent.SOURCE_TASK,
            CalendarEvent.SOURCE_FAITH_ROUTINE,
            CalendarEvent.SOURCE_WORKOUT_SCHEDULE,
            CalendarEvent.SOURCE_MEDICINE_SCHEDULE,
        }

        events = (
            CalendarEvent.objects
            .filter(user=user, start_dt__date=today)
            .exclude(status=CalendarEvent.STATUS_CANCELED)
            .exclude(source_type__in=_EXCLUDED_SOURCES)
        )

        for event in events:
            item_time = event.start_dt
            if timezone.is_aware(item_time):
                item_time = timezone.localtime(item_time)

            time_str = item_time.strftime("%I:%M %p").lstrip("0")

            commitment = (
                getattr(event, "commitment_level", "") or "important"
            ).lower()

            items.append({
                "name": (event.title or "").strip(),
                "time_str": time_str,
                "item_time": item_time.replace(
                    second=0, microsecond=0,
                ),
                "is_completed": event.status == CalendarEvent.STATUS_COMPLETED,
                "is_foundational": commitment == "foundational",
                "source": "calendar",
            })
    except ImportError:
        pass
    except Exception:
        logger.warning(
            "[DAY RENDERER] Calendar collection failed", exc_info=True,
        )

    return items


def _sort_by_time(items):
    """Sort (sort_time, label) tuples by time ascending.

    Python's sort is stable — items with identical times keep their
    relative insertion order.
    """
    return sorted(items, key=lambda x: x[0])


def _add_domain_completed(raw: dict, completed: list, seen: set):
    """Add domain-level completed items (Prayer, Bible, etc.) if not already listed.

    These don't have specific times, so they sort last within Completed.
    """
    _TIME_MAX = datetime.max
    for done_key, label in [
        ("prayer_done", "Prayer"),
        ("bible_done", "Bible reading"),
        ("workout_done", "Workout"),
        ("journal_done", "Journal entry"),
    ]:
        if raw.get(done_key) and label not in seen:
            seen.add(label)
            completed.append((_TIME_MAX, label))


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
