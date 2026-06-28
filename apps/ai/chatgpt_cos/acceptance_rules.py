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
    "reached openai", "response came back empty", "temporarily unavailable",
)

# goal_failure_modes is a SEMANTIC contract — "clearly communicate failure RISKS" —
# not a narrow lexical whitelist. A correct failure analysis may use "setback",
# "obstacle", "stall", "burnout", "inconsistent", etc. We accept the broad failure-
# risk vocabulary the SYSTEM ITSELF already recognizes (mirrors the input-side set in
# plan._infer_named_goal_intent + the LLM profile's own examples), so semantically-
# correct answers are not rejected for word choice. Still paired with the 'actionable'
# gate + domain check, so a pure PROGRESS answer (no risk language) still fails.
FAILURE_RISK_VOCAB = [
    # explicit risk / failure words
    "fail", "risk", "threat", "derail", "jeopard", "undermin", "danger",
    # trajectory loss
    "slip", "stall", "stagn", "plateau", "fade", "fading", "falter", "drift",
    "lapse", "regress", "backslid", "lose momentum", "losing", "lost momentum",
    "fall behind", "falling behind", "behind",
    # behavioural failure modes
    "setback", "obstacle", "challenge", "hurdle", "barrier", "burnout", "burn out",
    "inconsisten", "abandon", "skip", "miss", "give up", "giving up", "gave up",
    "quit", "off track", "off plan", "drop off", "dropping off",
    # caution framing
    "watch", "go wrong", "fall apart", "what could stop", "what would stop",
]

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

SUITES = ("full", "goals", "health", "checkin", "general", "rhythm", "boundary",
          "factual")
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
    ("gate_value", "missing_value"),
    ("unstable_fact", "unstable_fact"),
    ("too_short", "response_quality"),
    ("checkin", "checkin_time_awareness"),
    ("slow_response", "slow_response"),
]

# Rules that make a question a CRITICAL (release-blocking) failure.
CRITICAL_RULES = ("empty", "exception", "openai_failure_message", "wrong_domain",
                  "duplicate_answer", "unstable_fact")
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
    # ── Factual-trust criticality (Deep suite, 2026-06-28) ──────────────────
    # An unstable fact (Law 5) is always release-blocking. For the factual-trust
    # categories, answering the wrong question (forbidden/missing_required_any on
    # an intent question, Law 0) or failing to cite a value (Law 1/2) blocks too.
    if rule.startswith("unstable_fact"):
        return True
    cat = spec.get("category", "") if spec else ""
    if cat in ("intent", "deterministic", "regression") and \
            rule.startswith(("forbidden", "missing_required_any")):
        return True
    if cat in ("truth", "freshness", "deterministic", "regression") and \
            rule.startswith(("gate_value", "missing_required_any")):
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
         "min_len": kw.get("min_len", 0), "notes": kw.get("notes", ""),
         # Factual-trust taxonomy (Deep suite): intent | truth | freshness |
         # deterministic | stability | regression  ("" = legacy reasoning question).
         "category": kw.get("category", ""),
         # Freshness state declared by the spec. NOTE: no live harness creates this
         # state — `deterministic_only` specs are validated in the deterministic gate
         # (test_daily_health_freshness) + evaluator unit tests, NOT the live run.
         "freshness_expect": kw.get("freshness_expect", ""),
         "deterministic_only": kw.get("deterministic_only", False),
         # Stability questions sharing a group are asked repeatedly; their FACTS
         # (extracted numbers) must be identical across runs (data unchanged).
         "stability_group": kw.get("stability_group", "")}
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
        ("goal_failure_modes", ["actionable"], FAILURE_RISK_VOCAB,
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
          "What is the main health problem I should focus on?",
          "What should I be watching with my health?",
          "Is anything concerning in my health right now?"]),
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
                 ("checkin_wrap", "wrap up my day"),
                 # P29 morning CoS scenario — the real production "Good morning" path.
                 # These MUST answer deterministically (no assistant-unavailable msg).
                 ("morning_greet", "Good morning"),
                 ("morning_greet_beth", "good morning Beth"),
                 ("morning_day", "How is my day looking?"),
                 ("morning_start", "start my day"),
                 ("morning_derail", "What could derail me today?"),
                 ("morning_thirty", "If I only have 30 minutes, what should I do?")]:
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


