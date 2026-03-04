"""
Celery tasks for the Health Intelligence Engine.

Tasks:
    - build_nightly_health_summaries: Runs nightly at 3:00 AM UTC.
      Builds yesterday's summary + rescans last 7 days for all active users.
    - build_user_health_summary: Build summary for one user/date (on-demand).
"""

import logging
from datetime import date, timedelta

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger("celery.tasks")


@shared_task(
    name="health.build_nightly_health_summaries",
    bind=True,
    max_retries=1,
    soft_time_limit=600,   # 10 minutes
    time_limit=660,        # 11 minutes hard
    acks_late=True,
)
def build_nightly_health_summaries(self):
    """
    Nightly task: build DailyHealthSummary + scores for all active users.

    - Yesterday: full build (summary + scores)
    - Last 7 days: rebuild summaries + scores (catch late-arriving HealthKit data)

    Scheduled via Celery Beat at 3:00 AM UTC.
    """
    from django.contrib.auth import get_user_model

    from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
    from apps.health.services.score_pipeline import ScorePipeline

    User = get_user_model()
    builder = DailyHealthSummaryBuilder()

    yesterday = date.today() - timedelta(days=1)
    rebuild_start = date.today() - timedelta(days=7)

    users = User.objects.filter(is_active=True)
    total = 0
    errors = 0

    for user in users.iterator():
        try:
            # Rebuild last 7 days
            current = rebuild_start
            while current <= yesterday:
                try:
                    builder.build_for_date(user, current)
                    ScorePipeline.compute_scores(user, current)
                    total += 1
                except SoftTimeLimitExceeded:
                    raise  # Don't catch time limits
                except Exception:
                    errors += 1
                    logger.error(
                        "Failed to build summary for %s on %s",
                        user.email, current, exc_info=True,
                    )
                current += timedelta(days=1)

        except SoftTimeLimitExceeded:
            logger.warning(
                "Nightly health summary task hit time limit after %d summaries", total
            )
            break
        except Exception:
            errors += 1
            logger.error(
                "Error processing user %s", user.email, exc_info=True,
            )

    logger.info(
        "Nightly health summaries complete: %d built, %d errors", total, errors
    )
    return {"built": total, "errors": errors}


@shared_task(
    name="health.build_user_health_summary",
    bind=True,
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
)
def build_user_health_summary(self, user_id, target_date_str=None):
    """
    On-demand task: build summary for one user on one date.

    Args:
        user_id: User ID
        target_date_str: "YYYY-MM-DD" or None for yesterday
    """
    from django.contrib.auth import get_user_model

    from apps.health.services.score_pipeline import ScorePipeline

    User = get_user_model()

    try:
        user = User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        logger.warning("User %s not found or inactive", user_id)
        return {"status": "user_not_found"}

    if target_date_str:
        from datetime import datetime
        target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    else:
        target = date.today() - timedelta(days=1)

    try:
        summary = ScorePipeline.full_build(user, target)
        logger.info("Built health summary for %s on %s", user.email, target)
        return {
            "status": "success",
            "user": user.email,
            "date": str(target),
            "health_score": summary.health_score if summary else None,
        }
    except Exception as exc:
        logger.error(
            "Failed to build health summary for %s on %s",
            user.email, target, exc_info=True,
        )
        raise self.retry(exc=exc, countdown=30)
