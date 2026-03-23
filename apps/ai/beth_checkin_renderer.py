"""
Deterministic Check-in Renderer — Pure Truth Layer

Renders morning/midday/evening check-ins using ONLY deterministic data.
The LLM is NOT involved in generating any state description.

DATA SOURCES (exclusively):
- Execution Truth Engine (via cos_fact_statements.build_locked_facts)
- Execution Truth raw routine items (individual named items)
- Locked Next Action (via cos_fact_statements.build_locked_next_action)
- Current time (for upcoming window filter)

RULES:
- NO aggregation (no counts, no grouping, no "X items")
- NO coaching or commentary
- NO interpretation or inferred priorities
- Every bullet = one real named item
- Upcoming = only time-bound items within 90 minutes
"""

import logging
from datetime import datetime, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def render_morning_checkin(user) -> str:
    """Render a deterministic morning check-in from execution truth.

    Returns a structured, factual check-in string with:
    - Completed items (or "None")
    - Upcoming items with times
    - Next action directive

    This output is FINAL — it is NOT passed to an LLM for rephrasing.
    """
    try:
        return _render_checkin_from_truth(user)
    except Exception:
        logger.error(
            "[CHECKIN RENDERER] Failed for user=%s, returning safe fallback",
            user.id, exc_info=True,
        )
        return _SAFE_FALLBACK


def render_checkin_for_time(user) -> str:
    """Render a check-in appropriate for the current time of day.

    Routes to morning/midday/evening format based on hour.
    All formats use the same deterministic data — only framing differs.
    """
    try:
        hour = timezone.localtime().hour
        if hour < 12:
            return _render_checkin_from_truth(user, phase="morning")
        elif hour < 17:
            return _render_checkin_from_truth(user, phase="midday")
        else:
            return _render_checkin_from_truth(user, phase="evening")
    except Exception:
        logger.error(
            "[CHECKIN RENDERER] Failed for user=%s, returning safe fallback",
            user.id, exc_info=True,
        )
        return _SAFE_FALLBACK


# ---------------------------------------------------------------------------
# Internal renderer
# ---------------------------------------------------------------------------

_PHASE_LABELS = {
    "morning": "Morning Check-in",
    "midday": "Midday Check-in",
    "evening": "Evening Check-in",
}

_SAFE_FALLBACK = (
    "Morning Check-in\n\n"
    "Completed:\n• None\n\n"
    "Upcoming:\n• None\n\n"
    "Next: Start with your next planned item."
)

# Only show upcoming items within this window from now
UPCOMING_WINDOW_MINUTES = 90

# Banned words — if any appear in output, validation fails
_BANNED_WORDS = frozenset({"items", "tasks", "routines"})


def _render_checkin_from_truth(user, phase: str = "morning") -> str:
    """Core renderer — builds check-in from execution truth.

    Rules:
    - Completed: each real completed item on its own line, or "None"
    - Upcoming: only time-bound items within UPCOMING_WINDOW_MINUTES, or "None"
    - No aggregation, no counts, no grouping
    """
    from apps.ai.cos_fact_statements import build_locked_facts
    from apps.core.execution.execution_truth_engine import get_execution_truth

    facts = build_locked_facts(user)
    raw = facts.get("_raw", {})
    truth = get_execution_truth(user)

    label = _PHASE_LABELS.get(phase, "Check-in")

    # -- Completed: individual named items only --
    completed = _get_completed_items(raw, truth)
    completed_text = (
        "\n".join(f"• {name}" for name in completed)
        if completed
        else "• None"
    )

    # -- Upcoming: time-bound items within window only --
    upcoming = _get_upcoming_items(truth, user)
    upcoming_text = (
        "\n".join(f"• {name}" for name in upcoming)
        if upcoming
        else "• None"
    )

    # -- Next action (from system, not inferred) --
    next_action = facts.get("next_action", "")
    if not next_action or next_action == "Unable to determine.":
        next_action = "Check your schedule for the next planned item."

    # -- Build output --
    lines = [
        label,
        "",
        "Completed:",
        completed_text,
        "",
        "Upcoming:",
        upcoming_text,
        "",
        f"Next: {next_action}",
    ]

    output = "\n".join(lines)

    # -- Validation: ensure no aggregation leaked through --
    _validate_output(output)

    return output


