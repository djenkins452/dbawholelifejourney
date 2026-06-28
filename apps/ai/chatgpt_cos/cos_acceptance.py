# ==============================================================================
# File: apps/ai/chatgpt_cos/cos_acceptance.py
# Project: Whole Life Journey
# Description: CHIEF-OF-STAFF Acceptance Suite — the highest acceptance layer, ABOVE
#   Deep (Truth Certification). Deep proves the FACTS are right; this evaluates
#   whether Beth handled the CONVERSATION like a trusted, first-class Chief of Staff
#   built on those facts. Weighted scoring (not pass/fail). Pure functions — no DB,
#   no OpenAI (the live harness supplies Beth's responses; scoring is deterministic
#   against a golden rubric and can be refined by an LLM judge later).
#   Gated: may NEVER run unless Deep is GREEN. Spec:
#   docs/BETH_CHIEF_OF_STAFF_ACCEPTANCE_SUITE.md, docs/WLJ_ARCHITECTURE_LAWS.md
# ==============================================================================

# ---------------------------------------------------------------------------
# Weighted rubric — "would an exceptional human Chief of Staff have done better?"
# Weights sum to 1.0. TRUST and INTENT are HARD-FAIL dimensions: a violation there
# zeroes the dimension AND fails the whole scenario (a trust break or a wrong-
# question answer is never redeemable by other strengths).
# ---------------------------------------------------------------------------
DIMENSIONS = (
    "trust",                # increases (not decreases) trust — no stale/overconfident/misleading
    "intent",               # answered the ACTUAL question
    "truth_preservation",   # uncertainty explained, never false certainty
    "holistic",             # incorporated RELEVANT known context (not unrelated noise)
    "initiative",           # noticed something worth mentioning unasked
    "coaching",             # useful, context-specific next step (not a cliché)
    "customer_confidence",  # net: would a paying customer rely on this tomorrow?
)
WEIGHTS = {
    "trust": 0.20, "intent": 0.20, "truth_preservation": 0.15, "holistic": 0.15,
    "initiative": 0.10, "coaching": 0.10, "customer_confidence": 0.10,
}
HARD_FAIL_DIMENSIONS = ("trust", "intent")

# Failure classification (drives engineering priorities — Law-tied).
CLASS_TRUTH = "Truth"
CLASS_RETRIEVAL = "Retrieval"
CLASS_CONTEXT = "Context"
CLASS_ORCHESTRATION = "Orchestration"
CLASS_REASONING = "Reasoning"
CLASS_COACHING = "Coaching"

COS_RELEASE_THRESHOLD = 0.90   # weighted score for GREEN
COS_YELLOW_THRESHOLD = 0.75


def _scn(scenario_id, title, question, **kw):
    """A golden Chief-of-Staff scenario. `expects`/`forbids` map a dimension to
    signal phrases; `law`/`capability`/`classification` drive the report; `why`
    explains why a failure matters to customer trust; `setup` documents the data
    state the live harness must establish."""
    return {
        "id": scenario_id, "title": title, "question": question,
        "history": kw.get("history", []),
        "setup": kw.get("setup", ""),
        "expects": kw.get("expects", {}),
        "forbids": kw.get("forbids", {}),
        "law": kw.get("law", ""),
        "capability": kw.get("capability", ""),
        "classification": kw.get("classification", ""),
        "why": kw.get("why", ""),
    }


