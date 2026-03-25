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


# =============================================================================
# DEDUP CACHE — Batch-loads today's proactive messages in 1 query
# =============================================================================

class _ProactiveDedupCache:
    """
    In-memory cache of today's proactive messages for a single user.

    Eliminates 20-30 per-generator AssistantMessage dedup queries by loading
    all proactive metadata once and checking in memory.

    Usage:
        cache = _ProactiveDedupCache(user, today)
        if cache.already_sent('medicine_group', time_of_day='morning'):
            return  # skip
    """

    def __init__(self, user, today):
        self.user = user
        self.today = today
        self._entries = None  # Lazy load

    def _load(self):
        """Batch-load all proactive message metadata for today (single query)."""
        if self._entries is not None:
            return
        raw = AssistantMessage.objects.filter(
            conversation__user=self.user,
            is_proactive=True,
            created_at__date=self.today,
        ).values_list('metadata', flat=True)
        self._entries = [m for m in raw if m]

    def already_sent(self, check_in_type, **extra_filters):
        """
        Check if a proactive message of this type was already sent today.

        Args:
            check_in_type: The metadata.check_in_type value.
            **extra_filters: Additional metadata keys to match
                (e.g., time_of_day='morning', plan_id=5).

        Returns:
            bool — True if a matching message already exists.
        """
        self._load()
        for meta in self._entries:
            if meta.get('check_in_type') != check_in_type:
                continue
            if extra_filters:
                if all(meta.get(k) == v for k, v in extra_filters.items()):
                    return True
            else:
                return True
        return False


# Thread-local holder so generators can access the cache without parameter changes.
# Set by run_proactive_guidance_scheduler() before dispatching, cleared after.
import threading
_dedup_local = threading.local()


