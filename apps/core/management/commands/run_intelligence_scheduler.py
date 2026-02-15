"""
ISE — Management command to run the intelligence scheduler.

Usage:
    python manage.py run_intelligence_scheduler
    python manage.py run_intelligence_scheduler --dry-run

Designed to be called by Railway cron every 5 minutes.
"""

import logging

from django.core.management.base import BaseCommand

from apps.core.ai_scheduler.scheduler_engine import run_scheduler_cycle
from apps.core.ai_scheduler.scheduler_models import ScheduledIntelligenceTask

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run one cycle of the Intelligence Scheduler Engine (ISE)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show which tasks would run without executing them.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            self._dry_run()
            return

        self.stdout.write("ISE: Running scheduler cycle...")
        result = run_scheduler_cycle()

        self.stdout.write(
            f"ISE: Cycle complete — "
            f"executed={result['executed']}, "
            f"skipped={result['skipped']}, "
            f"failed={result['failed']}"
        )

    def _dry_run(self):
        """Show task status without executing."""
        from django.utils import timezone
        from apps.core.ai_scheduler.scheduler_engine import _ensure_task_records

        _ensure_task_records()

        tasks = ScheduledIntelligenceTask.objects.all()
        now = timezone.now()

        self.stdout.write("\nISE Scheduler Status (dry run):")
        self.stdout.write("-" * 60)

        for task in tasks:
            is_due = "DUE" if task.is_due else "waiting"
            active = "active" if task.is_active else "DISABLED"
            self.stdout.write(
                f"  {task.task_name}: {active}, {is_due}, "
                f"last={task.last_status}, runs={task.run_count}"
            )

        self.stdout.write("-" * 60)
        due_count = sum(1 for t in tasks if t.is_due)
        self.stdout.write(f"  {due_count} task(s) would execute.\n")
