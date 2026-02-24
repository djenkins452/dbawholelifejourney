"""
Deterministic date resolution for calendar events.

Phase 9: All weekday/relative-date resolution happens server-side,
never trusting LLM-provided date computations.

Phase 9.1: Same-day weekday + time logic — if the requested time has
already passed today, schedule next week instead.

Phase 9.2: "next <weekday>" support — "next Wednesday" always means the
Wednesday of the *following* week, never this week.

Phase 9.3: Enhanced relative date resolution — supports "last <weekday>",
"previous <weekday>", "<N> weeks from now", "in <N> days",
"<N> weeks ago", "<N> days ago", "yesterday".
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

# Number words → integers (for "three weeks from now" etc.)
_NUMBER_WORDS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12,
}

_ISO_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

# --- Weekday-relative patterns ---
# "next monday", "next wed"
_NEXT_WEEKDAY_RE = re.compile(r'^next\s+(\w+)$')
# "last monday", "last wed", "previous monday", "previous wed"
_LAST_WEEKDAY_RE = re.compile(r'^(?:last|previous|the\s+previous)\s+(\w+)$')
# "a wednesday three weeks from now", "wednesday two weeks from now"
_WEEKDAY_N_WEEKS_RE = re.compile(
    r'^(?:a\s+)?(\w+)\s+(\w+)\s+weeks?\s+from\s+now$'
)

# --- Numeric offset patterns ---
# "in 4 days", "in four days"
_IN_N_DAYS_RE = re.compile(r'^in\s+(\w+)\s+days?$')
# "in 2 weeks", "in two weeks"
_IN_N_WEEKS_RE = re.compile(r'^in\s+(\w+)\s+weeks?$')
# "2 days ago", "two days ago"
_N_DAYS_AGO_RE = re.compile(r'^(\w+)\s+days?\s+ago$')
# "2 weeks ago", "two weeks ago"
_N_WEEKS_AGO_RE = re.compile(r'^(\w+)\s+weeks?\s+ago$')
# "<N> weeks from now" (without weekday prefix)
_N_WEEKS_FROM_NOW_RE = re.compile(r'^(\w+)\s+weeks?\s+from\s+now$')


def _parse_number(token: str) -> Optional[int]:
    """Parse a number from a string — either a digit or a word like 'three'."""
    try:
        return int(token)
    except ValueError:
        return _NUMBER_WORDS.get(token.lower())


def resolve_weekday_to_date(user, start_date_str: str,
                            reference_dt: dt.datetime = None,
                            start_time: Optional[dt.time] = None) -> dt.date:
    """
    Deterministically resolve a date string to a concrete date.

    Supported inputs:
    - YYYY-MM-DD  → parsed directly
    - "today" / "now"  → user's local today
    - "tomorrow"  → user's local today + 1
    - "yesterday" → user's local today - 1
    - Bare weekday name (e.g. "wednesday", "fri") → nearest future occurrence
    - "next <weekday>" → following week's occurrence (never this week)
    - "last <weekday>" / "previous <weekday>" → most recent past occurrence
    - "<weekday> <N> weeks from now" → that weekday N weeks in the future
    - "in <N> days" → today + N days
    - "in <N> weeks" → today + N*7 days
    - "<N> days ago" → today - N days
    - "<N> weeks ago" → today - N*7 days
    - "<N> weeks from now" → today + N*7 days

    Weekday resolution rules:
    - "wednesday" → the soonest Wednesday from today.
      If today IS Wednesday and start_time is still in the future → today.
      If today IS Wednesday and start_time has passed → next week's Wednesday.
    - "next wednesday" → ALWAYS the Wednesday of the following week,
      never this week, even if this week's Wednesday hasn't happened yet.
    - "last wednesday" → the most recent Wednesday that has already passed.
      If today IS Wednesday → last week's Wednesday.

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

    if cleaned == 'yesterday':
        return user_today - dt.timedelta(days=1)

    # --- "next <weekday>" — always the FOLLOWING week ---
    next_match = _NEXT_WEEKDAY_RE.match(cleaned)
    if next_match:
        weekday_token = next_match.group(1)
        iso_weekday = WEEKDAY_NAMES.get(weekday_token)
        if iso_weekday is not None:
            return _next_weekday(user_today, iso_weekday, reference_dt,
                                 start_time, force_next_week=True)
        raise ValueError(
            f"Cannot resolve weekday from: {weekday_token!r} in '{start_date_str}'."
        )

    # --- "last/previous <weekday>" — most recent past occurrence ---
    last_match = _LAST_WEEKDAY_RE.match(cleaned)
    if last_match:
        weekday_token = last_match.group(1)
        iso_weekday = WEEKDAY_NAMES.get(weekday_token)
        if iso_weekday is not None:
            return _last_weekday(user_today, iso_weekday)
        raise ValueError(
            f"Cannot resolve weekday from: {weekday_token!r} in '{start_date_str}'."
        )

    # --- "<weekday> <N> weeks from now" ---
    wk_match = _WEEKDAY_N_WEEKS_RE.match(cleaned)
    if wk_match:
        weekday_token = wk_match.group(1)
        count_token = wk_match.group(2)
        iso_weekday = WEEKDAY_NAMES.get(weekday_token)
        count = _parse_number(count_token)
        if iso_weekday is not None and count is not None and count > 0:
            return _weekday_n_weeks_from_now(user_today, iso_weekday, count)
        # Maybe the first token is "a" and we have "a <weekday_token> ..."
        # but that's already handled by the optional "a\s+" in the regex.
        raise ValueError(
            f"Cannot resolve: '{start_date_str}'. Expected "
            f"'<weekday> <N> weeks from now'."
        )

    # --- "in <N> days" ---
    in_days_match = _IN_N_DAYS_RE.match(cleaned)
    if in_days_match:
        count = _parse_number(in_days_match.group(1))
        if count is not None:
            return user_today + dt.timedelta(days=count)
        raise ValueError(f"Cannot parse number in: '{start_date_str}'.")

    # --- "in <N> weeks" ---
    in_weeks_match = _IN_N_WEEKS_RE.match(cleaned)
    if in_weeks_match:
        count = _parse_number(in_weeks_match.group(1))
        if count is not None:
            return user_today + dt.timedelta(weeks=count)
        raise ValueError(f"Cannot parse number in: '{start_date_str}'.")

    # --- "<N> days ago" ---
    days_ago_match = _N_DAYS_AGO_RE.match(cleaned)
    if days_ago_match:
        count = _parse_number(days_ago_match.group(1))
        if count is not None:
            return user_today - dt.timedelta(days=count)
        raise ValueError(f"Cannot parse number in: '{start_date_str}'.")

    # --- "<N> weeks ago" ---
    weeks_ago_match = _N_WEEKS_AGO_RE.match(cleaned)
    if weeks_ago_match:
        count = _parse_number(weeks_ago_match.group(1))
        if count is not None:
            return user_today - dt.timedelta(weeks=count)
        raise ValueError(f"Cannot parse number in: '{start_date_str}'.")

    # --- "<N> weeks from now" (without weekday prefix) ---
    weeks_from_now_match = _N_WEEKS_FROM_NOW_RE.match(cleaned)
    if weeks_from_now_match:
        count = _parse_number(weeks_from_now_match.group(1))
        if count is not None:
            return user_today + dt.timedelta(weeks=count)
        raise ValueError(f"Cannot parse number in: '{start_date_str}'.")

    # --- Bare weekday name ---
    iso_weekday = WEEKDAY_NAMES.get(cleaned)
    if iso_weekday is not None:
        return _next_weekday(user_today, iso_weekday, reference_dt, start_time)

    raise ValueError(
        f"Cannot resolve date from: {start_date_str!r}. "
        f"Expected YYYY-MM-DD, 'today', 'tomorrow', 'yesterday', a weekday name, "
        f"'next/last <weekday>', 'in <N> days/weeks', '<N> days/weeks ago', "
        f"or '<weekday> <N> weeks from now'."
    )


