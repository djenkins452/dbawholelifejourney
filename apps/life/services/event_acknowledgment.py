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

Signal types (extensible via signal_type_rank):
- 10: significant_event (birthdays, anniversaries, memorials, milestones)
- (future) 5: health_critical (medication risk, vital alerts)
- (future) 8: execution_critical (missed commitments, urgent deadlines)
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

# Signal type rank — lower = higher priority. Used for sorting when
# multiple signal types coexist (future: health_critical = 5).
SIGNAL_TYPE_RANK_EVENT = 10

# Event-type keywords for idempotency detection.
# Includes synonyms. If the LLM response contains at least one keyword
# for the event type, that aspect of the check passes.
_EVENT_TYPE_KEYWORDS = {
    "birthday": {"birthday", "bday", "born", "turning"},
    "anniversary": {"anniversary"},
    "memorial": {"remembering", "memorial", "memory", "honor", "honour"},
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
        priority: str — relationship priority label (self, spouse, etc.)
        priority_rank: int — numeric priority (1=self, 5=general)
        signal_type_rank: int — signal category rank (10 for events)
        person: str — person name
        title: str — event title
        years: int or None — years since original event
        message: str — deterministic acknowledgment text (single event)
        keywords: set — keywords for idempotency matching

    Args:
        user: Django User instance.

    Returns:
        list[dict]: Structured events sorted by (signal_type_rank, priority_rank).
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

                message = _build_single_message(event_info, priority_rank)
                keywords = _get_detection_keywords(event_info)

                events.append({
                    "type": event_info["type"],
                    "priority": priority_label,
                    "priority_rank": priority_rank,
                    "signal_type_rank": SIGNAL_TYPE_RANK_EVENT,
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

        # Sort by signal_type_rank first, then priority_rank within type
        events.sort(key=lambda e: (e["signal_type_rank"], e["priority_rank"]))
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

    Uses grouped formatting for natural multi-event phrasing.

    Args:
        user: Django User instance.

    Returns:
        str or None: Acknowledgment text to prepend, or None if no events.
    """
    events = get_today_critical_events(user)
    if not events:
        return None
    return build_grouped_acknowledgment(events)


def build_grouped_acknowledgment(events):
    """
    Build naturally grouped acknowledgment text from critical events.

    Rules:
    - 1 event: return its message as-is
    - 2 events: "First message — and second detail."
    - 3+ events: first message, then "Also: X and Y."

    Events must already be sorted by (signal_type_rank, priority_rank).

    Args:
        events: list[dict] — from get_today_critical_events() or filtered subset.

    Returns:
        str or None
    """
    if not events:
        return None

    messages = [e["message"] for e in events if e.get("message")]
    if not messages:
        logger.error(
            "CRITICAL: %d events but no messages built", len(events),
        )
        return None

    if len(messages) == 1:
        return messages[0]

    if len(messages) == 2:
        # Natural join: "First message — and also, second detail."
        # Strip trailing period from first for cleaner join
        first = messages[0].rstrip(".")
        second = _lowercase_first(messages[1].rstrip("."))
        return f"{first} — and {second}."

    # 3+: Lead with highest priority, summarize rest
    lead = messages[0]
    rest_parts = []
    for msg in messages[1:]:
        # Extract the core phrase (strip "Today is " / "Remembering " etc.)
        rest_parts.append(msg.rstrip("."))
    also = " and ".join(rest_parts)
    return f"{lead}\nAlso today: {also}."


def check_response_acknowledges_events(response, events):
    """
    Check whether the LLM response already acknowledges the critical events.

    Uses event-type keyword matching with synonym support:
    - Self events: must contain an event-type keyword (e.g., "birthday", "bday")
    - Other events: must contain BOTH keyword AND person name

    This prevents false positives from generic phrases like "hope you have
    a great day" while allowing natural variations like "bday".

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

        # Check 1: response must contain an event-type keyword
        has_keyword = any(kw in resp_lower for kw in keywords)

        # Check 2: for non-self events, response should mention person name
        if event.get("priority") == "self":
            if has_keyword:
                continue  # Acknowledged
        else:
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
    person = (event_info.get("person") or "").lower().strip()
    result = set(base)
    if person:
        result.add(person)
    return result


def _lowercase_first(s):
    """Lowercase the first character of a string."""
    if not s:
        return s
    return s[0].lower() + s[1:]


def _ordinal(n):
    """Return ordinal string for an integer (1st, 2nd, 3rd, etc.)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