# ===========================================================================
# FACTUAL-TRUST CATEGORIES (Deep suite — "earn the right to be trusted").
# These prove Beth's deterministic FOUNDATION before any reasoning is graded.
# They enforce Architecture Laws 0/1/2/4/5 (Intent, Freshness, Confidence,
# Deterministic Retrieval, Stable Truth). All are critical (release-blocking).
# Spec: docs/WLJ_ARCHITECTURE_LAWS.md, docs/BETH_GOLD_STANDARD_ACCEPTANCE.md
# ===========================================================================

# Honest "I don't have it (yet)" — the correct answer when data is pending/missing
# (Law 1). A freshness-aware answer either cites a value OR acknowledges absence.
NO_DATA_MARKERS = (
    "don't have", "do not have", "haven't synced", "hasn't synced", "not synced",
    "not yet synced", "hasn't updated", "pending", "no data", "not available",
    "haven't recorded", "nothing recorded", "not yet", "still syncing", "syncing",
    "haven't received", "no sleep data", "no step", "isn't available", "no record",
)


def acknowledges_no_data(text):
    t = (text or "").lower()
    return any(m in t for m in NO_DATA_MARKERS)


def has_number(text):
    return bool(re.search(r"\d", text or ""))


def _facts_of(text):
    """The numeric FACTS in an answer — used to compare stability across runs."""
    return set(re.findall(r"\d+(?:\.\d+)?", text or ""))


def stability_violations(answers):
    """Law 5. `answers` = responses to the SAME question with unchanged source data.
    [] if every answer carries identical numeric facts; else a single critical
    `unstable_fact` violation describing the divergence (e.g. 5.3 vs 6.9)."""
    sets = [_facts_of(a) for a in answers if (a or "").strip()]
    if len(sets) < 2:
        return []
    if all(s == sets[0] for s in sets):
        return []
    rendered = " vs ".join("{" + ",".join(sorted(s)) + "}" for s in sets)
    return [f"unstable_fact:{rendered}"]


def _intent_questions():
    """Law 0 — Beth answers the question ACTUALLY asked. A wrong-domain answer
    (sleep when asked about a workout) is a critical failure."""
    # (key, text, asked-domain terms [required_any], other-domain terms [forbidden])
    specs = [
        ("intent_workout", "Did I workout today?",
         ["workout", "worked out", "exercise", "train", "gym", "no workout",
          "didn't work out", "haven't worked out", "rest day", "not yet"],
         ["slept", "hours of sleep", "your weight", "glucose", "blood sugar"]),
        ("intent_sleep", "How did I sleep last night?",
         ["slept", "sleep", "hours", "rest", "no sleep data", "haven't synced"],
         ["workout", "exercise", "your steps", "your weight", "calories"]),
        ("intent_weight", "What is my weight right now?",
         ["weigh", "lb", "pound", "kg", "weight"],
         ["slept", "sleep", "workout", "glucose", "steps"]),
        ("intent_steps", "How many steps did I get yesterday?",
         ["step", "walk"],
         ["slept", "sleep", "your weight", "workout", "glucose"]),
        ("intent_journal", "Did I journal today?",
         ["journal", "entry", "wrote", "didn't journal", "no journal", "haven't"],
         ["workout", "slept", "sleep", "your weight", "steps"]),
    ]
    return [_q(k, t, "intent", "deep", category="intent", criticality="critical",
               required_any=ra, forbidden=fb) for k, t, ra, fb in specs]


def _truth_questions():
    """Laws 1/2 — a deterministic fact answer must cite a VALUE (or honestly say it
    isn't available); it must never be silent or hand-wave."""
    specs = [
        ("truth_weight", "What is my current weight?"),
        ("truth_glucose", "What was my last glucose reading?"),
        ("truth_calories", "How many calories have I eaten today?"),
        ("truth_sleep", "How many hours did I sleep last night?"),
    ]
    return [_q(k, t, "truth", "deep", category="truth", criticality="critical",
               gates=["value"]) for k, t in specs]