# ---------------------------------------------------------------------------
# Golden conversation library — seeded from real production incidents. Every future
# production issue should be appended here as a permanent scenario.
# ---------------------------------------------------------------------------
COS_SCENARIOS = [
    _scn("cos_good_morning_stale_sleep", "Good morning with stale sleep",
         "Good morning",
         setup="Overnight Apple Health sleep NOT yet synced (pending).",
         expects={"trust": ["haven't synced", "not synced", "don't have", "pending",
                            "not yet"],
                  "truth_preservation": ["haven't synced", "don't have", "not yet",
                                         "once it syncs", "when it syncs"],
                  "initiative": ["sync", "apple health", "healthkit"]},
         forbids={"trust": ["you slept 5.3", "you slept 6.9", "you got 5.3 hours",
                            "you got 6.9 hours"]},
         law="Law 1 (Freshness) / Law 5 (Stable Truth)", capability="freshness-awareness",
         classification=CLASS_TRUTH,
         why="Presenting unsynced sleep as a confident number — or flip-flopping it — "
             "is the fastest way to lose a user's trust in every other number."),

    _scn("cos_workout_answered_with_sleep", "Workout question answered with sleep",
         "Did I workout today?",
         setup="No workout logged today; sleep data present.",
         expects={"intent": ["workout", "worked out", "exercise", "no workout",
                             "didn't work out", "haven't worked out", "rest day"]},
         forbids={"intent": ["you slept", "hours of sleep", "your sleep"],
                  "trust": ["you slept", "hours of sleep"]},
         law="Law 0 (Intent Before Retrieval)", capability="intent-scoping",
         classification=CLASS_RETRIEVAL,
         why="Answering a different question than asked makes Beth feel like a chatbot, "
             "not a Chief of Staff who listens."),

    _scn("cos_deterministic_retrieval_failure", "Deterministic retrieval failure",
         "How many steps did I get yesterday?",
         setup="Step count exists deterministically in WLJ.",
         expects={"intent": ["step"],
                  "truth_preservation": ["step"]},
         forbids={"trust": ["temporarily unavailable", "couldn't pull that together",
                           "assistant unavailable", "try again"],
                  "intent": ["temporarily unavailable", "couldn't pull that together"]},
         law="Law 4 (Deterministic Retrieval ≠ AI Failure)", capability="deterministic-retrieval",
         classification=CLASS_RETRIEVAL,
         why="A fact WLJ already owns, hidden behind an AI outage message, tells the "
             "customer the assistant is unreliable for the basics."),

    _scn("cos_medication_education", "Medication education (enumeration+enrichment)",
         "Can you list each medicine I take and what each is commonly used for?",
         setup="User takes several medications (deterministic list in WLJ).",
         expects={"intent": ["used for", "commonly used", "diabetes", "blood sugar",
                            "blood pressure", "cholesterol"],
                  "holistic": ["you take", "your medication", "based on"],
                  "coaching": ["doctor", "pharmacist", "provider"]},
         forbids={"trust": ["couldn't pull that together", "temporarily unavailable"]},
         law="Law 3 (Orchestration Before Reasoning)", capability="enumeration+enrichment",
         classification=CLASS_ORCHESTRATION,
         why="A retrieve→enrich→assemble request that errors out reads as 'Beth can't "
             "handle my real medication list' — a credibility loss for a health product."),

    _scn("cos_cgm_false_low_investigation", "CGM false-low investigation",
         "My Dexcom says my glucose is 45 but I just ate a big slice of pizza.",
         setup="A 45 mg/dL reading shortly after a high-carb meal — physiologically odd.",
         expects={"truth_preservation": ["doesn't quite fit", "unusual", "unexpected",
                                        "wouldn't expect", "odd", "verify", "double-check",
                                        "finger stick", "fingerstick", "compression"],
                  "initiative": ["verify", "double-check", "confirm", "sensor",
                                "finger stick", "compression low"],
                  "trust": ["wouldn't expect", "doesn't quite fit", "verify"]},
         forbids={"trust": ["you are hypoglycemic", "treat the low immediately",
                          "your blood sugar is dangerously low"]},
         law="Law 2 (Confidence Before Conversation)", capability="expectation-matching",
         classification=CLASS_REASONING,
         why="An elite CoS notices observed-vs-expected mismatch (pizza → low doesn't "
             "fit) and verifies before alarming — confidently declaring a true hypo on "
             "a likely sensor artifact is dangerous AND trust-destroying."),

    _scn("cos_goal_coaching", "Goal coaching (specific, not generic)",
         "How do I get back on track with my France 2027 goal?",
         setup="Goal is behind pace; recent activity has slipped.",
         expects={"coaching": ["this week", "specific", "schedule", "your next",
                              "18k", "training", "miles", "km"],
                  "holistic": ["france", "18k", "your"],
                  "initiative": ["behind", "slipped", "pace"]},
         forbids={"coaching": ["maintain momentum", "stay consistent", "keep going",
                             "you've got this", "take the next step", "keep it up"]},
         law="Beth Principles (no coaching clichés)", capability="context-specific-coaching",
         classification=CLASS_COACHING,
         why="Generic encouragement is what a chatbot does; a Chief of Staff gives a "
             "concrete, situation-aware next move."),

    _scn("cos_daily_planning", "Daily planning (holistic prioritization)",
         "What should I focus on today?",
         setup="Calendar, health signals, and goals all have relevant items today.",
         expects={"holistic": ["calendar", "appointment", "meeting", "goal", "health",
                             "sleep", "today"],
                  "coaching": ["first", "start with", "priority", "focus"],
                  "initiative": ["conflict", "coming up", "deadline", "before"]},
         forbids={"trust": ["temporarily unavailable", "couldn't pull that together"]},
         law="Law 3 (Orchestration) / holistic context", capability="cross-domain-synthesis",
         classification=CLASS_CONTEXT,
         why="A CoS synthesizes across the calendar, health, and goals to set the day; "
             "answering from one domain misses the point of having a CoS."),

    _scn("cos_weight_trend_discussion", "Weight trend discussion",
         "How's my weight trending?",
         setup="Weight entries exist; most recent may be a few days old.",
         expects={"truth_preservation": ["lb", "pound", "kg", "down", "up", "stable",
                                       "trend"],
                  "holistic": ["goal weight", "your goal", "toward"],
                  "initiative": ["last entry", "as of", "haven't logged", "a few days"]},
         forbids={"trust": ["temporarily unavailable"]},
         law="Law 1 (Freshness) / Law 2 (Confidence)", capability="trend-with-freshness",
         classification=CLASS_TRUTH,
         why="A trend stated without its as-of date, or invented from stale data, "
             "quietly misleads the customer about real progress."),
]


