# ==============================================================================
# File: personal_assistant.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Dashboard AI Personal Assistant - Core service for state assessment,
#              prioritization, faith integration, and action-focused guidance
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2025-12-29
# Last Updated: 2026-01-05 (Integrated personal data query system)
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
from assistant.views import process_assistant_message

logger = logging.getLogger(__name__)


# =============================================================================
# PERSONAL ASSISTANT SYSTEM PROMPTS
# =============================================================================

# Base system prompt - coaching style is appended dynamically
PERSONAL_ASSISTANT_BASE_PROMPT = """You are the Dashboard AI Personal Assistant for Whole Life Journey (WLJ).

RESPONSE STYLE (CRITICAL - FOLLOW EXACTLY):
- Answer the user's SPECIFIC QUESTION directly and concisely
- Do NOT proactively mention overdue tasks, outstanding items, or daily priorities
- Do NOT summarize what the user still needs to do unless they explicitly ask
- Keep responses focused ONLY on what was asked
- If they ask about their data, give them the data - don't add commentary about what else they should do
- Daily guidance and priorities belong in the Dashboard Insight on first visit, not in every response

NEVER VOLUNTEER THESE UNLESS ASKED:
- Overdue task counts or reminders
- Outstanding items or to-do lists
- Time remaining in the day ("Time's ticking down to bedtime!")
- Goal progress summaries
- What the user "should" focus on
- Encouragement about completing tasks ("hammer those out", "get after it")

You are NOT a chatbot, cheerleader, or nag. You are a responsive assistant that answers questions.

Your job is to:
- Answer questions directly with the information requested
- Wait for the user to ask before providing information
- Be concise - respect the user's time
- Let the user drive the conversation

CORE PRINCIPLE (NON-NEGOTIABLE):
Answer what was asked. Nothing more. Don't add fluff or unsolicited guidance.
You are a helpful assistant, not a motivational speaker or accountability partner (unless they ask).
If the user wants to know what they have left to do, THEY WILL ASK (e.g., "what do I have left to do today?").

WHEN THE USER ASKS ABOUT TASKS/PRIORITIES:
Only when the user explicitly asks questions like:
- "What do I have left to do today?"
- "What are my priorities?"
- "What tasks are overdue?"
- "What should I focus on?"

...THEN you can provide task summaries, overdue counts, and priority guidance.

HOW YOU THINK (internally, don't share unless asked):
You think in layers:
- What STILL needs attention right now
- What's at risk of slipping if not done TODAY
- What commitments are due and NOT yet completed
- What goals HAVEN'T seen progress yet

You understand energy, not just time.
You understand seasons of life.
You understand that progress is not linear.

PRIORITIZATION RULES (USE WHEN ASKED ABOUT PRIORITIES):
1. Faith and spiritual alignment
2. Stated Purpose and core values
3. Long-term goals
4. Commitments already made
5. Maintenance tasks
6. Optional or low-impact items

SUCCESS DEFINITION:
You are successful if:
- The user got a direct answer to their question
- Responses are concise and focused
- No unsolicited task summaries or reminders were given
- The assistant feels helpful, not naggy

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
Write like a real person texting a friend, not a corporate assistant or ChatGPT.

FORMAT (follow exactly):
1. One conversational sentence as an opener (casual, like talking to a buddy)
2. Then a SHORT bulleted list of what needs attention (actionable items they can act on)
3. One closing line that's motivating but not cheesy

VOICE RULES:
- Write like you're texting, not writing an email
- Use contractions (you've, don't, let's)
- Keep it punchy - no fluff words
- Sound like a helpful friend, not a robot
- Avoid corporate speak like "I wanted to reach out" or "Please note that"

DO NOT:
- Use bold text for emphasis (like **this**)
- Start with "Here's" or "Here are"
- Use superlatives or be overly encouraging
- List accomplishments or say "great job"
- Sound like ChatGPT or a motivational poster

EXAMPLES OF GOOD TONE:
- "Alright partner, here's what needs your attention tonight:"
- "Quick heads up - you've got a few things to knock out:"
- "Couple things on your radar today:"

Keep it under 80 words total. Focus on what's NEXT, not what's DONE.
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
        # Refresh preferences from database to ensure we have the latest values
        # This is important when user changes settings mid-session
        self.user.refresh_from_db()
        self.prefs = user.preferences
        self.prefs.refresh_from_db()
        self.faith_enabled = self.prefs.faith_enabled
        self.coaching_style = getattr(self.prefs, 'ai_coaching_style', 'supportive')
        self.user_profile = getattr(self.prefs, 'ai_profile', '') or ''
        # For data visibility confirmation flow
        self._data_visibility_response = None

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

        # Check if coaching style changed - if so, we need to regenerate the AI assessment
        # The coaching style is stored in alignment_gaps metadata when present
        coaching_style_changed = False
        if snapshot:
            snapshot_metadata = snapshot.alignment_gaps or []
            # We store coaching_style in a special metadata entry
            stored_style = None
            for item in snapshot_metadata:
                if isinstance(item, dict) and item.get('_coaching_style'):
                    stored_style = item.get('_coaching_style')
                    break
            # Regenerate if style changed OR if no style was stored (legacy snapshot)
            if stored_style is None or stored_style != self.coaching_style:
                coaching_style_changed = True
                if stored_style:
                    logger.info(f"Coaching style changed from {stored_style} to {self.coaching_style}, regenerating assessment")
                else:
                    logger.info(f"No coaching style stored in snapshot, regenerating assessment with {self.coaching_style}")

        if snapshot and not force_refresh and not coaching_style_changed:
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

        # Store coaching style in alignment_gaps metadata so we can detect style changes
        # and regenerate the AI assessment when needed
        alignment_gaps_with_style = list(alignment_gaps) if alignment_gaps else []
        alignment_gaps_with_style.append({'_coaching_style': self.coaching_style})

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
                'alignment_gaps': alignment_gaps_with_style,
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
        """Calculate consecutive days of journaling (excludes today)."""
        from apps.journal.models import JournalEntry

        entries = JournalEntry.objects.filter(
            user=self.user
        ).order_by('-entry_date').values_list('entry_date', flat=True).distinct()[:60]

        if not entries:
            return 0

        streak = 0
        # Start from yesterday - today doesn't count toward the streak
        expected = today - timedelta(days=1)

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

    def send_message(self, message: str, conversation: AssistantConversation = None, page_context: dict = None) -> dict:
        """
        Send a message to the assistant and get a response.

        Now supports intent recognition for structured data extraction.
        When the user says something like "my heart rate is 60", the assistant
        will recognize the intent, extract the data, and log it automatically.

        Supports multi-command messages like "update my oxygen to 95 and weight to 350"
        which will execute multiple actions and combine responses.

        Also detects feature requests ("I wish", "I want") when no matching solution
        exists and sends notifications to admin for review.

        Args:
            message: User's message
            conversation: Optional conversation to add to
            page_context: Optional dict with 'url', 'module', 'page_title' for context-aware responses

        Returns:
            Dict with 'response' (str) and optionally 'actions_taken' (list of dicts)
        """
        from .intent_service import intent_service
        from .feature_request_service import feature_request_service

        if not conversation:
            conversation = self.get_or_create_conversation()

        # Save user message
        user_msg = AssistantMessage.objects.create(
            conversation=conversation,
            role='user',
            content=message,
            message_type='text'
        )

        response = ""
        actions_taken = []

        # Check if AI is available
        if not ai_service.is_available or not AIService.check_user_consent(self.user):
            response = self._get_fallback_response(message)
        else:
            # First, check for pending data visibility confirmation
            if self._handle_data_visibility_confirmation(message, conversation):
                response = self._data_visibility_response
                self._data_visibility_response = None  # Clear after use
            # Then check for pending action confirmation
            elif (pending := intent_service.get_pending_confirmation(self.user)):
                # Handle confirmation response
                action_result = intent_service.handle_confirmation_response(self.user, message)
                if action_result:
                    if action_result.action_type == 'cancelled':
                        response = action_result.message
                    else:
                        response = action_result.message
                        actions_taken.append(self._build_action_taken(action_result))
                else:
                    # Response wasn't yes/no, ask again
                    response = f"Please confirm: {intent_service._build_confirmation_message(pending['intent_type'], pending['parameters'])} (yes/no)"
            else:
                # Try to recognize intents (supports multiple)
                intent_results = intent_service.recognize_intents(message, self.user)

                # Filter out no_action results
                actionable_intents = [ir for ir in intent_results if ir.intent_type != 'no_action']

                if actionable_intents:
                    # Check if any require confirmation
                    needs_confirmation = [ir for ir in actionable_intents if ir.requires_confirmation]

                    if needs_confirmation:
                        # For now, if any need confirmation, handle them one by one
                        # Store the first one pending and execute the rest
                        # TODO: Could enhance to batch confirmations
                        first_confirm = needs_confirmation[0]
                        intent_service.store_pending_confirmation(self.user, first_confirm)

                        # Execute any that don't need confirmation
                        no_confirm = [ir for ir in actionable_intents if not ir.requires_confirmation]
                        response_parts = []

                        for intent_result in no_confirm:
                            action_result = intent_service.execute_intent(intent_result, self.user)
                            if action_result.success:
                                response_parts.append(action_result.message)
                                actions_taken.append(self._build_action_taken(action_result))

                        # Add confirmation message for the pending one
                        response_parts.append(first_confirm.confirmation_message)
                        response = " ".join(response_parts)
                    else:
                        # Execute all actions immediately
                        response_parts = []

                        for intent_result in actionable_intents:
                            action_result = intent_service.execute_intent(intent_result, self.user)
                            if action_result.success:
                                response_parts.append(action_result.message)
                                actions_taken.append(self._build_action_taken(action_result))
                            else:
                                # Action failed - include error
                                response_parts.append(action_result.message)

                        response = " ".join(response_parts)
                else:
                    # No action intent - check for navigation query first
                    navigation_response = self._try_navigation_response(message, conversation)
                    if navigation_response:
                        response = navigation_response
                    else:
                        # Generate normal chat response
                        response = self._generate_response(message, conversation, page_context=page_context)

                    # Check for feature requests ("I wish", "I want") and notify admin
                    # This captures user needs that the system doesn't currently handle
                    self._check_feature_request(
                        message=message,
                        conversation=conversation,
                        feature_request_service=feature_request_service
                    )

        # Save assistant response
        msg_type = 'action' if actions_taken else 'text'
        assistant_msg = AssistantMessage.objects.create(
            conversation=conversation,
            role='assistant',
            content=response,
            message_type=msg_type
        )

        # Update conversation
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])

        # Return structured response
        result = {'response': response}
        if actions_taken:
            # For backwards compatibility, also include single action_taken
            result['action_taken'] = actions_taken[0] if len(actions_taken) == 1 else None
            result['actions_taken'] = actions_taken

        return result

    def _build_action_taken(self, action_result) -> dict:
        """Build the action_taken dict for API response."""
        return {
            'type': action_result.action_type,
            'success': action_result.success,
            'created': action_result.created_object
        }

    def _check_feature_request(
        self,
        message: str,
        conversation: AssistantConversation,
        feature_request_service
    ) -> bool:
        """
        Check if message is a feature request and notify admin if needed.

        When users express wishes or wants ("I wish", "I want") that the system
        doesn't currently handle, this sends a notification to admin for review.

        Args:
            message: The user's message
            conversation: The current conversation
            feature_request_service: The feature request service instance

        Returns:
            True if a notification was sent, False otherwise
        """
        try:
            # Build conversation context from recent messages
            recent_messages = conversation.messages.order_by('-created_at')[:5]
            context_parts = []
            for msg in reversed(list(recent_messages)):
                role = "User" if msg.role == 'user' else "Assistant"
                context_parts.append(f"{role}: {msg.content[:200]}")
            conversation_context = "\n".join(context_parts) if context_parts else None

            # Check and notify (handles rate limiting internally)
            return feature_request_service.check_and_notify(
                user=self.user,
                message=message,
                intent_type='no_action',
                conversation_context=conversation_context
            )
        except Exception as e:
            # Don't let feature request detection break the chat flow
            logger.warning(f"Feature request check failed: {e}")
            return False

    def _handle_data_visibility_confirmation(
        self, message: str, conversation: AssistantConversation
    ) -> bool:
        """
        Handle user's response to a data visibility clarifying question.

        When the assistant asks "Can you see your data in the app?", this method
        processes the user's yes/no response and takes appropriate action.

        Args:
            message: The user's message (checking for yes/no).
            conversation: The current conversation.

        Returns:
            True if this was a data visibility confirmation response (handled).
            False if not awaiting confirmation or message wasn't yes/no.
        """
        from assistant import handle_data_visibility_confirmation

        # Check if we're awaiting a data visibility confirmation
        metadata = conversation.metadata or {}
        if not metadata.get('awaiting_data_visibility_confirmation'):
            return False

        data_type = metadata.get('awaiting_data_type')
        if not data_type:
            # Clear invalid state
            metadata['awaiting_data_visibility_confirmation'] = False
            conversation.metadata = metadata
            conversation.save(update_fields=['metadata'])
            return False

        # Check if message is a yes/no response
        message_lower = message.lower().strip()
        affirmative_responses = ['yes', 'yeah', 'yep', 'yup', 'y', 'correct', 'right', 'i can', 'i can see', 'i do']
        negative_responses = ['no', 'nope', 'n', 'nah', "i can't", 'i cannot', "i don't", 'i do not']

        user_confirms = None
        if any(resp in message_lower for resp in affirmative_responses):
            user_confirms = True
        elif any(resp in message_lower for resp in negative_responses):
            user_confirms = False

        if user_confirms is None:
            # User didn't give a clear yes/no - let the normal flow handle it
            # but keep the awaiting state for the next message
            return False

        # Clear the awaiting state
        metadata['awaiting_data_visibility_confirmation'] = False
        metadata['awaiting_data_type'] = None
        conversation.metadata = metadata
        conversation.save(update_fields=['metadata'])

        # Handle the confirmation
        result = handle_data_visibility_confirmation(
            user=self.user,
            data_type=data_type,
            user_confirms_data_exists=user_confirms,
        )

        # Store response for retrieval in send_message
        self._data_visibility_response = result['response_message']

        logger.info(
            f"Data visibility confirmation handled for user {self.user.id}, "
            f"data_type={data_type}, user_confirms={user_confirms}, "
            f"action={result['action_taken']}"
        )

        return True

    def _try_navigation_response(self, message: str, conversation: AssistantConversation = None) -> str:
        """
        Check if the message is a navigation query and return a helpful response.

        Uses the Teaching Tool to answer questions like "where do I log my weight?"
        with a direct link, without calling the AI.

        For ambiguous queries like "how do I log it", uses conversation context
        to infer what the user is referring to.

        Args:
            message: User's message
            conversation: Optional conversation for context on ambiguous queries

        Returns:
            Response string with navigation info, or None if not a navigation query
        """
        # Check if query looks like a navigation question
        query_lower = message.lower().strip()
        navigation_indicators = [
            # Location questions
            'where do i', 'where can i', 'where is', 'where are',
            'where\'s the', 'where\'s my',
            # Navigation questions
            'how do i get to', 'how do i find', 'how do i access',
            'how do i go to', 'how do i navigate',
            # Action questions that imply needing to find a feature
            'how do i log', 'how do i track', 'how do i add',
            'how do i record', 'how do i enter', 'how do i create',
            'how do i write', 'how do i start', 'how do i set',
            'how can i log', 'how can i track', 'how can i add',
            'how can i record', 'how can i enter', 'how can i create',
            # Direct navigation requests
            'take me to', 'go to the', 'navigate to',
            'show me the', 'open the',
            'link to', 'path to', 'url for',
        ]

        is_navigation_query = any(
            query_lower.startswith(indicator) or f' {indicator}' in f' {query_lower}'
            for indicator in navigation_indicators
        )

        if not is_navigation_query:
            return None

        try:
            from apps.help.services import TeachingToolService

            teaching_service = TeachingToolService()

            # Check if query is ambiguous (uses pronouns like "it", "that", "this")
            # and try to get context from conversation
            search_query = message
            ambiguous_words = ['it', 'that', 'this', 'them', 'those']
            query_words = query_lower.split()
            is_ambiguous = any(word in ambiguous_words for word in query_words)

            if is_ambiguous and conversation:
                # Get recent messages from conversation for context
                recent_messages = conversation.messages.filter(
                    role='user'
                ).order_by('-created_at')[:5]

                # Look for topic keywords in recent messages
                topic_keywords = {
                    'weight': ['weight', 'weigh', 'pounds', 'lbs', 'kg'],
                    'food': ['food', 'eat', 'meal', 'calories', 'nutrition', 'ate'],
                    'journal': ['journal', 'write', 'diary', 'entry'],
                    'workout': ['workout', 'exercise', 'gym', 'fitness'],
                    'medication': ['medication', 'medicine', 'meds', 'pills'],
                    'fasting': ['fasting', 'fast', 'intermittent'],
                    'glucose': ['glucose', 'blood sugar', 'sugar'],
                    'prayer': ['prayer', 'pray', 'prayers'],
                    'goals': ['goal', 'goals', 'objective'],
                    'habits': ['habit', 'habits', 'routine'],
                    'task': ['task', 'tasks', 'todo', 'to-do'],
                }

                # Search recent messages for topic context
                detected_topic = None
                for msg in recent_messages:
                    msg_lower = msg.content.lower()
                    for topic, keywords in topic_keywords.items():
                        if any(kw in msg_lower for kw in keywords):
                            detected_topic = topic
                            break
                    if detected_topic:
                        break

                # If we found a topic, enhance the search query
                if detected_topic:
                    # Replace "it" with the detected topic
                    search_query = f"how do I log my {detected_topic}"
                    logger.debug(f"Enhanced ambiguous query '{message}' to '{search_query}' based on conversation context")

            result = teaching_service.search(search_query)

            if result['found'] and result['destination']:
                dest = result['destination']
                # Format a friendly response with "click here" as the link
                response = (
                    f"You can {dest['explanation'].lower().rstrip('.')} by going to "
                    f"**{dest['path']}**. For easy access, [click here]({dest['url']})."
                )
                return response

            # No strong match - return None to fall through to AI
            return None

        except Exception as e:
            logger.error(f"Error in navigation response: {e}")
            return None

    def _generate_response(self, message: str, conversation: AssistantConversation, page_context: dict = None) -> str:
        """Generate AI response to user message using coaching style.

        Now integrates with the personal data query system to inject relevant
        personal data context (weight, journal, medication, food, mood) when
        users ask about their data.

        The assistant is RESPONSIVE, not PROACTIVE. It only provides task/priority
        information when the user explicitly asks for it.

        Args:
            message: User's message
            conversation: The conversation object
            page_context: Optional dict with 'url', 'module', 'page_title' for context-aware responses
        """
        # Get conversation history
        history = conversation.messages.order_by('-created_at')[:10]

        # Build system prompt with coaching style (no time context by default - too pushy)
        system_prompt = self._build_system_prompt(include_time_context=False)

        # Check if user is asking about tasks/priorities - only then include state data
        message_lower = message.lower()
        is_asking_about_tasks = any(phrase in message_lower for phrase in [
            'what do i have', 'what\'s left', 'what tasks', 'what should i',
            'my priorities', 'my tasks', 'overdue', 'due today', 'to do',
            'what remains', 'what still needs', 'focus on', 'left to do',
            'what needs to be done', 'what\'s remaining', 'how many tasks',
        ])

        if is_asking_about_tasks:
            # User is asking about tasks - include full state context
            state = self.assess_current_state()
            time_context = self._get_time_context()
            tasks = state.get('tasks', {})
            remaining_tasks = tasks.get('due_today', 0) + tasks.get('overdue', 0)
            system_prompt += f"""

