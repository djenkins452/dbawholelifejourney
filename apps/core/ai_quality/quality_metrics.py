"""
ICQG — Quality Metrics Aggregation.

Weekly aggregation job that computes usefulness_score per rule/domain.

Usefulness formula:
  acted_rate * 0.40 + acknowledged_rate * 0.15
  - dismissed_rate * 0.20 - snoozed_rate * 0.05
  + response_speed_bonus * 0.20

Clamped to [0.0, 1.0].
"""

import logging
from datetime import timedelta

from django.db.models import Avg, Count, F, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# Weights for usefulness score
W_ACTED = 0.40
W_ACKNOWLEDGED = 0.15
W_DISMISSED = -0.20
W_SNOOZED = -0.05
W_RESPONSE_SPEED = 0.20

# Fast response threshold (seconds) — responses under this get full bonus
FAST_RESPONSE_SECONDS = 3600  # 1 hour
# Slow response threshold — responses over this get no bonus
SLOW_RESPONSE_SECONDS = 86400  # 24 hours


def aggregate_weekly_metrics():
    """
    Compute weekly quality metrics for all rule/domain combinations.

    Scans GuidanceItem actions from the past week and aggregates
    per guidance_type + module.

    Returns:
        dict — {created: int, updated: int, errors: int}
    """
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        from apps.core.ai_quality.quality_models import QualityMetricAggregate

        now = timezone.now()
        week_start = (now - timedelta(days=7)).date()
        # Align to Monday
        week_start = week_start - timedelta(days=week_start.weekday())
        week_end = week_start + timedelta(days=7)

        # Get all guidance items from the past week
        items = GuidanceItem.objects.filter(
            created_at__date__gte=week_start,
            created_at__date__lt=week_end,
        ).values(
            "guidance_type", "module"
        ).annotate(
            total=Count("id"),
            acted=Count("id", filter=Q(acted_upon_at__isnull=False)),
            dismissed=Count("id", filter=Q(dismissed_at__isnull=False)),
            snoozed=Count("id", filter=Q(snoozed_until__isnull=False)),
            acknowledged=Count("id", filter=Q(acknowledged_at__isnull=False)),
        )

        created = 0
        updated = 0
        errors = 0

        for row in items:
            try:
                rule_type = row["guidance_type"] or "unknown"
                domain = row["module"] or "general"
                total = row["total"]

                if total == 0:
                    continue

                acted_rate = row["acted"] / total
                dismissed_rate = row["dismissed"] / total
                snoozed_rate = row["snoozed"] / total
                acknowledged_rate = row["acknowledged"] / total

                # Compute average response time for acted items
                avg_response = _compute_avg_response_time(
                    rule_type, domain, week_start, week_end
                )
                response_bonus = _response_speed_bonus(avg_response)

                # Compute usefulness score
                score = (
                    acted_rate * W_ACTED
                    + acknowledged_rate * W_ACKNOWLEDGED
                    + dismissed_rate * W_DISMISSED
                    + snoozed_rate * W_SNOOZED
                    + response_bonus * W_RESPONSE_SPEED
                )
                # Clamp to [0.0, 1.0]
                score = max(0.0, min(1.0, score + 0.5))  # Base at 0.5

                # Count suppressions
                suppressed = _count_suppressions(rule_type, week_start, week_end)

                obj, was_created = QualityMetricAggregate.objects.update_or_create(
                    week_start=week_start,
                    rule_type=rule_type,
                    domain=domain,
                    defaults={
                        "delivered_count": total,
                        "acted_count": row["acted"],
                        "dismissed_count": row["dismissed"],
                        "snoozed_count": row["snoozed"],
                        "acknowledged_count": row["acknowledged"],
                        "suppressed_count": suppressed,
                        "avg_response_seconds": avg_response,
                        "usefulness_score": round(score, 3),
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

            except Exception as e:
                errors += 1
                logger.error(f"ICQG: Metric aggregation error for {row}: {e}")

        logger.info(
            f"ICQG: Metrics aggregation complete — "
            f"created={created}, updated={updated}, errors={errors}"
        )
        return {"created": created, "updated": updated, "errors": errors}

    except Exception as e:
        logger.error(f"ICQG: Weekly metrics aggregation failed: {e}", exc_info=True)
        return {"created": 0, "updated": 0, "errors": 1}


def _compute_avg_response_time(rule_type, domain, week_start, week_end):
    """
    Compute average response time (in seconds) for acted guidance items.

    Response time = acted_upon_at - created_at.
    """
    try:
        from apps.core.ai_guidance.models import GuidanceItem

        acted_items = GuidanceItem.objects.filter(
            guidance_type=rule_type,
            module=domain,
            created_at__date__gte=week_start,
            created_at__date__lt=week_end,
            acted_upon_at__isnull=False,
        ).annotate(
            response_time=F("acted_upon_at") - F("created_at")
        )

        if not acted_items.exists():
            return None

        total_seconds = sum(
            item.response_time.total_seconds() for item in acted_items
        )
        return total_seconds / acted_items.count()

    except Exception:
        return None


def _response_speed_bonus(avg_seconds):
    """
    Compute a speed bonus (0.0-1.0) based on average response time.

    Fast responses (< 1 hour) get full bonus.
    Slow responses (> 24 hours) get no bonus.
    """
    if avg_seconds is None:
        return 0.0

    if avg_seconds <= FAST_RESPONSE_SECONDS:
        return 1.0
    if avg_seconds >= SLOW_RESPONSE_SECONDS:
        return 0.0

    # Linear interpolation
    return 1.0 - (avg_seconds - FAST_RESPONSE_SECONDS) / (
        SLOW_RESPONSE_SECONDS - FAST_RESPONSE_SECONDS
    )


def _count_suppressions(rule_type, week_start, week_end):
    """Count how many times this rule type was suppressed this week."""
    try:
        from apps.core.ai_quality.quality_models import QualitySuppressionRecord

        return QualitySuppressionRecord.objects.filter(
            last_seen_at__date__gte=week_start,
            last_seen_at__date__lt=week_end,
        ).count()
    except Exception:
        return 0