def scenarios():
    return list(COS_SCENARIOS)


# ---------------------------------------------------------------------------
# Deep dependency — the Chief-of-Staff suite may NEVER run unless Deep is GREEN.
# ---------------------------------------------------------------------------
def cos_enabled(deep_grade):
    """True only when the latest Deep (Truth Certification) run graded GREEN."""
    return str(deep_grade or "").upper() == "GREEN"


def disabled_reason(deep_grade):
    g = str(deep_grade or "").upper()
    if not g:
        return ("Chief of Staff is locked: run Deep (Truth Certification) first. "
                "Beth must prove her facts before her judgment is evaluated.")
    if g != "GREEN":
        return (f"Chief of Staff is locked because Deep is {g}. Resolve the Deep "
                f"factual-trust failures first — a conversation built on wrong, stale, "
                f"or unstable facts cannot be a good conversation.")
    return ""


# ---------------------------------------------------------------------------
# Scoring — deterministic weighted rubric.
# ---------------------------------------------------------------------------
def _present(signals, text):
    t = (text or "").lower()
    return [s for s in signals if s.lower() in t]


def score_response(scenario, response):
    """Score one Beth response against a golden scenario. Returns a dict:
        dimensions: {dim: 0..1}, weighted: 0..1, hard_fail: bool, grade,
        failures: [dim], details: {dim: {expected_hit, forbidden_hit}}.
    Deterministic — same response ⇒ same score (mirrors Law 5 for the evaluator)."""
    expects = scenario.get("expects", {})
    forbids = scenario.get("forbids", {})
    dims, details, failures = {}, {}, []
    hard_fail = False
    for dim in DIMENSIONS:
        exp = expects.get(dim, [])
        forb = forbids.get(dim, [])
        forb_hit = _present(forb, response)
        exp_hit = _present(exp, response)
        if forb_hit:
            # Tripped a forbidden signal (stale number, wrong domain, AI-outage…).
            score = 0.0
            if dim in HARD_FAIL_DIMENSIONS:
                hard_fail = True
        elif exp:
            # `expects` are ALTERNATIVES — demonstrating the dimension with ANY of
            # them satisfies it (a great answer won't recite a checklist).
            score = 1.0 if exp_hit else 0.0
        else:
            score = 1.0  # dimension not exercised by this scenario → neutral
        dims[dim] = score
        details[dim] = {"expected_hit": exp_hit, "forbidden_hit": forb_hit,
                        "expected": exp, "forbidden": forb}
        # A dimension the scenario exercises that the answer missed.
        if (exp or forb) and score < 0.5:
            failures.append(dim)
    weighted = round(sum(WEIGHTS[d] * dims[d] for d in DIMENSIONS), 3)
    return {"dimensions": dims, "weighted": weighted, "hard_fail": hard_fail,
            "grade": cos_grade(weighted, hard_fail), "failures": failures,
            "details": details}


