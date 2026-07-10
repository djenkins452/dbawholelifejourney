"""
CoS Check-in — authoring seam (RETIRED renderer).

The WLJ-authored check-in renderer has been RETIRED. WLJ assembles deterministic truth
(Current Context · Current Action · Execution State + Timing · Mission Link · AI
Relationship) into the Executive Context Envelope, and OpenAI authors the entire proactive
check-in from it (`apps/ai/checkin_author.py`). WLJ contributes NO motivational or coaching
prose and NO judgment — those are the model's.

This module now only:
  • delegates the public check-in entrypoints to the OpenAI author (triggering/policy
    callers are unchanged — they call the same functions, now model-authored);
  • exposes `build_cos_structured_output` whose FACTS come from the single Execution
    Decision Authority (`current_action`) and whose prose (`rendered_text`) is model-authored;
  • keeps the small `guard_llm_output` / `contains_state_language` safety utility other
    surfaces depend on.

Nothing here computes a briefing, a situation, an escalation level, a triage, or any prose.
"""

import logging

logger = logging.getLogger(__name__)

_SAFE_FALLBACK = (
    "Good morning.\n\n"
    "I wasn't able to load your day right now. "
    "Try asking me what's on your plate."
)

_BANNED_WORDS = frozenset({"items", "tasks", "routines", "domains"})


# ── Public check-in entrypoints — now authored by OpenAI ─────────────────────
def render_checkin_for_time(user) -> str:
    """The proactive check-in for the current time of day — authored by OpenAI from the
    deterministic truth envelope. (Name kept so triggering/policy callers are unchanged.)"""
    from apps.ai.checkin_author import author_checkin
    return author_checkin(user)


def render_morning_checkin(user) -> str:
    from apps.ai.checkin_author import author_checkin
    return author_checkin(user, phase="morning")


def render_daily_briefing(user) -> str:
    """First-of-day check-in — authored by OpenAI (was the deterministic daily briefing)."""
    from apps.ai.checkin_author import author_checkin
    return author_checkin(user)


def build_cos_structured_output(user) -> dict:
    """Structured check-in payload for surfaces that need the facts AND the message.

    FACTS (`do_now` / `sequence` / `next_action`) come from the single Execution Decision
    Authority; the PROSE (`rendered_text`) is authored by OpenAI. No deterministic briefing
    is generated here anymore."""
    do_now, sequence, next_action = [], [], None
    try:
        from apps.core.execution.decision_authority import current_action
        primary = (current_action(user) or {}).get("primary_action") or None
        if primary and primary.get("title"):
            title = primary["title"]
            next_action = primary
            do_now = [{"name": title}]
            sequence = [title]
    except Exception:  # pragma: no cover - defensive
        logger.warning("[COS STRUCTURED] current_action failed for user=%s",
                       getattr(user, "id", "?"), exc_info=True)
    try:
        from apps.ai.checkin_author import author_checkin
        rendered_text = author_checkin(user)
    except Exception:  # pragma: no cover - defensive
        logger.warning("[COS STRUCTURED] authoring failed for user=%s",
                       getattr(user, "id", "?"), exc_info=True)
        rendered_text = _SAFE_FALLBACK
    return {
        "do_now": do_now,
        "sequence": sequence,
        "next_action": next_action,
        "rendered_text": rendered_text,
    }


# ── State-language guard (kept: used to protect legacy LLM surfaces) ──────────
# If a model surface leaks first-person "state" narration (claiming what the user did /
# still needs to do), replace it with a freshly authored check-in.
_STATE_PATTERNS = [
    "you completed", "you've completed", "you have completed", "you have done",
    "you did your", "you did the", "you've done your", "you've done the",
    "you still need to", "you still need", "what's left", "on your plate",
    "your tasks include", "your remaining", "you haven't done", "you haven't completed",
    "which sets a solid tone", "sets a great tone", "solid start", "great start to",
    "productive morning", "productive start", "keep the momentum", "keep up the momentum",
    "let's keep the momentum",
]


def contains_state_language(text: str) -> bool:
    """True if `text` contains first-person state narration WLJ must not assert."""
    if not text:
        return False
    low = text.lower()
    return any(p in low for p in _STATE_PATTERNS)


def guard_llm_output(llm_output: str, user) -> str:
    """If an LLM surface leaked state language, replace it with an authored check-in."""
    if not contains_state_language(llm_output):
        return llm_output
    logger.warning("[STATE GUARD] Blocked LLM state language for user=%s",
                   getattr(user, "id", "?"))
    try:
        return render_checkin_for_time(user)
    except Exception:
        logger.error("[STATE GUARD] Authoring fallback failed for user=%s",
                     getattr(user, "id", "?"), exc_info=True)
        return _SAFE_FALLBACK
