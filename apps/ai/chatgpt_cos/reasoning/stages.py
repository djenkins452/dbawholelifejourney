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
    "Rules: choose intent='biggest_risk' for risk/concern/what's-wrong questions; "
    "intent='overall_progress' for how-am-I-doing / on-track / overall-goals "
    "questions; intent='other' for anything else. NEVER invent truth keys outside "
    "the lists. NEVER write prose. NEVER answer the user. JSON only."
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


def retrieve_truth(user, plan):
    """Stage 2: fetch every planned truth key deterministically. Unknown keys
    are ignored (never fabricated); provider errors are captured, never raised."""
    keys = []
    for k in list(plan.required_truth) + list(plan.optional_truth):
        if k not in keys:
            keys.append(k)
    for d in plan.domains:
        dk = _DOMAIN_TRUTH.get(d)
        if dk and dk not in keys:
            keys.append(dk)

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
_WM_MAX_KEYS = 30
_HEALTH_WM_FIELDS = (
    "weight_current", "weight_unit", "weight_trend", "weight_goal",
    "weight_goal_remaining", "weight_goal_on_track", "latest_glucose",
    "latest_glucose_unit", "glucose_avg_7d", "glucose_variability_label",
    "bp_systolic", "bp_diastolic", "sleep_avg_hours_7d", "sleep_trend",
    "heart_rate_avg_7d", "latest_blood_oxygen",
)


def _curate_value(v):
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    if isinstance(v, list):
        return [_curate_value(x) for x in v[:_WM_MAX_LIST]]
    if isinstance(v, dict):
        return {k: vv for k, vv in list(v.items())[:8]
                if isinstance(vv, (int, float, str, bool)) or vv is None}
    return str(v)[:200]


def _curate_domain_state(data, whitelist=None):
    state = data.get("state") if isinstance(data, dict) else None
    if not isinstance(state, dict):
        return {"status": data.get("status") if isinstance(data, dict) else "unknown"}
    out = {}
    if whitelist:
        for k in whitelist:
            if k in state and state[k] is not None:
                out[k] = _curate_value(state[k])
    else:
        for k, v in state.items():
            if len(out) >= _WM_MAX_KEYS:
                break
            cv = _curate_value(v)
            if cv is not None and cv != [] and cv != {}:
                out[k] = cv
    return out


def _curate(key, data):
    if key in ("risk_decision", "execution_decision", "fix_decision"):
        pa = data.get("primary_action") if isinstance(data, dict) else None
        if isinstance(pa, dict):
            pa = pa.get("title") or pa.get("name") or pa
        return {
            "primary_action": pa,
            "reason": data.get("reason") if isinstance(data, dict) else None,
            "recommendation": data.get("message") if isinstance(data, dict) else None,
        }
    if key == "foundational_health":
        return data  # already scalar + tiny
    if key == "standing_context":
        return _curate_domain_state(data) if isinstance(data, dict) and "state" in data \
            else {k: _curate_value(v) for k, v in list((data or {}).items())[:_WM_MAX_KEYS]
                  if not k.startswith("_")}
    if key == "health_state":
        return _curate_domain_state(data, _HEALTH_WM_FIELDS)
    if key in ("goals_state", "fitness_state", "nutrition_state"):
        return _curate_domain_state(data)
    return _curate_value(data)


def build_working_memory(plan, truth):
    """Stage 3: curate the truth package into bounded, inspectable working
    memory. This is the ONLY data the reasoning model sees — never raw SAE."""
    wm = {"intent": plan.intent, "reasoning_style": plan.reasoning_style,
          "urgency": plan.urgency, "facts": {}}
    for key, data in truth.items():
        wm["facts"][key] = _curate(key, data)
    logger.info(
        "COS_REASONING_WORKING_MEMORY intent=%s keys=%s bytes=%d payload=%s",
        plan.intent, ",".join(wm["facts"].keys()) or "none",
        len(json.dumps(wm, default=str)),
        json.dumps(wm, default=str)[:1500],
    )
    return wm


# ----------------------------------------------------------------------------
# Stage 4 — OpenAI reasoning over working memory (one plain _call_api + fallback)
# ----------------------------------------------------------------------------
def _risk_fallback(wm):
    rd = (wm.get("facts") or {}).get("risk_decision") or {}
    return (rd.get("recommendation") or rd.get("reason")
            or "I don't see a single dominant risk in your current data right now.")


def _progress_fallback(wm):
    facts = wm.get("facts") or {}
    fh = facts.get("foundational_health") or {}
    bits = []
    w = fh.get("current_weight") if isinstance(fh, dict) else None
    if isinstance(w, dict) and w.get("value") is not None:
        bits.append(f"weight {w.get('value')} {w.get('unit', '')}".strip())
    sc = facts.get("standing_context") or {}
    focus = sc.get("recommended_focus") or sc.get("focus")
    if focus:
        bits.append(f"current focus: {focus}")
    ed = facts.get("execution_decision") or {}
    if ed.get("recommendation"):
        bits.append(ed["recommendation"])
    return ("Here's where things stand based on your current data — "
            + "; ".join(str(b) for b in bits) + ".") if bits else \
        "Here's where things stand based on your current data."


REASONING_PROFILES = {
    "biggest_risk": {
        "system": (
            "You are the user's Chief of Staff. Using ONLY the working memory "
            "provided, name the single biggest health risk right now and the one "
            "action to address it. Be direct and specific; cite the data. Never "
            "invent numbers or facts not in the working memory. Max 120 words."
        ),
        "max_tokens": 200,
        "fallback": _risk_fallback,
    },
    "overall_progress": {
        "system": (
            "You are the user's Chief of Staff. Using ONLY the working memory "
            "provided, give a balanced read on how the user is doing against "
            "their health goals — what's going well and what needs attention. "
            "Cite the data; never invent facts. Max 160 words."
        ),
        "max_tokens": 260,
        "fallback": _progress_fallback,
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
