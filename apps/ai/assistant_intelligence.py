# ==============================================================================
# File: apps/ai/assistant_intelligence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Core intelligence layer for the My Assistant feature
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-05
# ==============================================================================
"""
Assistant Intelligence Layer

The brain of the "My Assistant" feature. Continuously monitors user data across
all WLJ modules to provide awareness + alignment, not advice.

Core Philosophy:
- Behaves like a highly attentive, human-like right-hand assistant
- Not a cheerleader, not a therapist, not a medical advisor
- Calm, observant, factual, proactive, and efficient
- Short messages (1-2 sentences max)
- Acknowledges completion briefly ("Medications complete." not "Great job!")

Trigger Types:
1. MISSED/OVERDUE: Medications, tasks, planned routines
2. PATTERN RECOGNITION: Factual correlations only (no medical advice)
3. HEALTH CONTEXT: Remind why something exists using their data
4. PLANNING SUPPORT: Busy days, goal drift
5. QUICK RECOGNITION: Brief acknowledgment of completion

Key Question: "Is this helpful right now?" If not, don't interrupt.
"""

import logging
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import Avg, Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# COACHING STYLE TEMPLATES
# =============================================================================

COACHING_STYLE_TEMPLATES = {
    'default': {
        'missed_med': "Your {time} {medicine} wasn't marked. Did you take it, or should I mark it skipped?",
        'missed_med_with_context': "Your {time} {medicine} wasn't marked. Your last labs showed {context}.",
        'grouped_meds_due': "Your {group} meds are due by {time}.",
        'overdue_task': "'{task}' is overdue. Still on your plate, or should we reschedule?",
        'workout_check': "No workout logged today. Did you get one in?",
        'journal_check': "No journal entry today. Want to log one?",
        'busy_day': "Tomorrow looks packed with {count} items. Want to prioritize anything?",
        'pattern_positive': "Your {metric} tends to be better on days you {activity}.",
        'pattern_negative': "Higher {metric} readings on days when {trigger} is logged.",
        'streak_note': "{count} days in a row. Noted.",
        'completion': "{item} complete.",
        'correlation': "I'm noticing {observation}.",
    },
    'southern_belle': {
        'missed_med': "Sugar, looks like your {time} {medicine} wasn't marked yet. Did you take it, or want me to mark it skipped?",
        'missed_med_with_context': "Darlin', your {time} {medicine} wasn't marked. Remember, your last labs showed {context}.",
        'grouped_meds_due': "Mornin'! Your {group} meds are due by {time}, hon.",
        'overdue_task': "'{task}' is waitin' on you, hon. Still need to do it, or should we push it out?",
        'workout_check': "Haven't seen a workout logged today, sweetie. Did you get movin'?",
        'journal_check': "No journal entry today, dear. Want to jot something down?",
        'busy_day': "Bless your heart, tomorrow's lookin' busy with {count} things. Want to sort through 'em?",
        'pattern_positive': "Well now, your {metric} seems happier on days you {activity}.",
        'pattern_negative': "I've noticed your {metric} runs a bit high when {trigger} shows up.",
        'streak_note': "{count} days runnin'. Noted, hon.",
        'completion': "{item} done.",
        'correlation': "I'm seein' a little pattern here: {observation}.",
    },
    'new_yorker': {
        'missed_med': "{time} {medicine} - not marked. Took it or no?",
        'missed_med_with_context': "{time} {medicine} not marked. Your labs had elevated {context}.",
        'grouped_meds_due': "{group} meds — due by {time}.",
        'overdue_task': "'{task}' is overdue. Doing it or rescheduling?",
        'workout_check': "No workout today. Did you go or not?",
        'journal_check': "No journal yet. Writing one?",
        'busy_day': "Tomorrow's got {count} things. Need to move anything?",
        'pattern_positive': "Your {metric}'s better when you {activity}.",
        'pattern_negative': "{metric} spikes when you log {trigger}.",
        'streak_note': "{count} days straight.",
        'completion': "{item} done.",
        'correlation': "Seeing a pattern: {observation}.",
    },
    'california': {
        'missed_med': "Hey, your {time} {medicine} isn't marked yet. Did you take it, or want me to skip it?",
        'missed_med_with_context': "Yo, your {time} {medicine} isn't marked. Just a heads up - your labs showed {context}.",
        'grouped_meds_due': "Hey, your {group} meds are due by {time}.",
        'overdue_task': "'{task}' is overdue, dude. Still gonna do it, or should we reschedule?",
        'workout_check': "No workout logged today. Did you get out there?",
        'journal_check': "No journal entry yet. Wanna write something?",
        'busy_day': "Tomorrow's looking pretty stacked with {count} things. Wanna shuffle anything?",
        'pattern_positive': "Your {metric} seems way better on days you {activity}.",
        'pattern_negative': "Your {metric} tends to climb when {trigger} is in the mix.",
        'streak_note': "{count} days going. Nice.",
        'completion': "{item} logged.",
        'correlation': "Noticing something: {observation}.",
    },
}


