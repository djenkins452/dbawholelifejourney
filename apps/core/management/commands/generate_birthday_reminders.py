# ==============================================================================
# File: apps/core/management/commands/generate_birthday_reminders.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to generate birthday and memorial notifications
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-05
# ==============================================================================
"""
Generate Birthday Reminders - Create notifications for birthdays and memorials.

This command creates notifications for:
- Pet birthdays (living pets)
- Pet memorials (passed pets)
- People birthdays (via SignificantEvent)
- Anniversaries and other significant events

Usage:
    # Generate all birthday reminders for today
    python manage.py generate_birthday_reminders

    # Check what would be generated
    python manage.py generate_birthday_reminders --dry-run

Schedule:
    Run daily at 7:00 AM user time (or hourly to catch users in different timezones)
    "0 12 * * *" for 12:00 PM UTC (7:00 AM EST)
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Generate birthday and memorial reminder notifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbosity = options['verbosity']

        from apps.core.services.notification_service import notification_service
        from apps.life.models import SignificantEvent
        from django.contrib.auth import get_user_model
        from apps.core.utils import get_user_today

        User = get_user_model()

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No notifications will be created'))

        total_created = 0
        today_events_by_user = {}

        # Get all users with notifications enabled
        users = User.objects.filter(
            preferences__notifications_enabled=True,
            preferences__life_enabled=True,
        ).select_related('preferences')

        for user in users:
            try:
                today = get_user_today(user)

                # Find events that are today for this user
                events_today = SignificantEvent.objects.filter(
                    user=user,
                    event_date__month=today.month,
                    event_date__day=today.day,
                )

                for event in events_today:
                    if dry_run:
                        self.stdout.write(f"  Would notify {user.email}: {event.title}")
                        total_created += 1
                        continue

                    # Generate appropriate message based on event type
                    message, icon = self._generate_message(event)

                    notification = notification_service.create_notification(
                        user=user,
                        category='significant_event',
                        title=event.title,
                        message=message,
                        action_url=event.get_absolute_url(),
                        icon=icon,
                        source_object=event,
                    )

                    if notification:
                        total_created += 1
                        if verbosity >= 2:
                            self.stdout.write(f"  Created: {event.title} for {user.email}")

            except Exception as e:
                logger.warning(f"Failed to generate birthday reminders for user {user.id}: {e}")

        # Summary
        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'Would have created {total_created} notification(s)'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Created {total_created} birthday/event notification(s)'))

    def _generate_message(self, event):
        """Generate notification message and icon based on event type."""
        years_display = event.get_years_display()
        person_name = event.person_name or event.title

        if event.event_type == 'birthday':
            if years_display:
                message = f"Happy {years_display} Birthday to {person_name}! 🎂"
            else:
                message = f"Happy Birthday to {person_name}! 🎂"
            icon = "🎂"

        elif event.event_type == 'memorial':
            if years_display:
                message = f"Remembering {person_name} today 🌈 They would have been {years_display}."
            else:
                message = f"Remembering {person_name} today 🌈"
            icon = "🌈"

        elif event.event_type == 'anniversary':
            if years_display:
                message = f"Happy {years_display} Anniversary! 💕"
            else:
                message = f"Happy Anniversary! 💕"
            icon = "💕"

        elif event.event_type == 'milestone':
            message = f"Today marks: {event.title}"
            icon = "🏆"

        else:
            message = event.description or f"Today is {event.title}"
            icon = "📅"

        return message, icon
