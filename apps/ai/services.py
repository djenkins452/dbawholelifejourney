# ==============================================================================
# File: services.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: AI Services - Core OpenAI API wrapper with database-driven prompts
#              and optimized caching for reduced API calls
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-01-01
# Last Updated: 2025-12-31 (Added system prompt caching for optimization)
# ==============================================================================
"""
AI Services for Whole Life Journey - WITH DATABASE-DRIVEN PROMPTS

This module provides AI-powered insights and encouragement based on user data.
It uses OpenAI's API to generate personalized, meaningful feedback.

Both coaching styles AND prompt configurations are now database-driven for flexibility.

Caching Optimizations (2025-12-31):
- System prompts cached by user/style combination (1 hour)
- Coaching style prompts cached (1 hour)
- AIPromptConfig cached (1 hour)
"""
import hashlib
import logging
from typing import Optional
from datetime import timedelta
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Fallback coaching style prompt if database is unavailable
FALLBACK_COACHING_PROMPT = """
Your communication style is SUPPORTIVE PARTNER:
- Be warm but balanced—like a trusted friend walking alongside them
- Gently acknowledge both wins and gaps without judgment
- Offer encouraging nudges, not demands
- Celebrate progress genuinely
- Balance accountability with encouragement
"""

# Fallback system base prompt if database is unavailable
FALLBACK_SYSTEM_BASE = """You are a life coach integrated into "Whole Life Journey," a personal
journaling and life management app. Your role is to provide personalized insights
and encouragement based on the user's data.

Core principles:
- Be specific to their actual data—never generic
- Help users see patterns and growth
- Always maintain dignity and respect
- Never shame, mock, or be condescending"""

# Fallback faith context if database is unavailable
FALLBACK_FAITH_CONTEXT = """
FAITH CONTEXT: The user has faith/spirituality enabled. You may:
- Include occasional Scripture references when naturally relevant
- Reference spiritual growth and God's faithfulness
- Use faith-based encouragement when appropriate
- But keep it natural—don't force it or be preachy"""


# Safe response guidelines when user profile is used
PROFILE_SAFETY_INSTRUCTIONS = """
IMPORTANT SAFETY GUIDELINES:
- Never provide medical, legal, financial, or spiritual advice - only supportive observations
- If the user mentions health conditions, acknowledge supportively but don't diagnose or prescribe
- Maintain respectful, encouraging tone aligned with wholesome values
- If profile content seems concerning, focus on encouragement and suggest professional support
- Never repeat the user's profile information verbatim in responses
"""


