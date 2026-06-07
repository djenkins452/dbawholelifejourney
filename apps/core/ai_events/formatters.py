# ==============================================================================
# File: apps/core/ai_events/formatters.py
# Project: Whole Life Journey — Django 5.x Personal Wellness/Journaling App
# Description: Response formatters for event-level query results
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-28
# ==============================================================================
"""
Event Response Formatters.

Convert EventRecord lists into human-readable deterministic responses.
These responses are injected directly into the router response —
the LLM never touches them.

All formatting is deterministic. No inference, no generation.
"""

from datetime import date, timedelta
from collections import defaultdict


def format_missed_events(events, domain=None):
    """
    Format missed events into a deterministic response.

    Args:
        events: list[EventRecord] — missed events
        domain: str or None — if set, domain-specific formatting

    Returns:
        str — formatted response text
    """
    if not events:
        scope = f" {domain}" if domain else ""
        return f"You haven't missed any{scope} items in this period. Everything is on track."

    # Group by domain
    by_domain = defaultdict(list)
    for e in events:
        by_domain[e.domain].append(e)

    parts = []

    # Count summary
    total = len(events)
    if total == 1:
        parts.append(f"You missed 1 item:")
    else:
        parts.append(f"You missed {total} items:")

    # Format by domain
    for domain_name in ('medication', 'routine', 'workout'):
        domain_events = by_domain.get(domain_name, [])
        if not domain_events:
            continue

        if domain_name == 'medication':
            parts.append("")
            if len(domain_events) == 1:
                parts.append("**Medication** (1 dose):")
            else:
                parts.append(f"**Medication** ({len(domain_events)} doses):")
            for e in domain_events:
                date_str = _format_date(e.detail.get('scheduled_date'))
                parts.append(f"• {e.detail.get('medicine_name', 'Unknown')}"
                             f" — {date_str}"
                             f" at {e.detail.get('scheduled_time', 'unscheduled')}")

        elif domain_name == 'routine':
            parts.append("")
            if len(domain_events) == 1:
                parts.append("**Routine** (1 item):")
            else:
                parts.append(f"**Routine** ({len(domain_events)} items):")
            for e in domain_events:
                date_str = _format_date(e.detail.get('scheduled_date'))
                parts.append(f"• {e.detail.get('item_name', 'Unknown')}"
                             f" — {date_str}"
                             f" ({e.detail.get('routine_name', '')})")

    return "\n".join(parts)


def format_day_timeline(events, target_date):
    """
    Format a day's events into a timeline view.

    Args:
        events: list[EventRecord] — all events for the day
        target_date: date — which day

    Returns:
        str — formatted timeline
    """
    if not events:
        date_str = _format_date(str(target_date))
        return f"No tracked events on {date_str}."

    date_str = _format_date(str(target_date))
    parts = [f"Here's what happened on {date_str}:"]
    parts.append("")

    for e in events:
        time_str = e.timestamp.strftime("%-I:%M %p") if e.timestamp else "—"
        status_icon = _status_icon(e.status)
        parts.append(f"{time_str} — {status_icon} {e.label}")

    # Summary counts
    completed = sum(1 for e in events if e.status in ('completed', 'taken'))
    missed = sum(1 for e in events if e.status == 'missed')
    skipped = sum(1 for e in events if e.status == 'skipped')

    parts.append("")
    summary_parts = [f"{completed} completed"]
    if missed:
        summary_parts.append(f"{missed} missed")
    if skipped:
        summary_parts.append(f"{skipped} skipped")
    parts.append(f"**Summary:** {', '.join(summary_parts)}")

    return "\n".join(parts)


def format_slippage_trend(trend_data):
    """
    Format routine slippage analysis into a deterministic response.

    Args:
        trend_data: dict from routine adapter's get_completion_trend()

    Returns:
        str — formatted slippage analysis
    """
    slippage_date = trend_data.get('slippage_date')
    current_rate = trend_data.get('current_rate')
    prior_rate = trend_data.get('prior_rate')

    if not trend_data.get('daily_rates'):
        return "Not enough routine data to analyze trends yet."

    if slippage_date is None:
        if current_rate is not None:
            return (
                f"Your routine completion has been steady — "
                f"currently at **{current_rate}%**. No slippage detected."
            )
        return "Your routine completion has been steady. No slippage detected."

    parts = []

    date_str = _format_date(slippage_date)
    parts.append(f"Your routine started slipping around **{date_str}**.")

    if prior_rate is not None and current_rate is not None:
        parts.append(
            f"Before that, your completion rate was **{prior_rate}%**. "
            f"It has since dropped to **{current_rate}%**."
        )
    elif current_rate is not None:
        parts.append(f"Your current completion rate is **{current_rate}%**.")

    return " ".join(parts)


