"""
System Clock — Single authoritative time source for HTIE.

All relative time calculations MUST use get_current_time().
Never use naive datetime.now().
"""

from datetime import datetime

import pytz
from django.conf import settings


def get_current_time(timezone_str=None):
    """
    Return the current timezone-aware datetime.

    Args:
        timezone_str: IANA timezone string (e.g. 'America/New_York').
                      Falls back to settings.TIME_ZONE if not provided.

    Returns:
        Timezone-aware datetime in the specified timezone.
    """
    tz_name = timezone_str or getattr(settings, "TIME_ZONE", "UTC")
    tz = pytz.timezone(tz_name)
    return datetime.now(tz)
