"""
Date Parser Utility for WLJ Personal Data Query System.

This module provides natural language date extraction from user queries,
supporting phrases like 'since December 1st', 'this week', 'last month', etc.
"""

import re
from datetime import datetime, timedelta
from typing import Optional

from dateutil import parser as dateutil_parser
from dateutil.relativedelta import relativedelta
from django.utils import timezone


def _make_aware(dt: datetime, reference: datetime) -> datetime:
    """Make a datetime timezone-aware if the reference is aware."""
    if timezone.is_aware(reference) and timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def extract_date_from_message(message: str, reference_date: Optional[datetime] = None, user=None) -> Optional[datetime]:
    """
    Extract a date reference from a natural language message.

    This function parses user messages to find date references and converts
    them to datetime objects. It handles:
    - Relative dates: 'today', 'yesterday', 'this week', 'last month'
    - Absolute dates: 'December 1st', '12/25', '2024-01-15'
    - Phrases: 'since January', 'from last week', 'after December 1st'

    Args:
        message: The user's message string to analyze.
        reference_date: Optional reference date for relative calculations.
                       Defaults to current date/time if not provided.
        user: Optional user object for timezone-correct "today" resolution.
              When provided, uses the user's configured timezone instead of
              relying on Django middleware timezone activation.

    Returns:
        A datetime object representing the extracted date, or None if
        no date reference is found.

    Example:
        >>> extract_date_from_message("What was my weight since December 1st?")
        datetime.datetime(2024, 12, 1, 0, 0)

        >>> extract_date_from_message("How did I sleep last week?")
        datetime.datetime(2024, 12, 23, 0, 0)  # Monday of last week

        >>> extract_date_from_message("Hello, how are you?")
        None
    """
    if not message or not isinstance(message, str):
        return None

    # Use reference_date, or resolve "now" in the user's timezone.
    # Prefer the user's configured timezone over timezone.localtime()
    # which depends on middleware activation and falls back to UTC.
    if reference_date:
        now = reference_date
    elif user:
        try:
            from apps.core.utils import get_user_now
            now = get_user_now(user)
        except Exception:
            now = timezone.localtime(timezone.now())
    else:
        now = timezone.localtime(timezone.now())
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    message_lower = message.lower()

    # Check relative date phrases first (order matters - more specific first)
    relative_date = _extract_relative_date(message_lower, today)
    if relative_date is not None:
        return relative_date

    # Try to extract dates from phrases like 'since X', 'from X', 'after X'
    phrase_date = _extract_phrase_date(message_lower, today)
    if phrase_date is not None:
        return phrase_date

    # Try to extract standalone dates
    standalone_date = _extract_standalone_date(message_lower, today)
    if standalone_date is not None:
        return standalone_date

    return None


def _extract_relative_date(message: str, today: datetime) -> Optional[datetime]:
    """
    Extract relative date references like 'today', 'yesterday', 'this week'.

    Args:
        message: Lowercase message string.
        today: Reference date (start of day).

    Returns:
        Extracted datetime or None.
    """
    # Today
    if re.search(r'\btoday\b', message):
        return today

    # Yesterday
    if re.search(r'\byesterday\b', message):
        return today - timedelta(days=1)

    # This week (Monday of current week)
    if re.search(r'\bthis\s+week\b', message):
        # Find Monday of current week
        days_since_monday = today.weekday()
        return today - timedelta(days=days_since_monday)

    # Last week (Monday of previous week)
    if re.search(r'\blast\s+week\b', message):
        days_since_monday = today.weekday()
        monday_this_week = today - timedelta(days=days_since_monday)
        return monday_this_week - timedelta(weeks=1)

    # This month (1st of current month)
    if re.search(r'\bthis\s+month\b', message):
        return today.replace(day=1)

    # Last month (1st of previous month)
    if re.search(r'\blast\s+month\b', message):
        first_of_this_month = today.replace(day=1)
        last_month = first_of_this_month - relativedelta(months=1)
        return last_month

    # This year (January 1st of current year)
    if re.search(r'\bthis\s+year\b', message):
        return today.replace(month=1, day=1)

    # Last year (January 1st of previous year)
    if re.search(r'\blast\s+year\b', message):
        return today.replace(year=today.year - 1, month=1, day=1)

    # Past N days/weeks/months patterns
    past_pattern = r'\b(?:past|last)\s+(\d+)\s+(day|days|week|weeks|month|months)\b'
    match = re.search(past_pattern, message)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).rstrip('s')  # Normalize to singular

        if unit == 'day':
            return today - timedelta(days=amount)
        elif unit == 'week':
            return today - timedelta(weeks=amount)
        elif unit == 'month':
            return today - relativedelta(months=amount)

    return None


