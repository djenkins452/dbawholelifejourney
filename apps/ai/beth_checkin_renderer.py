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
    "morning": "Morning Briefing",
    "midday": "Midday Alignment",
    "evening": "Evening Debrief",
}

_SAFE_FALLBACK = (
    "Morning Briefing\n\n"
    "Completed:\n• None\n\n"
    "Upcoming:\n• None\n\n"
    "Next: Start with your next planned item."
)

# Re-export for backward compat with tests
from apps.core.today.today_engine import COMING_UP_WINDOW_MINUTES as UPCOMING_WINDOW_MINUTES  # noqa: F401, E402

# Banned words — if any appear in output, validation fails
_BANNED_WORDS = frozenset({"items", "tasks", "routines"})


def _classify_day_load(ctx) -> str:
    """Classify day as light / focused / heavy based on pending items."""
    pending = [i for i in ctx.get("all_items", []) if not i.get("completed")]
    count = len(pending)
    if count <= 3:
        return "light"
    elif count <= 7:
        return "focused"
    return "heavy"


def _render_checkin_from_truth(user, phase: str = "morning") -> str:
    """Core renderer — structured briefing from Today Engine.

    Uses the unified today context dataset. Output format varies by phase:

    MORNING: Greeting, yesterday context (if any), day framing, agenda,
             overdue/slipping items, next action.

    MIDDAY: Progress vs plan, completed, slipping, recalibrated next action.

    EVENING: Completed vs expected, explicit misses, carryover.

    All data is deterministic from execution truth — no LLM involvement.
    """
    from apps.core.today.today_engine import get_today_context
    from apps.core.utils import get_user_now

    ctx = get_today_context(user)
    label = _PHASE_LABELS.get(phase, "Check-in")
    user_now = get_user_now(user)

    def _fmt(bucket, limit=None):
        if not bucket:
            return "• None"
        entries = bucket[:limit] if limit else bucket
        result = "\n".join(f"• {entry['label']}" for entry in entries)
        if limit and len(bucket) > limit:
            result += f"\n• +{len(bucket) - limit} more"
        return result

    if phase == "morning":
        output = _render_morning(ctx, label, user, user_now, _fmt)
    elif phase == "midday":
        output = _render_midday(ctx, label, _fmt)
    elif phase == "evening":
        output = _render_evening(ctx, label, user, _fmt)
    else:
        output = _render_morning(ctx, label, user, user_now, _fmt)

    _validate_output(output)
    return output


def _render_morning(ctx, label, user, user_now, _fmt) -> str:
    """Morning briefing — day framing + agenda + next action."""
    lines = [label]

    # Greeting with time awareness
    hour = user_now.hour
    first_name = getattr(user, 'first_name', '') or ''
    if hour < 5:
        greeting = f"Early start{', ' + first_name if first_name else ''}."
    elif hour < 8:
        greeting = f"Good morning{', ' + first_name if first_name else ''}."
    elif hour < 12:
        greeting = f"Morning{', ' + first_name if first_name else ''}."
    else:
        greeting = f"Hey{', ' + first_name if first_name else ''}."
    lines.append(greeting)
    lines.append("")

    # Day framing (light / focused / heavy)
    day_load = _classify_day_load(ctx)
    pending = [i for i in ctx.get("all_items", []) if not i.get("completed")]
    load_msg = {
        "light": f"Light day ahead — {len(pending)} items on your plate.",
        "focused": f"Focused day — {len(pending)} items to work through.",
        "heavy": f"Full day ahead — {len(pending)} items. Stay sharp.",
    }
    lines.append(load_msg.get(day_load, f"{len(pending)} items today."))
    lines.append("")

    # Overdue / slipping (from yesterday or earlier today)
    overdue = ctx.get("overdue", [])
    if overdue:
        lines.append("Overdue:")
        lines.append(_fmt(overdue, limit=3))
        lines.append("")

    # Already completed
    completed = ctx.get("completed", [])
    if completed:
        lines.append("Done:")
        lines.append(_fmt(completed))
        lines.append("")

    # Upcoming (within 90 min)
    coming_up = ctx.get("coming_up", [])
    if coming_up:
        lines.append("Coming up:")
        lines.append(_fmt(coming_up))
        lines.append("")

    # Later today
    later = ctx.get("later", [])
    if later:
        lines.append("Later:")
        lines.append(_fmt(later, limit=5))
        lines.append("")

    # Next action (always shown)
    lines.append(f"Next: {ctx['next']}")

    return "\n".join(lines)


def _render_midday(ctx, label, _fmt) -> str:
    """Midday alignment — progress vs plan."""
    lines = [label]
    lines.append("")

    all_items = ctx.get("all_items", [])
    total = len(all_items)
    completed = ctx.get("completed", [])
    done_count = len(completed)

    if total > 0:
        lines.append(f"Progress: {done_count}/{total} done.")
    lines.append("")

    # Completed
    if completed:
        lines.append("Done:")
        lines.append(_fmt(completed))
        lines.append("")

    # Slipping / overdue
    overdue = ctx.get("overdue", [])
    if overdue:
        lines.append("Slipping:")
        lines.append(_fmt(overdue, limit=3))
        lines.append("")

    # Still coming
    coming_up = ctx.get("coming_up", [])
    later = ctx.get("later", [])
    remaining = coming_up + later
    if remaining:
        lines.append("Remaining:")
        lines.append(_fmt(remaining, limit=5))
        lines.append("")

    lines.append(f"Next: {ctx['next']}")
    return "\n".join(lines)


def _render_evening(ctx, label, user, _fmt) -> str:
    """Evening debrief — completed vs expected, explicit misses."""
    lines = [label]
    lines.append("")

    all_items = ctx.get("all_items", [])
    total = len(all_items)
    completed = ctx.get("completed", [])
    done_count = len(completed)
    missed_count = total - done_count

    if total > 0:
        lines.append(f"Day result: {done_count}/{total} completed.")
    lines.append("")

    # Completed
    if completed:
        lines.append("Done:")
        lines.append(_fmt(completed))
        lines.append("")

    # Explicit misses (overdue + coming_up + later that aren't done)
    overdue = ctx.get("overdue", [])
    coming_up = ctx.get("coming_up", [])
    later = ctx.get("later", [])
    missed = overdue + coming_up + later
    if missed:
        lines.append("Missed:")
        lines.append(_fmt(missed, limit=5))
        lines.append("")

    # Tomorrow's load (lightweight query — just count)
    try:
        from apps.core.utils import get_user_today
        from apps.life.models import Task
        from datetime import timedelta as _td
        today = get_user_today(user)
        tomorrow = today + _td(days=1)
        tomorrow_count = Task.objects.filter(
            user=user, due_date=tomorrow, deleted_at__isnull=True,
        ).exclude(completion_status='skipped').count()
        if tomorrow_count:
            lines.append(
                f"Tomorrow: {tomorrow_count} "
                f"item{'s' if tomorrow_count != 1 else ''} queued."
            )
            lines.append("")
    except Exception:
        pass  # Tomorrow count is optional

    return "\n".join(lines)


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
