"""
DNE — Delivery Engine.

Main entry point for the Delivery & Notification Engine.
Identifies new intelligence outputs and routes them through channels.
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def deliver_due_notifications():
    """
    Run one delivery cycle.

    Identifies undelivered intelligence items (PGE guidance, DBE briefings,
    WIRE weekly reports) and routes them to user-enabled channels.

    Returns:
        dict with counts: {"delivered": int, "skipped": int, "failed": int}
    """
    result = {"delivered": 0, "skipped": 0, "failed": 0}

    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # Get users who have AI features (active users)
        users = User.objects.filter(
            is_active=True,
            preferences__ai_enabled=True,
        ).select_related("preferences")

        for user in users:
            try:
                user_result = _deliver_for_user(user)
                result["delivered"] += user_result["delivered"]
                result["skipped"] += user_result["skipped"]
                result["failed"] += user_result["failed"]
            except Exception as e:
                logger.error(f"DNE: Failed for user {user.id}: {e}")
                result["failed"] += 1

    except Exception as e:
        logger.error(f"DNE: Delivery cycle failed: {e}", exc_info=True)

    logger.info(
        f"DNE: Cycle complete — delivered={result['delivered']}, "
        f"skipped={result['skipped']}, failed={result['failed']}"
    )
    return result


def deliver_single(user, source_engine, source_object):
    """
    Deliver a single intelligence item immediately (called from pipeline hooks).

    Non-blocking — failures are logged but never raised.
    """
    try:
        payload = _build_payload(source_engine, source_object)
        if not payload:
            return

        channels = _get_enabled_channels(user)
        obj_type = type(source_object).__name__
        obj_id = source_object.id

        for channel in channels:
            _deliver_to_channel(user, channel, payload, source_engine, obj_type, obj_id)

    except Exception as e:
        logger.error(f"DNE: deliver_single failed for user {user.id}: {e}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _deliver_for_user(user):
    """Identify and deliver undelivered intelligence items for one user."""
    result = {"delivered": 0, "skipped": 0, "failed": 0}
    channels = _get_enabled_channels(user)

    if not channels:
        return result

    # Gather deliverable items
    items = []
    items.extend(_get_undelivered_guidance(user))
    items.extend(_get_undelivered_briefings(user))
    items.extend(_get_undelivered_reports(user))

    # ICQG quality gate (non-blocking)
    try:
        from apps.core.ai_quality.quality_gate import filter_delivery_candidates
        items = filter_delivery_candidates(user, items)
    except Exception as e:
        logger.warning(f"DNE: ICQG filter failed (continuing): {e}")

    for engine, obj_type, obj_id, payload in items:
        for channel in channels:
            delivered = _deliver_to_channel(
                user, channel, payload, engine, obj_type, obj_id,
            )
            if delivered is True:
                result["delivered"] += 1
            elif delivered is False:
                result["skipped"] += 1
            else:
                result["failed"] += 1

    return result


def _deliver_to_channel(user, channel, payload, source_engine, obj_type, obj_id):
    """
    Apply policies and deliver to a single channel.

    Returns: True=sent, False=skipped, None=failed
    """
    from apps.core.ai_delivery.delivery_policies import apply_delivery_policies
    from apps.core.ai_delivery.delivery_router import CHANNEL_HANDLERS
    from apps.core.ai_delivery.delivery_logger import log_skip

    # Policy check
    passed, skip_reason = apply_delivery_policies(
        user, channel, source_engine, obj_type, obj_id,
    )
    if not passed:
        log_skip(user, channel, source_engine, obj_type, obj_id,
                 payload, skip_reason)
        return False

    # Route to channel
    handler = CHANNEL_HANDLERS.get(channel)
    if not handler:
        logger.warning(f"DNE: No handler for channel {channel}")
        return None

    record = handler(user, payload, source_engine, obj_type, obj_id)
    return True if record else None


def _get_enabled_channels(user):
    """Get list of channels the user has enabled for intelligence notifications."""
    channels = []

    try:
        prefs = user.preferences
    except Exception:
        return ["in_app"]  # Default to in-app only

    # In-app: always enabled unless master toggle is off
    if getattr(prefs, "notifications_enabled", True):
        if getattr(prefs, "intelligence_inapp_enabled", True):
            channels.append("in_app")

    # Email: opt-in (default off)
    if getattr(prefs, "email_notifications_enabled", False):
        if getattr(prefs, "intelligence_email_enabled", False):
            channels.append("email")

    # SMS: opt-in (default off), requires verified phone
    if getattr(prefs, "sms_enabled", False) and getattr(prefs, "phone_verified", False):
        if getattr(prefs, "intelligence_sms_enabled", False):
            channels.append("sms")

    return channels


def _build_payload(engine, obj):
    """Build notification payload from an intelligence object."""
    obj_type = type(obj).__name__

    if obj_type == "GuidanceItem":
        return {
            "title": f"New Guidance: {obj.title[:80]}",
            "message": obj.message[:300] if obj.message else obj.title,
            "action_url": f"/guidance/inbox/",
            "icon": "💡",
        }

    elif obj_type == "DailyBriefing":
        summary = ""
        if obj.summary_text:
            summary = obj.summary_text[:300]
        return {
            "title": "Your Daily Briefing is Ready",
            "message": summary or "Your intelligence briefing for today has been generated.",
            "action_url": "/dashboard/",
            "icon": "📋",
        }

    elif obj_type == "WeeklyIntelligenceReport":
        summary = ""
        if obj.summary_text:
            summary = obj.summary_text[:300]
        return {
            "title": "Weekly Intelligence Report",
            "message": summary or "Your weekly intelligence report is ready.",
            "action_url": f"/intelligence/weekly/{obj.id}/",
            "icon": "📊",
        }

    logger.warning(f"DNE: Unknown object type: {obj_type}")
    return None


def _get_undelivered_guidance(user):
    """Get active, non-dismissed guidance items not yet delivered via in_app."""
    items = []
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        from apps.core.ai_delivery.models import DeliveredNotification

        # Get active guidance from last 24 hours that hasn't been dismissed
        cutoff = timezone.now() - timezone.timedelta(hours=24)
        guidance = GuidanceItem.objects.filter(
            user=user,
            dismissed_at__isnull=True,
            is_active=True,
            created_at__gte=cutoff,
        ).order_by("-created_at")[:10]

        for item in guidance:
            payload = _build_payload("PGE", item)
            if payload:
                items.append(("PGE", "GuidanceItem", item.id, payload))

    except Exception as e:
        logger.error(f"DNE: Failed to get guidance for user {user.id}: {e}")

    return items


def _get_undelivered_briefings(user):
    """Get today's briefing if not yet delivered."""
    items = []
    try:
        from apps.core.ai_briefing.models import DailyBriefing

        today = timezone.now().date()
        briefing = DailyBriefing.objects.filter(
            user=user,
            briefing_date=today,
        ).first()

        if briefing:
            payload = _build_payload("DBE", briefing)
            if payload:
                items.append(("DBE", "DailyBriefing", briefing.id, payload))

    except Exception as e:
        logger.error(f"DNE: Failed to get briefing for user {user.id}: {e}")

    return items


def _get_undelivered_reports(user):
    """Get this week's report if not yet delivered."""
    items = []
    try:
        from apps.core.ai_weekly_report.models import WeeklyIntelligenceReport
        from datetime import timedelta

        # Look for reports created in the last 7 days
        cutoff = timezone.now() - timedelta(days=7)
        report = WeeklyIntelligenceReport.objects.filter(
            user=user,
            created_at__gte=cutoff,
        ).first()

        if report:
            payload = _build_payload("WIRE", report)
            if payload:
                items.append(("WIRE", "WeeklyIntelligenceReport", report.id, payload))

    except Exception as e:
        logger.error(f"DNE: Failed to get weekly report for user {user.id}: {e}")

    return items
