# ==============================================================================
# File: personal_assistant.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Dashboard AI Personal Assistant - Core service for state assessment,
#              prioritization, faith integration, and action-focused guidance
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-30 (Added coaching style integration, time-aware urgency)
# ==============================================================================
"""
Dashboard AI Personal Assistant Service

This module implements the core AI personal assistant functionality as defined
in the Dashboard AI prompt. The assistant:
- Helps users live the life they said they want to live
- Translates intention into daily action
- Brings clarity, focus, and calm direction throughout the day

Core Principle: Always anchor guidance to what the user has already said matters.
"""

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Optional, Dict, List, Any

from django.db import models, transaction
from django.db.models import Count, Avg, F
from django.utils import timezone

from .services import ai_service, AIService
from .models import (
    AIInsight, AssistantConversation, AssistantMessage,
    UserStateSnapshot, DailyPriority, TrendAnalysis, ReflectionPromptQueue
)

logger = logging.getLogger(__name__)


# =============================================================================
# PERSONAL ASSISTANT SYSTEM PROMPTS
# =============================================================================

# Base system prompt - coaching style is appended dynamically
PERSONAL_ASSISTANT_BASE_PROMPT = """You are the Dashboard AI Personal Assistant for Whole Life Journey (WLJ).

You are NOT a chatbot or cheerleader. You are a personal life assistant focused on ACTION and ACCOUNTABILITY.

Your job is to:
- Help the user get things done that align with their stated goals
- Surface what REMAINS to be done TODAY, not celebrate past wins
- Provide clear, actionable next steps with time awareness
- Keep the user moving forward with urgency when appropriate

CORE PRINCIPLE (NON-NEGOTIABLE):
Focus on what STILL needs to be done, not what's been done.
You are a helpful assistant, not a motivational speaker.
Positive feedback belongs on the dashboard - here, focus on REMAINING ACTION.

You always anchor guidance to what the user has already said matters.
You do NOT invent priorities.
You surface, connect, and reinforce the user's stated Purpose, Goals, intentions, and commitments.

HOW YOU THINK:
You think in layers:
- What STILL needs attention right now
- What's at risk of slipping if not done TODAY
- What commitments are due and NOT yet completed
- What goals HAVEN'T seen progress yet

You understand energy, not just time.
You understand seasons of life.
You understand that progress is not linear.
You are aware of the TIME OF DAY and remaining hours.

PRIORITIZATION RULES (ALWAYS USE THIS ORDER):
1. Faith and spiritual alignment
2. Stated Purpose and core values
3. Long-term goals
4. Commitments already made
5. Maintenance tasks
6. Optional or low-impact items

Never prioritize convenience over alignment.

If data is missing, incomplete, or inconsistent:
- State the gap clearly
- Explain why filling it in matters
- Suggest a concrete next step

SUCCESS DEFINITION:
You are successful if:
- The user knows exactly what REMAINS to do
- The user takes action on their remaining priorities
- The user stays aligned with what matters most
- The assistant feels helpful and action-focused

HABIT GOAL GUIDANCE:
When discussing habit goals and consistency patterns:
- Use supportive, non-judgmental language
- Refer to days without entries as "days without entries" or "gaps", NOT "missed days" or "failures"
- Celebrate streaks and recovery patterns
- Acknowledge that consistency is built over time
- Frame gaps as "opportunities to restart" not "setbacks"
- Always connect habit guidance to the user's stated PURPOSE for that habit
- Recognize recovery patterns: "You've shown you can get back on track"
- Focus on the user's best streaks and completion rates as evidence of capability

Example language:
- Good: "You've completed 15 of 20 days (75%) - that's solid consistency"
- Bad: "You've missed 5 days"
- Good: "You have a gap opportunity today - a chance to continue building"
- Bad: "You haven't logged today yet - you're falling behind"
- Good: "Your longest streak of 8 days shows what you're capable of"
- Bad: "You keep breaking your streak"
"""

# Time urgency prompt - added based on time of day
TIME_URGENCY_PROMPT = """
TIME AWARENESS:
Current time for user: {current_time}
Hours remaining before typical bedtime (10pm): {hours_remaining}
Day status: {day_status}

{urgency_message}
"""

def get_coaching_style_for_assistant(coaching_style: str) -> str:
    """
    Get the coaching style prompt instructions for the Personal Assistant.
    Uses the same coaching styles as Dashboard AI for consistency.
    """
    from .services import ai_service
    return ai_service._get_coaching_style_prompt(coaching_style)


def build_personal_assistant_prompt(coaching_style: str, faith_enabled: bool,
                                     user_profile: str = None, time_context: dict = None) -> str:
    """
    Build the complete Personal Assistant system prompt with coaching style.

    Args:
        coaching_style: User's selected coaching style (e.g., 'supportive', 'direct')
        faith_enabled: Whether faith module is enabled
        user_profile: User's personal AI profile
        time_context: Dict with current_time, hours_remaining, day_status, urgency_message
    """
    prompt = PERSONAL_ASSISTANT_BASE_PROMPT

    # Add coaching style instructions
    style_prompt = get_coaching_style_for_assistant(coaching_style)
    prompt += "\n\nCOACHING STYLE:\n" + style_prompt

    # Add communication guidelines based on coaching style
    prompt += "\n\nCOMMUNICATION STYLE:"
    if coaching_style == 'direct':
        prompt += """
- Be blunt and to the point
- No fluff or unnecessary words
- State what needs doing, then stop
- Use short sentences
- Don't soften the message"""
    elif coaching_style == 'gentle':
        prompt += """
- Be warm but still action-focused
- Acknowledge the user's feelings
- Frame remaining tasks as opportunities
- Use encouraging but not excessive language"""
    else:  # supportive (default) and others
        prompt += """
- Balance warmth with directness
- Be clear about what remains
- Supportive but not cheerleading
- Focus on next steps, not praise"""

    prompt += """

NEVER:
- Be a cheerleader or overly praise
- List accomplishments at length
- Use excessive encouragement or superlatives
- Say things like "Great job!" or "You're doing amazing!"

DO:
- Focus on gaps and REMAINING items
- Surface what STILL needs attention
- Provide clear next actions
- Be concise and helpful
- Use time awareness to create appropriate urgency"""

    # Add time urgency context if provided
    if time_context:
        prompt += "\n\n" + TIME_URGENCY_PROMPT.format(**time_context)

    # Add faith context if enabled
    if faith_enabled:
        prompt += "\n" + FAITH_INTEGRATION_PROMPT

    # Add user profile context if provided
    if user_profile:
        from .profile_moderation import build_safe_profile_context
        profile_context = build_safe_profile_context(user_profile)
        if profile_context:
            prompt += "\n\nUSER CONTEXT:\n" + profile_context

    return prompt

