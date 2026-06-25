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
IMPLEMENTED_INTENTS = ("biggest_risk", "overall_progress")
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