def get_style_template(user, template_key: str) -> str:
    """Get the message template for the user's coaching style."""
    style = 'default'
    try:
        prefs = user.preferences
        coaching_style = getattr(prefs, 'ai_coaching_style', 'supportive')
        # Map coaching styles to template keys
        style_map = {
            'southern_belle': 'southern_belle',
            'new_yorker': 'new_yorker',
            'california': 'california',
            'texas_rancher': 'southern_belle',  # Similar to southern
            'direct': 'new_yorker',  # Direct is similar to new yorker
            'supportive': 'default',
            'gentle': 'default',
            'cheerleader': 'default',
            'mentor': 'default',
            'companion': 'default',
            'coach': 'default',
        }
        style = style_map.get(coaching_style, 'default')
    except Exception:
        pass

    templates = COACHING_STYLE_TEMPLATES.get(style, COACHING_STYLE_TEMPLATES['default'])
    return templates.get(template_key, COACHING_STYLE_TEMPLATES['default'].get(template_key, ''))


# =============================================================================
# THROTTLING - PREVENT MESSAGE SPAM
# =============================================================================

class InteractionThrottler:
    """
    Prevents overwhelming the user with too many nudges.

    Rules:
    - Max 3 proactive messages per hour
    - Max 1 message per item type per day
    - No repeat nudges within 4 hours for same item
    """

    def __init__(self, user):
        self.user = user

    def can_send(self, check_type: str, item_id: Optional[int] = None) -> bool:
        """
        Check if we can send a proactive message of this type.

        Args:
            check_type: Type of check-in (medicine, workout, task, etc.)
            item_id: Optional specific item ID

        Returns:
            True if we can send, False if throttled
        """
        from .models import AssistantMessage
        from apps.core.utils import get_user_today

        now = timezone.now()
        today = get_user_today(self.user)
        one_hour_ago = now - timedelta(hours=1)
        four_hours_ago = now - timedelta(hours=4)

        # Rule 1: Max 3 proactive messages per hour
        recent_count = AssistantMessage.objects.filter(
            conversation__user=self.user,
            is_proactive=True,
            created_at__gte=one_hour_ago,
        ).count()

        if recent_count >= 3:
            logger.debug(f"Throttled: {self.user.id} has {recent_count} messages in last hour")
            return False

        # Rule 2: No repeat for same item within 4 hours
        if item_id:
            repeat_exists = AssistantMessage.objects.filter(
                conversation__user=self.user,
                is_proactive=True,
                metadata__check_in_type=check_type,
                metadata__contains={'item_id': item_id},
                created_at__gte=four_hours_ago,
            ).exists()

            if repeat_exists:
                logger.debug(f"Throttled: Same item {check_type}:{item_id} within 4 hours")
                return False

        # Rule 3: Max 1 of each type per day (except medicine which can have multiple doses)
        if check_type not in ['medicine', 'pattern', 'correlation']:
            type_today = AssistantMessage.objects.filter(
                conversation__user=self.user,
                is_proactive=True,
                metadata__check_in_type=check_type,
                created_at__date=today,
            ).exists()

            if type_today:
                logger.debug(f"Throttled: Already sent {check_type} today")
                return False

        return True

    def should_interact(self) -> bool:
        """
        The primary question: "Is this helpful right now?"

        Checks if the user is in a state where interaction is appropriate.
        """
        # Don't bother users who haven't been active in a while
        from .models import AssistantMessage

        # Check if user has interacted recently (within 24 hours)
        recent_activity = AssistantMessage.objects.filter(
            conversation__user=self.user,
            role='user',
            created_at__gte=timezone.now() - timedelta(hours=24),
        ).exists()

        # If no recent activity, only send if something is truly time-sensitive
        # (handled by caller - we just note activity level here)
        return True  # For now, always allow if throttle rules pass


