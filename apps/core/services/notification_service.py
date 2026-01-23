# ==============================================================================
# File: apps/core/services/notification_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Service for creating and sending in-app and email notifications
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-20
# ==============================================================================
"""
Notification Service - Handles creating in-app notifications and sending emails.

This service provides methods for:
- Creating in-app notifications for users
- Checking user preferences before creating notifications
- Sending individual notification emails
- Sending daily digest emails

Usage:
    from apps.core.services.notification_service import notification_service

    # Create a notification
    notification_service.create_notification(
        user=user,
        category='prayer',
        title='Prayer Reminder',
        message='Time for your daily prayers',
        action_url='/faith/prayers/',
        source_object=prayer_request,
    )

    # Send daily digest to a user
    notification_service.send_daily_digest(user)
"""

import logging
from datetime import datetime, time, timedelta
from typing import Optional, List, Any

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.mail import send_mail
from django.template import Template, Context
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing in-app and email notifications."""

    # Default email delivery time for daily digest (4:45 AM)
    DEFAULT_DIGEST_HOUR = 4
    DEFAULT_DIGEST_MINUTE = 45

    # Category to preference field mapping
    CATEGORY_INAPP_PREFS = {
        'medicine': 'notify_inapp_medicine',
        'medicine_refill': 'notify_inapp_medicine',
        'task': 'notify_inapp_task',
        'event': 'notify_inapp_event',
        'prayer': 'notify_inapp_prayer',
        'reading_plan': 'notify_inapp_reading_plan',
        'fasting': 'notify_inapp_medicine',  # Uses health module
        'significant_event': 'notify_inapp_significant_event',
        'milestone': 'notify_inapp_milestone',
        'finance': 'notify_inapp_finance',
        'journal': 'notify_inapp_journal',
        'capture': 'notify_inapp_capture',
        'system': None,  # Always allowed
    }

    CATEGORY_EMAIL_PREFS = {
        'medicine': 'notify_email_medicine',
        'medicine_refill': 'notify_email_medicine',
        'task': 'notify_email_task',
        'event': 'notify_email_event',
        'prayer': 'notify_email_prayer',
        'reading_plan': 'notify_email_reading_plan',
        'fasting': 'notify_email_medicine',  # Uses health module
        'significant_event': 'notify_email_significant_event',
        'milestone': 'notify_email_milestone',
        'finance': 'notify_email_finance',
        'journal': 'notify_email_journal',
        'capture': 'notify_email_capture',
        'system': None,  # Always allowed
    }

    # Category to module mapping for checking if module is enabled
    CATEGORY_MODULE_MAP = {
        'medicine': 'health_enabled',
        'medicine_refill': 'health_enabled',
        'task': 'life_enabled',
        'event': 'life_enabled',
        'prayer': 'faith_enabled',
        'reading_plan': 'faith_enabled',
        'fasting': 'health_enabled',
        'significant_event': 'life_enabled',
        'milestone': 'purpose_enabled',
        'finance': 'finances_enabled',
        'journal': 'journal_enabled',
        'capture': 'capture_enabled',
        'system': None,
    }

    def is_module_enabled(self, user, category: str) -> bool:
        """Check if the module for this category is enabled for the user."""
        module_field = self.CATEGORY_MODULE_MAP.get(category)
        if module_field is None:
            return True  # System notifications always allowed

        try:
            return getattr(user.preferences, module_field, True)
        except Exception:
            return True  # Default to enabled if preferences don't exist

    def is_inapp_enabled(self, user, category: str) -> bool:
        """Check if in-app notifications are enabled for this category."""
        try:
            prefs = user.preferences

            # Check master toggle
            if not prefs.notifications_enabled:
                return False

            # Check module is enabled
            if not self.is_module_enabled(user, category):
                return False

            # Check category-specific toggle
            pref_field = self.CATEGORY_INAPP_PREFS.get(category)
            if pref_field is None:
                return True  # System notifications always allowed

            return getattr(prefs, pref_field, True)
        except Exception:
            return True  # Default to enabled if preferences don't exist

    def is_email_enabled(self, user, category: str) -> bool:
        """Check if email notifications are enabled for this category."""
        try:
            prefs = user.preferences

            # Check master toggle
            if not prefs.email_notifications_enabled:
                return False

            # Check module is enabled
            if not self.is_module_enabled(user, category):
                return False

            # Check category-specific toggle
            pref_field = self.CATEGORY_EMAIL_PREFS.get(category)
            if pref_field is None:
                return True  # System notifications always allowed

            return getattr(prefs, pref_field, True)
        except Exception:
            return True  # Default to enabled if preferences don't exist

    def create_notification(
        self,
        user,
        category: str,
        title: str,
        message: str,
        action_url: str = '',
        icon: str = '',
        source_object: Any = None,
        scheduled_for: Optional[datetime] = None,
        send_email: bool = True,
    ) -> Optional['Notification']:
        """
        Create an in-app notification for a user.

        Args:
            user: The user to notify
            category: Notification category (medicine, task, prayer, etc.)
            title: Short notification title
            message: Notification message body
            action_url: URL to navigate to when clicked
            icon: Optional icon override
            source_object: Optional source object (Prayer, Task, etc.)
            scheduled_for: Optional future datetime to show notification
            send_email: Whether to also queue an email notification

        Returns:
            The created Notification object, or None if notifications are disabled
        """
        from apps.core.models import Notification

        # Check if in-app notifications are enabled for this category
        if not self.is_inapp_enabled(user, category):
            logger.debug(
                f"In-app notification skipped for {user.email}: "
                f"category={category} disabled"
            )
            return None

        # Build notification kwargs
        notification_kwargs = {
            'user': user,
            'category': category,
            'title': title,
            'message': message,
            'action_url': action_url,
            'icon': icon,
            'scheduled_for': scheduled_for,
        }

        # Add source object if provided
        if source_object:
            content_type = ContentType.objects.get_for_model(source_object)
            notification_kwargs['content_type'] = content_type
            notification_kwargs['object_id'] = source_object.pk

        # Create the notification
        notification = Notification.objects.create(**notification_kwargs)

        logger.info(
            f"Created notification for {user.email}: "
            f"category={category}, title={title}"
        )

        # If email notifications are enabled and frequency is 'immediate', send email now
        if send_email and self.is_email_enabled(user, category):
            try:
                prefs = user.preferences
                if prefs.email_notification_frequency == 'immediate':
                    self.send_immediate_email(notification)
            except Exception as e:
                logger.warning(f"Failed to send immediate email: {e}")

        return notification

    def send_immediate_email(self, notification) -> bool:
        """
        Send an immediate email for a single notification.

        Args:
            notification: The Notification object

        Returns:
            True if email was sent successfully
        """
        from apps.admin_console.models import EmailNotificationTemplate
        from apps.core.models import SiteConfiguration

        user = notification.user
        category = notification.category

        # Get the email template for this category
        template = EmailNotificationTemplate.get_template_for_category(category)
        if not template:
            logger.warning(f"No email template found for category: {category}")
            return False

        # Build context
        site_config = SiteConfiguration.get_solo()
        context = {
            'user': user,
            'notification': notification,
            'site_name': site_config.site_name,
            'current_year': timezone.now().year,
            'preferences_url': f"{settings.SITE_URL}/settings/preferences/",
        }

        try:
            # Render subject and body
            subject = template.render_subject(context)
            html_body = template.render_body(context)
            text_body = strip_tags(html_body)

            # Send email
            send_mail(
                subject=subject,
                message=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_body,
                fail_silently=False,
            )

            # Mark email as sent
            notification.mark_email_sent()

            logger.info(f"Sent immediate email to {user.email} for notification {notification.id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {user.email}: {e}")
            return False

    def send_daily_digest(self, user) -> bool:
        """
        Send a daily digest email to a user with all pending notifications.

        Args:
            user: The user to send digest to

        Returns:
            True if digest was sent (or no notifications to send)
        """
        from apps.admin_console.models import EmailNotificationTemplate
        from apps.core.models import Notification, SiteConfiguration

        # Check if email notifications are enabled
        try:
            prefs = user.preferences
            if not prefs.email_notifications_enabled:
                return True  # Nothing to do
        except Exception:
            return True

        # Get pending notifications that haven't been emailed
        notifications = list(
            Notification.get_pending_email_notifications(user)
            .order_by('category', '-created_at')
        )

        if not notifications:
            return True  # Nothing to send

        # Filter notifications based on email preferences
        filtered_notifications = []
        for notif in notifications:
            if self.is_email_enabled(user, notif.category):
                filtered_notifications.append(notif)

        if not filtered_notifications:
            return True  # Nothing to send after filtering

        # Get digest template
        template = EmailNotificationTemplate.get_template_for_category('digest')
        if not template:
            logger.warning("No email template found for daily digest")
            return False

        # Build context
        site_config = SiteConfiguration.get_solo()
        context = {
            'user': user,
            'notifications': filtered_notifications,
            'notification_count': len(filtered_notifications),
            'site_name': site_config.site_name,
            'current_year': timezone.now().year,
            'preferences_url': f"{settings.SITE_URL}/settings/preferences/",
            'notifications_url': f"{settings.SITE_URL}/notifications/",
        }

        try:
            # Render subject and body
            subject = template.render_subject(context)
            html_body = template.render_body(context)
            text_body = strip_tags(html_body)

            # Send email
            send_mail(
                subject=subject,
                message=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_body,
                fail_silently=False,
            )

            # Mark all notifications as emailed
            for notif in filtered_notifications:
                notif.mark_email_sent()

            logger.info(
                f"Sent daily digest to {user.email} with "
                f"{len(filtered_notifications)} notifications"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to send daily digest to {user.email}: {e}")
            return False

    def get_users_for_digest(self):
        """
        Get users who should receive daily digest emails.

        Returns users who:
        - Have email notifications enabled
        - Have daily_digest frequency selected
        - Have pending notifications
        """
        from django.contrib.auth import get_user_model
        from apps.core.models import Notification

        User = get_user_model()

        # Get users with pending notifications
        users_with_notifications = Notification.objects.filter(
            email_sent=False,
            is_read=False,
        ).values_list('user_id', flat=True).distinct()

        # Filter to users with digest frequency
        return User.objects.filter(
            id__in=users_with_notifications,
            preferences__email_notifications_enabled=True,
            preferences__email_notification_frequency='daily_digest',
        ).select_related('preferences')

    def create_prayer_reminders(self) -> int:
        """
        Create daily prayer reminder notifications for users who have
        prayers marked with remind_daily=True.

        Returns number of notifications created.
        """
        from django.contrib.auth import get_user_model
        from apps.faith.models import PrayerRequest

        User = get_user_model()
        count = 0

        # Get all users with daily prayer reminders
        users_with_prayers = User.objects.filter(
            preferences__faith_enabled=True,
            preferences__notifications_enabled=True,
            prayerrequests__remind_daily=True,
            prayerrequests__status='active',
            prayerrequests__is_answered=False,
        ).distinct().prefetch_related('prayerrequests')

        for user in users_with_prayers:
            # Get user's active prayers with reminders
            prayers = PrayerRequest.objects.filter(
                user=user,
                remind_daily=True,
                status='active',
                is_answered=False,
            )

            prayer_count = prayers.count()
            if prayer_count == 0:
                continue

            # Create single consolidated notification
            if prayer_count == 1:
                prayer = prayers.first()
                title = "Prayer Reminder"
                message = f"Time to pray: {prayer.title[:50]}"
                action_url = f"/faith/prayers/{prayer.id}/"
            else:
                title = f"Prayer Reminder ({prayer_count} prayers)"
                message = f"You have {prayer_count} prayers marked for daily reminder"
                action_url = "/faith/prayers/"

            notification = self.create_notification(
                user=user,
                category='prayer',
                title=title,
                message=message,
                action_url=action_url,
            )

            if notification:
                count += 1

        logger.info(f"Created {count} prayer reminder notifications")
        return count

    def create_reading_plan_reminders(self) -> int:
        """
        Create reading plan reminder notifications for users at their
        configured reminder time.

        Should be called hourly to catch users at their preferred time.

        Returns number of notifications created.
        """
        from django.contrib.auth import get_user_model
        from apps.faith.models import UserReadingPlan

        User = get_user_model()
        count = 0

        # Get current hour
        now = timezone.now()
        current_hour = now.hour

        # Get users whose reminder time matches current hour
        users = User.objects.filter(
            preferences__faith_enabled=True,
            preferences__notifications_enabled=True,
            preferences__notification_reminder_time__hour=current_hour,
        ).select_related('preferences')

        for user in users:
            # Get active reading plans
            active_plans = UserReadingPlan.objects.filter(
                user=user,
                status='active',
            ).select_related('plan')

            for plan in active_plans:
                # Get today's reading
                today_reading = plan.get_todays_reading()
                if not today_reading:
                    continue

                # Check if already completed today
                if plan.is_day_complete(today_reading.day_number):
                    continue

                # Create notification
                notification = self.create_notification(
                    user=user,
                    category='reading_plan',
                    title=f"Time for {plan.plan.name}",
                    message=f"Day {today_reading.day_number}: {today_reading.title or today_reading.scripture_reference}",
                    action_url=f"/faith/reading-plans/{plan.id}/",
                    source_object=plan,
                )

                if notification:
                    count += 1

        logger.info(f"Created {count} reading plan reminder notifications")
        return count


# Singleton instance
notification_service = NotificationService()
