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
    cockpit_domains = _safe(_build_cockpit_domains_raw, user, default=[])

    context: dict[str, Any] = {
        # Raw canonical dial data — matches v2 cockpit_dial.html contract.
        "cockpit_domains": cockpit_domains,
        # Composed/fallback gauges (used only when cockpit is empty).
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

    exec_summary = context["executive_summary"] or {}
    context["focus_now"] = exec_summary.get("focus_now")
    context["follow_on"] = exec_summary.get("follow_on") or []

    # ── Self-critique fix: drop biggest_risk if it duplicates focus_now.
    risk = exec_summary.get("biggest_risk")
    focus = context["focus_now"]
    if risk and focus and risk.get("title") == focus.get("title"):
        # The user is already looking at this in Focus Now — no value in
        # repeating it in the briefing.
        exec_summary["biggest_risk"] = None

    return context


def _build_cockpit_domains_raw(user) -> list[dict]:
    """Return the GoalCockpitService output unchanged.

    v3 renders these via the canonical v2 cockpit_dial.html partial so the
    visual matches v2 (which is what the user actually wants at the top of
    the page). No transformation — same shape, same source of truth.
    """
    from apps.dashboard_v2.services.cockpit_service import GoalCockpitService
    return GoalCockpitService(user).get_cockpit_data() or []


# ── Section builders ──────────────────────────────────────────────────


def _build_gauges(user) -> list[dict]:
    """Reuse GoalCockpitService — deterministic, goal-driven domain scores.

    Decorates each entry with a 'trend_label' and a short 'drivers' list
    (from components) for the gauge card template.

    Fallback: when the user has no active LifeGoals/HabitGoals the cockpit
    is empty. We don't show a "no domains" empty state — we render a
    canonical baseline (Health / Faith / Life Execution / Purpose) built
    READ-ONLY from existing SAE state. No new metric computation, no LLM.
    """
    from apps.dashboard_v2.services.cockpit_service import GoalCockpitService

    raw = GoalCockpitService(user).get_cockpit_data() or []
    if not raw:
        return _fallback_gauges_from_sae(user)

    out = []
    for d in raw:
        trend_delta = d.get("trend_delta") or 0
        if trend_delta > 0:
            trend_label = f"+{trend_delta}"
        elif trend_delta < 0:
            trend_label = f"{trend_delta}"
        else:
            trend_label = "—"

        components = d.get("components") or []
        drivers = [
            {
                "label": c.get("label", ""),
                "status": c.get("status", "info"),
                "detail": c.get("detail", ""),
            }
            for c in components[:3]
        ]

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
            "source": "cockpit",
        })
    return out


# ── Fallback gauges (canonical SAE-driven, no fabrication) ────────────


def _fallback_gauges_from_sae(user) -> list[dict]:
    """Baseline gauges derived from already-built SAE state.

    Every value comes from an existing canonical field — no aggregation
    or recomputation happens here. If a domain has no data, its gauge
    shows "—" instead of being hidden, so the dashboard always feels
    populated.
    """
    from apps.core.ai_state.state_engine import get_module_state

    gauges: list[dict] = []

    # ── Health ────────────────────────────────────────────────────
    try:
        health = get_module_state(user, "health") or {}
        gauges.append(_status_gauge(
            slug="health",
            label="Health",
            icon="💪",
            statuses=[
                ("Sleep", health.get("sleep_status")),
                ("Water", health.get("water_status")),
                ("Glucose", health.get("glucose_status")),
                ("Steps", health.get("steps_status")),
            ],
        ))
    except Exception:
        logger.debug("fallback health gauge failed", exc_info=True)

    # ── Faith ─────────────────────────────────────────────────────
    try:
        faith = get_module_state(user, "faith") or {}
        streak = faith.get("reading_streak") or 0
        plans = faith.get("active_reading_plans") or 0
        # Streak-driven 0-100; capped at 21-day plateau.
        score = min(100, int(streak * 5)) if streak else (40 if plans else None)
        drivers = []
        if streak:
            drivers.append({"label": f"{streak}-day streak", "status": "good"})
        if plans:
            drivers.append({"label": f"{plans} active plan{'s' if plans != 1 else ''}", "status": "good"})
        if not drivers:
            drivers.append({"label": "No plan active yet", "status": "info"})
        gauges.append({
            "slug": "faith", "label": "Faith", "icon": "✝️",
            "score": score, "trend": "flat", "trend_delta": 0,
            "trend_label": "—", "drivers": drivers,
            "source": "sae_fallback",
        })
    except Exception:
        logger.debug("fallback faith gauge failed", exc_info=True)

    # ── Life Execution — completion% of today's actionable items ──
    try:
        from apps.core.execution.today_execution import build_today_execution
        contract = build_today_execution(user)
        items = contract.get("items", []) or []
        actionable = [i for i in items if i.get("is_actionable")]
        completed = sum(1 for i in actionable if i.get("completed_today"))
        total = len(actionable)
        score = int(round((completed / total) * 100)) if total else None
        overdue = sum(
            1 for i in actionable
            if not i.get("completed_today") and i.get("urgency") == "overdue"
        )
        at_risk = sum(
            1 for i in actionable
            if not i.get("completed_today")
            and i.get("execution_status") == "AT_RISK"
        )
        drivers = [
            {"label": f"{completed}/{total} done today",
             "status": "good" if total and completed >= total * 0.75 else "info"},
        ]
        if overdue:
            drivers.append({"label": f"{overdue} overdue", "status": "warn"})
        if at_risk:
            drivers.append({"label": f"{at_risk} at risk", "status": "warn"})
        gauges.append({
            "slug": "life", "label": "Life Execution", "icon": "🧭",
            "score": score, "trend": "flat", "trend_delta": 0,
            "trend_label": "—", "drivers": drivers,
            "source": "sae_fallback",
        })
    except Exception:
        logger.debug("fallback life-execution gauge failed", exc_info=True)

    # ── Purpose ───────────────────────────────────────────────────
    try:
        goals = get_module_state(user, "goals") or {}
        count = goals.get("active_goal_count") or 0
        # Presence-driven: 0 goals → no score; 1+ goals → 50 + 10/goal cap 90.
        score = None if count == 0 else min(90, 50 + count * 10)
        drivers = [{
            "label": f"{count} active goal{'s' if count != 1 else ''}",
            "status": "good" if count else "info",
        }]
        gauges.append({
            "slug": "purpose", "label": "Purpose", "icon": "🎯",
            "score": score, "trend": "flat", "trend_delta": 0,
            "trend_label": "—", "drivers": drivers,
            "source": "sae_fallback",
        })
    except Exception:
        logger.debug("fallback purpose gauge failed", exc_info=True)

    return gauges


