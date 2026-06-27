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
    name="health.deferred_rebuild_health_summary",
    bind=True,
    max_retries=1,
    soft_time_limit=30,
    time_limit=45,
    acks_late=True,
)
def deferred_rebuild_health_summary(self, user_id, date_iso):
    """Class A post-write hook — defer DailyHealthSummaryBuilder off
    the request thread.

    Called via `.delay()` from `on_health_event_invalidate_state` for
    Class A health events (water, weight, medication, workout, etc.)
    so the user's dashboard reload doesn't block on the summary rebuild
    (was ~1.5–3s synchronous; now <50ms enqueue from the request).

    Class B health events (glucose, BP, sync_completed) still run the
    builder synchronously — see `SYNC_HEALTH_EVENTS` in
    `apps/core/events/subscribers.py` for the safety-critical list.

    Idempotent: the underlying builder uses update_or_create on
    DailyHealthSummary. Safe to retry; safe if the row already exists.

    Args:
        user_id: User PK
        date_iso: ISO date string ("YYYY-MM-DD") to build for —
                  callers pass today's date in the user's timezone.
    """
    from datetime import date as _date
    from django.contrib.auth import get_user_model

    from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

    User = get_user_model()
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return {"status": "user_not_found", "user_id": user_id}

    try:
        target = _date.fromisoformat(date_iso)
    except (TypeError, ValueError):
        return {"status": "bad_date", "date_iso": date_iso}

    try:
        DailyHealthSummaryBuilder().build_for_date(user, target)
        return {"status": "ok", "user_id": user_id, "date": date_iso}
    except SoftTimeLimitExceeded:
        logger.warning(
            "deferred_rebuild_health_summary soft-time-limit: user=%s date=%s",
            user_id, date_iso,
        )
        return {"status": "soft_timeout", "user_id": user_id, "date": date_iso}
    except Exception as exc:
        logger.error(
            "deferred_rebuild_health_summary failed: user=%s date=%s",
            user_id, date_iso, exc_info=True,
        )
        # Single retry — if it fails again, log and move on. The next
        # health event will re-enqueue, and the nightly job is the
        # ultimate safety net.
        try:
            raise self.retry(exc=exc, countdown=20)
        except Exception:
            return {"status": "failed", "user_id": user_id, "date": date_iso}


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


# ── Guided Capture background processing ──────────────────────────────────────
# Moves Vision off the web request path: the view creates a MedicationCaptureSession
# and returns immediately; this task analyzes the images, updates progress, and
# stages one MedicationScanDraft via the existing acquisition pipeline. The UI polls
# the session. Reuses the Celery worker (no new queue).

CAPTURE_MAX_RETRIES = 2


def _capture_retryable(exc):
    msg = str(exc).lower()
    return any(s in msg for s in (
        "timeout", "timed out", "rate limit", "429", "503", "502",
        "temporarily", "connection", "unavailable",
    ))


@shared_task(
    name="health.process_medication_capture",
    bind=True,
    max_retries=CAPTURE_MAX_RETRIES,
    soft_time_limit=300,   # 5 min — bounded multi-image Vision
    time_limit=330,
    acks_late=True,
    default_retry_delay=5,
)
def process_medication_capture(self, session_id, retry_count=0):
    """Analyze one Guided Capture session off the request path."""
    from apps.health.models import MedicationCaptureSession
    from apps.health.capture_session import process_capture_session

    try:
        session = MedicationCaptureSession.objects.get(id=session_id)
    except MedicationCaptureSession.DoesNotExist:
        logger.error("capture session %s not found", session_id)
        return {"success": False, "session_id": session_id, "reason": "not_found"}

    # Don't reprocess a finished/cancelled session.
    if session.processing_status in (MedicationCaptureSession.STATUS_READY,
                          MedicationCaptureSession.STATUS_CANCELLED):
        return {"success": True, "session_id": session_id, "reason": "already_done"}

    try:
        draft = process_capture_session(session)
        return {
            "success": draft is not None,
            "session_id": session_id,
            "draft_id": draft.id if draft else None,
        }
    except SoftTimeLimitExceeded:
        logger.error("capture session %s timed out", session_id)
        session.mark_failed("Analysis took too long. Please retry.")
        return {"success": False, "session_id": session_id, "reason": "timeout"}
    except Exception as exc:
        logger.error("capture session %s failed: %s", session_id, exc, exc_info=True)
        if _capture_retryable(exc) and retry_count < CAPTURE_MAX_RETRIES:
            backoff = min(2 ** (retry_count + 1), 20)
            session.current_step = "Hit a snag — retrying…"
            session.save(update_fields=["current_step", "updated_at"])
            raise self.retry(countdown=backoff,
                             kwargs={"session_id": session_id,
                                     "retry_count": retry_count + 1})
        session.mark_failed("We couldn't analyze your photos. Please retry.")
        return {"success": False, "session_id": session_id, "reason": "error"}
