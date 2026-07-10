# ==============================================================================
# File: apps/ai/checkin_author.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: OpenAI authors the entire proactive Check-in from deterministic truth.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-10
# ==============================================================================
"""
Check-in authoring — WLJ assembles deterministic truth; OpenAI writes the words.

This retires the WLJ-authored check-in renderer. The proactive Check-in message is now
authored end-to-end by the conversational model from the Executive Context Envelope
(Current Context · Current Action · Execution State + Timing · Mission Link · AI
Relationship). WLJ contributes NO motivational or coaching prose and NO judgment — it
supplies facts and calculations; the model recognizes the moment, judges the situation,
connects to the mission, and speaks.

Triggering logic and execution policy are unchanged and live elsewhere (proactive_checkins,
the routers) — this module only replaces the AUTHORING of the message.

Degrades to the canonical next-action DIRECTIVE (a deterministic fact line, not the retired
prose) when the model is unavailable, so a check-in is never a fabricated status report.
"""

import json
import logging

logger = logging.getLogger(__name__)

_PHASE_HINT = {
    "morning": "It is morning — the user is starting their day.",
    "midday": "It is midday — the day is in progress.",
    "evening": "It is evening — the day is winding down.",
    "end_of_day": "It is the end of the day.",
}


def _derive_phase(user):
    try:
        from apps.core.utils import get_user_now
        h = get_user_now(user).hour
    except Exception:
        return None
    if h < 10:
        return "morning"
    if h < 15:
        return "midday"
    if h < 21:
        return "evening"
    return "end_of_day"


def _system_prompt(envelope, phase) -> str:
    from apps.ai.model_interface.constitution import CONSTITUTION
    return (
        CONSTITUTION
        + "\n\n=== PROACTIVE CHECK-IN (author this now) ===\n"
        + (_PHASE_HINT.get(phase or "", "") + "\n")
        + "Author the user's proactive check-in, in your own natural voice, from the "
          "deterministic truth below. Recognize the moment. If a high-priority action is "
          "due or late (see `current_action` / `execution_state`), lead with it. When the "
          "truth carries a `mission_link`, connect that action to the mission using the "
          "mission's `why_it_matters` from `missions`. Give ONE clear next action, then "
          "stop. Judge the situation yourself (behind / on time / at risk) from the timing "
          "FACTS — WLJ does not label it. Use ONLY the truth provided; never invent a time, "
          "task, mission, or number. Be brief and human — a trusted Chief of Staff, not a "
          "status report; no lists of everything, no filler.\n"
        + "\n=== DETERMINISTIC TRUTH ===\n"
        + json.dumps(envelope, ensure_ascii=False, default=str)
    )


def author_checkin(user, *, phase=None) -> str:
    """OpenAI authors the entire proactive check-in from the Executive Context Envelope.

    WLJ assembles the truth; the model writes the message. Returns the authored text, or —
    if the model is unavailable — the canonical next-action directive (a deterministic fact,
    never the retired prose). Never raises."""
    phase = phase or _derive_phase(user)

    try:
        from apps.ai.model_interface.service import ModelInterfaceService
        envelope = ModelInterfaceService(user).build_standing_context()
    except Exception:  # pragma: no cover - defensive
        logger.warning("checkin_author: envelope assembly failed", exc_info=True)
        envelope = {}

    try:
        from apps.ai.services import ai_service
        text = ai_service._call_api(
            _system_prompt(envelope, phase), "",
            max_tokens=400, endpoint="proactive_checkin", user=user,
        )
        if text and str(text).strip():
            return str(text).strip()
    except Exception:
        logger.warning("checkin_author: model authoring failed", exc_info=True)

    # Degraded (model unavailable): the canonical next-action directive — a FACT, not prose.
    try:
        from apps.core.execution.decision_authority import current_action_directive
        return current_action_directive(user)
    except Exception:  # pragma: no cover - defensive
        return "Here's where things stand — ask me what's on your plate."