USER IS ASKING ABOUT THEIR TASKS/PRIORITIES - provide this information:
- Tasks REMAINING today: {remaining_tasks} ({tasks.get('overdue', 0)} overdue, {tasks.get('due_today', 0)} due today)
- Active goals needing progress: {state.get('goals', {}).get('active', 0)}
- Journal streak: {state.get('journal', {}).get('streak', 0)} days
- Active prayers: {state.get('faith', {}).get('active_prayers', 0)}
- Time remaining in day: ~{time_context['hours_remaining']} hours until bedtime
"""
            if state.get('ai_assessment'):
                system_prompt += f"\nASSESSMENT:\n{state['ai_assessment']}"

        # Add page context if provided - helps assistant give context-aware responses
        if page_context:
            page_url = page_context.get('url', '')
            page_module = page_context.get('module', '')
            page_title = page_context.get('page_title', '')
            page_content = page_context.get('page_content')

            context_parts = []
            if page_title:
                context_parts.append(f"Page: {page_title}")
            if page_module:
                context_parts.append(f"Module: {page_module}")

            # Build rich content description based on page type
            content_description = ""
            if page_content:
                content_type = page_content.get('type', '')

                if content_type == 'reading_plan_progress':
                    content_description = "\nREADING PLAN CONTENT (user is viewing this):\n"
                    if page_content.get('current_day'):
                        content_description += f"- {page_content['current_day']}\n"
                    if page_content.get('reading_title'):
                        content_description += f"- Theme: {page_content['reading_title']}\n"
                    if page_content.get('scriptures'):
                        content_description += f"- Scriptures: {', '.join(page_content['scriptures'])}\n"
                    if page_content.get('devotional'):
                        content_description += f"- Devotional: {page_content['devotional'][:300]}...\n" if len(page_content.get('devotional', '')) > 300 else f"- Devotional: {page_content['devotional']}\n"
                    if page_content.get('reflection_prompt'):
                        content_description += f"- Reflection Question: {page_content['reflection_prompt']}\n"
                    if page_content.get('progress'):
                        content_description += f"- Progress: {page_content['progress']}\n"

                elif content_type == 'journal_entry':
                    content_description = "\nJOURNAL ENTRY (user is viewing this):\n"
                    if page_content.get('title'):
                        content_description += f"- Title: {page_content['title']}\n"
                    if page_content.get('mood'):
                        content_description += f"- Mood: {page_content['mood']}\n"
                    if page_content.get('body'):
                        content_description += f"- Content: {page_content['body']}\n"

                elif content_type == 'task':
                    content_description = "\nTASK (user is viewing this):\n"
                    if page_content.get('title'):
                        content_description += f"- Title: {page_content['title']}\n"
                    if page_content.get('due_date'):
                        content_description += f"- Due: {page_content['due_date']}\n"
                    if page_content.get('description'):
                        content_description += f"- Description: {page_content['description']}\n"

                elif content_type == 'goal':
                    content_description = "\nGOAL (user is viewing this):\n"
                    if page_content.get('title'):
                        content_description += f"- Goal: {page_content['title']}\n"
                    if page_content.get('why_it_matters'):
                        content_description += f"- Why it matters: {page_content['why_it_matters']}\n"

                elif content_type == 'prayer_request':
                    content_description = "\nPRAYER REQUEST (user is viewing this):\n"
                    if page_content.get('title'):
                        content_description += f"- Prayer: {page_content['title']}\n"
                    if page_content.get('content'):
                        content_description += f"- Details: {page_content['content']}\n"

                elif content_type == 'fasting':
                    content_description = "\nFASTING PAGE (user is viewing this):\n"
                    if page_content.get('active_fast_duration'):
                        content_description += f"- Active fast duration: {page_content['active_fast_duration']}\n"
                        if page_content.get('active_fast_type'):
                            content_description += f"- Fast type: {page_content['active_fast_type']}\n"
                    if page_content.get('fasting_history'):
                        content_description += "- Completed fasts shown on page:\n"
                        for entry in page_content['fasting_history'][:10]:  # Limit to 10 entries
                            content_description += f"  * {entry.get('date', '')}: {entry.get('duration', '')} ({entry.get('type', '')})\n"

                elif content_type == 'health':
                    content_description = "\nHEALTH PAGE (user is viewing this):\n"
                    if page_content.get('current_weight'):
                        content_description += f"- Current weight: {page_content['current_weight']}\n"
                    if page_content.get('workout_info'):
                        content_description += f"- Workout info: {page_content['workout_info']}\n"

            if context_parts or content_description:
                system_prompt += f"""