def format_lookup_events(events, domain=None):
    """
    Format event data for lookup queries ("how was my sleep?", "what's my weight?").

    Args:
        events: list[EventRecord] — events to display (usually 1-5 recent entries)
        domain: str or None — domain for context-aware formatting

    Returns:
        str — formatted response text
    """
    if not events:
        domain_label = domain.replace('_', ' ') if domain else "data"
        return f"No {domain_label} entries found."

    if len(events) == 1:
        return _format_single_lookup(events[0])

    # Multiple entries
    parts = []
    domain_label = domain.replace('_', ' ').title() if domain else "Data"
    parts.append(f"Here are your recent **{domain_label}** entries:")
    parts.append("")

    for e in events:
        date_str = _format_date(
            e.detail.get('date') or e.detail.get('scheduled_date')
            or e.detail.get('sleep_date') or ''
        )
        parts.append(f"• {date_str}: {e.label}")

    return "\n".join(parts)


def _format_single_lookup(event):
    """Format a single event for a lookup response."""
    detail = event.detail
    date_str = _format_date(
        detail.get('date') or detail.get('scheduled_date')
        or detail.get('sleep_date') or ''
    )
    domain = event.domain

    if domain == 'sleep':
        hours = detail.get('hours')
        quality = detail.get('quality_rating', '')
        bedtime = detail.get('bedtime', '')
        wake = detail.get('wake_time', '')
        parts = []
        if hours is not None:
            parts.append(f"You slept **{hours} hours** ({date_str}).")
        if quality:
            parts.append(f"Quality: **{quality}**.")
        if detail.get('quality_score'):
            parts.append(f"Score: **{detail['quality_score']}/100**.")
        if detail.get('deep_minutes'):
            parts.append(f"Deep sleep: {detail['deep_minutes']} min.")
        if detail.get('rem_minutes'):
            parts.append(f"REM: {detail['rem_minutes']} min.")
        return " ".join(parts) if parts else event.label

    elif domain == 'weight':
        return f"Your latest weight is **{detail.get('value')} {detail.get('unit', 'lb')}** ({date_str})."

    elif domain == 'glucose':
        # 2026-06-07: glucose is time-sensitive. Preserve time-of-day +
        # relative-age so the user can answer "what time was that?" at
        # a glance. The prior render stripped both, which broke the
        # trust contract when the follow-up question ("what time?")
        # had no anchor in the response.
        val = detail.get('value')
        unit = detail.get('unit', 'mg/dL')
        ctx = detail.get('context', '')
        ts = event.timestamp
        when = _format_datetime(ts) if ts else date_str
        age = _format_relative_age(ts) if ts else ""
        resp = f"Your most recent glucose reading was **{val} {unit}**"
        if ctx:
            resp += f" ({ctx})"
        if age:
            resp += f" at **{when}** ({age})."
        else:
            resp += f" at **{when}**."
        # Surface Dexcom trend arrow when present — never invented.
        trend = detail.get('trend', '')
        if trend and trend not in ("none", "notComputable", "rateOutOfRange"):
            from apps.health.services.glucose_snapshot import TREND_DISPLAY
            t_label, t_arrow = TREND_DISPLAY.get(trend, ("", ""))
            if t_label:
                resp += f"\nTrend: {t_label} {t_arrow}"
        return resp

    elif domain == 'blood_pressure':
        s = detail.get('systolic')
        d = detail.get('diastolic')
        pulse = detail.get('pulse')
        resp = f"Your latest blood pressure is **{s}/{d} mmHg**"
        if pulse:
            resp += f" (pulse {pulse})"
        resp += f" — {date_str}."
        return resp

    elif domain == 'heart_rate':
        bpm = detail.get('bpm')
        ctx = detail.get('context', '')
        resp = f"Your latest heart rate is **{bpm} bpm**"
        if ctx:
            resp += f" ({ctx})"
        resp += f" — {date_str}."
        return resp

    elif domain == 'steps':
        count = detail.get('count', 0)
        goal = detail.get('goal')
        resp = f"You logged **{count:,} steps** ({date_str})."
        if goal:
            resp += f" Goal: {goal:,}."
        return resp

    elif domain == 'water':
        amount = detail.get('amount')
        unit = detail.get('unit', 'oz')
        return f"Water intake: **{amount} {unit}** ({date_str})."

    elif domain == 'nutrition':
        name = detail.get('food_name', '')
        meal = detail.get('meal_type', '')
        cal = detail.get('calories')
        protein = detail.get('protein_g')
        parts = []
        if meal:
            parts.append(f"**{meal.title()}**: {name}")
        else:
            parts.append(f"**{name}**")
        if cal:
            parts.append(f"{cal} cal")
        if protein:
            parts.append(f"{protein}g protein")
        return f"{' — '.join(parts)} ({date_str})."

    elif domain == 'fasting':
        ftype = detail.get('fasting_type', '')
        dur = detail.get('duration_hours')
        target = detail.get('target_hours')
        resp = f"Fast: **{ftype}**"
        if dur:
            resp += f" — {dur} hours"
            if target:
                resp += f" of {target}h target"
        resp += f" ({date_str})."
        return resp

    elif domain == 'journal':
        title = detail.get('title', 'Journal Entry')
        mood = detail.get('mood', '')
        wc = detail.get('word_count', 0)
        resp = f"**{title}** ({date_str})"
        if mood:
            resp += f" — mood: {mood}"
        if wc:
            resp += f", {wc} words"
        resp += "."
        return resp

    elif domain == 'faith':
        return f"{event.label} ({date_str})."

    elif domain == 'habits':
        name = detail.get('habit_name', 'Habit')
        completed = detail.get('completed')
        resp = f"**{name}** — {'completed ✓' if completed else 'not completed'} ({date_str})."
        return resp

    elif domain == 'workout':
        # Logged session: defer to label.
        # Scheduled (future) session: render deterministically from
        # the WorkoutSchedule snapshot in detail{}. No LLM, no inference.
        if event.status == 'scheduled':
            day_name = detail.get('day_of_week') or _format_date(detail.get('date'))
            msg = f"**{day_name} ({date_str})** — {event.label}"
            pref = detail.get('preferred_time')
            if pref:
                msg += f" at {pref[:5]}"
            return msg
        return f"{event.label} ({date_str})."

    elif domain == 'finance':
        amount = detail.get('amount', 0)
        desc = detail.get('description', '')
        cat = detail.get('category', '')
        resp = f"**${abs(amount):.2f}** {'income' if amount > 0 else 'expense'}"
        if desc:
            resp += f" — {desc}"
        if cat:
            resp += f" ({cat})"
        resp += f" on {date_str}."
        return resp

    # Default: use the label
    return f"{event.label} ({date_str})."


