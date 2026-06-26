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
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Named-goal PRE-ROUTER (runs BEFORE the planner — see engine.answer_reasoning_
# question). A question that references a named active goal, the mission, or uses
# "my mission"/"this goal"/"that goal" is OWNED by the Goals domain and must never
# be stolen by the health planner (root cause #1). Deterministic, gated on goal
# context + title length so it never captures an unrelated (e.g. health) question.
# ---------------------------------------------------------------------------
# Deictic references to a goal/mission that name no title but clearly point at one.
# Kept narrow on purpose: a bare "my goal" is excluded because phrases like "my
# goal weight" are HEALTH questions — only unambiguous goal/mission deixis qualifies.
_GOAL_DEICTIC = (
    "my mission", "this goal", "that goal", "this mission", "that mission",
    "how is my goal going", "how's my goal going", "hows my goal going",
    "how is my goal progressing", "how's my goal progressing",
)

# Length gate: a matched title must be at least this long to count (a 1–3 char
# title is too generic to safely own a question).
_MIN_TITLE_MATCH_LEN = 4

# A bare single-word title that collides with another domain's vocabulary (a goal
# literally named "Health"/"Sleep"/…) must NOT steal that domain's questions. A
# multi-word title that merely contains such a word still matches as a phrase.
_DOMAIN_COLLISION_WORDS = frozenset({
    "health", "weight", "sleep", "glucose", "fitness", "nutrition", "habits",
    "habit", "faith", "tasks", "task", "finance", "finances", "money",
})


def _infer_named_goal_intent(text):
    """Pick the goal intent for a message ALREADY known to be about a named goal.
    Generic cues (no 'goal' keyword required, since the subject is established)."""
    if any(k in text for k in ("what should i do", "focus on today", "do today",
                               "work on today", "action today", "next step today")):
        return "goals_focus_today"
    if any(k in text for k in ("biggest", "most at risk", "at risk", "worried",
                               "behind on", "in trouble")):
        return "biggest_goal_risk"
    if any(k in text for k in ("concerns", "slipping", "stalling", "stalled",
                               "problems with")):
        return "goal_concerns"
    return "goals_progress"


def named_goal_intent(message, goal_titles, mission_title=None):
    """Deterministic pre-router decision (pure — no DB). Returns a forced GOAL
    intent when the message references a named active goal/mission or uses a goal
    deictic, else None.

    Gates (so it cannot steal unrelated questions):
      - goal-context-gated: returns None unless the user actually has goal titles;
      - title matching is length-gated (>= _MIN_TITLE_MATCH_LEN) and word-boundary
        matched, and a bare domain-collision word title (e.g. "Health") is skipped.
    """
    text = (message or "").lower().strip()
    if not text:
        return None
    titles = [str(t).strip() for t in (goal_titles or []) if t]
    if mission_title:
        titles.append(str(mission_title).strip())
    if not titles:                       # goal-context-gated
        return None

    matched = any(d in text for d in _GOAL_DEICTIC)
    if not matched:
        for t in titles:
            tl = t.lower()
            if len(tl) < _MIN_TITLE_MATCH_LEN:
                continue
            if " " not in tl and tl in _DOMAIN_COLLISION_WORDS:
                continue                 # bare domain word — never steal that domain
            if re.search(r"\b" + re.escape(tl) + r"\b", text):
                matched = True
                break
    if not matched:
        return None
    return _infer_named_goal_intent(text)


def preroute_named_goal(user, message):
    """Pre-router wrapper: read canonical goal/mission titles READ-ONLY (snapshot,
    never recomputed on the request path) and apply named_goal_intent. Returns a
    forced GOAL intent or None. Any read failure degrades safely to None (the
    planner then runs as usual)."""
    if not message:
        return None
    try:
        from apps.ai.cos_services import get_domain_state
        envelope = get_domain_state(user, "purpose")  # allow_build=False (read-only)
    except Exception:
        logger.warning("COS_GOAL_PREROUTE_STATE_FAILED user=%s",
                       getattr(user, "id", None), exc_info=True)
        return None
    state = envelope.get("state") if isinstance(envelope, dict) else None
    state = state if isinstance(state, dict) else {}
    titles = [t.get("title") for t in (state.get("active_titles") or [])
              if isinstance(t, dict) and t.get("title")]
    mission = state.get("mission")
    mission_title = mission.get("title") if isinstance(mission, dict) else None
    return named_goal_intent(message, titles, mission_title)


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
