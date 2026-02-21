"""
Cleanup old diagnostics data (EngineRun, EngineSpan, DecisionRecord).

Usage:
    python manage.py cleanup_diagnostics          # 7 day default
    python manage.py cleanup_diagnostics --days 3  # custom retention

Project: Whole Life Journey
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Delete diagnostics data older than N days (default 7)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Retention period in days (default: 7).",
        )

    def handle(self, *args, **options):
        from apps.core.ai_observability.models import (
            DecisionRecord,
            EngineRun,
            EngineSpan,
        )

        days = options["days"]
        cutoff = timezone.now() - timedelta(days=days)

        runs_deleted, _ = EngineRun.objects.filter(created_at__lt=cutoff).delete()
        spans_deleted, _ = EngineSpan.objects.filter(started_at__lt=cutoff).delete()
        decisions_deleted, _ = DecisionRecord.objects.filter(
            created_at__lt=cutoff
        ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Cleaned up diagnostics data older than {days} days: "
                f"runs={runs_deleted}, spans={spans_deleted}, "
                f"decisions={decisions_deleted}"
            )
        )