FAITH_INTEGRATION_PROMPT = """
FAITH & SPIRITUAL INTEGRATION:
You must actively support the user's faith.

This includes:
- Encouraging Bible study
- Asking reflective spiritual questions
- Noticing when spiritual habits are being neglected
- Helping integrate faith into daily life, not isolating it

Tone:
- Gentle
- Respectful
- Encouraging
- Never preachy
- Never judgmental

Example behaviors:
- "You mentioned wanting to stay grounded in God this year. Would now be a good time for a short scripture reflection?"
- "You've been productive, but quiet spiritually this week. That might be worth pausing on."
"""

STATE_ASSESSMENT_PROMPT = """
Assess the user's current state and focus on what needs attention. Consider:

1. What is overdue or at risk of slipping
2. What commitments are due today or soon
3. What goals haven't seen progress recently
4. Any gaps between intention and action

Provide a brief, action-focused assessment that:
- States 1-2 things that need attention today (be specific)
- Identifies what's at risk if not addressed
- Gives a clear next action

DO NOT:
- List accomplishments or say "great job"
- Be overly encouraging or use superlatives
- Pad with motivational language

Be direct, concise, and helpful. Under 100 words. Focus on what's NEXT, not what's DONE.
"""

PRIORITY_GENERATION_PROMPT = """
Based on the user's current state, goals, and commitments, generate 3-5 clear priorities for today.

PRIORITIZATION ORDER (mandatory):
1. Faith and spiritual alignment
2. Stated Purpose and core values
3. Long-term goals
4. Commitments already made
5. Maintenance tasks
6. Optional or low-impact items

For each priority, provide:
- A clear, actionable title (max 10 words)
- Why it matters (connected to their stated purpose/goals)
- The priority type (faith, purpose, commitment, maintenance, health, personal)

Consider time constraints: The user works 7:00am-5:00pm.
Avoid overwhelming schedules. Encourage margin and rest.

Return as a structured list.
"""