def _get_dedup_cache(user):
    """
    Get the current dedup cache for this user, or create a per-call one.

    When called from PGS runner, returns the pre-loaded batch cache.
    When called standalone (e.g., tests), creates a new cache on demand.
    """
    cache = getattr(_dedup_local, 'cache', None)
    if cache is not None and cache.user == user:
        return cache
    # Fallback: create a new cache (still better than N queries if reused)
    from apps.core.utils import get_user_today
    return _ProactiveDedupCache(user, get_user_today(user))


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
        from apps.core.utils import get_user_today

        if not self.throttler.can_send('journal'):
            return None

        today = get_user_today(self.user)

        # Already journaled? Don't ask. Use canonical service.
        from apps.journal.services.metrics import get_journal_metrics
        metrics = get_journal_metrics(self.user)
        if metrics.get('last_journal_date') == today:
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
        if task.is_completed:
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

    def generate_cdce_correlation_check_in(
        self, correlation_type: str, narrative: str,
        strength: str, domains: list,
    ) -> Optional[AssistantMessage]:
        """
        Generate a proactive check-in based on a CDCE cross-domain correlation.

        Phase 7.2: Surfaces discovered cross-domain patterns as actionable
        intelligence. E.g., "Your sleep data shows a pattern: on days you
        sleep 7+ hours, your mood journal entries are significantly more positive."
        """
        throttle_key = f'cdce_{correlation_type}'
        if not self.throttler.can_send(throttle_key):
            return None

        domain_str = ' & '.join(d.title() for d in domains[:2])
        strength_label = (
            "a strong" if strength == 'strong'
            else "a notable" if strength == 'moderate'
            else "a possible"
        )

        message_content = (
            f"I've noticed {strength_label} pattern across your "
            f"{domain_str} data: {narrative}"
        )

        quick_replies = [
            {'label': 'Tell me more', 'action': 'chat',
             'value': f'Tell me more about the {correlation_type.replace("_", " ")} pattern'},
            {'label': 'How to use this', 'action': 'chat',
             'value': f'How can I use this {domain_str} insight to improve?'},
            {'label': 'Got it', 'action': 'dismiss'},
        ]

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='insight',
            metadata={
                'check_in_type': 'cdce_correlation',
                'correlation_type': correlation_type,
                'strength': strength,
                'domains': domains,
            }
        )

    def generate_routine_recovery_check_in(
        self, item: dict, tier: str,
    ) -> Optional[AssistantMessage]:
        """
        Generate a proactive check-in for a missed/overdue routine item.

        Escalation tiers:
        - tier1: Window passed, offer reschedule
        - tier2: Still outstanding midday
        - tier3: Last chance before day close

        Args:
            item: ExecutionItem dict from build_today_execution()
            tier: 'tier1', 'tier2', or 'tier3'

        Returns:
            AssistantMessage with quick reply buttons, or None if throttled
        """
        schedule_id = item.get('source_id')
        item_name = item.get('title', 'routine item')

        # Throttle key includes schedule_id + tier for per-item-per-tier dedup
        throttle_key = f'routine_recovery_{schedule_id}_{tier}'
        if not self.throttler.can_send(throttle_key, schedule_id):
            return None

        # Context-aware: if recent conversation suggests engagement, ask
        # instead of assuming a miss (Step 4 adjustment)
        recent_mention = self._check_recent_conversation_for_item(item)

        # Select template based on context and tier
        reschedule_count = item.get('reschedule_count', 0) or 0
        if recent_mention:
            template_key = 'routine_ask_if_completed'
        elif reschedule_count >= 2:
            # Item has been moved multiple times — use gentler "lock it in" tone
            template_key = 'routine_moved_multiple'
        else:
            template_map = {
                'tier1': 'routine_missed_window',
                'tier2': 'routine_still_outstanding',
                'tier3': 'routine_last_chance',
            }
            template_key = template_map.get(tier, 'routine_missed_window')
        template = get_style_template(self.user, template_key)
        message_content = template.format(
            item_name=item_name, count=reschedule_count,
        )

        # Use follow-up replies (with "Not yet") when context-aware
        if recent_mention:
            from apps.ai.quick_reply_handlers import generate_nudge_follow_up_replies
            quick_replies = generate_nudge_follow_up_replies(
                schedule_id=schedule_id,
                item_name=item_name,
            )
        else:
            from apps.ai.quick_reply_handlers import generate_routine_recovery_replies
            quick_replies = generate_routine_recovery_replies(
                schedule_id=schedule_id,
                item_name=item_name,
            )

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'routine_recovery',
                'schedule_id': schedule_id,
                'item_name': item_name,
                'tier': tier,
            }
        )

    # ── Domain alias map for conversation context matching ──
    _DOMAIN_ALIASES = {
        'faith': {
            'bible', 'scripture', 'reading', 'devotion', 'devotional', 'prayer',
            'praying', 'chapter', 'verse', 'psalm', 'proverbs', 'genesis',
            'exodus', 'matthew', 'mark', 'luke', 'john', 'acts', 'romans',
            'jonah', 'isaiah', 'revelation', 'faith', 'worship', 'church',
            'sermon', 'gospel', 'lord', 'god', 'jesus', 'spirit',
        },
        'health': {
            'workout', 'exercise', 'gym', 'run', 'running', 'fitness',
            'lifting', 'weights', 'cardio', 'walk', 'walking', 'steps',
            'stretch', 'yoga', 'training', 'pushup', 'squat',
        },
        'journal': {
            'journal', 'journaling', 'writing', 'reflect', 'reflection',
            'thoughts', 'diary', 'entry', 'gratitude',
        },
        'life': {
            'routine', 'morning', 'evening', 'meditation', 'meditate',
            'habit', 'schedule', 'task',
        },
    }

    def _check_recent_conversation_for_item(self, item: dict) -> bool:
        """
        Check if recent conversation suggests user was engaged with this item.

        Uses item title words + domain aliases for matching.
        Returns True if recent messages mention the item — affects wording ONLY,
        NEVER marks anything complete or changes data state.
        """
        from datetime import timedelta
        from django.utils import timezone

        try:
            from apps.ai.models import AssistantConversation, AssistantMessage
            conv = AssistantConversation.objects.filter(
                user=self.user, is_active=True
            ).order_by('-updated_at').first()
            if not conv:
                return False

            cutoff = timezone.now() - timedelta(minutes=30)
            recent_msgs = AssistantMessage.objects.filter(
                conversation=conv,
                created_at__gte=cutoff,
            ).order_by('-created_at')[:5]

            if not recent_msgs:
                return False

            # Build keyword set: item title words + domain aliases
            item_name = (item.get('title') or '').lower()
            keywords = {w for w in item_name.split() if len(w) > 2}

            # Add domain aliases
            item_domain = (item.get('domain') or '').lower()
            parent_title = (item.get('parent_title') or '').lower()
            for domain_key, aliases in self._DOMAIN_ALIASES.items():
                if (domain_key in item_domain
                        or domain_key in item_name
                        or domain_key in parent_title):
                    keywords.update(aliases)

            if not keywords:
                return False

            # Check message content for keyword matches
            for msg in recent_msgs:
                content_lower = (msg.content or '').lower()
                for kw in keywords:
                    if kw in content_lower:
                        return True

            return False
        except Exception:
            logger.debug("Error checking conversation context for nudge", exc_info=True)
            return False

    def generate_pre_nudge_check_in(
        self, item: dict, minutes_until_due: int,
    ) -> Optional[AssistantMessage]:
        """
        Generate a pre-nudge for an upcoming routine item (Stage 1).

        Fires 0-20 minutes before scheduled time. Gentle heads-up only.
        Dynamic phrasing based on distance:
        - 15-20 min → "coming up soon"
        - 5-14 min → "starts in X minutes"
        - ≤5 min → "starts in a few minutes"
        """
        schedule_id = item.get('source_id')
        item_name = item.get('title', 'routine item')

        throttle_key = f'pre_nudge_{schedule_id}'
        if not self.throttler.can_send(throttle_key, schedule_id):
            return None

        # Dynamic phrasing based on distance
        if minutes_until_due > 14:
            template = get_style_template(self.user, 'routine_pre_nudge_soon')
            message_content = template.format(item_name=item_name)
        elif minutes_until_due <= 5:
            template = get_style_template(self.user, 'routine_pre_nudge_imminent')
            message_content = template.format(item_name=item_name)
        else:
            template = get_style_template(self.user, 'routine_pre_nudge')
            message_content = template.format(
                item_name=item_name, minutes=minutes_until_due,
            )

        from apps.ai.quick_reply_handlers import generate_routine_recovery_replies
        quick_replies = generate_routine_recovery_replies(
            schedule_id=schedule_id,
            item_name=item_name,
        )

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'pre_nudge',
                'schedule_id': schedule_id,
                'item_name': item_name,
                'minutes_until_due': minutes_until_due,
            }
        )

    def generate_due_now_check_in(
        self, item: dict,
    ) -> Optional[AssistantMessage]:
        """
        Generate a due-now nudge for a routine item that just became due (Stage 2).

        Context-aware: if recent conversation suggests engagement, asks if completed
        instead of issuing a hard directive.
        """
        schedule_id = item.get('source_id')
        item_name = item.get('title', 'routine item')

        throttle_key = f'due_now_{schedule_id}'
        if not self.throttler.can_send(throttle_key, schedule_id):
            return None

        # Context-aware: check recent conversation before choosing template
        if self._check_recent_conversation_for_item(item):
            template_key = 'routine_ask_if_completed'
        else:
            template_key = 'routine_due_now'

        template = get_style_template(self.user, template_key)
        message_content = template.format(item_name=item_name)

        from apps.ai.quick_reply_handlers import generate_nudge_follow_up_replies
        quick_replies = generate_nudge_follow_up_replies(
            schedule_id=schedule_id,
            item_name=item_name,
        )

        return self._create_proactive_message(
            content=message_content,
            quick_replies=quick_replies,
            message_type='nudge',
            metadata={
                'check_in_type': 'due_now',
                'schedule_id': schedule_id,
                'item_name': item_name,
            }
        )

    # Check-in types that warrant immediate push delivery (high priority)
    _HIGH_PRIORITY_CHECKIN_TYPES = {'medicine', 'grouped_medicine'}
    # Check-in types that use standard delivery (lower priority)
    _STANDARD_CHECKIN_TYPES = {'workout', 'journal', 'overdue_task', 'busy_day',
                               'faith_reading', 'finance_budget', 'goal_deadline',
                               'relationship_drift', 'journal_concern',
                               'cdce_correlation', 'routine_recovery',
                               'pre_nudge', 'due_now'}

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

        # Suppress check-in if user has affirmed completion for this type.
        # Authority: user statement overrides system assumptions.
        check_in_type = (metadata or {}).get('check_in_type', '')
        if check_in_type:
            try:
                from .affirmation_detector import is_activity_affirmed
                if is_activity_affirmed(conversation, check_in_type):
                    logger.info(
                        "PROACTIVE_SUPPRESSED_AFFIRMED user=%s type=%s — "
                        "user affirmed completion in this conversation",
                        self.user.id, check_in_type,
                    )
                    return None
            except Exception:
                pass  # Suppression check must never block check-ins

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

        # ── Create PendingAction for entity-bearing check-ins ──
        # This bridges proactive check-ins to the confirmation pipeline so
        # natural language responses (not just button clicks) can resolve
        # back to the correct entity (task, medication, etc.).
        self._create_pending_action_for_checkin(message, metadata, quick_replies)

        # ── Route through DNE for push/SMS/email delivery ──
        check_in_type = (metadata or {}).get('check_in_type', '')
        self._route_through_dne(message, check_in_type, content)

        return message

    # ── Entity reference keys that indicate a check-in targets a specific record ──
    _ENTITY_KEYS = ('task_id', 'medication_id', 'med_id', 'goal_id', 'habit_id')

    # Map check_in_type → default intent_type for PendingAction
    _CHECKIN_INTENT_MAP = {
        'task_overdue': 'complete_task',
        'nn_skip_streak': 'complete_task',
        'medicine_reminder': 'log_medicine',
        'medicine_missed': 'log_medicine',
        'goal_deadline': 'update_goal',
    }

    def _create_pending_action_for_checkin(self, message, metadata, quick_replies):
        """
        Create a PendingAction when a proactive check-in references a specific entity.

        This bridges the proactive check-in flow to the confirmation pipeline so
        natural language responses (e.g., "B, 8:30am today") can resolve the entity
        via PendingAction instead of fragile title text-matching.

        Selection rule for multiple check-ins: latest pending wins (same strategy
        as the CRUD PendingAction pattern).
        """
        if not metadata:
            return

        # Detect entity reference in metadata
        entity_key = None
        entity_id = None
        for key in self._ENTITY_KEYS:
            if key in metadata and metadata[key]:
                entity_key = key
                entity_id = metadata[key]
                break

        if not entity_id:
            return  # No entity reference — nothing to bind

        check_in_type = metadata.get('check_in_type', '')
        intent_type = self._CHECKIN_INTENT_MAP.get(check_in_type, 'complete_task')

        try:
            import uuid as _uuid
            from datetime import timedelta as _td
            from django.core.cache import cache
            from apps.core.ai_governance.models import PendingAction

            action_id = str(_uuid.uuid4())
            expires_at = timezone.now() + _td(hours=4)

            # Build parameters with entity reference
            parameters = {
                entity_key: entity_id,
                'check_in_type': check_in_type,
                'proactive_message_id': message.id,
            }
            # Add task_title if available for display purposes
            if 'task_id' in metadata:
                parameters['task_title'] = metadata.get('task_title', '')

            # Map quick_replies to PendingAction options
            options = []
            for reply in (quick_replies or []):
                options.append({
                    'key': reply.get('id', ''),
                    'label': reply.get('label', ''),
                    'action': reply.get('action', ''),
                    'params': reply.get('params', {}),
                })

            # Dual-write: cache (fast lookup) + DB (durability)
            cache_key = f"pending_proactive_{self.user.id}"
            cache_data = {
                'action_id': action_id,
                'intent_type': intent_type,
                'parameters': parameters,
                'options': options,
                'check_in_type': check_in_type,
            }
            cache.set(cache_key, cache_data, timeout=4 * 3600)  # 4 hours

            PendingAction.objects.create(
                id=action_id,
                user=self.user,
                action_type='proactive_checkin',
                intent_type=intent_type,
                parameters=parameters,
                options=options,
                confirmation_message=message.content[:500],
                expires_at=expires_at,
            )

            # Store reference back in message metadata
            message.metadata['pending_action_id'] = action_id
            message.save(update_fields=['metadata'])

            logger.debug(
                "PROACTIVE_PENDING_ACTION user=%s action_id=%s entity=%s:%s type=%s",
                self.user.id, action_id, entity_key, entity_id, check_in_type,
            )

        except Exception as e:
            # PendingAction creation must never break proactive check-ins
            logger.error(
                "Failed to create PendingAction for proactive check-in "
                "user=%s: %s", self.user.id, e, exc_info=True,
            )

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

    # Get active medicines with prefetch_related to avoid N+1 on schedules
    medicines = Medicine.objects.filter(
        user=user, medicine_status='active',
    ).prefetch_related('medicineschedule_set')

    # Batch-load today's logs in a single query (eliminates N+1 per schedule)
    medicine_ids = [m.id for m in medicines]
    logged_keys = set()
    if medicine_ids:
        logs = MedicineLog.objects.filter(
            medicine_id__in=medicine_ids,
            scheduled_date=today,
            log_status__in=['taken', 'skipped'],
        ).values_list('medicine_id', 'scheduled_time')
        logged_keys = {(mid, st) for mid, st in logs}

    # Collect un-logged medicines grouped by time_of_day
    # Key: time_of_day (e.g., "morning") → list of (medicine, schedule) tuples
    pending_by_group = defaultdict(list)
    # Track the latest scheduled_time per group for "Remind me later"
    group_due_times = {}

    for medicine in medicines:
        # Use prefetched schedules (no additional query)
        schedules = [s for s in medicine.medicineschedule_set.all() if s.is_active]

        for schedule in schedules:
            if not schedule.applies_to_day(today.weekday()):
                continue

            scheduled_time = schedule.scheduled_time

            # Only check doses whose time has passed in user's LOCAL timezone
            if current_time < scheduled_time:
                continue

            # Check if already logged (in-memory from batch query)
            if (medicine.id, scheduled_time) in logged_keys:
                continue

            # Group by time_of_day (morning, evening, etc.)
            group_key = schedule.time_of_day or 'other'
            pending_by_group[group_key].append((medicine, schedule))

            # Track the due time for "Remind me later"
            if group_key not in group_due_times or scheduled_time > group_due_times[group_key]:
                group_due_times[group_key] = scheduled_time

    # Dedup cache: batch-loaded today's proactive messages
    dedup = _get_dedup_cache(user)

    # Generate ONE grouped check-in per time_of_day group
    for group_key, med_schedules in pending_by_group.items():
        if not med_schedules:
            continue

        # Check if we already sent a grouped check-in for this group today
        if dedup.already_sent('medicine_group', time_of_day=group_key):
            continue

        # Freshness check: re-verify at least one medicine is still untaken
        # (user may have logged since PGS started this cycle)
        still_pending = False
        for med, sched in med_schedules:
            fresh_log = MedicineLog.objects.filter(
                medicine=med,
                scheduled_date=today,
                scheduled_time=sched.scheduled_time,
                log_status__in=['taken', 'skipped'],
            ).exists()
            if not fresh_log:
                still_pending = True
                break
        if not still_pending:
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

    # Check if we already sent this type of check-in today (batch dedup)
    dedup = _get_dedup_cache(user)
    if dedup.already_sent(check_type):
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

    # Get the most overdue incomplete task (freshness: query at point of use)
    overdue_task = Task.objects.filter(
        user=user,
        due_date__lt=today,
        completion_status='pending',
        deleted_at__isnull=True,
    ).order_by('due_date').first()

    if overdue_task:
        # Freshness re-check: task may have been completed since query
        overdue_task.refresh_from_db(fields=['completion_status', 'deleted_at'])
        if overdue_task.completion_status == 'pending' and overdue_task.deleted_at is None:
            service.generate_overdue_task_check_in(overdue_task)


