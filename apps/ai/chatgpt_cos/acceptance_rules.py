# ==============================================================================
# File: apps/ai/chatgpt_cos/acceptance_rules.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Shared GOLD-STANDARD evaluator + the core validation question spec.
#   Used by the LIVE acceptance harness (management command `beth_acceptance`) and
#   unit-tested by apps/ai/tests/test_acceptance_rules.py. Pure functions — no DB,
#   no OpenAI. Spec: docs/BETH_GOLD_STANDARD_ACCEPTANCE.md
# ==============================================================================
import re

# Generic / system / cheerleading phrases that must never appear in an answer.
BANNED_PHRASES = (
    "take the next step", "take the concrete next step", "take a step",
    "make progress", "work on your goal", "work on the goal", "advance your goal",
    "advance the goal", "take one step", "take your first action", "support your mission",
    "maintain consistency", "maintain momentum", "maintaining consistency",
    "maintaining your consistency", "keep consistency", "keeping your consistency",
    "keep your consistency", "lock in consistency", "lock in momentum",
    "stay consistent", "keep up the momentum", "keep the momentum going",
    "keep progressing", "keep moving forward", "steady momentum", "keep momentum",
    "maintain your momentum", "keep going", "momentum over time",
    "do your best", "stay focused", "you've got this", "keep it up",
    "you're doing fine", "doing great", "you got this", "just keep going",
)

# Strings that signal an empty/fallback OpenAI failure reached the user.
FAILURE_MARKERS = (
    "couldn't reach", "could not reach", "came back empty", "try again",
    "couldn't compose", "something went wrong", "i wasn't able to",
    "reached openai", "response came back empty",
)

_MOMENTUM = ("momentum", "trending", "thriving", "steady", "stalled", "drifting",
             "strong", "rising", "falling", "on pace", "high", "low", "short")
_EVIDENCE = _MOMENTUM + ("phase", "milestone", "workout", "weight", "glucose",
                         "sleep", "protein", "nutrition", "habit", "blood sugar",
                         "streak", "calorie", "%")
_ACTION = ("complete", "log ", "walk", "write", "read ", "journal", "schedule",
           "define", "reschedule", "protein", "workout", "bedtime", "wind down",
           "prepare for tomorrow", "spend ", "milestone", "hit your", "block ",
           "reach out", "lever", "15 ", "20 ", "30 ")

_SYNTH_GROUPS = (
    ("momentum", "trending", "steady", "strong", "stalled", "drifting", "thriving"),
    ("phase", "milestone"),
    ("workout", "weight", "protein", "glucose", "sleep", "nutrition", "habit", "blood sugar"),
    ("risk", "watch", "slip", "light", "drop", "fail", "strength"),
    ("next", "today", "tomorrow", "step", "move", "lever"),
    # meaning/values split into distinct dimensions so genuine rationale (why a
    # goal matters) registers real synthesis, not a single lumped concept.
    ("family", "kids", "relationships", "loved"),
    ("health", "healthy", "values", "finish", "decades", "future", "matters",
     "means", "keep up"),
)


def is_failure_message(text):
    t = (text or "").lower()
    return any(m in t for m in FAILURE_MARKERS)


def has_evidence(text):
    t = (text or "").lower()
    return bool(re.search(r"\d", text or "")) or any(w in t for w in _EVIDENCE)


def is_actionable(text):
    t = (text or "").lower()
    return any(c in t for c in _ACTION)


def banned_hits(text):
    t = (text or "").lower()
    return [b for b in BANNED_PHRASES if b in t]


def synthesis_dims(text):
    t = (text or "").lower()
    return sum(1 for g in _SYNTH_GROUPS if any(w in t for w in g))


# Domain → the set of intents that legitimately answer it.
GOAL_INTENTS = ("biggest_goal_risk", "goals_progress", "goals_focus_today",
                "goal_concerns", "goal_on_track", "goal_why_priority",
                "goal_next_milestone", "goal_failure_modes", "goal_confidence")
HEALTH_INTENTS = ("biggest_health_risk", "overall_progress", "health_focus_today",
                  "health_concerns")


