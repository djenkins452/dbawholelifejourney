"""
Deterministic Check-in Renderer — Phase 5.2+ Safety Layer

Renders morning/midday/evening check-ins using ONLY deterministic data.
The LLM is NOT involved in generating any state description.

DATA SOURCES (exclusively):
- Execution Truth Engine (via cos_fact_statements.build_locked_facts)
- Locked Next Action (via cos_fact_statements.build_locked_next_action)
- Current time (for upcoming items)

NO:
- LLM generation of state
- Coaching or commentary
- Interpretation or inferred priorities
"""

import logging
from datetime import datetime

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
    "Next: Start with your next planned item."
)


def _render_checkin_from_truth(user, phase: str = "morning") -> str:
    """Core renderer — builds check-in from execution truth."""
    from apps.ai.cos_fact_statements import build_locked_facts

    facts = build_locked_facts(user)
    raw = facts.get("_raw", {})

    label = _PHASE_LABELS.get(phase, "Check-in")

    # -- Completed items --
    completed = []
    if raw.get("prayer_done"):
        completed.append("Prayer")
    if raw.get("bible_done"):
        completed.append("Bible reading")
    if raw.get("workout_done"):
        completed.append("Workout")
    if raw.get("journal_done"):
        completed.append("Journal entry")

    routine_done = raw.get("routine_done", 0)
    routine_total = raw.get("routine_total", 0)
    tasks_done = raw.get("tasks_done", 0)

    if routine_done > 0:
        completed.append(f"{routine_done} of {routine_total} routines")
    if tasks_done > 0:
        completed.append(
            f"{tasks_done} task{'s' if tasks_done != 1 else ''}"
        )

    completed_text = (
        "\n".join(f"• {item}" for item in completed)
        if completed
        else "• None"
    )

    # -- Upcoming / Still pending --
    upcoming = []
    if raw.get("workout_expected") and not raw.get("workout_done"):
        upcoming.append("Workout")
    if raw.get("bible_expected") and not raw.get("bible_done"):
        upcoming.append("Bible reading")
    if raw.get("prayer_expected") and not raw.get("prayer_done"):
        upcoming.append("Prayer")
    if raw.get("journal_expected") and not raw.get("journal_done"):
        upcoming.append("Journal entry")

    # Pending routines
    pending_routines = routine_total - routine_done
    if pending_routines > 0:
        upcoming.append(
            f"{pending_routines} routine item{'s' if pending_routines != 1 else ''}"
        )

    upcoming_text = (
        "\n".join(f"• {item}" for item in upcoming)
        if upcoming
        else "• All clear"
    )

    # -- Next action --
    next_action = facts.get("next_action", "")
    if not next_action or next_action == "Unable to determine.":
        if upcoming:
            next_action = f"Start with {upcoming[0]}."
        else:
            next_action = "All items are complete — nothing pending."

    # -- Build output --
    lines = [
        label,
        "",
        "Completed:",
        completed_text,
        "",
        "Upcoming:" if phase == "morning" else "Still pending:",
        upcoming_text,
        "",
        f"Next: {next_action}",
    ]

    return "\n".join(lines)


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