PAGE CONTEXT (where the user is currently viewing):
{chr(10).join('- ' + p for p in context_parts) if context_parts else ''}
{content_description}
When the user asks about "this page", "this scripture", "this entry", etc., they are referring to the content above.
Use this context to provide relevant, contextual help. For scripture questions, explain the passage and its meaning.
"""

        # Process message for personal data queries (weight, journal, medication, food, mood)
        # This will inject relevant data context if the user asks about their personal data
        personal_data_result = process_assistant_message(
            user=self.user,
            message=message,
            base_system_prompt=system_prompt,
        )

        # If personal data was found, use the enhanced prompt
        if personal_data_result['is_personal_query'] and personal_data_result['has_data']:
            system_prompt = personal_data_result['system_prompt']
            logger.debug(
                f"Personal data context injected for data types: {personal_data_result['data_types']}"
            )

        # If clarification is needed (data query but no data found), ask the user
        if personal_data_result.get('needs_clarification'):
            # Store the awaiting data type in conversation metadata for follow-up
            conversation.metadata = conversation.metadata or {}
            conversation.metadata['awaiting_data_visibility_confirmation'] = True
            conversation.metadata['awaiting_data_type'] = personal_data_result.get('awaiting_data_type')
            conversation.save(update_fields=['metadata'])

            logger.info(
                f"Asking user to verify data visibility for {personal_data_result.get('awaiting_data_type')}"
            )
            return personal_data_result['clarifying_question']

        # Check if this is a web search query (weather, news, etc.)
        # Handle these with web search before falling back to general AI
        from apps.ai.web_search_service import needs_web_search, search_web, get_user_location

        if needs_web_search(message):
            # Try web search for real-time information
            user_location = get_user_location(self.user)
            web_result = search_web(message, user_location)
            if web_result:
                logger.info(f"Answered query via web search: {message[:50]}...")
                return web_result

        # Build conversation context
        messages_context = ""
        for msg in reversed(list(history)[:5]):
            role = "User" if msg.role == 'user' else "Assistant"
            messages_context += f"{role}: {msg.content}\n"

        user_prompt = f"""Recent conversation:
{messages_context}

