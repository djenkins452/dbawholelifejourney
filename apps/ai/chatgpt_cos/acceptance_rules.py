# ==============================================================================
# File: apps/ai/chatgpt_cos/acceptance_rules.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Shared GOLD-STANDARD evaluator + the structured validation QUESTION
#   BANK. Used by the live harness (mgmt command `beth_acceptance`) and the Admin
#   Console Beth Acceptance Center. Pure functions — no DB, no OpenAI.
#   Each question carries metadata: key, suite, depth, text, expect_intent,
#   expect_lane, required, required_any, forbidden, banned (extra), gates,
#   distinct_group, criticality, notes. Spec: docs/BETH_GOLD_STANDARD_ACCEPTANCE.md
# ==============================================================================
import re

# ---------------------------------------------------------------------------
# Banned phrase CATEGORIES (a hit in any => fail). Applied to every answer.
# ---------------------------------------------------------------------------
COACHING_BANNED = (
    "maintain momentum", "maintain consistency", "maintaining consistency",
    "maintaining your momentum", "lock in consistency", "lock in momentum",
    "stay consistent", "keep moving forward", "keep progressing", "keep momentum",
    "keep up the momentum", "keep the momentum going", "steady momentum",
    "momentum over time", "make progress", "take the next step",
    "take the concrete next step", "take one step", "take a step",
    "work on your goal", "work on the goal", "advance your goal", "advance the goal",
    "take your first action", "support your mission", "do your best", "keep it up",
    "keep going", "stay focused", "you've got this", "you got this",
    "just keep going", "you're doing fine", "doing great",
)
SYSTEM_BANNED = (
    "source of truth", "state builder", "momentum score", "confidence score",
    "signal health", "sae state", "is_foundational", "frequency_type",
    "canonical truth", "raw score", "enum value",
)
DEFLECTION_BANNED = (
    "check your dashboard", "go to the goals page", "go to the goal page",
    "open the app", "ask me again", "visit the goals", "see your dashboard",
    "look at your dashboard", "in the app", "navigate to",
)
BANNED_PHRASES = COACHING_BANNED + SYSTEM_BANNED + DEFLECTION_BANNED

_BANNED_CATEGORY = {}
for _p in COACHING_BANNED:
    _BANNED_CATEGORY[_p] = "coaching"
for _p in SYSTEM_BANNED:
    _BANNED_CATEGORY[_p] = "system_language"
for _p in DEFLECTION_BANNED:
    _BANNED_CATEGORY[_p] = "deflection"

FAILURE_MARKERS = (
    "couldn't reach", "could not reach", "came back empty", "try again",
    "couldn't compose", "something went wrong", "i wasn't able to",
    "reached openai", "response came back empty",
)

_MOMENTUM = ("momentum", "trending", "thriving", "steady", "stalled", "drifting",
             "strong", "rising", "falling", "on pace", "ahead", "behind", "high",
             "low", "short")
_EVIDENCE = _MOMENTUM + ("phase", "milestone", "workout", "weight", "glucose",
                         "sleep", "protein", "nutrition", "habit", "blood sugar",
                         "streak", "calorie", "%", "pace")
_ACTION = ("complete", "log ", "walk", "write", "read ", "journal", "schedule",
           "define", "reschedule", "protein", "workout", "bedtime", "wind down",
           "prepare for tomorrow", "spend ", "milestone", "hit your", "block ",
           "reach out", "lever", "meal", "15 ", "20 ", "30 ")
