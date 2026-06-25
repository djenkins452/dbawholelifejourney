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

from apps.ai.chatgpt_cos.reasoning.plan import IMPLEMENTED_INTENTS
from apps.ai.chatgpt_cos.reasoning.stages import (
    build_working_memory,
    retrieve_truth,
    run_planner,
    run_reasoning,
)

logger = logging.getLogger(__name__)


def answer_reasoning_question(user, message):
    """Run the Reasoning Lane. Returns a result dict, or None to fall through."""
    plan = run_planner(user, message)
    if plan is None:
        return None
    if plan.intent not in IMPLEMENTED_INTENTS:
        logger.info("COS_REASONING_DECLINE user=%s intent=%s",
                    getattr(user, "id", None), plan.intent)
        return None

    truth = retrieve_truth(user, plan)
    working_memory = build_working_memory(plan, truth)
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
