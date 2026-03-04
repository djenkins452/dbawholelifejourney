"""
Score Pipeline — orchestrates recovery score and health score computation
after the DailyHealthSummary rollup is complete.

Separates the summary builder (data aggregation) from scoring (analysis)
so each can be tested and debugged independently.

Usage:
    from apps.health.services.score_pipeline import ScorePipeline
    ScorePipeline.compute_scores(user, date.today())
    ScorePipeline.compute_scores_range(user, start, end)
"""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


class ScorePipeline:
    """Orchestrate recovery + health score computation for DailyHealthSummary rows."""

    @staticmethod
    def compute_scores(user, target_date):
        """
        Compute and persist recovery_score and health_score for one date.

        Expects DailyHealthSummary to already exist for that date.
        Returns the updated DailyHealthSummary instance or None.
        """
        from apps.health.models import DailyHealthSummary
        from apps.health.services.health_score import HealthScoreService
        from apps.health.services.recovery_score import RecoveryScoreService

        summary = (
            DailyHealthSummary.objects
            .filter(user=user, summary_date=target_date)
            .first()
        )
        if not summary:
            logger.debug("No DailyHealthSummary for %s on %s", user.email, target_date)
            return None

        # Recovery score
        try:
            recovery_score, recovery_drivers = RecoveryScoreService.compute(user, target_date)
            summary.recovery_score = recovery_score
            summary.recovery_drivers = recovery_drivers
        except Exception:
            logger.error(
                "Failed to compute recovery score for %s on %s",
                user.email, target_date, exc_info=True,
            )

        # Health score
        try:
            health_score, health_drivers = HealthScoreService.compute(user, target_date)
            summary.health_score = health_score
            summary.health_score_drivers = health_drivers
        except Exception:
            logger.error(
                "Failed to compute health score for %s on %s",
                user.email, target_date, exc_info=True,
            )

        summary.save(update_fields=[
            "recovery_score", "recovery_drivers",
            "health_score", "health_score_drivers",
            "last_computed",
        ])

        logger.info(
            "Scores computed for %s on %s: health=%s recovery=%s",
            user.email, target_date, summary.health_score, summary.recovery_score,
        )
        return summary

    @staticmethod
    def compute_scores_range(user, start_date, end_date):
        """Compute scores for a date range (inclusive)."""
        current = start_date
        count = 0
        while current <= end_date:
            try:
                result = ScorePipeline.compute_scores(user, current)
                if result:
                    count += 1
            except Exception:
                logger.error(
                    "Score pipeline failed for %s on %s",
                    user.email, current, exc_info=True,
                )
            current += timedelta(days=1)
        return count

    @staticmethod
    def full_build(user, target_date):
        """
        Full pipeline: build summary + compute scores in one call.
        Convenience method for the management command and Celery task.
        """
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        builder = DailyHealthSummaryBuilder()
        summary = builder.build_for_date(user, target_date)
        ScorePipeline.compute_scores(user, target_date)
        return summary

    @staticmethod
    def full_build_range(user, start_date, end_date):
        """Build summaries + scores for a date range."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        builder = DailyHealthSummaryBuilder()
        current = start_date
        count = 0
        while current <= end_date:
            try:
                builder.build_for_date(user, current)
                ScorePipeline.compute_scores(user, current)
                count += 1
            except Exception:
                logger.error(
                    "Full build failed for %s on %s",
                    user.email, current, exc_info=True,
                )
            current += timedelta(days=1)
        return count
