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
