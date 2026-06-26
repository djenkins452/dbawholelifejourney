# ==============================================================================
# File: apps/ai/chatgpt_cos/reasoning/plan.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reasoning Lane — the structured Retrieval Plan + constrained vocab
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
Retrieval Plan — the Planner LLM's only output.

The planner UNDERSTANDS the request and emits a structured plan that names which
deterministic truth to retrieve. It never answers the user and never invents
truth. The vocabulary below is a closed set: anything the planner emits outside
it is dropped during parsing (the planner cannot fabricate truth sources).
"""

import json
import re
from dataclasses import dataclass, field

# Implemented reasoning intents (this milestone). The planner may also return
# "other" for anything not yet built — the engine then declines (falls through).
# All are HEALTH-scoped intents (see HEALTH_INTENTS in stages.py) and are
# intentionally differentiated per docs/BETH_HEALTH_INTENT_CONTRACTS.md.
IMPLEMENTED_INTENTS = ("biggest_health_risk", "overall_progress",
                       "health_focus_today", "health_concerns")
ALLOWED_INTENTS = IMPLEMENTED_INTENTS + ("other",)

ALLOWED_RESPONSE_MODES = ("lookup", "reasoning", "mixed")
ALLOWED_URGENCY = ("low", "normal", "high")

# Closed vocabulary of truth sources the retrieval layer knows how to fetch.
ALLOWED_DOMAINS = (
    "health", "fitness", "nutrition", "goals", "faith", "tasks", "execution",
)
ALLOWED_TRUTH = (
    "risk_decision", "execution_decision", "fix_decision",
    "standing_context", "foundational_health",
    "health_state", "goals_state", "fitness_state", "nutrition_state",
)


@dataclass
class RetrievalPlan:
    intent: str
    response_mode: str
    domains: list
    required_truth: list
    optional_truth: list
    reasoning_style: str
    urgency: str
    confidence: float
    raw: dict = field(default_factory=dict)

    def as_dict(self):
        return {
            "intent": self.intent,
            "response_mode": self.response_mode,
            "domains": self.domains,
            "required_truth": self.required_truth,
            "optional_truth": self.optional_truth,
            "reasoning_style": self.reasoning_style,
            "urgency": self.urgency,
            "confidence": self.confidence,
        }


# ---------------------------------------------------------------------------
# Resilience matcher (NOT the primary path): when the LLM planner is
# unavailable or misclassifies, route an implemented HEALTH reasoning question
# deterministically so the reasoning lane ALWAYS produces an answer and never
# falls through to the legacy tool loop. The LLM planner remains primary.
# ---------------------------------------------------------------------------
# Ordered MOST-SPECIFIC first — the matcher returns the first intent whose
# signals hit, so time/action cues and plural-survey cues are checked before the
# singular-superlative risk cues (which would otherwise swallow them). See
# docs/BETH_HEALTH_INTENT_CONTRACTS.md "Disambiguation".
_HEALTH_INTENT_SIGNALS = (
    # 1. Today / actionable → health_focus_today (time-bound action).
    ("health_focus_today", ("today", "right now what should i do",
                            "what to do first", "focus today", "do first today")),
    # 2. Plural survey → health_concerns (a ranked LIST, not a single priority).
    ("health_concerns", ("health concerns", "my concerns", "any concerns",
                         "concerns do i", "health issues", "what issues",
                         "what's off", "whats off", "list my health",
                         "anything wrong with my health")),
    # 3. Superlative single risk → biggest_health_risk (the ONE top priority).
    ("biggest_health_risk", ("biggest health risk", "biggest risk", "health risk",
                             "single biggest", "most important health",
                             "what's wrong", "whats wrong", "should i worry",
                             "worried about my health", "what needs attention",
                             "what to improve", "what should i focus on")),
    # 4. Progress / status → overall_progress (executive summary / trajectory).
    ("overall_progress", ("how am i doing", "how am i tracking", "overall",
                          "on track", "progress", "health goals",
                          "doing with my health")),
)


def deterministic_health_intent(message):
    """Best-effort deterministic match to an IMPLEMENTED health intent, or None."""
    text = (message or "").lower()
    for intent, sigs in _HEALTH_INTENT_SIGNALS:
        if intent in IMPLEMENTED_INTENTS and any(s in text for s in sigs):
            return intent
    return None


def synthesize_health_plan(intent):
    """A health-scoped RetrievalPlan for the resilience path."""
    return RetrievalPlan(
        intent=intent, response_mode="reasoning", domains=["health"],
        required_truth=["health_state", "foundational_health"],
        optional_truth=[], reasoning_style="resilience_fallback",
        urgency="normal", confidence=0.0,
        raw={"source": "deterministic_fallback"},
    )


def _coerce_list(value, allowed):
    if not isinstance(value, list):
        return []
    # keep only known vocabulary — the planner cannot invent truth sources
    return [v for v in value if isinstance(v, str) and v in allowed]


def parse_plan(text):
    """Parse the planner's text into a validated RetrievalPlan, or None.

    Tolerant of code fences / prose around the JSON. Unknown intents/domains/
    truth keys are normalized or dropped — never trusted blindly."""
    if not text:
        return None
    raw = None
    # Strip code fences and grab the first {...} block.
    cleaned = re.sub(r"```(?:json)?", "", str(text)).strip()
    try:
        raw = json.loads(cleaned)
    except Exception:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not m:
            return None
        try:
            raw = json.loads(m.group(0))
        except Exception:
            return None
    if not isinstance(raw, dict):
        return None

    intent = raw.get("intent")
    if intent not in ALLOWED_INTENTS:
        intent = "other"
    mode = raw.get("response_mode")
    if mode not in ALLOWED_RESPONSE_MODES:
        mode = "reasoning"
    urgency = raw.get("urgency")
    if urgency not in ALLOWED_URGENCY:
        urgency = "normal"
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return RetrievalPlan(
        intent=intent,
        response_mode=mode,
        domains=_coerce_list(raw.get("domains"), ALLOWED_DOMAINS),
        required_truth=_coerce_list(raw.get("required_truth"), ALLOWED_TRUTH),
        optional_truth=_coerce_list(raw.get("optional_truth"), ALLOWED_TRUTH),
        reasoning_style=str(raw.get("reasoning_style") or "")[:64],
        urgency=urgency,
        confidence=max(0.0, min(1.0, confidence)),
        raw=raw if isinstance(raw, dict) else {},
    )
