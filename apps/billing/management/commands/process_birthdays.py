"""
Management command to process birthday-related tier transitions.

Handles:
1. 30 days before 23rd birthday: Send preview email
2. On 23rd birthday: Set graduation_date (1 year gift), send celebration email
3. 30 days before graduation: Send reminder email
4. On graduation date: Transition to Adult tier

Run daily (recommended: 3am in user's timezone or server timezone).

Usage:
    python manage.py process_birthdays
    python manage.py process_birthdays --dry-run
"""

import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.billing.models import BillingProfile
from apps.billing.services import calculate_age

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process birthday-related tier transitions for students'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = timezone.now().date()

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made"))

        # Process each stage
        self.process_birthday_previews(today, dry_run)
        self.process_birthdays(today, dry_run)
        self.process_graduation_reminders(today, dry_run)
        self.process_graduations(today, dry_run)

        self.stdout.write(self.style.SUCCESS("Birthday processing complete"))

    def process_birthday_previews(self, today, dry_run):
        """
        Send preview emails to students turning 23 in 30 days.
        """
        target_date = today + timedelta(days=30)

        # Find students whose 23rd birthday is in 30 days
        profiles = self._get_students_with_birthday_in_days(30)

        count = 0
        for profile in profiles:
            age = calculate_age(profile.user.date_of_birth)
            if age == 22:  # Will turn 23
                count += 1
                self.stdout.write(
                    f"  Birthday preview: {profile.user.email} turning 23 on "
                    f"{self._get_birthday_this_year(profile.user.date_of_birth)}"
                )
                if not dry_run:
                    # TODO: Send birthday_preview email
                    pass

        self.stdout.write(f"Birthday previews: {count} users")

    def process_birthdays(self, today, dry_run):
        """
        Process users turning 23 today.

        Sets graduation_date to 1 year from now (gift year at student rate).
        """
        profiles = self._get_students_with_birthday_today()

        count = 0
        for profile in profiles:
            age = calculate_age(profile.user.date_of_birth)
            if age == 23:  # Just turned 23 today
                count += 1
                graduation_date = today + timedelta(days=365)

                self.stdout.write(
                    f"  Happy 23rd birthday: {profile.user.email} - "
                    f"gift year until {graduation_date}"
                )

                if not dry_run:
                    profile.graduation_date = graduation_date
                    profile.tier_locked_until = graduation_date
                    profile.save(update_fields=[
                        'graduation_date',
                        'tier_locked_until',
                        'updated_at'
                    ])
                    # TODO: Send birthday_celebration email
                    logger.info(
                        f"Set graduation date for {profile.user.email}: {graduation_date}"
                    )

        self.stdout.write(f"23rd birthdays: {count} users")

    def process_graduation_reminders(self, today, dry_run):
        """
        Send reminders to students graduating in 30 days.
        """
        target_date = today + timedelta(days=30)

        profiles = BillingProfile.objects.filter(
            pricing_tier=BillingProfile.TIER_STUDENT,
            graduation_date=target_date,
            subscription_status=BillingProfile.STATUS_ACTIVE,
        ).select_related('user')

        count = 0
        for profile in profiles:
            count += 1
            self.stdout.write(
                f"  Graduation reminder: {profile.user.email} graduates on {profile.graduation_date}"
            )
            if not dry_run:
                # TODO: Send graduation_reminder email
                pass

        self.stdout.write(f"Graduation reminders: {count} users")

    def process_graduations(self, today, dry_run):
        """
        Graduate students whose graduation_date is today.

        Transitions them from Student to Adult tier.
        """
        profiles = BillingProfile.objects.filter(
            pricing_tier=BillingProfile.TIER_STUDENT,
            graduation_date=today,
            subscription_status=BillingProfile.STATUS_ACTIVE,
        ).select_related('user')

        count = 0
        for profile in profiles:
            count += 1
            self.stdout.write(
                f"  Graduating: {profile.user.email} from Student to Adult"
            )

            if not dry_run:
                with transaction.atomic():
                    profile.pricing_tier = BillingProfile.TIER_ADULT
                    profile.tier_locked_until = None
                    profile.save(update_fields=[
                        'pricing_tier',
                        'tier_locked_until',
                        'updated_at'
                    ])

                    # TODO: Update Stripe subscription to Adult pricing
                    # TODO: Send graduation_complete email

                    logger.info(f"Graduated {profile.user.email} to Adult tier")

        self.stdout.write(f"Graduations: {count} users")

    def _get_students_with_birthday_in_days(self, days):
        """
        Get students whose birthday anniversary is in X days.
        """
        today = timezone.now().date()
        target_date = today + timedelta(days=days)

        # Get all student profiles
        profiles = BillingProfile.objects.filter(
            pricing_tier=BillingProfile.TIER_STUDENT,
            subscription_status=BillingProfile.STATUS_ACTIVE,
        ).select_related('user')

        # Filter by birthday (month and day match)
        matching = []
        for profile in profiles:
            dob = profile.user.date_of_birth
            if dob and dob.month == target_date.month and dob.day == target_date.day:
                matching.append(profile)

        return matching

    def _get_students_with_birthday_today(self):
        """
        Get students whose birthday is today.
        """
        return self._get_students_with_birthday_in_days(0)

    def _get_birthday_this_year(self, date_of_birth):
        """
        Get this year's birthday date for a DOB.
        """
        if not date_of_birth:
            return None
        today = timezone.now().date()
        return date_of_birth.replace(year=today.year)
