"""
DNE — Delivery Router.

Routes intelligence notifications to channels: in_app, email, sms.
Each channel implementation integrates with existing WLJ infrastructure.
"""

import logging

from django.db import IntegrityError

from apps.core.ai_delivery.models import DeliveredNotification

logger = logging.getLogger(__name__)


def deliver_in_app(user, payload, source_engine, source_object_type, source_object_id):
    """
    Deliver an intelligence notification via in-app notification bell.

    Uses existing NotificationService to create a Notification record,
    then logs a DeliveredNotification for DNE tracking.

    Returns:
        DeliveredNotification or None on failure.
    """
    from apps.core.services.notification_service import notification_service

    try:
        notification = notification_service.create_notification(
            user=user,
            category="intelligence",
            title=payload["title"],
            message=payload["message"],
            action_url=payload.get("action_url", ""),
            icon=payload.get("icon", "🧠"),
            send_email=False,  # DNE controls email separately
        )

        dedupe_hash = DeliveredNotification.compute_dedupe_hash(
            user.id, "in_app", source_engine, source_object_type, source_object_id,
        )

        record = DeliveredNotification.objects.create(
            user=user,
            source_engine=source_engine,
            source_object_type=source_object_type,
            source_object_id=source_object_id,
            channel=DeliveredNotification.CHANNEL_INAPP,
            title=payload["title"],
            message=payload["message"],
            action_url=payload.get("action_url", ""),
            status=DeliveredNotification.STATUS_SENT,
            dedupe_hash=dedupe_hash,
            metadata={"notification_id": notification.id if notification else None},
        )

        logger.info(
            f"DNE: in_app delivered to user {user.id}: {source_engine}/{source_object_type}/{source_object_id}"
        )
        return record

    except IntegrityError:
        logger.debug(f"DNE: in_app duplicate for user {user.id}")
        return None
    except Exception as e:
        logger.error(f"DNE: in_app delivery failed for user {user.id}: {e}")
        return None


def deliver_email(user, payload, source_engine, source_object_type, source_object_id):
    """
    Deliver an intelligence notification via email.

    Sends immediately using Django send_mail. Respects existing email prefs.

    Returns:
        DeliveredNotification or None.
    """
    from django.conf import settings as django_settings
    from django.core.mail import send_mail

    dedupe_hash = DeliveredNotification.compute_dedupe_hash(
        user.id, "email", source_engine, source_object_type, source_object_id,
    )

    try:
        subject = f"[WLJ Intelligence] {payload['title']}"
        message = payload["message"]
        action_url = payload.get("action_url", "")
        if action_url:
            site = getattr(django_settings, "SITE_DOMAIN", "https://wholelifejourney.com")
            message += f"\n\nView: {site}{action_url}"

        send_mail(
            subject=subject,
            message=message,
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )

        record = DeliveredNotification.objects.create(
            user=user,
            source_engine=source_engine,
            source_object_type=source_object_type,
            source_object_id=source_object_id,
            channel=DeliveredNotification.CHANNEL_EMAIL,
            title=payload["title"],
            message=payload["message"],
            action_url=payload.get("action_url", ""),
            status=DeliveredNotification.STATUS_SENT,
            dedupe_hash=dedupe_hash,
        )

        logger.info(f"DNE: email delivered to user {user.id}: {source_engine}")
        return record

    except IntegrityError:
        logger.debug(f"DNE: email duplicate for user {user.id}")
        return None
    except Exception as e:
        logger.error(f"DNE: email delivery failed for user {user.id}: {e}")
        return None


def deliver_sms(user, payload, source_engine, source_object_type, source_object_id):
    """
    Deliver an intelligence notification via SMS.

    Uses existing SMSNotificationService if available.

    Returns:
        DeliveredNotification or None.
    """
    dedupe_hash = DeliveredNotification.compute_dedupe_hash(
        user.id, "sms", source_engine, source_object_type, source_object_id,
    )

    try:
        from apps.sms.services import SMSNotificationService

        sms_service = SMSNotificationService()

        # Truncate message for SMS (max 320 chars)
        sms_msg = payload["title"]
        detail = payload.get("message", "")
        if detail:
            remaining = 320 - len(sms_msg) - 3
            if remaining > 20:
                sms_msg += " — " + detail[:remaining]

        sms_notification = sms_service.schedule_notification(
            user=user,
            category="system",
            message=sms_msg,
        )

        status = DeliveredNotification.STATUS_SENT if sms_notification else DeliveredNotification.STATUS_FAILED

        record = DeliveredNotification.objects.create(
            user=user,
            source_engine=source_engine,
            source_object_type=source_object_type,
            source_object_id=source_object_id,
            channel=DeliveredNotification.CHANNEL_SMS,
            title=payload["title"],
            message=payload["message"],
            action_url=payload.get("action_url", ""),
            status=status,
            dedupe_hash=dedupe_hash,
            metadata={"sms_id": sms_notification.id if sms_notification else None},
        )

        logger.info(f"DNE: sms delivered to user {user.id}: {source_engine}")
        return record

    except ImportError:
        # SMS module not available — skip gracefully
        try:
            record = DeliveredNotification.objects.create(
                user=user,
                source_engine=source_engine,
                source_object_type=source_object_type,
                source_object_id=source_object_id,
                channel=DeliveredNotification.CHANNEL_SMS,
                title=payload["title"],
                message=payload["message"],
                status=DeliveredNotification.STATUS_SKIPPED,
                skip_reason="sms_not_configured",
                dedupe_hash=dedupe_hash,
            )
            return record
        except IntegrityError:
            return None
    except IntegrityError:
        logger.debug(f"DNE: sms duplicate for user {user.id}")
        return None
    except Exception as e:
        logger.error(f"DNE: sms delivery failed for user {user.id}: {e}")
        return None


# Channel dispatch map
CHANNEL_HANDLERS = {
    "in_app": deliver_in_app,
    "email": deliver_email,
    "sms": deliver_sms,
}
