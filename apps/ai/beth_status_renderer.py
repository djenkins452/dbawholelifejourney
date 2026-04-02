"""
Beth Status Renderer — Deterministic response contract for "what's left today?"

Beth is NOT thinking. Beth is RENDERING.

This module produces a strict, deterministic response when the user asks
about their remaining items for today. No LLM involvement. No coaching.
No drift. No creativity.

RESPONSE CONTRACT:
    Section 1 — STATE: Items where expected=True and completed=False
    Section 2 — COMPLETED: Items where completed=True (omitted if empty)
    Section 3 — NEXT: Locked next action from decision engine (REQUIRED)

STRICT PROHIBITIONS:
    - No coaching language
    - No explanations or UI guidance
    - No encouragement phrases
    - No reordering of items
    - No additional suggestions
    - No extra paragraphs

MODE DETECTION (scope limited):
    Only triggers for: "what is left today", "what do I have left",
    "what's remaining", and similar status queries.
"""

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Status query detection
# ---------------------------------------------------------------------------

_STATUS_QUERY_PHRASES = (
    "what is left today",
    "what's left today",
    "whats left today",
    "what is left to do today",
    "what's left to do today",
    "whats left to do today",
    "what is left to do",
    "what's left to do",
    "whats left to do",
    "what do i have left",
    "what do i have left today",
    "what do i have remaining",
    "what's remaining",
    "whats remaining",
    "what is remaining",
    "what's remaining today",
    "what is remaining today",
    "what remains today",
    "what remains",
    "what still needs to be done",
    "what still needs to be done today",
    "anything left today",
    "anything left to do",
    "anything remaining",
    "anything remaining today",
    "how much is left today",
    "how much is left",
    "how much do i have left",
    "show me what's left",
    "show me whats left",
    "show what's left",
    "what haven't i done today",
    "what haven't i done",
    "what havent i done today",
    "what havent i done",
    "what didn't i do today",
    "what didnt i do today",
    "what am i missing today",
    "what's still on my list",
    "whats still on my list",
    "what's on my list today",
    "what is on my list today",
    "status for today",
    "today's status",
    "todays status",
    "daily status",
    "where do i stand today",
    "where do i stand",
    "where am i at today",
    "give me my status",
    "give me today's status",
)

# Phrases that signal coaching/planning/reflection — NOT status queries
_EXCLUSION_PHRASES = (
    "should i",
    "how do i",
    "help me",
    "can you",
    "tell me about",
    "explain",
    "why",
    "what if",
    "plan",
    "planning",
    "advice",
    "suggest",
    "recommend",
    "think about",
    "reflect",
)


def is_status_query(msg_lower: str) -> bool:
    """Detect if a message is a today-status query.

    Returns True only for clear, unqualified status queries.
    Returns False for coaching, planning, reflective, or filtered questions.
    Qualified queries ("other than X, what's left?") need the LLM.
    """
    if any(phrase in msg_lower for phrase in _EXCLUSION_PHRASES):
        return False
    # Qualified/filtered queries must reach the LLM, not terminal routes
    try:
        from apps.ai.deterministic_router import is_qualified_status_query
        if is_qualified_status_query(msg_lower):
            return False
    except ImportError:
        pass
    return any(phrase in msg_lower for phrase in _STATUS_QUERY_PHRASES)


# ---------------------------------------------------------------------------
# Micro labels
# ---------------------------------------------------------------------------

def _format_micro_label(item: dict) -> str:
    """Build micro label string from execution item metadata.

    Returns empty string if no label applies.
    """
    parts = []
    scheduled_time = item.get("scheduled_time")
    if scheduled_time:
        # Convert 24h time to 12h format
        parts.append(_format_time(scheduled_time))

    importance = item.get("importance")
    if importance == "high":
        parts.append("important")

    time_status = item.get("time_status")
    if time_status == "overdue":
        parts.append("overdue")
    elif scheduled_time:
        parts.append("time-critical")

    if not parts:
        return ""
    return " (" + ", ".join(parts) + ")"


def _format_time(time_str: str) -> str:
    """Convert HH:MM to 12-hour format. Always includes minutes for consistency."""
    try:
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        period = "AM" if hour < 12 else "PM"
        display_hour = hour % 12 or 12
        return f"{display_hour}:{minute:02d} {period}"
    except (ValueError, IndexError):
        return time_str


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------

