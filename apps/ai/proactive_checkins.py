# ==============================================================================
# File: apps/ai/proactive_checkins.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Generate proactive check-in messages for the assistant
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-05
# Updated: 2026-02-05 - Enhanced with master prompt principles
# ==============================================================================
"""
Proactive Check-ins

Generates personalized check-in messages that appear in the assistant chat.
The assistant behaves like a highly attentive, human-like right-hand assistant.

Core Philosophy (from Master Prompt):
- Not a cheerleader. Not a therapist. Not a medical advisor.
- Calm, observant, factual, proactive, and efficient.
- Awareness + alignment, not advice.
- Short messages (1-2 sentences max)
- Primary question: "Is this helpful right now?" If not, don't interrupt.

Check-in Types:
1. MISSED/OVERDUE: Medications not marked, tasks overdue, routines skipped
2. PATTERN RECOGNITION: Factual correlations only
3. HEALTH CONTEXT: Remind why something exists using their data
4. PLANNING SUPPORT: Busy days, goal drift
5. QUICK RECOGNITION: Brief acknowledgment (no cheerleading)
"""

import logging
from datetime import date, timedelta
from typing import Optional, List

from django.utils import timezone

from .models import AssistantConversation, AssistantMessage
from .quick_reply_handlers import (
    generate_medicine_check_in_replies,
    generate_workout_check_in_replies,
    generate_journal_check_in_replies,
    generate_mood_check_in_replies,
    generate_task_check_in_replies,
)
from .assistant_intelligence import (
    get_style_template,
    InteractionThrottler,
    IntelligentCheckInService,
    get_intelligent_service,
)

logger = logging.getLogger(__name__)


