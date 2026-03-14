# ==============================================================================
# File: apps/dashboard/services/daily_schedule_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Unified daily schedule aggregation
# Created: 2026-03-14 (Architecture Evolution Phase 2)
# ==============================================================================
"""
DailyScheduleService — Unified Daily Schedule

Aggregates all planned commitments for a given date from CalendarEngine.
Returns a chronological list of everything the user committed to do today.

Part of the WLJ Architecture Evolution — Layer 1 (Commitments).
"""

import logging

from django.utils import timezone as tz_utils

from apps.calendar_engine.models import CalendarEvent

logger = logging.getLogger(__name__)


class DailyScheduleService:
    """
    Aggregates all commitments for a user on a given date.

    Queries CalendarEngine for:
    - Direct CalendarEvent records (tasks, goals, medicine, faith, workouts, life events)
    - RecurrenceRule-generated occurrences for habits and recurring events

    Returns a chronological list of normalized commitment dicts.
    """

    @staticmethod
    def get_daily_schedule(user, date):
        """
        Returns chronological list of all commitments for a date.

        Each item is a dict with:
            time: datetime — scheduled start time
            end_time: datetime | None — scheduled end time
            title: str — display title
            domain: str — LifeDomain slug (e.g., 'health', 'faith')
            source_type: str — CalendarEvent source_type
            source_id: str — PK of source object
            commitment_level: str — optional/important/non_negotiable
            status: str — scheduled/completed/canceled
            event_kind: str — manual/deadline_marker/execution_block
            is_recurring_occurrence: bool — True if generated from RecurrenceRule
        """
        from zoneinfo import ZoneInfo

        user_tz = ZoneInfo(user.preferences.timezone_iana)

        # Build date range in user's timezone
        import datetime as dt
        day_start = tz_utils.make_aware(
            dt.datetime.combine(date, dt.time.min), user_tz,
        )
        day_end = tz_utils.make_aware(
            dt.datetime.combine(date, dt.time(23, 59, 59)), user_tz,
        )

        schedule = []

        # 1. Direct (non-recurring) events for this date
        direct_events = CalendarEvent.objects.filter(
            user=user,
            start_dt__lte=day_end,
            end_dt__gte=day_start,
            deleted_at__isnull=True,
        ).exclude(
            status=CalendarEvent.STATUS_CANCELED,
        ).select_related('domain')

        # Track which events have recurrence rules (handle separately)
        recurring_event_ids = set()

        for event in direct_events:
            has_recurrence = hasattr(event, 'recurrence') and event.recurrence is not None
            try:
                has_recurrence = event.recurrence is not None
            except CalendarEvent.recurrence.RelatedObjectDoesNotExist:
                has_recurrence = False

            if has_recurrence:
                recurring_event_ids.add(event.pk)
                continue  # Will handle via recurrence expansion below

            schedule.append(
                DailyScheduleService._event_to_dict(event, is_recurring=False)
            )

        # 2. Recurring events — expand occurrences for this date
        recurring_events = CalendarEvent.objects.filter(
            user=user,
            recurrence__isnull=False,
            deleted_at__isnull=True,
        ).exclude(
            status=CalendarEvent.STATUS_CANCELED,
        ).select_related('domain', 'recurrence')

        for event in recurring_events:
            try:
                occurrences = event.recurrence.get_occurrences(day_start, day_end)
            except Exception as e:
                logger.warning(
                    "Failed to expand recurrence for event %s: %s", event.pk, e
                )
                continue

            for occ_start, occ_end in occurrences:
                item = DailyScheduleService._event_to_dict(
                    event, is_recurring=True,
                )
                item['time'] = occ_start
                item['end_time'] = occ_end
                schedule.append(item)

        # Sort: all-day events first, then by time
        schedule.sort(key=lambda x: (
            0 if x.get('is_all_day') else 1,
            x['time'],
        ))

        return schedule

    @staticmethod
    def _event_to_dict(event, is_recurring=False):
        """Convert a CalendarEvent to a normalized dict."""
        domain_slug = ''
        if event.domain:
            domain_slug = event.domain.slug

        return {
            'time': event.start_dt,
            'end_time': event.end_dt,
            'title': event.title,
            'domain': domain_slug,
            'source_type': event.source_type,
            'source_id': event.source_id,
            'commitment_level': event.commitment_level,
            'status': event.status,
            'event_kind': event.event_kind,
            'is_all_day': event.is_all_day,
            'is_recurring_occurrence': is_recurring,
            'event_id': event.pk,
        }

    @staticmethod
    def get_commitment_summary(user, date):
        """
        Returns a summary of today's commitments by domain.

        Useful for CoS context assembly and dashboard tiles.
        """
        schedule = DailyScheduleService.get_daily_schedule(user, date)

        total = len(schedule)
        completed = sum(1 for s in schedule if s['status'] == 'completed')
        by_domain = {}
        by_commitment_level = {
            'non_negotiable': {'total': 0, 'completed': 0},
            'important': {'total': 0, 'completed': 0},
            'optional': {'total': 0, 'completed': 0},
        }

        for item in schedule:
            domain = item['domain'] or 'uncategorized'
            if domain not in by_domain:
                by_domain[domain] = {'total': 0, 'completed': 0}
            by_domain[domain]['total'] += 1
            if item['status'] == 'completed':
                by_domain[domain]['completed'] += 1

            level = item['commitment_level']
            if level in by_commitment_level:
                by_commitment_level[level]['total'] += 1
                if item['status'] == 'completed':
                    by_commitment_level[level]['completed'] += 1

        return {
            'total': total,
            'completed': completed,
            'completion_rate': completed / total if total > 0 else 0.0,
            'by_domain': by_domain,
            'by_commitment_level': by_commitment_level,
        }
