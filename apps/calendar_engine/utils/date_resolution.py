"""
Deterministic date resolution for calendar events.

Phase 9: All weekday/relative-date resolution happens server-side,
never trusting LLM-provided date computations.

Phase 9.1: Same-day weekday + time logic — if the requested time has
already passed today, schedule next week instead.
"""

import datetime as dt
import re
from typing import Optional

from apps.core.utils import get_user_now, get_user_today

# ISO weekday mapping (Monday=1 .. Sunday=7)
WEEKDAY_NAMES = {
    'monday': 1, 'mon': 1,
    'tuesday': 2, 'tue': 2, 'tues': 2,
    'wednesday': 3, 'wed': 3,
    'thursday': 4, 'thu': 4, 'thur': 4, 'thurs': 4,
    'friday': 5, 'fri': 5,
    'saturday': 6, 'sat': 6,
    'sunday': 7, 'sun': 7,
}

_ISO_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def resolve_weekday_to_date(user, start_date_str: str,
                            reference_dt: dt.datetime = None,
                            start_time: Optional[dt.time] = None) -> dt.date:
    """
    Deterministically resolve a date string to a concrete date.

    Supported inputs:
    - YYYY-MM-DD  → parsed directly
    - "today"     → user's local today
    - "tomorrow"  → user's local today + 1
    - Weekday name (e.g. "wednesday", "fri") → next occurrence

    Same-day weekday logic (Phase 9.1):
    - If target weekday == today AND start_time is provided:
        - If start_time > reference_dt.time() → schedule TODAY
        - If start_time <= reference_dt.time() → schedule NEXT WEEK (+7 days)
    - If target weekday == today AND start_time is None:
        - Schedule TODAY (preserve original behavior)

    Args:
        user: Django user with preferences.timezone_iana
        start_date_str: The date string to resolve
        reference_dt: Override for the "now" reference (for testing).
                      If None, uses get_user_now(user).
        start_time: The event's start time, used for same-day weekday
                    disambiguation. If None, same-day defaults to today.

    Returns:
        A concrete datetime.date

    Raises:
        ValueError: If start_date_str cannot be resolved
    """
    if not start_date_str or not isinstance(start_date_str, str):
        raise ValueError(f"Invalid start_date_str: {start_date_str!r}")

    cleaned = start_date_str.strip().lower()

    # --- ISO date literal ---
    if _ISO_DATE_RE.match(cleaned):
        try:
            return dt.date.fromisoformat(cleaned)
        except ValueError:
            raise ValueError(f"Invalid ISO date: {cleaned!r}")

    # --- Relative dates ---
    if reference_dt is None:
        reference_dt = get_user_now(user)

    user_today = reference_dt.date()

    if cleaned in ('today', 'now'):
        return user_today

    if cleaned == 'tomorrow':
        return user_today + dt.timedelta(days=1)

    # --- Weekday name ---
    iso_weekday = WEEKDAY_NAMES.get(cleaned)
    if iso_weekday is not None:
        return _next_weekday(user_today, iso_weekday, reference_dt, start_time)

    raise ValueError(
        f"Cannot resolve date from: {start_date_str!r}. "
        f"Expected YYYY-MM-DD, 'today', 'tomorrow', or a weekday name."
    )


def _next_weekday(today: dt.date, target_iso_weekday: int,
                  reference_dt: dt.datetime,
                  start_time: Optional[dt.time] = None) -> dt.date:
    """
    Compute the next occurrence of target_iso_weekday (1=Mon..7=Sun).

    Same-day logic:
    - If start_time is provided and has already passed → next week (+7)
    - If start_time is provided and is still in the future → today
    - If start_time is None → today (default)
    """
    current_iso_weekday = today.isoweekday()  # 1=Mon..7=Sun
    days_ahead = (target_iso_weekday - current_iso_weekday) % 7

    if days_ahead == 0:
        # Same weekday as today — check if time has passed
        if start_time is not None and start_time <= reference_dt.time():
            # Requested time already passed today → next week
            return today + dt.timedelta(days=7)
        # Time is still in the future (or no time given) → today
        return today

    return today + dt.timedelta(days=days_ahead)