def _format_date(date_str):
    """Format a date string into a human-readable form."""
    if not date_str:
        return "unknown date"
    try:
        d = date.fromisoformat(date_str) if isinstance(date_str, str) else date_str
        today = date.today()
        delta = (today - d).days

        if delta == 0:
            return "today"
        elif delta == 1:
            return "yesterday"
        elif delta < 7:
            return d.strftime("%A")  # Day name (e.g., "Monday")
        else:
            return d.strftime("%B %-d")  # "March 20"
    except (ValueError, TypeError):
        return str(date_str)


def _format_datetime(dt_value):
    """Format a datetime into "2:11 PM today" / "9:42 AM yesterday" /
    "Mon 7:33 PM" / "Mar 20 4:15 PM".

    Time-of-day preserved — unlike ``_format_date()``. Use this for
    time-sensitive vitals (glucose, blood pressure, heart rate, SpO2).
    Glucose specifically required this because the prior formatter
    stripped time and the user's "what time was my reading?" question
    had no anchor to bind to.
    """
    from datetime import datetime as _datetime
    from django.utils import timezone as _tz
    if dt_value is None:
        return "unknown time"
    if isinstance(dt_value, str):
        try:
            dt_value = _datetime.fromisoformat(dt_value)
        except (TypeError, ValueError):
            return str(dt_value)
    if not hasattr(dt_value, "hour"):
        return str(dt_value)
    if dt_value.tzinfo is None:
        try:
            dt_value = _tz.make_aware(dt_value, _tz.get_current_timezone())
        except Exception:
            pass
    try:
        local_dt = _tz.localtime(dt_value)
    except Exception:
        local_dt = dt_value
    now_local = _tz.localtime(_tz.now())
    today = now_local.date()
    target = local_dt.date()
    time_part = local_dt.strftime("%-I:%M %p")
    delta_days = (today - target).days
    if delta_days == 0:
        return f"{time_part} today"
    if delta_days == 1:
        return f"{time_part} yesterday"
    if 0 < delta_days < 7:
        return f"{local_dt.strftime('%a')} {time_part}"
    return f"{local_dt.strftime('%b %-d')} {time_part}"


def _format_relative_age(dt_value):
    """Format "7 minutes ago" / "3 hours ago" / "yesterday" / "5 days ago".

    Companion to ``_format_datetime``. Vitals are time-sensitive — the
    user wants to know "how fresh is this number?" at a glance.
    """
    from datetime import datetime as _datetime
    from django.utils import timezone as _tz
    if dt_value is None:
        return ""
    if isinstance(dt_value, str):
        try:
            dt_value = _datetime.fromisoformat(dt_value)
        except (TypeError, ValueError):
            return ""
    if not hasattr(dt_value, "hour"):
        return ""
    if dt_value.tzinfo is None:
        try:
            dt_value = _tz.make_aware(dt_value, _tz.get_current_timezone())
        except Exception:
            pass
    try:
        delta = _tz.now() - dt_value
    except Exception:
        return ""
    minutes_ago = max(0, int(round(delta.total_seconds() / 60)))
    if minutes_ago < 1:
        return "just now"
    if minutes_ago < 60:
        return f"{minutes_ago} minute{'s' if minutes_ago != 1 else ''} ago"
    hours = minutes_ago // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    weeks = days // 7
    if weeks == 1:
        return "1 week ago"
    return f"{weeks} weeks ago"


def _status_icon(status):
    """Return a status indicator character."""
    icons = {
        'completed': '✓',
        'taken': '✓',
        'completed_late': '✓',  # Still completed
        'late': '⏰',
        'missed': '✗',
        'skipped': '—',
        'rescheduled': '→',
        'in_progress': '▶',
        'logged': '•',
        'pending': '○',
    }
    return icons.get(status, '•')
