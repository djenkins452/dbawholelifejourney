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
# Two domains are implemented: HEALTH (reference) and GOALS (domain #2). Each
# quartet is intentionally differentiated per the intent contracts.
HEALTH_IMPLEMENTED = ("biggest_health_risk", "overall_progress",
                      "health_focus_today", "health_concerns")
GOAL_IMPLEMENTED = ("biggest_goal_risk", "goals_progress",
                    "goals_focus_today", "goal_concerns")
IMPLEMENTED_INTENTS = HEALTH_IMPLEMENTED + GOAL_IMPLEMENTED
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
    "health_state", "goals_state", "habits_state",
    "fitness_state", "nutrition_state",
)

# Single source of truth for intent -> (domain, required truth keys). Both the
# resilience planner (synthesize_plan) and the per-intent truth SCOPE in
# stages.py derive from this, so a new domain is registered in ONE place.
_HEALTH_REQUIRED = ("health_state", "foundational_health")
_GOALS_REQUIRED = ("goals_state", "habits_state")
INTENT_DOMAINS = {
    "biggest_health_risk": ("health", _HEALTH_REQUIRED),
    "overall_progress": ("health", _HEALTH_REQUIRED),
    "health_focus_today": ("health", _HEALTH_REQUIRED),
    "health_concerns": ("health", _HEALTH_REQUIRED),
    "biggest_goal_risk": ("goals", _GOALS_REQUIRED),
    "goals_progress": ("goals", _GOALS_REQUIRED),
    "goals_focus_today": ("goals", _GOALS_REQUIRED),
    "goal_concerns": ("goals", _GOALS_REQUIRED),
}


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


# Goal intent signals — goal-SPECIFIC cues only (every signal contains "goal"),
# so they never match a health-only message (health routing stays byte-identical)
# and a "health goals" phrase still routes to health (there is no bare "goals"
# signal). Ordered MOST-SPECIFIC first within the domain, mirroring health.
_GOAL_INTENT_SIGNALS = (
    # 1. Today / actionable → goals_focus_today (time-bound goal action).
    ("goals_focus_today", ("goal today", "goal to focus on", "which goal should i",
                           "what goal should i", "goal for today", "which goal today",
                           "goal to work on today", "advance a goal")),
    # 2. Plural survey → goal_concerns (a ranked LIST of slipping goals/habits).
    ("goal_concerns", ("goal concerns", "goals at risk", "goals am i behind",
                       "behind on my goals", "goals are slipping", "stalled goals",
                       "goals stalling", "which goals are", "what goals are wrong",
                       "problems with my goals")),
    # 3. Superlative single risk → biggest_goal_risk (the ONE goal most at risk).
    ("biggest_goal_risk", ("biggest goal risk", "biggest goal", "goal at risk",
                           "goal most at risk", "most important goal",
                           "which goal is at risk", "top goal risk",
                           "what goal needs")),
    # 4. Progress / status → goals_progress (executive summary / trajectory).
    ("goals_progress", ("how am i doing on my goals", "on my goals",
                        "with my goals", "my goals progress", "goal progress",
                        "goals progress", "how are my goals", "how's my goals",
                        "hows my goals", "tracking on my goals",
                        "on track with my goals", "doing on my goals",
                        "doing with my goals", "am i on track with my goals")),
)

# Goal signals are checked BEFORE health signals so a goal-specific phrase wins
# over a generic health cue (e.g. "how am I doing on my goals" → goals_progress,
# not overall_progress). Health-only messages match no goal signal, so existing
# health routing is unchanged.
_DOMAIN_INTENT_SIGNALS = _GOAL_INTENT_SIGNALS + _HEALTH_INTENT_SIGNALS


def deterministic_intent(message):
    """Best-effort deterministic match to an IMPLEMENTED intent, or None.

    Multi-domain (health + goals); goal-specific cues are checked first. The LLM
    planner remains primary — this is the resilience path."""
    text = (message or "").lower()
    for intent, sigs in _DOMAIN_INTENT_SIGNALS:
        if intent in IMPLEMENTED_INTENTS and any(s in text for s in sigs):
            return intent
    return None


# Backward-compatible alias (generalize-with-alias): existing callers/tests using
# the health-named function keep working; it now matches goal intents too.
deterministic_health_intent = deterministic_intent


def synthesize_plan(intent):
    """A domain-scoped RetrievalPlan for the resilience path, scoped by intent.

    Health intents map to the same domain + required_truth as before, so health
    behavior is byte-identical; goal intents map to goals truth."""
    domain, required = INTENT_DOMAINS.get(intent, ("health", _HEALTH_REQUIRED))
    return RetrievalPlan(
        intent=intent, response_mode="reasoning", domains=[domain],
        required_truth=list(required),
        optional_truth=[], reasoning_style="resilience_fallback",
        urgency="normal", confidence=0.0,
        raw={"source": "deterministic_fallback"},
    )


# Backward-compatible alias.
synthesize_health_plan = synthesize_plan


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
