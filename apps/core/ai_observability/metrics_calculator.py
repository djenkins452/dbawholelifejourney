"""
IOCD — Metrics Calculator.

Computes system-wide intelligence metrics by reading from existing
engine models. Each metric source is independently try/excepted so
partial failures never block snapshot creation.

Project: Whole Life Journey
Path: apps/core/ai_observability/metrics_calculator.py

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


def calculate_daily_metrics(target_date=None):
    """
    Compute system-wide intelligence metrics for a given date.

    Reads from GuidanceItem, GuidanceLearningEvent, GuidanceLearningProfile,
    Prediction, DeliveredNotification, and QualityMetricAggregate.

    Each source is independently try/excepted — partial data is better
    than no data.

    Args:
        target_date: date object. Defaults to yesterday.

    Returns:
        dict with all metric fields for IntelligenceMetricsSnapshot.
    """
    if target_date is None:
        target_date = (timezone.now() - timedelta(days=1)).date()

    metrics = {}

    # Guidance effectiveness
    metrics.update(_calculate_guidance_metrics())

    # Prediction confidence & coverage
    metrics.update(_calculate_prediction_metrics())

    # Delivery effectiveness
    metrics.update(_calculate_delivery_metrics())

    # User engagement
    metrics.update(_calculate_engagement_metrics())

    # Quality
    metrics.update(_calculate_quality_metrics())

    # Persona effectiveness
    metrics.update(_calculate_persona_metrics())

    return metrics


def _calculate_guidance_metrics():
    """
    Calculate guidance effectiveness from GuidanceItem and GuidanceLearningEvent.

    Returns:
        dict with guidance_* fields.
    """
    defaults = {
        "guidance_total": 0,
        "guidance_acknowledged": 0,
        "guidance_dismissed": 0,
        "guidance_acted": 0,
        "guidance_expired": 0,
        "guidance_acceptance_rate": 0.0,
        "guidance_action_rate": 0.0,
        "guidance_avg_response_seconds": 0.0,
    }

    try:
        from apps.core.ai_guidance.models import GuidanceItem

        total = GuidanceItem.objects.count()
        if total == 0:
            return defaults

        acknowledged = GuidanceItem.objects.filter(
            acknowledged_at__isnull=False,
        ).count()
        dismissed = GuidanceItem.objects.filter(
            dismissed_at__isnull=False,
        ).count()
        acted = GuidanceItem.objects.filter(
            acted_upon_at__isnull=False,
        ).count()
        expired = GuidanceItem.objects.filter(
            is_active=False,
            expires_at__isnull=False,
            expires_at__lt=timezone.now(),
        ).count()

        acceptance_rate = acknowledged / total if total > 0 else 0.0
        action_rate = acted / total if total > 0 else 0.0

        # Average response time from GLOE learning events
        avg_response = 0.0
        try:
            from apps.core.ai_guidance_learning.learning_models import (
                GuidanceLearningEvent,
            )

            result = GuidanceLearningEvent.objects.filter(
                response_time_seconds__gt=0,
            ).aggregate(avg=Avg("response_time_seconds"))
            avg_response = result["avg"] or 0.0
        except Exception:
            pass

        return {
            "guidance_total": total,
            "guidance_acknowledged": acknowledged,
            "guidance_dismissed": dismissed,
            "guidance_acted": acted,
            "guidance_expired": expired,
            "guidance_acceptance_rate": round(acceptance_rate, 4),
            "guidance_action_rate": round(action_rate, 4),
            "guidance_avg_response_seconds": round(avg_response, 1),
        }
    except Exception as e:
        logger.warning(f"IOCD: Guidance metrics failed: {e}")
        return defaults


def _calculate_prediction_metrics():
    """
    Calculate prediction confidence & coverage from Prediction model.

    Returns:
        dict with predictions_* fields.
    """
    defaults = {
        "predictions_total": 0,
        "predictions_active": 0,
        "predictions_expired": 0,
        "predictions_avg_confidence": 0.0,
    }

    try:
        from apps.core.ai_predictions.models import Prediction

        total = Prediction.objects.count()
        if total == 0:
            return defaults

        active = Prediction.objects.filter(status="active").count()
        expired = Prediction.objects.filter(status="expired").count()

        result = Prediction.objects.filter(
            status="active",
        ).aggregate(avg=Avg("confidence_score"))
        avg_confidence = result["avg"] or 0.0

        return {
            "predictions_total": total,
            "predictions_active": active,
            "predictions_expired": expired,
            "predictions_avg_confidence": round(avg_confidence, 4),
        }
    except Exception as e:
        logger.warning(f"IOCD: Prediction metrics failed: {e}")
        return defaults


def _calculate_delivery_metrics():
    """
    Calculate delivery effectiveness from DeliveredNotification.

    Returns:
        dict with deliveries_* fields.
    """
    defaults = {
        "deliveries_total": 0,
        "deliveries_sent": 0,
        "deliveries_skipped": 0,
        "deliveries_failed": 0,
        "deliveries_success_rate": 0.0,
        "deliveries_by_channel": {},
    }

    try:
        from apps.core.ai_delivery.models import DeliveredNotification

        total = DeliveredNotification.objects.count()
        if total == 0:
            return defaults

        sent = DeliveredNotification.objects.filter(status="sent").count()
        skipped = DeliveredNotification.objects.filter(status="skipped").count()
        failed = DeliveredNotification.objects.filter(status="failed").count()
        success_rate = sent / total if total > 0 else 0.0

        # Channel breakdown
        channel_counts = (
            DeliveredNotification.objects.values("channel")
            .annotate(count=Count("id"))
        )
        by_channel = {
            row["channel"]: row["count"] for row in channel_counts
        }

        return {
            "deliveries_total": total,
            "deliveries_sent": sent,
            "deliveries_skipped": skipped,
            "deliveries_failed": failed,
            "deliveries_success_rate": round(success_rate, 4),
            "deliveries_by_channel": by_channel,
        }
    except Exception as e:
        logger.warning(f"IOCD: Delivery metrics failed: {e}")
        return defaults


def _calculate_engagement_metrics():
    """
    Calculate user engagement from GuidanceLearningProfile.

    Returns:
        dict with active_users_count and avg_responsiveness_score.
    """
    defaults = {
        "active_users_count": 0,
        "avg_responsiveness_score": 0.0,
    }

    try:
        from apps.core.ai_guidance_learning.learning_models import (
            GuidanceLearningProfile,
        )

        profiles = GuidanceLearningProfile.objects.filter(
            total_guidance_seen__gt=0,
        )
        count = profiles.count()
        if count == 0:
            return defaults

        result = profiles.aggregate(avg=Avg("responsiveness_score"))
        avg_score = result["avg"] or 0.0

        return {
            "active_users_count": count,
            "avg_responsiveness_score": round(avg_score, 4),
        }
    except Exception as e:
        logger.warning(f"IOCD: Engagement metrics failed: {e}")
        return defaults


def _calculate_quality_metrics():
    """
    Calculate quality metrics from QualityMetricAggregate.

    Averages usefulness_score from last 4 weeks and sums suppressed counts.

    Returns:
        dict with avg_usefulness_score and total_suppressed.
    """
    defaults = {
        "avg_usefulness_score": 0.0,
        "total_suppressed": 0,
    }

    try:
        from apps.core.ai_quality.quality_models import QualityMetricAggregate

        cutoff = timezone.now().date() - timedelta(weeks=4)
        aggregates = QualityMetricAggregate.objects.filter(
            week_start__gte=cutoff,
        )
        if not aggregates.exists():
            return defaults

        result = aggregates.aggregate(
            avg_usefulness=Avg("usefulness_score"),
            total_suppressed=Count(
                "id",
                filter=Q(suppressed_count__gt=0),
            ),
        )

        # Sum actual suppressed counts
        from django.db.models import Sum

        suppressed_sum = aggregates.aggregate(
            total=Sum("suppressed_count")
        )

        return {
            "avg_usefulness_score": round(
                result["avg_usefulness"] or 0.0, 4
            ),
            "total_suppressed": suppressed_sum["total"] or 0,
        }
    except Exception as e:
        logger.warning(f"IOCD: Quality metrics failed: {e}")
        return defaults


def _calculate_persona_metrics():
    """
    Calculate persona effectiveness by grouping GuidanceItem
    action/dismiss rates by user's ai_coaching_style.

    Returns:
        dict with persona_effectiveness_scores JSON.
    """
    defaults = {
        "persona_effectiveness_scores": {},
    }

    try:
        from apps.core.ai_guidance.models import GuidanceItem

        # Get guidance items with user coaching style
        items = (
            GuidanceItem.objects.select_related("user__preferences")
            .values("user__preferences__ai_coaching_style")
            .annotate(
                total=Count("id"),
                acted=Count("id", filter=Q(acted_upon_at__isnull=False)),
                dismissed=Count("id", filter=Q(dismissed_at__isnull=False)),
            )
        )

        scores = {}
        for row in items:
            style = row["user__preferences__ai_coaching_style"] or "supportive"
            total = row["total"]
            acted = row["acted"]
            dismissed = row["dismissed"]

            scores[style] = {
                "total": total,
                "acted": acted,
                "dismissed": dismissed,
                "action_rate": round(acted / total, 4) if total > 0 else 0.0,
                "dismiss_rate": round(
                    dismissed / total, 4
                ) if total > 0 else 0.0,
            }

        return {"persona_effectiveness_scores": scores}
    except Exception as e:
        logger.warning(f"IOCD: Persona metrics failed: {e}")
        return defaults
