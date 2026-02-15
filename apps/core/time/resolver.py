"""
Time Resolution Engine — Convert human time expressions to precise timestamps.

Converts natural language time phrases into timezone-aware datetime objects
using deterministic arithmetic. No guessing, no hallucination.
"""

import re
from datetime import datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

# Day name to weekday number (Monday=0 ... Sunday=6)
DAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

# Unit mapping for relativedelta
DURATION_UNITS = {
    "minute": "minutes",
    "minutes": "minutes",
    "hour": "hours",
    "hours": "hours",
    "day": "days",
    "days": "days",
    "week": "weeks",
    "weeks": "weeks",
    "month": "months",
    "months": "months",
    "year": "years",
    "years": "years",
}

# Time-of-day defaults when user says "morning", "afternoon", etc.
TIME_OF_DAY = {
    "morning": time(9, 0),
    "afternoon": time(14, 0),
    "evening": time(18, 0),
    "night": time(21, 0),
}


class ResolvedTime:
    """Result of resolving a time expression."""

    __slots__ = ("datetime_aware", "original_expression", "confidence")

    def __init__(self, datetime_aware, original_expression, confidence="high"):
        self.datetime_aware = datetime_aware
        self.original_expression = original_expression
        self.confidence = confidence  # "high", "medium", "low"

    def to_dict(self):
        return {
            "resolved_datetime": self.datetime_aware.isoformat(),
            "original_expression": self.original_expression,
            "confidence": self.confidence,
        }


def _parse_time_component(text):
    """Extract an explicit time like '2pm', '14:00', '2:30pm' from text."""
    # Match "at 2pm", "at 14:00", "at 2:30 PM"
    m = re.search(
        r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?", text, re.IGNORECASE
    )
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    ampm = m.group(3)
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
    return time(hour, minute)


def _parse_quantity(text):
    """Parse 'a', 'an', or a number from the quantity portion."""
    text = text.strip().lower()
    if text in ("a", "an"):
        return 1
    try:
        return int(text)
    except ValueError:
        return 1


def _get_next_weekday(reference, target_weekday):
    """Get the next occurrence of a weekday after reference date."""
    days_ahead = target_weekday - reference.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return reference + timedelta(days=days_ahead)


def _get_last_weekday(reference, target_weekday):
    """Get the most recent past occurrence of a weekday before reference date."""
    days_back = reference.weekday() - target_weekday
    if days_back <= 0:
        days_back += 7
    return reference - timedelta(days=days_back)


