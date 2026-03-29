"""
Significant Event Signal Builder — deterministic signals from life events.

Pure function contract:
- NO DB queries (reads from pre-computed state dict only)
- NO user object access
- NO caching, NO side effects
- Empty state = empty signal list

Signal types:
- significant_event_today: Event happening today (mandatory acknowledgment)
- significant_event_upcoming: Event within 14-day window
- gift_consideration_window: Spouse/family birthday within 14 days

Relationship priority order: self > spouse > child > family > general
"""

# Relationship priority tiers (lower = higher priority)
PRIORITY_SELF = 1
PRIORITY_SPOUSE = 2
PRIORITY_CHILD = 3
PRIORITY_FAMILY = 4
PRIORITY_GENERAL = 5

PRIORITY_LABELS = {
    PRIORITY_SELF: "self",
    PRIORITY_SPOUSE: "spouse",
    PRIORITY_CHILD: "child",
    PRIORITY_FAMILY: "family",
    PRIORITY_GENERAL: "general",
}

# Keywords for deterministic relationship inference from person_name
# Used ONLY when no structured relationship data is available
_SELF_KEYWORDS = {"me", "myself", "my birthday", "danny", "self"}
_SPOUSE_KEYWORDS = {"wife", "husband", "spouse", "beth", "babe"}
_CHILD_KEYWORDS = {"son", "daughter", "kid", "child"}
_FAMILY_KEYWORDS = {
    "mom", "dad", "mother", "father", "parent",
    "brother", "sister", "grandma", "grandpa",
    "grandmother", "grandfather", "aunt", "uncle",
    "cousin", "niece", "nephew", "in-law",
}


def infer_relationship_priority(event_info):
    """
    Deterministic relationship priority from event data.

    Uses structured relationship_type if available (from Person FK),
    otherwise falls back to keyword matching on person_name and title.

    Args:
        event_info: dict with keys: title, type, person, days_until,
                    and optionally: relationship_type, person_type

    Returns:
        int: Priority tier (1=self, 2=spouse, ... 5=general)
    """
    # Prefer structured data from Person → Relationship
    rel_type = (event_info.get("relationship_type") or "").lower().strip()
    if rel_type:
        if rel_type in ("self",):
            return PRIORITY_SELF
        if rel_type in ("spouse", "wife", "husband", "partner"):
            return PRIORITY_SPOUSE
        if rel_type in ("child", "son", "daughter"):
            return PRIORITY_CHILD
        if rel_type in (
            "parent", "mother", "father", "sibling", "brother", "sister",
            "grandparent", "family",
        ):
            return PRIORITY_FAMILY

    # Fall back to person_type from Person model
    person_type = (event_info.get("person_type") or "").lower().strip()
    if person_type == "family":
        return PRIORITY_FAMILY

    # Fall back to keyword matching on person_name + title
    text = f"{event_info.get('person', '')} {event_info.get('title', '')}".lower()

    # Check self first (user's own birthday)
    if any(kw in text for kw in _SELF_KEYWORDS):
        return PRIORITY_SELF

    if any(kw in text for kw in _SPOUSE_KEYWORDS):
        return PRIORITY_SPOUSE

    if any(kw in text for kw in _CHILD_KEYWORDS):
        return PRIORITY_CHILD

    if any(kw in text for kw in _FAMILY_KEYWORDS):
        return PRIORITY_FAMILY

    return PRIORITY_GENERAL


def _signal(key, state, **kwargs):
    """Build a signal dict following project convention."""
    sig = {"key": key, "state": state}
    for k, v in kwargs.items():
        if v is not None:
            sig[k] = v
    return sig


def build_significant_event_signals(events_state):
    """
    Build deterministic signals from significant events state.

    Args:
        events_state: dict from build_life_events_state() with keys:
            - today_events: list of event dicts (days_until == 0)
            - approaching_events: list of event dicts (days_until <= 14)

    Returns:
        list[dict]: Signal dicts with keys: key, state, priority,
                    priority_label, insight, events
    """
    if not events_state:
        return []

    signals = []
    today_events = events_state.get("today_events", [])
    approaching = events_state.get("approaching_events", [])

    # ── Signal 1: significant_event_today ──────────────────────────
    if today_events:
        # Enrich with priority
        enriched = []
        highest_priority = PRIORITY_GENERAL
        for ev in today_events:
            priority = infer_relationship_priority(ev)
            highest_priority = min(highest_priority, priority)
            enriched.append({**ev, "priority": priority})

        # Build human-readable insight
        names = []
        for ev in enriched:
            person = ev.get("person", "")
            label = person if person else ev.get("title", "Event")
            years = ev.get("years")
            if years:
                label += f" ({years} years)"
            names.append(label)

        if len(names) == 1:
            insight = f"Today is {enriched[0].get('title', names[0])}."
        else:
            insight = f"Today's events: {', '.join(names)}."

        signals.append(_signal(
            "significant_event_today",
            "active",
            priority=highest_priority,
            priority_label=PRIORITY_LABELS.get(highest_priority, "general"),
            insight=insight,
            events=enriched,
            mandatory=True,  # CoS MUST acknowledge
        ))

    # ── Signal 2: significant_event_upcoming ───────────────────────
    upcoming = [e for e in approaching if e.get("days_until", 0) > 0]
    if upcoming:
        enriched_upcoming = []
        highest_upcoming = PRIORITY_GENERAL
        for ev in upcoming:
            priority = infer_relationship_priority(ev)
            highest_upcoming = min(highest_upcoming, priority)
            enriched_upcoming.append({**ev, "priority": priority})

        # Sort by priority then days_until
        enriched_upcoming.sort(key=lambda e: (e["priority"], e["days_until"]))

        top = enriched_upcoming[0]
        days = top["days_until"]
        person = top.get("person") or top.get("title", "Event")
        insight = f"{person}'s {top.get('type', 'event')} is in {days} day{'s' if days != 1 else ''}."

        signals.append(_signal(
            "significant_event_upcoming",
            "approaching",
            priority=highest_upcoming,
            priority_label=PRIORITY_LABELS.get(highest_upcoming, "general"),
            insight=insight,
            events=enriched_upcoming,
        ))

    # ── Signal 3: gift_consideration_window ────────────────────────
    gift_events = [
        e for e in upcoming
        if e.get("type") == "birthday"
        and infer_relationship_priority(e) <= PRIORITY_FAMILY
        and e.get("days_until", 99) <= 14
    ]
    if gift_events:
        top_gift = min(gift_events, key=lambda e: infer_relationship_priority(e))
        person = top_gift.get("person") or top_gift.get("title", "Someone")
        days = top_gift["days_until"]
        signals.append(_signal(
            "gift_consideration_window",
            "open",
            priority=infer_relationship_priority(top_gift),
            insight=f"{person}'s birthday is in {days} days — gift planning window.",
        ))

    return signals