class AIService:
    """
    Core AI service for generating insights and encouragement.

    This service is designed to be:
    - Warm and encouraging (never judgmental)
    - Faith-aware (respects user's Faith module setting)
    - Privacy-conscious (processes data, doesn't store prompts)
    - Style-adaptive (gentle, supportive, or direct)
    - Consent-aware (requires explicit user consent for data processing)

    Security Note (C-3): All AI processing methods should verify user consent
    via check_user_consent() before sending data to external AI services.
    """

    def __init__(self):
        self.client = None
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        self._initialize_client()

    @staticmethod
    def check_user_consent(user) -> bool:
        """
        Check if user has consented to AI data processing.

        Security Fix C-3: User must explicitly consent to having their
        personal data (journal entries, health metrics, etc.) processed
        by external AI services (OpenAI).

        Args:
            user: The User model instance

        Returns:
            bool: True if user has consented, False otherwise
        """
        if not hasattr(user, 'preferences'):
            return False
        prefs = user.preferences
        # Both AI must be enabled AND consent must be given
        return prefs.ai_enabled and prefs.ai_data_consent
    
    def _initialize_client(self):
        """Initialize OpenAI client if API key is available."""
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key)
            except ImportError:
                logger.warning("OpenAI package not installed. Run: pip install openai")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
    
    @property
    def is_available(self) -> bool:
        """Check if AI service is available."""
        return self.client is not None
    
    def _get_coaching_style_prompt(self, style: str) -> str:
        """Get the coaching style instructions from database."""
        try:
            from .models import CoachingStyle
            style_obj = CoachingStyle.get_by_key(style)
            if style_obj:
                if style_obj.prompt_instructions:
                    logger.debug(f"Loaded coaching style '{style}' (actual: {style_obj.key})")
                    return "\n" + style_obj.prompt_instructions
                else:
                    logger.warning(f"Coaching style '{style}' has empty prompt_instructions")
            else:
                logger.warning(f"Coaching style '{style}' not found in database")
        except Exception as e:
            logger.warning(f"Could not load coaching style from DB: {e}")

        # Fallback if database unavailable
        logger.info(f"Using fallback coaching prompt for style '{style}'")
        return FALLBACK_COACHING_PROMPT

    def _get_prompt_config(self, prompt_type: str):
        """Get prompt configuration from database."""
        try:
            from .models import AIPromptConfig
            return AIPromptConfig.get_config(prompt_type)
        except Exception as e:
            logger.warning(f"Could not load prompt config from DB: {e}")
            return None

    def _get_system_prompt(self, faith_enabled: bool = False,
                           coaching_style: str = 'supportive',
                           prompt_type: str = None,
                           user_profile: str = None) -> str:
        """Get the base system prompt for AI interactions.

        If prompt_type is provided and exists in database, uses that config.
        Otherwise falls back to system_base config or hardcoded defaults.

        Caching Strategy (Optimization 2025-12-31):
        - Base system prompt + coaching style + faith context is cached
        - User profile is NOT cached (too variable, needs safety processing each time)
        - Cache key: system_prompt_{coaching_style}_{faith_enabled}

        Args:
            faith_enabled: Whether faith context should be included
            coaching_style: The user's preferred coaching style
            prompt_type: Specific prompt type for database lookup
            user_profile: User's personal AI profile for personalization
        """
        # Try to get cached base prompt (without user profile)
        cache_key = f'system_prompt_{coaching_style}_{faith_enabled}'
        base = cache.get(cache_key)

        if base is None:
            # Build the base prompt
            base_config = self._get_prompt_config('system_base')

            if base_config:
                base = base_config.get_full_prompt()
            else:
                # Fallback to hardcoded base
                base = FALLBACK_SYSTEM_BASE

            # Add coaching style
            base += "\n" + self._get_coaching_style_prompt(coaching_style)

            # Add faith context if enabled
            if faith_enabled:
                faith_config = self._get_prompt_config('faith_context')
                if faith_config:
                    base += "\n" + faith_config.system_instructions
                else:
                    base += FALLBACK_FAITH_CONTEXT

            # Cache the base prompt (1 hour)
            cache.set(cache_key, base, 3600)

        # Add user profile context if provided (not cached - varies per user)
        if user_profile:
            from .profile_moderation import build_safe_profile_context
            profile_context = build_safe_profile_context(user_profile)
            if profile_context:
                base += "\n\n" + profile_context
                base += "\n" + PROFILE_SAFETY_INSTRUCTIONS

        return base

    def _get_prompt_with_config(self, prompt_type: str, default_prompt: str,
                                faith_enabled: bool = False,
                                coaching_style: str = 'supportive',
                                user_profile: str = None) -> tuple:
        """Get system prompt and max tokens for a specific prompt type.

        Returns (system_prompt, max_tokens) tuple.
        Uses database config if available, otherwise uses defaults.

        Args:
            prompt_type: The type of prompt to load from database
            default_prompt: Fallback prompt description
            faith_enabled: Whether faith context should be included
            coaching_style: The user's preferred coaching style
            user_profile: User's personal AI profile for personalization
        """
        config = self._get_prompt_config(prompt_type)

        if config:
            # Build system prompt with specific instructions from config
            system = self._get_system_prompt(faith_enabled, coaching_style, prompt_type, user_profile)
            system += "\n\n" + config.get_full_prompt()
            return (system, config.max_tokens)
        else:
            # Use default system prompt
            system = self._get_system_prompt(faith_enabled, coaching_style, user_profile=user_profile)
            return (system, 150)  # Default max tokens
    
    def _call_api(self, system_prompt: str, user_prompt: str, 
                  max_tokens: int = 300) -> Optional[str]:
        """Make an API call to OpenAI."""
        if not self.is_available:
            logger.warning("AI service not available - no API key configured")
            return None
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return None
    
    # =========================================================================
    # JOURNAL INSIGHTS
    # =========================================================================
    
    def analyze_journal_entry(self, entry_text: str, mood: str = None,
                              faith_enabled: bool = False,
                              coaching_style: str = 'supportive') -> Optional[str]:
        """
        Provide a brief, encouraging reflection on a journal entry.
        """
        system, max_tokens = self._get_prompt_with_config(
            'journal_reflection',
            'Provide journal reflection',
            faith_enabled,
            coaching_style
        )

        prompt = f"""The user just wrote this journal entry:

"{entry_text[:1500]}"
{f'Their mood: {mood}' if mood else ''}

Provide a reflection. Acknowledge what they shared
and offer encouragement or insight appropriate to your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)

    def generate_journal_summary(self, entries: list, period: str = "week",
                                  faith_enabled: bool = False,
                                  coaching_style: str = 'supportive') -> Optional[str]:
        """Generate a summary of journal entries over a period."""
        if not entries:
            return None

        system, max_tokens = self._get_prompt_with_config(
            'weekly_summary',
            'Generate journal summary',
            faith_enabled,
            coaching_style
        )

        entry_summaries = []
        for e in entries[:10]:
            summary = f"- {e.get('date', 'Unknown date')}: {e.get('title', 'Untitled')}"
            if e.get('mood'):
                summary += f" (mood: {e['mood']})"
            if e.get('body'):
                summary += f"\n  {e['body'][:200]}..."
            entry_summaries.append(summary)

        prompt = f"""Here are the user's journal entries from the past {period}:

