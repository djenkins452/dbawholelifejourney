"""
Today Engine — Canonical Day Context

Single source of truth for "what does today look like."
Collects routines, tasks, and calendar events into a unified dataset,
applies all time logic ONCE, and returns pre-bucketed sections.

ALL renderers (day agenda, check-in, CoS) read from this engine.
No renderer computes time buckets or merges data — that happens here.

RULES:
- Compute once, render everywhere
- No aggregation (every item is individually named)
- No coaching, commentary, or interpretation
- Chronological sort on all sections
- Foundation items appear in Foundation AND their time bucket
"""

import logging
from datetime import datetime, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Items within this window from now are "coming up"
COMING_UP_WINDOW_MINUTES = 90


def get_today_context(user) -> dict:
    """Build the canonical today context for a user.

    Returns:
        {
            "all_items": [...],       # every item, normalized
            "foundation": [...],      # priority == foundational (sorted)
            "overdue": [...],         # scheduled < now, not completed (sorted)
            "coming_up": [...],       # now <= scheduled <= now+90min (sorted)
            "later": [...],           # scheduled > now+90min (sorted)
            "completed": [...],       # completed items (sorted)
            "next": str,              # locked next action
        }

    Each item in all lists:
        {"id": str, "name": str, "scheduled_time": datetime|None,
         "time_str": str|None, "completed": bool,
         "priority": str|None, "source": str}
    """
    from apps.ai.cos_fact_statements import build_locked_facts, build_locked_next_action
    from apps.core.execution.execution_truth_engine import get_execution_truth
    from apps.core.utils import get_user_now

    try:
        user_now = get_user_now(user)
    except Exception:
        user_now = timezone.localtime()

    truth = get_execution_truth(user)
    facts = build_locked_facts(user)
    raw = facts.get("_raw", {})

    window_end = user_now + timedelta(minutes=COMING_UP_WINDOW_MINUTES)

    # ── Step 1: Collect + normalize from all sources ──
    all_items = []
    all_items.extend(_collect_routine_items(truth, user_now))
    all_items.extend(_collect_task_items(user, user_now))
    all_items.extend(_collect_calendar_items(user, user_now))

    # Add domain-level completions that aren't already in routine items
    _add_domain_completions(raw, all_items)

    # ── Step 2: Partition into buckets ──
    _TIME_MAX = user_now.replace(hour=23, minute=59, second=59)
    foundation = []
    overdue = []
    coming_up = []
    later = []
    completed = []

    seen_in_bucket = set()
    seen_completed = set()
    seen_foundation = set()

    for item in all_items:
        name = item["name"]
        time_str = item.get("time_str")
        sched = item["scheduled_time"]
        is_done = item["completed"]
        is_found = item.get("priority") == "foundational"
        sort_time = sched or _TIME_MAX
        label = f"{name} ({time_str})" if time_str else name

        # Completed → completed section
        if is_done:
            if label not in seen_completed:
                seen_completed.add(label)
                completed.append(_bucket_entry(sort_time, label, item))
            continue

        # Foundation → foundation section (AND time bucket below)
        if is_found:
            if label not in seen_foundation:
                seen_foundation.add(label)
                foundation.append(_bucket_entry(sort_time, label, item))

        # Time bucket (only if scheduled_time exists)
        if sched is None:
            continue

        bucket_key = (name, time_str)
        if bucket_key in seen_in_bucket:
            continue
        seen_in_bucket.add(bucket_key)

        if sched < user_now:
            overdue.append(_bucket_entry(sched, label, item))
        elif sched <= window_end:
            coming_up.append(_bucket_entry(sched, label, item))
        else:
            later.append(_bucket_entry(sched, label, item))

    # ── Step 3: Sort all sections chronologically ──
    foundation = _sort_by_time(foundation)
    overdue = _sort_by_time(overdue)
    coming_up = _sort_by_time(coming_up)
    later = _sort_by_time(later)
    completed = _sort_by_time(completed)

    # ── Step 4: Next action ──
    next_action = facts.get("next_action", "")
    if not next_action or next_action == "Unable to determine.":
        next_action = "Start with your next planned item."

    return {
        "all_items": all_items,
        "foundation": foundation,
        "overdue": overdue,
        "coming_up": coming_up,
        "later": later,
        "completed": completed,
        "next": next_action,
    }


