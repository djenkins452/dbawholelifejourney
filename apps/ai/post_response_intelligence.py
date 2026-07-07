# ==============================================================================
# File: apps/ai/post_response_intelligence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Canonical post-response evidence-writing pass (Phase 0A reconnect)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-07
# ==============================================================================
"""
Canonical post-response intelligence — the SINGLE evidence-writing pass that runs
after Beth answers, on every conversational runtime (ChatGPT CoS, legacy
streaming, legacy non-streaming).

WHY THIS EXISTS (Phase 0A — "Modify Before Adding")
    This logic was duplicated three ways: WORKING inline in apps/ai/views.py,
    BROKEN in apps/ai/tasks.py::_run_chat_post_response (two dead imports —
    `apps.ai.learning_extraction`, `apps.ai.correction_detector` — plus a
    wrong-arity `detect_patterns` call, all silently swallowed), and ABSENT
    entirely from the production ChatGPT CoS path. This module consolidates the
    proven implementation into one fail-open function so all three runtimes write
    the same evidence, and the broken/absent paths are reconnected by reuse.

SCOPE — evidence/personalization WRITES ONLY. This function:
    - extracts user-preference learning        (UserLearnedProfile)  — non-truth
    - RECORDS corrections                       (CorrectionRecord)    — evidence
    - detects behavioral patterns               (BehavioralPattern)
    - extracts biographical life facts          (PersonalFact)

    It performs NO prompt injection, NO behavior-directive learning
    (`behavior_guidance.learn()`), and NO correction read-back
    (`get_correction_context_block`). Those are *gated learning* surfaces that,
    per the Executive Reflection Architecture (P2 default-deny, P3 never learn
    around deterministic defects), may only be wired behind the Phase 0B failure
    classifier. Recording an evidence row is safe; acting on it is not — and this
    module only records.

    See docs/WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE.md.

CONTRACT: never raises. Each extractor is independently guarded so one failure
    cannot suppress the others or bubble up to fail the chat turn (WLJ Rule 6,
    fail-open).
"""

import logging

logger = logging.getLogger(__name__)


def run_post_response_intelligence(user, message, response_text, conversation):
    """Write post-response evidence for one completed turn. Fail-open; no returns.

    Args:
        user: Django User instance.
        message: the user's message text for this turn.
        response_text: Beth's response text for this turn (may be "").
        conversation: the AssistantConversation (may be None).
    """
    if not user or not message:
        return

    resp = response_text or ""

    # 1) User-preference learning (non-truth) + confidence evolution.
    try:
        from apps.core.ai_learning.learning_extractor import (
            evolve_profile,
            extract_learning,
        )
        extract_learning(user, message, resp)
        evolve_profile(user)
    except Exception as e:
        logger.debug("post-response learning extraction failed: %s", e)

    # 2) Correction RECORDING (evidence only — no read-back, no override).
    try:
        from apps.ai.correction_service import detect_correction, store_correction
        if detect_correction(message) and conversation is not None:
            prev = (
                conversation.messages.filter(role="assistant")
                .order_by("-created_at")
                .first()
            )
            if prev:
                store_correction(
                    user=user,
                    user_message=message,
                    original_response=prev.content,
                    conversation=conversation,
                    original_message_id=prev.id,
                )
    except Exception as e:
        logger.debug("post-response correction recording failed: %s", e)

    # 3) Behavioral pattern detection.
    try:
        from apps.ai.pattern_detector import detect_patterns
        detect_patterns(user)
    except Exception as e:
        logger.debug("post-response pattern detection failed: %s", e)

    # 4) Biographical life-fact extraction (family, milestones -> PersonalFact).
    try:
        from apps.core.ai_memory.life_fact_extractor import (
            extract_life_facts_from_message,
        )
        extract_life_facts_from_message(user, message, resp)
    except Exception as e:
        logger.debug("post-response life fact extraction failed: %s", e)

    # 5) Executive Reflection (Phase 4). Runs AFTER evidence is written (it
    # consumes that evidence), off the request path, fail-open. It assesses the
    # turn, classifies any failure deterministically, and routes to exactly one
    # disposition (reinforce / learn [default-deny] / EIO / observe). It NEVER
    # modifies deterministic truth. See docs/WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE.md.
    try:
        from apps.ai.reflection.engine import reflect_on_turn
        reflect_on_turn(user, message, resp, conversation)
    except Exception as e:
        logger.debug("post-response executive reflection failed: %s", e)
