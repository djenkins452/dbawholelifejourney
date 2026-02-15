"""
WIRE — Report Logger.

Stores weekly reports with deduplication (one per user per week).
"""

import logging

from django.db import IntegrityError

from apps.core.ai_weekly_report.models import WeeklyIntelligenceReport

logger = logging.getLogger(__name__)


def store_weekly_report(
    user,
    week_start,
    week_end,
    summary,
    state_delta_snapshot=None,
    insight_snapshot=None,
    prediction_snapshot=None,
    guidance_snapshot=None,
    learning_snapshot=None,
):
    """
    Store a weekly intelligence report with deduplication.

    If a report already exists for this user + week, returns the existing one.

    Args:
        user: Django User instance.
        week_start: date — Monday of the report week.
        week_end: date — Sunday of the report week.
        summary: str — natural language summary.
        *_snapshot: dict — JSON snapshots of each intelligence source.

    Returns:
        WeeklyIntelligenceReport instance.
    """
    # Check for existing report
    existing = WeeklyIntelligenceReport.objects.filter(
        user=user,
        week_start_date=week_start,
    ).first()

    if existing:
        logger.debug(
            f"WIRE: Report already exists for user {user.id}, "
            f"week {week_start}"
        )
        return existing

    try:
        report = WeeklyIntelligenceReport.objects.create(
            user=user,
            week_start_date=week_start,
            week_end_date=week_end,
            summary=summary,
            state_delta_snapshot=state_delta_snapshot or {},
            insight_snapshot=insight_snapshot or {},
            prediction_snapshot=prediction_snapshot or {},
            guidance_snapshot=guidance_snapshot or {},
            learning_snapshot=learning_snapshot or {},
        )
        logger.info(
            f"WIRE: Created weekly report for user {user.id}, "
            f"week {week_start}"
        )
        return report

    except IntegrityError:
        # Race condition — another process created it
        logger.debug(
            f"WIRE: Race condition for user {user.id}, week {week_start}"
        )
        return WeeklyIntelligenceReport.objects.filter(
            user=user,
            week_start_date=week_start,
        ).first()
