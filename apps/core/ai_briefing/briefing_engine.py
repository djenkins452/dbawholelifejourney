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

logger = logging.getLogger(__name__)


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

    # Step 4: Generate summary
    summary = _generate_summary(ranked, state)

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


def _generate_summary(ranked_items, state):
    """
    Generate a human-readable summary from ranked items and state.

    This is a template-based summary — no AI call needed.
    Produces natural-language sentences from structured data.
    """
    if not ranked_items and not state:
        return "No briefing data available yet. Start logging activity to see your daily summary."

    parts = []

    for item in ranked_items:
        item_type = item.get("type", "")
        message = item.get("message", "").strip()
        title = item.get("title", "").strip()

        if message:
            # Use the message directly (already human-readable from source engines)
            parts.append(message)
        elif title:
            parts.append(title)

    if not parts:
        # Fallback: generate from state
        parts = _state_summary_parts(state)

    if not parts:
        return "Your systems are running normally. No critical items to report."

    return " ".join(parts)


def _state_summary_parts(state):
    """Generate summary sentences from state data when no items available."""
    parts = []

    health = state.get("health", {})
    if health.get("weight_trend"):
        trend = health["weight_trend"]
        if trend == "decreasing":
            parts.append("Your weight trend is improving.")
        elif trend == "increasing":
            parts.append("Your weight has been trending up recently.")
        elif trend == "stable":
            parts.append("Your weight has been stable.")

    goals = state.get("goals", {})
    if goals.get("overdue_goal_count"):
        count = goals["overdue_goal_count"]
        parts.append(f"You have {count} overdue goal{'s' if count != 1 else ''}.")
    elif goals.get("active_goal_count"):
        count = goals["active_goal_count"]
        parts.append(f"You have {count} active goal{'s' if count != 1 else ''}.")

    habits = state.get("habits", {})
    if habits.get("avg_completion_rate"):
        rate = habits["avg_completion_rate"]
        if rate >= 0.8:
            parts.append("Your habit completion rate remains strong.")
        elif rate >= 0.5:
            parts.append("Your habit completion is moderate.")

    journal = state.get("journal", {})
    if journal.get("days_since_entry") and journal["days_since_entry"] > 3:
        parts.append(f"You haven't journaled in {journal['days_since_entry']} days.")

    return parts
