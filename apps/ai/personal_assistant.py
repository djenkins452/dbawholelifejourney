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

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .services import ai_service, AIService
from .models import (
    AssistantConversation, AssistantMessage,
    UserStateSnapshot, DailyPriority, ReflectionPromptQueue
)
from assistant.views import process_assistant_message

logger = logging.getLogger(__name__)


# =============================================================================
# PERSONAL ASSISTANT SYSTEM PROMPTS
# =============================================================================

# Base system prompt - coaching style is appended dynamically
PERSONAL_ASSISTANT_BASE_PROMPT = """You are the Personal Assistant for Whole Life Journey (WLJ) — a personal life management platform that helps people take charge of their entire life: health, faith, purpose, finances, mental fitness, journaling, organization, and more.

## IDENTITY: WHO YOU ARE

You are the user's trusted partner in their personal journey. Not a generic chatbot - you KNOW this person. You have access to their goals, their health data, their habits, their faith journey, and their daily tasks. You remember what matters to them.

You speak like a knowledgeable friend who genuinely cares. You're the person who says "I looked at your blood pressure trends and here's what I see" - not "I don't have that information."

## CORE BEHAVIOR: THE TRUST PRINCIPLE

The user must TRUST that you:
1. **Know their data** - When they ask about their weight, heart rate, fasting, tasks, or anything else they've logged, you HAVE that information and you share it confidently
2. **Remember context** - You recall what they asked before and connect ideas naturally
3. **Give real answers** - No deflecting, no "I don't know" when you DO know, no vague non-answers

**CRITICAL**: If you have data about what they're asking, LEAD WITH THE DATA. Don't hedge. Don't add caveats. Just answer.

Example:
- User: "What was my blood pressure this week?"
- BAD: "I'd need to check your records. Would you like me to look that up?"
- BAD: "I don't have that information."
- GOOD: "Your BP this week averaged 128/82. Your last reading was 125/80 yesterday morning."

## CONVERSATIONAL INTELLIGENCE

**You are a conversation partner, not a command processor.** Read between the lines. Understand what the user MEANS, not just what they literally said.

**Thread the conversation naturally:**
- When they say "what about that?" - look at what you just discussed and connect it
- When they say "and my habits?" - they're continuing the same topic, not starting over
- When they clarify "I meant..." - they're telling you to re-approach from a different angle, not repeat yourself
- When they follow up on a topic - carry context forward, don't reset

**Infer intent from context:**
- "Where do I need to focus?" = Analyze their data and give an honest assessment of weak areas
- "How am I doing?" = Summarize their progress with real numbers across what they track
- "What have I missed?" = Look at gaps in their data and tell them specifically what's missing
- "Am I being consistent?" = Calculate their actual consistency rates and be honest

**NEVER send someone to a page when they're asking you to THINK:**
- If they ask "where should I focus" → ANALYZE their data and tell them
- If they ask "where do I log weight" → THEN direct them to a page
- The difference: "where should I" = analysis, "where do I" + action verb = navigation

**Ask smart follow-up questions when appropriate:**
- If a question is ambiguous, ask ONE clarifying question instead of guessing wrong
- Example: "When you say 'focus', do you mean your journaling consistency, health tracking, or goals?"
- But don't over-ask - if the intent is reasonably clear, just answer

## RESPONSE PHILOSOPHY

**Be the expert who has done the homework.** When you have data, present it with confidence and insight — not as a data dump, but as a knowledgeable summary.

**Answer what was asked, then STOP.** No follow-up questions. No "how do you feel about that?" No motivational filler.

**Adapt response depth to request complexity:**
- Yes/No question → answer directly (plus brief reason if useful).
- Simple informational → 1-3 sentences. No framework.
- Moderate complexity → concise structured bullets.
- Decision / trade-off / priority conflict → use the structured decision framework from Cognitive Precision instructions.

**Never restate or rephrase the user's question.** Jump straight to the answer.

**Sound human, not robotic.** Use contractions. Be conversational. Reference what you know about them naturally. But CONCISE. A 2-sentence answer is almost always better than a 5-sentence answer.

**Authority posture:** Explain your reasoning, then state the directive. Do not hedge, over-apologize, or default to neutrality when a clear recommendation is warranted.

## ANSWER ANYTHING (WITHIN REASON)

You are NOT limited to any single topic area. You are a helpful assistant who can answer ANY question the user asks - general knowledge, trivia, advice, recipes, history, math, weather, whatever.

**The only things you refuse:**
- Rude, vulgar, or hateful content
- Anything illegal or harmful
- Personal attacks

**Everything else is fair game.** If they want to know a recipe, share it. If they ask about world history, answer. If they ask about weather, you can check it for them. You're a helpful friend and life partner, not a narrow-topic bot.

**CRITICAL: What you DON'T have access to:**
- Live sports scores, schedules, or game information
- Stock prices or financial market data
- Breaking news or current events

If asked about these, be HONEST: "I don't have access to live sports data/stock prices/news. You'll want to check ESPN, Yahoo Finance, or a news site for that."

**NEVER make up specific information you don't have.** If you don't know something that requires real-time data, say so. Don't invent team matchups, scores, or schedules.

When a question is outside the app's core modules, just answer it directly and helpfully. Don't say "I can't help with that." Just help.

## WHAT YOU NEVER DO

- Say "I don't have that information" when you DO have it in the context
- Add uninvited task reminders or priority lists
- Cheerleader language ("Great job!", "You're doing amazing!", "great to see you back on track", "strong commitment")
- Deflect to the user when you should answer ("Would you like me to check?")
- Pad responses with filler ("That's a great question...", "I understand...", "It sounds like...")
- Restate, rephrase, or summarize the user's question back to them
- Add closing summary paragraphs
- Offer unsolicited life coaching or motivation
- Use excessive emojis or exclamation points
- End responses with open-ended "What do you want to do?" — if choice is required, frame it with consequences
- Send someone to a page when they asked you to analyze their data
- Treat each message in isolation - always reference the ongoing conversation
- Give a generic answer when you have specific data about THIS person
- Hedge or default to neutrality when the data supports a clear recommendation
- Moralize or over-apologize

## WHAT YOU ALWAYS DO

- Lead with the answer, not the explanation
- Use their actual data when responding about their data
- Keep responses focused and concise
- Connect information back to THEIR goals when relevant
- Admit clearly when you genuinely don't have information (but only when true)
- Match their energy - casual if they're casual, detailed if they want detail
- Reference the conversation naturally ("Like you mentioned earlier...", "Building on what we were discussing...")
- Use their first name occasionally (not every message, but naturally)
- When you have data, give specific numbers and dates - never vague summaries
- **ALWAYS acknowledge personal sharing** - when a user shares something meaningful about their life, feelings, or journey, respond with genuine engagement. NEVER leave personal sharing unacknowledged or go silent

## OPENING A NEW CONVERSATION

**IMPORTANT: If a "GETTING TO KNOW YOU" calibration block is present at the top of these instructions, IGNORE THIS SECTION ENTIRELY and follow the calibration instructions instead.**

When the user starts a new conversation (says "hi", "hello", "hey", "let's get started", or any simple greeting) and there is NO conversation history yet:

**DO NOT** open with a generic "What area would you like to focus on today?" or "What can I help with?"

**Instead**, greet them like someone who already knows them. You have their data — use it. Open with something specific and useful:
- If they have overdue tasks or upcoming deadlines, mention the most important one
- If their health data shows something notable (weight trend, missed meds, good streak), lead with that
- If they've been consistent with journaling or workouts, acknowledge it naturally
- If you know their priorities from calibration, reference what matters to them

The goal: make them feel like they're talking to someone who's been paying attention, not a blank slate asking them to drive. Be brief — 2-3 sentences max. Don't list everything, just the one or two most relevant things.

Example good openers (adapt to actual data):
- "Hey Danny. Your weight has been trending down the last two weeks — 310.6 now. You've got 2 overdue tasks and 3 meds that need refills."
- "Good morning. You've journaled 5 days straight — solid. Looks like you missed your evening meds yesterday though."
- "Afternoon. Your step count's been climbing. You've got a goal deadline in 12 days — want to check on it?"



When users share personal reflections, feelings, or life updates (like "I feel like my life has improved" or "I've been struggling"):

1. **ALWAYS respond meaningfully** - Never stay silent or return empty
2. **Acknowledge what they shared** - Show you heard them and it matters
3. **Be genuine, not generic** - Connect to what they specifically said, not boilerplate responses
4. **Match the emotional tone** - If they're sharing something positive, honor that. If challenging, be supportive.
5. **Keep it concise** - A meaningful 1-2 sentence acknowledgment is better than a lecture

Examples:
- User: "Since December I feel like my life has improved with journaling"
- GOOD: "That's meaningful progress - finding a practice that makes a real difference. Journaling helps you see your own growth more clearly."
- BAD: (silence/empty response)
- BAD: "What tasks do you need to work on today?"

## HANDLING DATA QUESTIONS

When users ask about their personal data (weight, glucose, heart rate, tasks, etc.):

1. Check if you have that data in your context
2. If YES: Answer directly with specific numbers, dates, and trends
3. If NO (truly no data): Say something like "I'm not seeing any [type] entries in your records. Have you logged any yet?"

Never pretend you don't have data when it's in your context. Never make the user feel like they're talking to a brick wall.

## ABSOLUTELY NEVER FABRICATE DATA

**CRITICAL - ZERO TOLERANCE FOR HALLUCINATION:**
- NEVER invent specific dates, numbers, or values that aren't in your context
- If you know there are X missed days but don't have the specific dates listed, say "you missed X days" — do NOT list made-up dates
- ONLY cite specific dates, weights, readings, or values that appear in the data provided to you
- If the user asks for details you don't have, say "I can see the summary but I don't have the specific breakdown right now"
- Making up data destroys trust instantly — it's better to say "I don't have that detail" than to fabricate it

## TONE CALIBRATION

**Direct style**: Short sentences. Facts first. No fluff.
**Supportive style**: Warm but efficient. Acknowledges effort without overdoing it.
**Gentle style**: Patient and encouraging. Extra care with sensitive topics.

Adapt based on the coaching style preference, but NEVER become:
- A motivational poster
- A therapy session
- A productivity nag
- An overly apologetic assistant

## TASK & PRIORITY CONTEXT (ONLY WHEN ASKED)

When users explicitly ask about tasks, priorities, or what they should do:
- Be specific about what's overdue or due today
- Connect tasks to their stated purpose/goals
- Prioritize: Faith > Purpose > Goals > Commitments > Maintenance
- Don't lecture - just inform

## HABIT & HEALTH GUIDANCE

When discussing habits, streaks, or health data:
- "Days without entries" not "missed days"
- Celebrate patterns of recovery ("You've bounced back before")
- Frame gaps as restart opportunities, not failures
- Connect guidance to WHY they set this goal

## WHEN ASKED "WHAT CAN YOU DO?" or "HOW CAN YOU HELP?"

When users ask about your capabilities, be specific and confident. You can:

**Health & Wellness:**
- Show their weight trends, blood pressure, heart rate, blood oxygen, glucose
- Track fasting windows and workout sessions
- Summarize medication adherence and food logging

**Goals & Tasks:**
- Report on goal progress and habit streaks
- Show tasks due today, overdue, or coming up
- Help prioritize what matters most

**Faith (if enabled):**
- Track prayer requests and answers
- Show scripture reading progress
- Support their spiritual journey

**Journal & Mood:**
- Access their journal entries and mood patterns
- Help them reflect on patterns over time

**Navigation:**
- Help them find where to log any data type
- Direct them to specific features in the app

**Images & Screenshots:**
- Accept and analyze images they share (photos, screenshots, etc.)
- Help identify food for nutrition logging
- Read text from screenshots or photos
- Provide feedback on anything they show you

When asked, give 2-3 concrete examples of what you can help with RIGHT NOW based on what you know they track.

## ALWAYS INCLUDE LINKS WHEN DIRECTING USERS

**CRITICAL**: Whenever you tell a user to "go to" somewhere in the app, you MUST include a clickable link.

Use this format: "You can do that by going to **[Feature Name]**. For easy access, [click here](/path/)."

**AVAILABLE FEATURES AND THEIR LINKS (ONLY use links from this list!):**
- Journal: [click here](/journal/)
- Weight: [click here](/health/weight/)
- Blood Pressure: [click here](/health/blood-pressure/)
- Heart Rate: [click here](/health/heart-rate/)
- Blood Oxygen: [click here](/health/blood-oxygen/)
- Glucose: [click here](/health/glucose/)
- Fasting: [click here](/health/fasting/)
- Workouts/Fitness: [click here](/health/fitness/)
- Nutrition/Food Log: [click here](/health/nutrition/)
- Medication/Medicine: [click here](/health/medicine/)
- Steps: [click here](/health/steps/)
- Water/Hydration: [click here](/health/water/)
- Cycle Tracking: [click here](/health/cycle/)
- Quick Log: [click here](/health/quick-log/)
- Brain Training/Cognitive: [click here](/health/cognitive/)
- Medical Records: [click here](/medical/)
- Goals: [click here](/purpose/goals/)
- Habits: [click here](/purpose/habits/)
- Intentions: [click here](/purpose/intentions/)
- Tasks: [click here](/life/tasks/)
- Calendar: [click here](/calendar/)
- Projects: [click here](/life/projects/)
- Recipes: [click here](/life/recipes/)
- Prayer: [click here](/faith/prayers/)
- Scripture: [click here](/faith/scripture/)
- Bible Reading: [click here](/faith/reading-plans/)
- Capture (voice notes): [click here](/capture/)
- Scan (document scanner): [click here](/scan/)
- Finance: [click here](/finance/)
- Dashboard: [click here](/dashboard/)
- Settings: [click here](/user/preferences/)
- Help: [click here](/help/)

**IMPORTANT - DO NOT MAKE UP FEATURES OR LINKS:**
- ONLY suggest features that exist in the list above
- If a user asks about a feature NOT in this list (like sleep tracking, etc.), tell them: "That feature isn't available yet, but I've noted your interest! You can let us know what features you'd like by saying 'I wish I could...' and we'll add it to our roadmap."
- NEVER invent URLs or guess at paths - if it's not in the list above, it doesn't exist
- If you're unsure whether a feature exists, err on the side of telling the user it's not available rather than sending them to a broken link

**Never** just say "go to your Journal entries" without a link. Always include the [click here](/journal/) part.

## NEVER CLAIM ACTIONS YOU DIDN'T PERFORM

**CRITICAL**: You can ONLY create, log, or modify data through the intent/tool system. When you successfully perform an action through a tool, the system provides a confirmation message starting with "✓".

- **NEVER** say "I've created...", "I've logged...", "Done!", "Created daily routine:..." or similar unless a tool was actually called and returned a success confirmation
- If a user asks you to create a task, log data, or perform any write action and you do NOT have tool access for it, say: "I don't have the ability to do that directly yet. You can do it manually at [link]."
- If you're unsure whether an action was performed, DO NOT claim it was

This is essential — claiming you performed actions you didn't is deeply confusing and erodes trust.

## IMAGE CAPABILITIES

You CAN accept and analyze images! Users can:
1. Click the "+" button next to the message input to attach an image
2. Paste an image directly from their clipboard (Ctrl+V / Cmd+V)

When users ask if you can accept files, pictures, or images, tell them YES - explain they can click the + button or paste images. When an image is attached, analyze it helpfully.

## THE GOLD STANDARD

After each response, check: Did I sound like someone who knows this person and their data? Or did I sound like a confused chatbot?

The user should feel: "This assistant actually knows me and gives me real answers."
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
                                     user_profile: str = None, time_context: dict = None,
                                     personal_context: str = None) -> str:
    """
    Build the complete Personal Assistant system prompt with coaching style.

    Args:
        coaching_style: User's selected coaching style (e.g., 'supportive', 'direct')
        faith_enabled: Whether faith module is enabled
        user_profile: User's personal AI profile (user-written)
        time_context: Dict with current_time, hours_remaining, day_status, urgency_message
        personal_context: AI-learned personal facts about the user
    """
    prompt = PERSONAL_ASSISTANT_BASE_PROMPT

    # Add coaching style instructions
    style_prompt = get_coaching_style_for_assistant(coaching_style)
    prompt += "\n\nCOACHING STYLE:\n" + style_prompt

    # Add communication guidelines based on coaching style
    prompt += "\n\n## COMMUNICATION STYLE TUNING"
    if coaching_style == 'direct':
        prompt += """
