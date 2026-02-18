"""
Phase 4 CoS — Backfill Engagement Signals.

Backfills feedback loop data from existing records for the last 30 days:
1. BriefingEngagement — from DailyBriefing and WeeklyIntelligenceReport
2. InsightEngagement — from Insight status changes
3. InterventionEffectivenessProfile — from InterventionLog responses

Usage:
    python manage.py backfill_phase4_engagement
    python manage.py backfill_phase4_engagement --days 60
    python manage.py backfill_phase4_engagement --dry-run
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill Phase 4 engagement signals from existing records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days to look back (default: 30)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing to DB.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timedelta(days=days)

        self.stdout.write(f"Backfilling Phase 4 engagement (last {days} days)...")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no data will be written"))

        briefing_count = self._backfill_briefings(cutoff, dry_run)
        report_count = self._backfill_reports(cutoff, dry_run)
        insight_count = self._backfill_insights(cutoff, dry_run)
        intervention_count = self._backfill_interventions(cutoff, dry_run)

        self.stdout.write(self.style.SUCCESS(
            f"Done. Briefings: {briefing_count}, Reports: {report_count}, "
            f"Insights: {insight_count}, Interventions: {intervention_count}"
        ))

    def _backfill_briefings(self, cutoff, dry_run):
        """Backfill BriefingEngagement from existing DailyBriefings."""
        try:
            from apps.core.ai_briefing.models import DailyBriefing
            from apps.core.ai_feedback.briefing_tracker import record_briefing_opened
            from apps.core.ai_feedback.models import BriefingEngagement

            briefings = DailyBriefing.objects.filter(
                created_at__gte=cutoff,
            ).select_related("user")

            count = 0
            for briefing in briefings:
                # Skip if engagement already exists
                exists = BriefingEngagement.objects.filter(
                    user=briefing.user,
                    content_type="daily_briefing",
                    content_id=briefing.id,
                ).exists()
                if exists:
                    continue

                if not dry_run:
                    record_briefing_opened(
                        briefing.user, "daily_briefing", briefing.id
                    )
                count += 1

            self.stdout.write(f"  Briefings: {count} {'would be' if dry_run else ''} backfilled")
            return count

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  Briefings backfill failed: {e}"))
            return 0

    def _backfill_reports(self, cutoff, dry_run):
        """Backfill BriefingEngagement from existing WeeklyIntelligenceReports."""
        try:
            from apps.core.ai_weekly_report.models import WeeklyIntelligenceReport
            from apps.core.ai_feedback.briefing_tracker import record_briefing_opened
            from apps.core.ai_feedback.models import BriefingEngagement

            reports = WeeklyIntelligenceReport.objects.filter(
                created_at__gte=cutoff,
            ).select_related("user")

            count = 0
            for report in reports:
                exists = BriefingEngagement.objects.filter(
                    user=report.user,
                    content_type="weekly_report",
                    content_id=report.id,
                ).exists()
                if exists:
                    continue

                if not dry_run:
                    record_briefing_opened(
                        report.user, "weekly_report", report.id
                    )
                count += 1

            self.stdout.write(f"  Reports: {count} {'would be' if dry_run else ''} backfilled")
            return count

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  Reports backfill failed: {e}"))
            return 0

    def _backfill_insights(self, cutoff, dry_run):
        """Backfill InsightEngagement from Insight status changes."""
        try:
            from apps.core.ai_insights.models import Insight
            from apps.core.ai_feedback.insight_tracker import record_insight_engagement
            from apps.core.ai_feedback.models import InsightEngagement

            # Get insights that have been read or dismissed
            insights = Insight.objects.filter(
                updated_at__gte=cutoff,
                status__in=["read", "dismissed"],
            ).select_related("user")

            count = 0
            for insight in insights:
                # Skip if engagement already recorded
                exists = InsightEngagement.objects.filter(
                    user=insight.user,
                    insight=insight,
                ).exists()
                if exists:
                    continue

                event_type = "dismissed" if insight.status == "dismissed" else "viewed"
                if not dry_run:
                    record_insight_engagement(insight.user, insight, event_type)
                count += 1

            self.stdout.write(f"  Insights: {count} {'would be' if dry_run else ''} backfilled")
            return count

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  Insights backfill failed: {e}"))
            return 0

    def _backfill_interventions(self, cutoff, dry_run):
        """Backfill InterventionEffectivenessProfile from InterventionLog responses."""
        try:
            from apps.core.blueprint.models import InterventionLog
            from apps.core.ai_feedback.intervention_tracker import evaluate_intervention_effectiveness

            # Get users with responded interventions
            responded = InterventionLog.objects.filter(
                responded_at__gte=cutoff,
                user_response__in=["accepted", "dismissed", "proceeded"],
            ).values_list("user_id", flat=True).distinct()

            count = 0
            for user_id in responded:
                from apps.users.models import User
                try:
                    user = User.objects.get(id=user_id)
                    if not dry_run:
                        evaluate_intervention_effectiveness(user)
                    count += 1
                except User.DoesNotExist:
                    continue

            self.stdout.write(f"  Interventions: {count} users {'would be' if dry_run else ''} evaluated")
            return count

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  Interventions backfill failed: {e}"))
            return 0
