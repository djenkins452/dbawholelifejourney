# ==============================================================================
# File: apps/core/management/commands/generate_health_reminders.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to generate daily health reminder notifications
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-05
# ==============================================================================
"""
Generate Health Reminders - Create in-app notifications for health activities.

This command creates notifications for:
- Medicine reminders (scheduled doses not yet taken)
- Workout reminders (if no workout logged today)
- Journal reminders (if no journal entry today)

Usage:
    # Generate all health reminders
    python manage.py generate_health_reminders

    # Generate only medicine reminders
    python manage.py generate_health_reminders --medicine-only

    # Dry run
    python manage.py generate_health_reminders --dry-run

Schedule:
    - Morning reminders: Run at 8:00 AM user time (or hourly to catch users)
    - Evening reminders: Run at 7:00 PM user time

    "0 8 * * *" for morning reminders (UTC, adjust for timezone)
    "0 19 * * *" for evening reminders (UTC, adjust for timezone)
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Generate daily health reminder notifications for medicines, workouts, and journal'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )
        parser.add_argument(
            '--medicine-only',
            action='store_true',
            help='Only generate medicine reminders',
        )
        parser.add_argument(
            '--workout-only',
            action='store_true',
            help='Only generate workout reminders',
        )
        parser.add_argument(
            '--journal-only',
            action='store_true',
            help='Only generate journal reminders',
        )
        parser.add_argument(
            '--time-period',
            type=str,
            choices=['morning', 'evening', 'all'],
            default='all',
            help='Which time period to generate reminders for',
        )
        parser.add_argument(
            '--include-chat',
            action='store_true',
            help='Also create interactive check-ins in assistant chat (with quick replies)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        medicine_only = options['medicine_only']
        workout_only = options['workout_only']
        journal_only = options['journal_only']
        time_period = options['time_period']
        include_chat = options['include_chat']
        verbosity = options['verbosity']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No notifications will be created'))

        total_created = 0
        chat_created = 0
        generate_all = not (medicine_only or workout_only or journal_only)

        # Generate medicine reminders
        if generate_all or medicine_only:
            if verbosity >= 1:
                self.stdout.write('Generating medicine reminders...')

            if dry_run:
                count = self._count_medicine_reminders()
                self.stdout.write(f'  Would create reminders for {count} user(s)')
            else:
                count = self._create_medicine_reminders(time_period)
                total_created += count
                if verbosity >= 1:
                    self.stdout.write(self.style.SUCCESS(f'  Created {count} medicine reminder(s)'))

        # Generate workout reminders (evening only)
        if (generate_all or workout_only) and time_period in ['evening', 'all']:
            if verbosity >= 1:
                self.stdout.write('Generating workout reminders...')

            if dry_run:
                count = self._count_workout_reminders()
                self.stdout.write(f'  Would create reminders for {count} user(s)')
            else:
                count = self._create_workout_reminders()
                total_created += count
                if verbosity >= 1:
                    self.stdout.write(self.style.SUCCESS(f'  Created {count} workout reminder(s)'))

        # Generate journal reminders (evening only)
        if (generate_all or journal_only) and time_period in ['evening', 'all']:
            if verbosity >= 1:
                self.stdout.write('Generating journal reminders...')

            if dry_run:
                count = self._count_journal_reminders()
                self.stdout.write(f'  Would create reminders for {count} user(s)')
            else:
                count = self._create_journal_reminders()
                total_created += count
                if verbosity >= 1:
                    self.stdout.write(self.style.SUCCESS(f'  Created {count} journal reminder(s)'))

        # Generate assistant chat check-ins (with quick reply buttons)
        if include_chat and not dry_run:
            if verbosity >= 1:
                self.stdout.write('Generating assistant chat check-ins...')
            chat_created = self._create_chat_checkins(
                generate_all, medicine_only, workout_only, journal_only, time_period
            )
            if verbosity >= 1:
                self.stdout.write(self.style.SUCCESS(f'  Created {chat_created} chat check-in(s)'))

        # Summary
        self.stdout.write('')
        if dry_run:
            self.stdout.write('DRY RUN complete - no changes made')
        else:
            self.stdout.write(self.style.SUCCESS(f'Total notifications created: {total_created}'))
            if include_chat:
                self.stdout.write(self.style.SUCCESS(f'Total chat check-ins created: {chat_created}'))

    def _count_medicine_reminders(self) -> int:
        """Count users who would get medicine reminders."""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        return User.objects.filter(
            preferences__health_enabled=True,
            preferences__notifications_enabled=True,
            medicines__medicine_status='active',
        ).distinct().count()

    def _create_medicine_reminders(self, time_period: str) -> int:
        """Create medicine reminder notifications."""
        from django.contrib.auth import get_user_model
        from apps.health.models import Medicine, MedicineLog
        from apps.core.services.notification_service import notification_service
        from apps.core.utils import get_user_today

        User = get_user_model()
        count = 0

        # Get users with active medicines and notifications enabled
        users = User.objects.filter(
            preferences__health_enabled=True,
            preferences__notifications_enabled=True,
            medicines__medicine_status='active',
        ).distinct().select_related('preferences').prefetch_related('medicines')

        for user in users:
            try:
                today = get_user_today(user)
                day_of_week = today.weekday()

                # Count pending doses for today
                pending_count = 0
                for medicine in user.medicines.filter(medicine_status='active'):
                    for schedule in medicine.schedules.filter(is_active=True):
                        if schedule.applies_to_day(day_of_week):
                            # Check if dose already logged
                            log = MedicineLog.objects.filter(
                                user=user,
                                medicine=medicine,
                                schedule=schedule,
                                scheduled_date=today
                            ).first()
                            if not log or log.log_status == 'pending':
                                pending_count += 1

                if pending_count == 0:
                    continue

                # Create notification
                if pending_count == 1:
                    title = "Medicine Reminder"
                    message = "You have 1 medicine dose to take today."
                else:
                    title = f"Medicine Reminder ({pending_count} doses)"
                    message = f"You have {pending_count} medicine doses still pending today."

                notification = notification_service.create_notification(
                    user=user,
                    category='medicine',
                    title=title,
                    message=message,
                    action_url='/health/physical/medicine/',
                )

                if notification:
                    count += 1

            except Exception as e:
                logger.warning(f"Failed to create medicine reminder for user {user.id}: {e}")

        logger.info(f"Created {count} medicine reminder notifications")
        return count

    def _count_workout_reminders(self) -> int:
        """Count users who would get workout reminders."""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        return User.objects.filter(
            preferences__health_enabled=True,
            preferences__notifications_enabled=True,
        ).count()

    def _create_workout_reminders(self) -> int:
        """Create workout reminder notifications for users who haven't worked out today."""
        from django.contrib.auth import get_user_model
        from apps.health.models import WorkoutSession
        from apps.core.services.notification_service import notification_service
        from apps.core.utils import get_user_today

        User = get_user_model()
        count = 0

        # Get users with health enabled
        users = User.objects.filter(
            preferences__health_enabled=True,
            preferences__notifications_enabled=True,
        ).select_related('preferences')

        for user in users:
            try:
                today = get_user_today(user)

                # Check if workout logged today
                workout_today = WorkoutSession.objects.filter(
                    user=user,
                    date=today
                ).exists()

                if workout_today:
                    continue

                # Check last workout date to vary messaging
                last_workout = WorkoutSession.objects.filter(
                    user=user
                ).order_by('-date').first()

                if last_workout:
                    days_since = (today - last_workout.date).days
                    if days_since == 0:
                        continue  # Already worked out today
                    elif days_since == 1:
                        message = "No workout logged yet today. Time to move!"
                    elif days_since <= 3:
                        message = f"It's been {days_since} days since your last workout. Get moving!"
                    else:
                        message = f"It's been {days_since} days since your last workout. Today's a good day to get back on track."
                else:
                    message = "No workout logged yet today. Time to get active!"

                notification = notification_service.create_notification(
                    user=user,
                    category='medicine',  # Uses health module category
                    title="Workout Reminder",
                    message=message,
                    action_url='/health/physical/fitness/',
                )

                if notification:
                    count += 1

            except Exception as e:
                logger.warning(f"Failed to create workout reminder for user {user.id}: {e}")

        logger.info(f"Created {count} workout reminder notifications")
        return count

    def _count_journal_reminders(self) -> int:
        """Count users who would get journal reminders."""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        return User.objects.filter(
            preferences__journal_enabled=True,
            preferences__notifications_enabled=True,
        ).count()

    def _create_journal_reminders(self) -> int:
        """Create journal reminder notifications for users who haven't journaled today."""
        from django.contrib.auth import get_user_model
        from apps.journal.models import JournalEntry
        from apps.core.services.notification_service import notification_service
        from apps.core.utils import get_user_today

        User = get_user_model()
        count = 0

        # Get users with journal enabled
        users = User.objects.filter(
            preferences__journal_enabled=True,
            preferences__notifications_enabled=True,
            preferences__notify_inapp_journal=True,
        ).select_related('preferences')

        for user in users:
            try:
                today = get_user_today(user)

                # Check if journaled today
                journaled_today = JournalEntry.objects.filter(
                    user=user,
                    entry_date=today
                ).exists()

                if journaled_today:
                    continue

                # Check streak to vary messaging
                last_entry = JournalEntry.objects.filter(
                    user=user
                ).order_by('-entry_date').first()

                if last_entry:
                    days_since = (today - last_entry.entry_date).days
                    if days_since == 0:
                        continue  # Already journaled today
                    elif days_since == 1:
                        message = "Don't break your journaling streak! Take a moment to reflect on today."
                    elif days_since <= 3:
                        message = f"It's been {days_since} days since you journaled. What's on your mind?"
                    else:
                        message = "Haven't journaled in a while. Today's a good day to start again."
                else:
                    message = "End your day with some reflection. Take a moment to journal."

                notification = notification_service.create_notification(
                    user=user,
                    category='journal',
                    title="Journal Reminder",
                    message=message,
                    action_url='/journal/entries/new/',
                )

                if notification:
                    count += 1

            except Exception as e:
                logger.warning(f"Failed to create journal reminder for user {user.id}: {e}")

        logger.info(f"Created {count} journal reminder notifications")
        return count

    def _create_chat_checkins(
        self,
        generate_all: bool,
        medicine_only: bool,
        workout_only: bool,
        journal_only: bool,
        time_period: str
    ) -> int:
        """
        Create interactive check-in messages in the assistant chat.

        These messages include quick reply buttons so users can respond
        with a single tap (e.g., "Yes, I took my medicine").
        """
        from django.contrib.auth import get_user_model
        from apps.ai.proactive_checkins import (
            generate_medicine_check_ins_for_user,
            generate_daily_check_ins_for_user,
        )

        User = get_user_model()
        count = 0

        # Get users with Personal Assistant enabled
        users = User.objects.filter(
            preferences__personal_assistant_enabled=True,
            preferences__personal_assistant_consent=True,
            preferences__ai_enabled=True,
            preferences__ai_data_consent=True,
        ).select_related('preferences')

        for user in users:
            try:
                # Medicine check-ins
                if generate_all or medicine_only:
                    if user.preferences.health_enabled:
                        generate_medicine_check_ins_for_user(user)
                        count += 1

                # Workout check-ins (evening only)
                if (generate_all or workout_only) and time_period in ['evening', 'all']:
                    if user.preferences.health_enabled:
                        generate_daily_check_ins_for_user(user, 'workout')
                        count += 1

                # Journal check-ins (evening only)
                if (generate_all or journal_only) and time_period in ['evening', 'all']:
                    if user.preferences.journal_enabled:
                        generate_daily_check_ins_for_user(user, 'journal')
                        count += 1

            except Exception as e:
                logger.warning(f"Failed to create chat check-ins for user {user.id}: {e}")

        return count
