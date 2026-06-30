# ==============================================================================
# File: apps/ai/chatgpt_cos/reasoning/__init__.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reasoning Lane — Planner -> Retrieval -> Working Memory -> Reasoning
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
Reasoning Lane (milestone: framework + 2 intents — biggest_risk, overall_progress).

WLJ owns truth (deterministic retrieval); ChatGPT owns reasoning (one plain
_call_api over curated working memory). No agentic tool loop. Reasoning intents
are never keyword-classified — a small constrained Planner LLM produces a
structured Retrieval Plan.
"""

from apps.ai.chatgpt_cos.reasoning.engine import answer_reasoning_question
from apps.ai.chatgpt_cos.reasoning.plan import (
    IMPLEMENTED_INTENTS,
    RetrievalPlan,
    parse_plan,
)
# Layer 2 reusable reasoning engines (deterministic reasoning primitives).
from apps.ai.chatgpt_cos.reasoning.engines import (
    reasoning_confidence,
    confidence_rank,
    assess_risk,
    prioritize,
    explain,
)

__all__ = [
    "answer_reasoning_question",
    "IMPLEMENTED_INTENTS",
    "RetrievalPlan",
    "parse_plan",
    "reasoning_confidence",
    "confidence_rank",
    "assess_risk",
    "prioritize",
    "explain",
]