def _get_completed_items(raw: dict, truth: dict) -> list:
    """Extract individually named completed items from execution truth.

    Returns a list of human-readable item names. No counts, no grouping.
    """
    completed = []

    # Domain completions (from raw facts)
    if raw.get("prayer_done"):
        completed.append("Prayer")
    if raw.get("bible_done"):
        completed.append("Bible reading")
    if raw.get("workout_done"):
        completed.append("Workout")
    if raw.get("journal_done"):
        completed.append("Journal entry")

    # Individual completed routine items (by name, not count)
    raw_items = truth.get("routines", {}).get("_raw_items", {})
    for _window, items in raw_items.items():
        for item in items:
            if item.get("is_completed"):
                name = item.get("item_name", "").strip()
                if name and name not in completed:
                    completed.append(name)

    return completed


def _get_upcoming_items(truth: dict, user) -> list:
    """Extract time-bound upcoming items within the UPCOMING_WINDOW_MINUTES window.

    Only includes items that:
    - Have a scheduled_time
    - Are NOT completed
    - Fall within [now, now + window]

    Returns formatted strings like "Workout (6:15 AM)".
    """
    from apps.core.utils import get_user_now

    try:
        user_now = get_user_now(user)
    except Exception:
        user_now = timezone.localtime()

    window_end = user_now + timedelta(minutes=UPCOMING_WINDOW_MINUTES)
    upcoming = []

    # Routine items with scheduled times
    raw_items = truth.get("routines", {}).get("_raw_items", {})
    for _window, items in raw_items.items():
        for item in items:
            if item.get("is_completed"):
                continue

            scheduled_str = item.get("scheduled_time")
            if not scheduled_str:
                continue

            # Parse the time string (e.g., "6:15 AM") against today
            item_time = _parse_time_today(scheduled_str, user_now)
            if item_time is None:
                continue

            if user_now <= item_time <= window_end:
                name = item.get("item_name", "").strip()
                if name:
                    upcoming.append(f"{name} ({scheduled_str})")

    return upcoming


def _parse_time_today(time_str: str, now) -> datetime:
    """Parse a time string like '6:15 AM' into a datetime for today.

    Returns None if parsing fails.
    """
    try:
        parsed = datetime.strptime(time_str.strip(), "%I:%M %p")
        return now.replace(
            hour=parsed.hour, minute=parsed.minute,
            second=0, microsecond=0,
        )
    except (ValueError, AttributeError):
        return None


def _validate_output(output: str):
    """Validate that output contains no aggregation language.

    Logs a warning if banned words are found. Does NOT block output
    (fail-open for safety) but makes violations visible in logs.
    """
    output_lower = output.lower()
    for word in _BANNED_WORDS:
        if word in output_lower:
            logger.warning(
                "[CHECKIN RENDERER] VALIDATION: banned word '%s' found in output",
                word,
            )


# ---------------------------------------------------------------------------
# State guard — blocks LLM-generated state descriptions
# ---------------------------------------------------------------------------

# Patterns that indicate the LLM is fabricating user state
_STATE_PATTERNS = [
    "you completed",
    "you've completed",
    "you have completed",
    "you have done",
    "you did your",
    "you did the",
    "you've done your",
    "you've done the",
    "you still need to",
    "you still need",
    "what's left",
    "on your plate",
    "your tasks include",
    "your remaining",
    "you haven't done",
    "you haven't completed",
    "which sets a solid tone",
    "sets a great tone",
    "solid start",
    "great start to",
    "productive morning",
    "productive start",
    "keep the momentum",
    "keep up the momentum",
    "let's keep the momentum",
]


def contains_state_language(text: str) -> bool:
    """Check if text contains LLM-generated state language.

    Returns True if the text appears to contain state descriptions
    that should only come from the deterministic renderer.
    """
    if not text:
        return False
    text_lower = text.lower()
    return any(pattern in text_lower for pattern in _STATE_PATTERNS)


def guard_llm_output(llm_output: str, user) -> str:
    """Guard against LLM-generated state in output.

    If the LLM output contains state language, replace with
    the deterministic check-in renderer output.

    Returns the original output if safe, or the deterministic
    replacement if state language is detected.
    """
    if not contains_state_language(llm_output):
        return llm_output

    logger.warning(
        "[STATE GUARD] Blocked LLM state language for user=%s, "
        "replacing with deterministic check-in",
        user.id,
    )

    try:
        return render_checkin_for_time(user)
    except Exception:
        logger.error(
            "[STATE GUARD] Fallback renderer failed for user=%s",
            user.id, exc_info=True,
        )
        return _SAFE_FALLBACK
