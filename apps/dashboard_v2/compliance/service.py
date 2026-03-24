"""
Compliance Event Service — orchestrates evaluation, reconciliation, and rollup.

Pipeline:
    adapters → raw events → reconcile() → persist → rollup / detail queries

Caching:
    evaluate_week() results are cached for 2 minutes per user.
    Cache is invalidated on domain-level writes (workout log, routine log, etc.)
    via invalidate_compliance_cache(user).

Usage:
    from apps.dashboard_v2.compliance.service import ComplianceService

    svc = ComplianceService(user)
    svc.ensure_evaluated()                       # Evaluate if stale
    summary = svc.get_rollup("medication_doses")  # Get card summary
    detail = svc.get_detail("medication_doses")   # Get drill-down rows
"""

import logging
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Q

from apps.core.utils import get_user_today
from apps.dashboard_v2.compliance.adapters import evaluate_all_domains
from apps.dashboard_v2.compliance.constants import (
    FINAL_COMPLETED,
    FINAL_COMPLETED_LATE,
    FINAL_MISSED,
    FINAL_OVERDUE,
    FINAL_SKIPPED,
    SCORING_BUCKETS,
)
from apps.dashboard_v2.compliance.models import ComplianceEvent
from apps.dashboard_v2.compliance.reconciliation import reconcile_events

logger = logging.getLogger(__name__)

# Cache TTL: 2 minutes — short enough to stay fresh, long enough to
# avoid recomputing on every drill-down page load.
_CACHE_TTL = 120
_CACHE_PREFIX = "compliance:evaluated"


def _cache_key(user_id, week_start):
    return f"{_CACHE_PREFIX}:{user_id}:{week_start}"


def invalidate_compliance_cache(user):
    """
    Invalidate compliance cache for a user. Call this when domain data changes
    (new workout log, routine completion, medicine log, etc.).
    """
    try:
        today = get_user_today(user)
        week_start = today - timedelta(days=6)
        cache.delete(_cache_key(user.id, week_start))
        # Also invalidate yesterday's key in case of timezone boundary drift
        yesterday_start = today - timedelta(days=7)
        cache.delete(_cache_key(user.id, yesterday_start))
    except Exception:
        logger.debug("Compliance cache invalidation failed", exc_info=True)


class ComplianceService:
    """Orchestrates compliance event generation, reconciliation, rollup, and querying."""

    def __init__(self, user):
        self.user = user
        self.today = get_user_today(user)

    def get_week_range(self):
        """Return (start_date, end_date) for the current 7-day window."""
        end_date = self.today
        start_date = end_date - timedelta(days=6)
        return start_date, end_date

    def ensure_evaluated(self):
        """
        Evaluate the current week if not already cached.

        This is the recommended entry point — avoids redundant recomputation.
        """
        start_date, end_date = self.get_week_range()
        key = _cache_key(self.user.id, start_date)

        if cache.get(key):
            return  # Already fresh

        self.evaluate_range(start_date, end_date)
        cache.set(key, True, _CACHE_TTL)

    def evaluate_week(self):
        """
        Force-evaluate compliance events for the current 7-day window.

        Bypasses cache. Use ensure_evaluated() for normal reads.
        """
        start_date, end_date = self.get_week_range()
        count = self.evaluate_range(start_date, end_date)
        cache.set(_cache_key(self.user.id, start_date), True, _CACHE_TTL)
        return count

    def evaluate_range(self, start_date, end_date):
        """
        Generate, reconcile, and persist compliance events for a date range.

        Returns count of events created.
        """
        event_dicts = evaluate_all_domains(self.user, start_date, end_date)
        reconcile_events(event_dicts, self.user)

        with transaction.atomic():
            ComplianceEvent.objects.filter(
                user=self.user,
                event_date__gte=start_date,
                event_date__lte=end_date,
            ).delete()

            events = [ComplianceEvent(**d) for d in event_dicts]
            if events:
                ComplianceEvent.objects.bulk_create(events)

        return len(events)

    def get_rollup(self, scoring_bucket, start_date=None, end_date=None):
        """
        Get summary counts for a scoring bucket.

        Only counts score-bearing events (is_primary=True).
        """
        if start_date is None or end_date is None:
            start_date, end_date = self.get_week_range()

        qs = ComplianceEvent.objects.filter(
            user=self.user,
            scoring_bucket=scoring_bucket,
            event_date__gte=start_date,
            event_date__lte=end_date,
            expected=True,
            is_primary=True,
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

        denominator = expected - skipped
        numerator = completed + completed_late
        completion_pct = round((numerator / denominator) * 100) if denominator > 0 else 100

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

        Returns all events (primary + suppressed) for full audit trail.
        Suppressed events are clearly marked.
        """
        if start_date is None or end_date is None:
            start_date, end_date = self.get_week_range()

        qs = ComplianceEvent.objects.filter(
            user=self.user,
            scoring_bucket=scoring_bucket,
            event_date__gte=start_date,
            event_date__lte=end_date,
            expected=True,
        ).order_by("-event_date", "-is_primary", "expected_at", "item_label")

        if status_filter:
            qs = qs.filter(final_status=status_filter)

        grouped = {}
        for event in qs:
            date_key = event.event_date
            if date_key not in grouped:
                grouped[date_key] = {"date": date_key, "items": []}
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
                "is_primary": event.is_primary,
                "is_suppressed": event.is_suppressed,
                "suppression_reason": event.suppression_reason,
                "suppression_label": event.suppression_label,
                "obligation_key": event.obligation_key,
            })

        return sorted(grouped.values(), key=lambda x: x["date"], reverse=True)