def build_status_response(user) -> str:
    """Build a strict, deterministic status response.

    Reads from:
        1. Execution Truth Engine (via locked facts)
        2. Today Execution Contract (for item-level detail)
        3. Locked Next Action (from decision engine)

    Returns a formatted string matching the Beth Response Contract.
    """
    # Get locked facts (includes next_action)
    from apps.ai.cos_fact_statements import build_locked_facts
    facts = build_locked_facts(user)
    raw = facts.get("_raw", {})
    next_action = facts.get("next_action", "")

    # Get today execution items for time/importance metadata
    remaining_items = []
    completed_items = []

    try:
        from apps.core.execution.today_execution import build_today_execution
        exec_contract = build_today_execution(user)
        items = exec_contract.get("items", [])

        # Group medication items into summaries (medical domain ONLY)
        med_remaining, med_completed = _group_medication_items(items)

        for item in items:
            title = item.get("title", "")
            if not title:
                continue
            # Skip individual medication items — handled by grouped summaries
            if item.get("source_type") == "medication_dose":
                continue
            if item.get("completed_today"):
                completed_items.append(title)
            elif item.get("is_actionable", True):
                label = title + _format_micro_label(item)
                remaining_items.append(label)

        # Inject medication group summaries
        remaining_items.extend(med_remaining)
        completed_items.extend(med_completed)

        # Add domain-level items not covered by execution items
        # (faith, workout, journal are binary domains in summaries)
        domain_summaries = exec_contract.get("summaries", {}).get("domains", {})
        _add_domain_items(
            remaining_items, completed_items,
            raw, domain_summaries, items,
        )
    except Exception:
        logger.error(
            "Beth status renderer: today_execution failed, "
            "falling back to locked facts only",
            exc_info=True,
        )
        # Fallback: build from locked facts raw data only
        _add_domain_items_from_raw(remaining_items, completed_items, raw)

    # ── Build response ──
    sections = []

    # Section 1 — STATE
    if remaining_items:
        lines = ["Here's what's left today:"]
        for item in remaining_items:
            lines.append(f"• {item}")
        sections.append("\n".join(lines))
    else:
        sections.append("You've completed everything for today.")

    # Section 2 — COMPLETED (omit if empty)
    if completed_items:
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for c in completed_items:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        completed_lines = ["Completed:"]
        for c in unique:
            completed_lines.append(f"• {c}")
        sections.append("\n".join(completed_lines))

    # Section 3 — NEXT (REQUIRED)
    if remaining_items:
        sections.append(f"Next: {next_action}")
    else:
        sections.append("Next: You're all set. No remaining actions.")

    response = "\n\n".join(sections)

    logger.info(
        "[BETH STATUS RENDERER] user=%s remaining=%d completed=%d",
        user.id, len(remaining_items), len(completed_items),
    )

    return response


def _add_domain_items(
    remaining: list,
    completed: list,
    raw: dict,
    domain_summaries: dict,
    exec_items: list,
):
    """Add binary domain items (faith, workout, journal) if not already
    covered by execution items.

    Avoids double-counting: if a routine item named "Prayer Time" is
    already in the execution items list, we don't add "Prayer" again.
    """
    # Collect existing titles (lowered) to avoid duplicates
    existing = set()
    for item in exec_items:
        existing.add((item.get("title") or "").lower())
    for r in remaining:
        # Strip micro labels for comparison
        clean = r.split(" (")[0].lower() if " (" in r else r.lower()
        existing.add(clean)
    for c in completed:
        existing.add(c.lower())

    # Faith — prayer
    if raw.get("prayer_expected"):
        if not _is_covered(existing, "prayer"):
            if raw.get("prayer_done"):
                completed.append("Prayer")
            else:
                remaining.append("Prayer")

    # Faith — Bible reading
    if raw.get("bible_expected"):
        if not _is_covered(existing, "bible"):
            if raw.get("bible_done"):
                completed.append("Bible Reading")
            else:
                remaining.append("Bible Reading")

    # Workout
    if raw.get("workout_expected"):
        if not _is_covered(existing, "workout"):
            if raw.get("workout_done"):
                completed.append("Workout")
            else:
                remaining.append("Workout")

    # Journal
    if raw.get("journal_expected"):
        if not _is_covered(existing, "journal"):
            if raw.get("journal_done"):
                completed.append("Journal")
            else:
                remaining.append("Journal")

    # Medications — fallback from raw if not already covered by grouped items
    meds_expected = raw.get("meds_expected", 0)
    if meds_expected > 0 and not _is_covered(existing, "medic"):
        if raw.get("meds_all_taken"):
            completed.append(f"Medications — all {meds_expected} doses taken")
        else:
            taken = raw.get("meds_taken", 0)
            skipped = raw.get("meds_skipped", 0)
            left = meds_expected - taken - skipped
            skip_note = f", {skipped} skipped" if skipped else ""
            remaining.append(
                f"Medications — {taken}/{meds_expected} taken"
                f" ({left} remaining{skip_note})"
            )