_SYNTH_GROUPS = (
    ("momentum", "trending", "steady", "strong", "stalled", "drifting", "thriving",
     "pace"),
    ("phase", "milestone"),
    ("workout", "weight", "protein", "glucose", "sleep", "nutrition", "habit",
     "blood sugar"),
    ("risk", "watch", "slip", "light", "drop", "fail", "strength"),
    ("next", "today", "tomorrow", "step", "move", "lever"),
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


def banned_hits(text, extra=()):
    t = (text or "").lower()
    return [b for b in (BANNED_PHRASES + tuple(extra)) if b in t]


def banned_category(phrase):
    return _BANNED_CATEGORY.get(phrase, "coaching")


def synthesis_dims(text):
    t = (text or "").lower()
    return sum(1 for g in _SYNTH_GROUPS if any(w in t for w in g))


GOAL_INTENTS = ("biggest_goal_risk", "goals_progress", "goals_focus_today",
                "goal_concerns", "goal_on_track", "goal_why_priority",
                "goal_next_milestone", "goal_failure_modes", "goal_confidence")
HEALTH_INTENTS = ("biggest_health_risk", "overall_progress", "health_focus_today",
                  "health_concerns")

SUITES = ("full", "goals", "health", "checkin", "general", "rhythm", "boundary")
DEPTHS = ("smoke", "full", "deep")
_DEPTH_RANK = {"smoke": 0, "full": 1, "deep": 2}

# Failed-rule -> human category (for the failure summary).
_RULE_CATEGORY = [
    ("empty", "empty_response"),
    ("exception", "empty_response"),
    ("openai_failure_message", "general_failure"),
    ("wrong_domain", "wrong_domain"),
    ("banned_phrase", "banned_phrase"),
    ("missing_required", "missing_required"),
    ("forbidden", "forbidden_concept"),
    ("duplicate_answer", "duplicate_answer"),
    ("gate_evidence", "response_quality"),
    ("gate_synthesis", "response_quality"),
    ("gate_actionable", "response_quality"),
    ("too_short", "response_quality"),
    ("checkin", "checkin_time_awareness"),
    ("slow_response", "slow_response"),
]

# Rules that make a question a CRITICAL (release-blocking) failure.
CRITICAL_RULES = ("empty", "exception", "openai_failure_message", "wrong_domain",
                  "duplicate_answer")
CRITICAL_BANNED_CATEGORIES = ("system_language", "deflection")


def categorize_rule(rule):
    for prefix, cat in _RULE_CATEGORY:
        if rule.startswith(prefix):
            return cat
    return "response_quality"


def is_critical_rule(rule, spec=None):
    for c in CRITICAL_RULES:
        if rule.startswith(c):
            return True
    if rule.startswith("banned_phrase:"):
        phrase = rule.split(":", 1)[1]
        if banned_category(phrase) in CRITICAL_BANNED_CATEGORIES:
            return True
    # check-in time-awareness (forbidden morning item at night) is critical
    if rule.startswith("forbidden") and spec and spec.get("domain") in ("agenda", "checkin"):
        return True
    # healthy goals listed as slipping
    if rule.startswith("missing_required") and spec and spec.get("key", "").startswith("goal_slip"):
        return True
    return False


# ---------------------------------------------------------------------------
# Question bank
# ---------------------------------------------------------------------------
MISSION = "France 2027 Family 18K Mission"


def _q(key, text, domain, depth="full", **kw):
    d = {"key": key, "text": text, "domain": domain, "depth": depth,
         "required": kw.get("required", []), "required_any": kw.get("required_any", []),
         "forbidden": kw.get("forbidden", []), "banned": kw.get("banned", []),
         "gates": kw.get("gates", []), "expect_intent": kw.get("expect_intent", ""),
         "expect_lane": kw.get("expect_lane", ""),
         "distinct_group": kw.get("distinct_group", ""),
         "criticality": kw.get("criticality", "normal"),
         "min_len": kw.get("min_len", 0), "notes": kw.get("notes", "")}
    return d


def _goal_paraphrases():
    out = []
    # (intent, gates, required_any, distinct_group sharing the France goal)
    specs = [
        ("goals_progress", ["evidence", "synthesis", "actionable"], [],
         ["How is my France 2027 Family 18K Mission progressing?",
          "How is my mission going?", "How is this goal doing?",
          "Give me a progress update on my France goal.",
          "What's the current status of my France mission?"]),
        ("goal_on_track", ["evidence", "actionable"], ["on track", "on pace", "yes", "no", "behind", "adjust"],
         ["Am I still on track for my France 2027 Family 18K Mission?",
          "Am I behind on this goal?", "Do I need to adjust the timeline?",
          "Are we still okay for France 2027?"]),
        ("goal_why_priority", ["synthesis"], [],
         ["Why is this my highest priority goal?", "Why does this goal matter so much?",
          "Why is France 2027 important to me?",
          "Why should I keep focusing on this mission?"]),
        ("goal_next_milestone", [], ["milestone", "phase"],
         ["What is my next milestone?", "What milestone am I working on now?",
          "What's after Goal Weight 284.9?", "What comes next in this mission?"]),
        ("goal_failure_modes", ["actionable"], ["fail", "risk", "slip", "threat", "derail", "watch"],
         ["What could cause this goal to fail?", "What could derail this mission?",
          "What should I watch out for?", "What is the biggest threat to this goal?"]),
        ("goal_confidence", ["evidence"], ["confiden", "likely", "odds", "ready", "chance", "success"],
         ["How confident are you that I'll achieve this?", "What are my odds of making it?",
          "Do you think I'll be ready?", "How likely is success?"]),
        ("goals_focus_today", ["actionable"], ["today", "next"],
         ["What should I focus on for this goal?", "What should I do today for France?",
          "What's the highest leverage action today?",
          "What is the one thing I should do today to move this forward?"]),
        ("goal_concerns", [], ["slipping", "drifting", "stalled", "none", "attention", "at risk"],
         ["Which goals are slipping?", "Which goals are drifting?",
          "Which goals need attention?", "Are any goals at risk?"]),
        ("biggest_goal_risk", ["actionable"], ["risk", "no significant", "worries", "attention"],
         ["What's my biggest goal risk right now?", "Which goal worries you most?",
          "What goal needs the most attention?"]),
    ]
    for intent, gates, req_any, texts in specs:
        for i, t in enumerate(texts):
            depth = "smoke" if (intent == "goals_progress" and i == 0) else (
                "full" if i == 0 else "deep")
            out.append(_q(f"{intent}__{i}", t, "goals", depth, expect_intent=intent,
                          gates=gates, required_any=req_any, distinct_group="france_goal",
                          forbidden=(["active goal count", "completion %", "next deadline"]
                                     if intent == "goal_why_priority" else [])))
    return out


def _health_questions():
    out = []
    sets = [
        ("biggest_health_risk", ["actionable"], [],
         ["What's my biggest health risk right now?",
          "What health issue concerns you most?",
          "What is the main health problem I should focus on?"]),
        ("overall_progress", ["evidence"], [],
         ["How am I doing overall with my health goals?",
          "Am I making progress with my health?", "Give me a health summary."]),
        ("health_focus_today", ["actionable"], ["today"],
         ["What should I focus on from a health perspective today?",
          "What is one health action I should take today?",
          "What should I do today for my health?"]),
    ]
    for intent, gates, req_any, texts in sets:
        for i, t in enumerate(texts):
            depth = "smoke" if (intent == "biggest_health_risk" and i == 0) else (
                "full" if i == 0 else "deep")
            out.append(_q(f"{intent}__{i}", t, "health", depth, expect_intent=intent,
                          gates=gates, required_any=req_any, distinct_group="health"))
    return out


def _checkin_questions():
    out = [
        _q("checkin", "check in", "clarification", "smoke"),
        _q("checkin_agenda", "1", "agenda", "smoke", evening=True,
           required_any=["wind down", "winding down", "journal", "sleep",
                         "prepare for tomorrow", "tomorrow's first priority", "rest up"],
           forbidden=["begin workout", "next up: workout", "best next step is to begin"]),
    ]
    out[-1]["evening"] = True
    for k, t in [("checkin_daily", "daily check-in"), ("checkin_full", "full check-in"),
                 ("checkin_know", "what should I know today?"),
                 ("checkin_attention", "what needs my attention?"),
                 ("checkin_plan", "help me plan the rest of the day"),
                 ("checkin_wrap", "wrap up my day")]:
        out.append(_q(k, t, "clarification", "deep"))
    return out


def _general_questions():
    bank = [
        ("gen_lincoln", "Who was Abraham Lincoln?", ["president", "lincoln", "1865", "civil war"], "smoke"),
        ("gen_photo", "Explain photosynthesis.", ["light", "plant", "carbon", "chlorophyll", "energy"], "full"),
        ("gen_delphi", "What is Delphi?", ["oracle", "greece", "greek", "apollo", "temple"], "full"),
        ("gen_cte", "What is a CTE in SQL?", ["common table", "with", "query", "subquery", "temporary"], "deep"),
        ("gen_weather", "Explain the difference between weather and climate.", ["weather", "climate", "long", "short", "atmosphere"], "deep"),
        ("gen_hamlet", "Who wrote Hamlet?", ["shakespeare"], "deep"),
        ("gen_interest", "What is compound interest?", ["interest", "principal", "compound", "earn"], "deep"),
        ("gen_rest", "What is a REST API?", ["http", "rest", "api", "endpoint", "stateless", "resource"], "deep"),
    ]
    return [_q(k, t, "general", depth, required_any=ra,
               forbidden=["your weight", "your goal", "your health", "your mission"])
            for k, t, ra, depth in bank]


def _boundary_questions():
    return [
        _q("bnd_my_weight", "What is my current weight?", "personal", "full",
           notes="personal/foundational — must not route to general"),
        _q("bnd_healthy_weight", "What is a healthy weight generally?", "general", "deep",
           forbidden=["your weight", "your current weight"]),
        _q("bnd_my_health", "How is my health?", "health", "full"),
        _q("bnd_diabetes", "What is diabetes?", "general", "deep",
           required_any=["blood sugar", "insulin", "glucose", "condition"]),
        _q("bnd_my_diabetes", "How is my diabetes doing?", "health", "deep"),
        _q("bnd_my_milestone", "What is my next milestone?", "goals", "full",
           expect_intent="goal_next_milestone"),
        _q("bnd_pm_milestone", "What is a milestone in project management?", "general", "deep",
           required_any=["project", "checkpoint", "deliverable", "phase"],
           forbidden=["your mission", "France"]),
        # Ambiguous — Beth should clarify, not confidently guess (lenient checks).
        _q("amb_help", "help me", "clarification", "deep"),
        _q("amb_review", "review this", "clarification", "deep"),
        _q("amb_focus", "what should I focus on?", "clarification", "deep"),
        _q("amb_risk", "what is my biggest risk?", "clarification", "deep"),
        _q("amb_howdoing", "how am I doing?", "clarification", "deep"),
    ]


def _rhythm_questions():
    return [
        _q("rhythm_next", "What should I do next?", "rhythm", "smoke",
           forbidden=["overdue", "past its target"]),
    ]


QUESTIONS = (_checkin_questions() + _goal_paraphrases() + _health_questions()
             + _rhythm_questions() + _general_questions() + _boundary_questions())


_DOMAIN_TO_SUITE = {"goals": "goals", "health": "health", "general": "general",
                    "rhythm": "rhythm", "clarification": "checkin", "agenda": "checkin",
                    "personal": "boundary"}


def suite_of(spec):
    if spec.get("key", "").startswith(("bnd_", "amb_")):
        return "boundary"
    return _DOMAIN_TO_SUITE.get(spec.get("domain"), "full")


def questions_for(suite=None, depth="full"):
    """Questions for a suite ('full'/None = all suites) at a depth level
    (smoke ⊂ full ⊂ deep)."""
    maxr = _DEPTH_RANK.get(depth, 1)
    out = [q for q in QUESTIONS if _DEPTH_RANK.get(q["depth"], 1) <= maxr]
    if suite not in (None, "full"):
        out = [q for q in out if suite_of(q) == suite]
    return out


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
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
    if domain == "personal":
        return lane != "general_conversation"      # must not be answered as external
    # clarification / agenda — lenient (any non-empty, non-failure answer)
    return True


def evaluate(spec, text, intent=None, lane=None):
    """Return a list of FAILED rule names ([] == PASS) for a single response."""
    fails = []
    t = (text or "").strip()
    if not t:
        return ["empty"]
    if is_failure_message(t):
        fails.append("openai_failure_message")
    if not _domain_ok(spec, intent, lane):
        fails.append(f"wrong_domain(intent={intent},lane={lane})")
    for b in banned_hits(t, spec.get("banned", [])):
        fails.append(f"banned_phrase:{b}")
    for r in spec.get("required", []):
        if r.lower() not in t.lower():
            fails.append(f"missing_required:{r}")
    any_set = spec.get("required_any")
    if any_set and not any(r.lower() in t.lower() for r in any_set):
        fails.append("missing_required_any:" + "|".join(any_set[:6]))
    for f in spec.get("forbidden", []):
        if f.lower() in t.lower():
            cat = "checkin_time" if spec.get("domain") in ("agenda", "checkin") else "concept"
            fails.append(f"forbidden_{cat}:{f}")
    gates = spec.get("gates", [])
    if "evidence" in gates and not has_evidence(t):
        fails.append("gate_evidence")
    if "synthesis" in gates and synthesis_dims(t) < 2:
        fails.append("gate_synthesis")
    if "actionable" in gates and not is_actionable(t):
        fails.append("gate_actionable")
    # length sanity: a synthesis answer that is too short
    if ("synthesis" in gates or "evidence" in gates) and len(t) < max(40, spec.get("min_len", 0)):
        fails.append("too_short")
    return fails


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------
RELEASE_THRESHOLD = 95


def grade(score_percent, critical_count):
    if critical_count > 0:
        return "RED"
    if score_percent >= RELEASE_THRESHOLD:
        return "GREEN"
    if score_percent >= 85:
        return "YELLOW"
    return "RED"


def grade_color(g):
    return {"GREEN": "#10b981", "YELLOW": "#f59e0b", "RED": "#ef4444"}.get(g, "#6b7280")
