# ==============================================================================
# File: apps/ai/model_interface/understanding.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic Understanding (Truth's assessment tier) — whole-life scope
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
Deterministic Understanding — the assessment tier of the Truth pillar (whole-life scope).

Facts are what WLJ measures. Deterministic Understanding is what WLJ has already
deterministically *assessed those facts to mean* — primary challenge, biggest risk,
workload, cognitive load, executive & clinical priority, cross-domain patterns, wins,
opportunity, direction/goal pace, and what has materially changed. The conversational
model reasons FROM these; it never recomputes them. WLJ never reasons.

EXPOSE-DON'T-INVENT: every field here is EXISTING deterministic computation
(`interpret()`/`ExecutiveSignals`, `cos_intelligence`, `day_continuity`,
`StandingContextService`). No new assessments, no synthesis, no engine. We deliberately
expose only ASSESSMENTS (what things mean), NOT prescriptions/recommendations
(disposition, "batch them now", highest-leverage action verbs, composed prose) — those
are Reasoning and belong to the model.

OWNERSHIP / LIFECYCLE (Architecture Law — refresh cadence is an ownership boundary):
this interface owns its OWN cache and warm cadence (medium — minutes/hours), distinct
from Current Context (fast) and AI Relationship (slow). `interpret()` is heavy (~850ms)
and MUST NOT run on the request path:
  * warm(user)  — computes + caches (background/warming caller only).
  * read(user)  — CACHE-FIRST; returns the structured understanding or None (pending).
"""

import logging

from django.core.cache import cache

from apps.ai.cos_services.serialization import cap as _cap
from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

UNDERSTANDING_SCHEMA_VERSION = "1.0"
_TTL = 150
_MAX = 5


def _key(user_id):
    return f"wlj:mi:understanding:{user_id}"


def _compose(user):
    """Build the structured whole-life understanding from EXISTING deterministic
    computations. Heavy (interpret ~850ms). Never call on the request path."""
    out = {"schema_version": UNDERSTANDING_SCHEMA_VERSION, "status": "ok"}

    # --- interpret() → ExecutiveSignals (assessments only; NO prescriptions) ----
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import interpret
        s = interpret(user)
        out["executive"] = {
            "primary_challenge": getattr(s, "primary_challenge", None),
            "challenge_reason": getattr(s, "challenge_reason", None),
            "biggest_risk": getattr(s, "biggest_risk", None),
            "workload": getattr(s, "workload", None),
            "workload_summary": getattr(s, "workload_summary", None),
            "cognitive_load": getattr(s, "cognitive_load", None),
            "health_read": getattr(s, "health_read", None),
            "recovery_needed": bool(getattr(s, "recovery_needed", False)),
            "intervention_required": bool(getattr(s, "intervention_required", False)),
        }
        out["priority"] = {
            "executive": _jsonsafe(getattr(s, "priority_action", None)),
            "clinical": _jsonsafe(_cap(getattr(s, "health_critical", None) or [], _MAX)),
        }
        # patterns = cross-domain assessment (pattern + risks); keep observation, drop action
        patterns = []
        pat = getattr(s, "pattern", None)
        if isinstance(pat, dict) and pat.get("text"):
            patterns.append({"text": pat.get("text"), "basis": pat.get("basis")})
        for r in (getattr(s, "risks", None) or []):
            if isinstance(r, dict) and r.get("text"):
                patterns.append({"text": r.get("text"), "basis": r.get("basis"),
                                 "confidence": r.get("confidence")})
        out["patterns"] = _jsonsafe(_cap(patterns, _MAX))
        out["predictions"] = _jsonsafe(_cap(getattr(s, "predictions", None) or [], _MAX))
        out["wins"] = _jsonsafe(_cap(getattr(s, "wins", None) or [], _MAX))
        opp = getattr(s, "opportunity", None)
        if isinstance(opp, dict) and opp.get("text"):
            out["opportunity"] = {"text": opp.get("text"), "basis": opp.get("basis")}
        out["confidence"] = getattr(s, "confidence", None)
    except Exception:
        logger.warning("understanding: interpret failed user=%s",
                       getattr(user, "id", "?"), exc_info=True)

    # --- direction / momentum / goal pace (from the already-warm standing context) --
    try:
        from apps.ai.cos_services.standing_context import get_standing_context
        sc = get_standing_context(user)  # cache-first; warm
        if sc and sc.get("status") == "ready":
            ci = sc.get("cos_intelligence") or {}
            out["direction"] = {
                "goal_pace": _jsonsafe(ci.get("goal_pace")) if isinstance(ci, dict) else None,
                "momentum": _jsonsafe(sc.get("momentum")),
                "strategic_summary": sc.get("strategic_summary"),
            }
    except Exception:
        logger.warning("understanding: direction read failed", exc_info=True)

    # --- material changes / continuity (day_continuity assessment) ---------------
    try:
        from apps.ai.chatgpt_cos.day_continuity import assess
        d = assess(user)
        out["continuity"] = {
            "mode": getattr(d, "mode", None),
            "material_changes": _jsonsafe(getattr(d, "material_changes", None) or []),
        }
    except Exception:
        logger.warning("understanding: continuity failed", exc_info=True)

    return out


def warm(user):
    """Compute + cache the whole-life understanding. Background/warming only. Returns the
    payload or None. Never raises."""
    uid = getattr(user, "id", None)
    try:
        payload = _compose(user)
        cache.set(_key(uid), payload, _TTL)
        return payload
    except Exception:  # pragma: no cover - defensive
        logger.warning("understanding.warm failed user=%s", uid, exc_info=True)
        return None


def read(user):
    """Cache-first. Return the structured whole-life understanding, or a pending marker
    when cold (never live-computes; the warm cycle repopulates)."""
    try:
        payload = cache.get(_key(getattr(user, "id", None)))
    except Exception:  # pragma: no cover - defensive
        payload = None
    if not payload:
        return {"schema_version": UNDERSTANDING_SCHEMA_VERSION, "status": "pending"}
    return payload
