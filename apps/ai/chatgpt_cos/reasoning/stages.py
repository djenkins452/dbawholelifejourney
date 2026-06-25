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
    "Rules: choose intent='biggest_health_risk' for health risk/concern/what's-"
    "wrong-with-my-health questions; intent='overall_progress' for how-am-I-doing "
    "/ on-track / overall-health-goals questions; intent='other' for anything "
    "else. BOTH implemented intents are HEALTH-scoped: for them, required_truth "
    "must be ONLY ['health_state','foundational_health'] and domains ONLY "
    "['health']. NEVER request risk_decision, execution_decision, tasks, or any "
    "non-health truth for a health intent. NEVER invent truth keys outside the "
    "lists. NEVER write prose. NEVER answer the user. JSON only."
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
    "fitness_state": lambda u: _domain(u, "fitness"),
    "nutrition_state": lambda u: _domain(u, "nutrition"),
}

# domain name -> the truth key used to fetch that domain's state
_DOMAIN_TRUTH = {
    "health": "health_state", "fitness": "fitness_state",
    "nutrition": "nutrition_state", "goals": "goals_state",
}

# Per-intent truth SCOPE. Health intents are restricted to health truth ONLY —
# the generic cross-domain decisions (risk_decision/execution_decision/...) and
# task/finance truth are dropped here so they never reach health reasoning,
# regardless of what the planner emits (defense-in-depth against contamination).
HEALTH_TRUTH = frozenset({"health_state", "foundational_health"})
HEALTH_INTENTS = ("biggest_health_risk", "overall_progress",
                  "health_focus_today", "health_concerns")
INTENT_TRUTH_SCOPE = {i: HEALTH_TRUTH for i in HEALTH_INTENTS}


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


def health_working_memory(truth):
    """HealthWorkingMemoryCurator — bounded, deterministic, health-truth ONLY."""
    hs = truth.get("health_state")
    state = hs.get("state") if isinstance(hs, dict) else None
    state = state if isinstance(state, dict) else {}
    fh = truth.get("foundational_health") or {}
    buckets = {
        "current_status": _pick(state, _H_STATUS),
        "major_trends": _pick(state, _H_TRENDS),
        "active_risks": _pick(state, _H_RISKS),
        "goal_progress": _pick(state, _H_GOALS),
    }
    pd = state.get("physical_decision")
    if isinstance(pd, dict):
        buckets["health_assessment"] = {
            k: pd[k] for k in list(pd)[:6]
            if isinstance(pd.get(k), (int, float, str, bool))
        }
    if isinstance(fh, dict) and fh:
        buckets["foundational_facts"] = fh
    return {k: v for k, v in buckets.items() if v}


def _generic_curator(truth):
    """Default curator for non-health intents (Phase 1 adds domain curators)."""
    return {key: _curate_value(data) for key, data in truth.items()}


# intent -> curator. Both implemented intents are health-scoped.
INTENT_CURATORS = {
    "biggest_health_risk": health_working_memory,
    "overall_progress": health_working_memory,
}


def build_working_memory(plan, truth):
    """Stage 3: curate the truth into bounded, inspectable working memory via the
    intent's curator. This is the ONLY data the reasoning model sees — never raw
    SAE, and for health intents never cross-domain truth."""
    curator = INTENT_CURATORS.get(plan.intent, _generic_curator)
    facts = curator(truth)
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
    risks = (wm.get("facts") or {}).get("active_risks") or {}
    flags = []
    if risks.get("weight_goal_on_track") is False:
        flags.append("you're behind on your weight goal")
    for k in ("plateau_risk_label", "muscle_loss_risk_level",
              "glucose_variability_label", "fat_loss_quality_label"):
        v = risks.get(k)
        if v and str(v).strip().lower() not in (
                "none", "stable", "low", "good", "on track", "optimal", "normal"):
            flags.append(f"{k.replace('_', ' ')}: {v}")
    if flags:
        return "From your health data, the main thing to watch: " + flags[0] + "."
    return "Your health metrics don't show a single dominant risk right now."


def _health_progress_fallback(wm):
    facts = wm.get("facts") or {}
    gp = facts.get("goal_progress") or {}
    st = facts.get("current_status") or {}
    bits = []
    if st.get("weight_current") is not None:
        bits.append(f"weight {st['weight_current']} {st.get('weight_unit', '')}".strip())
    if gp.get("weight_goal_remaining") is not None:
        bits.append(f"{gp['weight_goal_remaining']} to your goal")
    if gp.get("weight_goal_on_track") is not None:
        bits.append("on track" if gp["weight_goal_on_track"] else "behind on your goal")
    return ("On your health goals: " + "; ".join(str(b) for b in bits) + ".") \
        if bits else "Here's where your health goals stand based on your data."


_NO_CROSS_DOMAIN = (
    " Stay strictly within health — never mention tasks, projects, work items, "
    "Harley, finances, or generic to-dos. Cite the data; never invent numbers."
)

REASONING_PROFILES = {
    "biggest_health_risk": {
        "system": (
            "You are the user's Chief of Staff. Using ONLY the health working "
            "memory provided, name the single biggest HEALTH risk right now and "
            "the one action to address it." + _NO_CROSS_DOMAIN + " Max 120 words."
        ),
        "max_tokens": 200,
        "fallback": _health_risk_fallback,
    },
    "overall_progress": {
        "system": (
            "You are the user's Chief of Staff. Using ONLY the health working "
            "memory provided, give a balanced read on how the user is doing "
            "against their HEALTH goals — what's going well and what needs "
            "attention." + _NO_CROSS_DOMAIN + " Max 160 words."
        ),
        "max_tokens": 260,
        "fallback": _health_progress_fallback,
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