def _freshness_questions():
    """Law 1 — Beth distinguishes current / stale / pending / partial / missing.

    TWO kinds of question:

    1. The per-state MATRIX (current/stale/pending/partial/missing) declares the data
       state each verdict needs. The LIVE harness (acceptance_service.run_one) asks
       against the user's ACTUAL data with NO per-question setup — `freshness_expect`
       is consumed by no harness code — so it cannot create these mutually-exclusive
       states (four ask the IDENTICAL question expecting contradictory answers). They
       are therefore `deterministic_only`: validated with real per-state setup in
       apps/health/tests/test_daily_health_freshness.py (all 5 GREEN) and by the
       evaluator unit tests. They are KEPT in the bank as evaluator fixtures but
       EXCLUDED from the live run (questions_for skips deterministic_only).

    2. The LIVE honesty checks run against whatever the user's real state is: Beth must
       cite the value OR honestly flag absence/staleness — never fabricate or present
       stale-as-current. These the read-only harness CAN run.
    """
    matrix = [
        ("fresh_current", "How many hours did I sleep last night?", "current",
         [], ["value"]),  # fresh data → cite the value
        ("fresh_stale", "How many hours did I sleep last night?", "stale",
         ["as of", "last synced", "earlier", "from", "hasn't updated", "yesterday",
          "older"], []),
        # PENDING is a TODAY-cumulative state (data expected, not yet synced) — it can
        # only arise for a today metric like steps, NOT last-night sleep (a past day,
        # whose no-data resolves to MISSING). See freshness.py:55.
        ("fresh_pending", "How many steps did I get today?", "pending",
         list(NO_DATA_MARKERS), []),
        ("fresh_partial", "How many steps did I get today?", "partial",
         ["partial", "some", "incomplete", "still syncing", "only have", "so far",
          "not all"], []),
        ("fresh_missing", "How many hours did I sleep last night?", "missing",
         list(NO_DATA_MARKERS), []),
    ]
    out = [_q(k, t, "freshness", "deep", category="freshness", criticality="critical",
              freshness_expect=fx, required_any=ra, gates=g, deterministic_only=True)
           for k, t, fx, ra, g in matrix]

    honest = (list(NO_DATA_MARKERS)
              + ["as of", "from", "earlier", "older", "so far", "partial"])
    out += [
        _q("fresh_sleep_honest", "How many hours did I sleep last night?", "freshness",
           "deep", category="freshness", criticality="critical",
           required_any=["slept", "hours", "hour"] + honest,
           notes="LIVE freshness honesty: cite the value OR honest absence/staleness"),
        _q("fresh_steps_honest", "How many steps did I get today?", "freshness",
           "deep", category="freshness", criticality="critical",
           required_any=["steps", "step"] + honest,
           notes="LIVE freshness honesty: cite value (maybe 'so far') OR honest absence"),
    ]
    return out


def _deterministic_retrieval_questions():
    """Law 4 — a question WLJ can answer deterministically must NEVER return the
    'assistant unavailable' / OpenAI-failure message. Covers the canonical domains."""
    specs = [
        ("det_weight", "What is my current weight?", ["value"], []),
        ("det_sleep", "How many hours did I sleep last night?", ["value"], []),
        ("det_steps", "How many steps did I get yesterday?", ["value"], []),
        ("det_calories", "How many calories did I eat yesterday?", ["value"], []),
        ("det_journal", "Did I write a journal entry today?", [],
         ["journal", "entry", "wrote", "didn't", "no journal", "haven't"]),
        ("det_workouts", "Did I work out yesterday?", [],
         ["workout", "worked out", "didn't", "no workout", "rest"]),
        ("det_meds", "What medications do I take?", [],
         ["medication", "medicine", "none", "you take", "take"]),
        ("det_appts", "Do I have any appointments today?", [],
         ["appointment", "calendar", "none", "no appointment", "scheduled"]),
    ]
    return [_q(k, t, "deterministic", "deep", category="deterministic",
               criticality="critical", gates=g, required_any=ra)
            for k, t, g, ra in specs]


