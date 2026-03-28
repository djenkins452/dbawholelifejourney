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
        val = detail.get('value')
        unit = detail.get('unit', 'mg/dL')
        ctx = detail.get('context', '')
        resp = f"Your latest glucose reading is **{val} {unit}**"
        if ctx:
            resp += f" ({ctx})"
        resp += f" — {date_str}."
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