def _extract_phrase_date(message: str, today: datetime) -> Optional[datetime]:
    """
    Extract dates from phrases like 'since December 1st', 'from January 15'.

    Args:
        message: Lowercase message string.
        today: Reference date for year defaulting.

    Returns:
        Extracted datetime or None.
    """
    # Patterns for date-prefixing phrases
    phrase_patterns = [
        r'\bsince\s+(.+?)(?:\?|$|,|\band\b)',
        r'\bfrom\s+(.+?)(?:\?|$|,|\band\b|\bto\b)',
        r'\bafter\s+(.+?)(?:\?|$|,|\band\b)',
        r'\bstarting\s+(.+?)(?:\?|$|,|\band\b)',
        r'\bbeginning\s+(.+?)(?:\?|$|,|\band\b)',
    ]

    for pattern in phrase_patterns:
        match = re.search(pattern, message)
        if match:
            date_str = match.group(1).strip()
            # Try to parse the extracted date string
            parsed = _parse_date_string(date_str, today)
            if parsed:
                return parsed

    return None


def _extract_standalone_date(message: str, today: datetime) -> Optional[datetime]:
    """
    Extract standalone date references from the message.

    Args:
        message: Lowercase message string.
        today: Reference date for year defaulting.

    Returns:
        Extracted datetime or None.
    """
    # Common date patterns to look for
    patterns = [
        # Month day with optional ordinal: "December 1st", "Jan 15th"
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december|'
        r'jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{1,2})(?:st|nd|rd|th)?\b',
        # Day Month: "1st December", "15 January"
        r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december|'
        r'jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b',
        # MM/DD or MM-DD format
        r'\b(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?\b',
        # ISO format: YYYY-MM-DD
        r'\b(\d{4})-(\d{2})-(\d{2})\b',
        # Just month name (assume 1st of that month)
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\b',
    ]

    # Try each pattern
    for i, pattern in enumerate(patterns):
        match = re.search(pattern, message)
        if match:
            if i == 0:  # Month day: "December 1st"
                month_str = match.group(1)
                day = int(match.group(2))
                return _build_date_from_month_day(month_str, day, today)
            elif i == 1:  # Day Month: "1st December"
                day = int(match.group(1))
                month_str = match.group(2)
                return _build_date_from_month_day(month_str, day, today)
            elif i == 2:  # MM/DD or MM/DD/YYYY
                month = int(match.group(1))
                day = int(match.group(2))
                year_str = match.group(3)
                if year_str:
                    year = int(year_str)
                    if year < 100:
                        year += 2000  # Assume 21st century for 2-digit years
                else:
                    year = _default_year(month, day, today)
                try:
                    return _make_aware(datetime(year, month, day), today)
                except ValueError:
                    pass
            elif i == 3:  # ISO format
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))
                try:
                    return _make_aware(datetime(year, month, day), today)
                except ValueError:
                    pass
            elif i == 4:  # Just month name
                month_str = match.group(1)
                return _build_date_from_month_day(month_str, 1, today)

    return None


def _parse_date_string(date_str: str, today: datetime) -> Optional[datetime]:
    """
    Parse a date string using multiple strategies.

    Args:
        date_str: The date string to parse.
        today: Reference date for year defaulting.

    Returns:
        Parsed datetime or None.
    """
    # Clean up the string
    date_str = date_str.strip()

    # First try relative dates in the string
    relative = _extract_relative_date(date_str, today)
    if relative:
        return relative

    # Try standalone date extraction
    standalone = _extract_standalone_date(date_str, today)
    if standalone:
        return standalone

    # Try dateutil parser as fallback
    try:
        parsed = dateutil_parser.parse(date_str, fuzzy=True, default=today)
        # If no year was in the string, dateutil uses default's year
        # We need to apply our year defaulting logic
        if not re.search(r'\b\d{4}\b', date_str):
            parsed = parsed.replace(
                year=_default_year(parsed.month, parsed.day, today)
            )
        return parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    except (ValueError, TypeError):
        pass

    return None


def _build_date_from_month_day(month_str: str, day: int, today: datetime) -> Optional[datetime]:
    """
    Build a datetime from month name and day with year defaulting.

    Args:
        month_str: Month name (full or abbreviated).
        day: Day of month.
        today: Reference date for year defaulting.

    Returns:
        Built datetime or None if invalid.
    """
    month_map = {
        'january': 1, 'jan': 1,
        'february': 2, 'feb': 2,
        'march': 3, 'mar': 3,
        'april': 4, 'apr': 4,
        'may': 5,
        'june': 6, 'jun': 6,
        'july': 7, 'jul': 7,
        'august': 8, 'aug': 8,
        'september': 9, 'sep': 9, 'sept': 9,
        'october': 10, 'oct': 10,
        'november': 11, 'nov': 11,
        'december': 12, 'dec': 12,
    }

    month = month_map.get(month_str.lower())
    if not month:
        return None

    year = _default_year(month, day, today)

    try:
        return _make_aware(datetime(year, month, day), today)
    except ValueError:
        return None


def _default_year(month: int, day: int, today: datetime) -> int:
    """
    Determine the appropriate year when year is not specified.

    Logic: If the specified month/day is in the future relative to today,
    assume the user means last year. Otherwise, use the current year.

    Args:
        month: Month number (1-12).
        day: Day of month.
        today: Reference date.

    Returns:
        The year to use.
    """
    current_year = today.year

    try:
        # Try to create a date this year
        candidate = _make_aware(datetime(current_year, month, day), today)
        # If the date is more than a week in the future, assume last year
        if candidate > today + timedelta(days=7):
            return current_year - 1
        return current_year
    except ValueError:
        # Invalid date (e.g., Feb 30), just return current year
        return current_year
