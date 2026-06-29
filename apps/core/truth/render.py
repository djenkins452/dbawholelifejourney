"""
Human-Ready Conversation Layer — user-preference renderers.

Beth must NEVER speak raw ISO dates, UTC, 24-hour time, timezone offsets, or
database datetime strings. Every user-facing date/time flows through here and is
rendered in the user's timezone and preferred formats (MM/DD/YYYY, 12-hour AM/PM).
Centralized so all Beth-facing facts render identically.
"""
from datetime import date, datetime

from django.utils import timezone


def _user_tz(user):
    try:
        from apps.core.utils import _get_user_tz
        return _get_user_tz(user)
    except Exception:
        from datetime import timezone as _tz
        return _tz.utc


def _parse(value):
    if isinstance(value, (datetime, date)):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None


def _to_user_dt(user, value):
    dt = _parse(value)
    if not isinstance(dt, datetime):
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    return dt.astimezone(_user_tz(user))


def _clock(dt):
    return dt.strftime("%I:%M %p").lstrip("0")           # "2:05 PM"


def render_time(user, value):
    """12-hour AM/PM in the user's timezone, e.g. '2:05 PM'."""
    dt = _to_user_dt(user, value)
    return _clock(dt) if dt else ""


def render_date(user, value):
    """MM/DD/YYYY in the user's timezone, e.g. '06/28/2026'."""
    # A date-only string is a calendar date — render it as-is, never tz-shift it
    # (converting midnight-UTC to a local tz would slide it to the prior day).
    if isinstance(value, str) and "T" not in value and ":" not in value:
        try:
            return date.fromisoformat(value.strip()).strftime("%m/%d/%Y")
        except ValueError:
            pass
    parsed = _parse(value)
    if isinstance(parsed, datetime):
        parsed = _to_user_dt(user, parsed)
    if parsed is None:
        return ""
    return parsed.strftime("%m/%d/%Y")


def render_datetime(user, value):
    """MM/DD/YYYY at 12-hour time, e.g. '06/28/2026 at 2:05 PM'."""
    dt = _to_user_dt(user, value)
    if dt is None:
        return ""
    return f"{dt.strftime('%m/%d/%Y')} at {_clock(dt)}"


def render_relative_time(user, value):
    """Natural relative phrasing: 'just now', '2 hours ago', 'yesterday', '3 days ago',
    falling back to the rendered date for older values."""
    dt = _to_user_dt(user, value)
    if dt is None:
        return ""
    from apps.core.utils import get_user_now
    now = get_user_now(user)
    secs = (now - dt).total_seconds()
    if secs < 0:
        return "in the future"                          # caller should temporal-guard
    if secs < 90:
        return "just now"
    mins = int(secs // 60)
    if mins < 60:
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    hours = int(secs // 3600)
    if hours < 24 and dt.date() == now.date():
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = (now.date() - dt.date()).days
    if days == 0:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    return f"on {render_date(user, dt)}"
