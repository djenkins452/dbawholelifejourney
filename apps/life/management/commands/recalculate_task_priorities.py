# ==============================================================================
# File: apps/life/management/commands/recalculate_task_priorities.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to recalculate task priorities based on due dates
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================
"""
Management command to recalculate task priorities.

This command updates the priority (Now/Soon/Someday) of all incomplete tasks
based on their due dates relative to today. Run nightly to ensure tasks
automatically move from "Soon" to "Now" as their due dates approach.

Run via scheduler or manually:
    python manage.py recalculate_task_priorities
"""

from django.core.management.base import BaseCommand
from django.db.models import F

from apps.life.models import Task
from apps.core.utils import get_user_today


class Command(BaseCommand):
    help = 'Recalculate task priorities based on due dates'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)

        # Get all incomplete tasks with a due date
        tasks_with_due_date = Task.objects.filter(
            is_completed=False,
            due_date__isnull=False
        ).select_related('user', 'user__preferences')

        updated_count = 0
        changes = {'now': 0, 'soon': 0, 'someday': 0}

        for task in tasks_with_due_date:
            # Calculate what the priority should be
            user_today = get_user_today(task.user)
            new_priority = task.calculate_priority(user_today=user_today)

            # Only update if priority has changed
            if task.priority != new_priority:
                old_priority = task.priority
                if not dry_run:
                    # Update directly to avoid triggering full save() which
                    # would recalculate anyway (and we already have the value)
                    Task.objects.filter(pk=task.pk).update(priority=new_priority)

                changes[new_priority] = changes.get(new_priority, 0) + 1
                updated_count += 1

                if options.get('verbosity', 1) > 1:
                    self.stdout.write(
                        f"  Task '{task.title}' ({task.user.email}): "
                        f"{old_priority} -> {new_priority}"
                    )

        # Output summary
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'[DRY RUN] Would update {updated_count} task(s)')
            )
        elif updated_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Updated {updated_count} task priorities '
                    f'(now: {changes["now"]}, soon: {changes["soon"]}, '
                    f'someday: {changes["someday"]})'
                )
            )
        else:
            self.stdout.write('No task priority changes needed')