def _next_weekday(today: dt.date, target_iso_weekday: int,
                  reference_dt: dt.datetime,
                  start_time: Optional[dt.time] = None,
                  force_next_week: bool = False) -> dt.date:
    """
    Compute the next occurrence of target_iso_weekday (1=Mon..7=Sun).

    Args:
        today: The user's local date.
        target_iso_weekday: Target day (1=Mon..7=Sun).
        reference_dt: Current local datetime for time comparisons.
        start_time: Event start time for same-day disambiguation.
        force_next_week: If True, always return the occurrence in the
                         FOLLOWING week (used for "next <weekday>" phrases).

    Same-day logic (when force_next_week=False):
    - If start_time is provided and has already passed → next week (+7)
    - If start_time is provided and is still in the future → today
    - If start_time is None → today (default)
    """
    current_iso_weekday = today.isoweekday()  # 1=Mon..7=Sun
    days_ahead = (target_iso_weekday - current_iso_weekday) % 7

    if force_next_week:
        # "next <weekday>" — always the following week's occurrence.
        # If days_ahead > 0, the weekday hasn't occurred yet this week,
        # but user explicitly said "next" so add 7 to skip this week.
        # If days_ahead == 0, same weekday today → next week.
        return today + dt.timedelta(days=days_ahead + 7)

    if days_ahead == 0:
        # Same weekday as today — check if time has passed
        if start_time is not None and start_time <= reference_dt.time():
            # Requested time already passed today → next week
            return today + dt.timedelta(days=7)
        # Time is still in the future (or no time given) → today
        return today

    return today + dt.timedelta(days=days_ahead)


def _last_weekday(today: dt.date, target_iso_weekday: int) -> dt.date:
    """
    Compute the most recent past occurrence of target_iso_weekday.

    If today IS the target weekday, returns LAST week's occurrence
    (never today — "last Wednesday" means a past Wednesday).
    """
    current_iso_weekday = today.isoweekday()
    days_back = (current_iso_weekday - target_iso_weekday) % 7
    if days_back == 0:
        days_back = 7  # same weekday → go back a full week
    return today - dt.timedelta(days=days_back)


def _weekday_n_weeks_from_now(today: dt.date, target_iso_weekday: int,
                              n_weeks: int) -> dt.date:
    """
    Compute the target weekday N weeks from now.

    First finds the next occurrence (or today), then adds (N-1) * 7 days
    if it's in the future, or N * 7 if occurrence is today.

    Simpler approach: go to the next occurrence of that weekday,
    then add (n_weeks - 1) * 7 days. But if the nearest occurrence is
    today, add n_weeks * 7 since "N weeks from now" implies future.
    """
    current_iso_weekday = today.isoweekday()
    days_ahead = (target_iso_weekday - current_iso_weekday) % 7

    if days_ahead == 0:
        # Today is that weekday — "wednesday 3 weeks from now" = today + 3*7
        return today + dt.timedelta(weeks=n_weeks)
    else:
        # Next occurrence is days_ahead away, then add (n_weeks - 1) more weeks
        # because the first occurrence IS "1 week from now-ish"
        # Actually: "wednesday 3 weeks from now" from Monday means
        # the Wednesday that is 3 weeks from now = today + 3*7 + days_ahead_offset
        # Simplest: find this week's target day, add n_weeks * 7
        this_weeks_target = today + dt.timedelta(days=days_ahead)
        return this_weeks_target + dt.timedelta(weeks=n_weeks - 1)
