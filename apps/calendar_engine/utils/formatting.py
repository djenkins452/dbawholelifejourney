# ==============================================================================
# File: calendar_engine/utils/formatting.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Human-friendly date/time formatting for calendar messages
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-24
# ==============================================================================
"""
Friendly Date/Time Formatting

Converts dates and times into natural, conversational formats:
  - "March 4th" instead of "Mar 04"
  - "6:15am" instead of "06:15 AM"
  - "March 4th at 6:15am" combined format
"""

from datetime import date, datetime, time


def _ordinal(n: int) -> str:
    """Return day number with ordinal suffix: 1st, 2nd, 3rd, 4th, ..., 31st."""
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def friendly_date(d) -> str:
    """
    Format a date as 'March 4th'.

    Accepts date, datetime, or ISO string.
    """
    if isinstance(d, str):
        d = datetime.fromisoformat(d).date()
    elif isinstance(d, datetime):
        d = d.date()
    return f"{d.strftime('%B')} {_ordinal(d.day)}"


def friendly_time(t) -> str:
    """
    Format a time as '6:15am' (no leading zero, lowercase am/pm, no space).

    Accepts time, datetime, or HH:MM string.
    """
    if isinstance(t, str):
        # Handle "HH:MM" strings
        parts = t.split(":")
        hour, minute = int(parts[0]), int(parts[1])
        t = time(hour, minute)
    elif isinstance(t, datetime):
        t = t.time()

    hour_12 = t.hour % 12 or 12
    minute = t.strftime("%M")
    ampm = "am" if t.hour < 12 else "pm"
    return f"{hour_12}:{minute}{ampm}"


def friendly_datetime(dt) -> str:
    """
    Format as 'March 4th at 6:15am'.

    Accepts datetime or ISO string.
    """
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return f"{friendly_date(dt)} at {friendly_time(dt)}"


def friendly_time_range(start, end) -> str:
    """
    Format a time range as '6:15am - 7:30pm'.

    Accepts datetime, time, or ISO string for each.
    """
    return f"{friendly_time(start)} \u2013 {friendly_time(end)}"
