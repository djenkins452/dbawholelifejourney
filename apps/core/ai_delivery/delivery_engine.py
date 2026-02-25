"""
DNE — Delivery Engine.

Main entry point for the Delivery & Notification Engine.
Identifies new intelligence outputs and routes them through channels.
"""

import logging

from django.utils import timezone

from apps.core.ai_observability.instrumentation import log_engine_run as _instrument_engine_run

logger = logging.getLogger(__name__)


@_instrument_engine_run("DNE", 3)
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


def deliver_single(user, source_engine, source_object, payload=None):
    """
    Deliver a single intelligence item immediately (called from pipeline hooks).

    Non-blocking — failures are logged but never raised.

    Args:
        user: Django User instance.
        source_engine: Engine code (e.g., "PIE", "CDCE", "COS").
        source_object: The source model instance.
        payload: Optional pre-built payload dict. If None, auto-built from source_object.
    """
    try:
        if payload is None:
            payload = _build_payload(source_engine, source_object)
        if not payload:
            return

        channels = _get_enabled_channels(user)
        obj_type = type(source_object).__name__
        obj_id = source_object.id

        for channel in channels:
            _deliver_to_channel(
                user, channel, payload, source_engine, obj_type, obj_id,
                priority=payload.get("priority"),
            )

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
    items.extend(_get_undelivered_insights(user))
    items.extend(_get_undelivered_correlations(user))

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
                priority=payload.get("priority"),
            )
            if delivered is True:
                result["delivered"] += 1
            elif delivered is False:
                result["skipped"] += 1
            else:
                result["failed"] += 1

    return result


def _deliver_to_channel(user, channel, payload, source_engine, obj_type, obj_id,
                        priority=None):
    """
    Apply policies and deliver to a single channel.

    Returns: True=sent, False=skipped, None=failed
    """
    from apps.core.ai_delivery.delivery_policies import apply_delivery_policies
    from apps.core.ai_delivery.delivery_router import CHANNEL_HANDLERS
    from apps.core.ai_delivery.delivery_logger import log_skip

    # Policy check (priority passed for critical push quiet-hours bypass)
    passed, skip_reason = apply_delivery_policies(
        user, channel, source_engine, obj_type, obj_id,
        priority=priority,
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

    # Push: opt-in (default off), requires active device with push token
    if getattr(prefs, "intelligence_push_enabled", False):
        try:
            from apps.mobile.models import MobileDevice

            has_push_device = MobileDevice.objects.filter(
                user=user,
                is_active=True,
                push_enabled=True,
            ).exclude(push_token="").exists()
            if has_push_device:
                channels.append("push")
        except Exception:
            pass

    return channels


def _build_payload(engine, obj):
    """Build notification payload from an intelligence object."""
    obj_type = type(obj).__name__

    if obj_type == "GuidanceItem":
        return {
            "title": f"New Guidance: {obj.title[:80]}",
            "message": obj.message[:300] if obj.message else obj.title,
            "action_url": "/guidance/inbox/",
            "icon": "💡",
            "priority": getattr(obj, "priority", None),
        }

    elif obj_type == "DailyBriefing":
        summary = ""
        if obj.summary:
            summary = obj.summary[:300]
        return {
            "title": "Your Daily Briefing is Ready",
            "message": summary or "Your intelligence briefing for today has been generated.",
            "action_url": "/dashboard/",
            "icon": "📋",
        }

    elif obj_type == "WeeklyIntelligenceReport":
        summary = ""
        if obj.summary:
            summary = obj.summary[:300]
        return {
            "title": "Weekly Intelligence Report",
            "message": summary or "Your weekly intelligence report is ready.",
            "action_url": f"/intelligence/weekly/{obj.id}/",
            "icon": "📊",
        }

    elif obj_type == "Insight":
        # PIE insights — critical/warning severity pushed proactively
        severity_icon = {
            "critical": "🚨",
            "warning": "⚠️",
            "positive": "✅",
            "info": "ℹ️",
        }
        priority = 1 if getattr(obj, "severity", "") == "critical" else 3
        return {
            "title": f"{severity_icon.get(obj.severity, 'ℹ️')} {obj.title[:80]}",
            "message": (obj.message or obj.title)[:300],
            "action_url": "/assistant/",
            "icon": severity_icon.get(obj.severity, "ℹ️"),
            "priority": priority,
        }

    elif obj_type == "DomainCorrelation":
        # CDCE cross-domain correlations
        strength_icon = {
            "strong": "🔗",
            "moderate": "🔄",
            "weak": "💡",
        }
        return {
            "title": f"{strength_icon.get(obj.strength, '🔄')} Cross-Domain Pattern Discovered",
            "message": obj.narrative[:300] if obj.narrative else "New pattern found across your life domains.",
            "action_url": "/assistant/",
            "icon": strength_icon.get(obj.strength, "🔄"),
            "priority": 3,
        }

    elif obj_type == "CosPromptSchedule":
        # CoS proactive prompts
        return {
            "title": f"CoS: {getattr(obj, 'activity_type', 'Activity').replace('_', ' ').title()}",
            "message": (getattr(obj, 'prompt_text', '') or "You have a prompt from your Chief of Staff.")[:300],
            "action_url": "/assistant/",
            "icon": "📌",
            "priority": 3,
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


def _get_undelivered_insights(user):
    """
    Get critical/warning PIE insights from the last 24h for proactive push.

    Only delivers critical and warning severity — info and positive are
    surfaced in-conversation via cos_context.py, not pushed.
    """
    items = []
    try:
        from apps.core.ai_insights.models import Insight
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(hours=24)
        insights = Insight.objects.filter(
            user=user,
            severity__in=["critical", "warning"],
            status__in=["new", "read"],
            created_at__gte=cutoff,
        ).order_by("-created_at")[:5]

        for insight in insights:
            payload = _build_payload("PIE", insight)
            if payload:
                items.append(("PIE", "Insight", insight.id, payload))

    except Exception as e:
        logger.error(f"DNE: Failed to get insights for user {user.id}: {e}")

    return items


def _get_undelivered_correlations(user):
    """
    Get new strong/moderate CDCE correlations for proactive push.

    Only delivers correlations created in the last 24h with strength >= moderate.
    Weak correlations are surfaced in-conversation only.
    """
    items = []
    try:
        from apps.core.ai_cross_domain.models import DomainCorrelation
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(hours=24)
        correlations = DomainCorrelation.objects.filter(
            user=user,
            status="active",
            strength__in=["strong", "moderate"],
            created_at__gte=cutoff,
        ).order_by("-strength_score")[:3]

        for corr in correlations:
            payload = _build_payload("CDCE", corr)
            if payload:
                items.append(("CDCE", "DomainCorrelation", corr.id, payload))

    except Exception as e:
        logger.error(f"DNE: Failed to get correlations for user {user.id}: {e}")

    return items
