# ==============================================================================
# File: scheduler.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: SMS scheduling for medicine, tasks, events, and other reminders
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-30
# Last Updated: 2025-12-30
# ==============================================================================
"""
SMS Scheduler - Schedule SMS reminders for various notification categories.

This module provides functions to schedule SMS notifications for:
- Medicine dose reminders
- Medicine refill alerts
- Task due date reminders
- Calendar event reminders
- Prayer reminders
- Fasting window reminders
"""

import logging
from datetime import datetime, time, timedelta
from typing import List, Optional

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from .models import SMSNotification
from .services import SMSNotificationService

logger = logging.getLogger(__name__)
User = get_user_model()


class SMSScheduler:
    """
    Scheduler for creating SMS notification records for upcoming reminders.

    This class is designed to be run periodically (e.g., daily at midnight)
    to schedule notifications for the next 24 hours.
    """

    def __init__(self):
        """Initialize the scheduler."""
        self.service = SMSNotificationService()

    def schedule_all_for_user(self, user, date=None) -> dict:
        """
        Schedule all enabled notification categories for a user.

        Args:
            user: User to schedule notifications for
            date: Date to schedule for (defaults to today in user's timezone)

        Returns:
            dict with counts of scheduled notifications by category
        """
        if date is None:
            date = self._get_user_today(user)

        results = {
            'medicine': 0,
            'medicine_refill': 0,
            'task': 0,
            'event': 0,
            'prayer': 0,
            'fasting': 0,
        }

        try:
            prefs = user.preferences
        except Exception:
            return results

        if not prefs.sms_enabled or not prefs.sms_consent or not prefs.phone_verified:
            return results

        # Schedule each enabled category
        if prefs.sms_medicine_reminders:
            results['medicine'] = self.schedule_medicine_reminders(user, date)

        if prefs.sms_medicine_refill_alerts:
            results['medicine_refill'] = self.schedule_medicine_refill_alerts(user, date)

        if prefs.sms_task_reminders:
            results['task'] = self.schedule_task_reminders(user, date)

        if prefs.sms_event_reminders:
            results['event'] = self.schedule_event_reminders(user, date)

        if prefs.sms_prayer_reminders:
            results['prayer'] = self.schedule_prayer_reminders(user, date)

        if prefs.sms_fasting_reminders:
            results['fasting'] = self.schedule_fasting_reminders(user, date)

        return results

    def schedule_for_all_users(self, date=None) -> dict:
        """
        Schedule notifications for all users with SMS enabled.

        Args:
            date: Date to schedule for (defaults to today)

        Returns:
            dict with total counts by category
        """
        from apps.users.models import UserPreferences

        # Find all users with SMS enabled
        enabled_prefs = UserPreferences.objects.filter(
            sms_enabled=True,
            sms_consent=True,
            phone_verified=True
        ).select_related('user')

        totals = {
            'users_processed': 0,
            'medicine': 0,
            'medicine_refill': 0,
            'task': 0,
            'event': 0,
            'prayer': 0,
            'fasting': 0,
        }

        for pref in enabled_prefs:
            user_results = self.schedule_all_for_user(pref.user, date)
            totals['users_processed'] += 1
            for key in user_results:
                totals[key] += user_results[key]

        logger.info(f"Scheduled SMS for {totals['users_processed']} users: {totals}")
        return totals

    def schedule_medicine_reminders(self, user, date) -> int:
        """
        Schedule medicine dose reminders for the given date.

        Returns:
            Number of notifications scheduled
        """
        from apps.health.models import Medicine, MedicineSchedule

        count = 0

        # Get active medicines with schedules
        medicines = Medicine.objects.filter(
            user=user,
            status='active',
            medicine_status=Medicine.STATUS_ACTIVE
        ).prefetch_related('schedules')

        for medicine in medicines:
            for schedule in medicine.schedules.filter(is_active=True):
                # Check if this schedule applies to this day of week
                weekday = date.weekday()
                if str(weekday) not in schedule.days_of_week:
                    continue

                # Check if notification already exists
                scheduled_datetime = self._combine_date_time(date, schedule.scheduled_time, user)
                if self._notification_exists(user, SMSNotification.CATEGORY_MEDICINE, medicine, scheduled_datetime):
                    continue

                # Build message
                message = f"Time for {medicine.name} {medicine.dose}. Reply D=Done, R=5min, N=Skip"

                # Schedule notification
                notification = self.service.schedule_notification(
                    user=user,
                    category=SMSNotification.CATEGORY_MEDICINE,
                    message=message,
                    scheduled_for=scheduled_datetime,
                    source_object=medicine
                )

                if notification:
                    count += 1

        return count

    def schedule_medicine_refill_alerts(self, user, date) -> int:
        """
        Schedule medicine refill alerts for low supplies.

        Returns:
            Number of notifications scheduled
        """
        from apps.health.models import Medicine

        count = 0

        # Get active medicines with supply tracking
        medicines = Medicine.objects.filter(
            user=user,
            status='active',
            medicine_status=Medicine.STATUS_ACTIVE,
            current_supply__isnull=False,
        )

        for medicine in medicines:
            # Check if medicine needs refill (supply at or below threshold)
            if not medicine.needs_refill:
                continue

            # Estimate days remaining
            days_remaining = medicine.estimated_days_remaining

            # Schedule for 9 AM in user's timezone
            scheduled_datetime = self._combine_date_time(date, time(9, 0), user)

            # Check if notification already exists today
            if self._notification_exists(user, SMSNotification.CATEGORY_MEDICINE_REFILL, medicine, scheduled_datetime):
                continue

            # Build message
            if days_remaining is None or days_remaining <= 0:
                message = f"Refill needed: {medicine.name} is out. Time to refill!"
            else:
                message = f"Low supply: {medicine.name} ({days_remaining} days left). Time to refill!"

            notification = self.service.schedule_notification(
                user=user,
                category=SMSNotification.CATEGORY_MEDICINE_REFILL,
                message=message,
                scheduled_for=scheduled_datetime,
                source_object=medicine
            )

            if notification:
                count += 1

        return count

    def schedule_task_reminders(self, user, date) -> int:
        """
        Schedule task due date reminders.

        Returns:
            Number of notifications scheduled
        """
        from apps.life.models import Task

        count = 0

        # Get tasks due today that aren't completed
        tasks = Task.objects.filter(
            user=user,
            status='active',
            is_completed=False,
            due_date=date
        )

        for task in tasks:
            # Schedule for due time or 9 AM if no time set
            if task.due_time:
                scheduled_time = task.due_time
            else:
                scheduled_time = time(9, 0)

            scheduled_datetime = self._combine_date_time(date, scheduled_time, user)

            # Check if notification already exists
            if self._notification_exists(user, SMSNotification.CATEGORY_TASK, task, scheduled_datetime):
                continue

            # Build message
            message = f"Due today: {task.title}. Reply D=Done, R=1hr, N=Not today"

            notification = self.service.schedule_notification(
                user=user,
                category=SMSNotification.CATEGORY_TASK,
                message=message,
                scheduled_for=scheduled_datetime,
                source_object=task
            )

            if notification:
                count += 1

        return count

    def schedule_event_reminders(self, user, date) -> int:
        """
        Schedule calendar event reminders.

        Returns:
            Number of notifications scheduled
        """
        from apps.life.models import LifeEvent

        count = 0

        # Get events happening today
        events = LifeEvent.objects.filter(
            user=user,
            status='active',
            start_date=date
        )

        for event in events:
            if not event.start_time:
                continue

            # Schedule reminder 30 minutes before event
            event_datetime = self._combine_date_time(date, event.start_time, user)
            reminder_time = event_datetime - timedelta(minutes=30)

            # Don't schedule if it's in the past
            if reminder_time < timezone.now():
                continue

            # Check if notification already exists
            if self._notification_exists(user, SMSNotification.CATEGORY_EVENT, event, reminder_time):
                continue

            # Build message
            time_str = event.start_time.strftime("%I:%M %p")
            message = f"In 30 min: {event.title} at {time_str}"

            notification = self.service.schedule_notification(
                user=user,
                category=SMSNotification.CATEGORY_EVENT,
                message=message,
                scheduled_for=reminder_time,
                source_object=event
            )

            if notification:
                count += 1

        return count

    def schedule_prayer_reminders(self, user, date) -> int:
        """
        Schedule daily prayer reminders.

        For now, schedules a generic reminder at 7 AM.
        Future enhancement: user-configurable prayer times.

        Returns:
            Number of notifications scheduled
        """
        count = 0

        # Schedule for 7 AM in user's timezone
        scheduled_datetime = self._combine_date_time(date, time(7, 0), user)

        # Don't schedule if it's in the past
        if scheduled_datetime < timezone.now():
            return 0

        # Check if notification already exists today
        existing = SMSNotification.objects.filter(
            user=user,
            category=SMSNotification.CATEGORY_PRAYER,
            scheduled_for__date=date,
            status__in=[SMSNotification.STATUS_PENDING, SMSNotification.STATUS_SENT]
        ).exists()

        if existing:
            return 0

        message = "Good morning! Take a moment for prayer and reflection today."

        notification = self.service.schedule_notification(
            user=user,
            category=SMSNotification.CATEGORY_PRAYER,
            message=message,
            scheduled_for=scheduled_datetime,
        )

        if notification:
            count += 1

        return count

    def schedule_fasting_reminders(self, user, date) -> int:
        """
        Schedule fasting window reminders.

        Checks for active fasts and schedules reminders for window open/close.

        Returns:
            Number of notifications scheduled
        """
        from apps.health.models import FastingSession

        count = 0

        # Get active fasting sessions
        active_fasts = FastingSession.objects.filter(
            user=user,
            status='active',
            is_active=True
        )

        for fast in active_fasts:
            # Schedule reminder 30 minutes before eating window opens
            if fast.planned_end:
                window_open = fast.planned_end
                reminder_time = window_open - timedelta(minutes=30)

                if reminder_time > timezone.now():
                    # Check if notification already exists
                    existing = SMSNotification.objects.filter(
                        user=user,
                        category=SMSNotification.CATEGORY_FASTING,
                        content_type__app_label='health',
                        content_type__model='fastingsession',
                        object_id=fast.pk,
                        scheduled_for=reminder_time
                    ).exists()

                    if not existing:
                        time_str = window_open.strftime("%I:%M %p")
                        message = f"Eating window opens at {time_str}. Keep going!"

                        notification = self.service.schedule_notification(
                            user=user,
                            category=SMSNotification.CATEGORY_FASTING,
                            message=message,
                            scheduled_for=reminder_time,
                            source_object=fast
                        )

                        if notification:
                            count += 1

        return count

    def _get_user_today(self, user):
        """Get today's date in user's timezone."""
        from apps.core.utils import get_user_today
        return get_user_today(user)

    def _combine_date_time(self, date, time_obj, user):
        """
        Combine date and time in user's timezone, return as UTC datetime.
        """
        import pytz

        try:
            prefs = user.preferences
            user_tz = pytz.timezone(prefs.timezone)
        except Exception:
            user_tz = pytz.UTC

        # Create datetime in user's timezone
        local_dt = datetime.combine(date, time_obj)
        local_dt = user_tz.localize(local_dt)

        # Convert to UTC
        return local_dt.astimezone(pytz.UTC)

    def _notification_exists(self, user, category, source_object, scheduled_for) -> bool:
        """
        Check if a notification already exists for this object and time.
        """
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(source_object)

        # Allow some time tolerance (within 5 minutes)
        time_min = scheduled_for - timedelta(minutes=5)
        time_max = scheduled_for + timedelta(minutes=5)

        return SMSNotification.objects.filter(
            user=user,
            category=category,
            content_type=content_type,
            object_id=source_object.pk,
            scheduled_for__range=(time_min, time_max),
            status__in=[SMSNotification.STATUS_PENDING, SMSNotification.STATUS_SENT]
        ).exists()
