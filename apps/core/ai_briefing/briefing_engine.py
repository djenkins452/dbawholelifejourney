"""
DBE — Briefing Engine.

Main entry point for generating daily briefings. Aggregates from
SAE (state), PIE (insights), PRIE (predictions), and PGE (guidance).

Does NOT generate new intelligence — only aggregates and prioritizes
existing intelligence outputs.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.ai_briefing.briefing_logger import store_briefing
from apps.core.ai_briefing.briefing_ranker import rank_briefing_items
from apps.core.ai_briefing.briefing_selector import select_briefing_items
from apps.core.ai_briefing.models import DailyBriefing
from apps.core.ai_observability.instrumentation import log_engine_run as _instrument_engine_run

logger = logging.getLogger(__name__)


@_instrument_engine_run("DBE", 3)
def generate_daily_briefing(user):
    """
    Generate the daily intelligence briefing for a user.

    Pipeline:
    1. Check for existing briefing today (skip if exists)
    2. Gather intelligence from SAE, PIE, PRIE, PGE
    3. Select top items via briefing_selector
    4. Rank items via briefing_ranker
    5. Generate summary text
    6. Store via briefing_logger

    Args:
        user: Django User instance.

    Returns:
        DailyBriefing instance (new or existing).
    """
    today = timezone.now().date()

    # Skip if already generated today
    existing = DailyBriefing.objects.filter(user=user, briefing_date=today).first()
    if existing:
        return existing

    # Step 1: Gather intelligence
    state = _get_state(user)
    guidance_items = _get_guidance(user)
    insights = _get_insights(user)
    predictions = _get_predictions(user)

    # Step 2: Select top items
    selected = select_briefing_items(guidance_items, insights, predictions)

    # Step 3: Rank items
    ranked = rank_briefing_items(selected)

    # Step 3.5: ICQG quality gate (non-blocking)
    try:
        from apps.core.ai_quality.quality_gate import filter_briefing_items
        ranked = filter_briefing_items(user, ranked)
    except Exception as e:
        logger.warning(f"DBE: ICQG filter failed (continuing): {e}")

    # Step 3.7: Phase 4 — Apply preferred briefing length
    preferred_length = "standard"
    try:
        from apps.core.ai_feedback.briefing_tracker import get_preferred_briefing_length
        preferred_length = get_preferred_briefing_length(user)
    except Exception:
        pass

    # Step 4: Generate summary
    summary = _generate_summary(ranked, state, preferred_length=preferred_length)

    # Step 4.5: Apply persona rendering (non-blocking)
    summary = _apply_persona(user, summary)

    # Step 5: Store
    briefing = store_briefing(
        user=user,
        summary=summary,
        ranked_items=ranked,
        state=state,
        guidance_items=guidance_items,
        insights=insights,
        predictions=predictions,
    )

    # E3: Create explain record (non-blocking)
    if briefing:
        try:
            from apps.core.ai_explain.explain_engine import ensure_explain_record
            ensure_explain_record(user, "DBE", briefing)
        except Exception:
            pass  # E3 failure must never block DBE

    return briefing


def get_todays_briefing(user):
    """
    Get today's briefing for a user (without generating).

    Args:
        user: Django User instance.

    Returns:
        DailyBriefing or None.
    """
    today = timezone.now().date()
    return DailyBriefing.objects.filter(user=user, briefing_date=today).first()


def _get_state(user):
    """Get SAE state snapshot."""
    try:
        from apps.core.ai_state.state_engine import get_user_state
        return get_user_state(user)
    except Exception as e:
        logger.error(f"DBE: Failed to get state for user {user.id}: {e}")
        return {}


def _get_guidance(user):
    """Get active PGE guidance items."""
    try:
        from apps.core.ai_guidance.guidance_engine import get_active_guidance
        return list(get_active_guidance(user, limit=10))
    except Exception as e:
        logger.error(f"DBE: Failed to get guidance for user {user.id}: {e}")
        return []


def _get_insights(user):
    """Get recent PIE insights (last 24 hours, not dismissed)."""
    try:
        from apps.core.ai_insights.models import Insight

        cutoff = timezone.now() - timedelta(hours=24)
        return list(
            Insight.objects.filter(
                user=user,
                created_at__gte=cutoff,
            )
            .exclude(status="dismissed")
            .order_by("-created_at")[:20]
        )
    except Exception as e:
        logger.error(f"DBE: Failed to get insights for user {user.id}: {e}")
        return []


def _get_predictions(user):
    """Get active PRIE predictions."""
    try:
        from apps.core.ai_predictions.models import Prediction

        return list(
            Prediction.objects.filter(
                user=user,
                status="active",
            )
            .order_by("-confidence_score")[:15]
        )
    except Exception as e:
        logger.error(f"DBE: Failed to get predictions for user {user.id}: {e}")
        return []


def _generate_summary(ranked_items, state, preferred_length="standard"):
    """
    Generate a Strategic Narrative for the Day.

    Phase 4 upgrade: Instead of listing insights, generates a
    6-section executive briefing narrative. Respects preferred_length
    from BriefingEngagementProfile feedback loop.

    Structure:
    1. Where you stand
    2. What matters most today
    3. Hidden risks (standard/detailed only)
    4. Relational considerations (standard/detailed only)
    5. Health considerations (standard/detailed only)
    6. One focus directive
    """
    sections = []

    # Section 1: Where you stand
    standing = _build_standing_section(state, ranked_items)
    if standing:
        sections.append(f"WHERE YOU STAND: {standing}")

    # Section 2: What matters most today
    priorities = _build_priorities_section(ranked_items)
    if priorities:
        sections.append(f"WHAT MATTERS MOST: {priorities}")

    # Concise mode: skip optional sections 3-5
    if preferred_length != "concise":
        # Section 3: Hidden risks
        risks = _build_risks_section(ranked_items, state)
        if risks:
            sections.append(f"HIDDEN RISKS: {risks}")

        # Section 4: Relational considerations
        relational = _build_relational_section(state)
        if relational:
            sections.append(f"RELATIONSHIPS: {relational}")

        # Section 5: Health considerations
        health_section = _build_health_section(state)
        if health_section:
            sections.append(f"HEALTH: {health_section}")

    # Section 6: Focus directive
    directive = _build_focus_directive(ranked_items, state)
    sections.append(f"TODAY'S DIRECTIVE: {directive}")

    if not sections:
        return "No briefing data available yet. Start logging activity to see your daily strategic narrative."

    return "\n\n".join(sections)


def _build_standing_section(state, ranked_items):
    """Section 1: Where you stand — alignment, drift, momentum."""
    parts = []

    goals = state.get("goals", {})
    habits = state.get("habits", {})

    active_goals = goals.get("active_goal_count", 0)
    overdue = goals.get("overdue_goal_count", 0)
    completion = habits.get("avg_completion_rate", 0)

    if completion >= 0.8:
        parts.append(f"Habit execution is strong at {completion:.0%}.")
    elif completion >= 0.5:
        parts.append(f"Habit completion is moderate at {completion:.0%}.")
    elif completion > 0:
        parts.append(f"Habit completion has dropped to {completion:.0%}.")

    if overdue > 0:
        parts.append(f"{overdue} goal{'s are' if overdue > 1 else ' is'} overdue.")
    elif active_goals > 0:
        parts.append(f"{active_goals} active goal{'s' if active_goals > 1 else ''} on track.")

    # Count critical/warning items
    warnings = [i for i in ranked_items if i.get("severity") in ("warning", "critical")]
    if warnings:
        parts.append(f"{len(warnings)} item{'s' if len(warnings) > 1 else ''} need{'s' if len(warnings) == 1 else ''} attention.")

    return " ".join(parts) if parts else "Systems nominal. No critical items."


def _build_priorities_section(ranked_items):
    """Section 2: What matters most today."""
    high_priority = [
        i for i in ranked_items
        if i.get("priority", 5) <= 2 or i.get("severity") in ("critical", "warning")
    ][:3]

    if not high_priority:
        return "Execute your scheduled plan. No urgent items surfaced."

    return " ".join(
        i.get("message", i.get("title", "")) for i in high_priority
    )


def _build_risks_section(ranked_items, state):
    """Section 3: Hidden risks — things that aren't urgent yet but forming."""
    risks = []
    for item in ranked_items:
        if item.get("type") == "prediction" and item.get("confidence", 0) >= 0.6:
            risks.append(item.get("title", ""))
        elif item.get("severity") == "warning" and item.get("type") == "insight":
            if "cross_domain" in item.get("insight_type", ""):
                risks.append(item.get("title", ""))

    if not risks:
        return None

    return " ".join(risks[:3])


