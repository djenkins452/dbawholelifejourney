# ==============================================================================
# File: schedule_sms_reminders.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to schedule SMS reminders for all users
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-30
# Last Updated: 2025-12-30
# ==============================================================================
"""
Schedule SMS Reminders Management Command

Schedules SMS notifications for all users with SMS enabled.
Should be run daily at midnight (or early morning) to schedule
reminders for the upcoming day.

Usage:
    python manage.py schedule_sms_reminders
    python manage.py schedule_sms_reminders --user=user@example.com
    python manage.py schedule_sms_reminders --dry-run
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.sms.scheduler import SMSScheduler

User = get_user_model()


class Command(BaseCommand):
    help = 'Schedule SMS reminders for all users (or a specific user)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Email of specific user to schedule for',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be scheduled without creating notifications',
        )
        parser.add_argument(
            '--date',
            type=str,
            help='Date to schedule for (YYYY-MM-DD), defaults to today',
        )

    def handle(self, *args, **options):
        scheduler = SMSScheduler()
        dry_run = options['dry_run']
        user_email = options.get('user')
        date_str = options.get('date')

        # Parse date if provided
        schedule_date = None
        if date_str:
            from datetime import datetime
            try:
                schedule_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                raise CommandError(f"Invalid date format: {date_str}. Use YYYY-MM-DD")

        if dry_run:
            self.stdout.write("DRY RUN - No notifications will be created")

        if user_email:
            # Schedule for specific user
            try:
                user = User.objects.get(email=user_email)
            except User.DoesNotExist:
                raise CommandError(f"User not found: {user_email}")

            if dry_run:
                self._show_user_schedule_preview(user, schedule_date)
            else:
                results = scheduler.schedule_all_for_user(user, schedule_date)
                self._show_user_results(user, results)
        else:
            # Schedule for all users
            if dry_run:
                self._show_all_users_preview()
            else:
                results = scheduler.schedule_for_all_users(schedule_date)
                self._show_all_results(results)

    def _show_user_schedule_preview(self, user, date):
        """Show what would be scheduled for a user."""
        self.stdout.write(f"\nUser: {user.email}")

        try:
            prefs = user.preferences
        except Exception:
            self.stdout.write(self.style.WARNING("  No preferences found"))
            return

        if not prefs.sms_enabled:
            self.stdout.write(self.style.WARNING("  SMS not enabled"))
            return

        if not prefs.phone_verified:
            self.stdout.write(self.style.WARNING("  Phone not verified"))
            return

        self.stdout.write(f"  Phone: {prefs.phone_number}")
        self.stdout.write("  Enabled categories:")

        if prefs.sms_medicine_reminders:
            self.stdout.write("    - Medicine reminders")
        if prefs.sms_medicine_refill_alerts:
            self.stdout.write("    - Medicine refill alerts")
        if prefs.sms_task_reminders:
            self.stdout.write("    - Task reminders")
        if prefs.sms_event_reminders:
            self.stdout.write("    - Event reminders")
        if prefs.sms_prayer_reminders:
            self.stdout.write("    - Prayer reminders")
        if prefs.sms_fasting_reminders:
            self.stdout.write("    - Fasting reminders")

    def _show_all_users_preview(self):
        """Show all users with SMS enabled."""
        from apps.users.models import UserPreferences

        enabled_prefs = UserPreferences.objects.filter(
            sms_enabled=True,
            sms_consent=True,
            phone_verified=True
        ).select_related('user')

        if not enabled_prefs:
            self.stdout.write(self.style.WARNING("No users with SMS enabled"))
            return

        self.stdout.write(f"\nUsers with SMS enabled: {enabled_prefs.count()}")
        for pref in enabled_prefs:
            self.stdout.write(f"  - {pref.user.email}: {pref.phone_number}")

    def _show_user_results(self, user, results):
        """Show scheduling results for a user."""
        self.stdout.write(f"\nScheduled for {user.email}:")
        total = 0
        for category, count in results.items():
            if count > 0:
                self.stdout.write(f"  {category}: {count}")
                total += count

        if total > 0:
            self.stdout.write(self.style.SUCCESS(f"Total: {total} notifications scheduled"))
        else:
            self.stdout.write(self.style.WARNING("No notifications scheduled"))

    def _show_all_results(self, results):
        """Show scheduling results for all users."""
        self.stdout.write(f"\nProcessed {results['users_processed']} users")

        total = 0
        for category in ['medicine', 'medicine_refill', 'task', 'event', 'prayer', 'fasting']:
            count = results.get(category, 0)
            if count > 0:
                self.stdout.write(f"  {category}: {count}")
                total += count

        if total > 0:
            self.stdout.write(self.style.SUCCESS(f"Total: {total} notifications scheduled"))
        else:
            self.stdout.write(self.style.WARNING("No notifications scheduled"))
