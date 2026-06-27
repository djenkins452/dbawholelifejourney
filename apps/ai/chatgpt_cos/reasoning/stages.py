# ==============================================================================
# File: apps/ai/chatgpt_cos/reasoning/stages.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reasoning Lane stages — planner, retrieval, working memory, reasoner
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
The four deterministic-boundary stages of the Reasoning Lane.

    run_planner          -> RetrievalPlan        (small, constrained Planner LLM)
    retrieve_truth       -> truth package        (deterministic, authoritative)
    build_working_memory -> working memory        (curated; OpenAI sees ONLY this)
    run_reasoning        -> narrative             (one plain _call_api + fallback)

Every stage logs its payload (requirement: inspectable/loggable at each stage).
No agentic tool loop. No raw SAE reaches OpenAI.
"""

import json
import logging
import re

from apps.ai.chatgpt_cos.reasoning.plan import (
    ALLOWED_DOMAINS,
    ALLOWED_TRUTH,
    IMPLEMENTED_INTENTS,
    parse_plan,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Stage 1 — Planner LLM (structured Retrieval Plan; never answers the user)
# ----------------------------------------------------------------------------
_PLANNER_SYSTEM = (
    "You are the RETRIEVAL PLANNER for a personal wellness Chief of Staff. You "
    "do NOT answer the user. You output ONLY a JSON retrieval plan describing "
    "which deterministic truth must be fetched to answer the question.\n\n"
    "Output JSON EXACTLY this shape:\n"
    "{\n"
    '  "intent": one of ' + json.dumps(list(IMPLEMENTED_INTENTS)) + ' or "other",\n'
    '  "response_mode": "lookup" | "reasoning" | "mixed",\n'
    '  "domains": subset of ' + json.dumps(list(ALLOWED_DOMAINS)) + ',\n'
    '  "required_truth": subset of ' + json.dumps(list(ALLOWED_TRUTH)) + ',\n'
    '  "optional_truth": subset of ' + json.dumps(list(ALLOWED_TRUTH)) + ',\n'
    '  "reasoning_style": short label,\n'
    '  "urgency": "low" | "normal" | "high",\n'
    '  "confidence": 0.0-1.0\n'
    "}\n\n"
    "Rules — pick the intent that matches the user's INTENT. Two domains are "
    "implemented (HEALTH and GOALS); keep each intent DISTINCT by shape.\n"
    "HEALTH intents — required_truth ONLY "
    "['health_state','foundational_health'], domains ONLY ['health']:\n"
    "- 'biggest_health_risk': the SINGLE highest-priority health issue. One thing.\n"
    "- 'health_concerns': a RANKED LIST of current health concerns. Multiple things.\n"
    "- 'health_focus_today': the best ACTIONABLE health step for TODAY. Today + action.\n"
    "- 'overall_progress': an executive SUMMARY of overall HEALTH status/trajectory.\n"
    "GOALS intents — required_truth ONLY ['goals_state','habits_state'], domains "
    "ONLY ['goals']:\n"
    "- 'biggest_goal_risk': the SINGLE goal most at risk (overdue/stalling). One thing.\n"
    "- 'goal_concerns': a RANKED LIST of goals/habits that are slipping. Multiple things.\n"
    "- 'goals_focus_today': the ONE goal action to advance TODAY. Today + action.\n"
    "- 'goals_progress': a SUMMARY of how a goal is progressing (milestone/momentum/wins).\n"
    "- 'goal_on_track': a TRAJECTORY verdict — am I on track / on pace? (yes-no + why).\n"
    "- 'goal_why_priority': the STRATEGIC RATIONALE — why this goal matters most.\n"
    "- 'goal_next_milestone': ONLY the current/next MILESTONE for a goal.\n"
    "- 'goal_failure_modes': what could CAUSE the goal to FAIL (risk-of-failure list).\n"
    "- 'goal_confidence': a CONFIDENCE assessment — how likely to achieve it.\n"
    "These are DISTINCT: 'how is X going'→goals_progress; 'am I on track'→goal_on_track; "
    "'why is X my priority'→goal_why_priority; 'next milestone'→goal_next_milestone; "
    "'what could make X fail'→goal_failure_modes; 'how confident'→goal_confidence.\n"
    "Match the DOMAIN to the question: health questions → health intents + health "
    "truth; goal/habit/mission/priority questions → goal intents + goal truth. "
    "NEVER mix truth across domains (no health truth for a goal intent, or "
    "vice-versa). Use intent='other' for anything else. NEVER invent truth keys "
    "outside the lists. NEVER write prose. NEVER answer the user. JSON only."
)


def run_planner(user, message):
    """Stage 1: the constrained Planner LLM returns a RetrievalPlan (or None)."""
    from apps.ai.services import ai_service
    try:
        raw = ai_service._call_api(
            _PLANNER_SYSTEM, message or "",
            max_tokens=220, temperature=0.0, endpoint="cos_chat", user=user,
        )
    except Exception:
        logger.warning("COS_REASONING_PLANNER_FAILED user=%s",
                       getattr(user, "id", None), exc_info=True)
        return None
    plan = parse_plan(raw)
    logger.info(
        "COS_REASONING_PLAN user=%s plan=%s",
        getattr(user, "id", None),
        json.dumps(plan.as_dict()) if plan else None,
    )
    return plan


# ----------------------------------------------------------------------------
# Stage 2 — Deterministic, authoritative truth retrieval (closed vocabulary)
# ----------------------------------------------------------------------------
_CANONICAL_MODES = ("execution", "risk", "fix")


def _decision(user, mode):
    # Canonical modes only (no legacy cos_mode_router import — keeps the clean
    # runtime free of conversational modules; enforced by the import-drift test).
    mode = mode if mode in _CANONICAL_MODES else "execution"
    from apps.core.execution.execution_state import build_execution_state
    from apps.core.execution.selectors import select as run_selector
    state = build_execution_state(user)
    d = run_selector(mode, state)
    return {
        "mode": d.get("mode"),
        "primary_action": d.get("primary_action"),
        "reason": d.get("reason"),
        "message": d.get("message"),
        "follow_on": d.get("follow_on"),
    }


def _domain(user, domain):
    from apps.ai.cos_services import get_domain_state
    return get_domain_state(user, domain)


_FOUNDATION_KEYS = [
    "current_weight", "last_glucose_reading", "last_blood_pressure_reading",
    "sleep_last_night", "calories_today", "protein_today",
]

TRUTH_PROVIDERS = {
    "risk_decision": lambda u: _decision(u, "risk"),
    "execution_decision": lambda u: _decision(u, "execution"),
    "fix_decision": lambda u: _decision(u, "fix"),
    "standing_context": lambda u: __import__(
        "apps.ai.cos_services", fromlist=["get_standing_context"]
    ).get_standing_context(u),
    "foundational_health": lambda u: __import__(
        "apps.ai.cos_services", fromlist=["get_foundational_health_facts"]
    ).get_foundational_health_facts(u, _FOUNDATION_KEYS),
    "health_state": lambda u: _domain(u, "health"),
    "goals_state": lambda u: _domain(u, "purpose"),
    "habits_state": lambda u: _domain(u, "habits"),
    "fitness_state": lambda u: _domain(u, "fitness"),
    "nutrition_state": lambda u: _domain(u, "nutrition"),
}

# domain name -> the truth key used to fetch that domain's state
_DOMAIN_TRUTH = {
    "health": "health_state", "fitness": "fitness_state",
    "nutrition": "nutrition_state", "goals": "goals_state",
    "habits": "habits_state",
}

# Per-intent truth SCOPE. Health intents are restricted to health truth ONLY —
# the generic cross-domain decisions (risk_decision/execution_decision/...) and
# task/finance truth are dropped here so they never reach health reasoning,
# regardless of what the planner emits (defense-in-depth against contamination).
HEALTH_TRUTH = frozenset({"health_state", "foundational_health"})
HEALTH_INTENTS = ("biggest_health_risk", "overall_progress",
                  "health_focus_today", "health_concerns")
# Goals domain (#2): goals-truth ONLY (goals_state + habits_state — Goals
# consumes Habits per docs/BETH_DOMAIN_DEPENDENCY_GRAPH.md). Same defense-in-depth
# isolation as health — no cross-domain truth can reach a goal intent.
GOALS_TRUTH = frozenset({"goals_state", "habits_state"})
GOAL_INTENTS = ("biggest_goal_risk", "goals_progress",
                "goals_focus_today", "goal_concerns",
                "goal_on_track", "goal_why_priority", "goal_next_milestone",
                "goal_failure_modes", "goal_confidence")
INTENT_TRUTH_SCOPE = {
    **{i: HEALTH_TRUTH for i in HEALTH_INTENTS},
    **{i: GOALS_TRUTH for i in GOAL_INTENTS},
}


def retrieve_truth(user, plan):
    """Stage 2: fetch every planned truth key deterministically. Unknown keys
    are ignored (never fabricated); provider errors are captured, never raised.
    For scoped intents (e.g. health), keys outside the scope are dropped."""
    keys = []
    for k in list(plan.required_truth) + list(plan.optional_truth):
        if k not in keys:
            keys.append(k)
    for d in plan.domains:
        dk = _DOMAIN_TRUTH.get(d)
        if dk and dk not in keys:
            keys.append(dk)

    scope = INTENT_TRUTH_SCOPE.get(plan.intent)
    if scope is not None:
        dropped = [k for k in keys if k not in scope]
        if dropped:
            logger.info("COS_REASONING_SCOPE_DROP intent=%s dropped=%s",
                        plan.intent, ",".join(dropped))
        keys = [k for k in keys if k in scope]

    truth = {}
    for key in keys:
        provider = TRUTH_PROVIDERS.get(key)
        if provider is None:
            continue
        try:
            truth[key] = provider(user)
        except Exception:
            logger.warning("COS_REASONING_TRUTH_ERROR user=%s key=%s",
                           getattr(user, "id", None), key, exc_info=True)
            truth[key] = {"status": "error", "key": key}

    logger.info(
        "COS_REASONING_TRUTH user=%s keys=%s bytes=%d",
        getattr(user, "id", None), ",".join(truth.keys()) or "none",
        len(json.dumps(truth, default=str)),
    )
    return truth


# ----------------------------------------------------------------------------
# Stage 3 — Working Memory Builder (curated; OpenAI never sees raw SAE)
# ----------------------------------------------------------------------------
_WM_MAX_LIST = 3


def _curate_value(v):
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    if isinstance(v, list):
        return [_curate_value(x) for x in v[:_WM_MAX_LIST]]
    if isinstance(v, dict):
        return {k: vv for k, vv in list(v.items())[:8]
                if isinstance(vv, (int, float, str, bool)) or vv is None}
    return str(v)[:200]


# ---- Health Working Memory Curator -----------------------------------------
# Health intents receive ONLY curated health truth — current status, trends,
# active risks, goal progress — derived SOLELY from health_state +
# foundational_health. It cannot leak tasks/decisions/finances because it never
# reads those keys (structural guarantee against the Harley-task contamination).
_H_STATUS = ("weight_current", "weight_unit", "latest_glucose",
             "latest_glucose_unit", "bp_systolic", "bp_diastolic",
             "sleep_avg_hours_7d", "heart_rate_avg_7d", "latest_blood_oxygen")
_H_TRENDS = ("weight_trend", "sleep_trend", "glucose_avg_7d",
             "glucose_variability_label")
_H_RISKS = ("weight_goal_on_track", "plateau_status", "plateau_risk_label",
            "muscle_preservation_status", "muscle_loss_risk_level",
            "fat_loss_quality_label", "glucose_variability_level")
_H_GOALS = ("weight_goal", "weight_goal_remaining", "weight_goal_on_track",
            "weight_goal_target_date")


def _pick(state, keys):
    return {k: state[k] for k in keys if state.get(k) is not None}


# ---- Fix 3: tone calibration — soften alarmist raw SAE risk labels ----------
_SEVERE_TO_CALIBRATED = (
    ("significant", "elevated — worth watching"),
    ("critical", "worth attention"),
    ("dangerous", "worth watching"),
    ("danger", "worth watching"),
    ("severe", "notable"),
    ("high risk", "elevated — worth watching"),
)


def _calibrate_label(v):
    if not isinstance(v, str):
        return v
    low = v.strip().lower()
    for severe, mild in _SEVERE_TO_CALIBRATED:
        if severe in low:
            return mild
    return v


def _calibrate_risks(risks):
    return {k: _calibrate_label(v) for k, v in risks.items()}


# ---- Fix #1: deterministic, evidence-ranked health concerns -----------------
# Prevents the model anchoring on one striking number (e.g. early-day 0 protein)
# by handing it a prioritized list of GENUINE concerns. Benign labels and
# early-day nutrition (not yet logged) are excluded — they are not risks.
_BENIGN_RISK = {"low", "stable", "none", "good", "optimal", "normal",
                "insufficient_data", "on track", "on_track", ""}


def _nonbenign(v):
    return isinstance(v, str) and v.strip().lower() not in _BENIGN_RISK


def _num(v):
    return v if isinstance(v, (int, float)) else None


def _rank_health_concerns(buckets):
    """Evidence-ranked health concerns as plain COACHING language (never raw
    labels/enums). Severity reflects clinical meaningfulness — glucose/diabetes
    management and sleep outrank muscle/nutrition — not the biggest numeric gap.
    Returns an ordered list of {concern, action} dicts (highest priority first).
    """
    risks = buckets.get("active_risks") or {}
    gp = buckets.get("goal_progress") or {}
    cs = buckets.get("current_status") or {}
    tr = buckets.get("major_trends") or {}
    nc = buckets.get("nutrition_context") or {}
    out = []  # (severity, concern, action)

    # Diabetes / glucose management — highest stakes (chronic condition).
    glu, glu_avg = _num(cs.get("latest_glucose")), _num(tr.get("glucose_avg_7d"))
    if (glu and glu >= 180) or (glu_avg and glu_avg >= 154):
        out.append((5, "your blood sugar has been running high lately",
                    "a short walk after meals and steadier carb timing is the highest-leverage move"))
    elif _nonbenign(risks.get("glucose_variability_label")):
        out.append((3, "your blood sugar has been swinging more than usual",
                    "more consistent meal timing and portions will help smooth it out"))

    # Sleep — foundational; affects everything else.
    sleep = _num(cs.get("sleep_avg_hours_7d"))
    if sleep is not None and sleep < 6.5:
        out.append((4, "you've been averaging under 6.5 hours of sleep, which makes everything else harder",
                    "protecting a consistent bedtime this week is the best next step"))
    elif tr.get("sleep_trend") == "decreasing":
        out.append((2, "your sleep has been trending down",
                    "an earlier wind-down a few nights would help"))

    # Weight-loss pace.
    if gp.get("weight_goal_on_track") is False:
        out.append((3, "your weight-loss pace is a bit behind where you'd planned",
                    "a small, steady calorie adjustment beats a big change"))

    # Plateau.
    if _nonbenign(risks.get("plateau_risk_label")):
        out.append((2, "your weight loss looks like it may be stalling",
                    "a short diet break or a training tweak can restart progress"))

    # Muscle preservation.
    if _nonbenign(risks.get("muscle_loss_risk_level")):
        out.append((2, "you may be losing some muscle along with the fat",
                    "keeping protein up and strength-training 2–3× a week protects it"))

    # Nutrition — only a genuine late-day gap, never early-day; lowest priority.
    for slot, what in (("protein_g", "protein"), ("calories", "calories")):
        if (nc.get(slot) or {}).get("interpretation") in (
                "below_typical_for_time_of_day", "nothing_logged_today"):
            out.append((1, f"your {what} is running low for today",
                        f"a {what}-focused next meal would close the gap"))

    out.sort(key=lambda x: -x[0])
    return [{"concern": c, "action": a} for _s, c, a in out]


# ---- Fix 2: time-aware intra-day nutrition interpretation ------------------
def _intra_day_hint(today, avg, target, phase):
    t = today or 0
    if phase == "morning":
        return "early_day_not_yet_logged" if t == 0 else "logging_in_progress"
    ref = avg or target or 0
    if t == 0:
        return "nothing_logged_today"
    if ref and t < 0.5 * ref:
        return "below_typical_for_time_of_day"
    return "on_track_for_time_of_day"


def _nutrition_time_context(user):
    """Deterministic, time-aware view of intra-day nutrition counters so a 0
    counter early in the day is NOT read as a deficit. Includes the 7-day
    typical (sustained trend) for reference."""
    try:
        from apps.core.ai_state.state_engine import get_module_state
        from apps.core.utils import get_user_now
        nut = get_module_state(user, "nutrition", allow_rebuild=False) or {}
        hour = get_user_now(user).hour
    except Exception:
        return {}
    phase = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"

    def slot(today_k, avg_k, target_k):
        today, avg, target = nut.get(today_k), nut.get(avg_k), nut.get(target_k)
        if today is None and avg is None:
            return None
        return {"today": today, "target": target, "typical_7d_avg": avg,
                "day_phase": phase,
                "interpretation": _intra_day_hint(today, avg, target, phase)}

    out = {}
    p = slot("daily_protein_g", "rolling_7d_protein_avg", "protein_target")
    c = slot("daily_calories", "rolling_7d_calories_avg", "calorie_target")
    if p:
        out["protein_g"] = p
    if c:
        out["calories"] = c
    out["day_phase"] = phase
    return out if (out.get("protein_g") or out.get("calories")) else {}


def _strip_source(fh):
    """Foundational facts minus intra-day nutrition counters AND internal
    'source' paths (e.g. 'SAE.health.weight_current') — never user-facing."""
    out = {}
    for k, v in (fh or {}).items():
        if k in ("calories_today", "protein_today"):
            continue
        if isinstance(v, dict):
            out[k] = {kk: vv for kk, vv in v.items() if kk != "source"}
        else:
            out[k] = v
    return out


def health_working_memory(truth, user=None):
    """HealthWorkingMemoryCurator — health-truth ONLY and EXECUTIVE-CLEAN.

    The model-facing output contains NO raw SAE labels, enum codes, internal
    field names, or data-source paths. Risk signals are expressed solely as
    evidence-ranked coaching concerns (ranked_concerns). Enum labels live only in
    the internal ranking inputs, never in what the model (or user) sees.
    """
    hs = truth.get("health_state")
    state = hs.get("state") if isinstance(hs, dict) else None
    state = state if isinstance(state, dict) else {}
    fh = truth.get("foundational_health") or {}

    # Internal ranking inputs — enum labels stay HERE, not in the model-facing WM.
    rank_input = {
        "active_risks": _pick(state, _H_RISKS),
        "goal_progress": _pick(state, _H_GOALS),
        "current_status": _pick(state, _H_STATUS),
        "major_trends": _pick(state, _H_TRENDS),
        "nutrition_context": _nutrition_time_context(user) if user is not None else {},
    }
    ranked = _rank_health_concerns(rank_input)

    # Model-facing facts: numbers / bools / human words / coaching only.
    facts = {}
    if rank_input["current_status"]:
        facts["current_status"] = rank_input["current_status"]
    trends = {k: v for k, v in rank_input["major_trends"].items()
              if not k.endswith("_label")}          # drop enum labels
    if trends:
        facts["trends"] = trends
    if rank_input["goal_progress"]:
        facts["goal_progress"] = rank_input["goal_progress"]
    if rank_input["nutrition_context"]:
        facts["nutrition_context"] = rank_input["nutrition_context"]
    ff = _strip_source(fh) if isinstance(fh, dict) else {}
    if ff:
        facts["foundational_facts"] = ff
    if ranked:
        facts["ranked_concerns"] = ranked
    return facts


def _generic_curator(truth, user=None):
    """Default curator for unmapped intents (each domain registers its own)."""
    return {key: _curate_value(data) for key, data in truth.items()}


# ===========================================================================
# GOALS domain (Beth domain #2) — mirrors the health curator/ranking/fallback
# pattern exactly. Goals-truth ONLY (goals_state + habits_state); EXECUTIVE-CLEAN
# (no IDs, enums, raw momentum scores, field names, or source paths reach the
# model). See docs/BETH_DOMAIN_REASONING_FRAMEWORK.md (§④–⑦).
# ===========================================================================
def _first_title(items):
    for t in (items or []):
        if isinstance(t, dict) and t.get("title"):
            return t.get("title")
    return None


def _goal_evidence(entry):
    """The sanitized momentum evidence on a goal/mission entry, or None."""
    if not isinstance(entry, dict):
        return None
    e = entry.get("evidence")
    return e if isinstance(e, dict) else None


def _evidence_healthy(e):
    # Real progress per the nightly momentum engine: steady-or-better momentum
    # that isn't slipping counts as progressing (a goal can hold steady on strong
    # foundations — e.g. weight trending down, milestone achieved — without a
    # "strong" score). Steady/moderate is healthy; only falling/low is not.
    return bool(e) and (e.get("momentum") in ("strong", "moderate")
                        and e.get("trend") != "falling")


def _evidence_losing(e):
    # Evidence-backed stall: falling trend or low momentum.
    return bool(e) and (e.get("trend") == "falling" or e.get("momentum") == "low")


# Risk LANGUAGE and kind vary by canonical goal STATE. drifting/stalled/failing are
# real RISKS; stable/thriving are WATCH items. Phrases avoid system-speak
# ("maintain consistency", "keep momentum") — the concrete next step is the action.
# (severity, kind, phrase)
_GOAL_STATE_RISK = {
    "failing":  (50, "risk",  "needs urgent recovery — it's overdue or clearly "
                              "declining and won't succeed without a reset"),
    "stalled":  (40, "risk",  "has stalled — there's been little recent progress"),
    "drifting": (30, "risk",  "is drifting — recent execution has dropped off"),
    "stable":   (25, "watch", "is on pace and tracking to plan"),
    "thriving": (20, "watch", "is thriving — ahead of pace, with the evidence backing it up"),
}

# Generic / system phrases that must NEVER reach a focus or recommendation
# (Defect 3 + Failure #3). Beth speaks in concrete actions, not these.
_BANNED_FOCUS = (
    "take the next step", "take the concrete next step", "take a step",
    "make progress", "work on your goal", "work on the goal", "advance your goal",
    "advance the goal", "take one step", "take your first action", "support your mission",
    "maintain consistency", "maintain momentum", "maintaining consistency",
    "maintaining your consistency", "keep consistency", "keeping your consistency",
    "keep your consistency", "lock in consistency", "lock in momentum",
    "stay consistent", "keep up the momentum", "keep the momentum going",
    "keep progressing", "keep moving forward", "steady momentum", "keep momentum",
    "maintain your momentum", "maintaining your momentum", "keep going",
    "keep it going", "keep it up", "just keep going", "momentum over time",
    # generic encouragement / motivation (parity with the acceptance evaluator's
    # COACHING_BANNED set — so scrubbing removes everything the gate flags).
    "do your best", "doing great", "stay focused", "you got this", "you've got this",
    "you're doing fine",
)


def _is_generic_action(s):
    l = (s or "").lower()
    return any(b in l for b in _BANNED_FOCUS)


def _scrub_coaching(text):
    """Strip generic-coaching clauses from echoed user/goal free-text so
    DETERMINISTIC goal narration never leaks banned phrases.

    Defect class: legacy generic coaching language (e.g. a user's own milestone
    description "Lock in consistency with protein…") leaking verbatim through
    deterministic narration. We remove the banned phrase plus a trailing connector
    and KEEP the substantive remainder ("Protein, hydration, workouts…"), so the
    answer still references concrete state/action. Returns cleaned text (possibly
    empty, in which case callers fall back to an honest 'no concrete step' line)."""
    if not text:
        return text
    original = str(text)
    if not _is_generic_action(original):
        return original                      # nothing banned — leave it byte-identical
    t = original
    for b in _BANNED_FOCUS:
        t = re.sub(r"\b" + re.escape(b) + r"\b[\s,;:.\-—]*(?:with|by|and|to|on|of|for)?\s*",
                   " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s+([.,;])", r"\1", t).strip(" .,;—-!?")
    if not re.search(r"[A-Za-z0-9]", t):   # only punctuation/whitespace left
        return ""
    t = re.sub(r"(^|[.;!?]\s+)([a-z])",
               lambda m: m.group(1) + m.group(2).upper(), t)
    if t[-1] not in ".!?":
        t += "."
    return t


def _concrete_or_honest_action(e, name=None):
    """The goal's concrete recommended action, or an HONEST 'no concrete step'
    statement — NEVER a generic placeholder (Defect 3)."""
    rec = _scrub_coaching((e or {}).get("recommended_action"))
    if rec and not _is_generic_action(rec):
        return rec
    return ("its current milestone has no defined next action yet — add one so "
            "there's a concrete thing to do today")


def _state_risk_concern(name, e, is_mission):
    """A state-appropriate concern for one goal, or None when no state is known.
    Returns (sev, concern, action, kind, state)."""
    spec = _GOAL_STATE_RISK.get((e or {}).get("state"))
    if not spec:
        return None
    sev, kind, phrase = spec
    lead = "your mission" if is_mission else "your goal"
    action = _concrete_or_honest_action(e, name)
    return (sev, f"{lead} '{name}' {phrase}", action, kind, (e or {}).get("state"))


def _rank_goal_concerns(goals, habits):
    """EVIDENCE-FIRST goal concerns as plain coaching language (never raw
    IDs/enums/scores/JSON). Beth narrates the nightly momentum engine's verdict
    rather than re-deriving progress from metadata. Severity:

        6 overdue (named, hard commitment) > 5 near-deadline (named, hard
        commitment) > 4 EVIDENCE-backed stall — a named goal the momentum engine
        shows is low/falling > 3 a named goal with NO evidence of progress AND no
        supporting habits (weak metadata signal) > 2 at-risk habit (named) > 1
        portfolio metric (anonymous, supplemental only).

    Healthy momentum SUPPRESSES the "no supporting habits" signal: a goal the
    engine shows progressing (e.g. weight loss / exercise) is never criticised for
    missing formal habits. Truth-first (P1): a goal is called stalled only when its
    canonical momentum evidence supports it; overdue/deadline stay verifiable.
    Returns ordered [{concern, action, kind, state}] — kind is "risk" or "watch",
    state is the goal's canonical state (or None for non-state concerns)."""
    out = []  # (severity, concern, action, kind, state)

    def add(sev, concern, action, kind="risk", state=None):
        out.append((sev, concern, action, kind, state))

    mission = goals.get("mission") if isinstance(goals.get("mission"), dict) else None
    mname = mission.get("title") if mission else None
    active = int(_num(goals.get("active_goal_count")) or 0)
    active_titles = goals.get("active_titles") or []
    me = _goal_evidence(mission) if mission else None

    # 60 — Overdue goals (named, most urgent — a hard commitment; state=failing).
    overdue_titles = [t for t in (goals.get("overdue_titles") or []) if t.get("title")]
    overdue = int(_num(goals.get("overdue_goal_count")) or 0) or len(overdue_titles)
    overdue_names = {t["title"] for t in overdue_titles}
    if overdue_titles:
        name = overdue_titles[0]["title"]
        extra = f" (and {overdue - 1} other goal(s))" if overdue > 1 else ""
        add(60, f"'{name}' is past its target date{extra}",
            f"reschedule '{name}' with a realistic new milestone date, or close it out",
            "risk", "failing")
    elif overdue:
        add(60, f"{overdue} goal(s) are past their target date",
            "reschedule each with a realistic new date, or close them out",
            "risk", "failing")

    # 45 — Nearest deadline within a week (named); includes the mission's deadline.
    soon = None  # (days, title)
    for t in (goals.get("upcoming_titles") or []):
        d = _num(t.get("days_remaining"))
        if d is not None and (soon is None or d < soon[0]):
            soon = (d, t.get("title"))
    md = _num(mission.get("days_remaining")) if mission else None
    if md is not None and (soon is None or md < soon[0]):
        soon = (md, mname)
    if soon and soon[0] is not None and soon[0] <= 7:
        name = soon[1] or "a goal"
        add(45, f"'{name}' is due in {int(soon[0])} day(s)",
            f"schedule focused calendar time this week to move '{name}' forward", "risk")

    # 50–20 — STATE-BASED concern per goal (Task 2): drifting/stalled/failing are
    # real RISKS; stable/thriving are WATCH items (never crisis framing).
    seen_state = set()
    if mission and mname and mname not in overdue_names:
        c = _state_risk_concern(mname, me, True)
        if c:
            out.append(c)
            seen_state.add(mname)
    for t in active_titles:
        nm = t.get("title")
        e = _goal_evidence(t)
        if nm and nm not in overdue_names and nm not in seen_state:
            c = _state_risk_concern(nm, e, False)
            if c:
                out.append(c)
                seen_state.add(nm)

    # 35 — Genuinely UNSUPPORTED goal (Task 1): only when there is provably NO
    # milestone, NO momentum evidence, and NO habit — i.e. nothing to measure
    # progress against. Habit-gap language is suppressed in every other case.
    hactive = int(_num(habits.get("active_habit_count")) or 0)
    any_evidence = (bool(me and (me.get("momentum") or me.get("trend")))
                    or any(_goal_evidence(t) and
                           (_goal_evidence(t).get("momentum") or _goal_evidence(t).get("trend"))
                           for t in active_titles))
    any_healthy = _evidence_healthy(me) or any(
        _evidence_healthy(_goal_evidence(t)) for t in active_titles)
    any_milestones = bool((mission or {}).get("context", {}).get("has_milestones")) or any(
        (t.get("context") or {}).get("has_milestones") for t in active_titles)
    if active and not hactive and not any_evidence and not any_milestones:
        name = mname or _first_title(active_titles)
        label = (f"'{name}' has no milestones, habits, or tracked activity yet"
                 if name else "your active goals have no milestones, habits, or "
                 "tracked activity yet")
        add(35, f"{label} — there's nothing to measure progress against",
            "define your first milestone so there's a concrete next step", "risk")

    # 15 — At-risk habit (named) — a real near-term loss when habits exist.
    at_risk = [h for h in (habits.get("streaks_per_habit") or [])
               if h.get("at_risk") and h.get("name")]
    if at_risk:
        name = at_risk[0]["name"]
        extra = f" (and {len(at_risk) - 1} other(s))" if len(at_risk) > 1 else ""
        add(15, f"your habit '{name}' is about to break its streak{extra}",
            f"complete '{name}' today to protect the streak", "risk")

    # 10 — Portfolio metrics (ANONYMOUS) — supplemental; headline ONLY when nothing
    # above. Low milestone completion is SUPPRESSED when the engine shows healthy
    # momentum (a goal can progress in real life while its milestones lag).
    rate = _num(goals.get("completion_rate"))
    if rate is not None and rate < 0.4 and active and not any_healthy:
        add(10, "your overall goal completion is running low",
            "narrow your focus to one or two goals to lift it", "risk")
    hrate = _num(habits.get("avg_completion_rate"))
    if active >= 6 and hrate is not None and hrate < 0.5:
        add(10, f"you're carrying {active} active goals with thin follow-through",
            "pause the lowest-priority goals to protect your top ones", "risk")

    out.sort(key=lambda x: -x[0])
    return [{"concern": c, "action": a, "kind": k, "state": st}
            for _s, c, a, k, st in out]


