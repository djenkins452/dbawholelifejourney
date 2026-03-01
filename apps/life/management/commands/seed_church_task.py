"""
Seed a recurring "Go to Church" task for a user.

Creates a weekly:sun recurring task linked to the faith module.
Safe to run multiple times — skips if task already exists.

Usage:
    python manage.py seed_church_task
    python manage.py seed_church_task user@example.com
"""
from datetime import date, time, timedelta

from django.core.management.base import BaseCommand

from apps.life.models import Task
from apps.users.models import User


class Command(BaseCommand):
    help = "Create a recurring 'Go to Church' task linked to faith module"

    def add_arguments(self, parser):
        parser.add_argument(
            "email",
            nargs="?",
            default="dannyjenkins71@gmail.com",
            type=str,
            help="Email of the user (default: dannyjenkins71@gmail.com)",
        )

    def handle(self, *args, **options):
        email = options["email"]

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(f"User {email} not found. Skipping.")
            )
            return

        # Check for existing
        existing = Task.objects.filter(
            user=user,
            title="Go to Church",
            is_recurring=True,
            deleted_at__isnull=True,
        ).first()

        if existing:
            self.stdout.write(
                self.style.WARNING(
                    f"'Go to Church' task already exists (pk={existing.pk}). Skipping."
                )
            )
            return

        # Find next Sunday for initial due_date
        today = date.today()
        days_until_sunday = (6 - today.weekday()) % 7
        if days_until_sunday == 0:
            days_until_sunday = 7  # If today is Sunday, start next Sunday
        next_sunday = today + timedelta(days=days_until_sunday)

        task = Task.objects.create(
            user=user,
            title="Go to Church",
            notes="Weekly church attendance — counts as daily faith engagement.",
            module="faith",
            is_recurring=True,
            recurrence_pattern="weekly:sun",
            is_routine=True,
            scheduled_time=time(9, 0),
            scheduled_end_time=time(12, 0),
            due_date=next_sunday,
            start_date=today,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created 'Go to Church' task (pk={task.pk}) "
                f"for {user.email}, first due {next_sunday}"
            )
        )
