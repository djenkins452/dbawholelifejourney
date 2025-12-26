"""
AI Services for Whole Life Journey - WITH COACHING STYLE SUPPORT

This module provides AI-powered insights and encouragement based on user data.
It uses OpenAI's API to generate personalized, meaningful feedback.

UPDATE: Replace your existing apps/ai/services.py with this file.
"""
import logging
from typing import Optional
from datetime import timedelta
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class AIService:
    """
    Core AI service for generating insights and encouragement.
    
    This service is designed to be:
    - Warm and encouraging (never judgmental)
    - Faith-aware (respects user's Faith module setting)
    - Privacy-conscious (processes data, doesn't store prompts)
    - Style-adaptive (gentle, supportive, or direct)
    """
    
    def __init__(self):
        self.client = None
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        self._initialize_client()
    
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
        """Get the coaching style instructions based on user preference."""
        
        styles = {
            'gentle': """
Your communication style is GENTLE GUIDE:
- Be soft, nurturing, and extremely patient
- Never pressure or create urgency
- Always affirm effort, no matter how small
- Use phrases like "whenever you're ready", "no pressure", "take your time"
- Frame suggestions as gentle invitations, not recommendations
- If noting gaps or struggles, be very tender and validating
- Focus on self-compassion and grace
- Celebrate every tiny win as meaningful""",
            
            'supportive': """
Your communication style is SUPPORTIVE PARTNER:
- Be warm but balanced—like a trusted friend walking alongside them
- Gently acknowledge both wins and gaps without judgment
- Offer encouraging nudges, not demands
- Use phrases like "I noticed...", "you might consider...", "how about..."
- Celebrate progress genuinely
- When noting missed goals or gaps, be kind but honest
- Balance accountability with encouragement
- Help them see patterns without lecturing""",
            
            'direct': """
Your communication style is DIRECT COACH:
- Be clear, straightforward, and action-oriented
- Don't sugarcoat—tell it like it is, but never be cruel
- Use direct language: "Do this", "You need to...", "Stop waiting and..."
- Push them toward action
- Call out excuses gently but firmly
- Focus on what they CAN control
- When they've missed goals, acknowledge it directly and redirect to action
- Keep it brief and punchy—no rambling
- Challenge them to be their best"""
        }
        
        return styles.get(style, styles['supportive'])
    
    def _get_system_prompt(self, faith_enabled: bool = False, 
                           coaching_style: str = 'supportive') -> str:
        """Get the base system prompt for AI interactions."""
        
        base = """You are a life coach integrated into "Whole Life Journey," a personal 
journaling and life management app. Your role is to provide personalized insights 
and encouragement based on the user's data.

Core principles:
- Be concise (2-4 sentences unless more detail is requested)
- Be specific to their actual data—never generic
- Help users see patterns and growth
- Always maintain dignity and respect
- Never shame, mock, or be condescending"""

        # Add coaching style
        base += "\n" + self._get_coaching_style_prompt(coaching_style)

        # Add faith context if enabled
        if faith_enabled:
            base += """

FAITH CONTEXT: The user has faith/spirituality enabled. You may:
- Include occasional Scripture references when naturally relevant
- Reference spiritual growth and God's faithfulness
- Use faith-based encouragement when appropriate
- But keep it natural—don't force it or be preachy"""
        
        return base
    
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
        system = self._get_system_prompt(faith_enabled, coaching_style)
        
        prompt = f"""The user just wrote this journal entry:

"{entry_text[:1500]}"
{f'Their mood: {mood}' if mood else ''}

Provide a brief (2-3 sentences) reflection. Acknowledge what they shared 
and offer encouragement or insight appropriate to your coaching style."""

        return self._call_api(system, prompt, max_tokens=150)
    
    def generate_journal_summary(self, entries: list, period: str = "week",
                                  faith_enabled: bool = False,
                                  coaching_style: str = 'supportive') -> Optional[str]:
        """Generate a summary of journal entries over a period."""
        if not entries:
            return None
        
        system = self._get_system_prompt(faith_enabled, coaching_style)
        
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

Provide a warm, insightful summary (3-5 sentences) that:
1. Notes any themes or patterns you see
2. Acknowledges their journey
3. Offers perspective for the {period} ahead