def goals_working_memory(truth, user=None):
    """GoalsWorkingMemoryCurator — goals-truth ONLY and EXECUTIVE-CLEAN.

    Reads goals_state + habits_state. Model-facing output has NO internal IDs,
    enum codes, raw momentum scores, field names, or data-source paths — only
    counts, percentages, plain goal/mission titles, and ranked coaching concerns.
    """
    gs = truth.get("goals_state")
    goals = gs.get("state") if isinstance(gs, dict) else None
    goals = goals if isinstance(goals, dict) else {}
    hsr = truth.get("habits_state")
    habits = hsr.get("state") if isinstance(hsr, dict) else None
    habits = habits if isinstance(habits, dict) else {}

    facts = {}
    status = {}
    active = _num(goals.get("active_goal_count"))
    if active is not None:
        status["active_goals"] = int(active)
    rate = _num(goals.get("completion_rate"))
    if rate is not None:
        status["completion_pct"] = round(rate * 100)
    overdue = _num(goals.get("overdue_goal_count"))
    if overdue is not None:
        status["overdue_goals"] = int(overdue)
    dnext = _num(goals.get("days_to_next_deadline"))
    if dnext is not None:
        status["next_deadline_in_days"] = int(dnext)
    if status:
        facts["goal_status"] = status

    # Goal titles — NAMES only (drop target_date isoformat + is_foundational enum).
    names = [t.get("title") for t in (goals.get("active_titles") or [])
             if t.get("title")]
    if names:
        facts["active_goals"] = names[:10]

    # Mission — TITLE only (strip momentum snapshot scores / milestone internals).
    mission = goals.get("mission")
    if isinstance(mission, dict):
        mtitle = (mission.get("title") or mission.get("goal_title")
                  or mission.get("name"))
        if mtitle:
            facts["mission"] = mtitle

    # Per-goal EVIDENCE (the nightly momentum engine's verdict) translated into
    # coaching language. NEVER exposes raw scores, trend enums, or JSON keys —
    # only banded momentum words and the engine's user-safe driver labels.
    def _coach_evidence(name, e, context=None):
        # The Goal Evidence Narrative in coaching language — phase, what's working,
        # what to watch, momentum summary, the recommended next action, AND the
        # rich canonical context (why it matters, success definition, the active
        # milestone detail, what's next, the most recent win). NEVER exposes raw
        # scores, trend enums, IDs, field names, or JSON keys (root cause #2 fix:
        # goals reasoning no longer ignores this canonical context).
        e = e if isinstance(e, dict) else {}
        context = context if isinstance(context, dict) else {}
        if not name or (not e and not context):
            return None
        item = {"goal": name}
        if e.get("state"):
            item["state"] = e["state"]               # thriving/stable/drifting/…
        phase = e.get("phase") or context.get("current_phase")
        if phase:
            item["phase"] = phase
        if context.get("active_milestone_detail"):
            # User milestone descriptions are free-text and may contain generic
            # coaching ("lock in consistency…"). Scrub before Beth narrates/echoes.
            detail = _scrub_coaching(context["active_milestone_detail"])
            if detail:
                item["current_milestone_detail"] = detail
        nxt = [m for m in (context.get("next_milestones") or [])
               if isinstance(m, str) and m != phase]
        if nxt:
            item["next_milestones"] = nxt[:3]
        if context.get("recently_completed_milestone"):
            item["recently_completed"] = context["recently_completed_milestone"]
        why = _scrub_coaching(context.get("why_it_matters"))
        if why:
            item["why_it_matters"] = why
        success = _scrub_coaching(context.get("success_definition"))
        if success:
            item["success_looks_like"] = success
        item["momentum"] = e.get("momentum_summary") or "in progress"
        succ = [s for s in (e.get("success_drivers") or []) if isinstance(s, str)]
        if succ:
            item["whats_working"] = succ[:3]
        risks = [s for s in (e.get("risk_drivers") or []) if isinstance(s, str)]
        if risks:
            item["watch"] = risks[:2]
        rec = _scrub_coaching(e.get("recommended_action"))
        if rec:
            item["recommended_action"] = rec
        return item

    evidence = []
    mev = _coach_evidence(mission.get("title") if isinstance(mission, dict) else None,
                          _goal_evidence(mission) if isinstance(mission, dict) else None,
                          mission.get("context") if isinstance(mission, dict) else None)
    if mev:
        evidence.append(mev)
    seen_names = {mev["goal"]} if mev else set()
    for t in (goals.get("active_titles") or []):
        nm = t.get("title")
        if nm and nm not in seen_names:
            ce = _coach_evidence(nm, _goal_evidence(t), t.get("context"))
            if ce:
                evidence.append(ce)
                seen_names.add(nm)
    if evidence:
        facts["goal_evidence"] = evidence[:6]

    # Habits — summarized consistency only.
    hb = {}
    hactive = _num(habits.get("active_habit_count"))
    if hactive is not None:
        hb["active_habits"] = int(hactive)
    hrate = _num(habits.get("avg_completion_rate"))
    if hrate is not None:
        hb["consistency_pct"] = round(hrate * 100)
    longest = _num(habits.get("longest_streak"))
    if longest is not None:
        hb["longest_streak_days"] = int(longest)
    if hb:
        facts["habits"] = hb

    ranked = _rank_goal_concerns(goals, habits)
    if ranked:
        facts["ranked_concerns"] = ranked
    return facts


