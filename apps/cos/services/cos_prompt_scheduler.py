"""
CosPromptScheduler — Periodic prompt generation for all calendar event types.

Generates CoS pre/post prompts for:
- Habit occurrences (daily/weekly/monthly recurring events)
- Goal deadlines approaching within 48 hours
- Milestone deadlines approaching within 48 hours
- Life events within the next 24 hours
- Manual calendar events within the next 24 hours

Called by ISE every 6 hours.
"""

import datetime as dt
import logging

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent
from apps.cos.models import CosPromptSchedule
from apps.cos.services.prompt_service import CosPromptService

logger = logging.getLogger(__name__)


class CosPromptScheduler:
    """Periodic scheduler for CoS prompts across all calendar event types."""

    @staticmethod
    def schedule_upcoming_prompts_for_all_users():
        """
        Entry point called by ISE scheduler.

        Finds all users with cos_v2_enabled and schedules prompts
        for their upcoming calendar events.
        """
        from apps.users.models import User

        users = User.objects.filter(
            is_active=True,
            preferences__cos_v2_enabled=True,
        ).select_related("preferences")

        scheduled = 0
        errors = 0

        for user in users:
            try:
                count = CosPromptScheduler._schedule_for_user(user)
                scheduled += count
            except Exception as e:
                errors += 1
                logger.error(
                    "CosPromptScheduler: Failed for user %s: %s", user.id, e
                )

        logger.info(
            "CosPromptScheduler: scheduled=%d, errors=%d", scheduled, errors
        )
        return {"scheduled": scheduled, "errors": errors}

    @staticmethod
    def _schedule_for_user(user):
        """Schedule all prompt types for a single user. Returns count of prompts created."""
        total = 0
        total += CosPromptScheduler._schedule_habit_prompts(user)
        total += CosPromptScheduler._schedule_goal_deadline_prompts(user)
        total += CosPromptScheduler._schedule_milestone_deadline_prompts(user)
        total += CosPromptScheduler._schedule_timed_event_prompts(user)
        return total

    @staticmethod
    def _schedule_habit_prompts(user):
        """Schedule prompts for habit occurrences in the next 24 hours."""
        now = timezone.now()
        window_end = now + dt.timedelta(hours=24)

        habit_events = CalendarEvent.objects.filter(
            user=user,
            source_type=CalendarEvent.SOURCE_HABIT,
            status=CalendarEvent.STATUS_SCHEDULED,
            recurrence__isnull=False,
        ).select_related('recurrence')

        svc = CosPromptService(user)
        count = 0

        for event in habit_events:
            occurrences = event.recurrence.get_occurrences(now, window_end)
            for occ_start, occ_end in occurrences:
                created = svc.schedule_prompts_for_event(
                    source_object=event,
                    activity_type='habit',
                    occurrence_date=occ_start.date(),
                    override_start_dt=occ_start,
                    override_end_dt=occ_end,
                )
                count += len(created)

        return count

    @staticmethod
    def _schedule_goal_deadline_prompts(user):
        """Schedule prompts for goals with deadlines within 48 hours."""
        now = timezone.now()
        window_end = now + dt.timedelta(hours=48)

        goal_events = CalendarEvent.objects.filter(
            user=user,
            source_type=CalendarEvent.SOURCE_GOAL,
            status=CalendarEvent.STATUS_SCHEDULED,
            start_dt__gte=now,
            start_dt__lte=window_end,
        )

        svc = CosPromptService(user)
        count = 0

        for event in goal_events:
            created = svc.schedule_prompts_for_event(
                source_object=event,
                activity_type='goal_deadline',
            )
            count += len(created)

        return count

    @staticmethod
    def _schedule_milestone_deadline_prompts(user):
        """Schedule prompts for milestones with deadlines within 48 hours."""
        now = timezone.now()
        window_end = now + dt.timedelta(hours=48)

        milestone_events = CalendarEvent.objects.filter(
            user=user,
            source_type=CalendarEvent.SOURCE_GOAL_MILESTONE,
            status=CalendarEvent.STATUS_SCHEDULED,
            start_dt__gte=now,
            start_dt__lte=window_end,
        )

        svc = CosPromptService(user)
        count = 0

        for event in milestone_events:
            created = svc.schedule_prompts_for_event(
                source_object=event,
                activity_type='milestone_deadline',
            )
            count += len(created)

        return count

    @staticmethod
    def _schedule_timed_event_prompts(user):
        """
        Schedule prompts for life events and manual events with specific times
        in the next 24 hours.
        """
        now = timezone.now()
        window_end = now + dt.timedelta(hours=24)

        # Life events and manual events with specific times (not all-day)
        timed_events = CalendarEvent.objects.filter(
            user=user,
            source_type__in=[
                CalendarEvent.SOURCE_LIFE_EVENT,
                CalendarEvent.SOURCE_NONE,
            ],
            status=CalendarEvent.STATUS_SCHEDULED,
            is_all_day=False,
            start_dt__gte=now,
            start_dt__lte=window_end,
            recurrence__isnull=True,  # non-recurring only
        )

        svc = CosPromptService(user)
        count = 0

        for event in timed_events:
            activity_type = 'life_event' if event.source_type == CalendarEvent.SOURCE_LIFE_EVENT else None
            created = svc.schedule_prompts_for_event(
                source_object=event,
                activity_type=activity_type,
            )
            count += len(created)

        return count
