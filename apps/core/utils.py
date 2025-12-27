"""
Core Utilities - Shared helper functions across the app.
"""

import pytz
from django.utils import timezone


def get_user_today(user):
    """
    Get today's date in the user's configured timezone.

    This is critical for date comparisons (overdue tasks, streaks, etc.)
    to work correctly across timezones. Using timezone.now().date() returns
    the UTC date, which can be a day ahead/behind the user's local date.

    Args:
        user: The User object (must have preferences.timezone)

    Returns:
        date: Today's date in the user's timezone
    """
    user_tz = pytz.timezone(user.preferences.timezone)
    user_now = timezone.now().astimezone(user_tz)
    return user_now.date()


def get_user_now(user):
    """
    Get the current datetime in the user's configured timezone.

    Args:
        user: The User object (must have preferences.timezone)

    Returns:
        datetime: Current datetime in the user's timezone (timezone-aware)
    """
    user_tz = pytz.timezone(user.preferences.timezone)
    return timezone.now().astimezone(user_tz)