def generate_pre_nudge_check_ins_for_user(user):
    """
    Generate pre-nudge check-ins for upcoming routine items (Stage 1).

    Fires for foundational/important items due within the next 20 minutes.
    Gentle heads-up only — no implication of lateness.
    Dynamic phrasing: 15-20 min → "coming up soon", 5-14 → "in X minutes", ≤5 → imminent.
    Max 2 check-ins per run.
    """
    from apps.core.utils import get_user_now, classify_time_status
    from datetime import datetime as _dt

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    try:
        from apps.core.execution.today_execution import build_today_execution
        execution = build_today_execution(user)
    except Exception:
        logger.exception("Failed to build execution for pre-nudge check-ins")
        return

    items = execution.get('items', [])
    if not items:
        return

    user_now = get_user_now(user)
    user_today = user_now.date()

    # Filter: upcoming routine items that are foundational/important
    candidates = []
    for item in items:
        if (item.get('source_type') != 'routine_item'
                or not item.get('is_actionable', False)
                or item.get('time_status') != 'upcoming'
                or item.get('importance') not in ('foundational', 'important')):
            continue

        # Re-derive minutes until due
        sched_time_str = item.get('scheduled_time')
        if not sched_time_str:
            continue
        try:
            sched_time_obj = _dt.strptime(sched_time_str, '%H:%M').time()
        except (ValueError, AttributeError):
            continue

        ts = classify_time_status(user_today, sched_time_obj, user_now, grace_minutes=0)
        minutes_until = ts.get('minutes_until_due')
        if minutes_until is not None and 0 < minutes_until <= 20:
            candidates.append((item, minutes_until))

    if not candidates:
        return

    service = get_proactive_service(user)
    generated = 0
    for item, minutes_until in candidates:
        result = service.generate_pre_nudge_check_in(item, minutes_until)
        if result:
            generated += 1
            if generated >= 2:
                break