def _goal_risk_fallback(wm):
    # biggest_goal_risk (Defect 1): a stable/thriving goal is a WATCH item, never a
    # "risk". Surface the worst REAL risk (drifting/stalled/failing/overdue/etc.);
    # if every goal is healthy, say so and give the watch item.
    ranked = (wm.get("facts") or {}).get("ranked_concerns") or []
    if not ranked:
        return ("No significant goal risks right now — nothing is overdue, drifting, "
                "or stalled.")
    real = [c for c in ranked if c.get("kind") == "risk"]
    if real:
        top = real[0]
        return ("The biggest risk to your goals right now: " + top.get("concern", "")
                + ". A good next step: " + top.get("action", "address it today") + ".")
    # All goals healthy — watch item, not a risk. (Capitalize only the first
    # letter; never lowercase the rest — that would mangle the goal name.)
    top = ranked[0]
    concern = top.get("concern", "")
    concern = concern[:1].upper() + concern[1:]
    return ("No significant risks right now. " + concern
            + ". A good next step: "
            + top.get("action", "take the next concrete action on its current milestone") + ".")


def _goals_progress_fallback(wm):
    # goals_progress (GOLD): lead with the headline goal — phase + momentum + what's
    # working + the next milestone — and END with today's concrete lever. A status
    # READ, distinct from the on-track verdict and the confidence assessment.
    f = wm.get("facts") or {}
    st = f.get("goal_status") or {}
    ev = f.get("goal_evidence") or []
    ranked = f.get("ranked_concerns") or []
    if not ev:
        parts = []
        if st.get("active_goals") is not None:
            parts.append(f"You have {st['active_goals']} active goal(s).")
        if st.get("completion_pct") is not None:
            parts.append(f"Milestone completion is around {st['completion_pct']}%.")
        if ranked:
            parts.append(f"The main thing to nudge next: {ranked[0].get('concern')}.")
        return (" ".join(parts) or
                "I don't have enough recent progress data to summarize your goals yet.")
    item = ev[0]
    name = item.get("goal")
    s = f"'{name}'"
    if item.get("phase"):
        s += f" is in its {item['phase']} and"
    s += f" showing {item.get('momentum', 'progress')}"
    work = [d for d in (item.get("whats_working") or []) if isinstance(d, str)]
    if work:
        s += f" — {', '.join(work[:2])}"
    parts = [s + "."]
    nxt = [m for m in (item.get("next_milestones") or []) if isinstance(m, str)]
    if nxt:
        parts.append(f"The next milestone is {nxt[0]}.")
    elif item.get("recently_completed"):
        parts.append(f"You recently cleared \"{item['recently_completed']}\".")
    parts.append(f"Today's lever: {_concrete_action(item)}.")
    return " ".join(parts)


