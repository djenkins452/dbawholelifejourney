# ==============================================================================
# File: apps/ai/chatgpt_cos/reasoning/engine.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reasoning Lane orchestrator
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
Reasoning Lane orchestrator.

    User Question
      -> run_planner          (Planner LLM -> Retrieval Plan)
      -> retrieve_truth       (deterministic, authoritative)
      -> build_working_memory (curated; OpenAI sees ONLY this)
      -> run_reasoning        (one plain _call_api + deterministic fallback)
      -> answer

Returns the same result shape as ChatGPTCoSService.generate, or None when the
planner declines (intent not yet implemented / planner unavailable) so the
caller can fall through to the existing path. No agentic tool loop is used.
"""

import logging

from apps.ai.chatgpt_cos.reasoning.plan import (
    IMPLEMENTED_INTENTS,
    deterministic_health_intent,
    synthesize_health_plan,
)
from apps.ai.chatgpt_cos.reasoning.stages import (
    build_working_memory,
    retrieve_truth,
    run_planner,
    run_reasoning,
)

logger = logging.getLogger(__name__)


def answer_reasoning_question(user, message):
    """Run the Reasoning Lane. Returns a result dict, or None to fall through.

    GUARANTEE: once a question is recognized as an implemented health-reasoning
    intent (by the planner OR the deterministic resilience matcher), the lane
    ALWAYS returns an answer — OpenAI narrative when available, else a
    deterministic fallback. It never falls through to the legacy tool loop, so
    the OpenAI-failure message can never reach the user for these intents.
    """
    plan = run_planner(user, message)

    # Resilience: planner unavailable (None) OR misclassified (not implemented).
    # If the message is a recognizable implemented health intent, proceed
    # deterministically so the lane still answers; otherwise decline.
    if plan is None or plan.intent not in IMPLEMENTED_INTENTS:
        fallback_intent = deterministic_health_intent(message)
        if fallback_intent is None:
            logger.info("COS_REASONING_DECLINE user=%s intent=%s",
                        getattr(user, "id", None),
                        plan.intent if plan else "planner_none")
            return None
        logger.warning(
            "COS_REASONING_PLANNER_FALLBACK user=%s intent=%s reason=%s",
            getattr(user, "id", None), fallback_intent,
            "planner_none" if plan is None else f"misclassified:{plan.intent}",
        )
        plan = synthesize_health_plan(fallback_intent)

    truth = retrieve_truth(user, plan)
    working_memory = build_working_memory(plan, truth, user)
    answer, used_fallback = run_reasoning(user, message, plan, working_memory)

    return {
        "answer": answer,
        "empty_reason": None,
        "tools_advertised": [],
        "tools_called": ["reasoning_planner"],
        "fast_path": "reasoning",
        "reasoning": {
            "intent": plan.intent,
            "response_mode": plan.response_mode,
            "confidence": plan.confidence,
            "truth_keys": list((working_memory.get("facts") or {}).keys()),
            "used_fallback": used_fallback,
        },
    }
