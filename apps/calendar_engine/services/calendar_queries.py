# ==============================================================================
# File: apps/calendar_engine/services/calendar_queries.py
# Description: Canonical calendar query authority (Layer 1).
# ==============================================================================
"""
Canonical calendar queries. All consumers (SAE state builder, CoS context,
CalendarDomainTruth) should read events through these methods — never ad-hoc
CalendarEvent QuerySets. Materialized rows only (no recurrence expansion).
"""
from datetime import datetime, time, timedelta

from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent


class CalendarQueries:
    """Deterministic calendar queries. No instance state — all classmethods.
    Return QuerySets of non-deleted CalendarEvents."""

    ACTIVE_STATUSES = ("scheduled", "completed")

    @classmethod
    def _base(cls, user):
        return CalendarEvent.objects.filter(user=user, deleted_at__isnull=True)

    @classmethod
    def _day_bounds(cls, user, d):
        """Aware [start, end] datetimes spanning local calendar day `d`."""
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(d, time.min), tz)
        end = timezone.make_aware(datetime.combine(d, time.max), tz)
        return start, end

    @classmethod
    def events_on_date(cls, user, d):
        """Events overlapping local calendar day `d` (scheduled or completed)."""
        start, end = cls._day_bounds(user, d)
        return (cls._base(user)
                .filter(start_dt__lte=end, end_dt__gte=start,
                        status__in=cls.ACTIVE_STATUSES)
                .select_related("domain").order_by("start_dt"))

    @classmethod
    def events_in_range(cls, user, start_date, end_date):
        """Events overlapping the inclusive local-date range [start_date, end_date]."""
        start, _ = cls._day_bounds(user, start_date)
        _, end = cls._day_bounds(user, end_date)
        return (cls._base(user)
                .filter(start_dt__lte=end, end_dt__gte=start,
                        status__in=cls.ACTIVE_STATUSES)
                .select_related("domain").order_by("start_dt"))

    @classmethod
    def upcoming(cls, user, now=None, horizon_days=7):
        """Scheduled events starting strictly after `now`, within horizon_days."""
        now = now or timezone.now()
        return (cls._base(user)
                .filter(start_dt__gt=now,
                        start_dt__lte=now + timedelta(days=horizon_days),
                        status="scheduled")
                .select_related("domain").order_by("start_dt"))

    @classmethod
    def past(cls, user, now=None, lookback_days=7):
        """Events that ended before `now` within lookback_days
        (answers 'appointments recently completed?')."""
        now = now or timezone.now()
        return (cls._base(user)
                .filter(end_dt__lte=now,
                        end_dt__gte=now - timedelta(days=lookback_days),
                        status__in=cls.ACTIVE_STATUSES)
                .select_related("domain").order_by("-start_dt"))