Match your response to your coaching style."""

        return self._call_api(system, prompt, max_tokens=250)
    
    # =========================================================================
    # DASHBOARD INSIGHTS
    # =========================================================================
    
    def generate_daily_insight(self, user_data: dict, 
                               faith_enabled: bool = False,
                               coaching_style: str = 'supportive') -> Optional[str]:
        """Generate a personalized daily insight for the dashboard."""
        system = self._get_system_prompt(faith_enabled, coaching_style)
        
        # Build context from available data
        context_parts = []
        
        if user_data.get('journal_count_week', 0) > 0:
            context_parts.append(f"Journaled {user_data['journal_count_week']} times this week")
        
        if user_data.get('last_journal_date'):
            days_ago = (timezone.now().date() - user_data['last_journal_date']).days
            if days_ago == 0:
                context_parts.append("Wrote in journal today")
            elif days_ago == 1:
                context_parts.append("Last journaled yesterday")
            elif days_ago > 3:
                context_parts.append(f"Haven't journaled in {days_ago} days")
        
        if user_data.get('current_streak', 0) > 1:
            context_parts.append(f"On a {user_data['current_streak']}-day journal streak")
        
        if faith_enabled and user_data.get('active_prayers', 0) > 0:
            context_parts.append(f"Tracking {user_data['active_prayers']} active prayers")
        
        if user_data.get('active_goals', 0) > 0:
            context_parts.append(f"Working on {user_data['active_goals']} life goals")
        
        if user_data.get('completed_tasks_today', 0) > 0:
            context_parts.append(f"Completed {user_data['completed_tasks_today']} tasks today")
        
        if user_data.get('overdue_tasks', 0) > 0:
            context_parts.append(f"Has {user_data['overdue_tasks']} overdue tasks")
        
        if user_data.get('weight_trend') == 'down':
            context_parts.append("Weight trending down recently")
        
        if user_data.get('fasting_active'):
            context_parts.append("Currently in a fasting window")
        
        if not context_parts:
            context_parts.append("Just getting started with their journey")
        
        prompt = f"""Based on this user's current activity and status:
{chr(10).join('- ' + p for p in context_parts)}

Generate a personalized message (2-3 sentences) for their dashboard.
Be specific to their situation. Match your coaching style perfectly."""

        return self._call_api(system, prompt, max_tokens=150)
    
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
        system = self._get_system_prompt(faith_enabled, coaching_style)
        
        gap_type = gap_data.get('gap_type', 'activity')
        days_since = gap_data.get('days_since', 0)
        item_name = gap_data.get('item_name', '')
        importance = gap_data.get('user_stated_importance', '')
        
        prompt = f"""The user has a gap in their {gap_type}:
- Days since last activity: {days_since}
{f'- Specific item: {item_name}' if item_name else ''}
{f'- They previously said this matters because: {importance}' if importance else ''}

Generate a brief (1-2 sentences) nudge that acknowledges this gap.
Match your coaching style exactly—this is important for how you frame it."""

        return self._call_api(system, prompt, max_tokens=100)
    
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
        system = self._get_system_prompt(faith_enabled, coaching_style)
        
        prompt = f"""The user just achieved something:
- Type: {achievement_data.get('achievement_type', 'milestone')}
- Details: {achievement_data.get('details', 'Completed something meaningful')}
{f"- Streak count: {achievement_data.get('streak_count')}" if achievement_data.get('streak_count') else ''}

Generate a brief (1-2 sentences) celebration message.
Match your coaching style—even Direct Coach should acknowledge wins warmly."""

        return self._call_api(system, prompt, max_tokens=100)
    
    # =========================================================================
    # GOAL & PURPOSE INSIGHTS
    # =========================================================================
    
    def analyze_goal_progress(self, goal_data: dict, 
                              faith_enabled: bool = False,
                              coaching_style: str = 'supportive') -> Optional[str]:
        """Provide encouragement on goal progress."""
        system = self._get_system_prompt(faith_enabled, coaching_style)
        
        prompt = f"""The user has this life goal:
Title: {goal_data.get('title', 'Untitled goal')}
Description: {goal_data.get('description', 'No description')[:500]}
Timeframe: {goal_data.get('timeframe', 'Ongoing')}
Started: {goal_data.get('created_date', 'Recently')}
Progress notes: {goal_data.get('progress_notes', 'None yet')[:300]}

Provide brief (2-3 sentences) feedback about their goal journey.
Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=150)
    
    # =========================================================================
    # HEALTH INSIGHTS
    # =========================================================================
    
    def generate_health_encouragement(self, health_data: dict,
                                       faith_enabled: bool = False,
                                       coaching_style: str = 'supportive') -> Optional[str]:
        """Generate encouraging health insight."""
        system = self._get_system_prompt(faith_enabled, coaching_style)
        
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

Provide brief (2 sentences) feedback about their health journey.
Focus on consistency and self-care. Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=100)
    
    # =========================================================================
    # FAITH INSIGHTS
    # =========================================================================
    
    def generate_prayer_encouragement(self, prayer_data: dict,
                                       coaching_style: str = 'supportive') -> Optional[str]:
        """Generate encouragement around prayer life."""
        system = self._get_system_prompt(faith_enabled=True, coaching_style=coaching_style)
        
        context = []
        if prayer_data.get('active_count', 0) > 0:
            context.append(f"Tracking {prayer_data['active_count']} active prayers")
        if prayer_data.get('answered_count', 0) > 0:
            context.append(f"{prayer_data['answered_count']} prayers answered")
        if prayer_data.get('recent_themes'):
            context.append(f"Recent prayer themes: {', '.join(prayer_data['recent_themes'][:3])}")
        
        prompt = f"""User's prayer life:
{chr(10).join('- ' + c for c in context) if context else '- Just starting their prayer tracking'}

Provide brief (2 sentences) encouragement about their prayer journey.
You may include a short, relevant Scripture reference if it fits naturally.
Match your coaching style."""

        return self._call_api(system, prompt, max_tokens=120)


# Singleton instance
ai_service = AIService()
