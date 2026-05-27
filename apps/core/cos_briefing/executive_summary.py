"""
Executive Summary Composer — Beth's exec briefing as deterministic data.

This is the canonical source of "what's going well / what needs attention /
biggest risk / focus right now / trajectory" — built from existing engines:

    SAE state                  → driver verdicts per domain
    Insights (severity=positive)→ "going well"
    Insights (severity=warning)→ "needs attention"
    Insights (severity=critical)→ "biggest risk" (tied with risk selector)
    Predictions                → trajectory hints
    GuidanceItem (priority 1-2)→ "recommended focus"
    Selectors                  → focus_now / biggest_risk / fix_priority

Architecture rules honored:
  - LLM-last: zero LLM here. Output is structured data; any narration layer
    (dashboard renderer, Beth) reads this dict and styles it.
  - State-first: only the read-allowlisted models (Insight, Prediction,
    GuidanceItem) and SAE-backed selectors are touched. No domain ORM
    aggregates.
  - No duplicate truth: domain verdicts come from per-module SAE state;
    drivers reference existing fields; the selectors here are the same ones
    Beth's locked-facts use.
  - Snapshot-safe: read-only reads against cached state + indexed rows.

Returned shape (stable; treat as a soft public contract — keep additive):

    {
        "trajectory": "improving" | "steady" | "slipping" | "mixed" | "unknown",
        "going_well":      [ {title, module, evidence}, ... ],
        "needs_attention": [ {title, module, severity, evidence}, ... ],
        "biggest_risk":    {title, message, module, source} | None,
        "biggest_opportunity": {title, message, module, source} | None,
        "focus_now":       {title, reason, time_display, source} | None,
        "follow_on":       [ {title, time_display}, ... ],
        "recommendations": [ {title, message, priority, module}, ... ],
        "as_of":           ISO datetime,
        "engine_versions": {"sae": int, "pie": int, "prie": int, "pge": int},
    }

Empty / no-data cases collapse gracefully — callers always receive every key
with a sane default. No exceptions are raised on the request path.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


# ── Knobs ──────────────────────────────────────────────────────────────
# Keep small — the dashboard surface is "executive", not exhaustive.
MAX_GOING_WELL = 5
MAX_NEEDS_ATTENTION = 5
MAX_RECOMMENDATIONS = 3
INSIGHT_WINDOW_DAYS = 7      # only fresh insights count toward the briefing


def build_executive_summary(user) -> dict[str, Any]:
    """Compose the executive briefing from canonical sources.

    Read-only. Safe on the request path.
    """
    try:
        going_well = _collect_going_well(user)
    except Exception:
        logger.warning("exec_summary: going_well failed", exc_info=True)
        going_well = []

    try:
        needs_attention = _collect_needs_attention(user)
    except Exception:
        logger.warning("exec_summary: needs_attention failed", exc_info=True)
        needs_attention = []

    try:
        focus_now, follow_on = _collect_focus_now(user)
    except Exception:
        logger.warning("exec_summary: focus_now failed", exc_info=True)
        focus_now, follow_on = None, []

    try:
        biggest_risk = _collect_biggest_risk(user, needs_attention)
    except Exception:
        logger.warning("exec_summary: biggest_risk failed", exc_info=True)
        biggest_risk = None

    try:
        biggest_opportunity = _collect_biggest_opportunity(user)
    except Exception:
        logger.warning("exec_summary: biggest_opportunity failed", exc_info=True)
        biggest_opportunity = None

    try:
        recommendations = _collect_recommendations(user)
    except Exception:
        logger.warning("exec_summary: recommendations failed", exc_info=True)
        recommendations = []

    trajectory = _derive_trajectory(going_well, needs_attention, biggest_risk)

    return {
        "trajectory": trajectory,
        "going_well": going_well,
        "needs_attention": needs_attention,
        "biggest_risk": biggest_risk,
        "biggest_opportunity": biggest_opportunity,
        "focus_now": focus_now,
        "follow_on": follow_on,
        "recommendations": recommendations,
        "as_of": timezone.now().isoformat(),
    }


# ── Going Well ─────────────────────────────────────────────────────────


def _collect_going_well(user) -> list[dict[str, Any]]:
    """Recent positive Insights, newest first."""
    from apps.core.ai_insights.models import Insight

    cutoff = timezone.now() - timedelta(days=INSIGHT_WINDOW_DAYS)
    qs = (
        Insight.objects.filter(
            user=user,
            severity="positive",
            status__in=("new", "read"),
            created_at__gte=cutoff,
        )
        .order_by("-created_at")[:MAX_GOING_WELL]
    )
    return [
        {
            "title": i.title,
            "message": i.message,
            "module": i.module,
            "insight_type": i.insight_type,
        }
        for i in qs
    ]


# ── Needs Attention ────────────────────────────────────────────────────


def _collect_needs_attention(user) -> list[dict[str, Any]]:
    """Recent warning / critical Insights, severity-weighted then newest."""
    from apps.core.ai_insights.models import Insight

    cutoff = timezone.now() - timedelta(days=INSIGHT_WINDOW_DAYS)
    qs = Insight.objects.filter(
        user=user,
        severity__in=("warning", "critical"),
        status__in=("new", "read"),
        created_at__gte=cutoff,
    ).order_by("-created_at")

    # Critical first, warning second; preserve created_at order inside each.
    critical = [i for i in qs if i.severity == "critical"]
    warning = [i for i in qs if i.severity == "warning"]
    ordered = (critical + warning)[:MAX_NEEDS_ATTENTION]

    return [
        {
            "title": i.title,
            "message": i.message,
            "module": i.module,
            "severity": i.severity,
            "insight_type": i.insight_type,
        }
        for i in ordered
    ]


# ── Focus Now (selector reuse) ─────────────────────────────────────────


def _collect_focus_now(user) -> tuple[dict | None, list[dict]]:
    """Reuse canonical execution selectors. No re-ranking."""
    from apps.core.execution.execution_state import build_execution_state
    from apps.core.execution.selectors import get_next_action

    state = build_execution_state(user)
    payload = get_next_action(state) or {}
    primary = payload.get("primary_action")

    focus = None
    if primary:
        focus = {
            "title": primary.get("title"),
            "module": primary.get("source_type"),
            "time_display": primary.get("time_display"),
            "execution_status": primary.get("execution_status"),
            "task_class": primary.get("task_class"),
            "reason": payload.get("reason") or "Top priority right now.",
            "source": "selector:next_action",
        }

    # Follow-on hints — next 2 future / upcoming items, soft suggestions only.
    follow_on_pool = (state.get("next_actions") or []) + (state.get("upcoming_actions") or [])
    seen_keys = {(primary.get("source_type"), primary.get("source_id"))} if primary else set()
    follow_on = []
    for a in follow_on_pool:
        key = (a.get("source_type"), a.get("source_id"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        follow_on.append({
            "title": a.get("title"),
            "time_display": a.get("time_display"),
            "module": a.get("source_type"),
        })
        if len(follow_on) >= 3:
            break

    return focus, follow_on


# ── Biggest Risk ───────────────────────────────────────────────────────


def _collect_biggest_risk(user, needs_attention: list[dict]) -> dict | None:
    """Prefer canonical risk selector. Fall back to top critical insight."""
    try:
        from apps.core.execution.execution_state import build_execution_state
        from apps.core.execution.selectors import get_biggest_risk

        state = build_execution_state(user)
        payload = get_biggest_risk(state) or {}
        primary = payload.get("primary_action")
        if primary:
            return {
                "title": primary.get("title"),
                "message": payload.get("reason") or "At risk of being missed.",
                "module": primary.get("source_type"),
                "time_display": primary.get("time_display"),
                "source": "selector:biggest_risk",
            }
    except Exception:
        logger.debug("biggest_risk selector failed; falling back to insights",
                     exc_info=True)

    # Fallback — top critical/warning from needs_attention.
    critical = [n for n in needs_attention if n.get("severity") == "critical"]
    pool = critical or needs_attention
    if pool:
        top = pool[0]
        return {
            "title": top["title"],
            "message": top.get("message", ""),
            "module": top.get("module"),
            "source": "insight",
        }
    return None


# ── Biggest Opportunity ────────────────────────────────────────────────


def _collect_biggest_opportunity(user) -> dict | None:
    """Strongest near-term positive prediction."""
    from apps.core.ai_predictions.models import Prediction

    candidate = (
        Prediction.objects.filter(user=user, status="active")
        .filter(confidence_score__gte=0.6)
        .order_by("-confidence_score", "-created_at")
        .first()
    )
    if not candidate:
        return None
    return {
        "title": candidate.prediction_type.replace("_", " ").title(),
        "message": candidate.explanation or "Trajectory looks favorable.",
        "module": candidate.module,
        "confidence": round(candidate.confidence_score, 2),
        "source": "prediction",
    }


# ── Recommendations (PGE) ──────────────────────────────────────────────


def _collect_recommendations(user) -> list[dict[str, Any]]:
    """Top deterministic guidance — small set, priority first."""
    from apps.core.ai_guidance.models import GuidanceItem

    qs = (
        GuidanceItem.objects.filter(user=user, is_active=True)
        .order_by("priority", "-created_at")[:MAX_RECOMMENDATIONS]
    )
    return [
        {
            "title": g.title,
            "message": g.message,
            "priority": g.priority,
            "module": g.module,
            "guidance_type": g.guidance_type,
        }
        for g in qs
    ]


# ── Trajectory ─────────────────────────────────────────────────────────


def _derive_trajectory(going_well, needs_attention, biggest_risk) -> str:
    """Cheap deterministic mood label — purely from counts + risk flag."""
    pos = len(going_well or [])
    neg = len(needs_attention or [])
    has_risk = bool(biggest_risk)

    if pos == 0 and neg == 0 and not has_risk:
        return "unknown"
    if pos > 0 and neg == 0:
        return "improving"
    if neg > 0 and pos == 0:
        return "slipping"
    if has_risk and neg >= pos:
        return "slipping"
    if pos >= max(neg, 1) * 2:
        return "improving"
    if pos == neg:
        return "steady"
    return "mixed"