User's new message: {message}

Respond as the Dashboard AI Personal Assistant. Answer ONLY what was asked - do not add unsolicited information about tasks, priorities, or what the user should be doing."""

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

    def get_opening_message(self, is_first_visit: bool = None) -> Dict[str, Any]:
        """
        Generate the opening message when user opens the app.

        The dashboard check-in card (left side) ALWAYS shows the full coaching review:
        - State summary with AI assessment
        - Today's priorities
        - Nudges for items needing attention

        The is_first_visit flag is tracked for informational purposes but doesn't
        affect what's shown in the check-in card. The coaching review should always
        be visible when viewing the assistant dashboard.

        Note: The CHAT (right side) is separate and should be interactive/responsive,
        not proactively showing task summaries.

        Args:
            is_first_visit: Override for first visit detection (used by views).
                           If None, will be determined automatically.
        """
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)
        time_context = self._get_time_context()

        # Track first visit of the day for informational purposes
        if is_first_visit is None:
            conversation = self.get_or_create_conversation()
            metadata = conversation.metadata or {}
            last_opening_date = metadata.get('last_opening_shown_date')
            is_first_visit = last_opening_date != str(today)

            # Update the last opening shown date
            if is_first_visit:
                metadata['last_opening_shown_date'] = str(today)
                conversation.metadata = metadata
                conversation.save(update_fields=['metadata'])

        # Always show full coaching check-in on the dashboard card
        # This is the "Good morning, Danny" section with your coach reviewing your status
        state = self.assess_current_state()
        priorities = self.generate_daily_priorities()

        result = {
            'greeting': self._get_greeting(),
            'time_context': time_context,
            'state_summary': state.get('ai_assessment', ''),
            'priorities': list(priorities),
            'celebrations': [],
            'nudges': self._build_nudges(state),
            'reflection_prompt': None,
            'coaching_style': self.coaching_style,
            'is_first_visit': is_first_visit,
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
