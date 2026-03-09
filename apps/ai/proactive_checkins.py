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
    generate_faith_reading_replies,
    generate_finance_budget_replies,
    generate_goal_check_in_replies,
    generate_relationship_drift_replies,
    generate_journal_concern_replies,
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

    def generate_grouped_medicine_check_in(
        self,
        time_of_day: str,
        medicines: list,
        due_time=None,
    ) -> Optional[AssistantMessage]:
        """
        Generate a SINGLE grouped check-in for all medicines in a time period.

        Instead of "Your 9:00 AM Atorvastatin wasn't marked" x3, sends:
        "Your morning meds are due by 9:00 AM." with group action buttons.

        Args:
            time_of_day: The time group (morning, evening, nightly, etc.)
            medicines: List of (medicine, schedule) tuples
            due_time: The scheduled_time for this group (for display + snooze)

        Returns:
            AssistantMessage with grouped quick reply buttons, or None if throttled
        """
        # Check throttle
        item_key = f"group_{time_of_day}"
        if not self.throttler.can_send('medicine', hash(item_key)):
            return None

        # Format time for display
        time_display = ''
        if due_time:
            try:
                from datetime import datetime
                time_obj = datetime.combine(datetime.today(), due_time)
                time_display = time_obj.strftime('%I:%M %p').lstrip('0')
            except (ValueError, TypeError):
                time_display = str(due_time)

        # Build grouped message
        group_display = time_of_day.replace('_', ' ').title()
        med_count = len(medicines)
        med_names = ', '.join(m.name for m, s in medicines)

        if time_display:
            template = get_style_template(self.user, 'grouped_meds_due')
            message_content = template.format(
                group=group_display.lower(),
                time=time_display,
                count=med_count,
                names=med_names,
            )
        else:
            message_content = f"Your {group_display.lower()} meds haven't been marked yet."

        # Build quick replies with GROUP actions
        from .quick_reply_handlers import generate_grouped_medicine_replies
        quick_replies = generate_grouped_medicine_replies(
            time_of_day=time_of_day,
            medicine_ids=[m.id for m, s in medicines],
            due_time=due_time.strftime('%H:%M') if due_time else None,
        )

        medicine_ids = [m.id for m, s in medicines]
        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'medicine_group',
                'time_of_day': time_of_day,
                'medicine_ids': medicine_ids,
                'medicine_count': med_count,
                'due_time': due_time.strftime('%H:%M') if due_time else None,
            }
        )

    def generate_workout_check_in(self) -> Optional[AssistantMessage]:
        """
        Generate a brief check-in about today's workout.

        Respects the user's workout schedule — skips rest days and
        unscheduled days. If no active plan, falls back to asking daily.

        Message: Direct, short question. No motivational speech.

        Returns:
            AssistantMessage with quick reply buttons, or None
        """
        from apps.health.models import WorkoutPlan, WorkoutSession
        from apps.core.utils import get_user_today

        if not self.throttler.can_send('workout'):
            return None

        today = get_user_today(self.user)

        # Check if today is a scheduled workout day
        active_plan = WorkoutPlan.objects.filter(
            user=self.user, is_active=True
        ).first()

        if active_plan:
            schedule_entry = active_plan.schedule_entries.filter(
                day_of_week=today.weekday()
            ).first()
            # Skip if no schedule entry for today, or if it's a rest day
            if schedule_entry is None or schedule_entry.is_rest_day:
                return None

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

    def generate_nn_skip_check_in(self, task) -> Optional[AssistantMessage]:
        """
        Generate an escalating check-in for a non-negotiable task with skip streak >= 2.

        Uses effective_skip_streak (recency-guarded) and coaching style templates.
        Escalation is capped at Day 3 — Day 4+ shifts to supportive problem-solving.

        Args:
            task: Task model instance with commitment_level='non_negotiable'

        Returns:
            AssistantMessage, or None if throttled or not applicable
        """
        streak = task.effective_skip_streak
        if streak < 2 or task.commitment_level != 'non_negotiable':
            return None

        if not self.throttler.can_send('nn_skip', task.id):
            return None

        # Select escalation tier (capped at Day 3)
        if streak >= 4:
            template_key = 'nn_skip_supportive'
        elif streak == 3:
            template_key = 'nn_skip_coaching'
        else:
            template_key = 'nn_skip_pattern'

        template = get_style_template(self.user, template_key)
        message_content = template.format(task=task.title, streak=streak)

        return self._create_proactive_message(
            content=message_content,
            message_type='nudge',
            metadata={
                'check_in_type': 'nn_skip_streak',
                'task_id': task.id,
                'item_id': task.id,
                'skip_streak': streak,
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

    # =========================================================================
    # Phase 4: Cross-Domain Proactive Check-Ins
    # =========================================================================

    def generate_faith_reading_check_in(
        self, plan, days_behind: int = 0
    ) -> Optional[AssistantMessage]:
        """
        Generate a check-in for an active reading plan.

        Args:
            plan: UserReadingPlan instance
            days_behind: Number of days behind schedule
        """
        if not self.throttler.can_send('faith_reading', plan.id):
            return None

        template = get_style_template(self.user, 'faith_reading_gap')
        message_content = template.format(
            day=plan.current_day,
            plan=plan.template.title,
            progress=plan.progress_percentage,
        )

        quick_replies = generate_faith_reading_replies(plan.id)

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'faith_reading',
                'plan_id': plan.id,
                'item_id': plan.id,
                'days_behind': days_behind,
            }
        )

    def generate_faith_prayer_check_in(
        self, count: int
    ) -> Optional[AssistantMessage]:
        """Generate a reminder about prayer requests with daily reminders."""
        if not self.throttler.can_send('faith_prayer'):
            return None

        template = get_style_template(self.user, 'faith_prayer_reminder')
        message_content = template.format(count=count)

        return self._create_proactive_message(
            content=message_content,
            quick_replies=[],
            message_type='nudge',
            metadata={
                'check_in_type': 'faith_prayer',
                'prayer_count': count,
            }
        )

    def generate_finance_budget_check_in(
        self, budget, percent_used: int, days_left: int
    ) -> Optional[AssistantMessage]:
        """Generate a budget threshold alert."""
        if not self.throttler.can_send('finance_budget', budget.id):
            return None

        template = get_style_template(self.user, 'finance_budget_alert')
        message_content = template.format(
            percent=percent_used,
            category=budget.category.name,
            days_left=days_left,
        )

        quick_replies = generate_finance_budget_replies(budget.category.name)

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'finance_budget',
                'budget_id': budget.id,
                'item_id': budget.id,
                'percent_used': percent_used,
            }
        )

    def generate_finance_goal_check_in(
        self, goal, stalling_days: int = 0
    ) -> Optional[AssistantMessage]:
        """Generate a financial goal progress or stalling check-in."""
        if not self.throttler.can_send('finance_goal', goal.id):
            return None

        percent = int((goal.current_amount / goal.target_amount) * 100) if goal.target_amount else 0

        if stalling_days > 14:
            template = get_style_template(self.user, 'finance_goal_stalling')
            message_content = template.format(
                goal=goal.name,
                days=stalling_days,
                target_date=goal.target_date.strftime('%b %d') if goal.target_date else 'not set',
            )
        else:
            template = get_style_template(self.user, 'finance_goal_milestone')
            message_content = template.format(
                goal=goal.name,
                current=f"{goal.current_amount:,.0f}",
                target=f"{goal.target_amount:,.0f}",
                percent=percent,
            )

        return self._create_proactive_message(
            content=message_content,
            quick_replies=[],
            message_type='nudge' if stalling_days > 14 else 'insight',
            metadata={
                'check_in_type': 'finance_goal',
                'goal_id': goal.id,
                'item_id': goal.id,
                'percent': percent,
            }
        )

    def generate_relationship_drift_check_in(
        self, drift_alert: dict
    ) -> Optional[AssistantMessage]:
        """Generate a check-in for relationship drift."""
        person_id = drift_alert['person_id']
        if not self.throttler.can_send('relationship_drift', person_id):
            return None

        tier_names = {1: 'inner', 2: 'close', 3: 'wider'}
        tier = tier_names.get(drift_alert['importance_tier'], 'wider')

        template = get_style_template(self.user, 'relationship_drift')
        message_content = template.format(
            days=drift_alert['actual_gap_days'],
            person=drift_alert['person_name'],
            tier=tier,
        )

        quick_replies = generate_relationship_drift_replies(drift_alert['person_name'])

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'relationship_drift',
                'person_id': person_id,
                'item_id': person_id,
                'gap_days': drift_alert['actual_gap_days'],
            }
        )

    def generate_goal_deadline_check_in(
        self, goal, days_until: int
    ) -> Optional[AssistantMessage]:
        """Generate a check-in for an approaching goal deadline."""
        if not self.throttler.can_send('goal_deadline', goal.id):
            return None

        template = get_style_template(self.user, 'goal_deadline')
        message_content = template.format(
            goal=goal.title,
            days=days_until,
        )

        quick_replies = generate_goal_check_in_replies(goal.id, goal_type='life')

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'goal_deadline',
                'goal_id': goal.id,
                'item_id': goal.id,
                'days_until': days_until,
            }
        )

    def generate_goal_stalling_check_in(
        self, goal, days_stalled: int
    ) -> Optional[AssistantMessage]:
        """Generate a check-in for a stalling goal."""
        if not self.throttler.can_send('goal_stalling', goal.id):
            return None

        template = get_style_template(self.user, 'goal_stalling')
        message_content = template.format(
            goal=goal.title,
            days=days_stalled,
        )

        quick_replies = generate_goal_check_in_replies(goal.id, goal_type='life')

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'goal_stalling',
                'goal_id': goal.id,
                'item_id': goal.id,
                'days_stalled': days_stalled,
            }
        )

    def generate_habit_streak_check_in(
        self, habit, streak: int, is_break: bool = False
    ) -> Optional[AssistantMessage]:
        """Generate a habit streak break or acknowledgment."""
        if not self.throttler.can_send('habit_streak', habit.id):
            return None

        if is_break:
            template = get_style_template(self.user, 'habit_streak_break')
            message_content = template.format(habit=habit.name, streak=streak)
            msg_type = 'nudge'
        else:
            template = get_style_template(self.user, 'habit_streak_note')
            message_content = template.format(habit=habit.name, streak=streak)
            msg_type = 'insight'

        return self._create_proactive_message(
            content=message_content,
            quick_replies=[],
            message_type=msg_type,
            metadata={
                'check_in_type': 'habit_streak',
                'habit_id': habit.id,
                'item_id': habit.id,
                'streak': streak,
                'is_break': is_break,
            }
        )

    def generate_journal_concern_check_in(
        self, concern: str, entry_count: int
    ) -> Optional[AssistantMessage]:
        """Generate a check-in about a recurring journal concern."""
        if not self.throttler.can_send('journal_concern'):
            return None

        template = get_style_template(self.user, 'journal_concern')
        message_content = template.format(concern=concern, count=entry_count)

        quick_replies = generate_journal_concern_replies()

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='insight',
            metadata={
                'check_in_type': 'journal_concern',
                'concern_term': concern,
                'entry_count': entry_count,
            }
        )

    def generate_journal_gap_check_in(
        self, days_since: int
    ) -> Optional[AssistantMessage]:
        """Generate a check-in for extended journal gap (3+ days)."""
        if not self.throttler.can_send('journal_gap'):
            return None

        template = get_style_template(self.user, 'journal_gap_extended')
        message_content = template.format(days=days_since)

        quick_replies = generate_journal_check_in_replies()

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'journal_gap',
                'days_since': days_since,
            }
        )

    # Check-in types that warrant immediate push delivery (high priority)
    _HIGH_PRIORITY_CHECKIN_TYPES = {'medicine', 'grouped_medicine'}
    # Check-in types that use standard delivery (lower priority)
    _STANDARD_CHECKIN_TYPES = {'workout', 'journal', 'overdue_task', 'busy_day',
                               'faith_reading', 'finance_budget', 'goal_deadline',
                               'relationship_drift', 'journal_concern'}

    def _create_proactive_message(
        self,
        content: str,
        quick_replies: list,
        message_type: str = 'nudge',
        metadata: dict = None
    ) -> AssistantMessage:
        """
        Create a proactive assistant message AND route through DNE.

        Creates the in-app chat message (so users see it when they open chat)
        AND creates a DeliveryItem routed through the Delivery Notification
        Engine for push/SMS/email delivery based on user preferences.

        High-priority check-ins (medication) get priority=1 (bypasses quiet hours).
        Standard check-ins get priority=3.

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

        # ── Route through DNE for push/SMS/email delivery ──
        check_in_type = (metadata or {}).get('check_in_type', '')
        self._route_through_dne(message, check_in_type, content)

        return message

    def _route_through_dne(self, message, check_in_type, content):
        """
        Route a proactive check-in through the Delivery Notification Engine.

        This enables push notifications, SMS, and email delivery in addition
        to the in-app chat message. Respects user notification preferences.

        High-priority items (medication) get priority=1 (bypass quiet hours).
        Standard items get priority=3.
        """
        try:
            from apps.core.ai_delivery.delivery_engine import deliver_single

            is_high_priority = check_in_type in self._HIGH_PRIORITY_CHECKIN_TYPES

            # Build delivery payload
            icon = "💊" if 'medicine' in check_in_type else "📋"
            if check_in_type == 'workout':
                icon = "🏋️"
            elif check_in_type == 'journal':
                icon = "📝"

            payload = {
                "title": f"Check-in: {check_in_type.replace('_', ' ').title()}",
                "message": content,
                "action_url": "/assistant/",
                "icon": icon,
                "priority": 1 if is_high_priority else 3,
            }

            deliver_single(
                user=self.user,
                source_engine="COS",
                source_object=message,
                payload=payload,
            )

            logger.info(
                "COS_PROACTIVE_DNE_ROUTED user=%s type=%s priority=%s",
                self.user.id, check_in_type,
                "HIGH" if is_high_priority else "STANDARD",
            )

        except Exception as e:
            # DNE routing is best-effort — never block the check-in
            logger.warning(
                "COS_PROACTIVE_DNE_FAIL user=%s type=%s error=%s",
                self.user.id, check_in_type, e,
            )


def get_proactive_service(user):
    """Get the proactive check-in service for a user."""
    return ProactiveCheckInService(user)


# =============================================================================
# SCHEDULED JOB FUNCTIONS
# =============================================================================

def generate_medicine_check_ins_for_user(user, dose_time: str = None):
    """
    Generate GROUPED medicine check-in messages for a user.

    Groups medicines by time_of_day (morning, evening, nightly, etc.) and
    sends ONE check-in per group instead of per-pill notifications.

    Only sends if:
    - User has proactive checkins enabled
    - Dose time has passed (in USER'S local timezone)
    - Not already logged or checked-in today
    - Not throttled (no spam)

    Args:
        user: User to generate check-ins for
        dose_time: Optional specific dose time
    """
    from apps.health.models import Medicine, MedicineSchedule, MedicineLog
    from apps.core.utils import get_user_today, get_user_now
    from collections import defaultdict

    # Check user preferences
    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return
    if not getattr(prefs, 'assistant_medicine_checkins', True):
        return

    service = get_proactive_service(user)
    today = get_user_today(user)
    # CRITICAL: Use user's LOCAL time, not UTC. At 7:42 AM CST,
    # timezone.now().time() returns 1:42 PM UTC which falsely triggers
    # 9:00 AM check-ins 2 hours early.
    user_now = get_user_now(user)
    current_time = user_now.time()

    # Get active medicines
    medicines = Medicine.objects.filter(user=user, medicine_status='active')

    # Collect un-logged medicines grouped by time_of_day
    # Key: time_of_day (e.g., "morning") → list of (medicine, schedule) tuples
    pending_by_group = defaultdict(list)
    # Track the latest scheduled_time per group for "Remind me later"
    group_due_times = {}

    for medicine in medicines:
        schedules = MedicineSchedule.objects.filter(medicine=medicine, is_active=True)

        for schedule in schedules:
            if not schedule.applies_to_day(today.weekday()):
                continue

            scheduled_time = schedule.scheduled_time

            # Only check doses whose time has passed in user's LOCAL timezone
            if current_time < scheduled_time:
                continue

            # Check if already logged
            log = MedicineLog.objects.filter(
                medicine=medicine,
                scheduled_date=today,
                scheduled_time=scheduled_time,
            ).first()

            if log and log.log_status in ['taken', 'skipped']:
                continue

            # Group by time_of_day (morning, evening, etc.)
            group_key = schedule.time_of_day or 'other'
            pending_by_group[group_key].append((medicine, schedule))

            # Track the due time for "Remind me later"
            if group_key not in group_due_times or scheduled_time > group_due_times[group_key]:
                group_due_times[group_key] = scheduled_time

    # Generate ONE grouped check-in per time_of_day group
    for group_key, med_schedules in pending_by_group.items():
        if not med_schedules:
            continue

        # Check if we already sent a grouped check-in for this group today
        recent_group_checkin = AssistantMessage.objects.filter(
            conversation__user=user,
            is_proactive=True,
            metadata__check_in_type='medicine_group',
            metadata__time_of_day=group_key,
            created_at__date=today,
        ).exists()

        if recent_group_checkin:
            continue

        # Build the grouped message
        due_time = group_due_times.get(group_key)
        service.generate_grouped_medicine_check_in(
            time_of_day=group_key,
            medicines=[(m, s) for m, s in med_schedules],
            due_time=due_time,
        )


def _get_medicine_health_context(medicine) -> Optional[str]:
    """
    Get relevant health context for a medicine reminder.

    Uses the medicine's reason/notes to add context.
    Example: "Your last labs showed elevated cholesterol"
    """
    purpose = getattr(medicine, 'purpose', '') or ''
    notes = getattr(medicine, 'notes', '') or ''
    combined = f"{purpose} {notes}".lower()

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


def generate_nn_skip_check_ins_for_user(user):
    """
    Generate check-ins for non-negotiable tasks with skip streaks >= 2.

    Only generates for tasks where effective_skip_streak >= 2 (recency-guarded).
    Max 3 check-ins per run to avoid overwhelming.
    """
    from apps.life.models import Task

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    service = get_proactive_service(user)

    # Get non-negotiable tasks with skip streaks
    nn_tasks = Task.objects.filter(
        user=user,
        commitment_level='non_negotiable',
        skip_streak__gte=2,
        status='active',
    ).order_by('-skip_streak')[:5]  # Top 5 candidates

    generated = 0
    for task in nn_tasks:
        if task.effective_skip_streak >= 2:
            result = service.generate_nn_skip_check_in(task)
            if result:
                generated += 1
                if generated >= 3:
                    break


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


# =============================================================================
# Phase 4: Cross-Domain Scheduled Job Functions
# =============================================================================


def generate_faith_check_ins_for_user(user):
    """
    Generate faith-related proactive check-ins.

    Checks:
    1. Active reading plans with unread days
    2. Prayer requests with daily reminders
    """
    from apps.core.utils import get_user_today

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    service = get_proactive_service(user)
    today = get_user_today(user)

    # 1. Reading plan check
    try:
        from apps.faith.models import UserReadingPlan, UserReadingProgress

        active_plans = UserReadingPlan.objects.filter(
            user=user, plan_status='active',
        )

        for plan in active_plans:
            # Check if today's reading is done
            today_done = UserReadingProgress.objects.filter(
                user_plan=plan,
                reading_day__day_number=plan.current_day,
                is_completed=True,
            ).exists()

            if not today_done:
                # Check if we already sent this today
                recent = AssistantMessage.objects.filter(
                    conversation__user=user,
                    is_proactive=True,
                    metadata__check_in_type='faith_reading',
                    metadata__plan_id=plan.id,
                    created_at__date=today,
                ).exists()

                if not recent:
                    service.generate_faith_reading_check_in(plan)
                    break  # Only one reading plan nudge per run

    except ImportError:
        pass
    except Exception as e:
        logger.warning("Faith reading check-in error: %s", e, exc_info=True)

    # 2. Prayer request reminders
    try:
        from apps.faith.models import PrayerRequest

        daily_prayers = PrayerRequest.objects.filter(
            user=user,
            remind_daily=True,
            is_answered=False,
            deleted_at__isnull=True,
        ).count()

        if daily_prayers > 0:
            recent = AssistantMessage.objects.filter(
                conversation__user=user,
                is_proactive=True,
                metadata__check_in_type='faith_prayer',
                created_at__date=today,
            ).exists()

            if not recent:
                service.generate_faith_prayer_check_in(daily_prayers)

    except ImportError:
        pass
    except Exception as e:
        logger.warning("Faith prayer check-in error: %s", e, exc_info=True)


def generate_finance_check_ins_for_user(user):
    """
    Generate finance-related proactive check-ins.

    Checks:
    1. Budget categories over 80% spent
    2. Financial goals stalling (no progress in 14+ days)
    """
    from apps.core.utils import get_user_today

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    service = get_proactive_service(user)
    today = get_user_today(user)

    # 1. Budget threshold alerts
    try:
        from apps.finance.models import Budget

        # Get current month's budgets
        current_month = today.replace(day=1)
        budgets = Budget.objects.filter(
            user=user, month=current_month,
        ).select_related('category')

        days_in_month = 30  # Approximate
        days_left = max(1, days_in_month - today.day)

        for budget in budgets:
            if budget.total_budget <= 0:
                continue

            spent = budget.spent_amount
            percent_used = int((spent / budget.total_budget) * 100)

            if percent_used >= 80:
                recent = AssistantMessage.objects.filter(
                    conversation__user=user,
                    is_proactive=True,
                    metadata__check_in_type='finance_budget',
                    metadata__budget_id=budget.id,
                    created_at__date=today,
                ).exists()

                if not recent:
                    service.generate_finance_budget_check_in(
                        budget, percent_used, days_left,
                    )

    except ImportError:
        pass
    except Exception as e:
        logger.warning("Finance budget check-in error: %s", e, exc_info=True)

    # 2. Financial goal stalling
    try:
        from apps.finance.models import FinancialGoal

        active_goals = FinancialGoal.objects.filter(
            user=user, status='active',
        )

        for goal in active_goals:
            # Check days since last update
            days_since_update = (today - goal.updated_at.date()).days if goal.updated_at else 999

            if days_since_update > 14:
                recent = AssistantMessage.objects.filter(
                    conversation__user=user,
                    is_proactive=True,
                    metadata__check_in_type='finance_goal',
                    metadata__goal_id=goal.id,
                    created_at__date=today,
                ).exists()

                if not recent:
                    service.generate_finance_goal_check_in(
                        goal, stalling_days=days_since_update,
                    )
                    break  # Only one per run

    except ImportError:
        pass
    except Exception as e:
        logger.warning("Finance goal check-in error: %s", e, exc_info=True)


def generate_relationship_check_ins_for_user(user):
    """
    Generate relationship drift check-ins.

    Uses the existing relationship engine's drift detection.
    Only sends for the top-priority drift alert per run.
    """
    from apps.core.utils import get_user_today

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    service = get_proactive_service(user)
    today = get_user_today(user)

    try:
        from apps.core.ai_relationships.relationship_engine import detect_relational_drift

        alerts = detect_relational_drift(user)

        for alert in alerts[:2]:  # Max 2 per run
            recent = AssistantMessage.objects.filter(
                conversation__user=user,
                is_proactive=True,
                metadata__check_in_type='relationship_drift',
                metadata__person_id=alert['person_id'],
                created_at__date=today,
            ).exists()

            if not recent:
                service.generate_relationship_drift_check_in(alert)

    except ImportError:
        pass
    except Exception as e:
        logger.warning("Relationship check-in error: %s", e, exc_info=True)


def generate_goal_check_ins_for_user(user):
    """
    Generate goal and habit check-ins.

    Checks:
    1. Life goals with approaching deadlines (within 7 days)
    2. Life goals stalling (no milestone update in 30+ days)
    3. Habit streaks broken or milestone reached
    """
    from apps.core.utils import get_user_today

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    service = get_proactive_service(user)
    today = get_user_today(user)

    # 1. Goal deadlines
    try:
        from apps.purpose.models import LifeGoal

        upcoming_deadline = today + timedelta(days=7)
        goals_near_deadline = LifeGoal.objects.filter(
            user=user,
            status='active',
            target_date__isnull=False,
            target_date__lte=upcoming_deadline,
            target_date__gte=today,
        )

        for goal in goals_near_deadline[:2]:
            days_until = (goal.target_date - today).days

            recent = AssistantMessage.objects.filter(
                conversation__user=user,
                is_proactive=True,
                metadata__check_in_type='goal_deadline',
                metadata__goal_id=goal.id,
                created_at__date=today,
            ).exists()

            if not recent:
                service.generate_goal_deadline_check_in(goal, days_until)

    except ImportError:
        pass
    except Exception as e:
        logger.warning("Goal deadline check-in error: %s", e, exc_info=True)

    # 2. Goal stalling
    try:
        from apps.purpose.models import LifeGoal, GoalMilestone

        active_goals = LifeGoal.objects.filter(
            user=user, status='active',
        )

        for goal in active_goals:
            # Check last milestone update
            last_milestone = GoalMilestone.objects.filter(
                goal=goal,
            ).order_by('-updated_at').first()

            if last_milestone:
                days_stalled = (today - last_milestone.updated_at.date()).days
            else:
                days_stalled = (today - goal.created_at.date()).days if goal.created_at else 0

            if days_stalled > 30:
                recent = AssistantMessage.objects.filter(
                    conversation__user=user,
                    is_proactive=True,
                    metadata__check_in_type='goal_stalling',
                    metadata__goal_id=goal.id,
                    created_at__date=today,
                ).exists()

                if not recent:
                    service.generate_goal_stalling_check_in(goal, days_stalled)
                    break  # Only one per run

    except ImportError:
        pass
    except Exception as e:
        logger.warning("Goal stalling check-in error: %s", e, exc_info=True)

    # 3. Habit streaks
    try:
        from apps.purpose.models import HabitGoal
        from apps.purpose.services.streak_service import get_current_streak

        active_habits = HabitGoal.objects.filter(
            user=user, status='active',
        )

        for habit in active_habits:
            try:
                streak = get_current_streak(habit)
            except Exception:
                # If no streak util exists, try a simple completion check
                continue

            if streak == 0:
                # Check if there was a streak that just broke
                # (had completions in recent days but not yesterday/today)
                from apps.purpose.models import HabitEntry
                recent_completions = HabitEntry.objects.filter(
                    goal=habit,
                    date__gte=today - timedelta(days=7),
                    date__lt=today,
                    completed=True,
                ).count()

                if recent_completions >= 3:
                    recent = AssistantMessage.objects.filter(
                        conversation__user=user,
                        is_proactive=True,
                        metadata__check_in_type='habit_streak',
                        metadata__habit_id=habit.id,
                        created_at__date=today,
                    ).exists()

                    if not recent:
                        service.generate_habit_streak_check_in(
                            habit, streak=recent_completions, is_break=True,
                        )

            elif streak in (7, 14, 21, 30, 60, 90):
                # Milestone acknowledgment
                recent = AssistantMessage.objects.filter(
                    conversation__user=user,
                    is_proactive=True,
                    metadata__check_in_type='habit_streak',
                    metadata__habit_id=habit.id,
                    created_at__date=today,
                ).exists()

                if not recent:
                    service.generate_habit_streak_check_in(
                        habit, streak=streak, is_break=False,
                    )

    except ImportError:
        pass
    except Exception as e:
        logger.warning("Habit streak check-in error: %s", e, exc_info=True)


def generate_journal_intelligence_check_ins_for_user(user):
    """
    Generate journal intelligence check-ins.

    Leverages Phase 2 content_intelligence for:
    1. Recurring concern patterns
    2. Extended journal gaps (3+ days)
    """
    from apps.core.utils import get_user_today

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return
    if not getattr(prefs, 'assistant_journal_checkins', True):
        return

    service = get_proactive_service(user)
    today = get_user_today(user)

    # 1. Recurring concerns
    try:
        from apps.journal.services.content_intelligence import detect_recurring_concerns

        concerns = detect_recurring_concerns(user, days=14, min_occurrences=3)

        if concerns:
            top_concern = concerns[0]
            recent = AssistantMessage.objects.filter(
                conversation__user=user,
                is_proactive=True,
                metadata__check_in_type='journal_concern',
                created_at__date=today,
            ).exists()

            if not recent:
                service.generate_journal_concern_check_in(
                    concern=top_concern['term'],
                    entry_count=top_concern['entries'],
                )

    except ImportError:
        pass
    except Exception as e:
        logger.warning("Journal concern check-in error: %s", e, exc_info=True)

    # 2. Extended journal gap
    try:
        from apps.journal.models import JournalEntry

        last_entry = JournalEntry.objects.filter(
            user=user, deleted_at__isnull=True,
        ).order_by('-entry_date').first()

        if last_entry:
            days_since = (today - last_entry.entry_date).days

            if days_since >= 3:
                recent = AssistantMessage.objects.filter(
                    conversation__user=user,
                    is_proactive=True,
                    metadata__check_in_type='journal_gap',
                    created_at__date=today,
                ).exists()

                if not recent:
                    service.generate_journal_gap_check_in(days_since)

    except ImportError:
        pass
    except Exception as e:
        logger.warning("Journal gap check-in error: %s", e, exc_info=True)