def _goal_concerns_fallback(wm):
    # goal_concerns / "which goals are slipping" (Defect 2): ONLY goals whose state
    # is drifting/stalled/failing. thriving/stable goals NEVER appear here.
    ranked = (wm.get("facts") or {}).get("ranked_concerns") or []
    slipping = [c for c in ranked if c.get("state") in ("drifting", "stalled", "failing")]
    if not slipping:
        return ("None of your active goals appear to be slipping right now. All "
                "active goals are on pace or ahead. The next thing to watch is your "
                "nearest upcoming milestone.")
    lines = ["Here's what's slipping right now, most important first:"]
    for i, c in enumerate(slipping[:4], 1):
        lines.append(f"{i}. {c.get('concern', '')} — {c.get('action', 'address it today')}.")
    return "\n".join(lines)


# INV-5 / Rule 3: map a goal concern to a CONCRETE, domain-aware action doable
# within 24h — tied to the detected risk, NEVER generic ("take one step", "work
# on the goal", "make progress today"). Used only when a concern carries no
# pre-attached action (the ranking already attaches a domain-aware action).
def _goal_concrete_today_action(concern):
    c = (concern or "").lower()
    if "past its target" in c or "past their target" in c or "overdue" in c:
        return "reschedule it with a realistic new milestone date, or close it out"
    if "due in" in c:
        return "schedule focused calendar time this week to move it forward"
    if "losing momentum" in c or "low momentum" in c or "stalled" in c \
            or "drifting" in c or "execution has dropped" in c:
        return "complete today's scheduled workout to rebuild momentum"
    if "no active next milestone" in c:
        return "define its next milestone so it has a clear next step"
    if "no milestones" in c or "nothing to measure" in c:
        return "define your first milestone so there's a concrete next step"
    if "streak" in c:
        return "complete the habit today to protect the streak"
    if "completion is running low" in c:
        return "narrow your focus to one or two goals to lift it"
    if "thin follow-through" in c:
        return "pause the lowest-priority goals to protect your top ones"
    # Honest — never a generic placeholder verb (Defect 3).
    return ("its current milestone has no defined next action yet — add one so "
            "there's a concrete thing to do today")


