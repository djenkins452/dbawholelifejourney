"""
DBE — Briefing Logger.

Stores daily briefings safely with duplicate prevention.
One briefing per user per day.
"""

import logging

from django.db import IntegrityError
from django.utils import timezone

from apps.core.ai_briefing.models import DailyBriefing

logger = logging.getLogger(__name__)


def store_briefing(user, summary, ranked_items, state, guidance_items, insights, predictions):
    """
    Store a daily briefing record.

    Prevents duplicate briefings for the same user + date.
    If a briefing already exists for today, returns the existing one.

    Args:
        user: Django User instance.
        summary: str — generated summary text.
        ranked_items: list of ranked item dicts.
        state: dict — SAE state snapshot.
        guidance_items: list/QuerySet — source guidance items.
        insights: list/QuerySet — source insights.
        predictions: list/QuerySet — source predictions.

    Returns:
        DailyBriefing instance.
    """
    today = timezone.now().date()

    # Check for existing briefing
    existing = DailyBriefing.objects.filter(user=user, briefing_date=today).first()
    if existing:
        logger.debug(f"Briefing already exists for user {user.id} on {today}")
        return existing

    # Build snapshots
    guidance_snapshot = _serialize_guidance(guidance_items)
    insight_snapshot = _serialize_insights(insights)
    prediction_snapshot = _serialize_predictions(predictions)

    try:
        briefing = DailyBriefing.objects.create(
            user=user,
            briefing_date=today,
            summary=summary,
            state_snapshot=state or {},
            guidance_snapshot=guidance_snapshot,
            insight_snapshot=insight_snapshot,
            prediction_snapshot=prediction_snapshot,
        )
        logger.info(f"Created daily briefing for user {user.id} on {today}")
        return briefing
    except IntegrityError:
        # Race condition — another process created it
        logger.debug(f"Briefing race condition for user {user.id} on {today}")
        return DailyBriefing.objects.filter(user=user, briefing_date=today).first()


def _serialize_guidance(items):
    """Serialize guidance items to JSON-safe list."""
    result = []
    for item in items:
        result.append({
            "id": item.id,
            "title": item.title,
            "priority": item.priority,
            "source": item.source,
            "module": item.module or "",
        })
    return {"items": result, "count": len(result)}


def _serialize_insights(items):
    """Serialize insight items to JSON-safe list."""
    result = []
    for item in items:
        result.append({
            "id": item.id,
            "title": item.title,
            "severity": item.severity,
            "module": item.module or "",
        })
    return {"items": result, "count": len(result)}


def _serialize_predictions(items):
    """Serialize prediction items to JSON-safe list."""
    result = []
    for item in items:
        result.append({
            "id": item.id,
            "prediction_type": item.prediction_type,
            "confidence_score": item.confidence_score,
            "module": item.module or "",
        })
    return {"items": result, "count": len(result)}