def _stability_questions():
    """Law 5 — identical question + unchanged data ⇒ identical facts. The harness
    asks each twice and calls stability_violations() on the pair."""
    specs = [
        ("stable_weight", "What is my current weight?", "weight_stable"),
        ("stable_sleep", "How many hours did I sleep last night?", "sleep_stable"),
        ("stable_steps", "How many steps did I get yesterday?", "steps_stable"),
    ]
    return [_q(k, t, "stability", "deep", category="stability", criticality="critical",
               stability_group=g) for k, t, g in specs]


def _regression_questions():
    """Every historical production defect, frozen as a permanent test. Once fixed,
    it can never silently regress."""
    return [
        # 2026-06-28 — sleep 5.3h then 6.9h a minute apart (unstable + stale).
        _q("reg_stale_sleep", "How many hours did I sleep last night?", "regression",
           "deep", category="regression", criticality="critical",
           stability_group="reg_sleep_stable",
           notes="stale/unstable sleep: must be stable + freshness-honest"),
        # Wrong-domain: 'Did I workout today?' answered about sleep.
        _q("reg_wrong_domain", "Did I workout today?", "regression", "deep",
           category="regression", criticality="critical",
           required_any=["workout", "worked out", "exercise", "no workout",
                         "didn't work out", "rest day", "haven't"],
           forbidden=["slept", "hours of sleep", "your weight"],
           notes="must answer the asked domain, never sleep"),
        # Deterministic step count returned 'assistant unavailable'.
        _q("reg_det_steps", "How many steps did I get yesterday?", "regression",
           "deep", category="regression", criticality="critical", gates=["value"],
           notes="deterministic retrieval must never be an AI-failure message"),
        # Contradictory factual answers across repeats.
        _q("reg_contradictory", "What is my current weight?", "regression", "deep",
           category="regression", criticality="critical",
           stability_group="reg_weight_stable",
           notes="repeated identical question must return identical facts"),
        # 2026-06-28 — BLOCKER: Beth narrated "43 mg/dL (in a good range)" — confident
        # reassurance over severe hypoglycemia. Interpretation is now deterministic
        # (glucose_interpretation); narration must surface a flagged value, never
        # reassure. The dangerous value needs setup → deterministic_only (validated in
        # apps/health/tests/test_glucose_interpretation.py).
        _q("reg_glucose_safety", "What was my last glucose reading?", "regression",
           "deep", category="regression", criticality="critical",
           deterministic_only=True,
           forbidden=["good range", "in a good range", "healthy range", "looking good",
                      "you're fine", "nothing to worry"],
           notes="never reassure over a low/dangerous glucose value"),
    ]


FACTUAL_TRUST_QUESTIONS = (_intent_questions() + _truth_questions()
                           + _freshness_questions() + _deterministic_retrieval_questions()
                           + _stability_questions() + _regression_questions())

QUESTIONS = (_checkin_questions() + _goal_paraphrases() + _health_questions()
             + _rhythm_questions() + _general_questions() + _boundary_questions()
             + FACTUAL_TRUST_QUESTIONS)


_DOMAIN_TO_SUITE = {"goals": "goals", "health": "health", "general": "general",
                    "rhythm": "rhythm", "clarification": "checkin", "agenda": "checkin",
                    "personal": "boundary",
                    # Factual-trust categories all roll up to the 'factual' suite.
                    "intent": "factual", "truth": "factual", "freshness": "factual",
                    "deterministic": "factual", "stability": "factual",
                    "regression": "factual"}


def suite_of(spec):
    if spec.get("key", "").startswith(("bnd_", "amb_")):
        return "boundary"
    return _DOMAIN_TO_SUITE.get(spec.get("domain"), "full")