def _add_domain_items_from_raw(remaining: list, completed: list, raw: dict):
    """Fallback: build item lists from raw locked facts only."""
    if raw.get("prayer_expected"):
        if raw.get("prayer_done"):
            completed.append("Prayer")
        else:
            remaining.append("Prayer")

    if raw.get("bible_expected"):
        if raw.get("bible_done"):
            completed.append("Bible Reading")
        else:
            remaining.append("Bible Reading")

    if raw.get("workout_expected"):
        if raw.get("workout_done"):
            completed.append("Workout")
        else:
            remaining.append("Workout")

    if raw.get("journal_expected"):
        if raw.get("journal_done"):
            completed.append("Journal")
        else:
            remaining.append("Journal")

    # Medications
    meds_expected = raw.get("meds_expected", 0)
    if meds_expected > 0:
        if raw.get("meds_all_taken"):
            completed.append(f"Medications — all {meds_expected} doses taken")
        else:
            taken = raw.get("meds_taken", 0)
            skipped = raw.get("meds_skipped", 0)
            left = meds_expected - taken - skipped
            skip_note = f", {skipped} skipped" if skipped else ""
            remaining.append(
                f"Medications — {taken}/{meds_expected} taken"
                f" ({left} remaining{skip_note})"
            )


def _is_covered(existing_titles: set, keyword: str) -> bool:
    """Check if a domain item is already represented in execution items."""
    return any(keyword in title for title in existing_titles)


# ---------------------------------------------------------------------------
# Medication grouping — summary by window (medical domain ONLY)
# ---------------------------------------------------------------------------

_WINDOW_DISPLAY_NAMES = {
    'morning': 'Morning medicines',
    'mid_morning': 'Mid-morning medicines',
    'lunch': 'Lunch medicines',
    'afternoon': 'Afternoon medicines',
    'evening': 'Evening medicines',
    'nightly': 'Night medicines',
    'unscheduled': 'Medicines',
}


def _group_medication_items(items: list) -> tuple:
    """Group medication execution items by window and produce summary lines.

    Returns (remaining_summaries, completed_summaries) where each is a list
    of display strings like "Morning medicines — completed on time" or
    "Evening medicines — partially complete (2/3)".

    DOMAIN SCOPE: Only operates on source_type='medication_dose'.
    Does NOT touch routines, faith, journal, goals, or any other domain.
    """
    # Separate medication items from the rest
    med_items = [i for i in items if i.get('source_type') == 'medication_dose']
    if not med_items:
        return [], []

    # Group by window (execution_group_id)
    windows = {}
    for item in med_items:
        window = item.get('execution_group_id', 'unscheduled')
        if window not in windows:
            windows[window] = {
                'total': 0, 'taken': 0, 'overdue': 0,
                'meds': [],
            }
        grp = windows[window]
        grp['total'] += 1
        completed = item.get('completed_today', False)
        if completed:
            grp['taken'] += 1
        if item.get('completion_status') == 'overdue' or item.get('time_status') == 'overdue':
            grp['overdue'] += 1
        grp['meds'].append(item)

    remaining = []
    completed = []

    for window, grp in windows.items():
        display_name = _WINDOW_DISPLAY_NAMES.get(window, f'{window.title()} medicines')
        total = grp['total']
        taken = grp['taken']

        if taken >= total:
            # All taken — check timing
            all_on_time = all(
                m.get('time_status') != 'overdue'
                for m in grp['meds'] if m.get('completed_today')
            )
            timing = "on time" if all_on_time else "late"
            completed.append(f"{display_name} — completed {timing}")
        elif taken > 0:
            # Partial
            remaining.append(f"{display_name} — partially complete ({taken}/{total})")
        else:
            # None taken
            if grp['overdue'] > 0:
                remaining.append(f"{display_name} — not completed (overdue)")
            else:
                remaining.append(f"{display_name} — pending")

    return remaining, completed