# =============================================================================
# PATTERN RECOGNITION (FACTUAL CORRELATIONS ONLY)
# =============================================================================

class PatternAnalyzer:
    """
    Analyzes user data for factual patterns and correlations.

    IMPORTANT: This provides OBSERVATIONS, not medical advice.
    We state facts like "Higher glucose on pizza days" not recommendations.
    """

    def __init__(self, user):
        self.user = user
        self._lookback_days = 30

    def find_food_glucose_correlations(self) -> Optional[dict]:
        """
        Find correlations between specific foods and glucose readings.

        Returns dict with food name and average glucose, or None.
        """
        from apps.health.models import BloodGlucoseReading, NutritionEntry

        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=self._lookback_days)

        # Get days with glucose readings
        glucose_by_day = {}
        readings = BloodGlucoseReading.objects.filter(
            user=self.user,
            recorded_at__date__gte=start_date,
            recorded_at__date__lte=end_date,
        ).values('recorded_at__date').annotate(avg_glucose=Avg('value'))

        for r in readings:
            glucose_by_day[r['recorded_at__date']] = float(r['avg_glucose'])

        if len(glucose_by_day) < 7:
            return None  # Not enough data

        # Get food entries
        food_entries = NutritionEntry.objects.filter(
            user=self.user,
            date__gte=start_date,
            date__lte=end_date,
        ).values('date', 'food_name')

        # Correlate
        food_glucose = {}
        for entry in food_entries:
            food_name = entry['food_name'].lower()
            entry_date = entry['date']

            if entry_date in glucose_by_day:
                if food_name not in food_glucose:
                    food_glucose[food_name] = []
                food_glucose[food_name].append(glucose_by_day[entry_date])

        # Find foods with significantly higher glucose
        overall_avg = sum(glucose_by_day.values()) / len(glucose_by_day) if glucose_by_day else 0

        significant_foods = []
        for food, glucose_values in food_glucose.items():
            if len(glucose_values) >= 3:  # Need at least 3 occurrences
                food_avg = sum(glucose_values) / len(glucose_values)
                # 15% higher than average is significant
                if food_avg > overall_avg * 1.15:
                    significant_foods.append({
                        'food': food,
                        'avg_glucose': round(food_avg, 1),
                        'occurrences': len(glucose_values),
                        'vs_average': round(food_avg - overall_avg, 1),
                    })

        if significant_foods:
            # Return the most significant one
            significant_foods.sort(key=lambda x: x['vs_average'], reverse=True)
            return significant_foods[0]

        return None

    def find_workout_mood_correlation(self) -> Optional[dict]:
        """
        Find correlation between workouts and mood scores.

        Returns dict with observation, or None.
        """
        from apps.health.models import WorkoutSession
        from apps.journal.models import JournalEntry

        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=self._lookback_days)

        # Get workout days
        workout_days = set(
            WorkoutSession.objects.filter(
                user=self.user,
                date__gte=start_date,
                date__lte=end_date,
            ).values_list('date', flat=True)
        )

        if len(workout_days) < 5:
            return None  # Not enough data

        # Get mood entries
        mood_values = {'great': 5, 'good': 4, 'okay': 3, 'low': 2, 'bad': 1}
        entries = JournalEntry.objects.filter(
            user=self.user,
            entry_date__gte=start_date,
            entry_date__lte=end_date,
            mood__in=mood_values.keys(),
        ).values('entry_date', 'mood')

        workout_moods = []
        non_workout_moods = []

        for entry in entries:
            mood_score = mood_values.get(entry['mood'], 3)
            if entry['entry_date'] in workout_days:
                workout_moods.append(mood_score)
            else:
                non_workout_moods.append(mood_score)

        if len(workout_moods) < 3 or len(non_workout_moods) < 3:
            return None

        workout_avg = sum(workout_moods) / len(workout_moods)
        non_workout_avg = sum(non_workout_moods) / len(non_workout_moods)

        # Significant if workout days are 0.5+ points better
        if workout_avg > non_workout_avg + 0.5:
            return {
                'observation': 'mood tends to be higher on workout days',
                'workout_avg': round(workout_avg, 1),
                'non_workout_avg': round(non_workout_avg, 1),
                'difference': round(workout_avg - non_workout_avg, 1),
            }

        return None

    def find_sleep_energy_correlation(self) -> Optional[dict]:
        """
        Find correlation between sleep duration and energy/mood.
        """
        from apps.health.models import SleepEntry
        from apps.journal.models import JournalEntry

        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=self._lookback_days)

        # Get sleep entries
        sleep_entries = SleepEntry.objects.filter(
            user=self.user,
            date__gte=start_date,
            date__lte=end_date,
            duration_hours__isnull=False,
        ).values('date', 'duration_hours')

        if len(sleep_entries) < 7:
            return None

        sleep_by_day = {s['date']: float(s['duration_hours']) for s in sleep_entries}

        # Get mood entries
        mood_values = {'great': 5, 'good': 4, 'okay': 3, 'low': 2, 'bad': 1}
        entries = JournalEntry.objects.filter(
            user=self.user,
            entry_date__gte=start_date,
            entry_date__lte=end_date,
            mood__in=mood_values.keys(),
        ).values('entry_date', 'mood')

        good_sleep_moods = []  # 7+ hours
        poor_sleep_moods = []  # <6 hours

        for entry in entries:
            entry_date = entry['entry_date']
            if entry_date in sleep_by_day:
                mood_score = mood_values.get(entry['mood'], 3)
                if sleep_by_day[entry_date] >= 7:
                    good_sleep_moods.append(mood_score)
                elif sleep_by_day[entry_date] < 6:
                    poor_sleep_moods.append(mood_score)

        if len(good_sleep_moods) < 3 or len(poor_sleep_moods) < 3:
            return None

        good_avg = sum(good_sleep_moods) / len(good_sleep_moods)
        poor_avg = sum(poor_sleep_moods) / len(poor_sleep_moods)

        if good_avg > poor_avg + 0.5:
            return {
                'observation': 'mood tends to be better after 7+ hours of sleep',
                'good_sleep_avg': round(good_avg, 1),
                'poor_sleep_avg': round(poor_avg, 1),
            }

        return None