def cos_grade(weighted, hard_fail):
    if hard_fail:
        return "RED"
    if weighted >= COS_RELEASE_THRESHOLD:
        return "GREEN"
    if weighted >= COS_YELLOW_THRESHOLD:
        return "YELLOW"
    return "RED"


def grade_run(scored_list):
    """Roll up per-scenario scores into a suite grade. ANY hard-fail ⇒ RED."""
    if not scored_list:
        return {"grade": "RED", "avg_weighted": 0.0, "hard_fails": 0, "count": 0}
    hard = sum(1 for s in scored_list if s.get("hard_fail"))
    avg = round(sum(s["weighted"] for s in scored_list) / len(scored_list), 3)
    if hard:
        grade = "RED"
    else:
        grade = "GREEN" if avg >= COS_RELEASE_THRESHOLD else (
            "YELLOW" if avg >= COS_YELLOW_THRESHOLD else "RED")
    return {"grade": grade, "avg_weighted": avg, "hard_fails": hard,
            "count": len(scored_list)}


# ---------------------------------------------------------------------------
# Reporting — every failure tied to an Architecture Law + a capability gap. The
# report is meant to GUIDE ENGINEERING PRIORITIES, not just grade.
# ---------------------------------------------------------------------------
def scenario_report(scenario, response, scored=None):
    """A per-scenario report entry. For a failing scenario, names what happened,
    why it matters to customer trust, which Law it violated, and the capability
    classification (Truth/Retrieval/Context/Orchestration/Reasoning/Coaching)."""
    s = scored or score_response(scenario, response)
    chatbot = bool(s["failures"]) or s["hard_fail"]
    return {
        "id": scenario["id"], "title": scenario["title"],
        "grade": s["grade"], "weighted": s["weighted"], "hard_fail": s["hard_fail"],
        "behaved_like": "chatbot" if chatbot else "chief_of_staff",
        "failed_dimensions": s["failures"],
        # The 5 report facets the spec requires:
        "what_happened": (
            f"On '{scenario['question']}', Beth scored {s['weighted']:.2f}"
            + (" with a hard trust/intent failure" if s["hard_fail"] else "")
            + (f"; weak on {', '.join(s['failures'])}" if s["failures"] else "")
            + "." ),
        "why_it_matters": scenario.get("why", ""),
        "law_violated": scenario.get("law", "") if chatbot else "",
        "missing_capability": scenario.get("capability", "") if chatbot else "",
        "classification": scenario.get("classification", "") if chatbot else "",
    }


def build_report(pairs):
    """pairs: list of (scenario, response). Returns the full Chief-of-Staff report:
    the suite grade, where Beth was first-class vs a chatbot, and a priority list
    grouped by capability classification."""
    scored = [(scn, score_response(scn, resp)) for scn, resp in pairs]
    run = grade_run([s for _, s in scored])
    entries = [scenario_report(scn, resp, s)
               for (scn, resp), (_, s) in zip(pairs, scored)]
    first_class = [e for e in entries if e["behaved_like"] == "chief_of_staff"]
    chatbot = [e for e in entries if e["behaved_like"] == "chatbot"]
    by_class = {}
    for e in chatbot:
        by_class.setdefault(e["classification"] or "Unclassified", []).append(e["id"])
    return {
        "grade": run["grade"], "avg_weighted": run["avg_weighted"],
        "hard_fails": run["hard_fails"], "count": run["count"],
        "first_class": [e["id"] for e in first_class],
        "behaved_like_chatbot": [e["id"] for e in chatbot],
        "priority_by_capability": by_class,
        "entries": entries,
    }