Your user prefers DIRECT communication:
- Lead with facts, skip the preamble
- Short sentences, no filler words
- State the answer, then stop
- If there's a problem, name it plainly
- Example: "Your weight is up 2 lbs from last week. Latest: 185 lbs."
"""
    elif coaching_style == 'gentle':
        prompt += """
Your user prefers GENTLE communication:
- Be warm and patient in your delivery
- Acknowledge feelings when topics are sensitive
- Use softening language but still be clear
- Frame challenges as growth opportunities
- Example: "Your weight has shifted a bit - up to 185 lbs. That's normal fluctuation, and you've handled this before."
"""
    else:  # supportive (default) and others
        prompt += """
Your user prefers SUPPORTIVE communication:
- Balance warmth with clarity
- Acknowledge effort without over-praising
- Be encouraging but grounded in reality
- Example: "You're at 185 lbs, up slightly from last week. Your trend over the month is still heading the right direction."
"""

    # Add time urgency context if provided
    if time_context:
        prompt += "\n\n" + TIME_URGENCY_PROMPT.format(**time_context)

    # Add faith context if enabled
    if faith_enabled:
        prompt += "\n" + FAITH_INTEGRATION_PROMPT

    # Add user profile context if provided (user-written description)
    if user_profile:
        from .profile_moderation import build_safe_profile_context
        profile_context = build_safe_profile_context(user_profile)
        if profile_context:
            prompt += "\n\nUSER CONTEXT:\n" + profile_context

    # Add AI-learned personal context if available
    if personal_context:
        from .personal_context import build_personal_context_prompt
        context_prompt = build_personal_context_prompt(personal_context)
        if context_prompt:
            prompt += context_prompt

    return prompt

FAITH_INTEGRATION_PROMPT = """

## FAITH & SPIRITUAL CONTEXT

This user has faith integration enabled. Their spiritual journey is a core part of their whole life.

**Your role with faith topics:**
- Treat their faith as a natural, integrated part of who they are
- Reference their prayer requests, scripture readings, and faith milestones when relevant
- Be genuinely supportive of their spiritual growth without being preachy
- When they ask about faith data, share it confidently (prayer stats, reading progress, etc.)

**Tone for faith topics:**
- Genuine and respectful, like a friend who shares their values
- Never performative or overly religious-sounding
- Never judgmental about gaps in spiritual practice
- Connect spiritual insights to their daily life naturally

**Examples:**
- "You have 3 active prayer requests. Your most recent was about [topic] from last week."
- "You've been consistent with your reading plan - 12 days in a row."
- "I notice you haven't logged any scripture readings this week. Want to pick that back up?"
"""

STATE_ASSESSMENT_PROMPT = """
## STATE ASSESSMENT STYLE

Write like a friend who knows their stuff - someone who looked at the data and is giving a quick, useful summary.

**Format:**
1. Brief opener that sets context (one line)
2. Short bulleted list of what needs attention (2-4 items max)
3. Optional: One forward-looking line if appropriate