{chr(10).join(entry_summaries)}

Provide a warm, insightful summary that:
1. Notes any themes or patterns you see
2. Acknowledges their journey
3. Offers perspective for the {period} ahead

Match your response to your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)
    
    # =========================================================================
    # DASHBOARD INSIGHTS
    # =========================================================================
    
    def generate_daily_insight(self, user_data: dict,
                               faith_enabled: bool = False,
                               coaching_style: str = 'supportive',
                               user_profile: str = None) -> Optional[str]:
        """Generate a personalized daily insight for the dashboard.

        Args:
            user_data: Dictionary of user activity and status data
            faith_enabled: Whether faith context should be included
            coaching_style: The user's preferred coaching style
            user_profile: User's personal AI profile for personalization
        """
        # Get system prompt and config from database
        system, max_tokens = self._get_prompt_with_config(
            'daily_insight',
            'Generate a personalized dashboard message',
            faith_enabled,
            coaching_style,
            user_profile
        )

        # Build comprehensive context from available data
        context_parts = []

        # ===================
        # ANNUAL DIRECTION & PURPOSE
        # ===================
        if user_data.get('word_of_year'):
            context_parts.append(f"Word of the Year: '{user_data['word_of_year']}'")
        if user_data.get('annual_theme'):
            context_parts.append(f"Annual Theme: {user_data['annual_theme']}")
        if user_data.get('anchor_scripture'):
            context_parts.append(f"Anchor Scripture: {user_data['anchor_scripture']}")

        # Active intentions
        if user_data.get('active_intentions'):
            intentions = ', '.join(user_data['active_intentions'][:3])
            context_parts.append(f"Trying to embody: {intentions}")

        # Goals with details
        if user_data.get('goals_list'):
            for goal in user_data['goals_list'][:2]:
                domain = goal.get('domain__name', '')
                title = goal.get('title', '')
                why = goal.get('why_it_matters', '')[:50]
                if domain:
                    context_parts.append(f"Goal ({domain}): {title}")
                else:
                    context_parts.append(f"Goal: {title}")
        elif user_data.get('active_goals', 0) > 0:
            context_parts.append(f"Working on {user_data['active_goals']} life goals")

        # ===================
        # JOURNAL ACTIVITY
        # ===================
        if user_data.get('journal_count_week', 0) > 0:
            context_parts.append(f"Journaled {user_data['journal_count_week']} times this week")

        if user_data.get('last_journal_date'):
            today = user_data.get('today', timezone.now().date())
            days_ago = (today - user_data['last_journal_date']).days
            if days_ago == 0:
                context_parts.append("Wrote in journal today")
            elif days_ago == 1:
                context_parts.append("Last journaled yesterday")
            elif days_ago > 3:
                context_parts.append(f"Haven't journaled in {days_ago} days")

        if user_data.get('current_streak', 0) > 1:
            context_parts.append(f"On a {user_data['current_streak']}-day journal streak")

        # ===================
        # TASK & PROJECT STATUS
        # ===================
        if user_data.get('completed_tasks_today', 0) > 0:
            context_parts.append(f"Completed {user_data['completed_tasks_today']} tasks today")

        if user_data.get('tasks_due_today', 0) > 0:
            context_parts.append(f"{user_data['tasks_due_today']} tasks due today")

        if user_data.get('overdue_tasks', 0) > 0:
            context_parts.append(f"{user_data['overdue_tasks']} overdue tasks need attention")

        if user_data.get('active_projects', 0) > 0:
            context_parts.append(f"{user_data['active_projects']} active projects")

        if user_data.get('priority_projects'):
            for proj in user_data['priority_projects']:
                context_parts.append(f"Priority project: {proj['title']} ({proj['progress']}% complete)")

        if user_data.get('events_today', 0) > 0:
            context_parts.append(f"{user_data['events_today']} events scheduled today")

        # ===================
        # FAITH CONTEXT
        # ===================
        if faith_enabled:
            if user_data.get('active_prayers', 0) > 0:
                context_parts.append(f"Tracking {user_data['active_prayers']} active prayers")
            if user_data.get('answered_prayers_month', 0) > 0:
                context_parts.append(f"{user_data['answered_prayers_month']} prayers answered this month")
            if user_data.get('memory_verse'):
                mv = user_data['memory_verse']
                context_parts.append(f"Memorizing: {mv['reference']}")
            if user_data.get('studying_scripture'):
                refs = ', '.join(user_data['studying_scripture'][:2])
                context_parts.append(f"Recently studied: {refs}")

        # ===================
        # HEALTH STATUS
        # ===================
        if user_data.get('weight_trend'):
            trend = user_data['weight_trend']
            if trend == 'down':
                context_parts.append("Weight trending down recently")
            elif trend == 'up':
                context_parts.append("Weight trending up recently")

        if user_data.get('weight_goal') and user_data.get('weight_remaining'):
            remaining = abs(user_data['weight_remaining'])
            direction = user_data.get('weight_direction', 'lose')
            if remaining > 0:
                context_parts.append(f"{remaining} lbs to go to reach weight goal")

        if user_data.get('fasting_active'):
            hours = user_data.get('fasting_hours', 0)
            if hours:
                context_parts.append(f"Currently fasting ({hours:.1f} hours in)")
            else:
                context_parts.append("Currently in a fasting window")

        if user_data.get('calories_today'):
            cal = user_data['calories_today']
            remaining = user_data.get('calories_remaining', 0)
            if remaining > 0:
                context_parts.append(f"Logged {cal} calories today ({remaining} remaining)")

        if user_data.get('workouts_this_week', 0) > 0:
            context_parts.append(f"{user_data['workouts_this_week']} workouts this week")
        elif user_data.get('days_since_workout') is not None and user_data['days_since_workout'] > 3:
            context_parts.append(f"No workout in {user_data['days_since_workout']} days")

        if user_data.get('recent_prs_count', 0) > 0:
            context_parts.append(f"Set {user_data['recent_prs_count']} personal records this month")

        if user_data.get('medicine_adherence_rate') is not None:
            rate = user_data['medicine_adherence_rate']
            if rate < 80:
                context_parts.append(f"Medicine adherence at {rate}% this week")
            elif rate >= 95:
                context_parts.append(f"Excellent medicine adherence ({rate}%)")

        if user_data.get('medicines_need_refill', 0) > 0:
            context_parts.append(f"{user_data['medicines_need_refill']} medicines need refill soon")

        if not context_parts:
            context_parts.append("Just getting started with their journey")

        prompt = f"""Based on this user's comprehensive life data:
{chr(10).join('- ' + p for p in context_parts)}

Generate a personalized, meaningful message for their dashboard.
Consider their Word of the Year, goals, and current progress.
Be specific to their situation. Match your coaching style perfectly.
Keep it concise but personal - 2-3 sentences max."""

        return self._call_api(system, prompt, max_tokens=max_tokens)
    
    def generate_accountability_nudge(self, gap_data: dict,
                                      faith_enabled: bool = False,
                                      coaching_style: str = 'supportive') -> Optional[str]:
        """
        Generate a nudge for something the user has been neglecting.

        Args:
            gap_data: Dict with info about what's been missed:
                - gap_type: 'journal', 'goal', 'task', 'health', etc.
                - days_since: days since last activity
                - item_name: specific item name if applicable
                - user_stated_importance: what user said about why it matters
        """
        system, max_tokens = self._get_prompt_with_config(
            'accountability_nudge',
            'Generate a gentle nudge',
            faith_enabled,
            coaching_style
        )

        gap_type = gap_data.get('gap_type', 'activity')
        days_since = gap_data.get('days_since', 0)
        item_name = gap_data.get('item_name', '')
        importance = gap_data.get('user_stated_importance', '')

        prompt = f"""The user has a gap in their {gap_type}:
- Days since last activity: {days_since}
{f'- Specific item: {item_name}' if item_name else ''}
{f'- They previously said this matters because: {importance}' if importance else ''}

Generate a nudge that acknowledges this gap.
Match your coaching style exactly—this is important for how you frame it."""

        return self._call_api(system, prompt, max_tokens=max_tokens)
    
    def generate_celebration(self, achievement_data: dict,
                             faith_enabled: bool = False,
                             coaching_style: str = 'supportive') -> Optional[str]:
        """
        Generate a celebration message for an achievement.

        Args:
            achievement_data: Dict with:
                - achievement_type: 'streak', 'goal_complete', 'milestone', etc.
                - details: specific details about what was achieved
                - streak_count: if applicable
        """
        system, max_tokens = self._get_prompt_with_config(
            'celebration',
            'Generate a celebration message',
            faith_enabled,
            coaching_style
        )

        prompt = f"""The user just achieved something:
- Type: {achievement_data.get('achievement_type', 'milestone')}
- Details: {achievement_data.get('details', 'Completed something meaningful')}
{f"- Streak count: {achievement_data.get('streak_count')}" if achievement_data.get('streak_count') else ''}

Generate a celebration message.
Match your coaching style—even Direct Coach should acknowledge wins warmly."""

        return self._call_api(system, prompt, max_tokens=max_tokens)
    
    # =========================================================================
    # GOAL & PURPOSE INSIGHTS
    # =========================================================================
    
    def analyze_goal_progress(self, goal_data: dict,
                              faith_enabled: bool = False,
                              coaching_style: str = 'supportive') -> Optional[str]:
        """Provide encouragement on goal progress."""
        system, max_tokens = self._get_prompt_with_config(
            'goal_progress',
            'Provide goal progress feedback',
            faith_enabled,
            coaching_style
        )

        prompt = f"""The user has this life goal:
Title: {goal_data.get('title', 'Untitled goal')}
Description: {goal_data.get('description', 'No description')[:500]}
Timeframe: {goal_data.get('timeframe', 'Ongoing')}
Started: {goal_data.get('created_date', 'Recently')}
Progress notes: {goal_data.get('progress_notes', 'None yet')[:300]}

Provide feedback about their goal journey.
Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)
    
    # =========================================================================
    # HEALTH INSIGHTS
    # =========================================================================
    
    def generate_health_encouragement(self, health_data: dict,
                                       faith_enabled: bool = False,
                                       coaching_style: str = 'supportive') -> Optional[str]:
        """Generate encouraging health insight."""
        system, max_tokens = self._get_prompt_with_config(
            'health_encouragement',
            'Generate health encouragement',
            faith_enabled,
            coaching_style
        )

        context = []
        if health_data.get('weight_entries_month', 0) > 0:
            context.append(f"Logged weight {health_data['weight_entries_month']} times this month")
        if health_data.get('weight_change'):
            direction = "down" if health_data['weight_change'] < 0 else "up"
            context.append(f"Weight is {direction} {abs(health_data['weight_change'])} lbs this month")
        if health_data.get('fasts_completed_month', 0) > 0:
            context.append(f"Completed {health_data['fasts_completed_month']} fasts this month")
        if health_data.get('avg_fast_hours'):
            context.append(f"Average fast length: {health_data['avg_fast_hours']} hours")

        if not context:
            return None

        prompt = f"""User's health tracking this month:
{chr(10).join('- ' + c for c in context)}

Provide feedback about their health journey.
Focus on consistency and self-care. Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)
    
    # =========================================================================
    # FAITH INSIGHTS
    # =========================================================================
    
    def generate_prayer_encouragement(self, prayer_data: dict,
                                       coaching_style: str = 'supportive') -> Optional[str]:
        """Generate encouragement around prayer life."""
        system, max_tokens = self._get_prompt_with_config(
            'prayer_encouragement',
            'Generate prayer encouragement',
            faith_enabled=True,
            coaching_style=coaching_style
        )

        context = []
        if prayer_data.get('active_count', 0) > 0:
            context.append(f"Tracking {prayer_data['active_count']} active prayers")
        if prayer_data.get('answered_count', 0) > 0:
            context.append(f"{prayer_data['answered_count']} prayers answered")
        if prayer_data.get('recent_themes'):
            context.append(f"Recent prayer themes: {', '.join(prayer_data['recent_themes'][:3])}")

        prompt = f"""User's prayer life:
{chr(10).join('- ' + c for c in context) if context else '- Just starting their prayer tracking'}

Provide encouragement about their prayer journey.
You may include a short, relevant Scripture reference if it fits naturally.
Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=max_tokens)


# Singleton instance
ai_service = AIService()