class ProactiveCheckInService:
    """
    Service for generating proactive check-in messages.

    Messages are concise (1-2 sentences), factual, and helpful.
    The tone adapts to the user's coaching style preference.
    """

    def __init__(self, user):
        self.user = user
        self.throttler = InteractionThrottler(user)
        self.intelligence = IntelligentCheckInService(user)

    def generate_medicine_check_in(
        self,
        medicine,
        dose_time: str,
        context: str = None
    ) -> Optional[AssistantMessage]:
        """
        Generate a check-in message for a missed medicine dose.

        Message format: Direct question about the missed dose.
        If health context available, include factual reminder.

        Args:
            medicine: Medicine model instance
            dose_time: The scheduled time for this dose (e.g., "09:00")
            context: Optional health context (e.g., "elevated cholesterol")

        Returns:
            AssistantMessage with quick reply buttons, or None if throttled
        """
        # Check throttle
        item_key = f"{medicine.id}_{dose_time.replace(':', '')}"
        if not self.throttler.can_send('medicine', hash(item_key)):
            return None

        # Format time for display
        try:
            from datetime import datetime
            time_obj = datetime.strptime(dose_time, '%H:%M')
            time_display = time_obj.strftime('%I:%M %p').lstrip('0')
        except (ValueError, TypeError):
            time_display = dose_time

        # Build message using coaching style template
        if context:
            template = get_style_template(self.user, 'missed_med_with_context')
            message_content = template.format(
                time=time_display,
                medicine=medicine.name,
                context=context
            )
        else:
            template = get_style_template(self.user, 'missed_med')
            message_content = template.format(
                time=time_display,
                medicine=medicine.name
            )

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
                'item_id': hash(item_key),
            }
        )

    def generate_workout_check_in(self) -> Optional[AssistantMessage]:
        """
        Generate a brief check-in about today's workout.

        Message: Direct, short question. No motivational speech.

        Returns:
            AssistantMessage with quick reply buttons, or None
        """
        from apps.health.models import WorkoutSession
        from apps.core.utils import get_user_today

        if not self.throttler.can_send('workout'):
            return None

        today = get_user_today(self.user)

        # Already worked out today? Don't ask.
        if WorkoutSession.objects.filter(user=self.user, date=today).exists():
            return None

        template = get_style_template(self.user, 'workout_check')
        message_content = template

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
        Generate a brief check-in about journaling today.

        Message: Short question, no pressure.

        Returns:
            AssistantMessage with quick reply buttons, or None
        """
        from apps.journal.models import JournalEntry
        from apps.core.utils import get_user_today

        if not self.throttler.can_send('journal'):
            return None

        today = get_user_today(self.user)

        # Already journaled? Don't ask.
        if JournalEntry.objects.filter(user=self.user, entry_date=today).exists():
            return None

        template = get_style_template(self.user, 'journal_check')
        message_content = template

        quick_replies = generate_journal_check_in_replies()

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'journal',
            }
        )

    def generate_overdue_task_check_in(self, task) -> Optional[AssistantMessage]:
        """
        Generate a check-in for an overdue task.

        Message: Note that it's overdue, offer to reschedule.

        Args:
            task: Task model instance

        Returns:
            AssistantMessage with quick reply buttons, or None
        """
        if task.is_complete:
            return None

        if not self.throttler.can_send('task_overdue', task.id):
            return None

        template = get_style_template(self.user, 'overdue_task')
        message_content = template.format(task=task.title)

        quick_replies = generate_task_check_in_replies(
            task_id=task.id,
            task_title=task.title
        )

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'task_overdue',
                'task_id': task.id,
                'item_id': task.id,
            }
        )

    def generate_busy_day_check_in(self, item_count: int) -> Optional[AssistantMessage]:
        """
        Generate a check-in about a busy upcoming day.

        Message: Note the load, offer to help prioritize.

        Args:
            item_count: Number of items scheduled

        Returns:
            AssistantMessage, or None
        """
        if not self.throttler.can_send('busy_day'):
            return None

        template = get_style_template(self.user, 'busy_day')
        message_content = template.format(count=item_count)

        # No quick replies - this is informational, user can respond naturally
        return self._create_proactive_message(
            content=message_content,
            quick_replies=[],
            message_type='nudge',
            metadata={
                'check_in_type': 'busy_day',
                'item_count': item_count,
            }
        )

    def generate_pattern_observation(
        self,
        pattern_type: str,
        observation: str
    ) -> Optional[AssistantMessage]:
        """
        Generate a factual pattern observation.

        IMPORTANT: This is an OBSERVATION, not advice.
        Example: "Higher glucose on pizza days" not "You should eat less pizza"

        Args:
            pattern_type: Type of pattern (food_glucose, workout_mood, etc.)
            observation: The factual observation

        Returns:
            AssistantMessage, or None
        """
        if not self.throttler.can_send('pattern'):
            return None

        template = get_style_template(self.user, 'correlation')
        message_content = template.format(observation=observation)

        return self._create_proactive_message(
            content=message_content,
            quick_replies=[],  # Observations don't need quick replies
            message_type='insight',
            metadata={
                'check_in_type': 'pattern',
                'pattern_type': pattern_type,
            }
        )

    def generate_streak_acknowledgment(
        self,
        count: int,
        activity: str
    ) -> Optional[AssistantMessage]:
        """
        Generate brief streak acknowledgment.

        Message: Just noting the fact. NO cheerleading.
        Example: "3 days in a row. Noted." NOT "Great job! Keep it up!"

        Args:
            count: Number of days in streak
            activity: What the streak is for

        Returns:
            AssistantMessage, or None
        """
        template = get_style_template(self.user, 'streak_note')
        message_content = template.format(count=count)

        return self._create_proactive_message(
            content=message_content,
            quick_replies=[],
            message_type='insight',
            metadata={
                'check_in_type': 'streak',
                'activity': activity,
                'count': count,
            }
        )

    def generate_completion_note(self, item_type: str, item_name: str) -> str:
        """
        Generate brief completion acknowledgment (NOT a full message).

        Returns just the text for inline acknowledgment.
        Example: "Medications complete." NOT "Amazing job taking your meds!"

        Args:
            item_type: Type of item completed
            item_name: Name of item

        Returns:
            Short acknowledgment string
        """
        template = get_style_template(self.user, 'completion')
        return template.format(item=item_name)

    def generate_birthday_greeting(self, event) -> Optional[AssistantMessage]:
        """
        Generate a birthday or memorial greeting message.

        Kept brief and factual. For memorials, respectful.

        Args:
            event: SignificantEvent model instance

        Returns:
            AssistantMessage, or None
        """
        person_name = event.person_name or event.title
        years_display = event.get_years_display() if hasattr(event, 'get_years_display') else None

        if event.event_type == 'birthday':
            if years_display:
                content = f"{person_name}'s birthday today. Turning {years_display}."
            else:
                content = f"{person_name}'s birthday today."

        elif event.event_type == 'memorial':
            if years_display:
                content = f"Remembering {person_name} today. Would have been {years_display}."
            else:
                content = f"Remembering {person_name} today."

        elif event.event_type == 'anniversary':
            if years_display:
                content = f"Anniversary today. {years_display} years."
            else:
                content = f"Anniversary today."

        else:
            content = f"Today: {event.title}"

        return self._create_proactive_message(
            content=content,
            quick_replies=[],
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
        Create a proactive assistant message.

        Args:
            content: The message content (keep SHORT)
            quick_replies: List of quick reply button definitions
            message_type: The type of message
            metadata: Additional metadata for tracking

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

    Only sends if:
    - User has proactive checkins enabled
    - Dose time has passed and not logged
    - Not throttled (no spam)

    Args:
        user: User to generate check-ins for
        dose_time: Optional specific dose time
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
    now = timezone.now()
    current_time = now.time()

    # Get active medicines
    medicines = Medicine.objects.filter(user=user, is_active=True)

    for medicine in medicines:
        schedules = MedicineSchedule.objects.filter(medicine=medicine, is_active=True)

        for schedule in schedules:
            if not schedule.applies_to_day(today):
                continue

            scheduled_time = schedule.time

            # Only check doses whose time has passed
            if current_time < scheduled_time:
                continue

            # Check if already logged
            log = MedicineLog.objects.filter(
                medicine=medicine,
                date=today,
                time=scheduled_time,
            ).first()

            if log and log.status in ['taken', 'skipped']:
                continue

            # Check if we already sent a check-in for this dose today
            item_key = f"{medicine.id}_{scheduled_time.strftime('%H%M')}"
            recent_checkin = AssistantMessage.objects.filter(
                conversation__user=user,
                is_proactive=True,
                metadata__check_in_type='medicine',
                metadata__medicine_id=medicine.id,
                metadata__dose_time=scheduled_time.strftime('%H:%M'),
                created_at__date=today,
            ).exists()

            if recent_checkin:
                continue

            # Get health context if available
            context = _get_medicine_health_context(medicine)

            # Generate check-in
            service.generate_medicine_check_in(
                medicine=medicine,
                dose_time=scheduled_time.strftime('%H:%M'),
                context=context
            )


def _get_medicine_health_context(medicine) -> Optional[str]:
    """
    Get relevant health context for a medicine reminder.

    Uses the medicine's reason/notes to add context.
    Example: "Your last labs showed elevated cholesterol"
    """
    reason = getattr(medicine, 'reason', '') or ''
    notes = getattr(medicine, 'notes', '') or ''
    combined = f"{reason} {notes}".lower()

    if 'cholesterol' in combined:
        return 'elevated cholesterol'
    if 'blood pressure' in combined or 'hypertension' in combined:
        return 'elevated blood pressure'
    if 'diabetes' in combined or 'glucose' in combined or 'blood sugar' in combined:
        return 'blood sugar management'
    if 'thyroid' in combined:
        return 'thyroid levels'
    if 'heart' in combined or 'cardiac' in combined:
        return 'heart health'

    return None


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
        return

    if check_type == 'workout':
        service.generate_workout_check_in()
    elif check_type == 'journal':
        service.generate_journal_check_in()


def generate_overdue_task_check_ins_for_user(user):
    """
    Generate check-ins for overdue tasks.

    Only sends for the most overdue task to avoid spam.
    """
    from apps.life.models import Task
    from apps.core.utils import get_user_today

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    service = get_proactive_service(user)
    today = get_user_today(user)

    # Get the most overdue incomplete task
    overdue_task = Task.objects.filter(
        user=user,
        due_date__lt=today,
        is_complete=False,
    ).order_by('due_date').first()

    if overdue_task:
        service.generate_overdue_task_check_in(overdue_task)


def generate_busy_day_check_ins_for_user(user):
    """
    Generate check-in if tomorrow is a busy day.

    Helps user plan ahead if they have 5+ items scheduled.
    """
    from apps.core.utils import get_user_today
    from apps.life.models import Task, CalendarEvent

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    service = get_proactive_service(user)
    today = get_user_today(user)
    tomorrow = today + timedelta(days=1)

    # Count tomorrow's load
    tasks_due = Task.objects.filter(
        user=user,
        due_date=tomorrow,
        is_complete=False,
    ).count()

    events = CalendarEvent.objects.filter(
        user=user,
        start_time__date=tomorrow,
    ).count()

    total = tasks_due + events

    if total >= 5:
        service.generate_busy_day_check_in(total)


def generate_pattern_check_ins_for_user(user):
    """
    Generate pattern observation messages.

    Finds factual correlations in user data and shares observations.
    NOT advice - just observations.
    """
    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    from .assistant_intelligence import PatternAnalyzer

    service = get_proactive_service(user)
    analyzer = PatternAnalyzer(user)

    # Try food-glucose correlation
    food_result = analyzer.find_food_glucose_correlations()
    if food_result:
        observation = f"higher blood sugar readings on days when {food_result['food']} is logged"
        service.generate_pattern_observation('food_glucose', observation)
        return  # Only one pattern per run

    # Try workout-mood correlation
    workout_result = analyzer.find_workout_mood_correlation()
    if workout_result:
        service.generate_pattern_observation('workout_mood', workout_result['observation'])
        return

    # Try sleep correlation
    sleep_result = analyzer.find_sleep_energy_correlation()
    if sleep_result:
        service.generate_pattern_observation('sleep_mood', sleep_result['observation'])


def generate_birthday_check_ins_for_user(user):
    """
    Generate birthday/memorial greeting messages for a user.
    """
    from apps.life.models import SignificantEvent
    from apps.core.utils import get_user_today

    service = get_proactive_service(user)
    today = get_user_today(user)

    events = SignificantEvent.objects.filter(
        user=user,
        event_date__month=today.month,
        event_date__day=today.day,
    )

    for event in events:
        # Check if we already sent a greeting today
        recent = AssistantMessage.objects.filter(
            conversation__user=user,
            is_proactive=True,
            metadata__check_in_type='birthday',
            metadata__event_id=event.id,
            created_at__date=today,
        ).exists()

        if not recent:
            service.generate_birthday_greeting(event)