# =============================================================================
# BUSY DAY DETECTION
# =============================================================================

class ScheduleAnalyzer:
    """Analyzes user's schedule for busy days and overload."""

    def __init__(self, user):
        self.user = user

    def get_tomorrow_load(self) -> dict:
        """
        Analyze tomorrow's schedule load.

        Returns dict with item count and details.
        """
        from apps.core.utils import get_user_today
        from apps.life.models import Task, CalendarEvent

        today = get_user_today(self.user)
        tomorrow = today + timedelta(days=1)

        # Count tasks due tomorrow
        tasks_due = Task.objects.filter(
            user=self.user,
            due_date=tomorrow,
            is_complete=False,
        ).count()

        # Count calendar events
        events = CalendarEvent.objects.filter(
            user=self.user,
            start_time__date=tomorrow,
        ).count()

        # Count scheduled medicine doses
        from apps.health.models import MedicineSchedule
        medicine_count = MedicineSchedule.objects.filter(
            medicine__user=self.user,
            medicine__is_active=True,
            is_active=True,
        ).count()

        total = tasks_due + events

        return {
            'total': total,
            'tasks': tasks_due,
            'events': events,
            'medicines': medicine_count,
            'is_busy': total >= 5,
        }

    def get_overdue_tasks(self) -> List[dict]:
        """Get tasks that are overdue."""
        from apps.core.utils import get_user_today
        from apps.life.models import Task

        today = get_user_today(self.user)

        overdue = Task.objects.filter(
            user=self.user,
            due_date__lt=today,
            is_complete=False,
        ).values('id', 'title', 'due_date')[:5]  # Max 5

        return list(overdue)

    def get_repeatedly_postponed_tasks(self) -> List[dict]:
        """Get tasks that have been postponed multiple times."""
        # This would require tracking postponement history
        # For now, return empty - can enhance later
        return []


