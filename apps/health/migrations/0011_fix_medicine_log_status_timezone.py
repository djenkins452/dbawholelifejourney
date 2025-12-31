# ==============================================================================
# File: 0011_fix_medicine_log_status_timezone.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to recalculate log_status for MedicineLog entries
#              that were incorrectly marked as 'late' due to timezone bug
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-30
# Last Updated: 2025-12-30
# ==============================================================================
"""
Data migration to fix MedicineLog entries that were incorrectly marked as 'late'.

The bug: mark_taken() was comparing UTC time against naive local time, causing
medicines taken BEFORE the scheduled time to be marked as "Taken Late".

Example: 8:24 AM EST = 1:24 PM UTC. When stripped of timezone,
"1:24 PM" > "10:00 AM" (schedule + grace), so it was marked as late.

This migration recalculates the log_status for all existing logs using the
corrected timezone-aware comparison logic.
"""
from django.db import migrations


def recalculate_medicine_log_status(apps, schema_editor):
    """Recalculate log_status for all MedicineLog entries with proper timezone handling."""
    MedicineLog = apps.get_model('health', 'MedicineLog')
    UserPreferences = apps.get_model('users', 'UserPreferences')

    from datetime import datetime, timedelta
    import pytz

    STATUS_TAKEN = 'taken'
    STATUS_LATE = 'late'

    # Get all logs that have a taken_at time and scheduled_time (not PRN)
    logs = MedicineLog.objects.filter(
        taken_at__isnull=False,
        scheduled_time__isnull=False,
        log_status__in=[STATUS_TAKEN, STATUS_LATE]
    ).select_related('medicine', 'user')

    fixed_count = 0

    for log in logs:
        try:
            # Get user's timezone
            prefs = UserPreferences.objects.filter(user=log.user).first()
            if not prefs or not prefs.timezone:
                continue

            user_tz = pytz.timezone(prefs.timezone)

            # Convert taken_at to user's local timezone
            if log.taken_at.tzinfo:
                taken_local = log.taken_at.astimezone(user_tz)
            else:
                taken_local = user_tz.localize(log.taken_at)

            # Create scheduled datetime in user's timezone
            scheduled_dt = datetime.combine(log.scheduled_date, log.scheduled_time)
            scheduled_local = user_tz.localize(scheduled_dt)

            # Get grace period (default 60 minutes if not set)
            grace_minutes = log.medicine.grace_period_minutes if log.medicine else 60
            latest_ok = scheduled_local + timedelta(minutes=grace_minutes)

            # Determine correct status
            if taken_local > latest_ok:
                correct_status = STATUS_LATE
            else:
                correct_status = STATUS_TAKEN

            # Update if different
            if log.log_status != correct_status:
                log.log_status = correct_status
                log.save(update_fields=['log_status'])
                fixed_count += 1

        except Exception:
            # Skip problematic records
            continue

    if fixed_count > 0:
        print(f"Fixed {fixed_count} MedicineLog entries with incorrect status")


def reverse_recalculate(apps, schema_editor):
    """No-op reverse migration - we can't restore the old incorrect values."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('health', '0010_add_medical_providers'),
        ('users', '0020_add_personal_assistant_module'),  # Ensure UserPreferences exists
    ]

    operations = [
        migrations.RunPython(recalculate_medicine_log_status, reverse_recalculate),
    ]