def _goals_focus_today_fallback(wm):
    # goals_focus_today: (1) one specific goal, (2) why today, (3) ONE concrete
    # 24h action. Evidence-first — uses the goal's narrative recommended action,
    # never a generic/portfolio line when evidence exists.
    facts = wm.get("facts") or {}
    ranked = facts.get("ranked_concerns") or []
    ev = facts.get("goal_evidence") or []
    if ranked:
        top = ranked[0]
        focus = top.get("concern", "your top goal")
        action = top.get("action")
        if not action or _is_generic_action(action):
            action = _goal_concrete_today_action(focus)
        return (f"Today, focus on {focus}. The single highest-leverage move: "
                f"{action}.")
    # No risk concern — narrate the top goal's evidence and give its recommended
    # next action (tied to actual drivers / phase). Never generic (Defect 3).
    if ev:
        item = ev[0]
        name = item.get("goal")
        action = item.get("recommended_action")
        if name and action and not _is_generic_action(action):
            phase = f" ({item['phase']})" if item.get("phase") else ""
            mom = item.get("momentum") or "it's progressing"
            return (f"Today, focus on '{name}'{phase}. {mom.capitalize()} — keep "
                    f"that going. The single highest-leverage move: {action}.")
    name = facts.get("mission")
    if not name:
        ag = facts.get("active_goals") or []
        name = ag[0] if ag else None
    if name:
        return (f"Today's focus is '{name}', but its current milestone has no defined "
                f"next action yet — add one so there's a concrete thing to do today.")
    return ("You don't have an active goal set yet. Create one specific goal today "
            "so there's something concrete to drive toward.")


