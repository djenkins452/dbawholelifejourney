"""
Management command to create/update the Apple App Review demo account.

This account is used by Apple reviewers to test the app during App Store review.
It bypasses MFA and other security measures to allow reviewers to test freely.

Usage:
    python manage.py setup_app_review_account

The account will be created with:
- Email: appreview@wholelifejourney.com
- Password: AppReview2026!
- All modules enabled
- AI features enabled
- Sample data populated
- MFA and security checks bypassed
"""

import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from allauth.account.models import EmailAddress

from apps.users.models import User, UserPreferences


class Command(BaseCommand):
    help = "Create or update the Apple App Review demo account with sample data"

    def handle(self, *args, **options):
        email = "appreview@wholelifejourney.com"
        password = "AppReview2026!"

        # Create or get the user
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": "App",
                "last_name": "Reviewer",
                "date_of_birth": date(1990, 1, 15),
                "is_active": True,
                "is_app_review_account": True,
            },
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created new user: {email}"))
        else:
            self.stdout.write(f"User already exists: {email}")
            # Update fields to ensure proper state
            user.first_name = "App"
            user.last_name = "Reviewer"
            user.is_active = True
            user.is_app_review_account = True

        # Set password
        user.set_password(password)
        user.save()
        self.stdout.write(f"Password set to: {password}")

        # Create verified email address via allauth
        email_addr, email_created = EmailAddress.objects.get_or_create(
            user=user,
            email=email,
            defaults={
                "verified": True,
                "primary": True,
            },
        )
        if not email_created:
            email_addr.verified = True
            email_addr.primary = True
            email_addr.save()
        self.stdout.write(self.style.SUCCESS("Email verified via allauth"))

        # Setup preferences - enable all modules
        prefs, _ = UserPreferences.objects.get_or_create(user=user)

        # Mark onboarding complete
        prefs.has_completed_onboarding = True

        # Enable all available modules (Finance is coming soon, not available yet)
        prefs.health_enabled = True
        prefs.journal_enabled = True
        prefs.faith_enabled = True
        prefs.life_enabled = True
        prefs.purpose_enabled = True
        prefs.ai_enabled = True
        prefs.capture_enabled = True
        prefs.scan_enabled = True

        # Enable AI features
        prefs.ai_data_consent = True
        prefs.ai_data_consent_date = timezone.now()
        prefs.ai_personal_assistant_consent = True
        prefs.ai_personal_assistant_consent_date = timezone.now()
        prefs.ai_coaching_style = "supportive"

        # Set a nice theme
        prefs.theme = "nature"

        # Disable MFA requirement
        prefs.mfa_required = False

        prefs.save()
        self.stdout.write(self.style.SUCCESS("Preferences configured - all modules enabled"))

        # Create sample data
        self._create_sample_journal_entries(user)
        self._create_sample_health_data(user)
        self._create_sample_goals(user)
        self._create_sample_tasks(user)
        self._create_sample_prayers(user)

        self.stdout.write(self.style.SUCCESS("\nApp Review account ready!"))
        self.stdout.write(f"  Email: {email}")
        self.stdout.write(f"  Password: {password}")
        self.stdout.write("  URL: https://wholelifejourney.com/app-review/")

    def _create_sample_journal_entries(self, user):
        """Create sample journal entries."""
        try:
            from apps.journal.models import JournalEntry
        except ImportError:
            self.stdout.write("  Skipping journal entries (module not available)")
            return

        # Check if entries already exist
        if JournalEntry.objects.filter(user=user).exists():
            self.stdout.write("  Journal entries already exist, skipping")
            return

        entries = [
            {
                "title": "Starting my wellness journey",
                "body": "Today I decided to take my health more seriously. I've downloaded this app to help me track my progress and stay accountable. I'm excited to see where this journey takes me!",
                "mood": "great",
                "entry_date": timezone.now().date() - timedelta(days=7),
            },
            {
                "title": "Morning reflection",
                "body": "Woke up feeling refreshed after a good night's sleep. I've been trying to go to bed earlier and it's really making a difference. Planning to go for a walk later today.",
                "mood": "good",
                "entry_date": timezone.now().date() - timedelta(days=5),
            },
            {
                "title": "Grateful for small wins",
                "body": "Hit my step goal for the third day in a row! It's amazing how tracking these small things helps me stay motivated. Also had a great conversation with a friend today.",
                "mood": "great",
                "entry_date": timezone.now().date() - timedelta(days=3),
            },
            {
                "title": "Challenging day",
                "body": "Work was stressful today but I managed to take a short break to breathe and reset. Remembering that it's okay to have difficult days - tomorrow is a new opportunity.",
                "mood": "okay",
                "entry_date": timezone.now().date() - timedelta(days=1),
            },
            {
                "title": "Feeling balanced",
                "body": "Found a nice rhythm this week between work, exercise, and rest. The app has been helpful in keeping me aware of my habits and patterns.",
                "mood": "good",
                "entry_date": timezone.now().date(),
            },
        ]

        for entry_data in entries:
            JournalEntry.objects.create(user=user, **entry_data)

        self.stdout.write(f"  Created {len(entries)} journal entries")

    def _create_sample_health_data(self, user):
        """Create sample health metrics."""
        try:
            from apps.health.models import WeightEntry, StepsEntry, SleepEntry
        except ImportError:
            self.stdout.write("  Skipping health data (module not available)")
            return

        # Weight entries
        if not WeightEntry.objects.filter(user=user).exists():
            base_weight = Decimal("175.0")
            for i in range(14):
                entry_date = timezone.now().date() - timedelta(days=13 - i)
                # Slight downward trend with some variation
                weight = base_weight - Decimal(str(i * 0.2)) + Decimal(str(random.uniform(-0.5, 0.5)))
                WeightEntry.objects.create(
                    user=user,
                    value=round(weight, 1),
                    unit="lb",
                    recorded_at=timezone.make_aware(datetime.combine(entry_date, datetime.min.time().replace(hour=7))),
                )
            self.stdout.write("  Created 14 weight entries")

        # Steps entries
        if not StepsEntry.objects.filter(user=user).exists():
            for i in range(14):
                entry_date = timezone.now().date() - timedelta(days=13 - i)
                steps = random.randint(5000, 12000)
                StepsEntry.objects.create(
                    user=user,
                    count=steps,
                    logged_date=entry_date,
                    source="manual",
                )
            self.stdout.write("  Created 14 steps entries")

        # Sleep entries
        if not SleepEntry.objects.filter(user=user).exists():
            for i in range(7):
                sleep_date = timezone.now().date() - timedelta(days=6 - i)
                hours = random.uniform(6.0, 8.5)
                total_minutes = int(hours * 60)
                # Bedtime at 10-11 PM the night before
                bedtime = timezone.make_aware(datetime.combine(sleep_date, datetime.min.time().replace(hour=22 + random.randint(0, 1))))
                wake_time = bedtime + timedelta(minutes=total_minutes)
                SleepEntry.objects.create(
                    user=user,
                    sleep_date=sleep_date,
                    bedtime=bedtime,
                    wake_time=wake_time,
                    total_duration_minutes=total_minutes,
                    asleep_duration_minutes=int(total_minutes * 0.9),  # 90% sleep efficiency
                    quality_rating=random.choice(["good", "excellent", "fair"]),
                    source="manual",
                )
            self.stdout.write("  Created 7 sleep entries")

    def _create_sample_goals(self, user):
        """Create sample goals."""
        try:
            from apps.purpose.models import Goal
        except ImportError:
            self.stdout.write("  Skipping goals (module not available)")
            return

        if Goal.objects.filter(user=user).exists():
            self.stdout.write("  Goals already exist, skipping")
            return

        goals = [
            {
                "title": "Walk 10,000 steps daily",
                "description": "Build a consistent walking habit to improve cardiovascular health",
                "progress": 70,
            },
            {
                "title": "Read 12 books this year",
                "description": "One book per month to expand knowledge and relax",
                "progress": 25,
            },
            {
                "title": "Learn to cook 5 new healthy recipes",
                "description": "Improve cooking skills and eat healthier meals",
                "progress": 40,
            },
        ]

        for goal_data in goals:
            Goal.objects.create(user=user, **goal_data)

        self.stdout.write(f"  Created {len(goals)} goals")

    def _create_sample_tasks(self, user):
        """Create sample tasks."""
        try:
            from apps.life.models import Task
        except ImportError:
            self.stdout.write("  Skipping tasks (module not available)")
            return

        if Task.objects.filter(user=user).exists():
            self.stdout.write("  Tasks already exist, skipping")
            return

        tasks = [
            {"title": "Schedule annual checkup", "priority": "high"},
            {"title": "Buy groceries for the week", "priority": "medium"},
            {"title": "Call mom", "priority": "medium"},
            {"title": "Review monthly budget", "priority": "low"},
            {"title": "Plan weekend activities", "priority": "low"},
        ]

        for task_data in tasks:
            Task.objects.create(user=user, **task_data)

        self.stdout.write(f"  Created {len(tasks)} tasks")

    def _create_sample_prayers(self, user):
        """Create sample prayer requests."""
        try:
            from apps.faith.models import PrayerRequest
        except ImportError:
            self.stdout.write("  Skipping prayers (module not available)")
            return

        if PrayerRequest.objects.filter(user=user).exists():
            self.stdout.write("  Prayer requests already exist, skipping")
            return

        prayers = [
            {
                "title": "Guidance for career decision",
                "description": "Seeking wisdom about a potential job opportunity",
                "is_answered": False,
            },
            {
                "title": "Health for family member",
                "description": "Praying for my aunt's recovery from surgery",
                "is_answered": False,
            },
            {
                "title": "Gratitude for new home",
                "description": "Thankful prayer for finding a wonderful place to live",
                "is_answered": True,
            },
        ]

        for prayer_data in prayers:
            PrayerRequest.objects.create(user=user, **prayer_data)

        self.stdout.write(f"  Created {len(prayers)} prayer requests")