# ---------------------------------------------------------------------------
# Bucket entry + sort
# ---------------------------------------------------------------------------

def _bucket_entry(sort_time, label: str, item: dict) -> dict:
    """Create a bucket entry with sort key and display label."""
    return {
        "sort_time": sort_time,
        "label": label,
        "item": item,
    }


def _sort_by_time(entries: list) -> list:
    """Sort bucket entries by time ascending. Stable sort."""
    return sorted(entries, key=lambda x: x["sort_time"])


# ---------------------------------------------------------------------------
# Source collectors (normalized output)
# ---------------------------------------------------------------------------

def _collect_routine_items(truth: dict, user_now) -> list:
    """Collect routine items from execution truth."""
    items = []
    raw_items = truth.get("routines", {}).get("_raw_items", {})

    for _window, window_items in raw_items.items():
        for item in window_items:
            name = (item.get("item_name") or "").strip()
            if not name:
                continue

            time_str = item.get("scheduled_time")
            sched = None
            if time_str:
                sched = _parse_time_today(time_str, user_now)

            importance = (item.get("importance") or "flexible").lower()

            items.append({
                "id": f"routine:{item.get('schedule_id', '')}",
                "name": name,
                "scheduled_time": sched,
                "time_str": time_str,
                "completed": bool(item.get("is_completed")),
                "priority": importance,
                "source": "routine",
            })

    return items


def _collect_task_items(user, user_now) -> list:
    """Collect non-routine tasks due today."""
    items = []
    try:
        from apps.life.models import Task

        today = user_now.date() if hasattr(user_now, "date") else user_now
        today_tasks = (
            Task.objects
            .filter(user=user, due_date=today, is_routine=False)
            .exclude(status="deleted")
        )

        for task in today_tasks:
            sched = None
            time_str = None
            if task.scheduled_time:
                sched = user_now.replace(
                    hour=task.scheduled_time.hour,
                    minute=task.scheduled_time.minute,
                    second=0, microsecond=0,
                )
                time_str = task.scheduled_time.strftime("%I:%M %p").lstrip("0")

            commitment = (
                getattr(task, "commitment_level", "") or "flexible"
            ).lower()

            items.append({
                "id": f"task:{task.pk}",
                "name": (task.title or "").strip(),
                "scheduled_time": sched,
                "time_str": time_str,
                "completed": task.completion_status == "completed",
                "priority": commitment,
                "source": "task",
            })
    except ImportError:
        pass
    except Exception:
        logger.warning("[TODAY ENGINE] Task collection failed", exc_info=True)

    return items


def _collect_calendar_items(user, user_now) -> list:
    """Collect calendar events for today (excludes routine/task-sourced)."""
    items = []
    try:
        from apps.calendar_engine.models import CalendarEvent

        today = user_now.date() if hasattr(user_now, "date") else user_now
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
            sched = item_time.replace(second=0, microsecond=0)

            commitment = (
                getattr(event, "commitment_level", "") or "important"
            ).lower()

            items.append({
                "id": f"calendar:{event.pk}",
                "name": (event.title or "").strip(),
                "scheduled_time": sched,
                "time_str": time_str,
                "completed": event.status == CalendarEvent.STATUS_COMPLETED,
                "priority": commitment,
                "source": "calendar",
            })
    except ImportError:
        pass
    except Exception:
        logger.warning("[TODAY ENGINE] Calendar collection failed", exc_info=True)

    return items


def _add_domain_completions(raw: dict, all_items: list, user_now=None):
    """Add domain-level completions (Prayer, Bible, etc.) if not already present."""
    existing_names = {item["name"] for item in all_items if item["completed"]}

    for done_key, label in [
        ("prayer_done", "Prayer"),
        ("bible_done", "Bible reading"),
        ("workout_done", "Workout"),
        ("journal_done", "Journal entry"),
    ]:
        if raw.get(done_key) and label not in existing_names:
            all_items.append({
                "id": f"domain:{label.lower().replace(' ', '_')}",
                "name": label,
                "scheduled_time": None,
                "time_str": None,
                "completed": True,
                "priority": None,
                "source": "domain",
            })


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
