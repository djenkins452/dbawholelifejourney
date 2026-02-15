"""
Insight Engine — Event-driven + safe insight generation.

Accepts events from the orchestrator after successful actions,
runs applicable rules, stores insights, and triggers notifications.
"""

import logging

from django.conf import settings

from apps.core.ai_insights.models import Insight
from apps.core.ai_insights.notification_engine import maybe_notify
from apps.core.ai_insights.rule_registry import get_rules

logger = logging.getLogger(__name__)


def run_insights(user, event):
    """
    Run all applicable insight rules for an event.

    Args:
        user: Django user instance.
        event: Dict with:
            - event_type: "record_created"|"record_updated"|"scheduled_check"
            - module: "health"|"goals"|"scripture"|...
            - action: "update_weight"|"log_habit"|...
            - record_id: Optional record ID
            - timestamp_utc: ISO timestamp
            - user_timezone: IANA timezone
            - context: Optional additional context dict

    Returns:
        List of created/updated Insight instances.
    """
    # Check if insights are enabled
    if not getattr(settings, "AI_INSIGHTS_ENABLED", True):
        return []

    created = []

    for rule in get_rules():
        try:
            if not rule.applies(user, event):
                continue

            insights = rule.evaluate(user, event)

            for insight_data in insights:
                confidence = insight_data.get("confidence_score", 0.0)

                # Only store if meets minimum threshold
                if confidence < rule.min_confidence_to_store:
                    continue

                insight_obj = _upsert_insight(user, rule, insight_data)
                if insight_obj:
                    created.append(insight_obj)

                    # Notify if meets notification threshold
                    if confidence >= rule.min_confidence_to_notify:
                        maybe_notify(user, insight_obj)

        except Exception as e:
            # Rule failures must never break the main flow
            logger.error(
                f"Insight rule '{rule.rule_name}' failed for user {user.id}: {e}",
                exc_info=True,
            )

    # Fire prediction generation after insight generation
    _trigger_predictions(user, event)

    return created


def _trigger_predictions(user, event):
    """
    Fire prediction generation after insight processing.
    Failures must never break the insight pipeline.
    """
    try:
        from apps.core.ai_predictions.prediction_engine import generate_predictions

        module = event.get("module")
        record_id = event.get("record_id")
        generate_predictions(user, module=module, record_id=record_id)
    except Exception as e:
        logger.error(
            f"Prediction generation failed for user {user.id}: {e}",
            exc_info=True,
        )


def _upsert_insight(user, rule, insight_data):
    """
    Create or update an insight using dedupe_key.

    If same dedupe_key exists and status != dismissed, update instead of create.
    """
    dedupe_key = insight_data.get("dedupe_key", "")

    if not dedupe_key:
        logger.warning(f"Rule {rule.rule_name} returned insight without dedupe_key")
        return None

    # Check for existing non-dismissed insight with same key
    existing = Insight.objects.filter(
        dedupe_key=dedupe_key,
        user=user,
    ).exclude(status="dismissed").first()

    if existing:
        # Update existing insight
        existing.confidence_score = insight_data.get(
            "confidence_score", existing.confidence_score
        )
        existing.message = insight_data.get("message", existing.message)
        existing.evidence = insight_data.get("evidence", existing.evidence)
        existing.explain_why = insight_data.get("explain_why", existing.explain_why)
        existing.severity = insight_data.get("severity", existing.severity)
        existing.save(
            update_fields=[
                "confidence_score",
                "message",
                "evidence",
                "explain_why",
                "severity",
                "updated_at",
            ]
        )
        return existing

    # Create new insight
    return Insight.objects.create(
        user=user,
        module=rule.module,
        insight_type=rule.insight_type,
        severity=insight_data.get("severity", "info"),
        title=insight_data.get("title", ""),
        message=insight_data.get("message", ""),
        confidence_score=insight_data.get("confidence_score", 0.0),
        explain_why=insight_data.get("explain_why", ""),
        evidence=insight_data.get("evidence", {}),
        dedupe_key=dedupe_key,
    )