def generate_due_now_check_ins_for_user(user):
    """
    Generate due-now check-ins for routine items that just became due (Stage 2).

    Fires for items 0-10 minutes past scheduled time (recently overdue).
    Context-aware: checks recent conversation before choosing directive vs ask tone.
    Max 2 check-ins per run.
    """
    from apps.core.utils import get_user_now, classify_time_status
    from datetime import datetime as _dt

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    try:
        from apps.core.execution.today_execution import build_today_execution
        execution = build_today_execution(user)
    except Exception:
        logger.exception("Failed to build execution for due-now check-ins")
        return

    items = execution.get('items', [])
    if not items:
        return

    user_now = get_user_now(user)
    user_today = user_now.date()

    resolved_statuses = {'completed', 'completed_late', 'skipped', 'rescheduled'}
    candidates = []
    for item in items:
        if (item.get('source_type') != 'routine_item'
                or not item.get('is_actionable', False)
                or item.get('time_status') != 'overdue'
                or item.get('completion_status') in resolved_statuses
                or item.get('importance') not in ('foundational', 'important')):
            continue

        # Re-derive to check how recently it became overdue
        sched_time_str = item.get('scheduled_time')
        if not sched_time_str:
            continue
        try:
            sched_time_obj = _dt.strptime(sched_time_str, '%H:%M').time()
        except (ValueError, AttributeError):
            continue

        ts = classify_time_status(user_today, sched_time_obj, user_now, grace_minutes=0)
        minutes_past = ts.get('minutes_past_due')
        if minutes_past is not None and 0 <= minutes_past <= 10:
            candidates.append(item)

    if not candidates:
        return

    service = get_proactive_service(user)
    generated = 0
    for item in candidates:
        result = service.generate_due_now_check_in(item)
        if result:
            generated += 1
            if generated >= 2:
                break


