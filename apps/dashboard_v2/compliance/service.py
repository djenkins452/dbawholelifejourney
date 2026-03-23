"""
Compliance Event Service — orchestrates evaluation, persistence, and rollup.

This is the primary API for the compliance audit system.

Usage:
    from apps.dashboard_v2.compliance.service import ComplianceService

    svc = ComplianceService(user)
    svc.evaluate_week()                          # Generate events for this week
    summary = svc.get_rollup("medication_doses")  # Get card summary
    detail = svc.get_detail("medication_doses")   # Get drill-down rows
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q

from apps.core.utils import get_user_today
from apps.dashboard_v2.compliance.adapters import evaluate_all_domains
from apps.dashboard_v2.compliance.constants import (
    FINAL_COMPLETED,
    FINAL_COMPLETED_LATE,
    FINAL_EXCLUDED_FROM_DENOMINATOR,
    FINAL_MISSED,
    FINAL_NEGATIVE,
    FINAL_NOT_EXPECTED,
    FINAL_OVERDUE,
    FINAL_POSITIVE,
    FINAL_SKIPPED,
    FINAL_STATUS_LABELS,
    REASON_LABELS,
    SCORING_BUCKETS,
)
from apps.dashboard_v2.compliance.models import ComplianceEvent

logger = logging.getLogger(__name__)


class ComplianceService:
    """Orchestrates compliance event generation, rollup, and querying."""

    def __init__(self, user):
        self.user = user
        self.today = get_user_today(user)

    def get_week_range(self):
        """Return (start_date, end_date) for the current 7-day window."""
        end_date = self.today
        start_date = end_date - timedelta(days=6)
        return start_date, end_date

    def evaluate_week(self):
        """
        Generate compliance events for the current 7-day window.

        Deletes existing events for the window and replaces with fresh evaluation.
        This ensures the data is always current.
        """
        start_date, end_date = self.get_week_range()
        return self.evaluate_range(start_date, end_date)

    def evaluate_range(self, start_date, end_date):
        """
        Generate compliance events for a date range.

        Replaces existing events for the same user/date range.
        Returns count of events created.
        """
        event_dicts = evaluate_all_domains(self.user, start_date, end_date)

        with transaction.atomic():
            # Clear old events for this range
            ComplianceEvent.objects.filter(
                user=self.user,
                event_date__gte=start_date,
                event_date__lte=end_date,
            ).delete()

            # Bulk create new events
            events = []
            for d in event_dicts:
                events.append(ComplianceEvent(**d))

            if events:
                ComplianceEvent.objects.bulk_create(events)

        return len(events)

    def get_rollup(self, scoring_bucket, start_date=None, end_date=None):
        """
        Get summary counts for a scoring bucket.

        Returns:
            {
                'bucket': str,
                'expected': int,
                'completed': int,
                'completed_late': int,
                'skipped': int,
                'missed': int,
                'overdue': int,
                'completion_pct': float,
                'missed_label': str,  # e.g., "Missed 3 medication doses"
            }
        """
        if start_date is None or end_date is None:
            start_date, end_date = self.get_week_range()

        qs = ComplianceEvent.objects.filter(
            user=self.user,
            scoring_bucket=scoring_bucket,
            event_date__gte=start_date,
            event_date__lte=end_date,
            expected=True,
        )

        counts = qs.aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(final_status=FINAL_COMPLETED)),
            completed_late=Count("id", filter=Q(final_status=FINAL_COMPLETED_LATE)),
            skipped=Count("id", filter=Q(final_status=FINAL_SKIPPED)),
            missed=Count("id", filter=Q(final_status=FINAL_MISSED)),
            overdue=Count("id", filter=Q(final_status=FINAL_OVERDUE)),
        )

        expected = counts["total"]
        completed = counts["completed"]
        completed_late = counts["completed_late"]
        skipped = counts["skipped"]
        missed = counts["missed"]
        overdue = counts["overdue"]

        # Denominator: expected minus skipped (skipped are intentional)
        denominator = expected - skipped
        numerator = completed + completed_late

        completion_pct = round((numerator / denominator) * 100) if denominator > 0 else 100

        # Build missed label
        total_negative = missed + overdue
        bucket_label = scoring_bucket.replace("_", " ").title()
        missed_label = f"Missed {total_negative} {bucket_label.lower()}" if total_negative > 0 else None

        return {
            "bucket": scoring_bucket,
            "expected": expected,
            "completed": completed,
            "completed_late": completed_late,
            "skipped": skipped,
            "missed": missed,
            "overdue": overdue,
            "completion_pct": completion_pct,
            "missed_label": missed_label,
        }

    def get_all_rollups(self, start_date=None, end_date=None):
        """Get rollups for all scoring buckets."""
        return {
            bucket: self.get_rollup(bucket, start_date, end_date)
            for bucket in SCORING_BUCKETS
        }

    def get_detail(self, scoring_bucket, start_date=None, end_date=None,
                   status_filter=None):
        """
        Get detailed event rows for drill-down UI.

        Args:
            scoring_bucket: Which card to drill into
            start_date, end_date: Date range (default: this week)
            status_filter: Optional final_status to filter by (e.g., 'missed')

        Returns:
            List of dicts grouped by date, ready for template rendering.
        """
        if start_date is None or end_date is None:
            start_date, end_date = self.get_week_range()

        qs = ComplianceEvent.objects.filter(
            user=self.user,
            scoring_bucket=scoring_bucket,
            event_date__gte=start_date,
            event_date__lte=end_date,
            expected=True,
        ).order_by("-event_date", "expected_at", "item_label")

        if status_filter:
            qs = qs.filter(final_status=status_filter)

        # Group by date
        grouped = {}
        for event in qs:
            date_key = event.event_date
            if date_key not in grouped:
                grouped[date_key] = {
                    "date": date_key,
                    "items": [],
                }
            grouped[date_key]["items"].append({
                "id": event.id,
                "domain": event.domain,
                "item_label": event.item_label,
                "expected_at": event.expected_at,
                "expected": event.expected,
                "actual_status": event.actual_status,
                "final_status": event.final_status,
                "final_status_label": event.final_status_label,
                "reason_code": event.reason_code,
                "reason_label": event.reason_label,
                "source_system": event.source_system,
                "reason_detail": event.reason_detail or {},
            })

        # Return as sorted list (newest first)
        return sorted(grouped.values(), key=lambda x: x["date"], reverse=True)