def _build_relational_section(state):
    """Section 4: Relational considerations."""
    # Pull from state if available
    relationships = state.get("relationships", {})
    drifting = relationships.get("drifting_count", 0)
    if drifting > 0:
        return f"{drifting} key relationship{'s' if drifting > 1 else ''} showing drift. Consider reaching out."
    return None


def _build_health_section(state):
    """Section 5: Health considerations."""
    parts = []
    health = state.get("health", {})
    medicine = state.get("medicine", {})

    weight_trend = health.get("weight_trend")
    if weight_trend and weight_trend != "stable":
        parts.append(f"Weight trending {weight_trend}.")

    sleep = health.get("sleep_avg_hours_7d")
    if sleep and sleep < 6.5:
        parts.append(f"Sleep averaging {sleep:.1f}h — below optimal.")

    # Phase 7 Fix: medication adherence lives on medicine state, not
    # health state. Reading from the correct domain. (Audit 2026-04-08.)
    med = medicine.get("adherence_7d")
    if med is not None and med < 80:
        parts.append(f"Medication adherence at {med}% — needs attention.")

    return " ".join(parts) if parts else None


def _build_focus_directive(ranked_items, state):
    """Section 6: One clear focus directive."""
    # Check for critical items first
    critical = [i for i in ranked_items if i.get("severity") == "critical"]
    if critical:
        return f"Address: {critical[0].get('title', 'critical item')}."

    overdue = state.get("goals", {}).get("overdue_goal_count", 0)
    if overdue > 2:
        return "Close overdue goals before taking on new commitments."

    completion = state.get("habits", {}).get("avg_completion_rate", 1.0)
    if completion < 0.5:
        return "Focus on one key habit today. Rebuild momentum."

    return "Execute today's plan. Protect your Tier-1 blocks."


def _apply_persona(user, summary):
    """Apply PIL persona rendering to briefing summary (non-blocking)."""
    if not summary:
        return summary
    try:
        from apps.core.ai_persona.persona_engine import render_with_persona

        return render_with_persona(
            user=user,
            base_message=summary,
            message_type="briefing",
        )
    except Exception:
        return summary  # fail-safe