def generate_routine_recovery_check_ins_for_user(user):
    """
    Generate proactive check-ins for missed/overdue routine items (Stage 3).

    Reads from execution contract (single source of truth).
    Filters: routine items that are actionable + overdue + not completed/skipped,
    with foundational or important importance.

    Context-aware: if recent conversation suggests engagement, asks if completed
    instead of assuming a miss.

    Escalation tiers by user's local hour:
    - Tier 1 (any hour post-grace): Window passed, offer reschedule
    - Tier 2 (10-14): Still outstanding midday
    - Tier 3 (16-20): Last chance before day close

    Max 2 check-ins per run to avoid overwhelming.
    """
    from apps.core.utils import get_user_now, classify_time_status
    from datetime import datetime as _dt

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    try:
        from apps.core.execution.today_execution import build_today_execution
        execution = build_today_execution(user)
    except Exception:
        logger.exception("Failed to build execution for routine recovery check-ins")
        return

    items = execution.get('items', [])
    if not items:
        return

    user_now = get_user_now(user)
    user_today = user_now.date()

    # Filter: routine items that are overdue, actionable, not resolved
    # Per user correction: do NOT depend on 'missed' status — use actionable + overdue
    # Stop nudging if: completed, skipped, OR already rescheduled (user engaged)
    # Exclude items ≤10 min overdue — those are handled by due_now generator
    resolved_statuses = {'completed', 'completed_late', 'skipped', 'rescheduled'}
    candidates = []
    for item in items:
        if (item.get('source_type') != 'routine_item'
                or not item.get('is_actionable', False)
                or item.get('time_status') != 'overdue'
                or item.get('completion_status') in resolved_statuses
                or item.get('importance') not in ('foundational', 'important')):
            continue
        # Exclude recently-overdue items (handled by due_now generator)
        sched_time_str = item.get('scheduled_time')
        if sched_time_str:
            try:
                sched_time_obj = _dt.strptime(sched_time_str, '%H:%M').time()
                ts = classify_time_status(user_today, sched_time_obj, user_now, grace_minutes=0)
                minutes_past = ts.get('minutes_past_due')
                if minutes_past is not None and minutes_past <= 10:
                    continue  # Let due_now handle this
            except (ValueError, AttributeError):
                pass
        candidates.append(item)

    if not candidates:
        return

    # Determine escalation tier from user's local hour
    hour = user_now.hour

    if 16 <= hour <= 20:
        tier = 'tier3'
    elif 10 <= hour <= 14:
        tier = 'tier2'
    else:
        tier = 'tier1'

    service = get_proactive_service(user)
    generated = 0
    for item in candidates:
        result = service.generate_routine_recovery_check_in(item, tier)
        if result:
            generated += 1
            if generated >= 2:
                break


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
        completion_status='pending',
        deleted_at__isnull=True,
    ).count()

    events = CalendarEvent.objects.filter(
        user=user,
        start_dt__date=tomorrow,
        deleted_at__isnull=True,
    ).exclude(status=CalendarEvent.STATUS_CANCELED).count()

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

    dedup = _get_dedup_cache(user)
    for event in events:
        if not dedup.already_sent('birthday', event_id=event.id):
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

        dedup = _get_dedup_cache(user)
        for plan in active_plans:
            # Check if today's reading is done
            today_done = UserReadingProgress.objects.filter(
                user_plan=plan,
                reading_day__day_number=plan.current_day,
                is_completed=True,
            ).exists()

            if not today_done:
                if not dedup.already_sent('faith_reading', plan_id=plan.id):
                    service.generate_faith_reading_check_in(plan)
                    break  # Only one reading plan nudge per run

    except ImportError:
        pass
    except Exception as e:
        logger.warning("Faith reading check-in error: %s", e, exc_info=True)

    # 2. Prayer request reminders — use FaithMetricsService for active count
    try:
        from apps.faith.models import PrayerRequest

        # Daily-reminder prayers need the remind_daily flag check which
        # is not in the generic FaithMetricsService (it tracks all active).
        # This is an intentionally specific query.
        daily_prayers = PrayerRequest.objects.filter(
            user=user,
            remind_daily=True,
            is_answered=False,
            deleted_at__isnull=True,
        ).count()

        if daily_prayers > 0:
            dedup = _get_dedup_cache(user)
            if not dedup.already_sent('faith_prayer'):
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
                dedup = _get_dedup_cache(user)
                if not dedup.already_sent('finance_budget', budget_id=budget.id):
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
                dedup = _get_dedup_cache(user)
                if not dedup.already_sent('finance_goal', goal_id=goal.id):
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

        dedup = _get_dedup_cache(user)
        for alert in alerts[:2]:  # Max 2 per run
            if not dedup.already_sent('relationship_drift', person_id=alert['person_id']):
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
    dedup = _get_dedup_cache(user)

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
            if not dedup.already_sent('goal_deadline', goal_id=goal.id):
                service.generate_goal_deadline_check_in(goal, days_until)

    except ImportError:
        pass
    except Exception as e:
        logger.warning("Goal deadline check-in error: %s", e, exc_info=True)

    # 2. Goal stalling — batch milestone lookup (eliminates N+1)
    try:
        from apps.purpose.models import LifeGoal, GoalMilestone
        from django.db.models import Max

        active_goals = list(LifeGoal.objects.filter(
            user=user, status='active',
        ))

        if active_goals:
            # Single query: latest milestone date per goal
            goal_ids = [g.id for g in active_goals]
            latest_milestones = dict(
                GoalMilestone.objects.filter(
                    goal_id__in=goal_ids,
                ).values('goal_id').annotate(
                    latest=Max('updated_at'),
                ).values_list('goal_id', 'latest')
            )

            for goal in active_goals:
                last_update = latest_milestones.get(goal.id)
                if last_update:
                    days_stalled = (today - last_update.date()).days
                else:
                    days_stalled = (today - goal.created_at.date()).days if goal.created_at else 0

                if days_stalled > 30:
                    if not dedup.already_sent('goal_stalling', goal_id=goal.id):
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
                continue

            if streak == 0:
                # Check if there was a streak that just broke
                from apps.purpose.models import HabitEntry
                recent_completions = HabitEntry.objects.filter(
                    goal=habit,
                    date__gte=today - timedelta(days=7),
                    date__lt=today,
                    completed=True,
                ).count()

                if recent_completions >= 3:
                    if not dedup.already_sent('habit_streak', habit_id=habit.id):
                        service.generate_habit_streak_check_in(
                            habit, streak=recent_completions, is_break=True,
                        )

            elif streak in (7, 14, 21, 30, 60, 90):
                if not dedup.already_sent('habit_streak', habit_id=habit.id):
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
    dedup = _get_dedup_cache(user)

    # 1. Recurring concerns
    try:
        from apps.journal.services.content_intelligence import detect_recurring_concerns

        concerns = detect_recurring_concerns(user, days=14, min_occurrences=3)

        if concerns:
            top_concern = concerns[0]
            if not dedup.already_sent('journal_concern'):
                service.generate_journal_concern_check_in(
                    concern=top_concern['term'],
                    entry_count=top_concern['entries'],
                )

    except ImportError:
        pass
    except Exception as e:
        logger.warning("Journal concern check-in error: %s", e, exc_info=True)

    # 2. Extended journal gap — use canonical JournalMetricsService
    try:
        from apps.journal.services.metrics import get_journal_metrics
        j_metrics = get_journal_metrics(user)
        last_date = j_metrics.get('last_journal_date')

        if last_date:
            days_since = (today - last_date).days
            if days_since >= 3:
                if not dedup.already_sent('journal_gap'):
                    service.generate_journal_gap_check_in(days_since)

    except ImportError:
        pass
    except Exception as e:
        logger.warning("Journal gap check-in error: %s", e, exc_info=True)


def generate_cdce_correlation_check_ins_for_user(user):
    """
    Phase 7.2: Generate proactive check-ins from CDCE cross-domain correlations.

    Surfaces strong/moderate correlations as actionable insights once per
    correlation type per day. Only fires for correlations with strength ≥ moderate.
    """
    from apps.core.utils import get_user_today

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    service = get_proactive_service(user)
    today = get_user_today(user)

    try:
        from apps.core.ai_cross_domain.models import DomainCorrelation

        # Get active, strong/moderate correlations
        correlations = DomainCorrelation.objects.filter(
            user=user,
            status='active',
            strength__in=['strong', 'moderate'],
        ).order_by('-strength_score')[:5]

        dedup = _get_dedup_cache(user)
        for corr in correlations:
            if not dedup.already_sent('cdce_correlation', correlation_type=corr.correlation_type):
                service.generate_cdce_correlation_check_in(
                    correlation_type=corr.correlation_type,
                    narrative=corr.narrative,
                    strength=corr.strength,
                    domains=[corr.domain_a, corr.domain_b],
                )
                # Only surface one correlation per run to avoid overload
                break

    except ImportError:
        pass
    except Exception as e:
        logger.warning("CDCE correlation check-in error: %s", e, exc_info=True)


# =============================================================================
# PROACTIVE GUIDANCE SCHEDULER (PGS)
# =============================================================================
# ISE-scheduled runner that dispatches proactive check-ins based on each
# user's local time window. Replaces the orphaned generate_health_reminders
# management command with proper ISE integration and full generator coverage.
# =============================================================================

# Time window ranges (user-local hour). Quiet hours = no proactive messages.
WINDOW_MORNING = range(7, 10)      # 7:00–9:59
WINDOW_MIDDAY = range(10, 13)      # 10:00–12:59
WINDOW_AFTERNOON = range(13, 17)   # 13:00–16:59
WINDOW_EVENING = range(17, 22)     # 17:00–21:59


