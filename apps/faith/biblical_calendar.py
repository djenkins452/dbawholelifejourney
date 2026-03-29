# ==============================================================================
# File: apps/faith/biblical_calendar.py
# Description: Deterministic biblical day resolver — raw data layer
# Created: 2026-03-29
# ==============================================================================
"""
Biblical Calendar — deterministic date resolver for significant biblical days.

This is a RAW DATA source, not a content engine. It produces structured data
about whether a given date is a biblically significant day.

Architecture position:
    Raw Data (this) → Signal Layer → CoS Context → LLM Narration

Rules:
- Deterministic only — no LLM, no user data, no DB
- Returns structured data, not presentation content
- Themes are 3-5 word phrases, never narratives
- Date computation uses standard algorithms (Anonymous Gregorian for Easter)
"""

import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Easter computation — Anonymous Gregorian algorithm
# ---------------------------------------------------------------------------


def compute_easter(year: int) -> datetime.date:
    """Compute Easter Sunday for a given year using the Anonymous Gregorian algorithm.

    Valid for years 1583–4099.
    Reference: https://en.wikipedia.org/wiki/Date_of_Easter#Anonymous_Gregorian_algorithm
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


# ---------------------------------------------------------------------------
# Biblical day definitions — structured raw data
# ---------------------------------------------------------------------------
# Each entry:
#   name: canonical name
#   date_rule: 'fixed' (month/day) or 'easter_relative' (offset from Easter)
#   level: 'baseline' | 'highlighted' | 'defining'
#   theme: 3-5 word significance phrase (NOT narrative)
#   scripture_reference: primary scripture

BIBLICAL_DAYS = [
    {
        'name': 'Palm Sunday',
        'date_rule': 'easter_relative',
        'easter_offset': -7,
        'level': 'highlighted',
        'theme': 'praise without alignment',
        'scripture_reference': 'Matthew 21:9',
    },
    {
        'name': 'Good Friday',
        'date_rule': 'easter_relative',
        'easter_offset': -2,
        'level': 'defining',
        'theme': 'sacrifice and surrender',
        'scripture_reference': 'John 19:30',
    },
    {
        'name': 'Easter Sunday',
        'date_rule': 'easter_relative',
        'easter_offset': 0,
        'level': 'defining',
        'theme': 'resurrection and conviction',
        'scripture_reference': 'Matthew 28:6',
    },
    {
        'name': 'Christmas',
        'date_rule': 'fixed',
        'month': 12,
        'day': 25,
        'level': 'highlighted',
        'theme': 'incarnation and purpose',
        'scripture_reference': 'John 1:14',
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_biblical_day(target_date: datetime.date) -> Optional[dict]:
    """Return biblical day data for the given date, or None.

    Returns:
        dict with keys: name, level, theme, scripture_reference,
        signal_ontology (event + influence classifications)
        — or None if the date has no biblical significance.
    """
    for entry in BIBLICAL_DAYS:
        if _matches_date(entry, target_date):
            return {
                'name': entry['name'],
                'level': entry['level'],
                'theme': entry['theme'],
                'scripture_reference': entry['scripture_reference'],
                'signal_ontology': {
                    'event': 'biblical_day_detected',
                    'influence': 'faith_theme_active',
                },
            }
    return None


def _matches_date(entry: dict, target_date: datetime.date) -> bool:
    """Check if a biblical day entry matches the target date."""
    rule = entry['date_rule']

    if rule == 'fixed':
        return (
            target_date.month == entry['month']
            and target_date.day == entry['day']
        )

    if rule == 'easter_relative':
        easter = compute_easter(target_date.year)
        offset_date = easter + datetime.timedelta(days=entry['easter_offset'])
        return target_date == offset_date

    return False