def questions_for(suite=None, depth="full"):
    """Questions for a suite ('full'/None = all suites) at a depth level
    (smoke ⊂ full ⊂ deep)."""
    maxr = _DEPTH_RANK.get(depth, 1)
    # Exclude deterministic_only specs from the LIVE run — the read-only harness cannot
    # create the per-question data state they require (validated in the deterministic
    # gate instead). They remain in QUESTIONS as evaluator fixtures.
    out = [q for q in QUESTIONS
           if _DEPTH_RANK.get(q["depth"], 1) <= maxr and not q.get("deterministic_only")]
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
    # GENERAL-KNOWLEDGE OUTAGE (architecture decision): general knowledge is the one
    # domain that depends on the EXTERNAL LLM — WLJ has no offline knowledge source
    # by design. When OpenAI is down, a graceful degradation IS the correct behavior,
    # so a CLEAN outage response passes the content gate (required tokens are
    # un-satisfiable during an outage). It is still held to quality: it must not leak
    # personal-domain concepts (forbidden) or any banned phrase, and must stay on the
    # general lane. Goals/Health stay strict — they own deterministic truth, so an
    # outage message THERE is still an infrastructure failure (handled below).
    if spec.get("domain") == "general" and is_failure_message(t):
        if not _domain_ok(spec, intent, lane):
            fails.append(f"wrong_domain(intent={intent},lane={lane})")
        for b in banned_hits(t, spec.get("banned", [])):
            fails.append(f"banned_phrase:{b}")
        for f in spec.get("forbidden", []):
            if f.lower() in t.lower():
                fails.append(f"forbidden_concept:{f}")
        return fails
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
    # Law 1/2 — a deterministic fact must cite a VALUE or honestly say it isn't
    # available; it may never be vague or silent about the number.
    if "value" in gates and not (has_number(t) or acknowledges_no_data(t)):
        fails.append("gate_value")
    # length sanity: a synthesis answer that is too short
    if ("synthesis" in gates or "evidence" in gates) and len(t) < max(40, spec.get("min_len", 0)):
        fails.append("too_short")
    return fails


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------
RELEASE_THRESHOLD = 95
INFRA_FAIL_THRESHOLD = 1     # more than this many infra failures => RED


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


# ---------------------------------------------------------------------------
# Architectural layer classification — every failure category maps to a layer,
# and infrastructure failures take precedence over content failures.
# ---------------------------------------------------------------------------
FAILURE_LAYERS = {
    "empty_response": "conversation_orchestration",
    "general_failure": "infrastructure",
    "slow_response": "infrastructure",
    "wrong_domain": "routing",
    "banned_phrase": "narration",
    "missing_required": "content_quality",
    "forbidden_concept": "content_quality",
    "checkin_time_awareness": "content_quality",
    "duplicate_answer": "content_quality",
    "response_quality": "content_quality",
}
# Ordered by precedence (most architectural first). A row's layer = the
# highest-precedence layer among its failures.
LAYER_PRECEDENCE = ("conversation_orchestration", "infrastructure", "routing",
                    "narration", "content_quality")
INFRA_LAYERS = ("conversation_orchestration", "infrastructure", "routing")
CONTENT_LAYERS = ("narration", "content_quality")


def layer_of(category):
    return FAILURE_LAYERS.get(category, "content_quality")


def is_infrastructure_category(category):
    return layer_of(category) in INFRA_LAYERS


def row_layer(failed_rules):
    """The dominant (highest-precedence) architectural layer for a failed row."""
    layers = {layer_of(categorize_rule(f)) for f in failed_rules}
    for lyr in LAYER_PRECEDENCE:
        if lyr in layers:
            return lyr
    return None


def compute_grade(score_percent, critical_count, infra_fails=0,
                  empty_present=False, entire_suite_failed=False):
    """Stronger grade: ANY of these deterministically forces RED — an empty
    response, an entire suite failing, or too many infrastructure failures."""
    if (empty_present or entire_suite_failed
            or infra_fails > INFRA_FAIL_THRESHOLD or critical_count > 0):
        return "RED"
    return grade(score_percent, critical_count)


ARCHITECTURAL_INVARIANTS = (
    "ARCHITECTURAL INVARIANTS (system laws — a violation is a release blocker):\n"
    "1. Empty responses are never acceptable.\n"
    "2. Every request must produce an OpenAI response, a deterministic fallback, "
    "OR a graceful failure response — never nothing.\n"
    "3. WLJ owns truth; ChatGPT only NARRATES truth.\n"
    "4. OpenAI outages must degrade gracefully (never an empty box, never a raw "
    "error).\n"
    "5. Deterministic providers (reasoning fallbacks, foundational facts) must "
    "remain reachable even when OpenAI is down.\n"
    "6. An entire-suite failure is presumed SYSTEMIC until proven otherwise.\n"
    "7. Any path that bypasses the fallback is a release blocker.\n"
    "8. Infrastructure failures take PRECEDENCE over content failures."
)
