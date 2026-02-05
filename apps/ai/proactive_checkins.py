# ==============================================================================
# File: apps/ai/proactive_checkins.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Generate proactive check-in messages for the assistant
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-05
# ==============================================================================
"""
Proactive Check-ins

Generates personalized check-in messages that appear in the assistant chat.
These are system-initiated messages that help keep users on track with:
- Medicine doses
- Workouts
- Journaling
- Tasks
- Mood check-ins (based on journal sentiment)

The check-ins include quick reply buttons for easy response.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from django.utils import timezone

from .models import AssistantConversation, AssistantMessage
from .quick_reply_handlers import (
    generate_medicine_check_in_replies,
    generate_workout_check_in_replies,
    generate_journal_check_in_replies,
    generate_mood_check_in_replies,
    generate_task_check_in_replies,
)

logger = logging.getLogger(__name__)


class ProactiveCheckInService:
    """
    Service for generating proactive check-in messages.

    These messages appear in the assistant chat and include quick reply
    buttons so users can respond with a single tap.
    """

    def __init__(self, user):
        self.user = user

    def generate_medicine_check_in(self, medicine, dose_time: str) -> Optional[AssistantMessage]:
        """
        Generate a check-in message for a medicine dose.

        Args:
            medicine: Medicine model instance
            dose_time: The scheduled time for this dose (e.g., "09:00")

        Returns:
            AssistantMessage with quick reply buttons, or None
        """
        # Format time for display
        try:
            from datetime import datetime
            time_obj = datetime.strptime(dose_time, '%H:%M')
            time_display = time_obj.strftime('%I:%M %p').lstrip('0')
        except (ValueError, TypeError):
            time_display = dose_time

        message_content = f"Hey! It's time for your {medicine.name}. Did you take your {time_display} dose?"

        quick_replies = generate_medicine_check_in_replies(
            medicine_id=medicine.id,
            medicine_name=medicine.name,
            dose_time=dose_time
        )

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'medicine',
                'medicine_id': medicine.id,
                'dose_time': dose_time,
            }
        )

    def generate_workout_check_in(self) -> Optional[AssistantMessage]:
        """
        Generate a check-in message about today's workout.

        Returns:
            AssistantMessage with quick reply buttons, or None
        """
        from apps.health.models import WorkoutSession
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)

        # Check if already worked out today
        if WorkoutSession.objects.filter(user=self.user, date=today).exists():
            return None  # Already logged

        message_content = "Have you had a chance to work out today?"

        quick_replies = generate_workout_check_in_replies()

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'workout',
            }
        )

    def generate_journal_check_in(self) -> Optional[AssistantMessage]:
        """
        Generate a check-in message about journaling today.

        Returns:
            AssistantMessage with quick reply buttons, or None
        """
        from apps.journal.models import JournalEntry
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)

        # Check if already journaled today
        if JournalEntry.objects.filter(user=self.user, entry_date=today).exists():
            return None  # Already journaled

        message_content = "How about taking a few minutes to journal today? It can help process your thoughts and track your progress."

        quick_replies = generate_journal_check_in_replies()

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='reflection_prompt',
            metadata={
                'check_in_type': 'journal',
            }
        )

    def generate_mood_check_in(self, yesterday_mood: str = None) -> Optional[AssistantMessage]:
        """
        Generate a mood check-in, especially after a difficult day.

        Args:
            yesterday_mood: The dominant mood from yesterday's journal (optional)

        Returns:
            AssistantMessage with quick reply buttons, or None
        """
        if yesterday_mood and yesterday_mood in ['sad', 'stressed', 'anxious', 'frustrated', 'overwhelmed']:
            message_content = f"I noticed yesterday was a bit tough. How are you feeling today?"
        else:
            message_content = "How's your day going so far?"

        quick_replies = generate_mood_check_in_replies()

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='state_assessment',
            metadata={
                'check_in_type': 'mood',
                'previous_mood': yesterday_mood,
            }
        )

    def generate_task_check_in(self, task) -> Optional[AssistantMessage]:
        """
        Generate a check-in for a specific task.

        Args:
            task: Task model instance

        Returns:
            AssistantMessage with quick reply buttons, or None
        """
        if task.is_complete:
            return None

        message_content = f"How's progress on '{task.title}'?"

        quick_replies = generate_task_check_in_replies(
            task_id=task.id,
            task_title=task.title
        )

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'task',
                'task_id': task.id,
            }
        )

    def generate_birthday_greeting(self, event) -> Optional[AssistantMessage]:
        """
        Generate a birthday or memorial greeting message.

        Args:
            event: SignificantEvent model instance

        Returns:
            AssistantMessage (no quick replies - just informational)
        """
        from apps.life.models import SignificantEvent

        person_name = event.person_name or event.title
        years_display = event.get_years_display() if hasattr(event, 'get_years_display') else None

        if event.event_type == 'birthday':
            if years_display:
                content = f"Today is {person_name}'s birthday! They're turning {years_display}. Don't forget to wish them well!"
            else:
                content = f"Today is {person_name}'s birthday! Don't forget to wish them well!"
            icon = "🎂"

        elif event.event_type == 'memorial':
            if years_display:
                content = f"Today we remember {person_name}. They would have been {years_display}. Take a moment to honor their memory."
            else:
                content = f"Today we remember {person_name}. Take a moment to honor their memory."
            icon = "🌈"

        elif event.event_type == 'anniversary':
            if years_display:
                content = f"Happy {years_display} Anniversary! I hope it's a wonderful celebration."
            else:
                content = f"Happy Anniversary! I hope it's a wonderful celebration."
            icon = "💕"

        else:
            content = f"Today marks: {event.title}"
            icon = "📅"

        return self._create_proactive_message(
            content=f"{icon} {content}",
            quick_replies=[],  # No quick replies for greetings
            message_type='celebration',
            metadata={
                'check_in_type': 'birthday',
                'event_id': event.id,
                'event_type': event.event_type,
            }
        )

    def _create_proactive_message(
        self,
        content: str,
        quick_replies: list,
        message_type: str = 'nudge',
        metadata: dict = None
    ) -> AssistantMessage:
        """
        Create a proactive assistant message with quick replies.

        Args:
            content: The message content
            quick_replies: List of quick reply button definitions
            message_type: The type of message (nudge, celebration, etc.)
            metadata: Additional metadata

        Returns:
            AssistantMessage instance (saved to database)
        """
        conversation = AssistantConversation.get_or_create_active(self.user)

        message = AssistantMessage.objects.create(
            conversation=conversation,
            role='assistant',
            content=content,
            message_type=message_type,
            metadata=metadata or {},
            quick_replies=quick_replies,
            is_proactive=True,
        )

        logger.debug(f"Created proactive check-in for user {self.user.id}: {message_type}")

        return message


def get_proactive_service(user):
    """Get the proactive check-in service for a user."""
    return ProactiveCheckInService(user)


# =============================================================================
# SCHEDULED JOB FUNCTIONS
# =============================================================================

def generate_medicine_check_ins_for_user(user, dose_time: str = None):
    """
    Generate medicine check-in messages for a user.

    Called by the scheduled job to create check-ins for pending doses.

    Args:
        user: User to generate check-ins for
        dose_time: Optional specific dose time (e.g., "09:00")
    """
    from apps.health.models import Medicine, MedicineSchedule, MedicineLog
    from apps.core.utils import get_user_today

    # Check user preferences
    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return
    if not getattr(prefs, 'assistant_medicine_checkins', True):
        return

    service = get_proactive_service(user)
    today = get_user_today(user)

    # Get active medicines
    medicines = Medicine.objects.filter(user=user, is_active=True)

    for medicine in medicines:
        # Get schedules for today
        schedules = MedicineSchedule.objects.filter(medicine=medicine, is_active=True)

        for schedule in schedules:
            if not schedule.applies_to_day(today):
                continue

            # Check if this dose was already taken
            existing_log = MedicineLog.objects.filter(
                medicine=medicine,
                date=today,
                time=schedule.time,
            ).first()

            if existing_log and existing_log.status == 'taken':
                continue  # Already taken

            # Check if we already sent a check-in for this dose today
            recent_checkin = AssistantMessage.objects.filter(
                conversation__user=user,
                is_proactive=True,
                metadata__check_in_type='medicine',
                metadata__medicine_id=medicine.id,
                metadata__dose_time=schedule.time.strftime('%H:%M'),
                created_at__date=today,
            ).exists()

            if recent_checkin:
                continue  # Already sent check-in

            # Generate check-in
            service.generate_medicine_check_in(
                medicine=medicine,
                dose_time=schedule.time.strftime('%H:%M')
            )


def generate_daily_check_ins_for_user(user, check_type: str):
    """
    Generate daily check-in messages for a user.

    Args:
        user: User to generate check-ins for
        check_type: Type of check-in ('workout', 'journal', 'mood')
    """
    from apps.core.utils import get_user_today

    # Check user preferences
    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    # Check specific check-in type preference
    pref_map = {
        'workout': 'assistant_workout_checkins',
        'journal': 'assistant_journal_checkins',
        'mood': 'assistant_mood_checkins',
    }
    pref_name = pref_map.get(check_type)
    if pref_name and not getattr(prefs, pref_name, True):
        return

    service = get_proactive_service(user)
    today = get_user_today(user)

    # Check if we already sent this type of check-in today
    recent_checkin = AssistantMessage.objects.filter(
        conversation__user=user,
        is_proactive=True,
        metadata__check_in_type=check_type,
        created_at__date=today,
    ).exists()

    if recent_checkin:
        return  # Already sent

    if check_type == 'workout':
        service.generate_workout_check_in()
    elif check_type == 'journal':
        service.generate_journal_check_in()
    elif check_type == 'mood':
        # Get yesterday's dominant mood for context
        yesterday = today - timedelta(days=1)
        yesterday_mood = _get_yesterday_mood(user, yesterday)
        service.generate_mood_check_in(yesterday_mood)


def _get_yesterday_mood(user, yesterday):
    """Get the dominant mood from yesterday's journal entries."""
    from apps.journal.models import JournalEntry

    entries = JournalEntry.objects.filter(
        user=user,
        entry_date=yesterday
    ).values_list('mood', flat=True)

    if not entries:
        return None

    # Return the most common mood
    from collections import Counter
    mood_counts = Counter(m for m in entries if m)
    if mood_counts:
        return mood_counts.most_common(1)[0][0]
    return None


def generate_birthday_check_ins_for_user(user):
    """
    Generate birthday/memorial greeting messages for a user.

    Args:
        user: User to generate greetings for
    """
    from apps.life.models import SignificantEvent
    from apps.core.utils import get_user_today

    service = get_proactive_service(user)
    today = get_user_today(user)

    # Find events for today
    events = SignificantEvent.objects.filter(
        user=user,
        event_date__month=today.month,
        event_date__day=today.day,
    )

    for event in events:
        # Check if we already sent a greeting for this event today
        recent_greeting = AssistantMessage.objects.filter(
            conversation__user=user,
            is_proactive=True,
            metadata__check_in_type='birthday',
            metadata__event_id=event.id,
            created_at__date=today,
        ).exists()

        if recent_greeting:
            continue

        service.generate_birthday_greeting(event)