# Maps SAE *_status values → (numeric weight, presentation status).
_STATUS_TO_WEIGHT = {
    "excellent": (100, "good"),
    "good": (80, "good"),
    "fair": (55, "warn"),
    "poor": (25, "poor"),
    "no_data": (None, "info"),
    None: (None, "info"),
    "": (None, "info"),
}


def _status_gauge(slug, label, icon, statuses):
    """Average available _status values into a 0-100 score with drivers."""
    weights = []
    drivers = []
    for driver_label, status in statuses:
        weight, vis = _STATUS_TO_WEIGHT.get(status, (None, "info"))
        if weight is not None:
            weights.append(weight)
        drivers.append({
            "label": driver_label,
            "status": vis,
            "detail": status or "no data",
        })
    score = int(round(sum(weights) / len(weights))) if weights else None
    return {
        "slug": slug, "label": label, "icon": icon,
        "score": score, "trend": "flat", "trend_delta": 0,
        "trend_label": "—", "drivers": drivers,
        "source": "sae_fallback",
    }


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

    # Convergence guard: SAE is the canonical freshness layer Beth reads.
    # The accountability card reads persisted Insight rows. If an Insight's
    # underlying condition has cleared in SAE, suppress it here so the
    # dashboard never tells the user something Beth contradicts.
    try:
        from apps.core.ai_state.state_engine import get_module_state
        _health = get_module_state(user, "health") or {}
        if not _health.get("weight_sync_stale", True):
            _gap = _health.get("weight_sync_gap_days")
            if _gap is not None and _gap < 3:
                fresh_insights = [
                    i for i in fresh_insights
                    if i.insight_type != "missing_weight_logging"
                ]
    except Exception:
        logger.debug("convergence guard: SAE read failed", exc_info=True)

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


def _accountability_insight(going_well, needs_attention, recommendation) -> str | None:
    """Deterministic one-line interpretation. No LLM, fully rule-based.

    Returns None when there's nothing meaningful to say — caller skips the
    insight block entirely instead of showing a "not enough signal" line
    next to a substantive recommendation (the contradiction the user
    flagged in the v3 review).
    """
    pos = len(going_well or [])
    neg = len(needs_attention or [])

    if neg == 0 and pos > 0:
        return "Healthy momentum. Keep the rhythm consistent."
    if neg > 0 and pos == 0:
        return "Drift detected — accountability needed here."
    if neg > 0 and pos > 0 and neg >= pos:
        return "Mixed signals. Wins are real, but drift is outpacing them."
    if neg > 0 and pos > 0:
        return "Steady progress — protect the wins and address the drift."
    # No going_well, no needs_attention. If we have a recommendation, the
    # rec speaks for itself — don't undercut it with a "no signal" line.
    if recommendation:
        return None
    return "Not enough signal yet — log more and patterns will emerge."


def build_weather_tile(user) -> dict:
    """Always-returns weather payload for the header tile.

    Shape: {'available': bool, 'data': dict | None, 'message': str | None}

    Guarantees the header pill always renders something — either real
    weather, or a "set location" hint — so the dashboard never feels
    half-built.
    """
    prefs = getattr(user, "preferences", None)
    location_city = (prefs and getattr(prefs, "location_city", "")) or ""
    if not location_city:
        return {
            "available": False,
            "data": None,
            "message": "Set location",
        }
    try:
        from apps.dashboard.services.weather import weather_service
        weather_data = weather_service.get_weather_data(location_city)
        if weather_data:
            return {
                "available": True,
                "data": weather_data.to_dict(),
                "message": None,
            }
    except Exception:
        logger.debug("v3: weather lookup failed", exc_info=True)
    return {"available": False, "data": None, "message": "Weather unavailable"}


def _build_utilities(user) -> dict:
    """Small supporting tiles — water only. Weather lives in the header."""
    util: dict[str, Any] = {}
    prefs = getattr(user, "preferences", None)

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
