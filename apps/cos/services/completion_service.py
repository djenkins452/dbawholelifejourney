"""
CosCompletionService — Routes positive CoS prompt responses to source object completion.

When CoS asks "Did you complete X?" and the user says "Yes", this service:
- Habits: Logs a HabitEntry for the occurrence date
- Goals: Marks the LifeGoal as complete
- Milestones: Marks the GoalMilestone as complete
- Tasks: Already handled by RoutineTaskService (no action needed here)
- Life events / manual: Reflection only (no completion action)

Also handles the reverse: when source objects are completed via UI,
syncs calendar events and schedules CoS reflection prompts.
"""

import logging

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

logger = logging.getLogger(__name__)


class CosCompletionService:
    """Routes CoS prompt responses and UI completions to the right actions."""

    # ── From CoS prompt response ──────────────────────────

    @staticmethod
    def handle_completion_from_prompt(prompt):
        """
        Called when a post-event prompt receives a positive response.
        Routes to the appropriate completion action based on source type.
        """
        source = prompt.source_entity
        if not source:
            return

        from apps.calendar_engine.models import CalendarEvent

        if not isinstance(source, CalendarEvent):
            return

        cal_event = source

        if cal_event.source_type == CalendarEvent.SOURCE_HABIT:
            CosCompletionService._complete_habit(prompt.user, cal_event, prompt)
        elif cal_event.source_type == CalendarEvent.SOURCE_GOAL:
            CosCompletionService._complete_goal(prompt.user, cal_event)
        elif cal_event.source_type == CalendarEvent.SOURCE_GOAL_MILESTONE:
            CosCompletionService._complete_milestone(prompt.user, cal_event)
        # Tasks are handled by RoutineTaskService — no action here
        # Life events / manual — reflection only, no completion

    @staticmethod
    def _complete_habit(user, cal_event, prompt):
        """Create a HabitEntry for the occurrence date."""
        try:
            from apps.purpose.models import HabitGoal, HabitEntry

            habit_id = int(cal_event.source_id)
            habit = HabitGoal.objects.get(pk=habit_id, user=user)

            occ_date = prompt.occurrence_date
            if not occ_date:
                occ_date = prompt.scheduled_for.date()

            HabitEntry.objects.update_or_create(
                goal=habit,
                date=occ_date,
                session_number=1,
                defaults={'completed': True},
            )
            logger.info(
                "CosCompletion: Logged HabitEntry for habit %s on %s (user %s)",
                habit_id, occ_date, user.id,
            )
        except Exception as e:
            logger.warning(
                "CosCompletion: Failed to log habit entry for event %s: %s",
                cal_event.pk, e,
            )

    @staticmethod
    def _complete_goal(user, cal_event):
        """Mark the LifeGoal as complete and sync calendar event."""
        try:
            from apps.purpose.models import LifeGoal

            goal = LifeGoal.objects.get(pk=int(cal_event.source_id), user=user)
            goal.mark_complete()

            cal_event.status = 'completed'
            cal_event.save(update_fields=['status', 'updated_at'])

            logger.info(
                "CosCompletion: Marked goal %s complete (user %s)",
                goal.pk, user.id,
            )
        except Exception as e:
            logger.warning(
                "CosCompletion: Failed to complete goal for event %s: %s",
                cal_event.pk, e,
            )

    @staticmethod
    def _complete_milestone(user, cal_event):
        """Mark the GoalMilestone as complete and sync calendar event."""
        try:
            from apps.purpose.models import GoalMilestone

            milestone = GoalMilestone.objects.get(pk=int(cal_event.source_id))
            if milestone.goal.user != user:
                logger.warning(
                    "CosCompletion: Milestone %s doesn't belong to user %s",
                    milestone.pk, user.id,
                )
                return

            milestone.mark_complete()

            cal_event.status = 'completed'
            cal_event.save(update_fields=['status', 'updated_at'])

            logger.info(
                "CosCompletion: Marked milestone %s complete (user %s)",
                milestone.pk, user.id,
            )
        except Exception as e:
            logger.warning(
                "CosCompletion: Failed to complete milestone for event %s: %s",
                cal_event.pk, e,
            )

    # ── From UI completion (reverse sync) ─────────────────

    @staticmethod
    def on_habit_logged(habit, date, user):
        """
        Called when a HabitEntry is logged via UI.
        Cancels pending pre-prompt and schedules reflection.
        """
        from apps.calendar_engine.models import CalendarEvent
        from apps.cos.models import CosPromptSchedule
        from apps.cos.services.prompt_service import CosPromptService

        cal_event = CalendarEvent.objects.filter(
            user=user,
            source_type=CalendarEvent.SOURCE_HABIT,
            source_id=str(habit.pk),
        ).first()

        if not cal_event:
            return

        if not hasattr(user, 'preferences') or not user.preferences.cos_v2_enabled:
            return

        ct = ContentType.objects.get_for_model(cal_event)

        # Cancel pending pre-prompt for this occurrence
        CosPromptSchedule.objects.filter(
            user=user,
            content_type=ct,
            object_id=cal_event.pk,
            occurrence_date=date,
            timing=CosPromptSchedule.TIMING_PRE,
            status=CosPromptSchedule.STATUS_PENDING,
        ).update(status=CosPromptSchedule.STATUS_CANCELED)

        # Schedule immediate post-completion reflection
        svc = CosPromptService(user)
        svc.schedule_prompts_for_event(
            source_object=cal_event,
            activity_type='habit',
            skip_pre=True,
            post_delay_minutes=2,
            occurrence_date=date,
        )

    @staticmethod
    def on_goal_completed(goal):
        """
        Called when a LifeGoal is completed via UI.
        Syncs CalendarEvent and schedules reflection.
        """
        from apps.calendar_engine.models import CalendarEvent
        from apps.cos.services.prompt_service import CosPromptService

        CalendarEvent.objects.filter(
            user=goal.user,
            source_type=CalendarEvent.SOURCE_GOAL,
            source_id=str(goal.pk),
            status=CalendarEvent.STATUS_SCHEDULED,
        ).update(status=CalendarEvent.STATUS_COMPLETED)

        if not hasattr(goal.user, 'preferences') or not goal.user.preferences.cos_v2_enabled:
            return

        # Schedule reflection prompt
        cal_event = CalendarEvent.objects.filter(
            user=goal.user,
            source_type=CalendarEvent.SOURCE_GOAL,
            source_id=str(goal.pk),
        ).first()

        if cal_event:
            svc = CosPromptService(goal.user)
            svc.schedule_prompts_for_event(
                source_object=cal_event,
                activity_type='goal_deadline',
                skip_pre=True,
                post_delay_minutes=2,
            )

    @staticmethod
    def on_milestone_completed(milestone):
        """
        Called when a GoalMilestone is completed via UI.
        Syncs CalendarEvent and schedules reflection.
        """
        from apps.calendar_engine.models import CalendarEvent
        from apps.cos.services.prompt_service import CosPromptService

        user = milestone.goal.user

        CalendarEvent.objects.filter(
            user=user,
            source_type=CalendarEvent.SOURCE_GOAL_MILESTONE,
            source_id=str(milestone.pk),
            status=CalendarEvent.STATUS_SCHEDULED,
        ).update(status=CalendarEvent.STATUS_COMPLETED)

        if not hasattr(user, 'preferences') or not user.preferences.cos_v2_enabled:
            return

        cal_event = CalendarEvent.objects.filter(
            user=user,
            source_type=CalendarEvent.SOURCE_GOAL_MILESTONE,
            source_id=str(milestone.pk),
        ).first()

        if cal_event:
            svc = CosPromptService(user)
            svc.schedule_prompts_for_event(
                source_object=cal_event,
                activity_type='milestone_deadline',
                skip_pre=True,
                post_delay_minutes=2,
            )