# ---------------------------------------------------------------------------
# Differentiated goal intents — six distinct questions, six distinct answers.
# Each fallback consumes the FOCAL goal's curated evidence (mission first).
# ---------------------------------------------------------------------------
def _focal_goal(wm):
    ev = (wm.get("facts") or {}).get("goal_evidence") or []
    return ev[0] if ev else None


def _concrete_action(item):
    a = _scrub_coaching((item or {}).get("recommended_action"))
    if a and not _is_generic_action(a):
        return a
    return ("its current milestone has no defined next action yet — add one so "
            "there's a concrete thing to do today")


def _goal_on_track_fallback(wm):
    # Trajectory assessment: yes/no + evidence + why. DISTINCT from progress.
    item = _focal_goal(wm)
    if not item:
        return ("I don't have an active goal with enough recent data to judge your "
                "trajectory yet.")
    name = item.get("goal")
    state = item.get("state")
    verdict = {
        "thriving": f"Yes — you're on track for '{name}', and then some",
        "stable": f"Yes — you're on track for '{name}'",
        "drifting": f"You're roughly on track for '{name}', but starting to slip",
        "stalled": f"Not right now — '{name}' has lost pace",
        "failing": f"No — '{name}' is off track",
    }.get(state, f"It's hard to say yet for '{name}'")
    parts = [verdict + "."]
    work = [w for w in (item.get("whats_working") or []) if isinstance(w, str)]
    if work:
        parts.append(f"The evidence: {', '.join(work[:2])}.")
    why = {
        "thriving": "Momentum and milestone progress are both moving the right way.",
        "stable": "Your momentum is steady and milestones are advancing.",
        "drifting": "Recent execution has dipped, so it needs attention to hold pace.",
        "stalled": "Progress has flattened — it needs a restart to get back on pace.",
        "failing": "Momentum has dropped and the timeline is at risk without a reset.",
    }.get(state, "")
    if why:
        parts.append(why)
    parts.append(f"Next move: {_concrete_action(item)}.")
    return " ".join(parts)


def _goal_why_priority_fallback(wm):
    # Strategic rationale — why_it_matters / success. NO counts/deadlines/portfolio.
    item = _focal_goal(wm)
    if not item:
        return ("I don't have a primary goal recorded for you yet — set one as your "
                "mission and tell me why it matters, and I'll reflect it back.")
    name = item.get("goal")
    why = item.get("why_it_matters")
    succ = item.get("success_looks_like")
    parts = [f"'{name}' is your priority because of what it means to you, not because "
             f"of where it sits on a list."]
    if why:
        parts.append(why)
    if succ:
        parts.append(f"Success looks like: {succ}")
    if not why and not succ:
        parts.append("You've set it as your primary mission — the goal you've chosen "
                     "to organize your effort around. Add a note on why it matters and "
                     "I can speak to it more fully.")
    return " ".join(parts)


def _goal_next_milestone_fallback(wm):
    # ONLY the active + next milestone and its detail. No other goals/portfolio.
    item = _focal_goal(wm)
    if not item:
        return ("I don't have a goal with milestones recorded yet — add one to set a "
                "concrete next target.")
    name = item.get("goal")
    phase = item.get("phase")
    detail = _scrub_coaching(item.get("current_milestone_detail"))
    nxt = [m for m in (item.get("next_milestones") or []) if isinstance(m, str)]
    parts = []
    if phase:
        s = f"Your current milestone for '{name}' is \"{phase}\""
        if detail:
            s += f" — {detail}"
        parts.append(s + ".")
    if nxt:
        parts.append(f"After that, the next milestone is \"{nxt[0]}\".")
    if not phase and not nxt:
        parts.append(f"'{name}' has no active milestone defined yet — adding one would "
                     f"give you a concrete next target to work toward.")
    return " ".join(parts)


_FITNESS_FAILURE_MODES = (
    "losing workout consistency", "missing scheduled sessions",
    "nutrition slipping off plan", "momentum fading if the routine lapses",
    "abandoning the daily habits that drive it",
)


def _goal_failure_modes_fallback(wm):
    # Failure analysis — what could cause it to fail. DISTINCT from progress.
    item = _focal_goal(wm)
    if not item:
        return ("I don't have enough on this goal to map its failure modes yet.")
    name = item.get("goal")
    modes = []
    for r in (item.get("watch") or []):
        if isinstance(r, str):
            modes.append(r)
    for m in _FITNESS_FAILURE_MODES:
        if m not in modes:
            modes.append(m)
    lines = [f"The most likely ways '{name}' could fail:"]
    for i, m in enumerate(modes[:5], 1):
        lines.append(f"{i}. {m}")
    lines.append(f"The single best guard against them today: {_concrete_action(item)}.")
    return "\n".join(lines)


def _goal_confidence_fallback(wm):
    # Confidence assessment — level + evidence + strengths + risks. DISTINCT.
    item = _focal_goal(wm)
    if not item:
        return ("I don't have enough recent evidence to give you a confidence read "
                "on this goal yet.")
    name = item.get("goal")
    state = item.get("state")
    level = {
        "thriving": "high", "stable": "solid", "drifting": "moderate",
        "stalled": "low-to-moderate", "failing": "low",
    }.get(state, "uncertain")
    parts = [f"My confidence that you'll achieve '{name}' is {level} right now."]
    strengths = [w for w in (item.get("whats_working") or []) if isinstance(w, str)]
    risks = [r for r in (item.get("watch") or []) if isinstance(r, str)]
    if strengths:
        parts.append(f"Strengths: {', '.join(strengths[:2])}.")
    if risks:
        parts.append(f"Risks: {', '.join(risks[:2])}.")
    elif state in ("thriving", "stable"):
        parts.append("No significant risks are showing up in the evidence.")
    parts.append(f"What would raise it: {_concrete_action(item)}.")
    return " ".join(parts)


_GOAL_GUIDANCE = (
    " Stay strictly within goals and habits — never mention health metrics, "
    "finances, labs, or unrelated domains. Cite the data; never invent goals, "
    "numbers, or deadlines."
    " LANGUAGE: translate everything into plain executive coaching language. "
    "NEVER output raw IDs, internal codes, enum values, raw momentum scores, "
    "field names, or data-source paths (e.g. 'SAE.goals…', 'is_foundational', "
    "'frequency_type'). If you can't say it as a coach would, omit it."
    " TONE: be motivating but honest about slippage — name the slip plainly and "
    "give the next step. Never shaming, never alarmist. Prefer 'worth focusing "
    "on', 'a bit behind', 'a good next step would be'."
    " CONTEXT: when a goal's working memory includes 'phase', "
    "'current_milestone_detail', 'next_milestones', 'why_it_matters', or "
    "'success_looks_like', GROUND your narration and the next step in them — name "
    "the active milestone and recommend the next concrete behavior that advances "
    "it. If a goal already has milestones, NEVER give generic planning advice "
    "('plan the goal', 'outline next steps', 'take one step', 'make progress'); "
    "reserve those only for a goal that has no milestones yet."
    " PROHIBITED PHRASES (NEVER use these — they are generic motivational filler, "
    "not coaching): 'maintain momentum', 'maintain consistency', 'lock in "
    "consistency', 'stay consistent', 'keep progressing', 'keep moving forward', "
    "'steady momentum', 'keep the momentum going', 'keep it up', 'keep going', "
    "'stay focused', 'you've got this'. Instead, name a SPECIFIC, concrete behavior "
    "(e.g. 'complete today's scheduled workout', 'hit your protein target', 'walk 30 "
    "minutes after dinner', 'meal-prep lunch and dinner')."
)


# intent -> curator. All four implemented intents are health-scoped and share the
# same health curator; the per-intent DIFFERENTIATION lives in the reasoning
# profile + deterministic fallback, not the curated truth.
INTENT_CURATORS = {
    "biggest_health_risk": health_working_memory,
    "overall_progress": health_working_memory,
    "health_focus_today": health_working_memory,
    "health_concerns": health_working_memory,
    "biggest_goal_risk": goals_working_memory,
    "goals_progress": goals_working_memory,
    "goals_focus_today": goals_working_memory,
    "goal_concerns": goals_working_memory,
    "goal_on_track": goals_working_memory,
    "goal_why_priority": goals_working_memory,
    "goal_next_milestone": goals_working_memory,
    "goal_failure_modes": goals_working_memory,
    "goal_confidence": goals_working_memory,
}


