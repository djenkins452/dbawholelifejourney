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
    "- 'goals_progress': an executive SUMMARY of goal progress/trajectory.\n"
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
                "goals_focus_today", "goal_concerns")
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
def _rank_goal_concerns(goals, habits):
    """Evidence-ranked goal/habit concerns as plain COACHING language (never raw
    IDs/enums/scores). Severity: overdue > near-deadline > at-risk habits > low
    completion > over-commitment. Returns ordered [{concern, action}]."""
    out = []  # (severity, concern, action)

    overdue = int(_num(goals.get("overdue_goal_count")) or 0)
    if overdue:
        titles = [t.get("title") for t in (goals.get("overdue_titles") or [])
                  if t.get("title")]
        names = ", ".join(f"'{t}'" for t in titles[:2])
        detail = f" ({names})" if names else ""
        out.append((5, f"you have {overdue} goal(s) past their target date{detail}",
                    "pick one and either set a realistic new date or close it out"))

    # Nearest upcoming deadline within a week.
    soon = None
    for t in (goals.get("upcoming_titles") or []):
        d = _num(t.get("days_remaining"))
        if d is not None and (soon is None or d < soon[0]):
            soon = (d, t.get("title"))
    if soon and soon[0] is not None and soon[0] <= 7:
        title = f"'{soon[1]}'" if soon[1] else "a goal"
        out.append((4, f"{title} is due in {int(soon[0])} day(s)",
                    "block focused time this week to move it forward"))

    # At-risk habits — the momentum that feeds goals.
    at_risk = [h for h in (habits.get("streaks_per_habit") or []) if h.get("at_risk")]
    if at_risk:
        names = ", ".join(f"'{h.get('name')}'" for h in at_risk[:2] if h.get("name"))
        detail = f" ({names})" if names else ""
        out.append((3, f"{len(at_risk)} habit(s) are about to break their streak{detail}",
                    "a quick completion today protects the streak and your momentum"))

    # Low overall goal completion.
    rate = _num(goals.get("completion_rate"))
    active = int(_num(goals.get("active_goal_count")) or 0)
    if rate is not None and rate < 0.4 and active:
        out.append((2, "your overall goal completion is running low",
                    "narrowing focus to one or two goals usually lifts it"))

    # Over-commitment: many active goals, thin habit follow-through.
    hrate = _num(habits.get("avg_completion_rate"))
    if active >= 6 and hrate is not None and hrate < 0.5:
        out.append((2, f"you're carrying {active} active goals with thin follow-through",
                    "consider pausing the lowest-priority ones to protect the top goals"))

    out.sort(key=lambda x: -x[0])
    return [{"concern": c, "action": a} for _s, c, a in out]


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
    # biggest_goal_risk: the SINGLE goal most at risk + why + action.
    ranked = (wm.get("facts") or {}).get("ranked_concerns") or []
    if not ranked:
        return ("Your goals look on track right now — nothing is overdue or "
                "stalling. Keep the momentum going.")
    top = ranked[0]
    return ("The goal most worth your attention right now: " + top.get("concern", "")
            + ". A good next step: " + top.get("action", "keep steady progress") + ".")


def _goals_progress_fallback(wm):
    # goals_progress: active goals + completion + deadline/overdue + mission + habits.
    f = wm.get("facts") or {}
    st = f.get("goal_status") or {}
    hb = f.get("habits") or {}
    ranked = f.get("ranked_concerns") or []
    parts = []
    active = st.get("active_goals")
    if active is not None:
        s = f"You have {active} active goal(s)"
        if st.get("completion_pct") is not None:
            s += f", about {st['completion_pct']}% of the way through their milestones"
        parts.append(s + ".")
    if st.get("overdue_goals"):
        parts.append(f"{st['overdue_goals']} are past their target date.")
    elif st.get("next_deadline_in_days") is not None:
        parts.append(f"Your next goal deadline is in {st['next_deadline_in_days']} day(s).")
    if f.get("mission"):
        parts.append(f"Your headline focus is \"{f['mission']}\".")
    if hb.get("consistency_pct") is not None:
        tag = "strong" if hb["consistency_pct"] >= 70 else "a bit uneven"
        parts.append(f"Habit follow-through is {tag} ({hb['consistency_pct']}%).")
    if ranked:
        parts.append(f"The main thing to nudge next: {ranked[0].get('concern')}.")
    if not parts:
        return ("I have your goals but not enough recent progress data to summarize "
                "your trajectory yet.")
    return " ".join(parts)


def _goal_concerns_fallback(wm):
    # goal_concerns: a RANKED LIST (≥2 when available), each concern + action.
    ranked = (wm.get("facts") or {}).get("ranked_concerns") or []
    if not ranked:
        return ("Your goals look healthy right now — nothing overdue or stalling. "
                "Keep doing what's working.")
    lines = ["Here's what's on your goals radar right now, most important first:"]
    for i, c in enumerate(ranked[:4], 1):
        lines.append(f"{i}. {c.get('concern', '')} — {c.get('action', 'stay consistent')}.")
    return "\n".join(lines)


# INV-5: map the top goal concern to a CONCRETE imperative doable within 24h.
def _goal_concrete_today_action(concern):
    c = (concern or "").lower()
    if "past their target" in c or "overdue" in c:
        return "open your top overdue goal and set one realistic new milestone date today"
    if "due in" in c:
        return "block 30 focused minutes on your nearest-deadline goal today"
    if "habit" in c and "streak" in c:
        return "complete your at-risk habit today to protect the streak"
    if "completion is running low" in c:
        return "pick your single most important goal and take one concrete step on it today"
    if "follow-through" in c:
        return "choose one goal to pause so you can fully focus on the top one today"
    return "spend 30 focused minutes moving your most important goal forward today"


def _goals_focus_today_fallback(wm):
    # goals_focus_today: (1) focus, (2) why today, (3) ONE concrete 24h action.
    ranked = (wm.get("facts") or {}).get("ranked_concerns") or []
    if not ranked:
        return ("Today, take one step on your most important goal — momentum "
                "compounds. One concrete step: spend 30 focused minutes moving "
                "your top goal forward today.")
    top = ranked[0]
    focus = top.get("concern", "your top goal")
    action = _goal_concrete_today_action(focus)
    return (f"Today, focus on {focus}. Acting on it today keeps it from slipping "
            f"further and protects your momentum. One concrete step: {action}.")


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
            + ". A good next step: " + top.get("action", "stay consistent") + ".")


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
    logger.info(
        "COS_REASONING_RESPONSE user=%s intent=%s fallback=%s answer_len=%d",
        getattr(user, "id", None), plan.intent, used_fallback, len(answer),
    )
    return answer, used_fallback
