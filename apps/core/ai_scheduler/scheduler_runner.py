"""
ISE — Scheduler Runner.

Task runner functions that call existing intelligence engines.
Each function wraps an engine's public API — no logic duplication.
"""

import logging

from apps.users.models import User

logger = logging.getLogger(__name__)


def _get_active_ai_users():
    """
    Get all active users with AI enabled.

    Returns:
        QuerySet of User instances.
    """
    return User.objects.filter(
        is_active=True,
        preferences__ai_enabled=True,
    ).select_related("preferences")


def run_daily_briefings():
    """
    Generate daily briefings for all active AI users.

    Calls DBE generate_daily_briefing() for each user.

    Returns:
        dict — {generated: int, errors: int}
    """
    try:
        from apps.core.ai_briefing.briefing_engine import generate_daily_briefing
    except ImportError:
        logger.error("ISE: DBE not available (import failed)")
        return {"generated": 0, "errors": 0}

    users = _get_active_ai_users()
    generated = 0
    errors = 0

    for user in users:
        try:
            result = generate_daily_briefing(user)
            if result:
                generated += 1
        except Exception as e:
            errors += 1
            logger.error(f"ISE: DBE failed for user {user.id}: {e}")

    logger.info(f"ISE: Daily briefings — generated={generated}, errors={errors}")
    return {"generated": generated, "errors": errors}


def run_learning_profile_updates():
    """
    Recalculate GLOE learning profiles for all active AI users.

    Calls GLOE update_learning_profile() for each user.

    Returns:
        dict — {updated: int, errors: int}
    """
    try:
        from apps.core.ai_guidance_learning.learning_engine import update_learning_profile
    except ImportError:
        logger.error("ISE: GLOE not available (import failed)")
        return {"updated": 0, "errors": 0}

    users = _get_active_ai_users()
    updated = 0
    errors = 0

    for user in users:
        try:
            update_learning_profile(user)
            updated += 1
        except Exception as e:
            errors += 1
            logger.error(f"ISE: GLOE failed for user {user.id}: {e}")

    logger.info(f"ISE: Learning profiles — updated={updated}, errors={errors}")
    return {"updated": updated, "errors": errors}


def run_guidance_refresh():
    """
    Refresh proactive guidance for all active AI users.

    Calls PGE generate_guidance() for each user.
    Also expires old guidance items.

    Returns:
        dict — {refreshed: int, expired: int, errors: int}
    """
    try:
        from apps.core.ai_guidance.guidance_engine import (
            expire_old_guidance,
            generate_guidance,
        )
    except ImportError:
        logger.error("ISE: PGE not available (import failed)")
        return {"refreshed": 0, "expired": 0, "errors": 0}

    # Step 1: Expire old guidance globally
    expired = expire_old_guidance()

    # Step 2: Generate fresh guidance per user
    users = _get_active_ai_users()
    refreshed = 0
    errors = 0

    for user in users:
        try:
            items = generate_guidance(user)
            if items:
                refreshed += 1
        except Exception as e:
            errors += 1
            logger.error(f"ISE: PGE failed for user {user.id}: {e}")

    logger.info(
        f"ISE: Guidance refresh — refreshed={refreshed}, "
        f"expired={expired}, errors={errors}"
    )
    return {"refreshed": refreshed, "expired": expired or 0, "errors": errors}


def run_weekly_reports():
    """
    Generate weekly intelligence reports for all active AI users.

    Calls WIRE generate_weekly_report() for each user.

    Returns:
        dict — {generated: int, errors: int}
    """
    try:
        from apps.core.ai_weekly_report.report_engine import generate_weekly_report
    except ImportError:
        logger.error("ISE: WIRE not available (import failed)")
        return {"generated": 0, "errors": 0}

    users = _get_active_ai_users()
    generated = 0
    errors = 0

    for user in users:
        try:
            result = generate_weekly_report(user)
            if result:
                generated += 1
        except Exception as e:
            errors += 1
            logger.error(f"ISE: WIRE failed for user {user.id}: {e}")

    logger.info(f"ISE: Weekly reports — generated={generated}, errors={errors}")
    return {"generated": generated, "errors": errors}


def run_delivery_cycle():
    """
    Run one cycle of the Delivery & Notification Engine.

    Calls DNE deliver_due_notifications() to route intelligence
    outputs to user-configured channels.

    Returns:
        dict — {delivered: int, skipped: int, failed: int}
    """
    try:
        from apps.core.ai_delivery.delivery_engine import deliver_due_notifications
    except ImportError:
        logger.error("ISE: DNE not available (import failed)")
        return {"delivered": 0, "skipped": 0, "failed": 0}

    result = deliver_due_notifications()
    logger.info(
        f"ISE: Delivery cycle — delivered={result['delivered']}, "
        f"skipped={result['skipped']}, failed={result['failed']}"
    )
    return result


def run_quality_metrics_aggregation():
    """
    Aggregate ICQG quality metrics for all rule/domain combinations.

    Calls ICQG aggregate_weekly_metrics() to compute usefulness scores.

    Returns:
        dict — {created: int, updated: int, errors: int}
    """
    try:
        from apps.core.ai_quality.quality_metrics import aggregate_weekly_metrics
    except ImportError:
        logger.error("ISE: ICQG not available (import failed)")
        return {"created": 0, "updated": 0, "errors": 0}

    result = aggregate_weekly_metrics()
    logger.info(
        f"ISE: Quality metrics — created={result['created']}, "
        f"updated={result['updated']}, errors={result['errors']}"
    )
    return result


def run_observability_snapshot():
    """
    Generate daily intelligence observability metrics snapshot.

    Calls IOCD generate_daily_snapshot() — system-wide, not per-user.

    Returns:
        dict — {generated: int, errors: int}
    """
    try:
        from apps.core.ai_observability.observability_engine import (
            generate_daily_snapshot,
        )
    except ImportError:
        logger.error("ISE: IOCD not available (import failed)")
        return {"generated": 0, "errors": 0}

    result = generate_daily_snapshot()
    if result:
        logger.info(f"ISE: Observability snapshot generated for {result.snapshot_date}")
        return {"generated": 1, "errors": 0}
    else:
        logger.warning("ISE: Observability snapshot generation failed")
        return {"generated": 0, "errors": 1}