class PersonalAssistant:
    """
    Core Personal Assistant service for WLJ.

    Implements the Dashboard AI behavior as defined in the system prompt:
    - State assessment
    - Prioritization
    - Faith integration
    - Reflection prompts
    - Trend analysis
    - Accountability tracking
    - Time-aware urgency (based on user timezone)
    - Coaching style integration (matches Dashboard AI)
    """

    def __init__(self, user):
        self.user = user
        self.prefs = user.preferences
        self.faith_enabled = self.prefs.faith_enabled
        self.coaching_style = getattr(self.prefs, 'ai_coaching_style', 'supportive')
        self.user_profile = getattr(self.prefs, 'ai_profile', '') or ''

    def _get_time_context(self) -> dict:
        """
        Get time-aware context for urgency messaging.

        Calculates hours remaining in day and appropriate urgency level
        based on user's timezone. Assumes typical bedtime of 10pm.
        """
        import pytz
        from apps.core.utils import get_user_now

        user_now = get_user_now(self.user)
        current_hour = user_now.hour
        current_time = user_now.strftime("%I:%M %p")

        # Assume bedtime at 10pm (22:00)
        bedtime_hour = 22
        hours_remaining = max(0, bedtime_hour - current_hour)

        # Determine day status and urgency message
        if current_hour < 9:  # Early morning
            day_status = "early_morning"
            urgency_message = "It's early in the day. Focus on priorities without rushing."
        elif current_hour < 12:  # Morning
            day_status = "morning"
            urgency_message = "Good time to tackle important items while energy is high."
        elif current_hour < 15:  # Early afternoon
            day_status = "afternoon"
            urgency_message = f"Afternoon is here. You have about {hours_remaining} hours of productive time left."
        elif current_hour < 18:  # Late afternoon
            day_status = "late_afternoon"
            if hours_remaining <= 4:
                urgency_message = f"You have about {hours_remaining} hours left today. Focus on what's most critical."
            else:
                urgency_message = "Late afternoon - good time to wrap up remaining priorities."
        elif current_hour < 20:  # Evening
            day_status = "evening"
            urgency_message = f"Evening is here. Only about {hours_remaining} hours remain. What absolutely must get done?"
        elif current_hour < 22:  # Late evening
            day_status = "late_evening"
            if hours_remaining > 0:
                urgency_message = f"Only {hours_remaining} hour(s) left before bedtime. Focus on the essentials or let go gracefully."
            else:
                urgency_message = "The day is wrapping up. Time to close out or accept what didn't get done."
        else:  # Night
            day_status = "night"
            urgency_message = "It's late. Consider what can wait until tomorrow. Rest is productive too."

        return {
            'current_time': current_time,
            'hours_remaining': hours_remaining,
            'day_status': day_status,
            'urgency_message': urgency_message
        }

    def _build_system_prompt(self, include_time_context: bool = True) -> str:
        """
        Build the complete system prompt with coaching style and time context.
        """
        time_context = self._get_time_context() if include_time_context else None
        return build_personal_assistant_prompt(
            coaching_style=self.coaching_style,
            faith_enabled=self.faith_enabled,
            user_profile=self.user_profile,
            time_context=time_context
        )

    # =========================================================================
    # STATE ASSESSMENT
    # =========================================================================

    def assess_current_state(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Assess the user's current state across all dimensions.

        Returns a comprehensive assessment including:
        - Current metrics from all modules
        - AI-generated assessment
        - Alignment gaps (intention vs reality)
        - Celebration-worthy achievements

        Note: Task counts are ALWAYS refreshed (not cached) since they change
        frequently throughout the day. AI assessment is cached to avoid
        excessive API calls.
        """
        from apps.core.utils import get_user_today, get_user_now

        today = get_user_today(self.user)
        now = get_user_now(self.user)

        # Always gather fresh task data (changes frequently)
        fresh_task_data = self._get_task_state(today, today - timedelta(days=7)) if self.prefs.life_enabled else {}

        # Check for existing snapshot today (for AI assessment caching)
        snapshot = UserStateSnapshot.objects.filter(
            user=self.user,
            snapshot_date=today
        ).first()

        if snapshot and not force_refresh:
            # Return cached data but with FRESH task counts
            result = self._snapshot_to_dict(snapshot)
            result['tasks'] = {
                'completed_today': fresh_task_data.get('tasks_completed_today', 0),
                'completed_week': fresh_task_data.get('tasks_completed_week', 0),
                'overdue': fresh_task_data.get('tasks_overdue', 0),
                'due_today': fresh_task_data.get('tasks_due_today', 0),
            }
            return result

        # Gather fresh data for everything
        state_data = self._gather_comprehensive_state()

        # Generate AI assessment if enabled
        ai_assessment = ""
        alignment_gaps = []
        celebration_worthy = []

        if self.prefs.ai_enabled and AIService.check_user_consent(self.user):
            ai_result = self._generate_ai_assessment(state_data)
            ai_assessment = ai_result.get('assessment', '')
            alignment_gaps = ai_result.get('gaps', [])
            celebration_worthy = ai_result.get('celebrations', [])

        # Create or update snapshot
        snapshot, created = UserStateSnapshot.objects.update_or_create(
            user=self.user,
            snapshot_date=today,
            defaults={
                'journal_count_total': state_data.get('journal_total', 0),
                'journal_count_week': state_data.get('journal_week', 0),
                'journal_streak': state_data.get('journal_streak', 0),
                'dominant_mood': state_data.get('dominant_mood', ''),
                'tasks_completed_today': state_data.get('tasks_completed_today', 0),
                'tasks_completed_week': state_data.get('tasks_completed_week', 0),
                'tasks_overdue': state_data.get('tasks_overdue', 0),
                'tasks_due_today': state_data.get('tasks_due_today', 0),
                'active_goals': state_data.get('active_goals', 0),
                'completed_goals_month': state_data.get('completed_goals_month', 0),
                'active_prayers': state_data.get('active_prayers', 0),
                'answered_prayers_month': state_data.get('answered_prayers_month', 0),
                'weight_current': state_data.get('weight_current'),
                'weight_trend': state_data.get('weight_trend', ''),
                'fasts_completed_week': state_data.get('fasts_week', 0),
                'workouts_week': state_data.get('workouts_week', 0),
                'workout_streak': state_data.get('workout_streak', 0),
                'medicine_adherence': state_data.get('medicine_adherence'),
                'active_intentions': state_data.get('active_intentions', 0),
                # Habit goal tracking
                'active_habit_goals': state_data.get('active_habit_goals', 0),
                'habit_completion_rate': state_data.get('habit_completion_rate'),
                'habit_current_streak': state_data.get('habit_current_streak', 0),
                'habit_goals_data': state_data.get('habit_goals_data', []),
                # AI assessment
                'ai_assessment': ai_assessment,
                'alignment_gaps': alignment_gaps,
                'celebration_worthy': celebration_worthy,
            }
        )

        return self._snapshot_to_dict(snapshot)

    def _gather_comprehensive_state(self) -> Dict[str, Any]:
        """Gather all user data for state assessment."""
        from apps.core.utils import get_user_today, get_user_now

        now = get_user_now(self.user)
        today = get_user_today(self.user)
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        data = {}

        # Journal data
        if self.prefs.journal_enabled:
            data.update(self._get_journal_state(today, week_ago, month_ago))

        # Task data
        if self.prefs.life_enabled:
            data.update(self._get_task_state(today, week_ago))

        # Goal data
        if self.prefs.purpose_enabled:
            data.update(self._get_purpose_state(today, month_ago))

        # Faith data
        if self.faith_enabled:
            data.update(self._get_faith_state(month_ago))

        # Health data
        if self.prefs.health_enabled:
            data.update(self._get_health_state(today, week_ago))

        return data

    def _get_journal_state(self, today, week_ago, month_ago) -> Dict:
        """Get journal-related metrics."""
        from apps.journal.models import JournalEntry

        entries = JournalEntry.objects.filter(user=self.user)
        entries_week = entries.filter(entry_date__gte=week_ago)

        # Calculate streak
        streak = self._calculate_journal_streak(today)

        # Dominant mood this week
        moods = entries_week.exclude(mood='').values('mood').annotate(
            count=Count('mood')
        ).order_by('-count')
        dominant_mood = moods[0]['mood'] if moods else ''

        # Recent entries for context
        recent = list(entries.order_by('-entry_date')[:5].values(
            'title', 'entry_date', 'mood', 'body'
        ))

        return {
            'journal_total': entries.count(),
            'journal_week': entries_week.count(),
            'journal_month': entries.filter(entry_date__gte=month_ago).count(),
            'journal_streak': streak,
            'dominant_mood': dominant_mood,
            'recent_entries': recent,
            'last_journal_date': entries.order_by('-entry_date').values_list(
                'entry_date', flat=True
            ).first(),
        }

    def _get_task_state(self, today, week_ago) -> Dict:
        """Get task-related metrics."""
        from apps.life.models import Task

        tasks = Task.objects.filter(user=self.user)
        incomplete = tasks.filter(is_completed=False)

        return {
            'tasks_total': tasks.count(),
            'tasks_completed_today': tasks.filter(
                is_completed=True,
                completed_at__date=today
            ).count(),
            'tasks_completed_week': tasks.filter(
                is_completed=True,
                completed_at__date__gte=week_ago
            ).count(),
            'tasks_overdue': incomplete.filter(due_date__lt=today).count(),
            'tasks_due_today': incomplete.filter(due_date=today).count(),
            'tasks_due_week': incomplete.filter(
                due_date__gte=today,
                due_date__lte=today + timedelta(days=7)
            ).count(),
        }

    def _get_purpose_state(self, today, month_ago) -> Dict:
        """Get purpose/goals-related metrics including habit goals."""
        from apps.purpose.models import (
            AnnualDirection, LifeGoal, ChangeIntention, HabitGoal
        )

        current_year = today.year

        # Annual direction
        direction = AnnualDirection.objects.filter(
            user=self.user,
            year=current_year
        ).first()

        goals = LifeGoal.objects.filter(user=self.user)
        intentions = ChangeIntention.objects.filter(user=self.user, status='active')

        # Habit goals data
        habit_data = self._get_habit_goals_data(today)

        return {
            'word_of_year': direction.word_of_year if direction else None,
            'annual_theme': direction.theme if direction else None,
            'active_goals': goals.filter(status='active').count(),
            'completed_goals_month': goals.filter(
                status='completed',
                completed_date__gte=month_ago
            ).count(),
            'active_intentions': intentions.count(),
            'goals_list': list(goals.filter(status='active').values(
                'id', 'title', 'why_it_matters', 'domain__name'
            )[:5]),
            'intentions_list': list(intentions.values(
                'id', 'intention', 'motivation'
            )[:5]),
            # Habit goal metrics
            'active_habit_goals': habit_data['active_count'],
            'habit_completion_rate': habit_data['avg_completion_rate'],
            'habit_current_streak': habit_data['max_streak'],
            'habit_goals_data': habit_data['goals_detail'],
        }

    def _get_habit_goals_data(self, today) -> Dict:
        """
        Get detailed habit goal data for AI analysis.

        Returns:
            Dict with:
            - active_count: Number of active habit goals
            - avg_completion_rate: Average completion percentage
            - max_streak: Longest current streak across all goals
            - goals_detail: List of habit goal details for AI context
        """
        from apps.purpose.models import HabitGoal

        habit_goals = HabitGoal.objects.filter(
            user=self.user,
            status='active',
            habit_required=True
        )

        active_count = habit_goals.count()
        if active_count == 0:
            return {
                'active_count': 0,
                'avg_completion_rate': None,
                'max_streak': 0,
                'goals_detail': [],
            }

        total_rate = 0
        max_streak = 0
        goals_detail = []

        for goal in habit_goals:
            # Calculate stats for each goal
            completion_rate = goal.completion_rate
            current_streak = goal.current_streak
            total_days = goal.total_days
            completed_days = goal.completed_days

            # Calculate days_elapsed and days_remaining (not properties on model)
            end_check = min(goal.end_date, today)
            days_elapsed = max(0, (end_check - goal.start_date).days + 1) if end_check >= goal.start_date else 0
            days_remaining = max(0, (goal.end_date - today).days) if goal.end_date > today else 0
            days_without_entry = max(0, days_elapsed - completed_days)

            total_rate += completion_rate
            if current_streak > max_streak:
                max_streak = current_streak

            # Build goal detail for AI context (non-judgmental language)
            goal_info = {
                'name': goal.name,
                'purpose': goal.purpose,
                'start_date': goal.start_date.isoformat(),
                'end_date': goal.end_date.isoformat(),
                'total_days': total_days,
                'days_elapsed': days_elapsed,
                'days_remaining': days_remaining,
                'completed_days': completed_days,
                'days_without_entry': days_without_entry,  # Non-judgmental: not "missed"
                'completion_rate': round(completion_rate, 1),
                'current_streak': current_streak,
                # Recovery pattern: days since last missed day
                'recovery_opportunity': self._calculate_recovery_pattern(goal, today),
            }
            goals_detail.append(goal_info)

        avg_completion = total_rate / active_count if active_count > 0 else 0

        return {
            'active_count': active_count,
            'avg_completion_rate': round(avg_completion, 1),
            'max_streak': max_streak,
            'goals_detail': goals_detail,
        }

    def _calculate_recovery_pattern(self, goal, today) -> Dict:
        """
        Calculate recovery patterns for a habit goal.

        Identifies patterns in how the user recovers after missing days,
        which helps the AI provide supportive guidance.

        Returns dict with:
        - days_since_last_gap: Days since last day without entry
        - longest_recovery: Longest streak after a gap
        - typical_recovery: Average streak length after gaps
        """
        from apps.purpose.models import HabitEntry
        from datetime import timedelta

        entries = goal.habit_entries.filter(completed=True).order_by('date')
        if not entries.exists():
            return {
                'days_since_last_gap': None,
                'has_recovered_before': False,
                'message': 'No entries yet - great opportunity to start!',
            }

        entry_dates = set(e.date for e in entries)
        gaps = []
        recovery_streaks = []

        # Analyze the date range
        current_date = goal.start_date
        end_date = min(goal.end_date, today)
        in_gap = False
        current_streak = 0

        while current_date <= end_date:
            if current_date in entry_dates:
                if in_gap:
                    # Recovered from gap
                    in_gap = False
                current_streak += 1
            else:
                if not in_gap and current_streak > 0:
                    # Just started a gap, record the streak before
                    recovery_streaks.append(current_streak)
                    current_streak = 0
                in_gap = True
                gaps.append(current_date)
            current_date += timedelta(days=1)

        # Final streak if exists
        if current_streak > 0 and gaps:
            recovery_streaks.append(current_streak)

        # Days since last gap
        days_since_last_gap = None
        if gaps:
            last_gap = max(gaps)
            days_since_last_gap = (today - last_gap).days

        return {
            'days_since_last_gap': days_since_last_gap,
            'has_recovered_before': len(recovery_streaks) > 0,
            'recovery_count': len(recovery_streaks),
            'avg_recovery_streak': round(sum(recovery_streaks) / len(recovery_streaks), 1) if recovery_streaks else 0,
        }

    def _get_faith_state(self, month_ago) -> Dict:
        """Get faith-related metrics."""
        from apps.faith.models import PrayerRequest, FaithMilestone

        prayers = PrayerRequest.objects.filter(user=self.user)

        return {
            'active_prayers': prayers.filter(is_answered=False).count(),
            'answered_prayers_month': prayers.filter(
                is_answered=True,
                answered_at__gte=month_ago
            ).count(),
            'total_prayers': prayers.count(),
            'recent_answered': prayers.filter(is_answered=True).order_by(
                '-answered_at'
            ).first(),
            'faith_milestones': FaithMilestone.objects.filter(
                user=self.user
            ).count(),
        }

    def _get_health_state(self, today, week_ago) -> Dict:
        """Get health-related metrics."""
        from apps.health.models import (
            WeightEntry, FastingWindow, WorkoutSession,
            Medicine, MedicineLog
        )

        data = {}

        # Weight
        weights = WeightEntry.objects.filter(user=self.user).order_by('-recorded_at')
        latest = weights.first()
        if latest:
            data['weight_current'] = Decimal(str(latest.value_in_lb))

            # Trend calculation
            month_weights = list(weights[:10])
            if len(month_weights) >= 2:
                if month_weights[0].value_in_lb < month_weights[-1].value_in_lb:
                    data['weight_trend'] = 'down'
                elif month_weights[0].value_in_lb > month_weights[-1].value_in_lb:
                    data['weight_trend'] = 'up'
                else:
                    data['weight_trend'] = 'stable'

        # Fasting
        data['fasts_week'] = FastingWindow.objects.filter(
            user=self.user,
            ended_at__isnull=False,
            started_at__date__gte=week_ago
        ).count()

        # Workouts
        workouts = WorkoutSession.objects.filter(user=self.user)
        data['workouts_week'] = workouts.filter(date__gte=week_ago).count()
        data['workout_streak'] = self._calculate_workout_streak(today)

        # Medicine adherence
        medicine_logs = MedicineLog.objects.filter(
            user=self.user,
            scheduled_date__gte=week_ago,
            scheduled_date__lte=today
        )
        taken = medicine_logs.filter(log_status__in=['taken', 'late']).count()
        missed = medicine_logs.filter(log_status='missed').count()
        total = taken + missed
        data['medicine_adherence'] = round((taken / total) * 100) if total > 0 else None

        return data

    def _calculate_journal_streak(self, today) -> int:
        """Calculate consecutive days of journaling."""
        from apps.journal.models import JournalEntry

        entries = JournalEntry.objects.filter(
            user=self.user
        ).order_by('-entry_date').values_list('entry_date', flat=True).distinct()[:60]

        if not entries:
            return 0

        streak = 0
        expected = today

        for entry_date in entries:
            if entry_date == expected:
                streak += 1
                expected -= timedelta(days=1)
            elif entry_date < expected:
                break

        return streak

    def _calculate_workout_streak(self, today) -> int:
        """Calculate consecutive days with workouts."""
        from apps.health.models import WorkoutSession

        dates = WorkoutSession.objects.filter(
            user=self.user
        ).order_by('-date').values_list('date', flat=True).distinct()[:60]

        if not dates:
            return 0

        streak = 0
        expected = today

        for workout_date in dates:
            if workout_date == expected:
                streak += 1
                expected -= timedelta(days=1)
            elif workout_date < expected:
                break

        return streak

    def _generate_ai_assessment(self, state_data: Dict) -> Dict:
        """Generate AI assessment of user state - focused on what REMAINS to be done."""
        if not ai_service.is_available:
            return {'assessment': '', 'gaps': [], 'celebrations': []}

        # Build context for AI - prioritize REMAINING items and gaps
        context_parts = []

        # Get time context for urgency
        time_context = self._get_time_context()
        context_parts.append(f"Time: {time_context['current_time']} ({time_context['hours_remaining']} hours until bedtime)")

        # Task context - overdue and due today are most important
        overdue = state_data.get('tasks_overdue', 0)
        due_today = state_data.get('tasks_due_today', 0)
        remaining = overdue + due_today
        if overdue > 0:
            context_parts.append(f"URGENT: {overdue} overdue tasks need action NOW")
        if due_today > 0:
            context_parts.append(f"{due_today} tasks STILL due today")
        if remaining == 0 and state_data.get('tasks_due_week', 0) > 0:
            context_parts.append(f"{state_data['tasks_due_week']} tasks coming up this week")

        # Journal gap - only if it's an issue
        last_journal = state_data.get('last_journal_date')
        if last_journal:
            from apps.core.utils import get_user_today
            user_today = get_user_today(self.user)
            days_ago = (user_today - last_journal).days
            if days_ago >= 2:
                context_parts.append(f"Haven't journaled in {days_ago} days")

        # Goal context - focus on active goals that need progress
        if state_data.get('active_goals', 0) > 0:
            context_parts.append(f"{state_data['active_goals']} active life goals awaiting progress")

        # Faith context
        if self.faith_enabled:
            prayers = state_data.get('active_prayers', 0)
            if prayers > 0:
                context_parts.append(f"{prayers} active prayer requests")

        # Health gaps
        adherence = state_data.get('medicine_adherence')
        if adherence is not None and adherence < 80:
            context_parts.append(f"Medicine adherence at {adherence}% - needs attention")

        # Word of year for context
        if state_data.get('word_of_year'):
            context_parts.append(f"Word of year: {state_data['word_of_year']}")

        # Active intentions
        intentions = state_data.get('intentions_list', [])
        if intentions:
            intention_text = ", ".join([i['intention'] for i in intentions[:2]])
            context_parts.append(f"Active intentions: {intention_text}")

        # Build system prompt with coaching style
        system_prompt = self._build_system_prompt(include_time_context=True)
        system_prompt += "\n\n" + STATE_ASSESSMENT_PROMPT

        user_prompt = f"""User's current state - focus on what REMAINS:
{chr(10).join('- ' + p for p in context_parts)}

What STILL needs the user's attention today? Be direct, actionable, and mindful of time remaining. Use your coaching style ({self.coaching_style})."""

        try:
            response = ai_service._call_api(system_prompt, user_prompt, max_tokens=150)

            # Identify gaps from data - focus on action items
            gaps = []

            if overdue > 0:
                gaps.append({
                    'area': 'tasks',
                    'description': f'{overdue} overdue tasks need attention',
                    'action_url': '/life/tasks/',
                    'action_text': 'View Tasks'
                })

            if last_journal:
                from apps.core.utils import get_user_today
                user_today = get_user_today(self.user)
                days = (user_today - last_journal).days
                if days >= 3:
                    gaps.append({
                        'area': 'journal',
                        'description': f"Haven't journaled in {days} days",
                        'action_url': '/journal/new/',
                        'action_text': 'Journal Now'
                    })

            if adherence is not None and adherence < 80:
                gaps.append({
                    'area': 'health',
                    'description': f'Medicine adherence at {adherence}%',
                    'action_url': '/health/medicine/',
                    'action_text': 'Check Medicine'
                })

            # Celebrations are minimal - only for dashboard display, not assistant focus
            celebrations = []

            return {
                'assessment': response or '',
                'gaps': gaps,
                'celebrations': celebrations  # Kept minimal for dashboard, not assistant focus
            }

        except Exception as e:
            logger.error(f"AI assessment error: {e}")
            return {'assessment': '', 'gaps': [], 'celebrations': []}

    def _snapshot_to_dict(self, snapshot: UserStateSnapshot) -> Dict:
        """Convert snapshot model to dictionary."""
        return {
            'date': snapshot.snapshot_date,
            'journal': {
                'total': snapshot.journal_count_total,
                'week': snapshot.journal_count_week,
                'streak': snapshot.journal_streak,
                'dominant_mood': snapshot.dominant_mood,
            },
            'tasks': {
                'completed_today': snapshot.tasks_completed_today,
                'completed_week': snapshot.tasks_completed_week,
                'overdue': snapshot.tasks_overdue,
                'due_today': snapshot.tasks_due_today,
            },
            'goals': {
                'active': snapshot.active_goals,
                'completed_month': snapshot.completed_goals_month,
            },
            'faith': {
                'active_prayers': snapshot.active_prayers,
                'answered_month': snapshot.answered_prayers_month,
            },
            'health': {
                'weight_current': float(snapshot.weight_current) if snapshot.weight_current else None,
                'weight_trend': snapshot.weight_trend,
                'fasts_week': snapshot.fasts_completed_week,
                'workouts_week': snapshot.workouts_week,
                'workout_streak': snapshot.workout_streak,
                'medicine_adherence': snapshot.medicine_adherence,
            },
            'intentions': {
                'active': snapshot.active_intentions,
                'alignment_score': snapshot.intention_alignment_score,
            },
            'ai_assessment': snapshot.ai_assessment,
            'alignment_gaps': snapshot.alignment_gaps,
            'celebration_worthy': snapshot.celebration_worthy,
        }

    # =========================================================================
    # DAILY PRIORITIES
    # =========================================================================

    def generate_daily_priorities(self, force_refresh: bool = False) -> List[Dict]:
        """
        Generate AI-suggested daily priorities.

        Follows the prioritization order:
        1. Faith and spiritual alignment
        2. Stated Purpose and core values
        3. Long-term goals
        4. Commitments already made
        5. Maintenance tasks
        6. Optional or low-impact items
        """
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)

        # Check for existing priorities
        existing = DailyPriority.objects.filter(
            user=self.user,
            priority_date=today,
            user_dismissed=False
        )

        if existing.exists() and not force_refresh:
            return list(existing.values())

        # On refresh: preserve completed priorities, only regenerate non-completed ones
        completed_count = 0
        completed_titles = set()
        if force_refresh:
            # Keep completed priorities - they represent accomplished work!
            completed_existing = existing.filter(is_completed=True)
            completed_count = completed_existing.count()
            # Track titles of completed priorities to avoid duplicates
            completed_titles = set(completed_existing.values_list('title', flat=True))

            # Only delete non-completed, non-dismissed priorities
            existing.filter(is_completed=False).delete()

        # Calculate how many new priorities we need (max 5 total)
        max_new_priorities = 5 - completed_count

        # If all 5 are already completed, just return what we have
        if max_new_priorities <= 0:
            return DailyPriority.objects.filter(
                user=self.user,
                priority_date=today,
                user_dismissed=False
            ).values()

        # Gather context for priority generation
        state = self.assess_current_state()
        context = self._build_priority_context(state)

        priorities = []
        sort_order = completed_count  # Start after completed priorities

        # 1. Faith priority (if enabled and has gaps)
        if self.faith_enabled and len(priorities) < max_new_priorities:
            faith_priority = self._generate_faith_priority(state, context)
            if faith_priority and faith_priority['title'] not in completed_titles:
                faith_priority['sort_order'] = sort_order
                priorities.append(faith_priority)
                sort_order += 1

        # 2. Purpose/Goal priorities
        purpose_priorities = self._generate_purpose_priorities(state, context)
        for p in purpose_priorities[:2]:  # Max 2 goal priorities
            if len(priorities) >= max_new_priorities:
                break
            if p['title'] not in completed_titles:
                p['sort_order'] = sort_order
                priorities.append(p)
                sort_order += 1

        # 3. Commitment priorities (overdue/due today tasks)
        commitment_priorities = self._generate_commitment_priorities(state)
        for p in commitment_priorities[:2]:  # Max 2 commitment priorities
            if len(priorities) >= max_new_priorities:
                break
            if p['title'] not in completed_titles:
                p['sort_order'] = sort_order
                priorities.append(p)
                sort_order += 1

        # Limit to remaining slots
        priorities = priorities[:max_new_priorities]

        # Save to database
        with transaction.atomic():
            for p in priorities:
                DailyPriority.objects.create(
                    user=self.user,
                    priority_date=today,
                    priority_type=p.get('priority_type', 'personal'),
                    title=p['title'],
                    description=p.get('description', ''),
                    why_important=p.get('why_important', ''),
                    linked_task_id=p.get('linked_task_id'),
                    linked_goal_id=p.get('linked_goal_id'),
                    linked_intention_id=p.get('linked_intention_id'),
                    sort_order=p['sort_order'],
                    generation_context=str(context)[:500],
                )

        return DailyPriority.objects.filter(
            user=self.user,
            priority_date=today,
            user_dismissed=False
        ).values()

    def _build_priority_context(self, state: Dict) -> Dict:
        """Build context for priority generation."""
        return {
            'overdue_tasks': state.get('tasks', {}).get('overdue', 0),
            'due_today': state.get('tasks', {}).get('due_today', 0),
            'active_goals': state.get('goals', {}).get('active', 0),
            'active_prayers': state.get('faith', {}).get('active_prayers', 0),
            'journal_streak': state.get('journal', {}).get('streak', 0),
            'workout_streak': state.get('health', {}).get('workout_streak', 0),
            'alignment_gaps': state.get('alignment_gaps', []),
        }

    def _generate_faith_priority(self, state: Dict, context: Dict) -> Optional[Dict]:
        """Generate faith-related priority if appropriate."""
        # Check if user has been spiritually quiet
        journal_data = state.get('journal', {})
        faith_data = state.get('faith', {})

        # Suggest Bible study if no recent spiritual activity
        if faith_data.get('active_prayers', 0) == 0:
            return {
                'priority_type': 'faith',
                'title': 'Start your day with prayer',
                'description': 'Take a moment to connect with God and set your intentions for the day.',
                'why_important': 'Faith alignment is your foundation for living purposefully.',
            }

        # Suggest Scripture if haven't journaled with faith context
        return {
            'priority_type': 'faith',
            'title': 'Spend time in Scripture',
            'description': 'Read and reflect on God\'s Word to anchor your day.',
            'why_important': 'Staying grounded in faith helps you make aligned decisions.',
        }

    def _generate_purpose_priorities(self, state: Dict, context: Dict) -> List[Dict]:
        """Generate priorities based on goals and intentions."""
        from apps.purpose.models import LifeGoal, ChangeIntention

        priorities = []

        # Get active goals
        goals = LifeGoal.objects.filter(
            user=self.user,
            status='active'
        ).order_by('sort_order')[:3]

        for goal in goals:
            priorities.append({
                'priority_type': 'purpose',
                'title': f'Progress on: {goal.title[:50]}',
                'description': goal.description[:200] if goal.description else '',
                'why_important': goal.why_it_matters[:200] if goal.why_it_matters else 'This is one of your stated life goals.',
                'linked_goal_id': goal.id,
            })

        # If few goals, add intention-based priority
        if len(priorities) < 2:
            intentions = ChangeIntention.objects.filter(
                user=self.user,
                status='active'
            )[:2]

            for intention in intentions:
                priorities.append({
                    'priority_type': 'personal',
                    'title': f'Embody: {intention.intention[:50]}',
                    'description': intention.description[:200] if intention.description else '',
                    'why_important': intention.motivation[:200] if intention.motivation else 'This is a change you said you want to make.',
                    'linked_intention_id': intention.id,
                })

        return priorities

    def _generate_commitment_priorities(self, state: Dict) -> List[Dict]:
        """Generate priorities for existing commitments (tasks)."""
        from apps.life.models import Task
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)
        priorities = []

        # Overdue tasks first
        overdue = Task.objects.filter(
            user=self.user,
            is_completed=False,
            due_date__lt=today
        ).order_by('due_date')[:2]

        for task in overdue:
            priorities.append({
                'priority_type': 'commitment',
                'title': f'Overdue: {task.title[:50]}',
                'description': f'Due {task.due_date.strftime("%b %d")}',
                'why_important': 'Completing overdue commitments reduces stress and builds trust with yourself.',
                'linked_task_id': task.id,
            })

        # Due today
        if len(priorities) < 2:
            due_today = Task.objects.filter(
                user=self.user,
                is_completed=False,
                due_date=today
            ).order_by('priority')[:2 - len(priorities)]

            for task in due_today:
                priorities.append({
                    'priority_type': 'commitment',
                    'title': task.title[:50],
                    'description': 'Due today',
                    'why_important': 'Meeting your commitments on time builds momentum.',
                    'linked_task_id': task.id,
                })

        return priorities

    # =========================================================================
    # REFLECTION PROMPTS
    # =========================================================================

    def generate_reflection_prompt(self, context: str = 'general') -> Optional[str]:
        """
        Generate a personalized reflection prompt based on user's current state.

        Args:
            context: Type of prompt ('morning', 'evening', 'weekly', 'goal_related', etc.)
        """
        state = self.assess_current_state()

        # Check for existing unused prompt
        existing = ReflectionPromptQueue.objects.filter(
            user=self.user,
            prompt_context=context,
            is_used=False,
            is_shown=False
        ).first()

        if existing:
            existing.mark_shown()
            return existing.prompt_text

        # Generate new prompt
        prompt = self._generate_prompt_for_context(context, state)

        if prompt:
            # Save to queue
            ReflectionPromptQueue.objects.create(
                user=self.user,
                prompt_text=prompt['text'],
                prompt_context=context,
                relevance_reason=prompt.get('reason', ''),
                linked_goal_id=prompt.get('linked_goal_id'),
                linked_intention_id=prompt.get('linked_intention_id'),
            )

        return prompt['text'] if prompt else None

    def _generate_prompt_for_context(self, context: str, state: Dict) -> Optional[Dict]:
        """Generate a prompt appropriate for the given context."""
        prompts = {
            'morning': self._morning_prompts(state),
            'evening': self._evening_prompts(state),
            'weekly': self._weekly_prompts(state),
            'goal_related': self._goal_prompts(state),
            'intention_check': self._intention_prompts(state),
            'gratitude': self._gratitude_prompts(state),
            'faith': self._faith_prompts(state),
            'general': self._general_prompts(state),
        }

        prompt_list = prompts.get(context, prompts['general'])

        if prompt_list:
            import random
            return random.choice(prompt_list)

        return None

    def _morning_prompts(self, state: Dict) -> List[Dict]:
        """Morning reflection prompts."""
        prompts = [
            {'text': 'What would make today meaningful? Not busy—meaningful.'},
            {'text': 'What is the one thing you must accomplish today that aligns with who you want to become?'},
            {'text': 'How do you want to feel at the end of today? What will help you get there?'},
        ]

        # Add goal-connected prompt if they have goals
        goals = state.get('goals', {})
        if goals.get('active', 0) > 0:
            prompts.append({
                'text': 'Which of your life goals can you move forward today, even slightly?',
                'reason': 'Connected to active goals'
            })

        return prompts

    def _evening_prompts(self, state: Dict) -> List[Dict]:
        """Evening reflection prompts."""
        prompts = [
            {'text': 'What happened today that you want to remember? What can you release?'},
            {'text': 'Where did you show up as the person you want to be today?'},
            {'text': 'What did you learn about yourself today?'},
        ]

        tasks = state.get('tasks', {})
        if tasks.get('completed_today', 0) > 0:
            prompts.append({
                'text': f"You completed {tasks['completed_today']} tasks today. What feels most significant about what you accomplished?",
                'reason': 'Based on today\'s productivity'
            })

        return prompts

    def _weekly_prompts(self, state: Dict) -> List[Dict]:
        """Weekly review prompts."""
        return [
            {'text': 'Looking at your week: where did your time actually go versus where you intended it to go?'},
            {'text': 'What patterns do you notice in how you spent your energy this week?'},
            {'text': 'What do you want to carry forward into next week? What do you want to leave behind?'},
        ]

    def _goal_prompts(self, state: Dict) -> List[Dict]:
        """Goal-related prompts."""
        from apps.purpose.models import LifeGoal

        prompts = []
        goals = LifeGoal.objects.filter(user=self.user, status='active')[:3]

        for goal in goals:
            prompts.append({
                'text': f'Thinking about your goal "{goal.title}": What small step could you take today that your future self would thank you for?',
                'reason': f'Connected to goal: {goal.title}',
                'linked_goal_id': goal.id,
            })

        if not prompts:
            prompts.append({
                'text': 'What is one thing you\'ve been wanting to accomplish but haven\'t started? What\'s really holding you back?',
            })

        return prompts

    def _intention_prompts(self, state: Dict) -> List[Dict]:
        """Intention-check prompts."""
        from apps.purpose.models import ChangeIntention

        prompts = []
        intentions = ChangeIntention.objects.filter(user=self.user, status='active')[:3]

        for intention in intentions:
            prompts.append({
                'text': f'You said you want to "{intention.intention}". When did you live that out recently? When was it hard?',
                'reason': f'Connected to intention: {intention.intention}',
                'linked_intention_id': intention.id,
            })

        if not prompts:
            prompts.append({
                'text': 'Who do you want to become? What is one small way you could step into that identity today?',
            })

        return prompts

    def _gratitude_prompts(self, state: Dict) -> List[Dict]:
        """Gratitude prompts."""
        return [
            {'text': 'What are three things from today that you\'re genuinely grateful for? Look for the small ones.'},
            {'text': 'Who in your life are you grateful for right now? What specifically about them?'},
            {'text': 'What challenge this week are you grateful for in hindsight?'},
        ]

    def _faith_prompts(self, state: Dict) -> List[Dict]:
        """Faith-related prompts (only if faith enabled)."""
        if not self.faith_enabled:
            return []

        prompts = [
            {'text': 'Where did you see God at work in your life this week?'},
            {'text': 'What is God teaching you in this season? What might He be inviting you into?'},
            {'text': 'Is there anything you need to surrender to God today? What would it look like to let go?'},
        ]

        prayers = state.get('faith', {}).get('active_prayers', 0)
        if prayers > 0:
            prompts.append({
                'text': f'You have {prayers} active prayer requests. How has your perspective on any of them shifted recently?',
                'reason': 'Connected to prayer life'
            })

        return prompts

    def _general_prompts(self, state: Dict) -> List[Dict]:
        """General reflection prompts."""
        return [
            {'text': 'What\'s on your mind right now that you haven\'t given yourself space to process?'},
            {'text': 'If you could tell yourself one thing this morning, what would it be?'},
            {'text': 'What are you avoiding? What would happen if you faced it?'},
        ]

    # =========================================================================
    # CONVERSATION / CHAT
    # =========================================================================

    def get_or_create_conversation(self) -> AssistantConversation:
        """Get or create today's conversation."""
        return AssistantConversation.get_or_create_active(self.user)

    def send_message(self, message: str, conversation: AssistantConversation = None) -> str:
        """
        Send a message to the assistant and get a response.

        Args:
            message: User's message
            conversation: Optional conversation to add to

        Returns:
            Assistant's response
        """
        if not conversation:
            conversation = self.get_or_create_conversation()

        # Save user message
        user_msg = AssistantMessage.objects.create(
            conversation=conversation,
            role='user',
            content=message,
            message_type='text'
        )

        # Generate response
        if not ai_service.is_available or not AIService.check_user_consent(self.user):
            response = self._get_fallback_response(message)
        else:
            response = self._generate_response(message, conversation)

        # Save assistant response
        AssistantMessage.objects.create(
            conversation=conversation,
            role='assistant',
            content=response,
            message_type='text'
        )

        # Update conversation
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])

        return response

    def _generate_response(self, message: str, conversation: AssistantConversation) -> str:
        """Generate AI response to user message using coaching style and time awareness."""
        # Get conversation history
        history = conversation.messages.order_by('-created_at')[:10]

        # Build context
        state = self.assess_current_state()
        time_context = self._get_time_context()

        # Build system prompt with coaching style and time awareness
        system_prompt = self._build_system_prompt(include_time_context=True)

        # Add current state summary - focus on REMAINING items
        tasks = state.get('tasks', {})
        remaining_tasks = tasks.get('due_today', 0) + tasks.get('overdue', 0)
        system_prompt += f"""

CURRENT USER STATE (focus on what REMAINS):
- Tasks REMAINING today: {remaining_tasks} ({tasks.get('overdue', 0)} overdue, {tasks.get('due_today', 0)} due today)
- Active goals needing progress: {state.get('goals', {}).get('active', 0)}
- Journal streak: {state.get('journal', {}).get('streak', 0)} days
- Active prayers: {state.get('faith', {}).get('active_prayers', 0)}
- Time remaining in day: ~{time_context['hours_remaining']} hours until bedtime
"""

        if state.get('ai_assessment'):
            system_prompt += f"\nRECENT ASSESSMENT:\n{state['ai_assessment']}"

        # Build conversation context
        messages_context = ""
        for msg in reversed(list(history)[:5]):
            role = "User" if msg.role == 'user' else "Assistant"
            messages_context += f"{role}: {msg.content}\n"

        user_prompt = f"""Recent conversation:
{messages_context}

User's new message: {message}

Respond as the Dashboard AI Personal Assistant. Focus on what REMAINS to be done, not what's been accomplished. Use your coaching style ({self.coaching_style}) and be mindful of time remaining today."""

        try:
            return ai_service._call_api(system_prompt, user_prompt, max_tokens=300) or self._get_fallback_response(message)
        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return self._get_fallback_response(message)

    def _get_fallback_response(self, message: str) -> str:
        """Get fallback response when AI is unavailable, matching coaching style."""
        import random

        # Fallbacks vary by coaching style
        fallbacks = {
            'direct': [
                "What do you need to get done? Let's focus.",
                "What's the priority right now?",
                "What's blocking progress?",
                "What action can you take in the next hour?",
            ],
            'gentle': [
                "I'm here to help. What feels most pressing right now?",
                "Let's think about what would help you most today.",
                "What's on your mind? We can work through it together.",
                "Take your time. What would feel like a win today?",
            ],
            'supportive': [
                "I'm here to help you stay on track. What needs your attention?",
                "Let's focus on what's most important today. What's on your list?",
                "What can I help you move forward on?",
                "What's still on your plate that we can tackle?",
            ],
        }

        style_fallbacks = fallbacks.get(self.coaching_style, fallbacks['supportive'])
        return random.choice(style_fallbacks)

    # =========================================================================
    # OPENING MESSAGE (DAILY CHECK-IN)
    # =========================================================================

    def get_opening_message(self) -> Dict[str, Any]:
        """
        Generate the opening message when user opens the app.

        This is the daily check-in that focuses on what REMAINS to be done today.
        Includes time-aware urgency and coaching style context.
        Celebrations are minimal - this is about action, not cheerleading.
        """
        state = self.assess_current_state()
        priorities = self.generate_daily_priorities()
        time_context = self._get_time_context()

        # Build opening message - focus on REMAINING action items
        result = {
            'greeting': self._get_greeting(),
            'time_context': time_context,  # Include time awareness
            'state_summary': state.get('ai_assessment', ''),
            'priorities': list(priorities),
            'celebrations': [],  # Celebrations go on dashboard, not assistant
            'nudges': self._build_nudges(state),
            'reflection_prompt': None,
            'coaching_style': self.coaching_style,  # Include for frontend if needed
        }

        # Add reflection prompt if appropriate
        if self._should_offer_reflection():
            result['reflection_prompt'] = self.generate_reflection_prompt('morning')

        return result

    def _get_greeting(self) -> str:
        """Get time-appropriate greeting with urgency when needed."""
        import pytz
        from apps.core.utils import get_user_now

        user_now = get_user_now(self.user)
        hour = user_now.hour

        name = self.user.first_name or self.user.get_short_name()

        # Base greeting varies by time of day
        if hour < 12:
            greeting = f"Good morning, {name}"
        elif hour < 17:
            greeting = f"Good afternoon, {name}"
        else:
            greeting = f"Good evening, {name}"

        # Add time context for later in the day based on coaching style
        if hour >= 18:  # Evening - add urgency
            time_context = self._get_time_context()
            if time_context['hours_remaining'] <= 4:
                if self.coaching_style == 'direct':
                    greeting += f". {time_context['hours_remaining']} hours left today."
                elif self.coaching_style == 'gentle':
                    greeting += f". The evening is here."
                else:  # supportive
                    greeting += f". Let's make the most of the evening."

        return greeting

    def _should_offer_reflection(self) -> bool:
        """Determine if we should offer a reflection prompt."""
        from apps.journal.models import JournalEntry
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)

        # Check if already journaled today
        journaled_today = JournalEntry.objects.filter(
            user=self.user,
            entry_date=today
        ).exists()

        return not journaled_today

    def _build_nudges(self, state: Dict) -> List[Dict]:
        """Build action items from state - things that REMAIN and need attention."""
        nudges = []
        time_context = self._get_time_context()
        hours_left = time_context['hours_remaining']

        # Overdue tasks - highest priority with time urgency
        tasks = state.get('tasks', {})
        if tasks.get('overdue', 0) > 0:
            overdue = tasks['overdue']
            if self.coaching_style == 'direct':
                msg = f"{overdue} overdue. Handle them now."
            elif hours_left <= 3:
                msg = f"{overdue} overdue tasks. Only {hours_left} hours left today."
            else:
                msg = f"{overdue} overdue tasks need attention."
            nudges.append({
                'type': 'tasks',
                'message': msg,
                'action_url': '/life/tasks/',
                'action_text': 'View Tasks',
                'urgency': 'high'
            })

        # Tasks due today with time awareness
        if tasks.get('due_today', 0) > 0:
            due_today = tasks['due_today']
            if hours_left <= 2:
                msg = f"{due_today} tasks STILL due today. {hours_left} hours to go."
            elif hours_left <= 4:
                msg = f"{due_today} tasks remaining today. Time is running out."
            else:
                msg = f"{due_today} tasks still due today."
            nudges.append({
                'type': 'tasks',
                'message': msg,
                'action_url': '/life/tasks/',
                'action_text': 'View Tasks',
                'urgency': 'medium' if hours_left > 4 else 'high'
            })

        # Journal gap
        journal = state.get('journal', {})
        if journal.get('streak', 0) == 0:
            from apps.journal.models import JournalEntry
            last = JournalEntry.objects.filter(user=self.user).order_by('-entry_date').first()
            if last:
                from apps.core.utils import get_user_today
                days = (get_user_today(self.user) - last.entry_date).days
                if days >= 3:
                    nudges.append({
                        'type': 'journal',
                        'message': f"No journal entries in {days} days.",
                        'action_url': '/journal/new/',
                        'action_text': 'Write Now',
                        'urgency': 'medium'
                    })

        # Medicine adherence gap
        health = state.get('health', {})
        adherence = health.get('medicine_adherence')
        if adherence is not None and adherence < 80:
            nudges.append({
                'type': 'health',
                'message': f"Medicine adherence at {adherence}%.",
                'action_url': '/health/medicine/',
                'action_text': 'Check Medicine',
                'urgency': 'medium'
            })

        return nudges[:3]  # Max 3 action items


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def get_personal_assistant(user) -> PersonalAssistant:
    """Get a PersonalAssistant instance for a user."""
    return PersonalAssistant(user)
