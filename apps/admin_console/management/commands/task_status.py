# ==============================================================================
# File: apps/admin_console/management/commands/task_status.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command for Claude to query task status and get next task
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================
"""
Management command for Claude Code to query task status.

Usage:
    python manage.py task_status              # Show summary and next task
    python manage.py task_status --all        # Show all open tasks
    python manage.py task_status --next       # Show only the next task to work on
    python manage.py task_status --list       # List all tasks (open only)
    python manage.py task_status --completed  # Include completed tasks in list
"""

from django.core.management.base import BaseCommand

from apps.admin_console.models import ClaudeTask


class Command(BaseCommand):
    help = "Query Claude Task status and get next task to work on"

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Show all open tasks grouped by priority'
        )
        parser.add_argument(
            '--next',
            action='store_true',
            help='Show only the next task to work on'
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List all tasks in a table format'
        )
        parser.add_argument(
            '--completed',
            action='store_true',
            help='Include completed tasks in list'
        )

    def handle(self, *args, **options):
        if options['next']:
            self.show_next_task()
        elif options['all']:
            self.show_all_open_tasks()
        elif options['list']:
            self.show_task_list(include_completed=options['completed'])
        else:
            self.show_summary()

    def show_summary(self):
        """Show task summary and next task."""
        summary = ClaudeTask.get_status_summary()

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("CLAUDE TASK QUEUE STATUS")
        self.stdout.write("=" * 60)

        # Status counts
        self.stdout.write(f"\nActive (In Progress): {summary['active']}")
        self.stdout.write(f"Pending (New):        {summary['pending']}")
        self.stdout.write(f"Blocked:              {summary['blocked']}")
        self.stdout.write(f"Completed:            {summary['complete']}")

        # User action items
        if summary['action_required'] > 0:
            self.stdout.write(self.style.WARNING(
                f"\n⚠️  ACTION REQUIRED: {summary['action_required']} task(s) need user action"
            ))
        if summary['review'] > 0:
            self.stdout.write(self.style.SUCCESS(
                f"\n✓ REVIEW NEEDED: {summary['review']} task(s) ready for review"
            ))

        # Priority breakdown of pending tasks
        high = ClaudeTask.objects.filter(
            status=ClaudeTask.STATUS_NEW,
            priority=ClaudeTask.PRIORITY_HIGH
        ).count()
        medium = ClaudeTask.objects.filter(
            status=ClaudeTask.STATUS_NEW,
            priority=ClaudeTask.PRIORITY_MEDIUM
        ).count()
        low = ClaudeTask.objects.filter(
            status=ClaudeTask.STATUS_NEW,
            priority=ClaudeTask.PRIORITY_LOW
        ).count()

        self.stdout.write(f"\nPending by Priority:")
        self.stdout.write(f"  HIGH:   {high} (bugs, blocking issues)")
        self.stdout.write(f"  MEDIUM: {medium} (features, enhancements)")
        self.stdout.write(f"  LOW:    {low} (ideas, nice-to-haves)")

        # Next task
        self.stdout.write("\n" + "-" * 60)
        self.show_next_task()

    def show_next_task(self):
        """Show the next task to work on."""
        # Priority order for categories (bugs/security first, then features, then ideas)
        priority_categories = [
            ClaudeTask.CATEGORY_BUG,
            ClaudeTask.CATEGORY_SECURITY,
            ClaudeTask.CATEGORY_PERFORMANCE,
            ClaudeTask.CATEGORY_FEATURE,
            ClaudeTask.CATEGORY_ENHANCEMENT,
            ClaudeTask.CATEGORY_REFACTOR,
            ClaudeTask.CATEGORY_MAINTENANCE,
            ClaudeTask.CATEGORY_CLEANUP,
            ClaudeTask.CATEGORY_DOCUMENTATION,
            ClaudeTask.CATEGORY_IDEA,
        ]

        # First, check for in-progress tasks
        in_progress = ClaudeTask.objects.filter(
            status=ClaudeTask.STATUS_IN_PROGRESS
        ).first()

        if in_progress:
            self.stdout.write(self.style.WARNING("\n⏳ TASK IN PROGRESS:"))
            self._print_task_details(in_progress)
            return

        # Then check for HIGH priority NEW tasks
        next_task = ClaudeTask.objects.filter(
            status=ClaudeTask.STATUS_NEW,
            priority=ClaudeTask.PRIORITY_HIGH
        ).exclude(
            category__in=[ClaudeTask.CATEGORY_ACTION_REQUIRED, ClaudeTask.CATEGORY_REVIEW]
        ).first()

        if not next_task:
            # Then MEDIUM priority, ordered by category priority
            for category in priority_categories:
                next_task = ClaudeTask.objects.filter(
                    status=ClaudeTask.STATUS_NEW,
                    priority=ClaudeTask.PRIORITY_MEDIUM,
                    category=category
                ).first()
                if next_task:
                    break

        if not next_task:
            # Finally LOW priority
            for category in priority_categories:
                next_task = ClaudeTask.objects.filter(
                    status=ClaudeTask.STATUS_NEW,
                    priority=ClaudeTask.PRIORITY_LOW,
                    category=category
                ).first()
                if next_task:
                    break

        if next_task:
            self.stdout.write(self.style.SUCCESS("\n🎯 NEXT TASK:"))
            self._print_task_details(next_task)
        else:
            self.stdout.write(self.style.SUCCESS(
                "\n✅ All tasks complete! No pending tasks."
            ))

    def show_all_open_tasks(self):
        """Show all open tasks grouped by priority."""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("ALL OPEN TASKS")
        self.stdout.write("=" * 60)

        # HIGH priority
        high_tasks = ClaudeTask.objects.filter(
            status=ClaudeTask.STATUS_NEW,
            priority=ClaudeTask.PRIORITY_HIGH
        )
        if high_tasks.exists():
            self.stdout.write(self.style.ERROR("\n🔴 HIGH PRIORITY:"))
            for task in high_tasks:
                self.stdout.write(f"  [{task.task_id}] {task.title}")
                self.stdout.write(f"       Category: {task.get_category_display()}")

        # MEDIUM priority
        medium_tasks = ClaudeTask.objects.filter(
            status=ClaudeTask.STATUS_NEW,
            priority=ClaudeTask.PRIORITY_MEDIUM
        )
        if medium_tasks.exists():
            self.stdout.write(self.style.WARNING("\n🟡 MEDIUM PRIORITY:"))
            for task in medium_tasks:
                self.stdout.write(f"  [{task.task_id}] {task.title}")
                self.stdout.write(f"       Category: {task.get_category_display()}")

        # LOW priority
        low_tasks = ClaudeTask.objects.filter(
            status=ClaudeTask.STATUS_NEW,
            priority=ClaudeTask.PRIORITY_LOW
        )
        if low_tasks.exists():
            self.stdout.write(self.style.SUCCESS("\n🟢 LOW PRIORITY:"))
            for task in low_tasks:
                self.stdout.write(f"  [{task.task_id}] {task.title}")
                self.stdout.write(f"       Category: {task.get_category_display()}")

        # BLOCKED
        blocked_tasks = ClaudeTask.objects.filter(
            status=ClaudeTask.STATUS_BLOCKED
        )
        if blocked_tasks.exists():
            self.stdout.write(self.style.NOTICE("\n⛔ BLOCKED:"))
            for task in blocked_tasks:
                self.stdout.write(f"  [{task.task_id}] {task.title}")
                if task.notes:
                    self.stdout.write(f"       Reason: {task.notes[:100]}...")

    def show_task_list(self, include_completed=False):
        """Show all tasks in a table format."""
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("TASK LIST")
        self.stdout.write("=" * 80)
        self.stdout.write(f"\n{'Task ID':<12} {'Title':<40} {'Status':<12} {'Priority':<8}")
        self.stdout.write("-" * 80)

        if include_completed:
            tasks = ClaudeTask.objects.all().order_by('-status', 'priority', 'task_number')
        else:
            tasks = ClaudeTask.objects.exclude(
                status__in=[ClaudeTask.STATUS_COMPLETE, ClaudeTask.STATUS_CANCELLED]
            ).order_by('priority', 'task_number')

        for task in tasks:
            title = task.title[:38] + '..' if len(task.title) > 40 else task.title
            self.stdout.write(
                f"{task.task_id:<12} {title:<40} {task.status:<12} {task.priority:<8}"
            )

    def _print_task_details(self, task):
        """Print detailed task information."""
        self.stdout.write(f"\n  Task ID:    {task.task_id}")
        self.stdout.write(f"  Title:      {task.title}")
        self.stdout.write(f"  Status:     {task.get_status_display()}")
        self.stdout.write(f"  Priority:   {task.get_priority_display()}")
        self.stdout.write(f"  Category:   {task.get_category_display()}")

        if task.is_multi_phase:
            self.stdout.write(f"  Phase:      {task.current_phase}/{task.total_phases}")

        self.stdout.write(f"\n  Description:")
        for line in task.description.split('\n')[:5]:
            self.stdout.write(f"    {line}")
        if len(task.description.split('\n')) > 5:
            self.stdout.write(f"    ... (truncated)")

        if task.acceptance_criteria:
            self.stdout.write(f"\n  Acceptance Criteria:")
            for line in task.acceptance_criteria.split('\n')[:5]:
                self.stdout.write(f"    {line}")

        if task.notes:
            self.stdout.write(f"\n  Notes:")
            for line in task.notes.split('\n')[:3]:
                self.stdout.write(f"    {line}")