def resolve_time_expression(expression, reference_time):
    """
    Convert a human time expression into a precise timezone-aware datetime.

    Args:
        expression: The extracted time phrase (e.g. "3 days ago", "next Friday at 2pm").
        reference_time: Timezone-aware datetime representing "now".

    Returns:
        ResolvedTime with the resolved datetime, or None if unresolvable.
    """
    if not expression:
        return None

    expr = expression.strip().lower()
    tz = reference_time.tzinfo

    # --- Simple keywords ---
    if expr == "today":
        result = reference_time.replace(hour=0, minute=0, second=0, microsecond=0)
        return ResolvedTime(result, expression)

    if expr == "yesterday":
        result = (reference_time - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return ResolvedTime(result, expression)

    if expr == "tomorrow":
        result = (reference_time + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return ResolvedTime(result, expression)

    if expr == "tonight":
        result = reference_time.replace(hour=21, minute=0, second=0, microsecond=0)
        return ResolvedTime(result, expression)

    # --- "tomorrow/yesterday morning/afternoon/evening at TIME" ---
    m = re.match(
        r"(tomorrow|yesterday)\s+(morning|afternoon|evening|night)"
        r"(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?",
        expr,
    )
    if m:
        base_day = m.group(1)
        period = m.group(2)
        if base_day == "tomorrow":
            base = reference_time + timedelta(days=1)
        else:
            base = reference_time - timedelta(days=1)
        explicit_time = _parse_time_component(expr)
        t = explicit_time or TIME_OF_DAY.get(period, time(9, 0))
        result = base.replace(
            hour=t.hour, minute=t.minute, second=0, microsecond=0
        )
        return ResolvedTime(result, expression)

    # --- "tomorrow/yesterday at TIME" ---
    m = re.match(
        r"(tomorrow|yesterday)\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?", expr
    )
    if m:
        base_day = m.group(1)
        if base_day == "tomorrow":
            base = reference_time + timedelta(days=1)
        else:
            base = reference_time - timedelta(days=1)
        t = _parse_time_component(expr)
        if t:
            result = base.replace(
                hour=t.hour, minute=t.minute, second=0, microsecond=0
            )
            return ResolvedTime(result, expression)

    # --- "this/last morning/afternoon/evening/night" ---
    m = re.match(r"(this|last|next)\s+(morning|afternoon|evening|night)", expr)
    if m:
        modifier = m.group(1)
        period = m.group(2)
        t = TIME_OF_DAY.get(period, time(9, 0))
        if modifier == "last":
            base = reference_time - timedelta(days=1)
        elif modifier == "next":
            base = reference_time + timedelta(days=1)
        else:
            base = reference_time
        result = base.replace(
            hour=t.hour, minute=t.minute, second=0, microsecond=0
        )
        return ResolvedTime(result, expression)

    # --- "N units ago" ---
    m = re.match(r"(a|an|\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", expr)
    if m:
        qty = _parse_quantity(m.group(1))
        unit = DURATION_UNITS.get(m.group(2), m.group(2))
        delta = relativedelta(**{unit: qty})
        result = reference_time - delta
        return ResolvedTime(result, expression)

    # --- "in N units" ---
    m = re.match(r"in\s+(a|an|\d+)\s+(minute|hour|day|week|month|year)s?", expr)
    if m:
        qty = _parse_quantity(m.group(1))
        unit = DURATION_UNITS.get(m.group(2), m.group(2))
        delta = relativedelta(**{unit: qty})
        result = reference_time + delta
        return ResolvedTime(result, expression)

    # --- "a/N unit(s) from now/today [at TIME]" ---
    m = re.match(
        r"(a|an|\d+)\s+(minute|hour|day|week|month|year)s?\s+from\s+(?:now|today)"
        r"(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?",
        expr,
    )
    if m:
        qty = _parse_quantity(m.group(1))
        unit = DURATION_UNITS.get(m.group(2), m.group(2))
        delta = relativedelta(**{unit: qty})
        result = reference_time + delta
        explicit_time = _parse_time_component(expr)
        if explicit_time:
            result = result.replace(
                hour=explicit_time.hour,
                minute=explicit_time.minute,
                second=0,
                microsecond=0,
            )
        return ResolvedTime(result, expression)

    # --- "next/last WEEKDAY [at TIME]" ---
    m = re.match(
        r"(next|last|this)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
        r"(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?",
        expr,
    )
    if m:
        modifier = m.group(1)
        target_day = DAY_NAMES[m.group(2)]
        if modifier == "next":
            base = _get_next_weekday(reference_time, target_day)
        elif modifier == "last":
            base = _get_last_weekday(reference_time, target_day)
        else:
            # "this" — if today is that day, use today; otherwise next occurrence
            if reference_time.weekday() == target_day:
                base = reference_time
            else:
                base = _get_next_weekday(reference_time, target_day)
        explicit_time = _parse_time_component(expr)
        if explicit_time:
            result = base.replace(
                hour=explicit_time.hour,
                minute=explicit_time.minute,
                second=0,
                microsecond=0,
            )
        else:
            result = base.replace(hour=0, minute=0, second=0, microsecond=0)
        return ResolvedTime(result, expression)

    # --- "next/last month on the Nth [at TIME]" --- (MUST be before generic "next month")
    m = re.match(
        r"(next|last)\s+month\s+on\s+the\s+(\d{1,2})(?:st|nd|rd|th)?"
        r"(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?",
        expr,
    )
    if m:
        modifier = m.group(1)
        target_day = int(m.group(2))
        if modifier == "next":
            base = reference_time + relativedelta(months=1)
        else:
            base = reference_time - relativedelta(months=1)
        explicit_time = _parse_time_component(expr)
        t = explicit_time or time(0, 0)
        result = base.replace(
            day=target_day,
            hour=t.hour,
            minute=t.minute,
            second=0,
            microsecond=0,
        )
        return ResolvedTime(result, expression)

    # --- "next/last week/month/year" ---
    m = re.match(r"(next|last)\s+(week|month|year)$", expr)
    if m:
        modifier = m.group(1)
        unit = m.group(2)
        if unit == "week":
            delta = timedelta(weeks=1)
            if modifier == "next":
                # Start of next week (next Monday)
                days_to_monday = (7 - reference_time.weekday()) % 7
                if days_to_monday == 0:
                    days_to_monday = 7
                result = (reference_time + timedelta(days=days_to_monday)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            else:
                # Start of last week (previous Monday)
                days_since_monday = reference_time.weekday()
                result = (
                    reference_time - timedelta(days=days_since_monday + 7)
                ).replace(hour=0, minute=0, second=0, microsecond=0)
        elif unit == "month":
            if modifier == "next":
                result = (reference_time + relativedelta(months=1)).replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )
            else:
                result = (reference_time - relativedelta(months=1)).replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )
        else:  # year
            if modifier == "next":
                result = reference_time.replace(
                    year=reference_time.year + 1,
                    month=1,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            else:
                result = reference_time.replace(
                    year=reference_time.year - 1,
                    month=1,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
        return ResolvedTime(result, expression)

    # Unresolvable
    return None