def _get_proactive_users():
    """
    Query users eligible for proactive check-ins.

    Requirements:
    - Active account
    - Personal Assistant enabled + consent
    - AI enabled + consent
    - Proactive check-ins master switch on
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    return User.objects.filter(
        is_active=True,
        preferences__personal_assistant_enabled=True,
        preferences__personal_assistant_consent=True,
        preferences__ai_enabled=True,
        preferences__ai_data_consent=True,
        preferences__assistant_proactive_checkins=True,
    ).select_related('preferences')


# -----------------------------------------------------------------------------
# Daily Rhythm Generators
# -----------------------------------------------------------------------------

def generate_midday_alignment_for_user(user):
    """
    Midday alignment check-in (10–12, weekdays only).

    Structured progress snapshot using execution truth and today engine.
    Includes: completed/total, slipping items, and current next action.
    """
    from apps.core.utils import get_user_today, get_user_now

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    today = get_user_today(user)

    # Dedup: already sent today? (batch cache)
    dedup = _get_dedup_cache(user)
    if dedup.already_sent('midday_alignment'):
        return

    # Use execution truth (single source) instead of raw Task queries
    try:
        from apps.core.execution.execution_truth_engine import (
            get_execution_truth,
        )
        truth = get_execution_truth(user)
    except Exception:
        return  # Can't build alignment without truth

    routines = truth.get('routines', {})
    tasks = truth.get('tasks', {})

    r_done = routines.get('completed', 0)
    r_total = routines.get('total', 0)
    t_done = tasks.get('completed', 0)
    t_total = tasks.get('total', 0)

    total_done = r_done + t_done
    total = r_total + t_total

    if total == 0:
        return  # Nothing scheduled

    # Slipping items from today engine
    slipping_count = 0
    next_action = ''
    try:
        from apps.core.today.today_engine import get_today_context
        today_ctx = get_today_context(user)
        overdue = today_ctx.get('overdue', [])
        slipping_count = len(overdue)
        next_action = today_ctx.get('next', '')
    except Exception:
        pass

    # Build structured message
    parts = [f"Midday: {total_done}/{total} done"]
    if slipping_count:
        parts.append(f"{slipping_count} slipping")
    if next_action:
        parts.append(f"Next: {next_action}")
    message = ". ".join(parts) + "."

    service = get_proactive_service(user)
    service._create_proactive_message(
        content=message,
        quick_replies=[],
        message_type='nudge',
        metadata={
            'check_in_type': 'midday_alignment',
            'completed': total_done,
            'total': total,
            'slipping': slipping_count,
            'next_action': next_action,
        },
    )


def generate_afternoon_momentum_for_user(user):
    """
    Afternoon momentum check-in (13–16, weekdays only).

    Surfaces non-negotiable tasks still pending for today.
    """
    from apps.core.utils import get_user_today
    from apps.life.models import Task

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    today = get_user_today(user)

    # Dedup (batch cache)
    dedup = _get_dedup_cache(user)
    if dedup.already_sent('afternoon_momentum'):
        return

    # Non-negotiable tasks still pending
    nn_pending = Task.objects.filter(
        user=user,
        due_date=today,
        completion_status='pending',
        commitment_level='non_negotiable',
        deleted_at__isnull=True,
    )

    nn_list = list(nn_pending[:3])
    if not nn_list:
        return

    if len(nn_list) == 1:
        message = f"'{nn_list[0].title}' is still on today's list. Afternoon's a good window."
    else:
        message = f"{len(nn_list)} non-negotiables still pending today."

    service = get_proactive_service(user)
    quick_replies = []
    if len(nn_list) == 1:
        quick_replies = generate_task_check_in_replies(nn_list[0].id, nn_list[0].title)

    service._create_proactive_message(
        content=message,
        quick_replies=quick_replies,
        message_type='nudge',
        metadata={
            'check_in_type': 'afternoon_momentum',
            'nn_count': len(nn_list),
        },
    )


def generate_evening_wrap_for_user(user):
    """
    Evening wrap-up check-in (17–21, every day).

    Structured debrief using execution truth: completed vs expected,
    explicit misses (routine items not done), medication adherence,
    and tomorrow's load.
    """
    from apps.core.utils import get_user_today
    from apps.life.models import Task

    prefs = user.preferences
    if not getattr(prefs, 'assistant_proactive_checkins', True):
        return

    today = get_user_today(user)
    tomorrow = today + timedelta(days=1)

    # Dedup (batch cache)
    dedup = _get_dedup_cache(user)
    if dedup.already_sent('evening_wrap'):
        return

    # Use execution truth for accurate completed-vs-expected
    try:
        from apps.core.execution.execution_truth_engine import (
            get_execution_truth,
        )
        truth = get_execution_truth(user)
    except Exception:
        return  # Can't build debrief without truth

    routines = truth.get('routines', {})
    tasks = truth.get('tasks', {})
    meds = truth.get('medications', {})

    r_done = routines.get('completed', 0)
    r_total = routines.get('total', 0)
    t_done = tasks.get('completed', 0)
    t_total = tasks.get('total', 0)

    total_done = r_done + t_done
    total_expected = r_total + t_total

    # Explicit misses — routine items not completed (named, not just counted)
    missed_items = [
        name for name, info in routines.get('items', {}).items()
        if not info.get('fully_complete')
    ]

    # Medication adherence
    med_taken = meds.get('taken', 0)
    med_expected = meds.get('expected', 0)

    # Tomorrow's load (lightweight query)
    tomorrow_load = Task.objects.filter(
        user=user, due_date=tomorrow, deleted_at__isnull=True,
    ).exclude(completion_status='skipped').count()

    if total_expected == 0 and tomorrow_load == 0:
        return

    # Build structured debrief message
    parts = []
    if total_expected > 0:
        parts.append(f"Day closing: {total_done}/{total_expected} completed")
    if missed_items:
        missed_str = ', '.join(missed_items[:3])
        if len(missed_items) > 3:
            missed_str += f' +{len(missed_items) - 3} more'
        parts.append(f"Missed: {missed_str}")
    if med_expected > 0 and med_taken < med_expected:
        parts.append(f"Meds: {med_taken}/{med_expected}")
    if tomorrow_load:
        parts.append(
            f"{tomorrow_load} item{'s' if tomorrow_load != 1 else ''} "
            f"tomorrow"
        )
    message = ". ".join(parts) + "."

    service = get_proactive_service(user)
    service._create_proactive_message(
        content=message,
        quick_replies=[],
        message_type='nudge',
        metadata={
            'check_in_type': 'evening_wrap',
            'completed': total_done,
            'expected': total_expected,
            'missed_items': missed_items[:5],
            'meds_taken': med_taken,
            'meds_expected': med_expected,
            'tomorrow': tomorrow_load,
        },
    )


# -----------------------------------------------------------------------------
# Nudge Candidate Collection & Scoring (Steps 2-4, 6)
# -----------------------------------------------------------------------------

# Maximum routine nudges per PGS cycle (prevents noise/stacking)
_MAX_ROUTINE_NUDGES_PER_CYCLE = 2

# Per-user cooldown: no new routine nudge within this many minutes of the last one
_NUDGE_COOLDOWN_MINUTES = 5

# Dedup windows by stage type (minutes) — prevents re-sending same item+stage
_NUDGE_DEDUP_WINDOWS = {
    'pre_nudge': 20,
    'due_now': 20,
    'routine_recovery': 60,
}

# Assertiveness multipliers — adjust scoring intensity and cooldown timing
# based on user preference (UserPreferences.assistant_assertiveness).
_ASSERTIVENESS_MULTIPLIERS = {
    'gentle':          {'score': 0.7, 'cooldown': 1.5},
    'firm_respectful': {'score': 1.0, 'cooldown': 1.0},
    'direct':          {'score': 1.3, 'cooldown': 0.7},
}

# Base scores by stage for prioritization
_STAGE_BASE_SCORES = {
    'due_now': 100,
    'routine_recovery': 80,
    'pre_nudge': 60,
}


def _collect_escalation_candidates(user):
    """
    Collect ALL routine escalation candidates (pre-nudge, due-now, recovery)
    in a single pass over the execution contract.

    Returns list of dicts:
        [{item, stage, score, minutes_until, minutes_past, tier}, ...]

    Does NOT create messages — just identifies and scores candidates.
    """
    from apps.core.utils import get_user_now, classify_time_status
    from datetime import datetime as _dt

    try:
        from apps.core.execution.today_execution import build_today_execution
        execution = build_today_execution(user)
    except Exception:
        logger.exception("Failed to build execution for escalation candidates")
        return []

    items = execution.get('items', [])
    if not items:
        return []

    user_now = get_user_now(user)
    user_today = user_now.date()
    hour = user_now.hour

    resolved_statuses = {'completed', 'completed_late', 'skipped', 'rescheduled'}
    candidates = []

    for item in items:
        if (item.get('source_type') != 'routine_item'
                or not item.get('is_actionable', False)
                or item.get('importance') not in ('foundational', 'important')
                or item.get('completion_status') in resolved_statuses):
            continue

        sched_time_str = item.get('scheduled_time')
        if not sched_time_str:
            continue
        try:
            sched_time_obj = _dt.strptime(sched_time_str, '%H:%M').time()
        except (ValueError, AttributeError):
            continue

        ts = classify_time_status(user_today, sched_time_obj, user_now, grace_minutes=0)
        minutes_until = ts.get('minutes_until_due')
        minutes_past = ts.get('minutes_past_due')

        stage = None
        tier = None

        # Determine stage
        if minutes_until is not None and 0 < minutes_until <= 20:
            stage = 'pre_nudge'
        elif minutes_past is not None and 0 <= minutes_past <= 10:
            stage = 'due_now'
        elif minutes_past is not None and minutes_past > 10:
            stage = 'routine_recovery'
            # Determine recovery tier by hour
            if 16 <= hour <= 20:
                tier = 'tier3'
            elif 10 <= hour <= 14:
                tier = 'tier2'
            else:
                tier = 'tier1'

        if not stage:
            continue

        # Score the candidate
        score = _score_nudge_candidate(item, stage, user)

        candidates.append({
            'item': item,
            'stage': stage,
            'score': score,
            'minutes_until': minutes_until,
            'minutes_past': minutes_past,
            'tier': tier,
        })

    # Sort by score descending
    candidates.sort(key=lambda c: c['score'], reverse=True)
    return candidates


def _score_nudge_candidate(item, stage, user):
    """
    Score a nudge candidate for prioritization.

    Base scoring:
    - due_now → 100, recovery → 80, pre_nudge → 60

    Adjustments:
    - +20 if importance == 'foundational'
    - +10 if time-sensitive (has scheduled_time)
    - -15 if similar nudge sent recently (same item, any stage, last 30 min)
    """
    score = _STAGE_BASE_SCORES.get(stage, 50)

    if item.get('importance') == 'foundational':
        score += 20
    if item.get('scheduled_time'):
        score += 10

    # Penalty if recently nudged (same item, any stage)
    schedule_id = item.get('source_id')
    if schedule_id and _was_recently_nudged(user, schedule_id, minutes=30):
        score -= 15

    # Apply assertiveness multiplier from user preference
    assertiveness = getattr(
        getattr(user, 'preferences', None),
        'assistant_assertiveness', 'firm_respectful',
    )
    mult = _ASSERTIVENESS_MULTIPLIERS.get(
        assertiveness, _ASSERTIVENESS_MULTIPLIERS['firm_respectful'],
    )
    score = int(score * mult['score'])

    return score


def _was_recently_nudged(user, schedule_id, minutes=30):
    """
    Check if a nudge was recently sent for this schedule item.

    Uses the existing dedup cache (thread-local) for fast lookup.
    Falls back to DB query if cache not available.
    """
    dedup = getattr(_dedup_local, 'cache', None)
    if dedup is not None:
        # Check all escalation stage types
        for stage_type in ('pre_nudge', 'due_now', 'routine_recovery'):
            if dedup.already_sent(stage_type, schedule_id=schedule_id):
                return True
        return False

    # Fallback: DB check for recent nudges (within N minutes)
    cutoff = timezone.now() - timedelta(minutes=minutes)
    return AssistantMessage.objects.filter(
        conversation__user=user,
        is_proactive=True,
        metadata__schedule_id=schedule_id,
        metadata__check_in_type__in=['pre_nudge', 'due_now', 'routine_recovery'],
        created_at__gte=cutoff,
    ).exists()


def _get_current_focus_source_id(user):
    """
    Get the source_id of the user's current focus item from action priorities.

    Returns None if unavailable (graceful degradation).
    """
    try:
        from apps.core.execution.today_execution import build_today_execution
        execution = build_today_execution(user)
        items = execution.get('items', [])
        # Current focus = first actionable, non-completed item sorted by priority
        for item in items:
            if (item.get('is_actionable', False)
                    and item.get('completion_status') not in (
                        'completed', 'completed_late', 'skipped', 'rescheduled')
                    and item.get('time_status') in ('overdue', 'upcoming')):
                return item.get('source_id')
    except Exception:
        pass
    return None


def _check_user_nudge_cooldown(user, cooldown_minutes=None):
    """
    Check if user is in nudge cooldown (a routine nudge was sent recently).

    Uses existing dedup cache data when available, falls back to DB.
    Returns True if in cooldown (should NOT send), False if clear.
    """
    if cooldown_minutes is None:
        cooldown_minutes = _NUDGE_COOLDOWN_MINUTES

    cutoff = timezone.now() - timedelta(minutes=cooldown_minutes)
    return AssistantMessage.objects.filter(
        conversation__user=user,
        is_proactive=True,
        metadata__check_in_type__in=['pre_nudge', 'due_now', 'routine_recovery'],
        created_at__gte=cutoff,
    ).exists()


def _send_prioritized_nudges(user, candidates):
    """
    Send the top-priority nudge candidates, respecting limits and cooldown.

    Args:
        user: The user
        candidates: Pre-sorted list of candidate dicts from _collect_escalation_candidates

    Returns:
        int — number of nudges actually sent
    """
    if not candidates:
        return 0

    # Cooldown check: skip if a routine nudge was sent very recently
    # Assertiveness adjusts cooldown: gentle = 1.5x, direct = 0.7x
    _assertiveness = getattr(
        getattr(user, 'preferences', None),
        'assistant_assertiveness', 'firm_respectful',
    )
    _cool_mult = _ASSERTIVENESS_MULTIPLIERS.get(
        _assertiveness, _ASSERTIVENESS_MULTIPLIERS['firm_respectful'],
    ).get('cooldown', 1.0)
    _effective_cooldown = int(_NUDGE_COOLDOWN_MINUTES * _cool_mult)
    if _check_user_nudge_cooldown(user, cooldown_minutes=_effective_cooldown):
        logger.debug(
            "PGS_COOLDOWN user=%s — routine nudge sent within last %d min "
            "(assertiveness=%s), skipping",
            user.pk, _effective_cooldown, _assertiveness,
        )
        return 0

    # Current focus alignment: get the user's top-priority item
    focus_source_id = _get_current_focus_source_id(user)

    service = get_proactive_service(user)
    sent = 0

    for candidate in candidates:
        if sent >= _MAX_ROUTINE_NUDGES_PER_CYCLE:
            break

        item = candidate['item']
        stage = candidate['stage']
        schedule_id = item.get('source_id')

        # Focus alignment: suppress non-focus nudges unless higher urgency
        if focus_source_id and schedule_id != focus_source_id:
            # Only allow if this candidate is due_now (urgent)
            # or if focus item is not time-sensitive
            if stage == 'pre_nudge':
                logger.debug(
                    "PGS_FOCUS_SUPPRESS user=%s item=%s stage=%s — "
                    "not current focus, suppressing pre-nudge",
                    user.pk, schedule_id, stage,
                )
                continue

        # Send based on stage
        result = None
        if stage == 'pre_nudge':
            minutes_until = candidate.get('minutes_until', 10)
            result = service.generate_pre_nudge_check_in(item, minutes_until)
        elif stage == 'due_now':
            result = service.generate_due_now_check_in(item)
        elif stage == 'routine_recovery':
            tier = candidate.get('tier', 'tier1')
            result = service.generate_routine_recovery_check_in(item, tier)

        if result:
            sent += 1

    return sent


# -----------------------------------------------------------------------------
# Time Window Dispatch
# -----------------------------------------------------------------------------

def _dispatch_for_window(user, prefs, hour, is_weekend):
    """
    Call the appropriate generators for the user's current time window.

    Routine escalation nudges (pre-nudge, due-now, recovery) are collected,
    scored, and prioritized before sending — max 2 per cycle. Other
    domain-specific generators run independently.

    Returns the number of generator invocations attempted.
    """
    count = 0

    # --- Always active (any non-quiet hour) ---
    if getattr(prefs, 'health_enabled', False):
        generate_medicine_check_ins_for_user(user)
        count += 1

    # ── Prioritized escalation ladder (collect → score → send top N) ──
    candidates = _collect_escalation_candidates(user)
    nudges_sent = _send_prioritized_nudges(user, candidates)
    count += 1  # Count as one coordinated dispatch
    if nudges_sent:
        logger.debug(
            "PGS_ESCALATION user=%s sent=%d candidates=%d",
            user.pk, nudges_sent, len(candidates),
        )

    # --- Morning 7–9 ---
    if hour in WINDOW_MORNING:
        generate_birthday_check_ins_for_user(user)
        count += 1

        if getattr(prefs, 'faith_enabled', False):
            generate_faith_check_ins_for_user(user)
            count += 1

    # --- Midday 10–12 ---
    elif hour in WINDOW_MIDDAY:
        if getattr(prefs, 'health_enabled', False):
            generate_daily_check_ins_for_user(user, 'workout')
            count += 1

        generate_overdue_task_check_ins_for_user(user)
        count += 1

        generate_nn_skip_check_ins_for_user(user)
        count += 1

        if not is_weekend:
            generate_midday_alignment_for_user(user)
            count += 1

    # --- Afternoon 13–16 ---
    elif hour in WINDOW_AFTERNOON:
        generate_goal_check_ins_for_user(user)
        count += 1

        if getattr(prefs, 'journal_enabled', False):
            generate_journal_intelligence_check_ins_for_user(user)
            count += 1

        if getattr(prefs, 'health_enabled', False):
            generate_pattern_check_ins_for_user(user)
            count += 1

        if getattr(prefs, 'finances_enabled', False):
            generate_finance_check_ins_for_user(user)
            count += 1

        if not is_weekend:
            generate_afternoon_momentum_for_user(user)
            count += 1

    # --- Evening 17–21 ---
    elif hour in WINDOW_EVENING:
        if getattr(prefs, 'journal_enabled', False):
            generate_daily_check_ins_for_user(user, 'journal')
            count += 1

        generate_busy_day_check_ins_for_user(user)
        count += 1

        generate_relationship_check_ins_for_user(user)
        count += 1

        generate_evening_wrap_for_user(user)
        count += 1

    # Quiet hours (<7 or >=22): no proactive messages

    return count


# -----------------------------------------------------------------------------
# ISE Runner
# -----------------------------------------------------------------------------

def run_proactive_guidance_scheduler():
    """
    ISE runner: dispatch proactive check-ins based on per-user time windows.

    Called every 15 minutes by ISE. Each invocation:
    1. Queries eligible users
    2. Determines each user's local hour and weekend status
    3. Calls the appropriate generators for their time window

    All generators handle their own dedup and throttling internally.

    Returns:
        dict — metrics for EngineRun telemetry.
    """
    from apps.core.ai_observability.trace import trace_context
    from apps.core.utils import get_user_now, get_user_today

    with trace_context(source="scheduler"):
        users = _get_proactive_users()
        users_processed = 0
        check_ins_attempted = 0
        errors = 0
        dedup_queries_saved = 0

        for user in users:
            try:
                user_now = get_user_now(user)
                hour = user_now.hour
                is_weekend = user_now.weekday() >= 5

                # Skip quiet hours
                if hour < 7 or hour >= 22:
                    continue

                prefs = user.preferences

                # Pre-load dedup cache: 1 query replaces 20-30 per-generator queries
                today = get_user_today(user)
                user_dedup = _ProactiveDedupCache(user, today)
                user_dedup._load()  # Force immediate load
                _dedup_local.cache = user_dedup

                try:
                    attempted = _dispatch_for_window(user, prefs, hour, is_weekend)
                    check_ins_attempted += attempted
                    users_processed += 1
                finally:
                    _dedup_local.cache = None  # Clean up thread-local

            except Exception as e:
                errors += 1
                logger.warning(
                    "PGS: check-in dispatch failed for user %s: %s",
                    user.pk, e, exc_info=True,
                )

        logger.info(
            "PGS: processed %d users, %d generators called, %d errors",
            users_processed, check_ins_attempted, errors,
        )

        return {
            "users_processed": users_processed,
            "check_ins_attempted": check_ins_attempted,
            "errors": errors,
        }
