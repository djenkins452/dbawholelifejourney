"""
COS-CX4: Temporal Execution Matching
=====================================

Matches unfinished high-priority tasks to available time windows in
today's schedule. This turns CoS from a reporter into a strategist.

"You have a 90-minute gap between your haircut and pickleball —
perfect for the quarterly report."

Performance target: < 5ms (uses already-loaded schedule data + 1 query).
Token budget: ~100 tokens max.
"""
import logging
from datetime import timedelta, datetime, time as dt_time

logger = logging.getLogger(__name__)

MAX_WINDOWS = 3
MIN_WINDOW_MINUTES = 30  # Don't suggest windows shorter than 30 min


def compute_execution_windows(user, now, cos_context=None):
    """
    Find free time windows today and match them to unfinished tasks.

    Args:
        user: Django User object
        now: timezone-aware datetime in user's timezone
        cos_context: optional dict from build_cos_context()

    Returns:
        str — formatted execution windows block, or "" if nothing to suggest.
    """
    try:
        today = now.date()

        # Step 1: Get today's committed time blocks
        busy_blocks = _get_busy_blocks(user, now, today, cos_context)

        # Step 2: Find free windows between now and end-of-day
        free_windows = _find_free_windows(now, busy_blocks)

        if not free_windows:
            return ""

        # Step 3: Get unfinished urgent tasks to match
        tasks = _get_matchable_tasks(user, today)

        if not tasks:
            return ""

        # Step 4: Match tasks to windows
        matches = _match_tasks_to_windows(tasks, free_windows)

        if not matches:
            return ""

        lines = ["=== SUGGESTED EXECUTION WINDOWS ==="]
        for task_title, window_start, window_end, duration_min in matches[:MAX_WINDOWS]:
            start_str = window_start.strftime('%I:%M %p').lstrip('0')
            end_str = window_end.strftime('%I:%M %p').lstrip('0')
            lines.append(
                f"  {task_title} \u2192 {start_str}\u2013{end_str} "
                f"({duration_min} min available)"
            )

        return "\n".join(lines)

    except Exception as e:
        logger.debug("Temporal matching skipped: %s", e)
        return ""


def _get_busy_blocks(user, now, today, cos_context):
    """
    Get all busy time blocks for today (calendar events + architecture blocks).
    Returns list of (start_dt, end_dt) tuples sorted by start time.
    """
    blocks = []

    # From calendar events
    try:
        from apps.calendar_engine.models import CalendarEvent

        events = CalendarEvent.objects.filter(
            user=user,
            start_dt__date=today,
            deleted_at__isnull=True,
        ).exclude(
            status='canceled'
        ).values_list('start_dt', 'end_dt')

        for start, end in events:
            if start and end:
                blocks.append((
                    start.astimezone(now.tzinfo),
                    end.astimezone(now.tzinfo)
                ))
    except Exception:
        pass

    # From architecture blocks (if in cos_context)
    if cos_context:
        for b in cos_context.get('today_blocks_summary', []):
            try:
                # Blocks have 'start' and 'end' as "HH:MM" strings
                start_parts = b['start'].split(':')
                end_parts = b['end'].split(':')
                block_start = now.replace(
                    hour=int(start_parts[0]),
                    minute=int(start_parts[1]),
                    second=0, microsecond=0
                )
                block_end = now.replace(
                    hour=int(end_parts[0]),
                    minute=int(end_parts[1]),
                    second=0, microsecond=0
                )
                if not b.get('completed'):
                    blocks.append((block_start, block_end))
            except (ValueError, KeyError, IndexError):
                continue

    # Sort and deduplicate overlapping blocks
    blocks.sort(key=lambda x: x[0])
    return _merge_overlapping(blocks)


def _merge_overlapping(blocks):
    """Merge overlapping time blocks."""
    if not blocks:
        return []

    merged = [blocks[0]]
    for start, end in blocks[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            # Overlapping — extend
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _find_free_windows(now, busy_blocks):
    """
    Find free windows between now and end-of-reasonable-day (9 PM).
    Returns list of (window_start, window_end, duration_minutes).
    """
    # Round up 'now' to next 15-minute mark for cleaner suggestions
    minute = now.minute
    round_up = 15 - (minute % 15) if minute % 15 != 0 else 0
    search_start = now + timedelta(minutes=round_up)
    search_start = search_start.replace(second=0, microsecond=0)

    # End of reasonable day: 9 PM
    end_of_day = now.replace(hour=21, minute=0, second=0, microsecond=0)

    if search_start >= end_of_day:
        return []

    windows = []
    current = search_start

    for block_start, block_end in busy_blocks:
        if block_start > current and block_start > search_start:
            # Free window found between current and next block
            window_start = max(current, search_start)
            window_end = min(block_start, end_of_day)
            duration = int((window_end - window_start).total_seconds() / 60)
            if duration >= MIN_WINDOW_MINUTES:
                windows.append((window_start, window_end, duration))
        current = max(current, block_end)

    # Check for window after last block
    if current < end_of_day:
        window_start = max(current, search_start)
        duration = int((end_of_day - window_start).total_seconds() / 60)
        if duration >= MIN_WINDOW_MINUTES:
            windows.append((window_start, end_of_day, duration))

    return windows


def _get_matchable_tasks(user, today):
    """Get unfinished tasks prioritized for matching."""
    try:
        from apps.life.models import Task

        # Overdue + due today, ordered by urgency
        tasks = list(
            Task.objects.filter(
                user=user,
                completion_status='pending',
                due_date__lte=today,
            ).order_by(
                'due_date',  # Oldest first (most overdue)
                'priority',  # 'now' < 'soon' < 'someday' alphabetically
            ).values_list('title', 'priority')[:5]
        )
        return tasks
    except Exception:
        return []


def _match_tasks_to_windows(tasks, free_windows):
    """
    Simple matching: assign highest-priority tasks to earliest windows.
    Returns list of (task_title, window_start, window_end, duration_min).
    """
    matches = []
    window_idx = 0

    for title, priority in tasks:
        if window_idx >= len(free_windows):
            break

        window_start, window_end, duration = free_windows[window_idx]
        matches.append((title, window_start, window_end, duration))
        window_idx += 1

    return matches
