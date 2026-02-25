# ==============================================================================
# File: apps/life/services/routine_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Coordinates routine task side effects — calendar projection,
#              CoS prompt scheduling, completion sync, and reflection triggers.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-24
# ==============================================================================
"""
RoutineTaskService — Central coordinator for routine task lifecycle.

Handles:
1. Calendar projection (time-specific execution blocks, not deadline markers)
2. CoS prompt scheduling (pre/post activity check-ins)
3. Task completion → CalendarEvent status sync
4. Post-completion reflection triggering

Called from:
- Task.mark_complete() — on_task_completed()
- post_save signal on Task — on_new_routine_task_created()
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


class RoutineTaskService:
    """Static service for routine task side effects."""

    @staticmethod
    def on_new_routine_task_created(task):
        """
        Called when a routine task is created (new or from recurrence).
        Projects to calendar and schedules CoS prompts.

        Args:
            task: Task instance with is_routine=True
        """
        if not task.is_routine or not task.scheduled_time or not task.due_date:
            return

        cal_event = RoutineTaskService.project_routine_to_calendar(task)
        if cal_event:
            RoutineTaskService.schedule_cos_prompts(task, cal_event)

    @staticmethod
    def on_task_completed(task):
        """
        Called after task.mark_complete(). Handles:
        1. Sync any associated CalendarEvent status to COMPLETED
        2. For routine tasks, trigger post-completion CoS reflection prompt

        Args:
            task: The just-completed Task instance
        """
        try:
            from apps.calendar_engine.models import CalendarEvent

            # Sync associated CalendarEvent(s) to completed
            updated = CalendarEvent.objects.filter(
                user=task.user,
                source_type=CalendarEvent.SOURCE_TASK,
                source_id=str(task.pk),
                status=CalendarEvent.STATUS_SCHEDULED,
            ).update(status=CalendarEvent.STATUS_COMPLETED)

            if updated:
                logger.debug(
                    "Synced %d CalendarEvent(s) to COMPLETED for task %s",
                    updated, task.pk,
                )
        except Exception as e:
            logger.warning("Failed to sync CalendarEvent for task %s: %s", task.pk, e)

        # For routine tasks, trigger post-completion reflection
        if task.is_routine:
            RoutineTaskService._trigger_post_completion_reflection(task)

    @staticmethod
    def project_routine_to_calendar(task):
        """
        Create/update a time-specific CalendarEvent for a routine task.

        Returns:
            CalendarEvent instance, or None on failure
        """
        try:
            from apps.calendar_engine.services.projection import (
                upsert_from_routine_task,
            )
            return upsert_from_routine_task(task)
        except Exception as e:
            logger.warning(
                "Failed to project routine task %s to calendar: %s",
                task.pk, e,
            )
            return None

    @staticmethod
    def schedule_cos_prompts(task, calendar_event):
        """
        Schedule pre- and post-activity CoS prompts for a routine task.
        Uses the existing CosPromptService.

        Args:
            task: Task instance
            calendar_event: The CalendarEvent linked to this task
        """
        try:
            if not hasattr(task.user, 'preferences'):
                return
            if not task.user.preferences.cos_v2_enabled:
                return

            from apps.cos.services.prompt_service import CosPromptService

            svc = CosPromptService(task.user)
            prompts = svc.schedule_prompts_for_event(
                source_object=calendar_event,
                activity_type=None,  # auto-detect from title
            )
            if prompts:
                logger.debug(
                    "Scheduled %d CoS prompt(s) for routine task '%s'",
                    len(prompts), task.title,
                )
        except Exception as e:
            logger.warning(
                "Failed to schedule CoS prompts for task %s: %s",
                task.pk, e,
            )

    @staticmethod
    def _trigger_post_completion_reflection(task):
        """
        Schedule a CoS post-activity prompt to ask 'How did it go?'
        Fires immediately (2-min delay) after task completion.
        """
        try:
            if not hasattr(task.user, 'preferences'):
                return
            if not task.user.preferences.cos_v2_enabled:
                return

            from apps.calendar_engine.models import CalendarEvent
            from apps.cos.services.prompt_service import CosPromptService

            # Find the CalendarEvent linked to this task
            cal_event = CalendarEvent.objects.filter(
                user=task.user,
                source_type=CalendarEvent.SOURCE_TASK,
                source_id=str(task.pk),
            ).order_by('-start_dt').first()

            if not cal_event:
                return

            svc = CosPromptService(task.user)
            prompts = svc.schedule_prompts_for_event(
                source_object=cal_event,
                skip_pre=True,
                skip_post=False,
                post_delay_minutes=2,  # Ask shortly after completion
            )
            if prompts:
                logger.debug(
                    "Scheduled post-completion reflection for routine '%s'",
                    task.title,
                )
        except Exception as e:
            logger.warning(
                "Failed to trigger reflection for task %s: %s",
                task.pk, e,
            )