def build_working_memory(plan, truth, user=None):
    """Stage 3: curate the truth into bounded, inspectable working memory via the
    intent's curator. This is the ONLY data the reasoning model sees — never raw
    SAE, and for health intents never cross-domain truth."""
    curator = INTENT_CURATORS.get(plan.intent, _generic_curator)
    facts = curator(truth, user)
    wm = {"intent": plan.intent, "reasoning_style": plan.reasoning_style,
          "urgency": plan.urgency, "facts": facts}
    logger.info(
        "COS_REASONING_WORKING_MEMORY intent=%s curator=%s keys=%s bytes=%d payload=%s",
        plan.intent, curator.__name__, ",".join(facts.keys()) or "none",
        len(json.dumps(wm, default=str)),
        json.dumps(wm, default=str)[:1500],
    )
    return wm


# ----------------------------------------------------------------------------
# Stage 4 — OpenAI reasoning over working memory (one plain _call_api + fallback)
# ----------------------------------------------------------------------------
def _health_risk_fallback(wm):
    # biggest_health_risk: concern + (coaching) explanation + recommended action.
    ranked = (wm.get("facts") or {}).get("ranked_concerns") or []
    if not ranked:
        return ("Your health metrics look steady right now — nothing stands out "
                "as a concern. Keep doing what's working.")
    top = ranked[0]
    return ("The main thing worth your attention right now: "
            + top.get("concern", "")
            + ". A good next step: " + top.get("action", "take the next concrete action on its current milestone") + ".")


def _health_progress_fallback(wm):
    # overall_progress: weight trend + glucose status + sleep status + next focus.
    f = wm.get("facts") or {}
    cs = f.get("current_status") or {}
    tr = f.get("trends") or {}
    gp = f.get("goal_progress") or {}
    ranked = f.get("ranked_concerns") or []
    parts = []
    w = _num(cs.get("weight_current"))
    if w is not None:
        s = f"Your weight is {w} {cs.get('weight_unit', 'lb')}"
        if tr.get("weight_trend"):
            s += f" and {tr['weight_trend']}"
        rem = _num(gp.get("weight_goal_remaining"))
        if rem is not None:
            s += f", about {rem} from your goal"
        parts.append(s + ".")
    glu = _num(cs.get("latest_glucose"))
    if glu is not None:
        tag = "in a good range" if glu < 140 else "running a little high"
        parts.append(f"Glucose is around {glu} {cs.get('latest_glucose_unit', 'mg/dL')} ({tag}).")
    sl = _num(cs.get("sleep_avg_hours_7d"))
    if sl is not None:
        tag = "solid" if sl >= 7 else "a bit short"
        parts.append(f"Sleep is averaging {sl} hours ({tag}).")
    if ranked:
        parts.append(f"The main thing to nudge next: {ranked[0].get('concern')}.")
    if not parts:
        return ("I have your health profile but not enough recent data to "
                "summarize your progress yet.")
    return " ".join(parts)


def _health_concerns_fallback(wm):
    # health_concerns: a RANKED LIST (≥2 when available), each concern + action.
    ranked = (wm.get("facts") or {}).get("ranked_concerns") or []
    if not ranked:
        return ("Your health metrics look steady right now — nothing stands out "
                "as a concern. Keep doing what's working.")
    lines = ["Here's what's on your health radar right now, most important first:"]
    for i, c in enumerate(ranked[:4], 1):
        lines.append(f"{i}. {c.get('concern', '')} — {c.get('action', 'stay consistent')}.")
    return "\n".join(lines)


# INV-5: map the top concern to a CONCRETE imperative the user can do in 24h.
# Never vague ("work on nutrition"); always a specific, completable action.
def _concrete_today_action(concern, phase):
    c = (concern or "").lower()
    after = "after dinner tonight" if phase == "evening" else "after your biggest meal today"
    if "blood sugar" in c or "glucose" in c:
        return f"take a 15–20 minute walk {after}"
    if "sleep" in c:
        return "protect a consistent bedtime tonight — set a wind-down reminder 30 minutes before"
    if "weight-loss pace" in c or "pace" in c:
        return "log everything you eat today and keep your portions steady"
    if "protein" in c:
        return "make your next meal protein-forward — aim for about 30g"
    if "calorie" in c:
        return "plan one balanced meal to close today's gap"
    if "stalling" in c or "plateau" in c:
        return "add a 20-minute walk or one short strength set today"
    if "muscle" in c:
        return "get a protein-rich meal and a short strength set in today"
    return "take one 20-minute walk today"


def _health_focus_today_fallback(wm):
    # health_focus_today: (1) today's focus, (2) why today, (3) ONE concrete 24h
    # action (INV-5). Time-aware via nutrition_context.day_phase.
    f = wm.get("facts") or {}
    ranked = f.get("ranked_concerns") or []
    phase = ((f.get("nutrition_context") or {}).get("day_phase")) or "today"
    if not ranked:
        return ("Today, keep your healthy routine steady — nothing urgent stands "
                "out. It keeps your momentum going. One concrete step: take a "
                "20-minute walk today.")
    top = ranked[0]
    focus = top.get("concern", "your health")
    action = _concrete_today_action(focus, phase)
    return (f"Today, focus on {focus}. Acting on it today keeps it from "
            f"compounding and protects your momentum. One concrete step: "
            f"{action}.")


_HEALTH_GUIDANCE = (
    " Stay strictly within health — never mention tasks, projects, work items, "
    "Harley, finances, or generic to-dos. Cite the data; never invent numbers."
    " LANGUAGE: translate everything into plain executive coaching language. "
    "NEVER output raw labels, internal codes, enum values, field names, or data-"
    "source paths (e.g. 'MED', 'LOW', 'INSUFFICIENT_DATA', 'SAE.health…', "
    "'early_day_not_yet_logged'). If you can't say it as a coach would, omit it."
    " TONE: be evidence-based and measured. Avoid alarmist language — 'significant"
    " risk', 'critical', 'dangerous', 'muscle loss risk' — unless the data clearly"
    " supports that severity. Prefer 'worth watching', 'below target', 'could "
    "affect progress if it continues', 'a good next step would be', or 'the main "
    "thing to improve today is'."
    " NUTRITION: read nutrition_context with TIME AWARENESS — when its "
    "interpretation is 'early_day_not_yet_logged' or 'logging_in_progress', do NOT"
    " treat 0 calories/protein as a risk or deficit (it is simply early in the "
    "day). Only call out a nutrition gap when the interpretation shows a late-day "
    "shortfall or a sustained trend below the 7-day typical."
)

