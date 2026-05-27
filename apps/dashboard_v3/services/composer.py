"""
Dashboard V3 Composer — assembles the page context from canonical sources.

This is a thin orchestrator. ALL truth comes from existing engines:

    Gauges                  ← GoalCockpitService (already deterministic,
                                domain-driven by active LifeGoals/HabitGoals)
    Executive Summary       ← apps.core.cos_briefing.build_executive_summary
    Focus Right Now         ← same composer (which reuses get_next_action)
    Accountability Cards    ← per-domain composition from SAE state +
                                Insights + GuidanceItem (deterministic)
    Rhythm Sections         ← apps.core.cos_briefing.build_rhythm_sections
    Weather                 ← apps.dashboard.services.weather

NO new business logic. NO LLM. Only reshaping for the presentation layer.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Domain order for accountability cards (presentation-only).
ACCOUNTABILITY_DOMAIN_ORDER = [
    "health",
    "faith",
    "purpose",
    "relationships",
    "life",
    "finance",
]

DOMAIN_LABELS = {
    "health": "Health",
    "faith": "Faith",
    "purpose": "Purpose",
    "relationships": "Relationships",
    "life": "Life Execution",
    "finance": "Finance",
    "work": "Work",
}

DOMAIN_ICONS = {
    "health": "💪",
    "faith": "✝️",
    "purpose": "🎯",
    "relationships": "👥",
    "life": "🧭",
    "finance": "💼",
    "work": "📋",
}


def build_dashboard_v3_context(user) -> dict[str, Any]:
    """Build the full dashboard_v3 page context.

    Read-only. Safe on the request path. Returns a dict that the template
    consumes directly — no further compute happens in templates.
    """
    context: dict[str, Any] = {
        "gauges": _safe(_build_gauges, user, default=[]),
        "executive_summary": _safe(_build_executive_summary, user, default={}),
        "focus_now": None,        # filled below from executive_summary
        "follow_on": [],          # filled below from executive_summary
        "accountability_cards": _safe(
            _build_accountability_cards, user, default=[]
        ),
        "rhythm": _safe(_build_rhythm, user, default={"sections": [], "totals": {}}),
        "utilities": _safe(_build_utilities, user, default={}),
    }

    # Promote focus_now / follow_on from the exec summary so the template
    # can render them in their own dedicated section without re-reading the
    # composer. Keeps the template thin.
    exec_summary = context["executive_summary"] or {}
    context["focus_now"] = exec_summary.get("focus_now")
    context["follow_on"] = exec_summary.get("follow_on") or []

    return context


# ── Section builders ──────────────────────────────────────────────────


def _build_gauges(user) -> list[dict]:
    """Reuse GoalCockpitService — already produces deterministic, signed
    domain scores driven by the user's active goals.

    We re-decorate each entry with a 'trend_label' and a short 'drivers'
    list (from components) for the gauge card template, without touching
    the underlying scoring logic.
    """
    from apps.dashboard_v2.services.cockpit_service import GoalCockpitService

    raw = GoalCockpitService(user).get_cockpit_data() or []
    out = []
    for d in raw:
        trend_delta = d.get("trend_delta") or 0
        if trend_delta > 0:
            trend_label = f"Trending Up (+{trend_delta})"
        elif trend_delta < 0:
            trend_label = f"Trending Down ({trend_delta})"
        else:
            trend_label = "Steady"

        # Top up to 3 driver components, preserving the cockpit's order.
        components = d.get("components") or []
        drivers = []
        for c in components[:4]:
            drivers.append({
                "label": c.get("label", ""),
                "status": c.get("status", "info"),   # good/warn/poor/info
                "detail": c.get("detail", ""),
            })

        out.append({
            "slug": d.get("slug"),
            "label": d.get("label"),
            "icon": d.get("icon"),
            "color": d.get("color"),
            "score": d.get("score"),
            "trend": d.get("trend"),
            "trend_delta": trend_delta,
            "trend_label": trend_label,
            "drivers": drivers,
            "priority": d.get("priority"),
        })
    return out


def _build_executive_summary(user) -> dict:
    from apps.core.cos_briefing import build_executive_summary
    return build_executive_summary(user)


def _build_rhythm(user) -> dict:
    from apps.core.cos_briefing import build_rhythm_sections
    return build_rhythm_sections(user)


def _build_accountability_cards(user) -> list[dict]:
    """For each enabled domain, compose a card from SAE state + insights.

    Composition is deterministic and references the SAME going_well /
    needs_attention / recommendations data the exec summary uses — just
    filtered per-domain so the cards align with their gauges.
    """
    from apps.core.ai_insights.models import Insight
    from apps.core.ai_guidance.models import GuidanceItem
    from datetime import timedelta
    from django.utils import timezone

    prefs = getattr(user, "preferences", None)
    enabled_flags = {
        "health": getattr(prefs, "health_enabled", True),
        "faith": getattr(prefs, "faith_enabled", True),
        "purpose": getattr(prefs, "purpose_enabled", True),
        "life": getattr(prefs, "life_enabled", True),
        "relationships": True,
        "finance": True,
    }

    cutoff = timezone.now() - timedelta(days=7)
    # Fetch once; filter in Python — small datasets and avoids N+1.
    fresh_insights = list(
        Insight.objects.filter(
            user=user,
            status__in=("new", "read"),
            created_at__gte=cutoff,
        ).order_by("-created_at")
    )
    fresh_guidance = list(
        GuidanceItem.objects.filter(user=user, is_active=True)
        .order_by("priority", "-created_at")
    )

    cards: list[dict] = []
    for domain in ACCOUNTABILITY_DOMAIN_ORDER:
        if not enabled_flags.get(domain, True):
            continue

        domain_insights = [i for i in fresh_insights if i.module == domain]
        going_well = [
            {"title": i.title, "message": i.message}
            for i in domain_insights if i.severity == "positive"
        ][:3]
        needs_attention = [
            {"title": i.title, "message": i.message, "severity": i.severity}
            for i in domain_insights
            if i.severity in ("warning", "critical")
        ][:3]

        domain_guidance = [g for g in fresh_guidance if g.module == domain]
        recommendation = None
        if domain_guidance:
            top = domain_guidance[0]
            recommendation = {
                "title": top.title,
                "message": top.message,
                "priority": top.priority,
            }

        insight = _accountability_insight(
            going_well, needs_attention, recommendation
        )

        # Skip cards that are entirely empty — surfaces only what has signal.
        if not (going_well or needs_attention or recommendation):
            continue

        cards.append({
            "slug": domain,
            "label": DOMAIN_LABELS.get(domain, domain.title()),
            "icon": DOMAIN_ICONS.get(domain, "•"),
            "going_well": going_well,
            "needs_attention": needs_attention,
            "insight": insight,
            "recommendation": recommendation,
        })

    return cards


def _accountability_insight(going_well, needs_attention, recommendation) -> str:
    """Deterministic one-line interpretation. No LLM, fully rule-based."""
    pos = len(going_well or [])
    neg = len(needs_attention or [])

    if neg == 0 and pos > 0:
        return "Healthy momentum. Keep the rhythm consistent."
    if neg > 0 and pos == 0:
        return "Drift detected — accountability needed here."
    if neg > 0 and pos > 0 and neg >= pos:
        return "Mixed signals. Wins are real, but drift is outpacing them."
    if neg > 0 and pos > pos:
        return "Mostly steady with one or two areas to tighten."
    if pos > 0 and neg > 0:
        return "Steady progress — protect the wins and address the drift."
    return "Not enough signal yet — log more and patterns will emerge."


def _build_utilities(user) -> dict:
    """Small supporting tiles — weather + water. Moved out of premium space."""
    util: dict[str, Any] = {}
    prefs = getattr(user, "preferences", None)

    # Weather — same source as v2, smaller surface area.
    try:
        location_city = (prefs and getattr(prefs, "location_city", "")) or ""
        if location_city:
            from apps.dashboard.services.weather import weather_service
            weather_data = weather_service.get_weather_data(location_city)
            if weather_data:
                util["weather"] = weather_data.to_dict()
    except Exception:
        logger.debug("v3: weather lookup failed", exc_info=True)

    # Water — keep visible but compact.
    if prefs and getattr(prefs, "health_enabled", True):
        try:
            from apps.core.utils import get_user_now
            from apps.health.models import WaterEntry

            today = get_user_now(user).date()
            progress = WaterEntry.get_daily_goal_progress(user, today)
            util["water"] = {
                "total_oz": progress["total_oz"],
                "goal_oz": progress["goal_oz"],
                "percentage": progress["percentage"],
                "goal_met": progress["goal_met"],
            }
        except Exception:
            logger.debug("v3: water lookup failed", exc_info=True)

    return util


# ── Internals ─────────────────────────────────────────────────────────


def _safe(fn, *args, default):
    """Run a section builder and degrade gracefully on failure."""
    try:
        return fn(*args)
    except Exception:
        logger.warning("dashboard_v3 section build failed: %s", fn.__name__,
                       exc_info=True)
        return default
