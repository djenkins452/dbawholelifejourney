"""
Critical Signal Acknowledgment Layer — Deterministic Post-LLM Injection.

This module provides the deterministic guarantee that critical signals
(today's significant events, and in the future: health alerts, missed
commitments, etc.) are ALWAYS acknowledged in responses, regardless of
LLM behavior or mode.

Architecture:
- System determines WHAT must be said (this module)
- LLM determines HOW it is expressed (advisory context in CoS)
- Deterministic injection guarantees inclusion (post-LLM fallback)
- Queries SignificantEvent model directly (no SAE cache dependency)
- Never calls LLM
- Idempotent: safe to call multiple times per request

Signal types (extensible):
- significant_event: birthdays, anniversaries, memorials, milestones
- (future) health_critical: medication risk, vital alerts
- (future) execution_critical: missed commitments, urgent deadlines
"""

import logging

from apps.life.services.event_signals import (
    infer_relationship_priority,
    PRIORITY_SELF,
    PRIORITY_SPOUSE,
    PRIORITY_CHILD,
    PRIORITY_FAMILY,
    PRIORITY_LABELS,
)

logger = logging.getLogger(__name__)

# Event-type keywords used for idempotency detection.
# If the LLM response contains the event-type keyword + person name,
# the deterministic injection is skipped (LLM already acknowledged).
_EVENT_TYPE_KEYWORDS = {
    "birthday": {"birthday", "born", "turning"},
    "anniversary": {"anniversary"},
    "memorial": {"remembering", "memorial", "memory", "honor"},
    "milestone": {"milestone", "marks"},
    "holiday": {"holiday"},
}


# ─────────────────────────────────────────────────────────────────
# Structured critical event objects
# ─────────────────────────────────────────────────────────────────

def get_today_critical_events(user):
    """
    Return structured critical event objects for today.

    Each event is a dict with:
        type: str — event type (birthday, anniversary, memorial, etc.)
        priority: str — relationship priority label (self, spouse, family, etc.)
        priority_rank: int — numeric priority (1=self, 5=general)
        person: str — person name
        title: str — event title
        years: int or None — years since original event
        message: str — deterministic acknowledgment text
        keywords: set — keywords for idempotency matching

    Args:
        user: Django User instance.

    Returns:
        list[dict]: Structured events sorted by priority (highest first).
        Empty list if no events today.
    """
    try:
        from apps.core.utils import get_user_today
        from apps.life.models import SignificantEvent

        today = get_user_today(user)
        events = []

        for event in SignificantEvent.objects.filter(user=user):
            try:
                days_until = event.days_until_next(today)
                if days_until != 0:
                    continue

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

                priority_rank = infer_relationship_priority(event_info)
                priority_label = PRIORITY_LABELS.get(
                    priority_rank, "general"
                )

                message = _build_single_message(
                    event_info, priority_rank,
                )
                keywords = _get_detection_keywords(event_info)

                events.append({
                    "type": event_info["type"],
                    "priority": priority_label,
                    "priority_rank": priority_rank,
                    "person": event_info.get("person", ""),
                    "title": event_info.get("title", ""),
                    "years": event_info.get("years"),
                    "message": message,
                    "keywords": keywords,
                })
            except Exception:
                logger.warning(
                    "Critical event: skipped event pk=%s",
                    getattr(event, 'pk', '?'),
                    exc_info=True,
                )
                continue

        # Sort by priority (self first, general last)
        events.sort(key=lambda e: e["priority_rank"])
        return events

    except Exception:
        logger.error(
            "CRITICAL: get_today_critical_events failed for user %s",
            getattr(user, 'id', '?'),
            exc_info=True,
        )
        return []


def build_event_acknowledgment(user):
    """
    Build deterministic acknowledgment text for today's significant events.

    Convenience wrapper: calls get_today_critical_events() and joins messages.

    Args:
        user: Django User instance.

    Returns:
        str or None: Acknowledgment text to prepend, or None if no events.
    """
    events = get_today_critical_events(user)
    if not events:
        return None

    messages = [e["message"] for e in events if e.get("message")]
    if not messages:
        logger.error(
            "CRITICAL: %d today events but no messages built for user %s",
            len(events), getattr(user, 'id', '?'),
        )
        return None

    return "\n".join(messages)


def check_response_acknowledges_events(response, events):
    """
    Check whether the LLM response already acknowledges the critical events.

    Uses event-type keyword matching: the response must contain at least one
    keyword for the event type (e.g., "birthday") AND mention the person name
    (for non-self events). This prevents false positives from generic phrases
    like "hope you have a great day."

    Args:
        response: str — LLM response text.
        events: list[dict] — from get_today_critical_events().

    Returns:
        list[dict]: Events that are NOT acknowledged (need injection).
    """
    if not response or not events:
        return events or []

    resp_lower = response.lower()
    unacknowledged = []

    for event in events:
        keywords = event.get("keywords", set())
        person = (event.get("person") or "").lower().strip()
        event_type = event.get("type", "")

        # Check 1: response must contain an event-type keyword
        has_keyword = any(kw in resp_lower for kw in keywords)

        # Check 2: for non-self events, response should mention person name
        if event.get("priority") == "self":
            # Self events: keyword alone is sufficient
            # ("Happy birthday" is enough for user's own birthday)
            if has_keyword:
                continue  # Acknowledged
        else:
            # Other events: need keyword + person name
            has_person = bool(person) and person in resp_lower
            if has_keyword and has_person:
                continue  # Acknowledged

        unacknowledged.append(event)

    return unacknowledged


# ─────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────

def _build_single_message(event_info, priority_rank):
    """Build acknowledgment message for a single event."""
    event_type = event_info.get("type", "other")
    person = event_info.get("person") or event_info.get("title", "")
    years = event_info.get("years")
    years_text = f" ({years} years)" if years else ""

    if event_type == "birthday":
        if priority_rank == PRIORITY_SELF:
            if years:
                return f"Happy birthday, {person}! Turning {years} today."
            return f"Happy birthday, {person}!"
        return f"Today is {person}'s birthday{years_text}."

    if event_type == "anniversary":
        if years:
            return f"Today is your {_ordinal(years)} anniversary."
        return "Today is your anniversary."

    if event_type == "memorial":
        if years:
            return f"Remembering {person} today{years_text}."
        return f"Remembering {person} today."

    if event_type == "milestone":
        return f"Today marks {event_info.get('title', person)}{years_text}."

    # holiday, other
    return f"Today: {event_info.get('title', person)}{years_text}."


def _get_detection_keywords(event_info):
    """Get keywords for idempotency detection based on event type."""
    event_type = event_info.get("type", "other")
    base = _EVENT_TYPE_KEYWORDS.get(event_type, set())
    # Also include the person name as a keyword for better matching
    person = (event_info.get("person") or "").lower().strip()
    result = set(base)
    if person:
        result.add(person)
    return result


def _ordinal(n):
    """Return ordinal string for an integer (1st, 2nd, 3rd, etc.)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
