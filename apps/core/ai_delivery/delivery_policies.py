"""
DNE — Delivery Policies.

Enforces quiet hours, throttling, and deduplication before delivery.
"""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def check_dedupe(user, channel, source_engine, source_object_type, source_object_id):
    """
    Check if this item has already been delivered on this channel.

    Returns:
        (passed: bool, skip_reason: str or None)
    """
    from apps.core.ai_delivery.models import DeliveredNotification

    dedupe_hash = DeliveredNotification.compute_dedupe_hash(
        user.id, channel, source_engine, source_object_type, source_object_id,
    )
    exists = DeliveredNotification.objects.filter(dedupe_hash=dedupe_hash).exists()
    if exists:
        return False, "duplicate"
    return True, None


def check_quiet_hours(user, channel):
    """
    Check if delivery is blocked by quiet hours.

    In-app is always allowed. Email/SMS respect user's quiet hours.

    Returns:
        (passed: bool, skip_reason: str or None)
    """
    if channel == "in_app":
        return True, None

    try:
        prefs = user.preferences
    except Exception:
        return True, None

    # Use SMS quiet hours (which already exist) for all channels
    if not getattr(prefs, "sms_quiet_hours_enabled", False):
        return True, None

    now = timezone.localtime().time()
    quiet_start = getattr(prefs, "sms_quiet_start", None)
    quiet_end = getattr(prefs, "sms_quiet_end", None)

    if not quiet_start or not quiet_end:
        return True, None

    # Handle overnight quiet hours (e.g., 22:00 → 07:00)
    if quiet_start > quiet_end:
        in_quiet = now >= quiet_start or now < quiet_end
    else:
        in_quiet = quiet_start <= now < quiet_end

    if in_quiet:
        return False, f"quiet_hours ({quiet_start}-{quiet_end})"
    return True, None


def check_throttle(user, channel, max_per_hour=2, max_per_day=6):
    """
    Check if user has exceeded notification rate limits.

    Returns:
        (passed: bool, skip_reason: str or None)
    """
    from apps.core.ai_delivery.models import DeliveredNotification

    now = timezone.now()

    # Count sent in the last hour
    hour_ago = now - timedelta(hours=1)
    sent_last_hour = DeliveredNotification.objects.filter(
        user=user,
        channel=channel,
        status=DeliveredNotification.STATUS_SENT,
        delivered_at__gte=hour_ago,
    ).count()

    if sent_last_hour >= max_per_hour:
        return False, f"throttle_hourly ({sent_last_hour}/{max_per_hour})"

    # Count sent today
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = DeliveredNotification.objects.filter(
        user=user,
        channel=channel,
        status=DeliveredNotification.STATUS_SENT,
        delivered_at__gte=today_start,
    ).count()

    if sent_today >= max_per_day:
        return False, f"throttle_daily ({sent_today}/{max_per_day})"

    return True, None


def apply_delivery_policies(user, channel, source_engine, source_object_type,
                            source_object_id):
    """
    Run all delivery policy checks in order.

    Returns:
        (passed: bool, skip_reason: str or None)
    """
    # 1. Dedup first (cheapest check)
    passed, reason = check_dedupe(
        user, channel, source_engine, source_object_type, source_object_id,
    )
    if not passed:
        return False, reason

    # 2. Quiet hours
    passed, reason = check_quiet_hours(user, channel)
    if not passed:
        return False, reason

    # 3. Throttle (read user prefs for limits)
    max_per_hour = 2
    max_per_day = 6
    try:
        prefs = user.preferences
        max_per_hour = getattr(prefs, "intelligence_max_per_hour", 2)
        max_per_day = getattr(prefs, "intelligence_max_per_day", 6)
    except Exception:
        pass

    passed, reason = check_throttle(user, channel, max_per_hour, max_per_day)
    if not passed:
        return False, reason

    return True, None