REASONING_PROFILES = {
    "biggest_health_risk": {
        "system": (
            "You are the user's Chief of Staff. 'ranked_concerns' is an ordered "
            "list of {concern, action} in plain coaching language (highest "
            "priority first), already excluding normal values like an early-day 0 "
            "protein. Use the TOP entry: state its concern, briefly explain why "
            "it matters, and give its action. If ranked_concerns is absent or "
            "empty, say nothing stands out right now — do NOT manufacture one or "
            "default to nutrition." + _HEALTH_GUIDANCE + " Max 120 words."
        ),
        "max_tokens": 200,
        "fallback": _health_risk_fallback,
    },
    "overall_progress": {
        "system": (
            "You are the user's Chief of Staff. Using ONLY the health working "
            "memory provided, give a balanced read on how the user is doing "
            "against their HEALTH goals — what's going well and what to improve."
            + _HEALTH_GUIDANCE + " Max 160 words."
        ),
        "max_tokens": 260,
        "fallback": _health_progress_fallback,
    },
    "health_concerns": {
        "system": (
            "You are the user's Chief of Staff. 'ranked_concerns' is an ordered "
            "list of {concern, action} (highest priority first). List the CURRENT "
            "health concerns — up to 4 — most important first, each as a brief "
            "'concern — why/what to do'. This is a SURVEY (a list), not a single "
            "headline: if two or more concerns exist, give two or more. If "
            "ranked_concerns is absent or empty, say nothing stands out right now "
            "— do NOT manufacture concerns." + _HEALTH_GUIDANCE + " Max 150 words."
        ),
        "max_tokens": 240,
        "fallback": _health_concerns_fallback,
    },
    "health_focus_today": {
        "system": (
            "You are the user's Chief of Staff. Give the user ONE thing to focus "
            "on TODAY, derived from the TOP entry of 'ranked_concerns'. Output "
            "exactly three parts: (1) today's focus, (2) one sentence on why it "
            "matters today, (3) ONE specific action they can COMPLETE within 24 "
            "hours. The action MUST be concrete and doable — e.g. 'take a "
            "20-minute walk after dinner', 'have a 30g-protein breakfast', "
            "'protect a 10:30 PM bedtime tonight'. NEVER vague ('keep improving "
            "sleep', 'work on nutrition', 'stay active'). Be time-aware using "
            "nutrition_context.day_phase. If no concerns exist, give one simple, "
            "concrete healthy action for today." + _HEALTH_GUIDANCE + " Max 90 words."
        ),
        "max_tokens": 180,
        "fallback": _health_focus_today_fallback,
    },
    # ----- GOALS domain (#2) -----
    "biggest_goal_risk": {
        "system": (
            "You are the user's Chief of Staff. 'ranked_concerns' is an ordered "
            "list of {concern, action} in plain coaching language (most at-risk "
            "first). Use the TOP entry: state the goal most at risk, briefly "
            "explain why it matters, and give its action. If ranked_concerns is "
            "absent or empty, say the goals look on track — do NOT manufacture a "
            "risk." + _GOAL_GUIDANCE + " Max 120 words."
        ),
        "max_tokens": 200,
        "fallback": _goal_risk_fallback,
    },
    "goals_progress": {
        "system": (
            "You are the user's Chief of Staff. Using ONLY the goals working "
            "memory provided, give a balanced executive read on how the user is "
            "tracking against their GOALS — active goals, completion, deadlines, "
            "mission, and habit follow-through. A summary, not a single risk or a "
            "bare list." + _GOAL_GUIDANCE + " Max 160 words."
        ),
        "max_tokens": 260,
        "fallback": _goals_progress_fallback,
    },
    "goal_concerns": {
        "system": (
            "You are the user's Chief of Staff. 'ranked_concerns' is an ordered "
            "list of {concern, action} (most important first). List the CURRENT "
            "goal/habit concerns — up to 4 — most important first, each as a brief "
            "'concern — what to do'. This is a SURVEY (a list), not one headline: "
            "if two or more concerns exist, give two or more. If ranked_concerns "
            "is empty, say nothing stands out." + _GOAL_GUIDANCE + " Max 150 words."
        ),
        "max_tokens": 240,
        "fallback": _goal_concerns_fallback,
    },
    "goals_focus_today": {
        "system": (
            "You are the user's Chief of Staff. Give the user ONE goal-related "
            "thing to focus on TODAY, derived from the TOP entry of "
            "'ranked_concerns'. Output exactly three parts: (1) today's focus, "
            "(2) one sentence on why it matters today, (3) ONE specific action "
            "they can COMPLETE within 24 hours (e.g. 'spend 30 focused minutes on "
            "goal X', 'set a new milestone date for your overdue goal'). NEVER "
            "vague ('work on your goals', 'make progress'). If no concerns exist, "
            "give one simple concrete step on their top goal." + _GOAL_GUIDANCE +
            " Max 90 words."
        ),
        "max_tokens": 180,
        "fallback": _goals_focus_today_fallback,
    },
    "goal_on_track": {
        "system": (
            "You are the user's Chief of Staff. Answer ONLY the trajectory question "
            "for the FOCAL goal (goal_evidence[0]): are they on track? Lead with a "
            "clear yes / roughly / no, then the EVIDENCE (whats_working, momentum, "
            "state) and WHY, then the concrete next move (recommended_action). This "
            "is a verdict, NOT a progress summary and NOT a portfolio overview."
            + _GOAL_GUIDANCE + " Max 110 words."
        ),
        "max_tokens": 200,
        "fallback": _goal_on_track_fallback,
    },
    "goal_why_priority": {
        "system": (
            "You are the user's Chief of Staff. Explain the STRATEGIC RATIONALE for "
            "why this goal is the user's priority, using ONLY why_it_matters and "
            "success_looks_like (the user's own words about meaning, family, health, "
            "values, future impact). Do NOT mention active goal counts, deadlines, "
            "completion %, momentum scores, or any portfolio summary. End on the "
            "MEANING — do NOT pivot into a coaching action or a next step; this "
            "answer should usually contain no recommendation at all." + _GOAL_GUIDANCE
            + " Max 120 words."
        ),
        "max_tokens": 200,
        "fallback": _goal_why_priority_fallback,
    },
    "goal_next_milestone": {
        "system": (
            "You are the user's Chief of Staff. Return ONLY the current active "
            "milestone (phase) and its detail, plus the next milestone if known. Do "
            "NOT discuss other goals, momentum, the portfolio, or progress %. Just "
            "the milestone(s)." + _GOAL_GUIDANCE + " Max 90 words."
        ),
        "max_tokens": 160,
        "fallback": _goal_next_milestone_fallback,
    },
    "goal_failure_modes": {
        "system": (
            "You are the user's Chief of Staff. Give a FAILURE ANALYSIS for the "
            "focal goal: the specific ways it could fail (from 'watch' risk drivers "
            "plus the obvious execution risks — inconsistency, missed workouts, "
            "nutrition slipping, lost momentum, abandoned routines), then the single "
            "best guard today (recommended_action). This is a risk-of-failure list, "
            "NOT a progress summary." + _GOAL_GUIDANCE + " Max 130 words."
        ),
        "max_tokens": 220,
        "fallback": _goal_failure_modes_fallback,
    },
    "goal_confidence": {
        "system": (
            "You are the user's Chief of Staff. Give a CONFIDENCE ASSESSMENT for the "
            "focal goal: a clear confidence level (high/solid/moderate/low) grounded "
            "in the evidence, then strengths (whats_working) and risks (watch), then "
            "what would raise it (recommended_action). This is a confidence verdict, "
            "NOT a progress summary." + _GOAL_GUIDANCE + " Max 120 words."
        ),
        "max_tokens": 200,
        "fallback": _goal_confidence_fallback,
    },
}


def run_reasoning(user, message, plan, working_memory):
    """Stage 4: one plain _call_api over the working memory, with a deterministic
    truth-based fallback so the user always gets an authoritative answer."""
    from apps.ai.services import ai_service
    profile = REASONING_PROFILES[plan.intent]
    user_prompt = (
        f"Question: {message}\n\n"
        f"Working memory (the ONLY facts you may use):\n"
        f"{json.dumps(working_memory, default=str)}"
    )
    logger.info(
        "COS_REASONING_PROMPT user=%s intent=%s prompt_chars=%d",
        getattr(user, "id", None), plan.intent, len(user_prompt),
    )
    answer = None
    try:
        answer = ai_service._call_api(
            profile["system"], user_prompt,
            max_tokens=profile["max_tokens"], temperature=0.4,
            endpoint="cos_chat", user=user,
        )
    except Exception:
        logger.warning("COS_REASONING_LLM_FAILED user=%s intent=%s",
                       getattr(user, "id", None), plan.intent, exc_info=True)
        answer = None
    answer = (answer or "").strip()
    used_fallback = not answer
    if used_fallback:
        answer = profile["fallback"](working_memory)

    # SYSTEMIC GUARD (ALL reasoning intents — goals AND health): the LLM must not
    # leak prohibited momentum/consistency coaching, and certain intents must
    # contain their required tokens. If the LLM answer violates either, replace it
    # with the clean deterministic fallback (proven to pass the acceptance gates).
    # This eliminates the whole "legacy coaching language" defect class regardless
    # of domain or what the model phrases (P: health LLM narration was previously
    # unguarded and leaked "keep momentum").
    if not used_fallback:
        violation = _answer_violation(plan.intent, answer)
        if violation:
            logger.info("COS_REASONING_GUARD user=%s intent=%s reason=%s",
                        getattr(user, "id", None), plan.intent, violation)
            answer = profile["fallback"](working_memory)
            used_fallback = True

    logger.info(
        "COS_REASONING_RESPONSE user=%s intent=%s fallback=%s answer_len=%d",
        getattr(user, "id", None), plan.intent, used_fallback, len(answer),
    )
    return answer, used_fallback


# Per-intent required tokens — the answer must contain at least one of each set.
_GOAL_REQUIRE_ANY = {
    "goal_concerns": ("slipping", "drifting", "stalled", "failing", "none"),
    "biggest_goal_risk": ("risk", "no significant"),
    "goal_on_track": ("on track", "on pace", "yes", "no"),
}


def _answer_violation(intent, answer):
    """Return a reason string if a reasoning answer (goal OR health) violates the
    banned-language or required-token rules, else None. The banned-language check
    applies to EVERY intent; the required-token check is intent-specific (only the
    intents present in _GOAL_REQUIRE_ANY)."""
    low = (answer or "").lower()
    for b in _BANNED_FOCUS:
        if b in low:
            return f"banned:{b}"
    req = _GOAL_REQUIRE_ANY.get(intent)
    if req and not any(r in low for r in req):
        return "missing_required_any"
    return None


# Backward-compatible alias (the guard now covers health too; same logic).
_goal_answer_violation = _answer_violation