# ---------------------------------------------------------------------------
# The core validation questions (the live harness runs these in order).
#   gates: which of evidence/synthesis/actionable to enforce.
#   expect_intent: exact reasoning intent (when deterministic).
#   domain: routing family — goals/health/general/rhythm/clarification/agenda.
# ---------------------------------------------------------------------------
QUESTIONS = [
    # ---- Daily check-in (two turns; the agenda turn is evening-sensitive) ----
    {"key": "checkin", "text": "check in", "domain": "clarification",
     "required": [], "forbidden": [], "gates": []},
    {"key": "checkin_agenda", "text": "1", "domain": "agenda", "evening": True,
     "required_any": ["wind down", "winding down", "journal", "sleep",
                      "prepare for tomorrow", "tomorrow's first priority", "rest up"],
     "forbidden": ["begin workout", "next up: workout", "best next step is to begin"],
     "gates": []},

    # ---- Goals (named France mission) ----
    {"key": "goal_progress", "domain": "goals", "expect_intent": "goals_progress",
     "text": "How is my France 2027 Family 18K Mission progressing?",
     "required": ["France 2027"], "gates": ["evidence", "synthesis", "actionable"]},
    {"key": "goal_on_track", "domain": "goals", "expect_intent": "goal_on_track",
     "text": "Am I still on track for my France 2027 Family 18K Mission?",
     "required": ["France 2027"], "required_any": ["on track", "on pace", "yes", "no"],
     "gates": ["evidence", "actionable"]},
    {"key": "goal_why", "domain": "goals", "expect_intent": "goal_why_priority",
     "text": "Why is the France 2027 Family 18K Mission my highest priority goal?",
     "required": [], "forbidden": ["active goal count", "completion %", "next deadline"],
     "gates": ["synthesis"]},
    {"key": "goal_milestone", "domain": "goals", "expect_intent": "goal_next_milestone",
     "text": "What is the next milestone for my France 2027 Family 18K Mission?",
     "required_any": ["milestone", "phase"], "gates": []},
    {"key": "goal_failure", "domain": "goals", "expect_intent": "goal_failure_modes",
     "text": "What could cause the France 2027 Family 18K Mission to fail?",
     "required_any": ["fail", "risk", "slip"], "gates": ["actionable"]},
    {"key": "goal_confidence", "domain": "goals", "expect_intent": "goal_confidence",
     "text": "How confident are you that I'll achieve the France 2027 Family 18K Mission?",
     "required_any": ["confiden", "likely", "chance"], "gates": ["evidence"]},
    {"key": "goal_focus", "domain": "goals", "expect_intent": "goals_focus_today",
     "text": "What should I focus on for this goal?",
     "required_any": ["today", "next"], "gates": ["actionable"]},
    {"key": "goal_slipping", "domain": "goals", "expect_intent": "goal_concerns",
     "text": "Which goals are slipping?",
     "required_any": ["slipping", "drifting", "stalled", "none"], "gates": []},
    {"key": "goal_risk", "domain": "goals", "expect_intent": "biggest_goal_risk",
     "text": "What's my biggest goal risk right now?",
     "required_any": ["risk", "no significant"], "gates": ["actionable"]},

    # ---- Health ----
    {"key": "health_risk", "domain": "health", "expect_intent": "biggest_health_risk",
     "text": "What's my biggest health risk right now?", "gates": ["actionable"]},
    {"key": "health_overall", "domain": "health", "expect_intent": "overall_progress",
     "text": "How am I doing overall with my health goals?", "gates": ["evidence"]},
    {"key": "health_focus", "domain": "health", "expect_intent": "health_focus_today",
     "text": "What should I focus on from a health perspective today?",
     "required_any": ["today"], "gates": ["actionable"]},

    # ---- Rhythm ----
    {"key": "rhythm_next", "domain": "rhythm", "text": "What should I do next?",
     "forbidden": ["overdue", "past its target"], "gates": []},

    # ---- General knowledge ----
    {"key": "gen_lincoln", "domain": "general", "text": "Who was Abraham Lincoln?",
     "required_any": ["president", "lincoln", "1865", "civil war"], "gates": []},
    {"key": "gen_photo", "domain": "general", "text": "Explain photosynthesis.",
     "required_any": ["light", "plant", "carbon", "chlorophyll", "energy"], "gates": []},
    {"key": "gen_delphi", "domain": "general", "text": "What is Delphi?",
     "required_any": ["oracle", "greece", "greek", "apollo", "temple"], "gates": []},
]


def _domain_ok(spec, intent, lane):
    domain = spec.get("domain")
    if domain == "goals":
        if intent and intent not in GOAL_INTENTS:
            return False
        if intent and spec.get("expect_intent") and intent != spec["expect_intent"]:
            return False
        return True
    if domain == "health":
        return intent is None or intent in HEALTH_INTENTS
    if domain == "general":
        return (lane in (None, "general_conversation")) and intent is None
    if domain == "rhythm":
        return lane in (None, "next_rhythm")
    return True


def evaluate(spec, text, intent=None, lane=None):
    """Return a list of FAILED rule names ([] == PASS) for a single response."""
    fails = []
    t = (text or "").strip()
    if not t:
        return ["empty"]
    if is_failure_message(t):
        fails.append("openai_failure_message")

    # Routing.
    if not _domain_ok(spec, intent, lane):
        fails.append(f"wrong_domain(intent={intent},lane={lane})")

    # Banned phrases.
    bh = banned_hits(t)
    if bh:
        fails.append(f"banned_phrase:{bh[0]}")

    # Required (all) + required_any (at least one).
    for r in spec.get("required", []):
        if r.lower() not in t.lower():
            fails.append(f"missing_required:{r}")
    any_set = spec.get("required_any")
    if any_set and not any(r.lower() in t.lower() for r in any_set):
        fails.append("missing_required_any:" + "|".join(any_set))

    # Forbidden.
    for f in spec.get("forbidden", []):
        if f.lower() in t.lower():
            fails.append(f"forbidden:{f}")

    # Quality gates.
    gates = spec.get("gates", [])
    if "evidence" in gates and not has_evidence(t):
        fails.append("gate_evidence")
    if "synthesis" in gates and synthesis_dims(t) < 2:
        fails.append("gate_synthesis")
    if "actionable" in gates and not is_actionable(t):
        fails.append("gate_actionable")

    return fails


# Suite categorisation — derived from each question's domain.
SUITES = ("full", "goals", "health", "checkin", "general", "rhythm")
_DOMAIN_TO_SUITE = {"goals": "goals", "health": "health", "general": "general",
                    "rhythm": "rhythm", "clarification": "checkin", "agenda": "checkin"}


def suite_of(spec):
    return _DOMAIN_TO_SUITE.get(spec.get("domain"), "full")


def questions_for(suite):
    """Return the question specs for a suite ('full' = all)."""
    if suite in (None, "full"):
        return list(QUESTIONS)
    return [q for q in QUESTIONS if suite_of(q) == suite]
