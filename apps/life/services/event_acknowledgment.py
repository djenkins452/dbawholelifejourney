"""
Deterministic Significant Event Acknowledgment Builder.

Generates acknowledgment text for today's significant events that is
injected into the response AFTER LLM generation. This ensures critical
relational events (birthdays, anniversaries, memorials) are ALWAYS
acknowledged, regardless of LLM behavior or mode.

Architecture:
- Queries SignificantEvent model directly (no SAE cache dependency)
- Uses existing relationship priority inference
- Returns plain text or None
- Never calls LLM
- Idempotent: safe to call multiple times per request
"""

import logging

from apps.life.services.event_signals import (
    infer_relationship_priority,
    PRIORITY_SELF,
    PRIORITY_SPOUSE,
    PRIORITY_CHILD,
    PRIORITY_FAMILY,
)

logger = logging.getLogger(__name__)


def build_event_acknowledgment(user):
    """
    Build deterministic acknowledgment text for today's significant events.

    Queries the database directly — does NOT rely on SAE cache. This ensures
    the acknowledgment is always current, even if the SAE hasn't refreshed.

    Args:
        user: Django User instance.

    Returns:
        str or None: Acknowledgment text to prepend, or None if no events.
    """
    try:
        from apps.core.utils import get_user_today
        from apps.life.models import SignificantEvent

        today = get_user_today(user)
        today_events = []

        for event in SignificantEvent.objects.filter(user=user):
            try:
                days_until = event.days_until_next(today)
                if days_until == 0:
                    event_info = {
                        "title": event.title,
                        "type": event.event_type,
                        "days_until": 0,
                        "person": event.person_name or "",
                    }
                    if event.original_year:
                        event_info["years"] = today.year - event.original_year
                    # Enrich with structured relationship data
                    if event.person_id:
                        try:
                            person_obj = event.person
                            event_info["person_type"] = person_obj.person_type
                            rel = person_obj.relationships.first()
                            if rel:
                                event_info["relationship_type"] = (
                                    rel.relationship_type
                                )
                        except Exception:
                            pass
                    today_events.append(event_info)
            except Exception:
                logger.warning(
                    "Event acknowledgment: skipped event pk=%s",
                    getattr(event, 'pk', '?'),
                    exc_info=True,
                )
                continue

        if not today_events:
            return None

        return _format_acknowledgment(today_events)

    except Exception:
        logger.error(
            "CRITICAL: Event acknowledgment builder failed for user %s",
            getattr(user, 'id', '?'),
            exc_info=True,
        )
        return None


def _format_acknowledgment(today_events):
    """
    Format acknowledgment text from today's events.

    Rules:
    - Self birthday: warm, celebratory
    - Spouse/family: clear mention
    - Memorial: respectful
    - Multiple: combine on separate lines
    - Simple and deterministic — no LLM

    Returns:
        str or None
    """
    parts = []

    for event in today_events:
        priority = infer_relationship_priority(event)
        event_type = event.get("type", "other")
        person = event.get("person") or event.get("title", "")
        years = event.get("years")
        years_text = f" ({years} years)" if years else ""

        if event_type == "birthday":
            if priority == PRIORITY_SELF:
                if years:
                    parts.append(f"Happy birthday, {person}! Turning {years} today.")
                else:
                    parts.append(f"Happy birthday, {person}!")
            elif priority <= PRIORITY_FAMILY:
                parts.append(
                    f"Today is {person}'s birthday{years_text}."
                )
            else:
                parts.append(
                    f"Today is {person}'s birthday{years_text}."
                )

        elif event_type == "anniversary":
            if years:
                parts.append(
                    f"Today is your {_ordinal(years)} anniversary."
                )
            else:
                parts.append("Today is your anniversary.")

        elif event_type == "memorial":
            if years:
                parts.append(
                    f"Remembering {person} today{years_text}."
                )
            else:
                parts.append(f"Remembering {person} today.")

        elif event_type == "milestone":
            parts.append(
                f"Today marks {event.get('title', person)}{years_text}."
            )

        else:
            # holiday, other
            parts.append(
                f"Today: {event.get('title', person)}{years_text}."
            )

    if not parts:
        logger.error(
            "CRITICAL: %d today_events but no acknowledgment parts built",
            len(today_events),
        )
        return None

    return "\n".join(parts)


def _ordinal(n):
    """Return ordinal string for an integer (1st, 2nd, 3rd, etc.)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
