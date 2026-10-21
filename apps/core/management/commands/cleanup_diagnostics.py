"""
Cleanup old diagnostics data (EngineRun, EngineSpan, DecisionRecord).

Thin alias for ``prune_telemetry --only engine_run --only engine_span
--only decision_record``. Retention windows live in apps/core/data_retention.py.
The old fixed 7-day window was removed: it deleted the only run of weekly
engines, which hid their MISSED/starvation alerts (heartbeat NEVER_RUN).

Usage:
    python manage.py cleanup_diagnostics
    python manage.py cleanup_diagnostics --dry-run

Project: Whole Life Journey
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Delete expired diagnostics rows (policy windows in apps/core/data_retention.py)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        call_command(
            "prune_telemetry",
            only=["engine_run", "engine_span", "decision_record"],
            dry_run=options["dry_run"],
            stdout=self.stdout,
        )