# =============================================================================
# INTELLIGENT CHECK-IN GENERATOR
# =============================================================================

class IntelligentCheckInService:
    """
    The main intelligence service for generating check-ins.

    Combines throttling, pattern analysis, and context awareness
    to generate helpful, non-intrusive check-ins.
    """

    def __init__(self, user):
        self.user = user
        self.throttler = InteractionThrottler(user)
        self.pattern_analyzer = PatternAnalyzer(user)
        self.schedule_analyzer = ScheduleAnalyzer(user)

    def generate_check_ins(self) -> List[dict]:
        """
        Generate all appropriate check-ins for the user.

        Returns a list of check-in messages to create.
        This is the main entry point called by scheduled jobs.
        """
        check_ins = []

        # 1. Missed medications (time-sensitive, highest priority)
        med_check_ins = self._check_missed_medications()
        check_ins.extend(med_check_ins)

        # 2. Overdue tasks
        if self.throttler.can_send('task_overdue'):
            task_check_in = self._check_overdue_tasks()
            if task_check_in:
                check_ins.append(task_check_in)

        # 3. Busy day planning
        if self.throttler.can_send('busy_day'):
            busy_check_in = self._check_busy_day()
            if busy_check_in:
                check_ins.append(busy_check_in)

        # 4. Pattern notifications (max 1 per day)
        if self.throttler.can_send('pattern'):
            pattern_check_in = self._check_patterns()
            if pattern_check_in:
                check_ins.append(pattern_check_in)

        return check_ins

    def _check_missed_medications(self) -> List[dict]:
        """Check for medications that are past their scheduled time."""
        from apps.health.models import Medicine, MedicineSchedule, MedicineLog
        from apps.core.utils import get_user_today

        check_ins = []
        today = get_user_today(self.user)
        now = timezone.now()
        current_time = now.time()

        medicines = Medicine.objects.filter(user=self.user, is_active=True)

        for medicine in medicines:
            schedules = MedicineSchedule.objects.filter(
                medicine=medicine,
                is_active=True
            )

            for schedule in schedules:
                if not schedule.applies_to_day(today.weekday()):
                    continue

                # Check if this dose time has passed
                scheduled_time = schedule.scheduled_time
                if current_time < scheduled_time:
                    continue  # Not time yet

                # Check if already logged
                log = MedicineLog.objects.filter(
                    medicine=medicine,
                    scheduled_date=today,
                    scheduled_time=scheduled_time,
                ).first()

                if log and log.log_status in ['taken', 'skipped', 'late']:
                    continue  # Already handled

                # Check throttle for this specific dose
                item_key = f"{medicine.id}_{scheduled_time.strftime('%H%M')}"
                if not self.throttler.can_send('medicine', hash(item_key)):
                    continue

                # Build message with context if available
                context = self._get_medicine_context(medicine)
                time_display = scheduled_time.strftime('%I:%M %p').lstrip('0')

                if context:
                    template = get_style_template(self.user, 'missed_med_with_context')
                    message = template.format(
                        time=time_display,
                        medicine=medicine.name,
                        context=context
                    )
                else:
                    template = get_style_template(self.user, 'missed_med')
                    message = template.format(
                        time=time_display,
                        medicine=medicine.name
                    )

                check_ins.append({
                    'type': 'medicine',
                    'message': message,
                    'medicine_id': medicine.id,
                    'dose_time': scheduled_time.strftime('%H:%M'),
                    'item_id': hash(item_key),
                })

        return check_ins

    def _get_medicine_context(self, medicine) -> Optional[str]:
        """
        Get relevant health context for a medicine.

        Example: "Your last labs showed elevated cholesterol"
        """
        # Check medicine reason/notes for context
        reason = getattr(medicine, 'reason', '') or ''

        # Keywords that indicate health reasons
        if 'cholesterol' in reason.lower():
            return 'elevated cholesterol'
        if 'blood pressure' in reason.lower() or 'bp' in reason.lower():
            return 'elevated blood pressure'
        if 'diabetes' in reason.lower() or 'glucose' in reason.lower():
            return 'blood sugar concerns'
        if 'thyroid' in reason.lower():
            return 'thyroid levels'

        return None

    def _check_overdue_tasks(self) -> Optional[dict]:
        """Check for overdue tasks."""
        overdue = self.schedule_analyzer.get_overdue_tasks()

        if not overdue:
            return None

        # Get the most overdue task
        task = overdue[0]

        template = get_style_template(self.user, 'overdue_task')
        message = template.format(task=task['title'])

        return {
            'type': 'task_overdue',
            'message': message,
            'task_id': task['id'],
            'item_id': task['id'],
        }

    def _check_busy_day(self) -> Optional[dict]:
        """Check if tomorrow is a busy day."""
        load = self.schedule_analyzer.get_tomorrow_load()

        if not load['is_busy']:
            return None

        template = get_style_template(self.user, 'busy_day')
        message = template.format(count=load['total'])

        return {
            'type': 'busy_day',
            'message': message,
            'item_id': None,
        }

    def _check_patterns(self) -> Optional[dict]:
        """Check for interesting patterns to share."""
        # Try food-glucose correlation first
        food_correlation = self.pattern_analyzer.find_food_glucose_correlations()
        if food_correlation:
            template = get_style_template(self.user, 'pattern_negative')
            message = template.format(
                metric='blood sugar',
                trigger=food_correlation['food']
            )
            return {
                'type': 'pattern',
                'message': message,
                'item_id': None,
            }

        # Try workout-mood correlation
        workout_correlation = self.pattern_analyzer.find_workout_mood_correlation()
        if workout_correlation:
            template = get_style_template(self.user, 'pattern_positive')
            message = template.format(
                metric='mood',
                activity='work out'
            )
            return {
                'type': 'pattern',
                'message': message,
                'item_id': None,
            }

        # Try sleep-mood correlation
        sleep_correlation = self.pattern_analyzer.find_sleep_energy_correlation()
        if sleep_correlation:
            template = get_style_template(self.user, 'correlation')
            message = template.format(
                observation=sleep_correlation['observation']
            )
            return {
                'type': 'pattern',
                'message': message,
                'item_id': None,
            }

        return None

    def generate_completion_acknowledgment(self, item_type: str, item_name: str) -> str:
        """
        Generate brief acknowledgment for completed item.

        Keep it SHORT. No cheerleading.
        """
        template = get_style_template(self.user, 'completion')
        return template.format(item=item_name)

    def generate_streak_note(self, count: int, activity: str) -> str:
        """
        Generate brief streak acknowledgment.

        Keep it SHORT. Just noting the fact.
        """
        template = get_style_template(self.user, 'streak_note')
        return template.format(count=count)


def get_intelligent_service(user):
    """Get the intelligent check-in service for a user."""
    return IntelligentCheckInService(user)
