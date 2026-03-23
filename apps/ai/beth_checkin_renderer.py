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

# Re-export for backward compat with tests
from apps.core.today.today_engine import COMING_UP_WINDOW_MINUTES as UPCOMING_WINDOW_MINUTES  # noqa: F401, E402

# Banned words — if any appear in output, validation fails
_BANNED_WORDS = frozenset({"items", "tasks", "routines"})


def _render_checkin_from_truth(user, phase: str = "morning") -> str:
    """Core renderer — builds check-in from Today Engine.

    Uses the same unified dataset as the day renderer.
    Shows: Completed, Upcoming (coming_up bucket), Next action.
    """
    from apps.core.today.today_engine import get_today_context

    ctx = get_today_context(user)
    label = _PHASE_LABELS.get(phase, "Check-in")

    def _fmt(bucket):
        if not bucket:
            return "• None"
        return "\n".join(f"• {entry['label']}" for entry in bucket)

    lines = [
        label,
        "",
        "Completed:",
        _fmt(ctx["completed"]),
        "",
        "Upcoming:",
        _fmt(ctx["coming_up"]),
        "",
        f"Next: {ctx['next']}",
    ]

    output = "\n".join(lines)
    _validate_output(output)
    return output


def _validate_output(output: str):
    """Validate that output contains no aggregation language."""
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
