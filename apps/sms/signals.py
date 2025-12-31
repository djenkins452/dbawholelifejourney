# ==============================================================================
# File: signals.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Django signals for real-time SMS notification scheduling
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================
"""
SMS Signals - Real-time scheduling of SMS notifications.

When users create or update medicines, tasks, or events, these signals
automatically schedule SMS notifications for any upcoming reminders today.

This provides immediate scheduling rather than waiting for the nightly
batch job.
"""

import logging
from datetime import datetime, timedelta

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


def schedule_medicine_sms_for_today(medicine):
    """
    Schedule SMS notifications for a medicine's schedules that are today.

    Called when a Medicine or MedicineSchedule is saved.
    """
    from apps.sms.scheduler import SMSScheduler
    from apps.sms.models import SMSNotification
    from apps.core.utils import get_user_today

    user = medicine.user

    # Check if user has SMS enabled for medicine reminders
    try:
        prefs = user.preferences
        if not prefs.sms_enabled or not prefs.sms_consent or not prefs.phone_verified:
            return 0
        if not prefs.sms_medicine_reminders:
            return 0
    except Exception:
        return 0

    # Only schedule for active medicines
    if medicine.status != 'active' or medicine.medicine_status != medicine.STATUS_ACTIVE:
        return 0

    scheduler = SMSScheduler()
    today = get_user_today(user)
    count = 0

    for schedule in medicine.schedules.filter(is_active=True):
        # Check if this schedule applies to today
        weekday = today.weekday()
        if str(weekday) not in schedule.days_of_week:
            continue

        # Create the scheduled datetime
        scheduled_datetime = scheduler._combine_date_time(today, schedule.scheduled_time, user)

        # Only schedule if it's in the future
        if scheduled_datetime <= timezone.now():
            continue

        # Check if notification already exists
        if scheduler._notification_exists(user, SMSNotification.CATEGORY_MEDICINE, medicine, scheduled_datetime):
            continue

        # Build message
        message = f"Time for {medicine.name} {medicine.dose}. Reply D=Done, R=5min, N=Skip"

        # Schedule notification
        notification = scheduler.service.schedule_notification(
            user=user,
            category=SMSNotification.CATEGORY_MEDICINE,
            message=message,
            scheduled_for=scheduled_datetime,
            source_object=medicine
        )

        if notification:
            count += 1
            logger.info(f"Real-time scheduled SMS for {medicine.name} at {scheduled_datetime}")

    return count


def schedule_task_sms_for_today(task):
    """
    Schedule SMS notification for a task due today.

    Called when a Task is saved.
    """
    from apps.sms.scheduler import SMSScheduler
    from apps.sms.models import SMSNotification
    from apps.core.utils import get_user_today
    from datetime import time

    user = task.user

    # Check if user has SMS enabled for task reminders
    try:
        prefs = user.preferences
        if not prefs.sms_enabled or not prefs.sms_consent or not prefs.phone_verified:
            return 0
        if not prefs.sms_task_reminders:
            return 0
    except Exception:
        return 0

    # Only schedule for active, incomplete tasks
    if task.status != 'active' or task.is_completed:
        return 0

    today = get_user_today(user)

    # Only schedule if due today
    if task.due_date != today:
        return 0

    scheduler = SMSScheduler()

    # Schedule for due time or 9 AM if no time set
    scheduled_time = task.due_time if task.due_time else time(9, 0)
    scheduled_datetime = scheduler._combine_date_time(today, scheduled_time, user)

    # Only schedule if it's in the future
    if scheduled_datetime <= timezone.now():
        return 0

    # Check if notification already exists
    if scheduler._notification_exists(user, SMSNotification.CATEGORY_TASK, task, scheduled_datetime):
        return 0

    # Build message
    message = f"Due today: {task.title}. Reply D=Done, R=1hr, N=Not today"

    # Schedule notification
    notification = scheduler.service.schedule_notification(
        user=user,
        category=SMSNotification.CATEGORY_TASK,
        message=message,
        scheduled_for=scheduled_datetime,
        source_object=task
    )

    if notification:
        logger.info(f"Real-time scheduled SMS for task '{task.title}' at {scheduled_datetime}")
        return 1

    return 0


