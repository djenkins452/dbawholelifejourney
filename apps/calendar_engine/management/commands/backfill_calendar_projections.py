"""
One-time backfill: Project all existing tasks, goals, milestones, and habits
to the calendar engine.

Items created before the signal wiring was added have no CalendarEvent records.
This command creates them using the same projection functions the signals use.

Safe to run multiple times — all upsert functions check for existing records.

Usage:
    python manage.py backfill_calendar_projections
    python manage.py backfill_calendar_projections --dry-run
"""

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill CalendarEvent records for all existing tasks, goals, milestones, and habits"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Count items that would be projected without creating records',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        prefix = "[DRY RUN] " if dry_run else ""

        from apps.life.models import Task
        from apps.purpose.models import LifeGoal, GoalMilestone, HabitGoal
        from apps.calendar_engine.services.projection import (
            upsert_from_task,
            upsert_from_goal,
            _upsert_milestone_marker,
            upsert_from_habit,
        )

        # --- Tasks ---
        tasks_with_dates = Task.objects.filter(
            due_date__isnull=False,
            deleted_at__isnull=True,
        ).select_related('user', 'user__preferences')

        task_count = tasks_with_dates.count()
        self.stdout.write(f"{prefix}Processing {task_count} tasks with due dates...")

        task_created = 0
        task_errors = 0
        if not dry_run:
            for task in tasks_with_dates.iterator():
                try:
                    upsert_from_task(task)
                    task_created += 1
                except Exception as e:
                    task_errors += 1
                    logger.warning("Failed to project task %s: %s", task.pk, e)

        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Tasks: {task_created} projected, {task_errors} errors"
        ))

        # --- Goals ---
        goals = LifeGoal.objects.filter(
            deleted_at__isnull=True,
        ).select_related('user', 'domain').prefetch_related('milestones')

        goal_count = goals.count()
        self.stdout.write(f"{prefix}Processing {goal_count} goals...")

        goal_created = 0
        goal_errors = 0
        if not dry_run:
            for goal in goals.iterator():
                try:
                    upsert_from_goal(goal)
                    goal_created += 1
                except Exception as e:
                    goal_errors += 1
                    logger.warning("Failed to project goal %s: %s", goal.pk, e)

        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Goals: {goal_created} projected, {goal_errors} errors"
        ))

        # --- Habits ---
        habits = HabitGoal.objects.filter(
            deleted_at__isnull=True,
            status='active',
        ).select_related('user', 'domain')

        habit_count = habits.count()
        self.stdout.write(f"{prefix}Processing {habit_count} active habits...")

        habit_created = 0
        habit_errors = 0
        if not dry_run:
            for habit in habits.iterator():
                try:
                    upsert_from_habit(habit)
                    habit_created += 1
                except Exception as e:
                    habit_errors += 1
                    logger.warning("Failed to project habit %s: %s", habit.pk, e)

        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Habits: {habit_created} projected, {habit_errors} errors"
        ))

        # --- Summary ---
        total = task_created + goal_created + habit_created
        total_errors = task_errors + goal_errors + habit_errors
        self.stdout.write(self.style.SUCCESS(
            f"\n{prefix}TOTAL: {total} items projected to calendar, {total_errors} errors"
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"\nDry run complete. Would project: {task_count} tasks, "
                f"{goal_count} goals, {habit_count} habits"
            ))