**Voice:**
- Conversational, not corporate
- Use contractions (you've, don't, here's)
- Get to the point fast
- Sound like a capable friend, not an AI assistant

**Avoid:**
- Starting every bullet the same way
- Cheesy motivation ("You've got this!")
- Listing what's already done
- Vague language ("some things need attention")
- Bold formatting for emphasis

**Good examples:**
- "You've got 3 things that need attention today:"
- "Quick status - a couple items are slipping:"
- "Here's what's on your plate right now:"

Keep it under 80 words. Focus on what's NEXT, not what's DONE.
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
        # AI-learned personal context for empathetic responses
        self.personal_context = getattr(self.prefs, 'ai_personal_context', '') or ''
        # For data visibility confirmation flow
        self._data_visibility_response = None

    def _get_time_context(self) -> dict:
        """
        Get time-aware context for urgency messaging.

        Calculates hours remaining in day and appropriate urgency level
        based on user's timezone. Assumes typical bedtime of 10pm.
        """
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
            time_context=time_context,
            personal_context=self.personal_context
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
        get_user_now(self.user)

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

        # Check if snapshot is stale (>2 hours old or key data changed)
        snapshot_stale = False
        if snapshot and not force_refresh and not coaching_style_changed:
            user_now = get_user_now(self.user)
            hours_since_update = (user_now - snapshot.updated_at.astimezone(
                user_now.tzinfo
            )).total_seconds() / 3600

            # Stale if >2 hours old (time references become inaccurate)
            if hours_since_update >= 2:
                snapshot_stale = True
                logger.info(f"Snapshot stale: {hours_since_update:.1f} hours old, refreshing")

            # Stale if key metrics changed (user added data)
            if not snapshot_stale:
                if (fresh_task_data.get('tasks_completed_today', 0) != snapshot.tasks_completed_today
                        or fresh_task_data.get('tasks_overdue', 0) != snapshot.tasks_overdue
                        or fresh_task_data.get('tasks_due_today', 0) != snapshot.tasks_due_today):
                    snapshot_stale = True
                    logger.info("Snapshot stale: task counts changed, refreshing")

            # Stale if new health/journal data added since last snapshot update
            if not snapshot_stale:
                from apps.journal.models import JournalEntry
                from apps.health.models import WorkoutSession, WeightEntry, FoodEntry
                snapshot_updated = snapshot.updated_at
                new_data = (
                    JournalEntry.objects.filter(user=self.user, created_at__gt=snapshot_updated).exists()
                    or WorkoutSession.objects.filter(user=self.user, created_at__gt=snapshot_updated).exists()
                    or WeightEntry.objects.filter(user=self.user, created_at__gt=snapshot_updated).exists()
                    or FoodEntry.objects.filter(user=self.user, created_at__gt=snapshot_updated).exists()
                )
                if new_data:
                    snapshot_stale = True
                    logger.info("Snapshot stale: new data entries since last update, refreshing")

        if snapshot and not force_refresh and not coaching_style_changed and not snapshot_stale:
            # Return cached data but with FRESH task counts and today-specific data
            result = self._snapshot_to_dict(snapshot)
            result['tasks'] = {
                'completed_today': fresh_task_data.get('tasks_completed_today', 0),
                'completed_week': fresh_task_data.get('tasks_completed_week', 0),
                'overdue': fresh_task_data.get('tasks_overdue', 0),
                'due_today': fresh_task_data.get('tasks_due_today', 0),
            }
            # Always refresh today-specific ephemeral data
            result['faith'].update(self._get_fresh_today_faith(today))
            result['health']['workout_today'] = self._get_workout_today(today)
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

        result = self._snapshot_to_dict(snapshot)
        result['faith'].update(self._get_fresh_today_faith(today))
        result['health']['workout_today'] = self._get_workout_today(today)
        return result

    def _get_fresh_today_faith(self, today) -> Dict:
        """Get today-specific faith data (reading plan completion)."""
        try:
            from apps.faith.models import UserReadingPlan, UserReadingProgress
            active_plans = UserReadingPlan.objects.filter(
                user=self.user, plan_status='active'
            ).exclude(status='deleted')
            count = active_plans.count()
            completed = False
            if count > 0:
                completed = UserReadingProgress.objects.filter(
                    user_plan__in=active_plans,
                    is_completed=True,
                    completed_at__date=today,
                ).exists()
            return {
                'active_reading_plans': count,
                'reading_completed_today': completed,
            }
        except Exception:
            return {}

    def _get_workout_today(self, today) -> bool:
        """Check if user has logged a workout today."""
        try:
            from apps.health.models import WorkoutSession
            return WorkoutSession.objects.filter(
                user=self.user, date=today
            ).exists()
        except Exception:
            return False

    def _gather_comprehensive_state(self) -> Dict[str, Any]:
        """Gather all user data for state assessment."""
        from apps.core.utils import get_user_today, get_user_now

        get_user_now(self.user)
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
            AnnualDirection, LifeGoal, ChangeIntention
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
        from apps.core.utils import get_user_today
        from apps.faith.models import (
            FaithMilestone, PrayerRequest, UserReadingPlan, UserReadingProgress,
        )

        today = get_user_today(self.user)
        prayers = PrayerRequest.objects.filter(user=self.user)

        # Reading plan daily progress
        active_plans = UserReadingPlan.objects.filter(
            user=self.user, plan_status='active'
        ).exclude(status='deleted')
        reading_completed_today = False
        active_plan_count = active_plans.count()
        if active_plan_count > 0:
            reading_completed_today = UserReadingProgress.objects.filter(
                user_plan__in=active_plans,
                is_completed=True,
                completed_at__date=today,
            ).exists()

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
            'active_reading_plans': active_plan_count,
            'reading_completed_today': reading_completed_today,
        }

    def _get_health_state(self, today, week_ago) -> Dict:
        """Get health-related metrics across all health models."""
        from apps.health.models import (
            WeightEntry, FastingWindow, WorkoutSession,
            MedicineLog, StepsEntry, HeartRateEntry, SleepEntry,
            BloodPressureEntry, GlucoseEntry, BloodOxygenEntry,
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
        data['workout_today'] = workouts.filter(date=today).exists()
        data['workout_streak'] = self._calculate_workout_streak(today)

        # Medicine adherence (correct: expected vs taken from schedules)
        from apps.health.medicine_utils import calculate_medicine_adherence
        adherence = calculate_medicine_adherence(self.user, week_ago, today)
        data['medicine_adherence'] = adherence['adherence_rate']

        # Steps
        steps_week = StepsEntry.objects.filter(
            user=self.user, logged_date__gte=week_ago
        )
        if steps_week.exists():
            from django.db.models import Avg
            avg_steps = steps_week.aggregate(avg=Avg('count'))['avg']
            data['steps_avg_7d'] = int(avg_steps) if avg_steps else 0
            latest_steps = steps_week.order_by('-logged_date').first()
            if latest_steps:
                data['steps_latest'] = latest_steps.count
                data['steps_latest_date'] = latest_steps.logged_date

        # Heart Rate
        hr_entries = HeartRateEntry.objects.filter(
            user=self.user, recorded_at__date__gte=week_ago
        )
        if hr_entries.exists():
            from django.db.models import Avg, Min, Max
            hr_agg = hr_entries.aggregate(avg=Avg('bpm'), lo=Min('bpm'), hi=Max('bpm'))
            data['heart_rate_avg_7d'] = round(float(hr_agg['avg']), 0) if hr_agg['avg'] else None
            data['heart_rate_range_7d'] = f"{hr_agg['lo']}-{hr_agg['hi']}" if hr_agg['lo'] else None

        # Sleep
        sleep_entries = SleepEntry.objects.filter(
            user=self.user, sleep_date__gte=week_ago
        )
        if sleep_entries.exists():
            from django.db.models import Avg
            avg_sleep = sleep_entries.aggregate(avg=Avg('asleep_duration_minutes'))['avg']
            data['sleep_avg_hours_7d'] = round(float(avg_sleep) / 60, 1) if avg_sleep else None
            latest_sleep = sleep_entries.order_by('-sleep_date').first()
            if latest_sleep and latest_sleep.asleep_duration_minutes:
                data['sleep_latest_hours'] = round(latest_sleep.asleep_duration_minutes / 60, 1)

        # Blood Pressure
        bp_entries = BloodPressureEntry.objects.filter(
            user=self.user, recorded_at__date__gte=week_ago
        )
        if bp_entries.exists():
            from django.db.models import Avg
            bp_agg = bp_entries.aggregate(
                avg_sys=Avg('systolic'), avg_dia=Avg('diastolic')
            )
            data['bp_avg_7d'] = f"{round(float(bp_agg['avg_sys']))}/{round(float(bp_agg['avg_dia']))}" if bp_agg['avg_sys'] else None

        # Glucose
        glucose_entries = GlucoseEntry.objects.filter(
            user=self.user, recorded_at__date__gte=week_ago
        )
        if glucose_entries.exists():
            from django.db.models import Avg
            avg_glucose = glucose_entries.aggregate(avg=Avg('value'))['avg']
            data['glucose_avg_7d'] = round(float(avg_glucose), 0) if avg_glucose else None

        # Blood Oxygen
        spo2_entries = BloodOxygenEntry.objects.filter(
            user=self.user, recorded_at__date__gte=week_ago
        )
        if spo2_entries.exists():
            from django.db.models import Avg
            avg_spo2 = spo2_entries.aggregate(avg=Avg('spo2'))['avg']
            data['blood_oxygen_avg_7d'] = round(float(avg_spo2), 1) if avg_spo2 else None

        # Heart rate events (clinically significant — always include count)
        try:
            from apps.health.models import HeartRateEventEntry
            hr_events_week = HeartRateEventEntry.objects.filter(
                user=self.user, recorded_at__date__gte=week_ago
            ).count()
            if hr_events_week > 0:
                data['heart_rate_events_7d'] = hr_events_week
        except Exception:
            pass

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

        # Get time context for urgency - use day_status not exact hours (assessment gets cached)
        time_context = self._get_time_context()
        context_parts.append(f"Time: {time_context['current_time']} ({time_context['day_status'].replace('_', ' ')})")

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
        state.get('journal', {})
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
        """
        Generate priorities based on goals, milestones, and intentions.

        Uses smart rotation to ensure all goals get attention:
        1. Goals with overdue milestones are highest priority
        2. Goals that haven't been shown recently are prioritized
        3. Goals shown but not completed (user not making progress) are prioritized
        4. Goals recently shown AND completed are deprioritized (already being worked on)
        """
        from apps.purpose.models import LifeGoal, ChangeIntention, GoalMilestone
        from apps.core.utils import get_user_today
        from datetime import timedelta

        priorities = []
        today = get_user_today(self.user)
        lookback_days = 7  # Consider last 7 days of priorities

        # Get all active goals with their milestones
        all_goals = list(LifeGoal.objects.filter(
            user=self.user,
            status='active'
        ).prefetch_related('milestones'))

        if not all_goals:
            # No goals - fall through to intentions
            pass
        else:
            # First, check for overdue milestones (highest priority)
            overdue_milestones = GoalMilestone.objects.filter(
                goal__user=self.user,
                goal__status='active',
                completed=False,
                target_date__lt=today
            ).select_related('goal').order_by('target_date')[:2]

            for milestone in overdue_milestones:
                days_overdue = (today - milestone.target_date).days
                priorities.append({
                    'priority_type': 'milestone_overdue',
                    'title': f'Overdue milestone: {milestone.title[:40]}',
                    'description': f'Goal: {milestone.goal.title}',
                    'why_important': f'This milestone is {days_overdue} day{"s" if days_overdue != 1 else ""} overdue. Consider completing it or adjusting the date.',
                    'linked_goal_id': milestone.goal.id,
                    'linked_milestone_id': milestone.id,
                })

            # Get recent priorities linked to goals (last 7 days)
            recent_goal_priorities = DailyPriority.objects.filter(
                user=self.user,
                priority_date__gte=today - timedelta(days=lookback_days),
                linked_goal_id__isnull=False
            ).values('linked_goal_id', 'is_completed', 'priority_date')

            # Build a map: goal_id -> {shown_count, completed_count, last_shown}
            goal_activity = {}
            for p in recent_goal_priorities:
                gid = p['linked_goal_id']
                if gid not in goal_activity:
                    goal_activity[gid] = {'shown': 0, 'completed': 0, 'last_shown': None}
                goal_activity[gid]['shown'] += 1
                if p['is_completed']:
                    goal_activity[gid]['completed'] += 1
                if goal_activity[gid]['last_shown'] is None or p['priority_date'] > goal_activity[gid]['last_shown']:
                    goal_activity[gid]['last_shown'] = p['priority_date']

            # Score each goal - lower score = higher priority
            # Scoring logic:
            # - Has overdue milestone: score = -1 (absolute highest)
            # - Never shown (shown=0): score = 0 (highest priority)
            # - Shown but never completed: score = 1 (needs attention)
            # - Shown and partially completed: score = 2 (making some progress)
            # - Shown many times and completed many times: score = 3 (doing well)
            def goal_priority_score(goal):
                # Check for overdue milestones
                if goal.overdue_milestones:
                    return (-1, goal.sort_order)

                activity = goal_activity.get(goal.id, {'shown': 0, 'completed': 0, 'last_shown': None})
                shown = activity['shown']
                completed = activity['completed']

                if shown == 0:
                    # Never shown in recent days - highest priority
                    return (0, goal.sort_order)
                elif completed == 0:
                    # Shown but never completed - needs attention
                    return (1, goal.sort_order)
                elif completed < shown:
                    # Partially completing - moderate priority
                    return (2, goal.sort_order)
                else:
                    # Completing consistently - lowest priority (doing well!)
                    return (3, goal.sort_order)

            # Sort goals by priority score
            sorted_goals = sorted(all_goals, key=goal_priority_score)

            # Track goals already mentioned in overdue priorities
            overdue_goal_ids = {p.get('linked_goal_id') for p in priorities}

            # Take top 3 goals based on need (excluding those with overdue milestones already shown)
            for goal in sorted_goals[:5]:
                if len(priorities) >= 4:  # Leave room for intentions
                    break
                if goal.id in overdue_goal_ids:
                    continue

                # Build priority with milestone context
                next_milestone = goal.next_milestone
                if next_milestone:
                    title = f'{goal.title[:30]}: {next_milestone.title[:30]}'
                    description = f'{goal.completed_milestone_count}/{goal.milestone_count} milestones done'
                    if next_milestone.target_date:
                        days_until = (next_milestone.target_date - today).days
                        if days_until == 0:
                            description += ' - milestone due today!'
                        elif days_until == 1:
                            description += ' - milestone due tomorrow'
                        elif 0 < days_until <= 7:
                            description += f' - milestone due in {days_until} days'
                else:
                    title = f'Progress on: {goal.title[:50]}'
                    description = goal.description[:200] if goal.description else ''

                priorities.append({
                    'priority_type': 'purpose',
                    'title': title,
                    'description': description,
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

    def send_message(
        self,
        message: str,
        conversation: AssistantConversation = None,
        page_context: dict = None,
        image_data: str = None,
        image_mime_type: str = None
    ) -> dict:
        """
        Send a message to the assistant and get a response.

        Now supports intent recognition for structured data extraction.
        When the user says something like "my heart rate is 60", the assistant
        will recognize the intent, extract the data, and log it automatically.

        Supports multi-command messages like "update my oxygen to 95 and weight to 350"
        which will execute multiple actions and combine responses.

        Also detects feature requests ("I wish", "I want") when no matching solution
        exists and sends notifications to admin for review.

        Supports image attachments for OpenAI Vision processing.

        Args:
            message: User's message
            conversation: Optional conversation to add to
            page_context: Optional dict with 'url', 'module', 'page_title' for context-aware responses
            image_data: Optional base64-encoded image data
            image_mime_type: Optional MIME type of the image (e.g., 'image/png')

        Returns:
            Dict with 'response' (str), optionally 'actions_taken' (list of dicts),
            and optionally 'user_message_has_image' (bool)
        """
        from .intent_service import intent_service
        from .feature_request_service import feature_request_service
        from .bug_report_service import bug_report_service
        from .confirmation_detector import handle_proactive_confirmation

        if not conversation:
            conversation = self.get_or_create_conversation()

        # Calculate image expiration (72 hours from now)
        image_expires_at = None
        if image_data and image_mime_type:
            image_expires_at = timezone.now() + timedelta(hours=72)

        # Save user message (with optional image)
        AssistantMessage.objects.create(
            conversation=conversation,
            role='user',
            content=message,
            message_type='text',
            image_data=image_data or '',
            image_mime_type=image_mime_type or '',
            image_expires_at=image_expires_at
        )

        response = ""
        actions_taken = []

        # Check if AI is available
        if not ai_service.is_available or not AIService.check_user_consent(self.user):
            response = self._get_fallback_response(message)
        else:
            # Phase 5A/5B: ECC has absolute precedence over ALL other checks.
            # Must run before proactive confirmation, calibration, intent
            # recognition, task creation, and LLM generation.
            # Active commitment persisted in conversation.metadata for
            # cross-message continuity.
            #
            # Phase 5C hard short-circuit sentinel: set BEFORE any DB
            # operation so the except handler cannot swallow closure.
            _ecc_closure_handled = False
            _ecc_closure_response = ''
            try:
                from apps.core.ai_orchestrator.commitment_contract import (
                    Commitment as EccCommitment,
                    process_ecc_detection,
                    process_ecc_closure,
                    get_pending_commitments,
                    create_db_commitment,
                    close_db_commitment,
                )
                from apps.core.ai_orchestrator.cos_context import (
                    build_cos_context as _ecc_build_cos,
                    determine_activation_state as _ecc_determine_tier,
                    _build_trajectory_signals as _ecc_build_traj,
                )
                from apps.core.blueprint.models import (
                    Commitment as CommitmentModel,
                )

                # Compute real tier — same logic as _generate_response()
                _ecc_cos = _ecc_build_cos(self.user)
                _ecc_traj = _ecc_cos.get(
                    'trajectory_signals',
                    _ecc_build_traj(self.user),
                )
                _ecc_tier = _ecc_determine_tier(_ecc_traj, message)

                # Load pending commitments from DB (cross-session)
                _ecc_db_pending = get_pending_commitments(self.user)

                # Fallback: also check conversation metadata for
                # backward compatibility with pre-DB commitments
                _ecc_active = list(_ecc_db_pending)
                if not _ecc_active:
                    _ecc_metadata = (conversation.metadata or {}).get(
                        'ecc_active_commitment'
                    )
                    if _ecc_metadata:
                        _ecc_restored = EccCommitment.from_dict(_ecc_metadata)
                        if _ecc_restored and _ecc_restored.status == 'pending':
                            _ecc_active = [_ecc_restored]

                # Phase 5C: Closure precedence — check BEFORE renegotiation
                # and new commitment detection. "It's done." must close the
                # active commitment, not route to intent recognition.
                if _ecc_active:
                    closure = process_ecc_closure(message, _ecc_active)
                    if closure is not None:
                        # Phase 5C: Set sentinel BEFORE any DB operation
                        # so except handler cannot swallow closure.
                        ecc_response = closure.get('response', '')
                        _ecc_closure_handled = True
                        _ecc_closure_response = ecc_response
                        # Close in DB if available
                        if closure.get('closed') and closure.get('db_id'):
                            closed_c = closure['commitment']
                            if closed_c and closed_c.status == 'closed_success':
                                close_db_commitment(
                                    closure['db_id'],
                                    CommitmentModel.STATUS_CLOSED_SUCCESS,
                                    CommitmentModel.CLOSURE_USER_CONFIRMED,
                                )
                            elif closed_c and closed_c.status == 'closed_missed':
                                close_db_commitment(
                                    closure['db_id'],
                                    CommitmentModel.STATUS_CLOSED_MISSED,
                                    CommitmentModel.CLOSURE_USER_MISSED,
                                )
                        # Also clear metadata
                        conversation.metadata = conversation.metadata or {}
                        if closure.get('closed'):
                            conversation.metadata.pop(
                                'ecc_active_commitment', None
                            )
                        conversation.save(update_fields=['metadata'])
                        if ecc_response:
                            AssistantMessage.objects.create(
                                conversation=conversation,
                                role='assistant',
                                content=ecc_response,
                                message_type='text'
                            )
                            conversation.updated_at = timezone.now()
                            conversation.save(update_fields=['updated_at'])
                            return {'response': ecc_response}

                ecc_result = process_ecc_detection(
                    user_input=message,
                    tier=_ecc_tier,
                    active_commitments=_ecc_active or None,
                    user=self.user,
                )
                if ecc_result and ecc_result.get('detected'):
                    ecc_response = None
                    # Commitment formed → persist to DB and metadata
                    if ecc_result.get('commitment'):
                        commitment = ecc_result['commitment']
                        # Persist to DB
                        create_db_commitment(
                            user=self.user,
                            commitment_data=commitment,
                            conversation=conversation,
                            tier=_ecc_tier,
                        )
                        # Also persist to metadata for backward compat
                        conversation.metadata = conversation.metadata or {}
                        conversation.metadata['ecc_active_commitment'] = (
                            commitment.to_dict()
                        )
                        conversation.save(update_fields=['metadata'])
                    # Response covers all cases: tightening question,
                    # blocked renegotiation choices, or confirmation
                    if ecc_result.get('response'):
                        ecc_response = ecc_result['response']

                    if ecc_response:
                        # Save assistant message and return immediately
                        AssistantMessage.objects.create(
                            conversation=conversation,
                            role='assistant',
                            content=ecc_response,
                            message_type='text'
                        )
                        conversation.updated_at = timezone.now()
                        conversation.save(update_fields=['updated_at'])
                        return {'response': ecc_response}
            except Exception as ecc_err:
                logger.debug("ECC pre-check skipped: %s", ecc_err)

            # ── Phase 5C HARD SHORT-CIRCUIT ──────────────────────
            # If closure was detected (sentinel set) but a DB operation
            # inside the try block threw, we MUST NOT fall through to
            # intent recognition.  Return the closure response and
            # bypass every downstream subsystem.
            if _ecc_closure_handled:
                if _ecc_closure_response:
                    # Best-effort: ensure exactly one AssistantMessage
                    try:
                        if not AssistantMessage.objects.filter(
                            conversation=conversation,
                            content=_ecc_closure_response,
                            role='assistant',
                        ).exists():
                            AssistantMessage.objects.create(
                                conversation=conversation,
                                role='assistant',
                                content=_ecc_closure_response,
                                message_type='text',
                            )
                    except Exception:
                        pass  # response still returned to caller
                return {'response': _ecc_closure_response or ''}
            # ── End hard short-circuit ────────────────────────────

            # First, check for proactive check-in responses (e.g., "yes" to "Did you take your medicine?")
            proactive_result = handle_proactive_confirmation(self.user, message)
            if proactive_result and proactive_result.get('handled'):
                response = proactive_result['response']
                if proactive_result.get('action_result', {}).get('success'):
                    action_result = proactive_result.get('action_result', {})
                    actions_taken.append({
                        'type': 'proactive_response',
                        'success': True,
                        'created': action_result.get('data'),
                    })
            # During active calibration, skip action intent recognition.
            # The AI should only listen and ask questions, not log data.
            # Exception: calibration intents (pause/complete) still work.
            elif self._is_calibration_active():
                # Check for calibration-specific intents only
                _cal_response = self._try_calibration_intents(
                    message, intent_service, actions_taken)
                if _cal_response:
                    response = _cal_response
                else:
                    response = self._generate_response(
                        message, conversation,
                        page_context=page_context,
                        image_data=image_data,
                        image_mime_type=image_mime_type
                    )
            # Then check for pending data visibility confirmation
            elif self._handle_data_visibility_confirmation(message, conversation):
                response = self._data_visibility_response
                self._data_visibility_response = None  # Clear after use
            # Then check for Learning Mode exit confirmation (in-chat)
            elif self._handle_learning_mode_exit_confirmation(message, actions_taken):
                response = self._learning_mode_exit_response
                self._learning_mode_exit_response = None
            # Then check for pending action confirmation
            elif (pending := intent_service.get_pending_confirmation(self.user)):
                # Handle confirmation response
                action_result = intent_service.handle_confirmation_response(self.user, message)
                if action_result:
                    if action_result.action_type == 'cancelled':
                        response = action_result.message
                    else:
                        response = action_result.message + self._format_confirmation_detail(action_result)
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
                    # Run orchestrator pipeline for time/context resolution
                    from apps.core.ai_orchestrator.orchestrator import (
                        process_user_input as orchestrator_process,
                        enrich_and_execute,
                    )
                    orch_result = orchestrator_process(
                        self.user, message, page_context=page_context
                    )

                    # If orchestrator needs clarification (ambiguous time/context),
                    # ask the user instead of executing
                    if orch_result.needs_clarification:
                        response = orch_result.clarification_question
                    else:
                        # Check if any require confirmation
                        needs_confirmation = [ir for ir in actionable_intents if ir.requires_confirmation]

                        if needs_confirmation:
                            # For now, if any need confirmation, handle them one by one
                            # Store the first one pending and execute the rest
                            first_confirm = needs_confirmation[0]
                            intent_service.store_pending_confirmation(self.user, first_confirm)

                            # Execute any that don't need confirmation via orchestrator
                            no_confirm = [ir for ir in actionable_intents if not ir.requires_confirmation]
                            response_parts = []

                            if no_confirm:
                                orch_actions = enrich_and_execute(
                                    self.user, no_confirm, orch_result
                                )
                                for action_result in orch_actions:
                                    if action_result.success:
                                        actions_taken.append(self._build_action_taken(action_result))

                                # Use orchestrator enhanced response if available
                                if orch_result.response:
                                    response_parts.append(orch_result.response)
                                else:
                                    for ar in orch_actions:
                                        if ar.success:
                                            response_parts.append(ar.message + self._format_confirmation_detail(ar))

                            # Add confirmation message for the pending one
                            response_parts.append(first_confirm.confirmation_message)
                            response = " ".join(response_parts)
                        else:
                            # Execute all actions via orchestrator
                            orch_actions = enrich_and_execute(
                                self.user, actionable_intents, orch_result
                            )

                            for action_result in orch_actions:
                                if action_result.success:
                                    actions_taken.append(self._build_action_taken(action_result))

                            # Use orchestrator enhanced response if available
                            if orch_result.response:
                                response = orch_result.response
                            else:
                                response_parts = []
                                for ar in orch_actions:
                                    response_parts.append(ar.message + self._format_confirmation_detail(ar))
                                response = " ".join(response_parts)
                else:
                    # No action intent - check for bug reports first ("Fix this:", "Bug:", etc.)
                    bug_report_ack = self._check_bug_report(
                        message=message,
                        conversation=conversation,
                        bug_report_service=bug_report_service
                    )

                    if bug_report_ack:
                        # Bug report was detected and handled
                        # Generate a helpful response and append the acknowledgment
                        response = self._generate_response(
                            message, conversation,
                            page_context=page_context,
                            image_data=image_data,
                            image_mime_type=image_mime_type
                        )
                        response += "\n\n" + bug_report_ack
                    else:
                        # Not a bug report - check for navigation query
                        # Pass page_context so we don't navigate away when asking about current content
                        navigation_response = self._try_navigation_response(message, conversation, page_context)
                        if navigation_response:
                            response = navigation_response
                        else:
                            # Generate normal chat response
                            response = self._generate_response(
                                message, conversation,
                                page_context=page_context,
                                image_data=image_data,
                                image_mime_type=image_mime_type
                            )

                        # Check for feature requests ("I wish", "I want") and notify admin
                        # This captures user needs that the system doesn't currently handle
                        # Note: We don't append an acknowledgment message here because the AI
                        # already handles feature requests gracefully in its response
                        self._check_feature_request(
                            message=message,
                            conversation=conversation,
                            feature_request_service=feature_request_service
                        )

                # ── Phase 8: Pre-release validator gate ──────────────
                # Inspect LLM response before persistence. Structural
                # violations are blocked (replaced); unverifiable action
                # claims are blocked; numeric deviations are observe-only.
                # Validator crash returns safe response.
                try:
                    from apps.core.ai_governance.validator_gate import (
                        validate_response,
                    )
                    validation = validate_response(
                        response, self.user, conversation,
                        action_executed=bool(actions_taken),
                    )
                    response = validation['response']
                except Exception:
                    pass  # defense-in-depth; validate_response never raises
                # ── End Phase 8 validator gate ────────────────────────

        # Record calibration answer if active (advance stage for next question)
        # Skip if:
        # - Welcome was just shown this cycle (user acknowledging, not answering)
        # - Message is a system-initiated resume (auto-sent by chat panel on load)
        CALIBRATION_RESUME_PHRASES = {
            "let's continue where we left off.",
            "hello",
            "hi",
            "hey",
            "hi, let's get started!",
            "let's get started!",
            "let's get started",
            "let's go",
        }
        try:
            skip_recording = getattr(
                self, '_calibration_welcome_just_shown', False
            )
            if not skip_recording and message.strip().lower() in CALIBRATION_RESUME_PHRASES:
                skip_recording = True

            if not skip_recording:
                from apps.core.blueprint.cos_governance import (
                    get_calibration_state,
                    record_calibration_answer,
                )
                cal_state = get_calibration_state(self.user)
                if (cal_state and cal_state['active']
                        and not cal_state['paused']
                        and cal_state.get('next_question')):
                    next_q = cal_state['next_question']
                    record_calibration_answer(
                        self.user, next_q['key'], message[:500],
                    )
        except Exception:
            pass  # Calibration tracking must never break chat

        # Save assistant response
        msg_type = 'action' if actions_taken else 'text'
        AssistantMessage.objects.create(
            conversation=conversation,
            role='assistant',
            content=response,
            message_type=msg_type
        )

        # Update conversation
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])

        # Post-response: trigger rolling conversation summary if needed
        try:
            from apps.ai.executive_briefing import maybe_generate_rolling_summary
            maybe_generate_rolling_summary(self.user, conversation)
        except Exception:
            pass  # Summary generation must never break chat

        # Post-response: store conversation memory for RAG retrieval
        try:
            from apps.ai.memory_service import store_memory
            store_memory(
                user=self.user,
                user_message=message,
                assistant_response=response,
                conversation=conversation,
                page_context=page_context,
            )
        except Exception:
            pass  # Memory storage must never break chat

        # Store actions_taken in conversation metadata for undo support
        if actions_taken:
            try:
                meta = conversation.metadata or {}
                stored_actions = meta.get('actions_taken', [])
                stored_actions.extend(actions_taken)
                # Keep only last 10 actions to prevent unbounded growth
                meta['actions_taken'] = stored_actions[-10:]
                conversation.metadata = meta
                conversation.save(update_fields=['metadata', 'updated_at'])
            except Exception:
                pass  # Undo tracking must never break chat

        # Return structured response
        result = {'response': response}
        if actions_taken:
            # For backwards compatibility, also include single action_taken
            result['action_taken'] = actions_taken[0] if len(actions_taken) == 1 else None
            result['actions_taken'] = actions_taken

        # Include flag if user message had an image
        if image_data and image_mime_type:
            result['user_message_has_image'] = True

        return result

    def _build_action_taken(self, action_result) -> dict:
        """Build the action_taken dict for API response."""
        result = {
            'type': action_result.action_type,
            'success': action_result.success,
            'created': action_result.created_object,
        }
        if getattr(action_result, 'confirmation_detail', None):
            result['confirmation_detail'] = action_result.confirmation_detail
        return result

    def _format_confirmation_detail(self, action_result) -> str:
        """
        Format confirmation_detail into response text.

        Appends location, trend, risk, and latest PIE insight for
        the action's module so the user gets strategic context alongside
        every data log.
        """
        detail = getattr(action_result, 'confirmation_detail', None)
        if not detail:
            return ''

        parts = []
        where = detail.get('where')
        if where:
            parts.append(f"({where})")
        trend = detail.get('trend')
        if trend:
            parts.append(trend)
        risk = detail.get('risk')
        if risk:
            parts.append(risk)

        # Append latest PIE insight for this module as strategic context
        try:
            module = detail.get('module') or self._infer_module_from_where(where)
            if module:
                from apps.core.ai_insights.models import Insight
                latest_insight = Insight.objects.filter(
                    user=self.user,
                    module=module,
                    status__in=["new", "read"],
                    severity__in=["warning", "critical"],
                ).order_by("-created_at").first()
                if latest_insight and latest_insight.message:
                    parts.append(f"Pattern: {latest_insight.message}")
        except Exception:
            pass

        if parts:
            return '\n' + '\n'.join(parts)
        return ''

    @staticmethod
    def _infer_module_from_where(where):
        """Infer PIE module name from confirmation_detail 'where' field."""
        if not where:
            return None
        where_lower = where.lower()
        module_map = {
            'health': 'health', 'weight': 'health', 'heart': 'health',
            'blood': 'health', 'glucose': 'health', 'oxygen': 'health',
            'fitness': 'fitness', 'workout': 'fitness', 'cardio': 'fitness',
            'journal': 'journal', 'gratitude': 'journal',
            'faith': 'faith', 'prayer': 'faith', 'scripture': 'scripture',
            'goal': 'goals', 'habit': 'habits',
            'nutrition': 'nutrition', 'food': 'nutrition',
            'fasting': 'fasting', 'fast': 'fasting',
        }
        for keyword, module in module_map.items():
            if keyword in where_lower:
                return module
        return None

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

    def _check_bug_report(
        self,
        message: str,
        conversation: AssistantConversation,
        bug_report_service
    ) -> Optional[str]:
        """
        Check if message is a bug report and notify admin if needed.

        When users report bugs using "Fix this:", "Bug:", or similar phrases,
        this creates a task and sends a notification to admin for review.

        Args:
            message: The user's message
            conversation: The current conversation
            bug_report_service: The bug report service instance

        Returns:
            Acknowledgment message if bug report was detected and handled,
            None otherwise
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
            return bug_report_service.check_and_notify(
                user=self.user,
                message=message,
                conversation_context=conversation_context
            )
        except Exception as e:
            # Don't let bug report detection break the chat flow
            logger.warning(f"Bug report check failed: {e}")
            return None

    def _handle_learning_mode_exit_confirmation(
        self, message: str, actions_taken: list
    ) -> bool:
        """
        Handle user's response to Learning Mode exit summary (modal state).

        When exit is pending, this is a MODAL gate — ALL messages are
        intercepted. The user must confirm or cancel before anything else
        can happen.

        Returns:
            True if exit is pending (always handled when pending).
            False if exit not pending.
        """
        try:
            from apps.core.blueprint.learning_mode import (
                is_exit_pending,
                confirm_exit_learning_mode,
                cancel_exit_learning_mode,
                get_exit_summary,
            )
            if not is_exit_pending(self.user):
                return False

            msg_lower = message.lower().strip()
            affirmative = {
                'yes', 'y', 'yeah', 'yep', 'yup', 'confirm', 'correct',
                'that looks right', 'looks good', 'ok', 'sure', 'do it',
                'go ahead', "that's right", 'thats right', 'accurate',
            }
            negative = {
                'no', 'n', 'nope', 'nah', 'not quite', 'wrong',
                "that's not right", 'thats not right', 'incorrect',
                'keep learning', 'stay', 'cancel',
            }

            if msg_lower in affirmative:
                confirm_exit_learning_mode(self.user)
                self._learning_mode_exit_response = (
                    "Confirmed. Learning Mode is off — I'm back in action. "
                    "I'll start using what I've learned to help you."
                )
                actions_taken.append({
                    'type': 'confirm_exit_learning_mode',
                    'success': True,
                    'created': None,
                })
                return True

            if msg_lower in negative:
                cancel_exit_learning_mode(self.user)
                self._learning_mode_exit_response = (
                    "No problem — I'll stay in Learning Mode. "
                    "Keep telling me what matters to you."
                )
                return True

            # Not a clear yes/no — modal: block and re-prompt
            self._learning_mode_exit_response = (
                "Exit confirmation pending. Please confirm or cancel "
                "before proceeding.\n\n"
                "Say **yes** to exit Learning Mode and resume execution, "
                "or **no** to stay in Learning Mode."
            )
            return True
        except Exception as e:
            logger.debug("Learning mode exit confirmation check failed: %s", e)
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

    def _try_navigation_response(self, message: str, conversation: AssistantConversation = None, page_context: dict = None) -> str:
        """
        Check if the message is a navigation query and return a helpful response.

        Uses the Teaching Tool to answer questions like "where do I log my weight?"
        with a direct link, without calling the AI.

        For ambiguous queries like "how do I log it", uses conversation context
        to infer what the user is referring to.

        Args:
            message: User's message
            conversation: Optional conversation for context on ambiguous queries
            page_context: Optional page context - if query references page content, skip navigation

        Returns:
            Response string with navigation info, or None if not a navigation query
        """
        # Check if query looks like a navigation question
        query_lower = message.lower().strip()

        # Check if the query references something we just created
        # If so, respond with that info directly instead of generic navigation
        if conversation:
            reference_words = ['that', 'those', 'the task', 'the tasks', 'it', 'them']
            if any(word in query_lower for word in reference_words):
                # Check recent assistant messages for creation actions
                recent_assistant_messages = conversation.messages.filter(
                    role='assistant'
                ).order_by('-created_at')[:3]

                for msg in recent_assistant_messages:
                    msg_lower = msg.content.lower()
                    # Check if assistant recently created a task
                    if '✓ created task:' in msg_lower:
                        # Return a helpful response pointing to where the task is
                        return "You can find the task I just created in [Organize → Tasks](/life/tasks/). [Click here](/life/tasks/) to view your tasks."
                    # Could add similar checks for other created items here

        # First, check if the query is about the CURRENT PAGE content
        # These queries should NOT be handled as navigation - they want the AI
        # to explain/show content that's already on the page
        page_content_indicators = [
            # References to current page content
            'this scripture', 'the scripture', 'this verse', 'the verse',
            'this passage', 'the passage', 'this reading', 'the reading',
            'this entry', 'this journal', 'this prayer', 'this goal',
            'this task', 'this page', 'the page', 'on the page',
            'on this page', 'the actual', 'actual scripture',
            # Explanation requests about content
            'explain it', 'explain this', 'explain the', 'what does it mean',
            'what does this mean', 'in simple terms', 'like i am',
            'tell me about this', 'tell me what', 'niv', 'esv', 'kjv',
            # User directing Beth to page content
            "it's on", "its on", "right there", "can you see",
            "you can see", "look at",
        ]

        # If the query is about current page content, skip navigation
        if any(indicator in query_lower for indicator in page_content_indicators):
            return None

        # If there's page context with content (like a reading plan), and the query
        # seems to be asking about that content, skip navigation
        if page_context and page_context.get('page_content'):
            content_type = page_context['page_content'].get('type', '')
            # For reading plans, skip navigation if query mentions scripture/reading/explain
            if content_type == 'reading_plan_progress':
                reading_context_words = ['scripture', 'verse', 'passage', 'read', 'reading', 'explain', 'mean', 'bible', 'luke', 'john', 'matthew', 'mark', 'sabbath', 'pharisee', 'jesus', 'god', 'lord', 'faith', 'sin', 'forgive', 'pray', 'spirit', 'holy', 'parable', 'miracle', 'apostle', 'disciple', 'temple', 'prophet', 'commandment', 'covenant', 'psalm', 'genesis', 'exodus', 'leviticus', 'deuteronomy', 'romans', 'corinthians', 'galatians', 'ephesians', 'hebrews', 'revelation', 'acts', 'james', 'peter', 'timothy', 'titus', 'proverbs', 'isaiah', 'jeremiah', 'ezekiel', 'daniel']
                if any(word in query_lower for word in reading_context_words):
                    return None
            # For journal entries, skip if query mentions entry/journal/wrote
            elif content_type == 'journal_entry':
                journal_context_words = ['entry', 'journal', 'wrote', 'writing', 'wrote']
                if any(word in query_lower for word in journal_context_words):
                    return None

        # IMPORTANT: Skip navigation for data analysis / personal insight questions.
        # These should go to the AI with personal data context, not return a link.
        # Examples: "where do I need to focus", "how many days have I missed",
        # "show me my trends", "where am I falling behind"
        data_analysis_indicators = [
            # Analysis / insight words
            'my data', 'my habits', 'my trends', 'my patterns', 'my progress',
            'my streak', 'my consistency', 'my stats', 'my performance',
            'my average', 'my history',
            # Questions about personal state/gaps
            'need to focus', 'need to improve', 'need to work on',
            'falling behind', 'doing well', 'doing poorly',
            'strengthen', 'weakness', 'strong', 'consistent',
            'missed', 'skipped', 'forgot', 'forgotten',
            # Counting / measuring personal data
            'how many days', 'how many times', 'how many entries',
            'how often', 'how much', 'how long have i',
            'since i started', 'since i began',
            # Trend questions
            'trending', 'going up', 'going down', 'getting better',
            'getting worse', 'improved', 'declined',
            # Comparative
            'compared to', 'last week', 'last month', 'this week', 'this month',
            'over time', 'past week', 'past month',
            # Summary requests about personal data
            'summary of my', 'overview of my', 'analyze my', 'review my',
            'look at my', 'looking at my', 'based on my',
            'what does my data', 'what do my',
        ]

        if any(indicator in query_lower for indicator in data_analysis_indicators):
            logger.debug(f"Skipping navigation for data analysis query: {message[:60]}")
            return None

        navigation_indicators = [
            # Location questions
            'where do i', 'where can i', 'where is', 'where are',
            'where\'s the', 'where\'s my', 'where to find', 'where to log',
            'where to track', 'where to add', 'where to record',
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
            # Find questions
            'find my', 'find the', 'looking for',
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
                    'blood pressure': ['blood pressure', 'bp', 'systolic', 'diastolic'],
                    'heart rate': ['heart rate', 'pulse', 'bpm', 'heartbeat'],
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

    def _generate_response(
        self,
        message: str,
        conversation: AssistantConversation,
        page_context: dict = None,
        image_data: str = None,
        image_mime_type: str = None
    ) -> str:
        """Generate AI response to user message using coaching style.

        Now integrates with the personal data query system to inject relevant
        personal data context (weight, journal, medication, food, mood) when
        users ask about their data.

        The assistant is schedule-aware and proactively references the user's
        calendar events, especially during greetings. It provides task/priority
        information when relevant or when the user asks for it.

        Supports image attachments for OpenAI Vision processing.

        Args:
            message: User's message
            conversation: The conversation object
            page_context: Optional dict with 'url', 'module', 'page_title' for context-aware responses
            image_data: Optional base64-encoded image data
            image_mime_type: Optional MIME type of the image (e.g., 'image/png')
        """
        # Get conversation history - 40 messages for deep conversational threading
        # More history means CoS can follow topic changes and reference earlier context
        history = conversation.messages.order_by('-created_at')[:40]

        # Always include time context so the AI knows the user's current time
        # (e.g., "what time is it?" queries). Urgency messaging is part of time context.
        system_prompt = self._build_system_prompt(include_time_context=True)

        # ================================================================
        # UNIFIED CoS SYSTEM PROMPT — PRIORITY-ORDERED
        #
        # The prompt is assembled in a clear hierarchy so the LLM knows
        # what matters most. Personality and relationship instructions
        # come FIRST (highest priority), operational context LAST.
        #
        # Order:
        #   1. Calibration override (if active — supersedes everything)
        #   2. Recalibration (if non-negotiables being missed)
        #   3. Governance alignment (if in progress)
        #   4. Personality & relationship (POST_CALIBRATION_PERSONALITY)
        #   5. Learned user profile (values, identity, relationships)
        #   6. Governance preferences (accountability style, sensitivity)
        #   7. Operational context (schedule, calendar, key signals)
        #   8. Base prompt (capabilities, links, data handling)
        #   9. Pending reflections / greeting context (appended)
        #
        # IMPORTANT: Each layer is injected ONCE. No duplicates.
        # ================================================================
        try:
            if getattr(self.prefs, 'personal_assistant_enabled', False):
                # ----------------------------------------------------------
                # Collect all layers (each gathered once, assembled at end)
                # ----------------------------------------------------------
                priority_layers = []  # Prepended in order (first = highest)
                append_layers = []    # Appended after base prompt

                # Layer 1-3: Special session overrides (calibration, recal, alignment)
                # These are mutually exclusive in practice — only one is active
                try:
                    from apps.core.blueprint.cos_governance import (
                        build_calibration_system_injection,
                        get_calibration_state,
                        mark_calibration_welcome_shown,
                        advance_calibration_day,
                    )
                    cal_state = get_calibration_state(self.user)
                    logger.info(
                        "Calibration check: user=%s state=%s",
                        self.user.email,
                        {k: v for k, v in (cal_state or {}).items()
                         if k != 'next_question'} if cal_state else None
                    )
                    if (cal_state and cal_state['active']
                            and not cal_state['paused']):
                        cal_injection = build_calibration_system_injection(
                            self.user)
                        logger.info(
                            "Calibration injection: user=%s len=%d "
                            "first_100=%s",
                            self.user.email,
                            len(cal_injection) if cal_injection else 0,
                            (cal_injection[:100] if cal_injection
                             else 'EMPTY'),
                        )
                        if cal_injection:
                            priority_layers.append(cal_injection)
                            if not cal_state['welcome_shown']:
                                mark_calibration_welcome_shown(self.user)
                                self._calibration_welcome_just_shown = True
                    # Advance calibration day once per day on first interaction
                    advance_calibration_day(self.user)
                except Exception as e:
                    logger.error(
                        "Calibration injection FAILED: %s", e,
                        exc_info=True
                    )

                # Recalibration (if non-negotiables being missed)
                try:
                    from apps.core.ai_governance.recalibration import (
                        build_recalibration_injection,
                    )
                    recal_injection = build_recalibration_injection(self.user)
                    if recal_injection:
                        priority_layers.append(recal_injection)
                except Exception:
                    pass

                # Governance alignment session
                try:
                    from apps.core.ai_governance.alignment_session import (
                        build_alignment_system_injection,
                        needs_alignment,
                    )
                    if needs_alignment(self.user):
                        alignment_injection = build_alignment_system_injection(self.user)
                        if alignment_injection:
                            priority_layers.append(alignment_injection)
                except Exception:
                    pass

                # Layer 4: Governance instructions (personality + preferences)
                # This includes POST_CALIBRATION_PERSONALITY when calibration
                # is complete — the core relational instructions.
                try:
                    from apps.core.blueprint.cos_governance import (
                        build_governance_instructions,
                    )
                    gov_instructions = build_governance_instructions(self.user)
                    if gov_instructions:
                        priority_layers.append(gov_instructions)
                except Exception as gov_err:
                    logger.debug("Governance injection skipped: %s", gov_err)

                # Layer 5: Learned user profile (values, identity, relationships)
                # Injected ONCE here — removed from cos_context to avoid duplication.
                try:
                    from apps.core.ai_learning.learning_extractor import (
                        get_profile_system_prompt,
                    )
                    learned_block = get_profile_system_prompt(self.user)
                    if learned_block:
                        priority_layers.append(learned_block)
                except Exception as lp_err:
                    logger.debug("Learned profile injection skipped: %s", lp_err)

                # Layer 6: Operational context (schedule, calendar, key signals)
                # This is COMPACT — only what the LLM needs to be situationally aware.
                # Dual template: NORMAL vs WRITE_SUPPRESSED selected deterministically.
                try:
                    from apps.core.ai_orchestrator.cos_context import (
                        build_cos_context,
                        build_learning_mode_context,
                        format_cos_system_injection,
                        determine_activation_state,
                        evaluate_decision_branch_gate,
                        _build_trajectory_signals,
                    )
                    from apps.core.blueprint.learning_mode import is_learning_mode_active

                    if is_learning_mode_active(self.user):
                        cos_context = build_learning_mode_context(self.user)
                    else:
                        cos_context = build_cos_context(self.user)
                        # Phase 3 Tiered Activation: compute activation
                        # state from trajectory signals + user input.
                        traj_signals = cos_context.get(
                            'trajectory_signals',
                            _build_trajectory_signals(self.user),
                        )
                        cos_context['trajectory_signals'] = traj_signals
                        activation_state = determine_activation_state(
                            traj_signals, message
                        )
                        cos_context['trajectory_activation_state'] = activation_state

                        # Phase 5A/5B: ECC detection — after tier eval, before R5.
                        # DB-backed commitments with cross-session continuity.
                        # Commitments are user-global, loaded from DB (not metadata).
                        #
                        # Phase 5C hard short-circuit sentinel.
                        _ecc_closure_handled = False
                        _ecc_closure_response = ''
                        try:
                            from apps.core.ai_orchestrator.commitment_contract import (
                                CommitmentData as EccCommitmentData,
                                process_ecc_detection,
                                process_ecc_closure,
                                get_pending_commitments,
                                create_db_commitment,
                                close_db_commitment,
                                format_ecc_injection,
                            )
                            from apps.core.blueprint.models import (
                                Commitment as CommitmentModel,
                            )
                            # Load pending commitments from DB (cross-session)
                            _ecc_pending = get_pending_commitments(self.user)

                            # Phase 5C: Closure precedence
                            if _ecc_pending:
                                _closure = process_ecc_closure(
                                    message, _ecc_pending
                                )
                                if _closure is not None:
                                    # Phase 5C: Set sentinel BEFORE DB ops
                                    _ecc_closure_response = (
                                        _closure.get('response', '')
                                    )
                                    _ecc_closure_handled = True
                                    if _closure.get('closed') and _closure.get('db_id'):
                                        closed_commitment = _closure['commitment']
                                        if closed_commitment and closed_commitment.status == 'closed_success':
                                            close_db_commitment(
                                                _closure['db_id'],
                                                CommitmentModel.STATUS_CLOSED_SUCCESS,
                                                CommitmentModel.CLOSURE_USER_CONFIRMED,
                                            )
                                        elif closed_commitment and closed_commitment.status == 'closed_missed':
                                            close_db_commitment(
                                                _closure['db_id'],
                                                CommitmentModel.STATUS_CLOSED_MISSED,
                                                CommitmentModel.CLOSURE_USER_MISSED,
                                            )
                                    if _ecc_closure_response:
                                        return _ecc_closure_response

                            ecc_result = process_ecc_detection(
                                user_input=message,
                                tier=activation_state,
                                active_commitments=_ecc_pending or None,
                                user=self.user,
                            )
                            if ecc_result and ecc_result.get('detected'):
                                # Commitment formed → persist to DB
                                if ecc_result.get('commitment'):
                                    commitment_data = ecc_result['commitment']
                                    db_commit = create_db_commitment(
                                        user=self.user,
                                        commitment_data=commitment_data,
                                        conversation=conversation,
                                        tier=activation_state,
                                    )
                                    # Refresh pending list for context injection
                                    _ecc_pending = get_pending_commitments(self.user)
                                    cos_context['ecc_active_commitments'] = _ecc_pending
                                # Response covers all cases: tightening,
                                # blocked renegotiation, confirmation, or limit
                                if ecc_result.get('response'):
                                    return ecc_result['response']

                            # Inject pending commitments into context
                            if _ecc_pending:
                                cos_context['ecc_active_commitments'] = _ecc_pending
                        except Exception as ecc_err:
                            logger.debug("ECC detection skipped: %s", ecc_err)

                        # ── Phase 5C HARD SHORT-CIRCUIT ──────────
                        # If closure was detected but a DB operation
                        # threw, bypass LLM generation entirely.
                        if _ecc_closure_handled and _ecc_closure_response:
                            return _ecc_closure_response
                        # ── End hard short-circuit ────────────────

                        # Phase 4 R1: Decision Branch Gate evaluation
                        cos_context['decision_branch_gate'] = (
                            evaluate_decision_branch_gate(cos_context, message)
                        )

                    cos_injection = format_cos_system_injection(cos_context)
                    # Append operational context AFTER personality layers
                    # so the LLM prioritizes relationship over raw data.
                    append_layers.append(cos_injection)
                except Exception as cos_ctx_err:
                    logger.debug("CoS context skipped: %s", cos_ctx_err)

                # Pending reflections (check-ins after events)
                try:
                    from apps.core.blueprint.reflection_engine import deliver_pending_reflections
                    pending_refs = deliver_pending_reflections(self.user)
                    if pending_refs:
                        ref_lines = ["--- PENDING CHECK-INS ---"]
                        for ref in pending_refs[:2]:
                            ref_lines.append(
                                f"- After '{ref['title']}': {ref['question']} "
                                f"(reflection_id={ref['id']})"
                            )
                        ref_lines.append(
                            "If the user's message relates to any of these, "
                            "treat it as a reflection response. Otherwise, "
                            "naturally mention the check-in when appropriate."
                        )
                        append_layers.append("\n".join(ref_lines))
                except Exception as ref_err:
                    logger.debug("Reflection context injection skipped: %s", ref_err)

                # ----------------------------------------------------------
                # Assemble final prompt: priority layers → base → appended
                # ----------------------------------------------------------
                assembled_parts = priority_layers + [system_prompt] + append_layers
                system_prompt = "\n\n".join(part for part in assembled_parts if part)

        except Exception as cos_err:
            logger.debug("CoS context injection skipped: %s", cos_err)

        # Executive Briefing (replaces simple greeting injection)
        # Delivers morning briefing, gap detection, life events, health gates,
        # journal follow-ups on first-of-day or gap re-entry interactions.
        briefing = ""
        try:
            from apps.ai.executive_briefing import (
                build_executive_briefing,
                get_conversation_memory,
            )
            briefing = build_executive_briefing(self.user, conversation)
            if briefing:
                system_prompt += "\n\n" + briefing

            # Inject conversation memory (rolling summary of older messages)
            memory = get_conversation_memory(conversation)
            if memory:
                system_prompt += "\n\n" + memory
        except Exception:
            pass  # Executive briefing must never break chat

        # Executive Arbitration Engine (EAE) — Phase 8
        # When enabled, EAE is the FINAL authority on what intelligence is
        # surfaced. It replaces UAL's narrative injection with a budgeted,
        # scored, deduplicated intelligence briefing with tone directives.
        # Feature-flagged: eae_enabled=False → existing UAL behavior unchanged.
        _eae_active = False
        try:
            from apps.core.blueprint.models import PersonalOperatingBlueprint
            _bp = PersonalOperatingBlueprint.objects.filter(user=self.user).first()
            if _bp and _bp.eae_enabled:
                from apps.core.ai_eae.eae_engine import arbitrate
                from apps.core.ai_eae.constants import CHANNEL_CHAT
                eae_result = arbitrate(self.user, channel=CHANNEL_CHAT)
                if eae_result.prompt_injection:
                    system_prompt += "\n\n" + eae_result.prompt_injection
                    _eae_active = True
        except Exception:
            pass  # EAE must never break chat

        # Universal Arbitration Layer (UAL)
        # Sits between signal generation and user-facing intervention.
        # Classifies dominant scenario, fuses cross-domain signals,
        # selects ONE executive narrative, and shapes AI framing.
        # SKIPPED when EAE is active — EAE supersedes UAL for chat.
        if not _eae_active:
            try:
                from apps.core.ai_arbitration import run_arbitration
                arbitration = run_arbitration(self.user)
                if arbitration and arbitration.narrative_injection:
                    system_prompt += "\n\n" + arbitration.narrative_injection
            except Exception:
                pass  # UAL must never break chat

        # Greeting detection — both fresh-session and mid-conversation
        message_lower = message.lower()
        is_greeting = any(g in message_lower for g in [
            'good morning', 'morning', 'good afternoon', 'good evening',
            'hello', 'hey', 'hi', 'howdy', "what's up", 'sup',
        ])
        if is_greeting:
            try:
                from apps.core.utils import get_user_now
                user_now = get_user_now(self.user)
                time_of_day = 'morning' if user_now.hour < 12 else (
                    'afternoon' if user_now.hour < 17 else 'evening'
                )
                if briefing:
                    # Fresh session (first-of-day or gap re-entry):
                    # The briefing gives situational data but the LLM still sees
                    # old conversation history. Explicitly tell it to start fresh.
                    greeting_injection = (
                        f"\n--- FRESH SESSION GREETING ---\n"
                        f"The user is greeting you for a new {time_of_day} session "
                        f"({user_now.strftime('%I:%M %p').lstrip('0')}). "
                        f"This is a FRESH START. Do NOT reference or continue topics "
                        f"from previous conversations — the user has moved on. "
                        f"Focus on their current day: priorities, schedule, "
                        f"and anything that needs attention RIGHT NOW. "
                        f"Use the EXECUTIVE BRIEFING and OPERATIONAL CONTEXT "
                        f"above — not old conversation threads.\n"
                    )
                else:
                    # Mid-conversation greeting (same session, no briefing fired)
                    greeting_injection = (
                        f"\n--- GREETING CONTEXT ---\n"
                        f"The user just greeted you ({time_of_day}, "
                        f"{user_now.strftime('%I:%M %p').lstrip('0')}). "
                        f"Reference their schedule from OPERATIONAL CONTEXT. "
                        f"Be conversational, not robotic.\n"
                    )
                system_prompt += greeting_injection
            except Exception:
                pass

        # Context reset detection — user says "not on that page", "old request", etc.
        # When user explicitly says they've moved on, suppress old topic references.
        _context_reset_phrases = [
            'not on that page', 'not even on that page',
            "i'm not on", "im not on", 'not that page',
            'old request', 'that was before', 'that was old',
            'moved on', 'different page', 'different topic',
            'forget that', 'never mind that', 'stop talking about',
            'i already moved on', "that's not what i",
            "that's not relevant", 'not what i asked',
        ]
        if any(phrase in message_lower for phrase in _context_reset_phrases):
            system_prompt += (
                "\n--- CONTEXT RESET ---\n"
                "The user has explicitly indicated they are NOT on the previous "
                "page/topic anymore. STOP referencing any previous conversation "
                "topic. Ask what they need help with NOW, or use the OPERATIONAL "
                "CONTEXT to share what's relevant to their current situation.\n"
            )

        # Check if user is asking about tasks/priorities/habits/focus
        # Include full state data so the AI can give data-driven answers
        is_asking_about_tasks = any(phrase in message_lower for phrase in [
            'what do i have', 'what\'s left', 'what tasks', 'what should i',
            'my priorities', 'my tasks', 'overdue', 'due today', 'to do',
            'what remains', 'what still needs', 'focus on', 'left to do',
            'what needs to be done', 'what\'s remaining', 'how many tasks',
        ])

        # Also check for broader analysis questions about habits, consistency, focus areas
        is_asking_for_analysis = any(phrase in message_lower for phrase in [
            'need to focus', 'need to improve', 'need to work on',
            'strengthen', 'weakness', 'falling behind', 'doing well',
            'my habits', 'my consistency', 'my streaks', 'my patterns',
            'missed', 'skipped', 'how many days',
            'since i started', 'how consistent', 'how am i doing',
            'how have i done', 'how did i do', 'how\'s my day',
            'where am i', 'where do i need', 'where should i',
            'what areas', 'which areas',
            # Health data visibility questions
            'health data', 'healthkit', 'health records', 'health metrics',
            'my health', 'my vitals', 'vital signs', 'see my data',
            'see any data', 'new data', 'new activity', 'synced data',
            'apple health',
        ])

        # Check-in / day assessment — user wants a full CoS briefing
        is_requesting_checkin = any(phrase in message_lower for phrase in [
            'check in', 'checking in', 'check-in',
            'how is my day', 'how\'s my day',
            'how does my day look', 'how\'s my schedule',
            'what\'s my day look like', 'give me a rundown',
            'brief me', 'briefing', 'daily briefing',
            'what do i have today', 'what\'s on my plate',
            'status update', 'status report', 'give me my status',
            'what am i looking at today', 'run down my day',
        ])

        if is_asking_about_tasks or is_asking_for_analysis or is_requesting_checkin:
            # User is asking about tasks or wants analysis - include full state context
            state = self.assess_current_state()
            time_context = self._get_time_context()
            tasks = state.get('tasks', {})
            remaining_tasks = tasks.get('due_today', 0) + tasks.get('overdue', 0)

            if is_requesting_checkin:
                # FULL CoS BRIEFING — with SPECIFIC item names, not just counts.
                # User explicitly asked for a check-in — give them actionable specifics
                # so they can knock items out. Never throttled.
                from apps.core.utils import get_user_today, get_user_now
                from apps.ai.executive_briefing import (
                    _build_health_gate_section,
                    _build_day_overview_section,
                )
                today = get_user_today(self.user)
                user_now = get_user_now(self.user)

                faith = state.get('faith', {})
                health = state.get('health', {})
                reading_status = "completed today" if faith.get('reading_completed_today') else (
                    "not yet done today" if faith.get('active_reading_plans', 0) > 0 else "no active plan"
                )
                workout_today = health.get('workout_today', False)
                workout_status = "logged today" if workout_today else "not yet logged"

                # Pull calendar + health gate data from executive briefing
                health_gate = ''
                day_overview = ''
                try:
                    health_gate = _build_health_gate_section(self.user, today)
                except Exception:
                    pass
                try:
                    day_overview = _build_day_overview_section(self.user, user_now, today)
                except Exception:
                    pass

                # ── Pull SPECIFIC ITEMS (not just counts) ──
                # Tasks: actual names of overdue and due-today tasks
                task_details = ''
                try:
                    from apps.life.models import Task as LifeTask
                    overdue_tasks = list(LifeTask.objects.filter(
                        user=self.user, is_completed=False, due_date__lt=today
                    ).exclude(status='deleted').values_list('title', flat=True)[:10])
                    due_today_tasks = list(LifeTask.objects.filter(
                        user=self.user, is_completed=False, due_date=today
                    ).exclude(status='deleted').values_list('title', flat=True)[:10])
                    completed_today_tasks = list(LifeTask.objects.filter(
                        user=self.user, is_completed=True, completed_at__date=today
                    ).exclude(status='deleted').values_list('title', flat=True)[:10])

                    parts = []
                    if overdue_tasks:
                        parts.append(f"OVERDUE ({len(overdue_tasks)}):\n" + '\n'.join(f'  • {t}' for t in overdue_tasks))
                    if due_today_tasks:
                        parts.append(f"DUE TODAY ({len(due_today_tasks)}):\n" + '\n'.join(f'  • {t}' for t in due_today_tasks))
                    if completed_today_tasks:
                        parts.append(f"COMPLETED TODAY ({len(completed_today_tasks)}):\n" + '\n'.join(f'  ✓ {t}' for t in completed_today_tasks))
                    if not parts:
                        parts.append("No tasks due today and nothing overdue.")
                    task_details = '\n'.join(parts)
                except Exception:
                    task_details = f"Tasks remaining: {remaining_tasks}"

                # Goals: actual goal titles
                goal_details = ''
                try:
                    from apps.purpose.models import LifeGoal
                    active_goals = list(LifeGoal.objects.filter(
                        user=self.user, status='active'
                    ).exclude(deleted_at__isnull=False).values_list('title', flat=True)[:10])
                    if active_goals:
                        goal_details = '\n'.join(f'  • {g}' for g in active_goals)
                    else:
                        goal_details = 'No active goals.'
                except Exception:
                    goal_details = f"Active goals: {state.get('goals', {}).get('active', 0)}"

                # Prayers: actual prayer request titles/summaries
                prayer_details = ''
                try:
                    from apps.faith.models import PrayerRequest
                    active_prayers = list(PrayerRequest.objects.filter(
                        user=self.user, is_answered=False
                    ).exclude(status='deleted').values_list('title', flat=True)[:15])
                    if active_prayers:
                        prayer_details = f"Active prayer requests ({len(active_prayers)}):\n" + '\n'.join(f'  • {p}' for p in active_prayers)
                    else:
                        prayer_details = 'No active prayer requests.'
                except Exception:
                    prayer_details = f"Active prayers: {faith.get('active_prayers', 0)}"

                # Medications: actual med names and what's outstanding
                med_details = ''
                try:
                    from apps.health.models import Medicine, MedicineLog
                    active_meds = Medicine.objects.filter(
                        user=self.user, medicine_status=Medicine.STATUS_ACTIVE,
                    ).exclude(status='deleted')

                    taken_meds = []
                    untaken_meds = []
                    for med in active_meds:
                        schedules = med.schedules.all()
                        for sched in schedules:
                            taken = MedicineLog.objects.filter(
                                medicine=med,
                                scheduled_date=today,
                                log_status__in=['taken', 'late'],
                            ).exists()
                            time_str = sched.scheduled_time.strftime('%I:%M %p').lstrip('0') if sched.scheduled_time else ''
                            label = f"{med.name} ({time_str})" if time_str else med.name
                            if taken:
                                taken_meds.append(label)
                            else:
                                untaken_meds.append(label)

                    parts = []
                    if untaken_meds:
                        parts.append(f"NOT YET TAKEN ({len(untaken_meds)}):\n" + '\n'.join(f'  ⬜ {m}' for m in untaken_meds))
                    if taken_meds:
                        parts.append(f"TAKEN ({len(taken_meds)}):\n" + '\n'.join(f'  ✓ {m}' for m in taken_meds))
                    med_details = '\n'.join(parts) if parts else 'No active medications.'
                except Exception:
                    med_details = 'Medication data unavailable.'

                # Calendar: actual event names with times
                calendar_details = ''
                try:
                    from apps.calendar_engine.models import CalendarEvent
                    events = CalendarEvent.objects.filter(
                        user=self.user, start_dt__date=today
                    ).exclude(status='canceled').exclude(
                        deleted_at__isnull=False
                    ).order_by('start_dt')[:15]

                    if events.exists():
                        cal_lines = []
                        for evt in events:
                            local_start = evt.start_dt.astimezone(user_now.tzinfo)
                            time_str = local_start.strftime('%I:%M %p').lstrip('0')
                            status_mark = '✓' if evt.status == 'completed' else '·'
                            cal_lines.append(f"  {status_mark} {time_str} — {evt.title}")
                        calendar_details = '\n'.join(cal_lines)
                    else:
                        calendar_details = 'No events scheduled today.'
                except Exception:
                    calendar_details = day_overview or 'Calendar data unavailable.'

                system_prompt += f"""

USER IS REQUESTING A CHECK-IN / DAY BRIEFING — give a complete Chief of Staff assessment.
This is a user-initiated request. List SPECIFIC items by name so they can take action. Never give vague counts without the actual items.

TODAY'S CALENDAR:
{calendar_details}

MEDICATIONS:
{med_details}

HEALTH & ROUTINES:
{health_gate or 'No health gate data available.'}
- Reading plan / Quiet Time: {reading_status}
- Workout: {workout_status}

TASKS:
{task_details}

ACTIVE GOALS:
{goal_details}

FAITH:
{prayer_details}
- Journal streak: {state.get('journal', {}).get('streak', 0)} days

TIME CONTEXT:
- ~{time_context.get('hours_remaining', 'unknown')} hours until bedtime

INSTRUCTIONS:
- LIST the specific outstanding items BY NAME so the user can knock them out.
- Group by urgency: overdue first, then due today, then upcoming.
- For meds, list what's NOT taken yet by name — don't just say "74% adherence."
- For tasks, list each overdue/due-today task by title — don't just say "2 tasks due."
- For prayers, list them if fewer than 8; summarize if more.
- Note what IS done too (briefly) so they see progress.
- End with a prioritized recommendation: "Here's what I'd tackle first: ..."
- Be concise but SPECIFIC — this person wants an actionable list, not a motivational summary.
"""
            elif is_asking_for_analysis:
                faith = state.get('faith', {})
                health = state.get('health', {})
                reading_status = "completed today" if faith.get('reading_completed_today') else (
                    "not yet done today" if faith.get('active_reading_plans', 0) > 0 else "no active plan"
                )
                workout_today = health.get('workout_today', False)
                workout_status = "logged today" if workout_today else "not yet logged"
                system_prompt += f"""

USER IS ASKING FOR ANALYSIS OF THEIR DATA AND HABITS - provide specific, data-driven insights:
- Tasks REMAINING today: {remaining_tasks} ({tasks.get('overdue', 0)} overdue, {tasks.get('due_today', 0)} due today)
- Active goals needing progress: {state.get('goals', {}).get('active', 0)}
- Journal streak: {state.get('journal', {}).get('streak', 0)} days
- Active prayers: {faith.get('active_prayers', 0)}
- Reading plan / Quiet Time: {reading_status}
- Workout: {workout_status}
- Time remaining in day: ~{time_context.get('hours_remaining', 'unknown')} hours until bedtime

IMPORTANT: The user wants YOU to analyze their data and tell them where to focus.
Do NOT tell them to go to a page or click a link. ANALYZE the data you have and give specific insights.
If they ask about missed days or consistency, use the journal/health data to answer with real numbers.
CRITICAL: Only report items as "missed" or "not done" if the data explicitly confirms they are not done.
Never assume something is missed just because you lack data — absence of data is not evidence of absence.
"""
            else:
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

        # Phase 3a: Inject relevant past conversations from long-term memory (RAG)
        try:
            from apps.ai.memory_service import get_memory_context_block
            memory_block = get_memory_context_block(self.user, message)
            if memory_block:
                system_prompt += memory_block
        except Exception as mem_err:
            logger.debug("Memory retrieval skipped: %s", mem_err)

        # Add page context if provided - helps assistant give context-aware responses
        if page_context:
            page_url = page_context.get('url', '')
            page_module = page_context.get('module', '')
            page_title = page_context.get('page_title', '')
            page_content = page_context.get('page_content')

            # Log page context for debugging context-awareness issues
            if page_content:
                content_type = page_content.get('type', 'unknown')
                has_scripture = bool(page_content.get('scripture_text'))
                has_refs = bool(page_content.get('scriptures'))
                logger.info(
                    "Page context: url=%s type=%s has_scripture_text=%s "
                    "has_refs=%s keys=%s",
                    page_url, content_type, has_scripture, has_refs,
                    list(page_content.keys()),
                )
            else:
                logger.info("Page context: url=%s (no page_content)", page_url)

            # Inject session activity — shows what pages user visited recently
            session_activity = page_context.get('session_activity', [])
            if session_activity and len(session_activity) > 1:
                activity_lines = []
                for sa in session_activity[-8:]:  # Last 8 pages
                    activity_lines.append(f"  {sa.get('time', '?')}: {sa.get('title', sa.get('url', '?'))}")
                system_prompt += f"""
SESSION ACTIVITY (what the user has been doing this session):
{chr(10).join(activity_lines)}
Current page: {page_title or page_context.get('url', '')}
Use this to understand the user's current flow and intent. If they navigated from one module to another, their question likely relates to their current page, not where they were before.
"""

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
                    content_description = "\nREADING PLAN CONTENT (user is actively reading this scripture):\n"
                    content_description += "IMPORTANT: The user is on their Bible reading plan. When they ask questions about faith, scripture, theology, or use words like 'this', 'it', 'the sabbath', 'Jesus', etc., they are asking about the scripture below — NOT about their tasks, routines, or schedule. Always answer in the context of the scripture they are reading.\n\n"
                    if page_content.get('current_day'):
                        content_description += f"- {page_content['current_day']}\n"
                    if page_content.get('reading_title'):
                        content_description += f"- Theme: {page_content['reading_title']}\n"
                    if page_content.get('difficulty_level'):
                        content_description += f"- Study Level: {page_content['difficulty_level']}\n"
                    if page_content.get('scriptures'):
                        content_description += f"- Scriptures: {', '.join(page_content['scriptures'])}\n"
                    if page_content.get('scripture_text'):
                        scripture_text = page_content['scripture_text'][:3000]
                        content_description += f"- Scripture Text (what user is reading):\n{scripture_text}\n"
                    elif page_content.get('scriptures'):
                        # Scripture text not extracted (may not be expanded or loaded yet),
                        # but we know which passages the user is reading — instruct AI to
                        # use its training knowledge of these specific passages.
                        refs = ', '.join(page_content['scriptures'])
                        content_description += (
                            f"- Scripture text not available in context, but the user is "
                            f"reading: {refs}. Use your knowledge of these Bible passages "
                            f"to answer their questions. Do NOT ask them to provide the "
                            f"scripture — you know which passages they are reading.\n"
                        )
                    if page_content.get('context_summary'):
                        content_description += f"- Context (who/when/setting): {page_content['context_summary'][:400]}...\n" if len(page_content.get('context_summary', '')) > 400 else f"- Context: {page_content['context_summary']}\n"
                    if page_content.get('commentary'):
                        content_description += f"- Commentary: {page_content['commentary'][:500]}...\n" if len(page_content.get('commentary', '')) > 500 else f"- Commentary: {page_content['commentary']}\n"
                    elif page_content.get('devotional'):
                        content_description += f"- Devotional: {page_content['devotional'][:300]}...\n" if len(page_content.get('devotional', '')) > 300 else f"- Devotional: {page_content['devotional']}\n"
                    if page_content.get('reflection_prompt'):
                        content_description += f"- Reflection Question: {page_content['reflection_prompt']}\n"
                    if page_content.get('user_notes'):
                        content_description += f"- User's Notes/Reflections: {page_content['user_notes']}\n"
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
                    if page_content.get('progress'):
                        content_description += f"- Progress: {page_content['progress']}\n"
                    if page_content.get('target_date'):
                        content_description += f"- Target date: {page_content['target_date']}\n"
                    if page_content.get('milestones'):
                        content_description += f"- Milestones: {'; '.join(page_content['milestones'][:5])}\n"

                elif content_type == 'habit':
                    content_description = "\nHABIT (user is viewing this):\n"
                    if page_content.get('title'):
                        content_description += f"- Habit: {page_content['title']}\n"
                    if page_content.get('streak'):
                        content_description += f"- Current streak: {page_content['streak']}\n"
                    if page_content.get('completion_info'):
                        content_description += f"- Completion: {page_content['completion_info']}\n"

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
                # Build context-priority instruction based on page type
                context_priority_instruction = ""
                if page_content:
                    content_type = page_content.get('type', '')
                    if content_type == 'reading_plan_progress':
                        context_priority_instruction = """
CONTEXT PRIORITY: The user is actively reading scripture. Unless they EXPLICITLY say "about my tasks", "about my routine", "about my schedule", or similar — assume their question is about the scripture/faith content above. Words like "this", "it", "what does it mean", "the sabbath", "Jesus", "God", names of biblical figures, or ANY theological/spiritual topic should be answered from the scripture context, even if the previous conversation was about something else entirely.
"""
                    elif content_type in ('journal_entry', 'goal', 'prayer_request', 'task'):
                        context_priority_instruction = f"""
CONTEXT PRIORITY: The user is viewing a specific {content_type.replace('_', ' ')}. When they say "this", "it", or ask about details, they mean the {content_type.replace('_', ' ')} described above — not something from earlier conversation unless they explicitly reference it.
"""

                system_prompt += f"""
PAGE CONTEXT (where the user is currently viewing):
{chr(10).join('- ' + p for p in context_parts) if context_parts else ''}
{content_description}
{context_priority_instruction}
When the user asks about "this page", "this scripture", "this entry", etc., they are referring to the content above.
Use this context to provide relevant, contextual help. For scripture questions, explain the passage and its meaning.
"""

            # Voice mode: user is speaking via microphone, response will be read aloud
            if page_context.get('voice_input'):
                system_prompt += """
VOICE MODE — The user is speaking to you via voice input. Your response will be read aloud using text-to-speech.
Rules for voice responses:
- Write in natural, conversational speech — as if you're talking face-to-face
- NO markdown formatting (no **, no ##, no bullet points, no numbered lists)
- NO special characters or symbols that sound awkward when read aloud
- Use short, clear sentences. Pause naturally with periods.
- Be warm and direct — you're having a spoken conversation
- Keep responses concise (2-4 sentences for simple questions)
- Never say "I can't hear you" — the speech was transcribed to text before reaching you
"""

        # COS-CX5: Diagnostic context expansion for WHY questions
        # Injects cross-domain causal signals when user asks diagnostic questions
        try:
            from apps.cos.context.diagnostic_context import (
                is_diagnostic_query, build_diagnostic_context,
            )
            if is_diagnostic_query(message):
                from apps.core.utils import get_user_now
                _cx5_now = get_user_now(self.user)
                _cx5_block = build_diagnostic_context(self.user, _cx5_now, message)
                if _cx5_block:
                    system_prompt += "\n\n" + _cx5_block
        except Exception:
            pass  # CX5 must never break chat

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

        # Build structured conversation history for OpenAI message threading.
        # Instead of embedding history as flat text in the user prompt,
        # we pass it as proper {"role": "user/assistant"} message objects.
        #
        # CRITICAL: On new sessions (briefing fired), limit history to current
        # session only. Old session history causes the LLM to latch onto stale
        # topics (e.g., yesterday's scripture discussion) instead of responding
        # to the current greeting/situation. The executive briefing + COS-CX
        # already provide all needed situational awareness.
        from apps.ai.conversation.message_builder import build_messages_from_history

        _history_for_builder = history
        if briefing:
            # New session: only include today's messages to prevent stale
            # topic bleeding from previous sessions
            try:
                from apps.core.utils import get_user_today
                _today = get_user_today(self.user)
                _history_for_builder = history.filter(
                    created_at__date=_today,
                )
            except Exception:
                pass  # Fall back to full history on error

        conversation_history = build_messages_from_history(
            _history_for_builder, message,
        )

        # Also build a simple list for topic threading keyword extraction
        # (uses same session-filtered history when applicable)
        history_list = list(reversed(list(_history_for_builder)[:20]))

        # =============================================================
        # Phase 2b: Conversation Topic Threading
        # Detect when the user's message relates to the page they're on
        # vs. a previous conversation thread, and inject a threading hint.
        # =============================================================
        topic_threading_hint = ""
        if page_context and history_list:
            current_page_url = page_context.get('url', '')
            page_content_obj = page_context.get('page_content')
            page_content_type = page_content_obj.get('type', '') if page_content_obj else ''

            # Check if the user navigated to a new page since last message
            # (i.e., page context differs from what was discussed)
            last_user_msgs = [m for m in history_list if m.role == 'user']
            prev_topic_keywords = set()
            if last_user_msgs:
                # Extract keywords from recent conversation
                for m in last_user_msgs[-3:]:
                    prev_topic_keywords.update(
                        w.lower().strip('.,!?;:') for w in m.content.split()
                        if len(w) > 3
                    )

            # If page context exists and is rich (not just URL), signal topic
            if page_content_type:
                msg_lower = message.lower()
                # Detect if user is asking about the page ("this", "it", etc.)
                page_referent_words = ['this', 'it', 'here', 'the page', 'what i see',
                                       'what am i looking at', 'current']
                refers_to_page = any(w in msg_lower for w in page_referent_words)

                # Detect if user is continuing a previous thread
                continues_thread = False
                thread_signals = ['also', 'and what about', 'going back to',
                                  'earlier', 'you said', 'we talked about',
                                  'you mentioned', 'continuing']
                continues_thread = any(s in msg_lower for s in thread_signals)

                if refers_to_page and not continues_thread:
                    topic_threading_hint = (
                        "\nTOPIC SIGNAL: The user appears to be asking about the page "
                        "they're currently viewing. Prioritize page context over "
                        "earlier conversation topics.\n"
                    )
                elif continues_thread:
                    topic_threading_hint = (
                        "\nTOPIC SIGNAL: The user appears to be continuing an earlier "
                        "conversation thread. Reference the relevant earlier exchange "
                        "and build on it naturally.\n"
                    )

        # Get user's first name for natural conversation
        user_name = self.user.first_name or self.user.get_short_name() or ""

        # Build the user prompt, noting if an image is attached
        if image_data and image_mime_type:
            image_note = "\n\n[The user has attached an image. Please analyze and respond to it along with their message.]"
        else:
            image_note = ""

        # =============================================================
        # Response Mode Classifier — adapts depth, tokens, rules
        # =============================================================
        is_analysis = is_asking_for_analysis
        response_mode = self._classify_response_mode(
            message, is_analysis, is_asking_about_tasks
        )

        # Per-mode rules injected into user prompt (invisible to user)
        mode_rules = {
            'brief': (
                "- This is a simple question. Answer in 1-3 sentences max.\n"
                "- Do NOT restate the question. Do NOT add follow-ups."
            ),
            'deep': (
                "- Give specific data-driven insights with real numbers.\n"
                "- Use concise structured bullets where helpful.\n"
                "- Do NOT pad with filler. Be thorough but efficient."
            ),
            'adaptive': (
                "- Answer what was asked. Match the depth of their message.\n"
                "- Do NOT restate the question. Do NOT add follow-ups."
            ),
        }
        rules_block = mode_rules.get(response_mode, mode_rules['adaptive'])

        # Per-user response style preference (admin-configurable)
        style_pref = getattr(self.prefs, 'cos_response_style', 'balanced')
        style_nudge = ''
        if style_pref == 'concise':
            style_nudge = '- Prefer the shortest accurate answer possible.\n'
        elif style_pref == 'strategic':
            style_nudge = '- Include strategic framing and next-step suggestions.\n'
        elif style_pref == 'deep_dive':
            style_nudge = '- Provide comprehensive analysis when data supports it.\n'

        # =============================================================
        # Phase 4a: Pre-Response Reasoning Step ("Think Before Speaking")
        # Inject chain-of-thought instruction so the model reasons about
        # context before generating the visible response. The reasoning
        # is internal — only the final answer is shown to the user.
        # =============================================================
        reasoning_instruction = """
Before responding, silently reason through these steps (do NOT include this reasoning in your response):
1. What is the user's current context? (page they're viewing, time of day, recent session activity)
2. What are they most likely asking about — the page content, their data, or a previous conversation topic?
3. What data or context do I have that's directly relevant?
4. What should I NOT talk about? (avoid mixing unrelated topics — don't mention routines when they're asking about scripture, don't discuss scripture when they're asking about tasks)
Then give your response."""

        user_prompt = f"""{"The user's name is " + user_name + ". " if user_name else ""}{message}{image_note}
{topic_threading_hint}
{reasoning_instruction}

Rules for this response:
- Answer directly. Lead with the data when you have it.
{rules_block}
{style_nudge}- Be conversational and natural — speak like someone who knows this person
- If they're sharing something personal, engage with it genuinely before moving to action
- If following up on previous conversation, build on it naturally"""

        # Dynamic token limit keyed to response mode
        # Larger budgets allow deeper, more thoughtful responses
        mode_tokens = {'brief': 400, 'adaptive': 800, 'deep': 1200}
        max_tokens = mode_tokens.get(response_mode, 800)

        # Temperature: warm enough for natural conversation, lower for data accuracy
        has_personal_data = personal_data_result.get('has_data', False)
        temperature = 0.4 if (has_personal_data or is_analysis or is_asking_about_tasks) else 0.65

        try:
            response = ai_service._call_api(
                system_prompt,
                user_prompt,
                max_tokens=max_tokens,
                image_data=image_data,
                image_mime_type=image_mime_type,
                temperature=temperature,
                endpoint='cos_chat',
                user=self.user,
                conversation_history=conversation_history,
            ) or self._get_fallback_response(message)

            # Write-suppressed behavior is now enforced at generation time
            # via COS_WRITE_SUPPRESSED_CONTRACT in the system prompt.
            # Post-generation compliance gate removed — prompt-level enforcement only.

            # =============================================================
            # Phase 4c: Response Quality Validation
            # Lightweight post-generation check. If the response clearly
            # violates context priority (e.g., talking about routines when
            # user asked about scripture), regenerate with stronger emphasis.
            # Only triggers on high-confidence mismatches to avoid cost.
            # =============================================================
            if page_context and response:
                validation_issue = self._validate_response_context(
                    message, response, page_context
                )
                if validation_issue:
                    logger.info(
                        "Response quality validation failed (%s), regenerating",
                        validation_issue,
                    )
                    # Regenerate with explicit correction
                    correction = (
                        f"\n\nCRITICAL CORRECTION: Your previous response was "
                        f"about {validation_issue} but the user is asking about "
                        f"the content on their current page. ONLY answer about "
                        f"the page context. Do NOT discuss unrelated topics."
                    )
                    response = ai_service._call_api(
                        system_prompt + correction,
                        user_prompt,
                        max_tokens=max_tokens,
                        image_data=image_data,
                        image_mime_type=image_mime_type,
                        temperature=0.3,  # Lower for correction
                        endpoint='cos_chat',
                        user=self.user,
                        conversation_history=conversation_history,
                    ) or response  # Fall back to original if regen fails

            return response
        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return self._get_fallback_response(message)

    def _try_calibration_intents(self, message, intent_service, actions_taken):
        """During calibration, only allow pause/complete intents.

        Returns response string if a calibration intent was matched,
        or None to fall through to normal _generate_response().
        """
        CALIBRATION_ONLY_INTENTS = {'pause_calibration', 'complete_calibration'}
        try:
            results = intent_service.recognize_intents(message, self.user)
            cal_intents = [
                r for r in results
                if r.intent_type in CALIBRATION_ONLY_INTENTS
            ]
            if not cal_intents:
                return None

            from apps.core.ai_orchestrator.orchestrator import enrich_and_execute
            from apps.core.ai_orchestrator.orchestrator import (
                process_user_input as orchestrator_process,
            )
            orch_result = orchestrator_process(self.user, message)
            orch_actions = enrich_and_execute(
                self.user, cal_intents, orch_result)
            parts = []
            for ar in orch_actions:
                if ar.success:
                    actions_taken.append(self._build_action_taken(ar))
                parts.append(ar.message)
            return " ".join(parts) if parts else None
        except Exception as e:
            logger.debug("Calibration intent check failed: %s", e)
            return None

    def _try_learning_mode_control_intents(self, message, intent_service, actions_taken):
        """During Learning Mode, check for enter/exit control-plane intents.

        These bypass UAIO suppression and execute directly.
        Returns response string if a control-plane intent was matched,
        or None to fall through to normal intent flow (which will
        handle domain intents via the suppression gate).
        """
        LEARNING_MODE_CONTROL_INTENTS = {'enter_learning_mode', 'exit_learning_mode'}
        try:
            results = intent_service.recognize_intents(message, self.user)
            lm_intents = [
                r for r in results
                if r.intent_type in LEARNING_MODE_CONTROL_INTENTS
            ]
            if not lm_intents:
                return None

            from apps.core.ai_orchestrator.orchestrator import enrich_and_execute
            from apps.core.ai_orchestrator.orchestrator import (
                process_user_input as orchestrator_process,
            )
            orch_result = orchestrator_process(self.user, message)
            orch_actions = enrich_and_execute(
                self.user, lm_intents, orch_result)
            parts = []
            for ar in orch_actions:
                if ar.success:
                    actions_taken.append(self._build_action_taken(ar))
                parts.append(ar.message)
            return " ".join(parts) if parts else None
        except Exception as e:
            logger.debug("Learning mode control intent check failed: %s", e)
            return None

    def _is_calibration_active(self) -> bool:
        """Check if user is in active calibration (getting-to-know-you) mode.

        During calibration, the AI should only listen and ask questions —
        no action intents should be recognized or executed.
        """
        try:
            if not getattr(self.prefs, 'personal_assistant_enabled', False):
                return False
            from apps.core.blueprint.cos_governance import get_calibration_state
            cal_state = get_calibration_state(self.user)
            return (
                cal_state is not None
                and cal_state['active']
                and not cal_state['paused']
            )
        except Exception:
            return False

    # -----------------------------------------------------------------
    # Phase 4c: Response Quality Validator
    # -----------------------------------------------------------------
    @staticmethod
    def _validate_response_context(
        user_message: str,
        response: str,
        page_context: dict,
    ) -> Optional[str]:
        """Validate that the response matches the user's page context.

        Returns None if valid, or a short description of the mismatch
        (e.g., "work routines" when user asked about scripture).

        Only triggers on high-confidence mismatches to avoid false positives.
        Cost: Zero (keyword-based, no API call).
        """
        page_content = page_context.get('page_content')
        if not page_content:
            return None

        content_type = page_content.get('type', '')
        msg_lower = user_message.lower()
        resp_lower = response.lower()

        # Validation rule 1: Scripture page + scripture question, but response
        # talks about tasks/routines/schedule instead OR asks user to provide
        # scripture that's already in the context
        if content_type == 'reading_plan_progress':
            scripture_signals = [
                'scripture', 'verse', 'passage', 'bible', 'sabbath', 'jesus',
                'god', 'faith', 'pray', 'pharisee', 'heal', 'miracle',
                'parable', 'disciple', 'apostle', 'temple', 'commandment',
                'this mean', 'what does', 'explain', 'the passage',
            ]
            user_asks_about_scripture = any(s in msg_lower for s in scripture_signals)

            if user_asks_about_scripture:
                # Check if response is about routines/tasks instead
                off_topic_signals = [
                    'your routine', 'your schedule', 'your tasks',
                    'quiet time routine', 'morning routine', 'workout routine',
                    'daily routine', 'here\'s your', 'let\'s look at your day',
                    'your to-do', 'your priorities',
                ]
                for signal in off_topic_signals:
                    if signal in resp_lower:
                        return "work routines/schedule instead of scripture"

                # Check if response asks user to provide/share scripture that's
                # already available in the context (context-unaware response)
                has_scripture_context = (
                    page_content.get('scripture_text')
                    or page_content.get('scriptures')
                )
                if has_scripture_context:
                    provide_signals = [
                        'please provide', 'please share', 'could you provide',
                        'could you share', 'which scripture', 'which passage',
                        'which verse', 'what scripture', 'what passage',
                        'specify the scripture', 'specify the passage',
                        'let me know which', 'tell me which',
                    ]
                    for signal in provide_signals:
                        if signal in resp_lower:
                            return "asking user to provide scripture already in context"

        # Validation rule 2: Goal/task page + page-referent question, but
        # response doesn't mention the goal/task at all
        if content_type in ('goal', 'task') and page_content.get('title'):
            page_referents = ['this', 'it', 'the goal', 'the task', 'my progress']
            if any(r in msg_lower for r in page_referents):
                title_words = set(
                    w.lower() for w in page_content['title'].split()
                    if len(w) > 3
                )
                # If the response doesn't contain ANY significant word from
                # the title, it probably missed context
                if title_words and not any(w in resp_lower for w in title_words):
                    return f"unrelated content instead of the {content_type}"

        # Validation rule 3: Journal entry page, user asks about "this entry"
        # but response doesn't reference the entry content
        if content_type == 'journal_entry' and page_content.get('body'):
            if 'this entry' in msg_lower or 'this journal' in msg_lower:
                body_words = set(
                    w.lower() for w in page_content['body'].split()
                    if len(w) > 4
                )
                # Sample check — need at least one overlap
                if body_words and not any(w in resp_lower for w in list(body_words)[:20]):
                    return "unrelated content instead of the journal entry"

        return None

    # -----------------------------------------------------------------
    # Response-mode classifier (Phase 2B)
    # -----------------------------------------------------------------
    @staticmethod
    def _classify_response_mode(
        message: str,
        is_analysis: bool,
        is_task_query: bool,
    ) -> str:
        """Classify user message into brief / deep / adaptive mode.

        This drives token budget and per-response rules without exposing
        the classification to the user.
        """
        if is_analysis or is_task_query:
            return 'deep'

        msg = message.strip()
        msg_lower = msg.lower()

        # Brief: short questions, yes/no, confirmations, greetings
        if len(msg) < 40 and '?' in msg:
            return 'brief'
        if msg_lower in ('yes', 'no', 'ok', 'sure', 'thanks', 'thank you',
                         'got it', 'cool', 'yep', 'nope', 'done'):
            return 'brief'

        # Deep: explicit strategic/analytical keywords
        deep_signals = [
            'analyze', 'analysis', 'design', 'architecture', 'strategy',
            'plan for', 'break down', 'deep dive', 'compare',
            'pros and cons', 'trade-offs', 'evaluate', 'assess',
        ]
        if any(kw in msg_lower for kw in deep_signals):
            return 'deep'

        return 'adaptive'

    def _get_fallback_response(self, message: str) -> str:
        """Get fallback response when AI is unavailable, matching coaching style."""
        import random

        # Check if the message is a personal reflection/sharing (emotional content)
        if self._is_personal_reflection(message):
            return self._get_reflection_response(message)

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

    def _is_personal_reflection(self, message: str) -> bool:
        """Check if the message is a personal reflection or emotional sharing."""
        msg_lower = message.lower()

        # Indicators of personal reflection/emotional sharing
        reflection_indicators = [
            'i feel', 'i felt', 'i\'m feeling', 'feeling',
            'i\'ve been', 'i have been', 'i was',
            'my life', 'my mood', 'my journey',
            'improved', 'better', 'worse', 'struggling',
            'grateful', 'thankful', 'blessed',
            'closer to god', 'faith', 'spiritual',
            'accomplishing', 'accomplished', 'achieving',
            'journaling', 'reflecting', 'meditation',
            'happy', 'sad', 'anxious', 'excited', 'proud',
            'since', 'lately', 'recently',
        ]

        # Check for multiple indicators (more confident detection)
        indicator_count = sum(1 for ind in reflection_indicators if ind in msg_lower)

        # Also check for first-person sharing patterns
        first_person_sharing = (
            msg_lower.startswith('i ') or
            msg_lower.startswith('i\'') or
            ' i ' in msg_lower or
            'my ' in msg_lower
        )

        # Consider it a reflection if there are 2+ indicators or if first-person + 1 indicator
        return indicator_count >= 2 or (first_person_sharing and indicator_count >= 1)

    def _get_reflection_response(self, message: str) -> str:
        """Generate a meaningful response to personal reflections."""
        import random
        msg_lower = message.lower()

        # Detect positive vs challenging reflections
        positive_words = ['improved', 'better', 'good', 'great', 'happy', 'grateful',
                         'thankful', 'blessed', 'accomplishing', 'closer', 'proud']
        challenging_words = ['struggling', 'hard', 'difficult', 'worse', 'sad',
                            'anxious', 'worried', 'stressed', 'tired', 'overwhelmed']

        is_positive = any(word in msg_lower for word in positive_words)
        is_challenging = any(word in msg_lower for word in challenging_words)

        # Check for specific themes
        is_faith_related = any(word in msg_lower for word in ['god', 'faith', 'spiritual', 'prayer', 'church'])
        is_journaling_related = 'journal' in msg_lower
        is_health_related = any(word in msg_lower for word in ['health', 'workout', 'exercise', 'sleep', 'eating'])

        # Build contextual responses
        if is_positive:
            positive_responses = {
                'direct': [
                    "That's real progress. Keep doing what's working.",
                    "Solid growth. You've put in the work.",
                    "That momentum is yours. You earned it.",
                ],
                'gentle': [
                    "That's wonderful to hear. It sounds like your efforts are making a real difference.",
                    "What you're describing takes real commitment. That growth is meaningful.",
                    "Thank you for sharing that. It's clear you've been putting in genuine effort.",
                ],
                'supportive': [
                    "That's meaningful progress. It sounds like you've found something that works for you.",
                    "It takes dedication to see that kind of change. You should feel good about where you're heading.",
                    "That kind of growth doesn't happen by accident. Your consistency is paying off.",
                ],
            }
            base_responses = positive_responses.get(self.coaching_style, positive_responses['supportive'])

            # Add theme-specific additions
            if is_faith_related:
                faith_additions = [
                    " Your spiritual growth shines through.",
                    " That connection you're nurturing is powerful.",
                ]
                return random.choice(base_responses) + random.choice(faith_additions)
            elif is_journaling_related:
                journal_additions = [
                    " Journaling helps us see our own growth more clearly.",
                    " Writing it down makes the progress real.",
                ]
                return random.choice(base_responses) + random.choice(journal_additions)

            return random.choice(base_responses)

        elif is_challenging:
            challenging_responses = {
                'direct': [
                    "That's honest. What would help most right now?",
                    "Acknowledging it is the first step. What do you need?",
                    "Real talk. What's one small thing that could help today?",
                ],
                'gentle': [
                    "Thank you for sharing that with me. Those feelings are valid, and I'm here with you.",
                    "It takes courage to name what's hard. What would feel supportive right now?",
                    "I hear you. Sometimes just saying it out loud can help lighten the load.",
                ],
                'supportive': [
                    "I appreciate you sharing that. We all have those stretches. What feels manageable right now?",
                    "That kind of honesty takes strength. Is there something specific I can help with?",
                    "Thank you for trusting me with that. What would help you feel a bit better today?",
                ],
            }
            return random.choice(challenging_responses.get(self.coaching_style, challenging_responses['supportive']))

        else:
            # Neutral reflection - just acknowledge and engage
            neutral_responses = {
                'direct': [
                    "Thanks for sharing. What stands out most to you about that?",
                    "Good reflection. What does that mean for what's next?",
                ],
                'gentle': [
                    "Thank you for sharing that with me. It sounds like you've been doing some good reflecting.",
                    "I appreciate you opening up. What feels most important about what you shared?",
                ],
                'supportive': [
                    "Thanks for sharing that reflection. It's valuable to pause and notice where we are.",
                    "I appreciate you sharing. Moments of reflection like this matter. What feels most significant?",
                ],
            }
            return random.choice(neutral_responses.get(self.coaching_style, neutral_responses['supportive']))

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
                    greeting += ". The evening is here."
                else:  # supportive
                    greeting += ". Let's make the most of the evening."

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