def schedule_event_sms_for_today(event):
    """
    Schedule SMS notification for an event happening today.

    Called when a LifeEvent is saved.
    """
    from apps.sms.scheduler import SMSScheduler
    from apps.sms.models import SMSNotification
    from apps.core.utils import get_user_today

    user = event.user

    # Check if user has SMS enabled for event reminders
    try:
        prefs = user.preferences
        if not prefs.sms_enabled or not prefs.sms_consent or not prefs.phone_verified:
            return 0
        if not prefs.sms_event_reminders:
            return 0
    except Exception:
        return 0

    # Only schedule for active events with a start time
    if event.status != 'active' or not event.start_time:
        return 0

    today = get_user_today(user)

    # Only schedule if happening today
    if event.start_date != today:
        return 0

    scheduler = SMSScheduler()

    # Schedule reminder 30 minutes before event
    event_datetime = scheduler._combine_date_time(today, event.start_time, user)
    reminder_time = event_datetime - timedelta(minutes=30)

    # Only schedule if reminder is in the future
    if reminder_time <= timezone.now():
        return 0

    # Check if notification already exists
    if scheduler._notification_exists(user, SMSNotification.CATEGORY_EVENT, event, reminder_time):
        return 0

    # Build message
    time_str = event.start_time.strftime("%I:%M %p")
    message = f"In 30 min: {event.title} at {time_str}"

    # Schedule notification
    notification = scheduler.service.schedule_notification(
        user=user,
        category=SMSNotification.CATEGORY_EVENT,
        message=message,
        scheduled_for=reminder_time,
        source_object=event
    )

    if notification:
        logger.info(f"Real-time scheduled SMS for event '{event.title}' at {reminder_time}")
        return 1

    return 0


# ==============================================================================
# Signal Receivers
# ==============================================================================

@receiver(post_save, sender='health.Medicine')
def on_medicine_save(sender, instance, created, **kwargs):
    """Schedule SMS when a medicine is saved."""
    try:
        count = schedule_medicine_sms_for_today(instance)
        if count > 0:
            logger.info(f"Scheduled {count} SMS notification(s) for medicine {instance.name}")
    except Exception as e:
        logger.error(f"Error scheduling SMS for medicine {instance.id}: {e}")


@receiver(post_save, sender='health.MedicineSchedule')
def on_medicine_schedule_save(sender, instance, created, **kwargs):
    """Schedule SMS when a medicine schedule is saved."""
    try:
        count = schedule_medicine_sms_for_today(instance.medicine)
        if count > 0:
            logger.info(f"Scheduled {count} SMS notification(s) for schedule {instance}")
    except Exception as e:
        logger.error(f"Error scheduling SMS for medicine schedule {instance.id}: {e}")


@receiver(post_save, sender='life.Task')
def on_task_save(sender, instance, created, **kwargs):
    """Schedule SMS when a task is saved."""
    try:
        count = schedule_task_sms_for_today(instance)
        if count > 0:
            logger.info(f"Scheduled SMS notification for task '{instance.title}'")
    except Exception as e:
        logger.error(f"Error scheduling SMS for task {instance.id}: {e}")


@receiver(post_save, sender='life.LifeEvent')
def on_event_save(sender, instance, created, **kwargs):
    """Schedule SMS when an event is saved."""
    try:
        count = schedule_event_sms_for_today(instance)
        if count > 0:
            logger.info(f"Scheduled SMS notification for event '{instance.title}'")
    except Exception as e:
        logger.error(f"Error scheduling SMS for event {instance.id}: {e}")
