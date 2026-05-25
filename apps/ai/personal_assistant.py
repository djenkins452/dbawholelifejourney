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
from .state_assessment import StateAssessmentMixin
from .priority_generator import PriorityGeneratorMixin
from .greeting_service import GreetingMixin
from assistant.views import (
    process_assistant_message,
    DATA_TYPE_NAVIGATION,
    get_friendly_data_type_name,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CHECK-IN / STATUS QUERY PATTERNS
# =============================================================================
# Single source of truth for phrases that indicate the user is requesting
# a status check-in, day overview, or task briefing. Used in:
#   1. send_message() prefilter (non-streaming)
#   2. send_message_stream() prefilter (streaming)
#   3. _generate_response() internal check-in detection
# IMPORTANT: When adding patterns here, they apply to ALL paths automatically.
CHECKIN_PATTERNS = frozenset([
    # Explicit check-in
    'check in', 'checking in', 'check-in', 'checkin',
    # Status / refresh requests (force context rebuild)
    'status', 'refresh', 'update my status',
    'where do things stand', 'where are things',
    # Day overview
    "how's my day", 'how is my day', 'how does my day look',
    "how's my schedule", "what's my day look like",
    'give me a rundown', 'brief me', 'briefing', 'daily briefing',
    'what do i have today', "what's on my plate", 'whats on my plate',
    'status update', 'status report', 'give me my status',
    'what am i looking at today', 'run down my day',
    # Remaining / left
    "what's left", 'whats left', 'what is left',
    "what's remaining", 'whats remaining',
    'what do i have left', 'what do i still need',
    "what's left for me", 'whats left for me',
    'what still needs to be done', "what haven't i done",
    # Cross-domain check-in
    'meds and journal', 'journal and meds',
    'meds and reading', 'reading and meds',
    # Broad day-overview fragments
    'my day look', 'day look like', 'day ahead',
    'what does my day', 'what is my day',
    'plan for today', 'plan for the day',
    'today look like', 'today looking like',
    'what should i do today', 'what should i focus on',
    'what should i be doing', 'what should i do right now',
    'what should i do now', 'what should i be doing right now',
    'what do i need to do', 'walk me through my day',
    'my schedule today', 'my schedule look',
    'what am i doing today', 'what have i got today',
    'where do i stand', 'where am i at',
    'catch me up', 'fill me in',
    # Task-oriented queries
    'have to do today', 'to do today',
    "haven't completed", 'havent completed',
    "haven't done", 'havent done',
    "haven't finished", 'havent finished',
    'still need to do', 'need to finish',
    'left to do', 'left to finish',
    'still outstanding', 'still pending',
    'incomplete today', 'not done today',
    'remaining today', 'remaining for today',
    'tasks today', 'tasks for today',
    'things to do', 'to-do list',
    'anything left',
    # v7: Completed-task queries (temporal contamination fix)
    'completed today', 'i completed', 'have completed',
    'i finished today', 'did i complete', 'did i finish',
    'what did i complete', 'what have i completed',
    'what did i finish', 'which tasks did i finish',
    'tasks i completed', 'tasks i finished',
    'tasks i have completed', 'tasks i have done',
    'what got done', 'what have i done today',
    # Advisory / planning queries (Part 3 — v4 expansion)
    'structure my day', 'what matters most',
    'biggest improvement', 'biggest difference', 'biggest impact',
    'highest impact', 'what single habit',
    'what would you tell me', 'if you were my chief of staff',
    'if you were my cos', 'what should my priorities',
    'what would make the biggest', 'most important thing',
    'top priority', 'where should i start',
    'what would improve my life', 'what should i change',
])


# =============================================================================
# HEALTH-SENSITIVE CLAIM GROUNDING
# =============================================================================
# These data domains require strict factual grounding. The CoS must NOT state
# specific values for these unless the exact values appear in the structured
# CoS context or direct query results.
GROUNDED_HEALTH_DOMAINS = frozenset([
    'weight', 'body_fat', 'lean_mass', 'blood_pressure', 'heart_rate',
    'glucose', 'spo2', 'sleep', 'medication', 'calories', 'macros',
    'protein', 'body_composition', 'blood_oxygen',
])


def _build_missing_data_context(personal_data_result: dict) -> str:
    """Build a structured context block for personal data queries with no direct data.

    Instead of returning a hard-coded template string, this injects context into the
    system prompt so the CoS can generate an intelligent, contextual response that:
    - Acknowledges the data gap honestly
    - Uses secondary context (priorities, forecasts, intelligence summaries)
    - Provides relevant navigation links
    - Applies general reasoning where appropriate
    - Never fabricates specific health values
    """
    data_type = personal_data_result.get('awaiting_data_type', 'data')
    friendly_name = get_friendly_data_type_name(data_type)
    nav_info = DATA_TYPE_NAVIGATION.get(data_type)
    nav_link = f"[{nav_info[0]}]({nav_info[1]})" if nav_info else None

    context_lines = [
        "",
        "=== PERSONAL DATA QUERY — NO DIRECT DATA ===",
        f"The user is asking about: {friendly_name}",
        f"Data source searched: {data_type}",
        "Direct records found: NONE",
        "",
        "RESPONSE GUIDANCE:",
        f"- Acknowledge honestly that no {friendly_name} data has been logged yet",
    ]

    if nav_link:
        context_lines.append(
            f"- Direct the user to log data: {nav_link}"
        )

    context_lines.extend([
        "- Use your operational context above (priorities, forecasts, health intelligence,",
        "  watch areas) to still provide useful, personalized guidance",
        "- If the question allows general reasoning (e.g., 'why does sleep matter for fat loss'),",
        "  provide helpful general guidance alongside the data gap acknowledgment",
        "- Apply your coaching personality and executive tone",
        "",
        "STRICT GROUNDING RULE FOR THIS RESPONSE:",
        f"You have NO {friendly_name} records for this user. Do NOT state, imply, or invent",
        "specific values for: weight, body fat %, lean mass, blood pressure, heart rate,",
        "glucose, SpO2, sleep hours/quality, medication names/doses/schedules, calorie counts,",
        "or macro values. These may ONLY be stated when exact values appear in the CoS",
        "operational context above. Saying 'I don't have that data yet' is ALWAYS better",
        "than fabricating a number or schedule.",
        "=== END PERSONAL DATA QUERY ===",
    ])

    return "\n".join(context_lines)


# =============================================================================
# PERSONAL ASSISTANT SYSTEM PROMPTS
# =============================================================================
# Prompt constants and assembly logic are centralized in apps/core/cos/prompt_builder.py
# Import them here for backward compatibility.
from apps.core.cos.prompt_builder import (                  # noqa: E402
    PERSONAL_ASSISTANT_BASE_PROMPT,
    TIME_URGENCY_PROMPT,
    FAITH_INTEGRATION_PROMPT,
    STATE_ASSESSMENT_PROMPT,
    PRIORITY_GENERATION_PROMPT,
    build_personal_assistant_prompt,
    get_coaching_style_for_assistant,
)


# [EXTRACTED] Base system prompt moved to apps/core/cos/prompt_builder.py
# The following constant is kept as a reference comment for file navigation.
# PERSONAL_ASSISTANT_BASE_PROMPT is now imported from prompt_builder.
_PROMPT_BUILDER_MODULE = "apps.core.cos.prompt_builder"  # For IDE reference
# NOTE: The old inline prompt definitions (PERSONAL_ASSISTANT_BASE_PROMPT,
# TIME_URGENCY_PROMPT, FAITH_INTEGRATION_PROMPT, STATE_ASSESSMENT_PROMPT,
# PRIORITY_GENERATION_PROMPT, build_personal_assistant_prompt,
# get_coaching_style_for_assistant) have been extracted to prompt_builder.py
# and are imported above for backward compatibility.

# --- CUT START: Old inline definitions removed (see apps/core/cos/prompt_builder.py) ---
# [Approximately 550 lines of prompt constants and builder functions were here]
# --- CUT END ---

# This marker helps grep find where COS_PROACTIVE_INTELLIGENCE_PROMPT starts:
# KEEP: COS_PROACTIVE_INTELLIGENCE_PROMPT remains here (complex, deeply integrated)

COS_PROACTIVE_INTELLIGENCE_PROMPT = """

## DETERMINISTIC CoS OPERATING MODEL

This section defines mandatory, deterministic behavior. All language is enforcement,
not advisory. Compliance is not optional.

### SECTION 1 — CONTEXT SCAN (EVERY INTERACTION)

Before responding to ANY user message, scan the DAILY SCAN BRIEF and operational data.
How you USE the scan depends on the SESSION MODE directive:

DAILY ORIENTATION mode: Deliver the full daily brief with all five mandatory elements
(see DAILY ORIENTATION section above). Write naturally — no headers, no templates.

LIGHT mode: Full awareness persists. Weave data into responses when relevant. Answer
questions directly. Do NOT repeat the orientation unless drift override fires.

GREETING / SHORT MESSAGE: Check SESSION MODE. DAILY ORIENTATION → full brief.
LIGHT → respond naturally with data awareness, no re-briefing.

### SECTION 2 — NON-NEGOTIABLE + FOUNDATIONAL DETECTION & PRIORITY HIERARCHY

Non-negotiables are automatically determined by the operational data:
- Medication timing (scheduled doses)
- Workout consistency risk (2+ consecutive missed days in the data)
- Hard deadlines within 48 hours
- Identity anchors (prayer, Scripture, core health routines the user has committed to)

FOUNDATIONAL items are marked explicitly in the data (is_foundational=True on goals,
habits, or tasks). Foundational means identity-level priority — these define who the
user is building themselves to be. When a foundational item is incomplete or at risk,
name it as foundational: "This is foundational." Do not over-explain — one sentence.

If a task's non-negotiable status is ambiguous, ask ONCE: "Is [task] non-negotiable
for you, or flexible?" Persist the classification and do not ask again.

Priority ordering (strict hierarchy — never violate):
1. Foundational + at risk (identity-level items under threat)
2. Foundational + incomplete today
3. Important + at risk (medication, identity anchor, consistency threat)
4. Important + incomplete today or deadline within 48 hours
5. Flexible (only if no urgency exists above)

The THREE priority tiers in WLJ are: FOUNDATIONAL > IMPORTANT > FLEXIBLE.
Routine items, tasks, and all execution layers use this model.

TIME PROXIMITY TIEBREAKER (applies within EVERY tier above):
When multiple items qualify for the same tier, the one with the nearest
scheduled_time ALWAYS wins. Tier always outranks time — but within a tier:
DUE NOW > DUE SOON > LATER TODAY > UNSCHEDULED.
Example: A foundational task due at 5:30 AM beats a foundational task at 8:30 PM.
A tier-2 LATER TODAY item still beats a tier-5 DUE NOW item (tier wins).

Foundational ALWAYS outranks important and flexible at the same urgency level.
Important ALWAYS outranks flexible. Never recommend a flexible item over
an at-risk foundational or important item.

### SECTION 3 — ACTION-FIRST PRESENTATION FORMAT

When recommending a next action (in daily orientation OR mid-conversation):
1. Direct instruction first: "Start with [action]." or "[Action] first."
2. One sentence of reasoning — why this, why now.
3. If foundational: "This is foundational."
4. Momentum chain: suggest ONE follow-up — "Then move into [next action]."
5. Present execution options:
   A) Do it now  B) Move to a specific time  C) Defer for today

NEVER lead with explanation. NEVER hedge. The user needs direction, not analysis.

Example (foundational + overdue):
"Journal first. It's overdue and foundational — this anchors your day.
Then move into your workout.
A) Start now  B) Schedule for after lunch  C) Defer today"

Example (completion + chain):
"Morning meds are done. Good.
Start your Bible reading — it's next and foundational.
A) Start now  B) Move to later  C) Defer today"

Example (time-proximity — DUE NOW beats same-tier LATER TODAY):
"Prayer first — it's at 5:30 and foundational. Bible reading right after at 5:45.
Journal is tonight at 8:30, so no rush there.
A) Start prayer now  B) Push to later  C) Defer today"

No additional commentary before user selection. Wait for their choice.

### SECTION 4 — OVERRIDE LEARNING LOOP

When the user rejects a recommendation or chooses a different task:
1. Accept immediately. No debate. No defense. No lecture.
2. Ask: "What's driving that choice? A) Energy level  B) Timing conflict  C) Strategic shift"
3. Note the response.
4. Adjust future prioritization weighting based on accumulated override patterns.

If the user consistently overrides a category (e.g., always defers workouts to evening),
adapt recommendations to match their pattern — don't fight it.

### SECTION 5 — EXECUTIVE BRIEF + DEEP DIVE (DATA DISCUSSIONS)

When the user's message involves measurable data (health, finances, performance, habits):

DEFAULT — Executive Brief (concise analytical snapshot, natural tone):
- Trend direction with specific numbers
- Strongest positive signal in the data
- Primary risk or concern
- One concrete immediate focus
- One strategic question
- End with: "Type 'Deep Dive' for full strategic breakdown."

Keep it to 6-8 lines. Every line must contain INSIGHT, not just data.
No generic encouragement. No simple number recaps.

ON REQUEST — Deep Dive (only when user says "deep dive", "go deeper", "full breakdown"):
1. Trend Analysis — direction, velocity, comparison to prior periods
2. Signal vs Noise — real pattern or normal fluctuation?
3. Root Cause Drivers — behaviors driving the trend
4. Risk Assessment — trajectory consequence
5. Forward Projection — 2-4 weeks out (quantifiable domains only)
6. Action Plan — 3-5 MEASURABLE steps (not vague advice)
7. Strategic Question

Never default to Deep Dive. Never skip the "Type Deep Dive" prompt.

### SECTION 6 — DRIFT OVERRIDE (SUSPENDS LIGHT MODE)

If consistency violation is detected in the operational data:
- Workout gaps (2+ consecutive missed days)
- Medication inconsistency (missed doses)
- Repeated deferment of the same task (3+ times)
- Declining sentiment streak (3+ negative days)
- Growing activity gaps

Light mode is SUSPENDED. Response must:
1. Name the pattern explicitly. No hedging.
2. State consequence risk in one sentence.
3. Offer immediate reset using A/B/C format:
   A) Do it now  B) Schedule for later today  C) Convert to shorter version

No soft language. No shame. No passivity. No waiting for user to ask.

Example (correct form):
"You've missed two planned workouts this week. That's the beginning of a pattern, not
a one-off. Let's reset today. A) Train now, B) schedule it for later today, or
C) convert to a shorter session?"

### SECTION 7 — POST-EVENT FOLLOW-UP

Calendar events involving social gatherings, travel, dining out, or disrupted routine:
- Pre-event: Flag it, note trigger patterns, offer 2-3 strategies.
- Post-event: Ask how it went:
  A) Stayed disciplined  B) Partial win  C) Slipped

A → Reinforce identity alignment. B → Acknowledge, suggest one micro-adjustment.
C → Normalize, identify lesson, offer immediate reset. Prevent spiral.

### SECTION 8 — PROHIBITED BEHAVIOR (ABSOLUTE)

The following are forbidden in ALL responses:
- "You're making good progress" or any generic praise not tied to specific data
- "How can I help you today?" / "What can I assist you with?"
- "I'm here to assist you" / "I'd be happy to help with that"
- "That's a great question!" / "Great question!"
- "As an AI assistant..." / "As your assistant..."
- "Let me help you with that"
- "You might consider..." / "You could think about..."
- "I'm unable to access your personal data" / "I can't access your records"
- Repeating full daily orientation more than once per session
- Multiple competing recommendations (ONE recommendation, always)
- Excessive explanation before presenting options
- Markdown headers in responses (##, ###)
- Dashboard or report-style formatting
- Motivational filler or cheerleading
- Vague prioritization without naming specific tasks
- Generic productivity templates ("prioritize your tasks", "create a morning routine", "time block your day", "start with the most important task", "Eisenhower Matrix", "Pomodoro Technique", "review your priorities", "set daily objectives") when user context is available
- Generic disclaimers ("consult your healthcare provider", "talk to your doctor", "seek professional advice") UNLESS the user explicitly asks for medical/professional advice or the situation involves genuine safety risk
- Injecting schedule, task, or medication information when the user did not ask about it and it does not directly answer their question
- Context dumping — attaching operational data (schedule blocks, medication status, task counts) to a response where it adds no value to the answer
- Falling back to generic LLM knowledge when you have the user's actual data to reason from
- Mirroring decision questions back without a recommendation ("What do you think?" / "How does that sound?" WITHOUT first stating your recommendation)
- Responding to strategic/advisory questions with empathy templates instead of operational analysis

### SECTION 9 — HEALTH INTELLIGENCE ENFORCEMENT (ABSOLUTE)

When the user asks about ANY health metric — protein target, calorie goal, weight trend,
sleep average, recovery score, health score, or any other metric — you MUST follow
these rules without exception:

RULE 1: USE SYSTEM VALUES ONLY.
The HEALTH INTELLIGENCE section in your operational data contains values calculated
by the WLJ Health Intelligence Engine from the user's ACTUAL biometric data, logged
meals, workouts, and body composition. These are the ONLY correct values.

RULE 2: NEVER GENERATE GENERIC RANGES.
You are FORBIDDEN from producing ranges like "0.7-1.0g per pound" or "110-138g protein"
or "7-9 hours of sleep" or similar textbook-style ranges. The system has already
computed the EXACT target for THIS user. Quote the system value.

RULE 3: CITE THE SOURCE.
When sharing a health metric, indicate it comes from the system:
  CORRECT: "Your protein target is 193g today (based on your lean body mass)."
  WRONG: "A good protein target for someone your size would be 110-138g."

RULE 4: CORRECT FRAMING WHEN DATA IS MISSING.
If a health metric is NOT in your operational data, say:
"I don't see any [metric] logged yet. You can start tracking at [relevant page link]."
Do NOT say "I'm unable to access" or "I don't have that information."
Do NOT guess, estimate, or substitute generic medical advice.

RULE 5: NEVER CONTRADICT SYSTEM VALUES.
If the user quotes a number that conflicts with system data, gently correct them
using the system value: "Actually, your system-calculated target is [X]."

RULE 6: NEVER COMPUTE YOUR OWN HEALTH MATH.
Do NOT multiply, divide, add, or subtract health numbers yourself. The system has
already done the math. Use ONLY the pre-calculated values. In particular:
- NEVER multiply a daily average by 7 to get a "weekly total"
- NEVER divide a number you see by days to get an average
- NEVER say "X this week" about a daily number — always say "X per day"
- NEVER combine individual day values to derive a total

RULE 7: WEEKLY PROTEIN QUESTIONS — ALWAYS USE 7-DAY AVERAGE.
When the user asks "how's my protein this week?", "protein update", or any
weekly protein question, your answer MUST use the PROTEIN WEEKLY EVALUATION
fields from your operational data. Format your response like this:

  "Your protein target is [target]g per day. Over the last 7 days you've
   averaged [avg_7d]g per day, hitting about [consistency_pct]% of your target."

If the average is below target, add the gap:
  "You're about [gap]g per day below target."

NEVER say "You logged Xg this week" — that uses a total. ALWAYS say
"You averaged Xg per day" — that uses the system-calculated average.

RULE 8: BODY COMPOSITION — USE LOCKED SYSTEM VALUES.
The BODY COMPOSITION block contains pre-computed intelligence:
fat_loss_quality_label, fat_loss_ratio, recomposition flag, plateau_status,
fat_loss_speed, muscle_loss_risk_level, plateau_risk, fat_loss_phase,
muscle_preservation_status.

When the user asks "Am I losing weight the right way?" or similar:
  "Over the last 14 days your weight is down [delta] lbs. About [fat_delta]
   came from fat mass and lean mass is [stable/up/down]. Fat loss quality:
   [label] (ratio [ratio]). Muscle preservation: [status]."

When the user asks "Am I plateauing?" or "Will I plateau?":
  Use plateau_status for current state. Use plateau_risk_label +
  plateau_prediction_window_days for predictive warning.
  If RECOMP, explain weight is stable but composition is improving.

When the user asks "What phase am I in?":
  Use fat_loss_phase + phase_confidence. Explain what the phase means
  and what to expect next.

Rules:
- NEVER compute fat mass, lean mass, or fat loss ratios yourself.
- NEVER cite generic body fat ranges like "15-20% is ideal for men."
- NEVER cite generic fat loss advice like "1-2 lbs per week is recommended."
- NEVER say "your fat mass is approximately" — use the system value exactly.
- NEVER predict plateau timing yourself — use plateau_prediction_window_days.
- NEVER classify metabolic phase yourself — use fat_loss_phase.
- For muscle preservation → use muscle_preservation_status.
- All body composition responses must reference locked system values.

### SECTION 10 — RHYTHM AWARENESS (ABSOLUTE)

The CoS Situation State may set situation_mode to `off_rhythm` or `returning`.
When it does, an OPENING FRAME has been pre-computed deterministically from
the user's own personal-baseline signals (engagement, foundational adherence,
workout consistency, days-since-last-interaction). It is grounded truth, not
inference.

Rules — non-negotiable:
1. When OPENING FRAME is provided, use it VERBATIM as the first sentence of
   your response. Do not paraphrase, soften, or rephrase.
2. After the opening frame, respond to the user's actual message normally.
3. Do NOT extend the rhythm observation with inferred causes, emotional
   claims, motivational interpretations, or hypothetical reasons.
4. Do NOT repeat the rhythm observation later in the same response.
5. Do NOT mention rhythm at all when situation_mode is not `off_rhythm` or
   `returning`.
6. Do NOT claim first-person feelings about the user's rhythm. No "I worry",
   "I'm glad", "I'm concerned", "I noticed and care", "it makes me happy".
   Beth observes; Beth does not feel.
7. Do NOT ask "how are you feeling?", "are you okay?", "is everything alright?"
   These are therapist-register questions. The opening frame already invites
   the user to respond on their terms.
8. Do NOT add chatbot disclaimers like "as your assistant" or "I'm here for you".
9. The contributor values in the OPENING FRAME (percentages, counts, day
   windows) are authoritative. Do not invent additional numbers in the same
   response. If the user asks for detail, cite the same numbers — never make
   up a contributing reason that was not in the frame.

### SUCCESS CONTRACT

Every CoS response must be: decisive, specific, frictionless, and natural.
CoS learns from overrides, protects identity anchors, and never sounds robotic
or like a generic assistant. This contract replaces all prior advisory instructions.
"""

# STATE_ASSESSMENT_PROMPT — imported from apps.core.cos.prompt_builder
# PRIORITY_GENERATION_PROMPT — imported from apps.core.cos.prompt_builder


class PersonalAssistant(StateAssessmentMixin, PriorityGeneratorMixin, GreetingMixin):
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
        # Structured personal life facts (permanent biographical memory)
        self._personal_facts_prompt = ''
        try:
            from apps.core.ai_memory.life_fact_extractor import build_personal_facts_prompt
            self._personal_facts_prompt = build_personal_facts_prompt(user)
        except Exception:
            pass
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

    def _build_system_prompt(self, include_time_context: bool = True,
                             include_proactive_prompt: bool = True) -> str:
        """
        Build the complete system prompt with coaching style and time context.

        Args:
            include_time_context: Include current time/urgency context.
            include_proactive_prompt: Include COS_PROACTIVE_INTELLIGENCE_PROMPT
                (~2,900 tokens). Set False for simple data queries when
                WLJ_CONDITIONAL_FRAMEWORKS_ENABLED is on.
        """
        time_context = self._get_time_context() if include_time_context else None
        _proactive = COS_PROACTIVE_INTELLIGENCE_PROMPT if include_proactive_prompt else None
        return build_personal_assistant_prompt(
            coaching_style=self.coaching_style,
            faith_enabled=self.faith_enabled,
            user_profile=self.user_profile,
            time_context=time_context,
            personal_context=self.personal_context,
            personal_facts_prompt=self._personal_facts_prompt,
            cos_proactive_prompt=_proactive,
        )

    # =========================================================================
    # STATE ASSESSMENT — see apps/ai/state_assessment.py (StateAssessmentMixin)
    # DAILY PRIORITIES — see apps/ai/priority_generator.py (PriorityGeneratorMixin)
    # OPENING/GREETING — see apps/ai/greeting_service.py (GreetingMixin)
    # =========================================================================

    # [EXTRACTED] assess_current_state → StateAssessmentMixin
    # [EXTRACTED] _build_state_from_sae → StateAssessmentMixin
    # [EXTRACTED] _gather_comprehensive_state → StateAssessmentMixin
    # [EXTRACTED] _get_journal_state, _get_task_state, _get_purpose_state → StateAssessmentMixin
    # [EXTRACTED] _get_faith_state, _get_health_state → StateAssessmentMixin
    # [EXTRACTED] _get_habit_goals_data, _calculate_recovery_pattern → StateAssessmentMixin
    # [EXTRACTED] _calculate_journal_streak, _calculate_workout_streak → StateAssessmentMixin
    # [EXTRACTED] _generate_ai_assessment, _snapshot_to_dict → StateAssessmentMixin
    # [EXTRACTED] _get_fresh_today_faith, _get_workout_today → StateAssessmentMixin
    # [EXTRACTED] generate_daily_priorities → PriorityGeneratorMixin
    # [EXTRACTED] _build_priority_context, _generate_faith_priority → PriorityGeneratorMixin
    # [EXTRACTED] _generate_purpose_priorities, _generate_commitment_priorities → PriorityGeneratorMixin
    # [EXTRACTED] generate_reflection_prompt → PriorityGeneratorMixin
    # [EXTRACTED] _generate_prompt_for_context, _*_prompts → PriorityGeneratorMixin
    # [EXTRACTED] get_opening_message → GreetingMixin
    # [EXTRACTED] _get_greeting, _should_offer_reflection, _build_nudges → GreetingMixin

    # NOTE: The methods above are now inherited via mixins. They are NOT
    # duplicated — Python MRO resolves them from the mixin classes.
    # This comment block serves as a navigational aid for developers.

    # =========================================================================
    # CONVERSATION / CHAT
    # =========================================================================

    def get_or_create_conversation(self) -> AssistantConversation:
        """Get or create today's conversation."""
        return AssistantConversation.get_or_create_active(self.user)

    def _cos_mode_shortcut(self, message, conversation):
        """
        Deterministic CoS decision-mode shortcut.

        If the user message matches a CoS decision-mode keyword
        (execution / risk / fix), build the deterministic answer from
        the shared execution_state and selectors, log both the user
        message and the deterministic assistant message to the
        conversation, and return the chat payload.

        Returns:
            dict — chat response payload — when a mode matched.
            None — when the message did not match; caller falls through
                   to the normal LLM pipeline.

        The LLM is NEVER called in this path.
        """
        try:
            from apps.ai.cos_mode_router import resolve_cos_mode
            from apps.core.execution.execution_state import (
                build_execution_state,
            )
            from apps.core.execution.selectors import select as run_selector

            mode = resolve_cos_mode(message)
            if mode is None:
                return None

            state = build_execution_state(self.user)
            decision = run_selector(mode, state)

            response_text = decision.get('message') or (
                "Unable to determine a deterministic answer right now."
            )

            # Log both messages to conversation history so the chat UI
            # shows the exchange like any other.
            try:
                AssistantMessage.objects.create(
                    conversation=conversation,
                    role='user',
                    content=message,
                    message_type='text',
                )
                AssistantMessage.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=response_text,
                    message_type='text',
                )
            except Exception:
                logger.warning(
                    "[COS MODE SHORTCUT] history log failed user=%s mode=%s",
                    self.user.id, mode, exc_info=True,
                )

            primary = decision.get('primary_action') or {}
            logger.info(
                "[COS MODE SHORTCUT] user=%s mode=%s primary=%s",
                self.user.id, mode,
                primary.get('title') or '<none>',
            )

            return {
                'response': response_text,
                'cos_decision': {
                    'mode': decision.get('mode'),
                    'primary_action': decision.get('primary_action'),
                    'reason': decision.get('reason'),
                    'follow_on': decision.get('follow_on'),
                },
                'deterministic': True,
            }
        except Exception:
            logger.warning(
                "[COS MODE SHORTCUT] failed user=%s — falling through to LLM",
                self.user.id, exc_info=True,
            )
            return None

    def generate_proactive_briefing(self) -> Optional[dict]:
        """
        Generate a proactive daily executive briefing (v7).

        Goes through the FULL _generate_response() pipeline with a synthetic
        check-in message. Saves ONLY the assistant response (no fake user
        message). Uses timestamp-based cooldown (v7.1) for precise gap control.

        Returns:
            dict with 'response' (str) and 'message_id' (int),
            or None if briefing is not needed or LLM is unavailable.
        """
        try:
            from apps.core.utils import get_user_now, get_user_today
            from apps.ai.executive_briefing import _compute_session_gap

            conversation = self.get_or_create_conversation()
            user_now = get_user_now(self.user)
            today = get_user_today(self.user)
            metadata = conversation.metadata or {}

            # ── v7.1 Part 1: Timestamp-based cooldown ──────────────────
            last_briefing_date = metadata.get('last_briefing_date')
            last_briefing_at = metadata.get('last_briefing_at')
            is_first_of_day = last_briefing_date != str(today)

            if not is_first_of_day:
                # Same day — check if 4+ hours since last briefing
                if last_briefing_at:
                    from django.utils.dateparse import parse_datetime
                    last_ts = parse_datetime(last_briefing_at)
                    if last_ts and (timezone.now() - last_ts).total_seconds() < 4 * 3600:
                        logger.info(
                            "v7_BRIEFING_COOLDOWN user=%s reason=timestamp "
                            "last_at=%s",
                            self.user.id, last_briefing_at,
                        )
                        return None
                else:
                    # No timestamp but same date — check session gap
                    gap_hours = _compute_session_gap(conversation)
                    if gap_hours is None or gap_hours < 4:
                        logger.info(
                            "v7_BRIEFING_COOLDOWN user=%s reason=date+gap "
                            "gap_hours=%s",
                            self.user.id, gap_hours,
                        )
                        return None

            # ── v7.1 Part 2: Server-side idempotency ──────────────────
            # Prevent duplicate briefings from concurrent requests
            recent_briefing = conversation.messages.filter(
                role='assistant',
                is_proactive=True,
                message_type='state_assessment',
                created_at__gte=timezone.now() - timedelta(minutes=2),
            ).first()
            if recent_briefing:
                logger.info(
                    "v7_BRIEFING_IDEMPOTENT user=%s existing_msg=%s",
                    self.user.id, recent_briefing.id,
                )
                return {
                    'response': recent_briefing.content,
                    'message_id': recent_briefing.id,
                }

            # ── v7.1 Part 5: Determine delivery reason ────────────────
            delivery_reason = 'first_open' if is_first_of_day else 'return_after_gap'

            # ── v8: Interaction awareness — lightweight alignment ───
            # If a deep interaction occurred within 90 minutes, deliver
            # a compressed alignment instead of a full briefing.
            # This prevents CoS from repeating herself.
            deep_at = metadata.get('last_deep_interaction_at')
            if deep_at:
                from django.utils.dateparse import parse_datetime as _parse_dt
                deep_ts = _parse_dt(deep_at)
                if deep_ts and (timezone.now() - deep_ts).total_seconds() < 90 * 60:
                    try:
                        from apps.ai.executive_briefing import (
                            build_lightweight_alignment,
                        )
                        lightweight = build_lightweight_alignment(
                            self.user, conversation,
                        )
                        if lightweight:
                            logger.info(
                                "v8_BRIEFING_LIGHTWEIGHT user=%s "
                                "deep_at=%s",
                                self.user.id, deep_at,
                            )
                            delivery_reason = 'lightweight_alignment'
                            # Use the lightweight alignment as the
                            # briefing text — skip full render below.
                            # Save + mark as delivered to prevent retry.
                            assistant_msg = AssistantMessage.objects.create(
                                conversation=conversation,
                                role='assistant',
                                content=lightweight,
                                message_type='state_assessment',
                                is_proactive=True,
                                metadata={
                                    'check_in_type': 'lightweight_alignment',
                                    'delivery_reason': delivery_reason,
                                    'generated_at': timezone.now().isoformat(),
                                },
                            )
                            from apps.ai.executive_briefing import (
                                mark_briefing_delivered,
                            )
                            mark_briefing_delivered(conversation)
                            metadata = conversation.metadata or {}
                            metadata['last_briefing_at'] = (
                                timezone.now().isoformat()
                            )
                            conversation.metadata = metadata
                            conversation.updated_at = timezone.now()
                            conversation.save(
                                update_fields=['metadata', 'updated_at']
                            )
                            return {
                                'response': lightweight,
                                'message_id': assistant_msg.id,
                            }
                    except Exception as _lw_err:
                        logger.debug(
                            "Lightweight alignment failed, using full: %s",
                            _lw_err,
                        )

            # ── Generate deterministic briefing (no LLM) ───────────────
            # Phase 5.2+: Daily briefings are now rendered deterministically
            # from execution truth data. The LLM is NOT involved in
            # generating state descriptions — it fabricates completions.
            logger.info(
                "v7_BRIEFING_GENERATE user=%s reason=%s method=deterministic",
                self.user.id, delivery_reason,
            )
            try:
                from apps.ai.beth_checkin_renderer import render_checkin_for_time
                response_text = render_checkin_for_time(self.user)
            except Exception:
                logger.error(
                    "v7_BRIEFING_RENDERER_FAIL user=%s — deterministic "
                    "renderer failed, using safe fallback",
                    self.user.id, exc_info=True,
                )
                from apps.ai.beth_checkin_renderer import _SAFE_FALLBACK
                response_text = _SAFE_FALLBACK

            if not response_text or len(response_text) < 20:
                logger.warning(
                    "v7_BRIEFING_FALLBACK user=%s len=%s — renderer returned "
                    "short/empty response. Will retry on next interaction.",
                    self.user.id, len(response_text) if response_text else 0,
                )
                return None

            logger.info(
                "v7_BRIEFING_ACCEPTED user=%s len=%s method=deterministic",
                self.user.id, len(response_text),
            )

            # Save ONLY the assistant response (no fake user message)
            assistant_msg = AssistantMessage.objects.create(
                conversation=conversation,
                role='assistant',
                content=response_text,
                message_type='state_assessment',
                is_proactive=True,
                metadata={
                    'check_in_type': 'daily_executive_briefing',
                    'delivery_reason': delivery_reason,
                    'generated_at': timezone.now().isoformat(),
                },
            )

            # ── v7.1 Part 1: Store ISO timestamp for precise cooldown ──
            # Also mark briefing as delivered via canonical helper
            from apps.ai.executive_briefing import mark_briefing_delivered
            mark_briefing_delivered(conversation)
            metadata = conversation.metadata or {}  # Re-read after mark
            metadata['last_briefing_at'] = timezone.now().isoformat()
            conversation.metadata = metadata
            conversation.updated_at = timezone.now()
            conversation.save(update_fields=['metadata', 'updated_at'])

            logger.info(
                "v7_BRIEFING_DELIVERED user=%s msg_id=%s reason=%s len=%s",
                self.user.id, assistant_msg.id, delivery_reason,
                len(response_text),
            )

            return {
                'response': response_text,
                'message_id': assistant_msg.id,
            }

        except Exception as e:
            logger.error(
                "v7_BRIEFING_ERROR user=%s error=%s",
                self.user.id, e, exc_info=True,
            )
            return None

    def send_message(
        self,
        message: str,
        conversation: AssistantConversation = None,
        page_context: dict = None,
        image_data: str = None,
        image_mime_type: str = None,
        images_list: list = None,
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
        import time as _t
        _t_total_start = _t.monotonic()

        # ── Latency tracer (diagnostic instrumentation) ──
        try:
            from apps.core.ai_observability.latency_trace import LatencyTrace
            _ltrace = LatencyTrace(user_id=self.user.id, path='non_stream')
        except Exception:
            _ltrace = None

        from .intent_service import intent_service
        from .feature_request_service import feature_request_service
        from .bug_report_service import bug_report_service
        from .confirmation_detector import handle_proactive_confirmation

        # Idempotency guard — prevent duplicate actions from retries/double-clicks
        from .idempotency import check_duplicate, store_result
        cached = check_duplicate(self.user.id, message)
        if cached is not None:
            logger.info("Idempotency hit for user %s — returning cached response", self.user.id)
            return cached

        if not conversation:
            conversation = self.get_or_create_conversation()

        # ── Deterministic CoS decision-mode shortcut ──
        # Three keyword-routed queries ("what should I do" / "biggest risk"
        # / "what should I fix") bypass the LLM and intent pipeline entirely.
        # The state, selectors, and message text are 100% deterministic and
        # share the same execution_state contract used by Action Center.
        # See apps/ai/cos_mode_router.py + apps/core/execution/selectors.py.
        if not (image_data or images_list):
            shortcut = self._cos_mode_shortcut(message, conversation)
            if shortcut is not None:
                return shortcut

        # Calculate image expiration (72 hours from now)
        image_expires_at = None
        has_any_images = bool(image_data and image_mime_type) or bool(images_list)
        if has_any_images:
            image_expires_at = timezone.now() + timedelta(hours=72)

        # Save user message (first image in legacy fields for backward compat)
        user_msg = AssistantMessage.objects.create(
            conversation=conversation,
            role='user',
            content=message,
            message_type='text',
            image_data=image_data or '',
            image_mime_type=image_mime_type or '',
            image_expires_at=image_expires_at
        )

        # Increment event context turn counter (for follow-up expiration)
        try:
            from apps.core.ai_events.followup import increment_turn_count
            increment_turn_count(conversation)
        except Exception:
            pass  # Non-critical — don't block message flow

        # Save additional images (2nd+) to MessageImage table
        if images_list:
            from .models import MessageImage
            for idx, (img_data, img_mime) in enumerate(images_list):
                MessageImage.objects.create(
                    message=user_msg,
                    image_data=img_data,
                    image_mime_type=img_mime,
                    image_expires_at=image_expires_at,
                    order=idx,
                )

        # Build consolidated list of all images for API calls
        # This combines legacy single image + multi-image records
        all_images = user_msg.all_images  # List of (base64, mime_type) tuples

        # Comprehensive vision analysis — persist structured analysis for CoS
        if all_images:
            try:
                from apps.scan.services.comprehensive_vision import comprehensive_vision_service
                from apps.scan.services.image_utils import clean_base64
                for img_b64, img_mime in all_images:
                    clean_img, _ = clean_base64(img_b64)
                    comprehensive_vision_service.analyze(
                        image_base64=clean_img,
                        mime_type=img_mime,
                        user=self.user,
                        source_type='chat',
                        source_object=user_msg,
                    )
            except Exception as e:
                logger.warning("Comprehensive vision analysis failed: %s", e)

        response = ""
        actions_taken = []
        # Phase 6.6: Quick reply pills for CRUD confirmations. Populated from
        # action_result.confirmation_detail when the CRUD gate is tripped.
        # Saved onto the AssistantMessage so the chat widget can render
        # pill-primary/secondary/danger buttons.
        _pending_quick_replies = []

        # Conversation mode persistence — detect and lock mode from message
        try:
            from apps.core.blueprint.conversation_mode import update_mode_from_message
            update_mode_from_message(self.user, message)
        except Exception:
            pass  # Mode tracking must never break chat

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
            _cos_context_cache = None  # Cache cos_context from ECC to avoid recomputing
            _route_result = None  # Shared router result for domain scoping / memory gating
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

                # Compute real tier — same logic as _generate_response().
                # Cache result to avoid rebuilding in _generate_response.
                # Try readiness cache first (pre-warmed by wake endpoint).
                _t_cache_start = _t.monotonic()
                try:
                    from apps.ai.readiness_cache import (
                        get_cached_cos_context as _rc_get,
                        get_layered_cos_context as _rc_get_layered,
                        set_readiness_state as _rc_set_state,
                        track_active_user as _rc_track,
                    )
                    _rc_set_state(self.user, 'active')
                    _rc_track(self.user)
                    # Try layered cache first (stable layer survives dynamic expiry),
                    # then flat cache, then full rebuild
                    _rc_cached = (
                        _rc_get_layered(self.user)
                        or _rc_get(self.user)
                    )
                except Exception as _ecc_cache_err:
                    logger.warning(
                        "ECC_CACHE_LOOKUP user=%s — readiness cache failed: %s",
                        self.user.id, _ecc_cache_err, exc_info=True,
                    )
                    _rc_cached = None
                logger.warning("COS CACHE lookup took %.1f ms", (_t.monotonic() - _t_cache_start) * 1000)
                _t_ctx_start = _t.monotonic()
                _ecc_cos = _rc_cached if _rc_cached else _ecc_build_cos(self.user)
                _cos_context_cache = _ecc_cos
                logger.warning("COS CONTEXT build took %.1f ms", (_t.monotonic() - _t_ctx_start) * 1000)
                # Write-back on cache miss so the main response path gets a hit
                if not _rc_cached:
                    try:
                        from apps.ai.readiness_cache import (
                            set_cached_cos_context as _rc_set_ctx,
                            set_layered_cos_context as _rc_set_layered,
                        )
                        _rc_set_ctx(self.user, _ecc_cos)
                        _rc_set_layered(self.user, _ecc_cos)
                    except Exception:
                        pass  # Cache write-back — non-critical
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
                logger.warning("ECC pre-check failed: %s", ecc_err, exc_info=True)

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

            # ── Capture pre-generation state snapshot for revalidation ──
            # Used later to detect if execution truth changed during response
            # generation. Lightweight: only the raw completion booleans.
            try:
                from apps.ai.cos_state_revalidator import capture_state_snapshot
                _pre_gen_snapshot = capture_state_snapshot(self.user)
            except Exception:
                _pre_gen_snapshot = None

            # User-affirmed completion check ("I already did it") — must run
            # BEFORE proactive confirmation to avoid CRUD execution when user
            # only wants to suppress reminders. See affirmation_detector.py.
            try:
                from .affirmation_detector import handle_affirmed_completion
                _affirm_result = handle_affirmed_completion(
                    self.user, message, conversation,
                )
                if _affirm_result and _affirm_result.get('handled'):
                    response = _affirm_result['response']
            except Exception:
                logger.warning("Affirmation detection failed", exc_info=True)

            # First, check for proactive check-in responses (e.g., "yes" to "Did you take your medicine?")
            # Also captures entity context (task_id, etc.) from PendingAction
            # when the response isn't a simple yes/no so intent recognition
            # can skip fragile title text-matching.
            _proactive_entity_context = None
            if not response:
                proactive_result = handle_proactive_confirmation(self.user, message)
            else:
                proactive_result = None
            if proactive_result and proactive_result.get('handled'):
                response = proactive_result['response']
                if proactive_result.get('action_result', {}).get('success'):
                    action_result = proactive_result.get('action_result', {})
                    actions_taken.append({
                        'type': 'proactive_response',
                        'success': True,
                        'created': action_result.get('data'),
                    })
            elif proactive_result and not proactive_result.get('handled'):
                # Not a simple yes/no, but entity context is available from
                # PendingAction. Store it so intent recognition can use it.
                _proactive_entity_context = proactive_result.get('pending_context')
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
                        image_mime_type=image_mime_type,
                        cos_context_cache=_cos_context_cache,
                        all_images=all_images,
                        route_result=_route_result,
                        _ltrace=_ltrace,
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
            # Then check for pending CRUD action confirmation
            elif (pending_crud := intent_service.get_pending_crud_action(self.user)):
                try:
                    crud_result = intent_service.handle_crud_confirmation(
                        self.user, message,
                    )
                    if crud_result:
                        if crud_result.action_type == 'confirmation_escaped':
                            # User said something other than CONFIRM/CANCEL/EDIT.
                            # Pending action already cancelled — fall through to
                            # normal AI processing with the user's message.
                            pass  # response stays None → handled by normal pipeline below
                        elif crud_result.action_type in (
                            'cancelled', 'expired', 'idempotent_skip',
                        ):
                            response = crud_result.message
                        else:
                            response = (
                                crud_result.message
                                + self._format_confirmation_detail(crud_result)
                            )
                            actions_taken.append(
                                self._build_action_taken(crud_result)
                            )
                    else:
                        # Unrecognized response — re-show confirmation with
                        # the same A/B/C pills via quick_replies (no plain-text
                        # fallback instructions per Phase 6.6).
                        _crud_options = pending_crud.get('options', [])
                        response = pending_crud['confirmation_message']
                        if _crud_options:
                            _pending_quick_replies = list(_crud_options)
                except Exception as crud_err:
                    logger.error(
                        "[CRUD_GATE] Confirmation handling failed: %s",
                        crud_err, exc_info=True,
                    )
                    intent_service.clear_pending_crud_action(self.user)
                    response = (
                        "Something went wrong processing that action. "
                        "I've reset it so we can try again."
                    )
            # Then check for pending activity disambiguation (multi-candidate)
            elif (pending_disambig := intent_service.get_pending_disambiguation(self.user)):
                disambig_result = intent_service.handle_disambiguation_response(
                    self.user, message,
                )
                if disambig_result:
                    if disambig_result.action_type in (
                        'cancelled', 'expired',
                    ):
                        response = disambig_result.message
                    elif disambig_result.error == 'crud_confirmation_required':
                        # Two-step: disambiguation resolved, now showing CRUD gate
                        response = disambig_result.message
                    else:
                        response = (
                            disambig_result.message
                            + self._format_confirmation_detail(disambig_result)
                        )
                        if disambig_result.success:
                            actions_taken.append(
                                self._build_action_taken(disambig_result)
                            )
                else:
                    # Unrecognized — re-show disambiguation prompt
                    response = (
                        f"{pending_disambig['confirmation_message']}\n\n"
                        "Please reply with a number, NONE, or CANCEL"
                    )
            # Then check for pending entity clarification (disambiguation)
            elif (clarification := intent_service.get_pending_clarification(self.user)):
                clarification_result = intent_service.resolve_clarification(
                    self.user, message,
                )
                if clarification_result:
                    response = (
                        clarification_result.message
                        + self._format_confirmation_detail(clarification_result)
                    )
                    if clarification_result.success:
                        actions_taken.append(
                            self._build_action_taken(clarification_result)
                        )
                else:
                    # Could not resolve — re-show numbered options
                    candidates = clarification['candidates']
                    numbered = [
                        f"{i + 1}. {c['title']}"
                        for i, c in enumerate(candidates)
                    ]
                    response = (
                        "I'm not sure which one you mean. "
                        "Please choose:\n" + "\n".join(numbered)
                    )
            else:
                # ── Shared Deterministic Router ────────────────────────────
                # Unified routing layer for both streaming and non-streaming.
                # Handles: deterministic data queries, health summary fast
                # path, strict health status, and check-in prefilter.
                # See apps/ai/deterministic_router.py for route registry.
                _route_result = None
                if _ltrace:
                    _ltrace.start('ROUTER_CLASSIFICATION')
                try:
                    from apps.ai.deterministic_router import (
                        classify_and_route as _classify_route,
                        RouteCategory as _RC,
                    )
                    _route_result = _classify_route(
                        message, self.user,
                        cos_context_cache=_cos_context_cache,
                        conversation=conversation,
                    )

                    # Terminal routes: response is complete, skip LLM
                    if _route_result.is_terminal and _route_result.response:
                        response = _route_result.response
                        # Store event context for follow-up continuity
                        if _route_result.route_name in (
                            'event_missed_query',
                            'event_timeline_query',
                            'event_slippage_query',
                        ):
                            try:
                                from apps.ai.deterministic_router import get_stashed_events
                                from apps.core.ai_events.followup import store_event_context
                                _stashed = get_stashed_events()
                                if _stashed and conversation:
                                    store_event_context(
                                        conversation,
                                        _route_result.route_name,
                                        _stashed,
                                        response,
                                    )
                            except Exception as _ec_err:
                                logger.debug(
                                    "Event context storage failed: %s", _ec_err,
                                )
                except ImportError:
                    pass
                except Exception as _router_err:
                    logger.warning(
                        "Deterministic router failed, falling through: %s",
                        _router_err, exc_info=True,
                    )
                finally:
                    if _ltrace:
                        _ltrace.end('ROUTER_CLASSIFICATION')
                        if _route_result:
                            _ltrace.set_meta('route_name', _route_result.route_name)
                            _ltrace.set_meta('route_category', str(_route_result.category))

                # ── Check-in prefilter (detected by shared router) ─────────
                # Check-in queries skip intent recognition but need the full
                # CoS _generate_response flow with check-in context injection.
                _is_checkin_prefilter = (
                    _route_result is not None
                    and _route_result.category == 'checkin_prefilter'
                )
                if not response and _is_checkin_prefilter:
                    logger.info(
                        "CHECKIN_PREFILTER user=%s path=non_stream msg=%r",
                        self.user.id, message[:80],
                    )
                    response = self._generate_response(
                        message, conversation,
                        page_context=page_context,
                        image_data=image_data,
                        image_mime_type=image_mime_type,
                        cos_context_cache=_cos_context_cache,
                        all_images=all_images,
                        route_result=_route_result,
                        _ltrace=_ltrace,
                    )
                    # Quality gate: reject generic fallback check-in responses.
                    # The proactive briefing path has this gate but user-initiated
                    # check-ins did not — generic responses leaked to the user.
                    if response and self._is_fallback_response(response):
                        logger.warning(
                            "CHECKIN_FALLBACK_GATE user=%s — LLM returned "
                            "a fallback string for a check-in request. "
                            "Fallback already contains real data. Preview: %s",
                            self.user.id, (response or '')[:120],
                        )
                        # No replacement needed — new fallback already uses
                        # Execution Truth Engine data, not generic text.
                elif not response:
                    # ── Intent bypass: skip expensive intent LLM call when
                    # router detects no action signals in the message ──────
                    _skip_intent = (
                        _route_result is not None
                        and getattr(_route_result, 'skip_intent', False)
                    )
                    if _skip_intent:
                        logger.info(
                            "INTENT_BYPASS user=%s reason=no_action_signal msg=%r",
                            self.user.id, message[:80],
                        )
                        if _ltrace:
                            _ltrace.set_governance_decision('intent_bypassed')
                        intent_results = []
                        actionable_intents = []
                    else:
                        # Build lean conversation history for intent context
                        # resolution (anaphora: "the other one", "that event", "it").
                        from apps.ai.conversation.message_builder import build_messages_from_history
                        _intent_history = build_messages_from_history(
                            conversation.messages.order_by('-created_at'),
                            message,
                            max_messages=5,
                            max_content_chars=300,
                            token_budget=800,
                        )

                        # Try to recognize intents (supports multiple)
                        if _ltrace:
                            _ltrace.start('INTENT_RECOGNITION')
                        _intent_domain = (
                            _route_result.domain if _route_result else None
                        )
                        intent_results = intent_service.recognize_intents(
                            message, self.user, conversation_history=_intent_history,
                            page_context=page_context,
                            domain=_intent_domain,
                        )
                        if _ltrace:
                            _ltrace.end('INTENT_RECOGNITION')
                            if _intent_domain:
                                _ltrace.set_governance_decision(
                                    'scoped_tools', _intent_domain
                                )

                    # Filter out no_action results
                    actionable_intents = [ir for ir in intent_results if ir.intent_type != 'no_action']

                    # ── Inject proactive entity context into intent parameters ──
                    # When the user responds to a proactive check-in with a complex
                    # request (e.g., "B, 8:30am today"), the PendingAction holds the
                    # entity_id. Inject it into matching intent parameters so the
                    # action handler can resolve by ID instead of title matching.
                    if _proactive_entity_context and actionable_intents:
                        _entity_task_id = _proactive_entity_context.get('task_id')
                        if _entity_task_id:
                            for ir in actionable_intents:
                                if ir.intent_type in (
                                    'complete_task', 'skip_task', 'mutate_task',
                                ):
                                    # Inject as _resolved_id — the existing pattern
                                    # that action handlers use to skip text matching
                                    if not ir.parameters.get('_resolved_id'):
                                        ir.parameters['_resolved_id'] = _entity_task_id
                                        ir.parameters['_from_proactive_context'] = True
                                        logger.info(
                                            "PROACTIVE_ENTITY_INJECT user=%s task_id=%s intent=%s",
                                            self.user.id, _entity_task_id, ir.intent_type,
                                        )

                    # Domain mismatch telemetry (non-blocking)
                    self._log_intent_domain_mismatch(
                        self.user, actionable_intents, page_context, message,
                    )

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

                                if actions_taken:
                                    _cos_context_cache = None
                            else:
                                # Execute all actions via orchestrator
                                orch_actions = enrich_and_execute(
                                    self.user, actionable_intents, orch_result
                                )

                                for action_result in orch_actions:
                                    if action_result.success:
                                        actions_taken.append(self._build_action_taken(action_result))

                                # Store clarification state for any multiple_matches
                                for ar in orch_actions:
                                    if (ar.error == 'multiple_matches'
                                            and ar.created_object
                                            and ar.created_object.get('candidates')):
                                        _match_intent = next(
                                            (ir for ir in actionable_intents
                                             if ir.intent_type == ar.action_type),
                                            None,
                                        )
                                        if _match_intent:
                                            intent_service.store_pending_clarification(
                                                self.user,
                                                intent_type=_match_intent.intent_type,
                                                parameters=_match_intent.parameters,
                                                candidates=ar.created_object['candidates'],
                                            )

                                # Use orchestrator enhanced response if available
                                if orch_result.response:
                                    response = orch_result.response
                                else:
                                    response_parts = []
                                    for ar in orch_actions:
                                        response_parts.append(ar.message + self._format_confirmation_detail(ar))
                                    response = " ".join(response_parts)

                                # Phase 6.6: Capture CRUD confirmation pills
                                # from any blocked action so they render as
                                # A/B/C buttons in the chat widget.
                                _qr = self._extract_quick_replies(orch_actions)
                                if _qr:
                                    _pending_quick_replies = _qr

                                # Invalidate in-request CoS context cache after
                                # mutations so downstream code (validators, etc.)
                                # doesn't use stale schedule data.
                                if actions_taken:
                                    _cos_context_cache = None

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
                                image_mime_type=image_mime_type,
                                cos_context_cache=_cos_context_cache,
                                all_images=all_images,
                                route_result=_route_result,
                                _ltrace=_ltrace,
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
                                    image_mime_type=image_mime_type,
                                    cos_context_cache=_cos_context_cache,
                                    all_images=all_images,
                                    route_result=_route_result,
                                    _ltrace=_ltrace,
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

                # ── Invalidate in-request CoS cache after mutations ──
                # If any actions were executed (task created/moved/completed),
                # clear the cached context so downstream validators and any
                # follow-up processing don't use stale schedule data.
                if actions_taken:
                    _cos_context_cache = None

                # ── Phase 8: Pre-release validator gate ──────────────
                # Inspect LLM response before persistence. Structural
                # violations are blocked (replaced); unverifiable action
                # claims are blocked; numeric deviations are observe-only.
                # Validator crash returns safe response.
                if _ltrace:
                    _ltrace.start('POST_PROCESSING')
                try:
                    from apps.core.ai_governance.validator_gate import (
                        validate_response,
                    )
                    validation = validate_response(
                        response, self.user, conversation,
                        action_executed=bool(actions_taken),
                    )
                    response = validation['response']
                except Exception as e:
                    logger.warning("Phase 8 validator gate failed: %s", e, exc_info=True)
                # ── End Phase 8 validator gate ────────────────────────

                # ── Health Intelligence validator (observe-only) ──────
                try:
                    from apps.ai.validators.health_response_validator import (
                        validate_health_response,
                    )
                    validate_health_response(
                        response, _cos_context_cache, self.user,
                    )
                except ImportError:
                    pass
                except Exception as e:
                    logger.debug("Health response validator error: %s", e)
                # ── End health intelligence validator ─────────────────
                if _ltrace:
                    _ltrace.end('POST_PROCESSING')

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

        # ── CoS Truth Validation (post-response guardrail) ──
        # Check if CoS fabricated completions that contradict live execution data.
        # If violations found, REJECT the response and regenerate with strict mode.
        try:
            from apps.ai.cos_fact_statements import build_locked_facts
            from apps.ai.cos_truth_validator import (
                validate_locked_facts, log_cos_debug_state,
                build_locked_regeneration_prompt,
            )
            log_cos_debug_state(self.user)
            _locked = build_locked_facts(self.user)
            _validated, _truth_violations = validate_locked_facts(
                response, _locked, self.user, allow_regenerate=True,
            )
            if _truth_violations and any(
                v.get('should_reject') for v in _truth_violations
            ):
                logger.error(
                    "COS_LOCKED_REJECT user=%s violations=%d domains=%s "
                    "— REJECTING, regenerating with locked facts",
                    self.user.id, len(_truth_violations),
                    [v['domain'] for v in _truth_violations],
                )
                try:
                    response = self._generate_response(
                        message, conversation,
                        page_context=page_context,
                        cos_context_cache=None,
                        all_images=all_images,
                        route_result=_route_result,
                        _ltrace=_ltrace,
                    )
                    # Validate regenerated (no more retries)
                    response, _regen_violations = validate_locked_facts(
                        response, _locked, self.user,
                        allow_regenerate=False,
                    )
                    if _regen_violations:
                        logger.error(
                            "COS_LOCKED_REGEN_STILL_VIOLATED user=%s",
                            self.user.id,
                        )
                except Exception as regen_err:
                    logger.error(
                        "COS_LOCKED_REGEN_FAILED user=%s error=%s",
                        self.user.id, regen_err,
                    )
                    response = _validated
            elif _truth_violations:
                response = _validated

            # ── Narration Contract enforcement (5a — soft) ──
            # Inspect the (possibly regenerated) response for state
            # claims and check traceability to canonical sources.
            # Canonical and rollup blobs are constructed from the
            # data we already have in scope, not from prompt text —
            # so this path doesn't depend on prompt plumbing.
            _narration_result = None
            _exec_state_for_telem = None
            _contradictions = []
            try:
                from apps.ai.narration_contract_validator import (
                    validate_narration_contract,
                )
                from apps.core.execution.execution_state import (
                    build_execution_state,
                )
                _exec_state_for_telem = build_execution_state(self.user)
                _eligible = _exec_state_for_telem.get('eligible_actions') or []
                _at_risk = _exec_state_for_telem.get('at_risk_actions') or []
                _expired = _exec_state_for_telem.get('expired_items') or []
                _domains = (
                    _exec_state_for_telem.get('summaries', {}).get('domains', {})
                )
                _meds = (
                    _exec_state_for_telem.get('summaries', {}).get('medications', {})
                )
                # Canonical blob: per-item entity titles the LLM is
                # allowed to make state claims about.
                _canonical_titles = (
                    [a.get('title', '') for a in _eligible]
                    + [a.get('title', '') for a in _at_risk]
                    + [i.get('title', '') for i in _expired]
                )
                _next_msg = (
                    (_locked or {}).get('next_action', '')
                )
                _canonical_blob = "\n".join(
                    [_next_msg] + _canonical_titles
                )
                # Rollup blob: domain labels + window labels.
                _rollup_blob = "\n".join(
                    list(_domains.keys())
                    + [m.get('label', '') for m in _meds.values()]
                )
                _narration_result = validate_narration_contract(
                    response, _canonical_blob, _rollup_blob,
                    user_id=self.user.id,
                    request_id=getattr(self, '_chat_request_id', None),
                )
            except Exception:
                logger.warning(
                    "NARRATION_CONTRACT_VALIDATOR failed user=%s",
                    self.user.id, exc_info=True,
                )

            # ── Contradiction telemetry (5b) ──
            try:
                from apps.core.ai_orchestrator.contradiction_telemetry import (
                    detect_contradictions,
                )
                if _exec_state_for_telem is None:
                    from apps.core.execution.execution_state import (
                        build_execution_state as _bes2,
                    )
                    _exec_state_for_telem = _bes2(self.user)
                _fresh_med_schedule = []
                try:
                    from apps.core.ai_state.state_builder import (
                        build_medicine_state,
                    )
                    _fresh_med = build_medicine_state(self.user) or {}
                    _fresh_med_schedule = _fresh_med.get(
                        'schedule_status_today', [],
                    )
                except Exception:
                    pass
                _contradictions = detect_contradictions(
                    exec_state=_exec_state_for_telem,
                    fresh_med_schedule=_fresh_med_schedule,
                    user_id=self.user.id,
                    request_id=getattr(self, '_chat_request_id', None),
                )
            except Exception:
                logger.warning(
                    "CONTRADICTION_TELEMETRY failed user=%s",
                    self.user.id, exc_info=True,
                )

            # ── Snapshot artifact (B1, flag-gated) ──
            try:
                from django.conf import settings as _snap_settings
                from apps.ai.observability.chat_snapshot import (
                    build_snapshot_payload, dump_chat_snapshot,
                    new_request_id,
                )
                _request_id = (
                    getattr(self, '_chat_request_id', None)
                    or new_request_id()
                )
                dump_chat_snapshot(build_snapshot_payload(
                    request_id=_request_id,
                    user_id=self.user.id,
                    user_message=str(message)[:1024],
                    rendered_prompt='',
                    execution_state=_exec_state_for_telem or {},
                    selector_outputs={},
                    rollup_summaries=(
                        (_exec_state_for_telem or {}).get('summaries', {})
                    ),
                    contradictions=[
                        c.as_dict() if hasattr(c, 'as_dict') else c
                        for c in (_contradictions or [])
                    ],
                    narration_validations=_narration_result or {},
                    llm_response_text=response or '',
                    llm_model=getattr(_snap_settings, 'COS_MODEL', 'unknown'),
                    llm_duration_ms=0,
                ))
            except Exception:
                # Snapshot is observability — never break chat.
                logger.warning(
                    "CHAT_SNAPSHOT post-response failed user=%s",
                    self.user.id, exc_info=True,
                )
        except Exception as _val_outer_err:
            # Truth validation failure is CRITICAL — log at error level
            logger.error(
                "COS_LOCKED_VALIDATOR_CRASHED user=%s error=%s "
                "— truth validation could not run on non-stream response",
                self.user.id, _val_outer_err, exc_info=True,
            )

        # ── State guard: block LLM-fabricated state descriptions ──
        # Only apply when the router selected a state-reporting path
        # (check-in, status, deterministic data). Conversational fallthrough
        # responses (faith Q&A, coaching, etc.) must not be replaced by
        # the evening/morning renderer. The router is the source of truth
        # for interaction type.
        _is_conversational_fallthrough = (
            _route_result is not None
            and getattr(_route_result, 'category', None) == 'fallthrough'
        )
        if not _is_conversational_fallthrough:
            try:
                from apps.ai.beth_checkin_renderer import guard_llm_output
                response = guard_llm_output(response, self.user)
            except Exception:
                pass  # Guard failure must never break chat

        # ── Mid-response state revalidation (context comparison) ──
        # Compares pre-generation state snapshot with current truth.
        # If ANY completion status changed, DISCARD stale response and
        # REGENERATE. No LLM text parsing — purely system state comparison.
        try:
            if _pre_gen_snapshot is not None:
                from apps.ai.cos_state_revalidator import (
                    capture_state_snapshot, has_state_changed,
                )
                _post_gen_snapshot = capture_state_snapshot(self.user)
                if has_state_changed(_pre_gen_snapshot, _post_gen_snapshot):
                    logger.info(
                        "COS_STATE_REGEN user=%s — execution truth changed "
                        "during generation, regenerating with fresh context",
                        self.user.id,
                    )
                    try:
                        response = self._generate_response(
                            message, conversation,
                            page_context=page_context,
                            cos_context_cache=None,  # force fresh context
                            all_images=all_images,
                            route_result=_route_result,
                            _ltrace=_ltrace,
                        )
                    except Exception as _regen_err:
                        logger.error(
                            "COS_STATE_REGEN_FAILED user=%s error=%s "
                            "— keeping original response",
                            self.user.id, _regen_err,
                        )
                        # Keep original response — fail-open
        except Exception:
            pass  # Revalidation failure must never break chat

        # Save assistant response
        msg_type = 'action' if actions_taken else 'text'
        import uuid as _uuid_ns
        _ns_request_id = str(_uuid_ns.uuid4())
        AssistantMessage.objects.create(
            conversation=conversation,
            role='assistant',
            content=response,
            message_type=msg_type,
            # Phase 6.6: structured A/B/C pills for CRUD confirmations.
            quick_replies=_pending_quick_replies or [],
            # Phase 6.7: lifecycle metadata for execution isolation.
            metadata={
                'request_id': _ns_request_id,
                'status': 'completed',
                'stream_interrupted': False,
                'intent_locked': bool(actions_taken),
                'page_context_captured': bool(page_context),
            },
        )

        # Update conversation
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])

        # Post-response: record interaction depth for Adaptive CoS Presence.
        # Determines whether this was a "deep" interaction (briefing, check-in,
        # or multi-message engagement) so future briefings can adapt.
        try:
            from apps.ai.executive_briefing import record_interaction_depth
            _metadata_post = conversation.metadata or {}
            _briefing_was_delivered = (
                _metadata_post.get('last_briefing_date') == str(
                    timezone.now().date()
                )
            )
            _msg_lower_depth = (message or '').lower()
            _is_checkin_depth = any(
                p in _msg_lower_depth for p in [
                    'check in', 'checking in', 'status', 'refresh',
                    "how's my day", 'how does my day look',
                    "what's left", "what do i have",
                ]
            )
            record_interaction_depth(
                conversation, self.user,
                briefing_delivered=_briefing_was_delivered,
                is_checkin=_is_checkin_depth,
            )
        except Exception:
            pass  # Interaction depth tracking must never break chat

        # Post-response: trigger rolling conversation summary if needed.
        # Run in background thread — may make an OpenAI API call (~1-3s).
        try:
            import threading
            from apps.ai.executive_briefing import maybe_generate_rolling_summary

            def _rolling_summary_bg():
                try:
                    maybe_generate_rolling_summary(self.user, conversation)
                except Exception:
                    pass

            threading.Thread(
                target=_rolling_summary_bg, daemon=True
            ).start()
        except Exception:
            pass  # Summary generation must never break chat

        # Post-response: store conversation memory for RAG retrieval.
        # Run in a background thread to avoid blocking the response
        # (embedding API call + DB write takes ~150-300ms).
        try:
            import threading
            from apps.ai.memory_service import store_memory

            def _store_memory_bg():
                try:
                    store_memory(
                        user=self.user,
                        user_message=message,
                        assistant_response=response,
                        conversation=conversation,
                        page_context=page_context,
                    )
                except Exception:
                    pass

            threading.Thread(
                target=_store_memory_bg, daemon=True
            ).start()
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

        # ── Deterministic critical signal injection (post-LLM, never skipped) ──
        # Critical signals (birthdays, anniversaries, and future: health alerts)
        # are injected deterministically — the LLM does NOT decide inclusion.
        response = self._inject_critical_signals(response)

        # Return structured response
        # Phase 6.7: surface request_id so the frontend can clear its
        # pending marker and correlate the reply with the submitted message.
        result = {'response': response, 'request_id': _ns_request_id}
        if actions_taken:
            # For backwards compatibility, also include single action_taken
            result['action_taken'] = actions_taken[0] if len(actions_taken) == 1 else None
            result['actions_taken'] = actions_taken

        # Include structured options for CRUD confirmations (A/B/C chips)
        # Phase 6.6: _pending_quick_replies is the canonical source; it is
        # populated on both initial CRUD gate trips and re-shown confirmations.
        if _pending_quick_replies:
            result['options'] = _pending_quick_replies
        elif (_resp_options := self._extract_options_from_actions(actions_taken)):
            result['options'] = _resp_options
        else:
            # Parse A/B/C patterns from LLM text for general responses
            _cleaned, _text_options = self._extract_options_from_text(response)
            if _text_options:
                result['response'] = _cleaned
                result['options'] = _text_options

        # Include navigation hint for successful actions
        _nav = self._get_navigation_hint(actions_taken)
        if _nav:
            result['navigation'] = _nav

        # Include flag if user message had image(s)
        if has_any_images:
            result['user_message_has_image'] = True

        logger.warning("COS TOTAL send_message took %.1f ms", (_t.monotonic() - _t_total_start) * 1000)

        # ── Latency report (diagnostic instrumentation) ──
        if _ltrace:
            try:
                _ltrace.report()
            except Exception:
                pass

        # Store result for idempotency deduplication
        store_result(self.user.id, message, result)

        return result

    def _inject_critical_signals(self, response):
        """
        Deterministic injection of critical signals into the response.

        Runs AFTER LLM response generation. The system — not the LLM —
        determines what must be acknowledged. Currently handles significant
        events (birthdays, anniversaries, memorials). Designed to support
        future signal types (health alerts, missed commitments).

        Uses structured idempotency: checks event-type keywords + person
        name to determine if the LLM already acknowledged each event.
        Only injects events the LLM missed, using grouped formatting
        for natural multi-event phrasing.

        Args:
            response: str — The LLM-generated (or deterministic) response.

        Returns:
            str — Response with unacknowledged signals prepended if needed.
        """
        try:
            from apps.life.services.event_acknowledgment import (
                get_today_critical_events,
                check_response_acknowledges_events,
                build_grouped_acknowledgment,
            )

            events = get_today_critical_events(self.user)
            if not events:
                return response

            # Structured idempotency: check which events LLM missed
            unacknowledged = check_response_acknowledges_events(
                response, events,
            )
            ack_count = len(events) - len(unacknowledged)

            if not unacknowledged:
                logger.info(
                    "critical_signal_evaluation user=%s events_found=%d "
                    "acknowledged_by_llm=%d injected=0",
                    self.user.id, len(events), ack_count,
                )
                return response

            # Build grouped injection from only the missed events
            injection = build_grouped_acknowledgment(unacknowledged)
            if not injection:
                # Events exist but no injection built — critical failure
                logger.error(
                    "CRITICAL: events_found=%d acknowledged=0 injected=0 "
                    "— event not acknowledged or injected user=%s",
                    len(events), self.user.id,
                )
                return response

            logger.warning(
                "critical_signal_evaluation user=%s events_found=%d "
                "acknowledged_by_llm=%d injected=%d types=%s",
                self.user.id,
                len(events),
                ack_count,
                len(unacknowledged),
                [e.get("type") for e in unacknowledged],
            )

            # Prepend at top of response (already sorted by priority)
            if response:
                return injection + "\n\n" + response
            return injection

        except Exception:
            logger.error(
                "CRITICAL_SIGNALS_FAILED user=%s — injection failed, "
                "returning original response",
                self.user.id,
                exc_info=True,
            )
            return response

    # Backward-compatible alias (tests, external callers)
    _inject_event_acknowledgment = _inject_critical_signals

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

    def _extract_quick_replies(self, action_results) -> list:
        """
        Extract quick_replies pills from any ActionResult in a list that
        was blocked by the CRUD confirmation gate.

        Phase 6.6: CRUD confirmations MUST always carry their A/B/C pill
        options through to the saved AssistantMessage. Never fall back to
        plain-text instructions.
        """
        if not action_results:
            return []
        try:
            for ar in action_results:
                if getattr(ar, 'error', None) != 'crud_confirmation_required':
                    continue
                detail = getattr(ar, 'confirmation_detail', None) or {}
                options = detail.get('quick_replies') or detail.get('options')
                if options:
                    return list(options)
        except Exception:
            pass
        return []

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
            parts.append(f"Saved in {where}")
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

    # ── Navigation hints for post-action UX ─────────────────────────
    # Maps action_type → URL path so the front-end can offer "View it"
    NAVIGATION_HINTS = {
        'log_heart_rate': '/health/vitals/',
        'log_blood_pressure': '/health/vitals/',
        'log_blood_glucose': '/health/vitals/',
        'log_oxygen_saturation': '/health/vitals/',
        'log_temperature': '/health/vitals/',
        'log_weight': '/health/weight/',
        'log_body_measurements': '/health/weight/',
        'log_medicine': '/health/medicine/log/',
        'create_medicine': '/health/medicine/',
        'log_workout': '/health/fitness/',
        'log_cardio': '/health/fitness/',
        'log_nutrition': '/health/nutrition/',
        'log_fasting': '/health/fasting/',
        'log_journal': '/journal/',
        'create_journal': '/journal/',
        'log_prayer': '/faith/prayer/',
        'log_scripture_reading': '/faith/scripture/',
        'create_task': '/life/tasks/',
        'mutate_task': '/life/tasks/',
        'complete_task': '/life/tasks/',
        'create_goal': '/purpose/goals/',
        'create_habit': '/life/habits/',
        'create_event': '/life/calendar/',
        'mutate_calendar_event': '/life/calendar/',
        'create_appointment': '/medical/appointments/',
    }

    @staticmethod
    def _extract_options_from_actions(actions_taken):
        """
        Extract structured options from action results.

        When a CRUD confirmation was required, the confirmation_detail
        contains the options list that should be rendered as clickable chips.
        """
        if not actions_taken:
            return None
        for action in actions_taken:
            detail = action.get('confirmation_detail') or {}
            opts = detail.get('options')
            if opts:
                return opts
        return None

    @staticmethod
    def _extract_options_from_text(response_text):
        """
        Parse A/B/C option patterns from LLM response text and convert
        them into structured option dicts for rendering as clickable chips.

        Detects patterns like:
            A) Do it now
            B) Schedule it for later
            C) Skip it

        Also handles:
            A. Do it now
            **A)** Do it now

        Returns:
            (cleaned_text, options_list) — text with options removed and
            the structured options, or (response_text, None) if no pattern found.
        """
        import re

        if not response_text:
            return response_text, None

        # Pattern: lines starting with a letter A-D followed by ) or .
        # Handles optional markdown bold wrapper: **A)** or **A.**
        _pattern = re.compile(
            r'^\s*(?:\*\*)?([A-D])\s*[).\]]\s*(?:\*\*)?\s*(.+?)$',
            re.MULTILINE,
        )
        matches = list(_pattern.finditer(response_text))

        if len(matches) < 2:
            # Need at least 2 options to form a valid set
            return response_text, None

        options = []
        for m in matches:
            key = m.group(1).upper()
            label = m.group(2).strip().rstrip('*')
            options.append({
                'key': key,
                'label': label,
                'action': 'acknowledge',
                'style': 'primary' if key == 'A' else 'secondary',
            })

        # Remove the option lines from the text so they render as chips only
        cleaned = response_text
        for m in reversed(matches):
            # Remove the line containing this match
            start = m.start()
            end = m.end()
            # Extend to consume the newline after the match
            if end < len(cleaned) and cleaned[end] == '\n':
                end += 1
            cleaned = cleaned[:start] + cleaned[end:]

        # Clean up trailing whitespace / blank lines
        cleaned = cleaned.rstrip()

        return cleaned, options

    def _get_navigation_hint(self, actions_taken):
        """
        Get a navigation hint for successful actions.

        Returns a dict with 'url' and 'label' if the action type
        has a known destination page, or None.
        """
        if not actions_taken:
            return None
        for action in actions_taken:
            if not action.get('success'):
                continue
            action_type = action.get('type', '')
            url = self.NAVIGATION_HINTS.get(action_type)
            if url:
                return {
                    'url': url,
                    'label': 'View it',
                    'action_type': action_type,
                }
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
            # User directing CoS to page content
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

        # Meta-questions about CoS / system behavior / errors / complaints
        # are NOT navigation — they need the LLM to answer conversationally.
        meta_question_indicators = [
            'how come', 'why do you', 'why does', 'why did you',
            'why are you', 'why is it', 'why is beth', 'why is the',
            'you always', 'you never', 'you keep', 'you said',
            'server', 'error', 'crash', 'broke', 'broken', 'wrong',
            'bug', 'not working', 'doesn\'t work', 'failed',
            'what happened', 'what went wrong', 'what is going on',
            'what\'s going on', 'confused', 'makes no sense',
        ]
        if any(indicator in query_lower for indicator in meta_question_indicators):
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
        image_mime_type: str = None,
        cos_context_cache: dict = None,
        _return_context_only: bool = False,
        all_images: list = None,
        _defer_briefing_marking: bool = False,
        route_result=None,
        _ltrace=None,
    ) -> str:
        """Generate AI response to user message using coaching style.

        Now integrates with the personal data query system to inject relevant
        personal data context (weight, journal, medication, food, mood) when
        users ask about their data.

        The assistant is schedule-aware and proactively references the user's
        calendar events, especially during greetings. It provides task/priority
        information when relevant or when the user asks for it.

        Supports image attachments for OpenAI Vision processing (up to 5).

        Args:
            message: User's message
            conversation: The conversation object
            page_context: Optional dict with 'url', 'module', 'page_title' for context-aware responses
            image_data: Optional base64-encoded image data (first/legacy image)
            image_mime_type: Optional MIME type of the image (e.g., 'image/png')
            _return_context_only: If True, return assembled prompt context dict
                instead of calling the LLM. Used by _generate_response_stream().
            all_images: Optional list of (base64, mime_type) tuples for multi-image
        """
        # Get conversation history - 40 messages for deep conversational threading
        # More history means CoS can follow topic changes and reference earlier context
        history = conversation.messages.order_by('-created_at')[:40]

        # Always include time context so the AI knows the user's current time
        # (e.g., "what time is it?" queries). Urgency messaging is part of time context.
        # Conditional framework: skip COS_PROACTIVE_INTELLIGENCE_PROMPT (~2.9K tokens)
        # for simple domain-specific data queries (Phase 4 token governance).
        _include_proactive = True
        from django.conf import settings as _fw_settings
        if getattr(_fw_settings, 'WLJ_CONDITIONAL_FRAMEWORKS_ENABLED', False):
            _is_simple_domain = (
                route_result is not None
                and route_result.domain is not None
                and route_result.category not in ('checkin_prefilter',)
            )
            _coaching_keywords = (
                'should i', 'what should', 'help me', 'advice',
                'recommend', 'suggest', 'coach', 'motivat',
                'priorit', 'focus', 'struggling',
            )
            _needs_coaching = any(kw in message.lower() for kw in _coaching_keywords)
            if _is_simple_domain and not _needs_coaching:
                _include_proactive = False
                if _ltrace:
                    _ltrace.set_governance_decision(
                        'framework_skipped', 'proactive_intelligence'
                    )
        system_prompt = self._build_system_prompt(
            include_time_context=True,
            include_proactive_prompt=_include_proactive,
        )

        # ── v4: Functional query detection ──────────────────────────────
        # Suppress calibration injection for ANY functional query.
        # The calibration MANDATORY OVERRIDE tells the LLM "only listen
        # and ask calibration questions" — this conflicts with check-ins,
        # status requests, data queries, and advice questions, causing the
        # LLM to hallucinate (e.g., "3 of 5 tasks" fabrication).
        #
        # Calibration should ONLY be active when the user is answering
        # a calibration question (short statements without question marks
        # or imperative verbs). For everything else, suppress it.
        _msg_lower_early = (message or '').lower()
        _is_checkin_early = any(
            p in _msg_lower_early for p in CHECKIN_PATTERNS
        )
        _is_functional_query = (
            '?' in (message or '')
            or any(m in _msg_lower_early for m in [
                'what ', 'how ', 'why ', 'when ', 'where ', 'which ',
                'tell me', 'remind me', 'encourage', 'explain',
                'help me', 'show me', 'should i', 'am i', 'do i',
                'can i', 'will i', 'would you',
            ])
            or _is_checkin_early
        )
        if _is_functional_query:
            logger.info(
                "v4_CALIBRATION_SKIP user=%s msg=%r — functional query "
                "detected, suppressing calibration injection",
                self.user.id, (message or '')[:80],
            )
        # ────────────────────────────────────────────────────────────────

        # ── PIE Health Screenshot Analysis (early, before system prompt) ──
        # Run structured extraction + deterministic analysis on health
        # screenshots so the result is available for CoS prompt injection
        # and vision instruction replacement below.
        _health_analysis = None
        _img_count_early = (
            len(all_images) if all_images
            else (1 if image_data and image_mime_type else 0)
        )
        if _img_count_early >= 1 and all_images:
            try:
                from apps.core.ai_insights.health.screenshot_parser import (
                    parse_health_screenshot,
                )
                _img_b64, _img_mime = all_images[0]
                _parsed_health = parse_health_screenshot(_img_b64, _img_mime)
                if _parsed_health and _parsed_health.get('screenshot_type') != 'unknown':
                    from apps.core.ai_insights.health.sleep_analysis import (
                        analyze_sleep_data,
                    )
                    from apps.core.ai_insights.health.user_context import (
                        get_health_user_context,
                    )
                    _user_ctx = get_health_user_context(self.user)
                    if _parsed_health['screenshot_type'] == 'sleep':
                        _health_analysis = analyze_sleep_data(
                            _parsed_health, _user_ctx,
                        )
                    # Future: elif _parsed_health['screenshot_type'] == 'glucose': ...
            except Exception:
                logger.warning(
                    "PIE health screenshot analysis failed", exc_info=True,
                )

        # ================================================================
        # UNIFIED CoS SYSTEM PROMPT — PRIORITY-ORDERED
        #
        # The prompt is assembled in a clear hierarchy so the LLM knows
        # what matters most. Personality and relationship instructions
        # come FIRST (highest priority), operational context LAST.
        #
        # Order:
        #   1. Calibration override (if active — supersedes everything)
        #      EXCEPT: suppressed for check-in/advisory queries (v4)
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
                #
                # v4: Calibration injection is SUPPRESSED for check-in/advisory
                # queries. The calibration MANDATORY OVERRIDE conflicts with
                # check-in briefing instructions, causing hallucinated task
                # counts. Check-in queries have their own comprehensive data
                # injection and don't need calibration context.
                try:
                    from apps.core.blueprint.cos_governance import (
                        build_calibration_system_injection,
                        get_calibration_state,
                        mark_calibration_welcome_shown,
                        advance_calibration_day,
                    )
                    cal_state = get_calibration_state(self.user)
                    logger.info(
                        "Calibration check: user=%s state=%s checkin_skip=%s",
                        self.user.email,
                        {k: v for k, v in (cal_state or {}).items()
                         if k != 'next_question'} if cal_state else None,
                        _is_functional_query,
                    )
                    if (cal_state and cal_state['active']
                            and not cal_state['paused']
                            and not _is_functional_query):
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
                    logger.warning("Governance injection failed: %s", gov_err, exc_info=True)

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
                if _ltrace:
                    _ltrace.start('COS_CONTEXT_BUILD_TOTAL')
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
                    elif _is_checkin_early:
                        # Check-in / status requests FORCE a fresh context
                        # rebuild. Cached context may be stale — the user
                        # explicitly asked "where do things stand?" so they
                        # need real-time state, not a cached snapshot.
                        cos_context = build_cos_context(self.user)
                        logger.info(
                            "COS_FORCED_REFRESH user=%s reason=checkin_request",
                            self.user.id,
                        )
                    elif cos_context_cache:
                        # Reuse pre-computed cos_context from ECC pre-check
                        cos_context = cos_context_cache
                    else:
                        # Try layered cache → flat cache → full rebuild
                        try:
                            from apps.ai.readiness_cache import (
                                get_cached_cos_context as _rc_get_ctx,
                                get_layered_cos_context as _rc_get_layered,
                            )
                            from apps.ai.readiness_telemetry import log_fast_path, log_full_path
                            _rc_ctx = (
                                _rc_get_layered(self.user)
                                or _rc_get_ctx(self.user)
                            )
                        except Exception as _rc_err:
                            logger.warning(
                                "COS_CACHE_LOOKUP user=%s — readiness cache failed: %s",
                                self.user.id, _rc_err, exc_info=True,
                            )
                            _rc_ctx = None
                        if _rc_ctx:
                            cos_context = _rc_ctx
                            try:
                                log_fast_path(self.user.id)
                            except Exception:
                                pass  # Telemetry — non-critical
                        else:
                            # Domain scoping: if the router identified a
                            # domain, only build relevant context sections.
                            _scoped = None
                            if route_result and route_result.domain:
                                try:
                                    from apps.ai.deterministic_router import (
                                        get_scoped_builders as _get_scoped,
                                    )
                                    _scoped = _get_scoped(route_result.domain)
                                except Exception as _scope_err:
                                    logger.warning(
                                        "COS_DOMAIN_SCOPE user=%s — scoped builder failed: %s",
                                        self.user.id, _scope_err, exc_info=True,
                                    )
                            cos_context = build_cos_context(
                                self.user, scoped_builders=_scoped,
                            )
                            try:
                                log_full_path(self.user.id)
                            except Exception:
                                pass  # Telemetry — non-critical
                            # Write-back: populate readiness cache so subsequent
                            # messages within the TTL window get a cache hit.
                            try:
                                from apps.ai.readiness_cache import (
                                    set_cached_cos_context as _rc_set_ctx,
                                    set_layered_cos_context as _rc_set_layered,
                                )
                                _rc_set_ctx(self.user, cos_context)
                                _rc_set_layered(self.user, cos_context)
                            except Exception:
                                pass  # Cache write-back — non-critical
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
                            logger.warning("ECC detection failed in _generate_response: %s", ecc_err, exc_info=True)

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

                    # Inject affirmed completions so system prompt suppresses
                    # further reminders for user-affirmed activities.
                    try:
                        from .affirmation_detector import get_affirmed_completions
                        _affirmed = get_affirmed_completions(conversation)
                        if _affirmed:
                            cos_context['affirmed_completions'] = _affirmed
                    except Exception:
                        pass  # Affirmation context must never break chat

                    # Inject PIE health screenshot analysis for immediate
                    # reasoning response (not just persisted insight).
                    if _health_analysis:
                        cos_context['health_screenshot_analysis'] = _health_analysis

                    # Inject recent event context for follow-up continuity
                    try:
                        from apps.core.ai_events.followup import get_event_context
                        _rec_evt = get_event_context(conversation) if conversation else None
                        if _rec_evt:
                            cos_context['recent_event_context'] = _rec_evt
                    except Exception:
                        pass  # Non-critical

                    cos_injection = format_cos_system_injection(
                        cos_context, user_message=message,
                    )

                    # ── CoS prompt debug logging ──
                    # Log the last ~500 chars to verify FINAL TRUTH ANCHOR
                    # is present at the end of the prompt.
                    if cos_injection:
                        _tail = cos_injection[-600:] if len(cos_injection) > 600 else cos_injection
                        _has_anchor = 'FINAL EXECUTION STATUS' in cos_injection
                        logger.info(
                            "[CoS PROMPT DEBUG] user=%s path=non_stream "
                            "len=%d has_truth_anchor=%s "
                            "context_builder=cos_context.format_cos_system_injection "
                            "last_500_chars=\n%s",
                            self.user.id, len(cos_injection),
                            _has_anchor, _tail,
                        )
                        if not _has_anchor:
                            logger.error(
                                "COS_TRUTH_ANCHOR_MISSING user=%s — "
                                "FINAL TRUTH ANCHOR not found in prompt! "
                                "This means CoS has NO execution truth.",
                                self.user.id,
                            )

                    # Append operational context AFTER personality layers
                    # so the LLM prioritizes relationship over raw data.
                    append_layers.append(cos_injection)

                    # ── LOCKED CoS STATE ──────────────────────────────
                    # Inject deterministic structured output as immutable
                    # facts. The LLM MUST NOT alter, reorder, or infer
                    # beyond this data when referencing the user's day.
                    try:
                        from apps.ai.beth_checkin_renderer import (
                            build_cos_structured_output,
                        )
                        _cos_struct = build_cos_structured_output(self.user)
                        _do_now_str = ', '.join(
                            item['name'] for item in _cos_struct.get('do_now', [])
                        ) or 'none'
                        _seq_str = ' → '.join(
                            _cos_struct.get('sequence', [])
                        ) or 'none'
                        _locked_state = (
                            "--- LOCKED CoS STATE (DO NOT ALTER) ---\n"
                            f"Day state: {_cos_struct.get('state', 'on_track')}\n"
                            f"Phase: {_cos_struct.get('phase', 'morning')}\n"
                            f"Next commitment: {_cos_struct.get('next_commitment') or 'none'}\n"
                            f"Do now: {_do_now_str}\n"
                            f"Sequence: {_seq_str}\n"
                            f"Completed: {', '.join(_cos_struct.get('completed', [])) or 'none'}\n"
                            "--- END LOCKED CoS STATE ---\n"
                            "When referencing the user's day, priorities, or "
                            "state, you MUST use ONLY the data in LOCKED CoS "
                            "STATE. Do NOT infer, reorder, or add items beyond "
                            "what is listed."
                        )
                        append_layers.append(_locked_state)
                    except Exception:
                        pass  # LOCKED CoS STATE is advisory; must never break chat

                except Exception as cos_ctx_err:
                    logger.warning("CoS context (Layer 6) failed: %s", cos_ctx_err, exc_info=True)
                finally:
                    if _ltrace:
                        _ltrace.end('COS_CONTEXT_BUILD_TOTAL')
                        # Extract per-builder timings from context
                        try:
                            _bt = cos_context.get('_builder_timings', {}) if cos_context else {}
                            for _btag, _bdur in _bt.items():
                                if _bdur == 'skipped':
                                    # Record skipped builders as 0-duration so ops
                                    # telemetry can distinguish "skipped" from "missing".
                                    _ltrace.start(f'COS_BUILDER_{_btag}')
                                    _ltrace._stages[f'COS_BUILDER_{_btag}']['end'] = (
                                        _ltrace._stages[f'COS_BUILDER_{_btag}']['start']
                                    )
                                    continue
                                if not isinstance(_bdur, (int, float)):
                                    continue
                                _ltrace.start(f'COS_BUILDER_{_btag}')
                                _ltrace._stages[f'COS_BUILDER_{_btag}']['end'] = (
                                    _ltrace._stages[f'COS_BUILDER_{_btag}']['start'] + _bdur / 1000
                                )
                            # Ensure at least one COS_BUILDER_ entry exists so
                            # ops telemetry doesn't report false STALE.  This
                            # covers cached contexts or exception paths where
                            # _builder_timings is empty/missing.
                            if not _bt and cos_context:
                                _ltrace.start('COS_BUILDER_context_present')
                                _ltrace._stages['COS_BUILDER_context_present']['end'] = (
                                    _ltrace._stages['COS_BUILDER_context_present']['start']
                                )
                        except Exception as _bt_err:
                            logger.warning(
                                "CoS builder timing extraction failed: %s",
                                _bt_err, exc_info=True,
                            )

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
                except ImportError:
                    pass  # Reflection engine not installed
                except Exception as ref_err:
                    logger.warning(
                        "REFLECTION_CONTEXT user=%s — injection failed: %s",
                        self.user.id, ref_err, exc_info=True,
                    )

                # ----------------------------------------------------------
                # Assemble final prompt: priority layers → base → appended
                # ----------------------------------------------------------
                assembled_parts = priority_layers + [system_prompt] + append_layers
                system_prompt = "\n\n".join(part for part in assembled_parts if part)

        except Exception as cos_err:
            logger.error("CoS prompt assembly failed (total context loss): %s", cos_err, exc_info=True)

        # Executive Briefing (replaces simple greeting injection)
        # Delivers morning briefing, gap detection, life events, health gates,
        # journal follow-ups on first-of-day or gap re-entry interactions.
        if _ltrace:
            _ltrace.start('EXECUTIVE_BRIEFING')
        briefing = ""
        try:
            from apps.ai.executive_briefing import (
                build_executive_briefing,
                build_checkin_briefing,
                get_conversation_memory,
            )
            briefing = build_executive_briefing(self.user, conversation)
            if briefing:
                system_prompt += "\n\n" + briefing
            elif _is_checkin_early:
                # Mid-conversation check-in: executive briefing returned
                # empty (not first-of-day, no 4h gap), but user explicitly
                # asked for status. Build a lightweight check-in briefing
                # with health gates, tasks, and calendar data.
                checkin_briefing = build_checkin_briefing(self.user)
                if checkin_briefing:
                    system_prompt += "\n\n" + checkin_briefing
                    logger.info(
                        "CHECKIN_BRIEFING_INJECTED user=%s len=%d",
                        self.user.id, len(checkin_briefing),
                    )

            # Inject conversation memory (rolling summary of older messages).
            # v7: Skip for check-in/task queries — rolling summaries may contain
            # stale task references ("User completed Move Bins") that contaminate
            # deterministic task responses.
            if not _is_checkin_early:
                memory = get_conversation_memory(conversation)
                if memory:
                    system_prompt += "\n\n" + memory

            # ── Phase 1A · C15 — HealthBriefing narration addendum ──
            # If the CoS context carries a recent HealthBriefingSnapshot
            # (set by cos_context._build_health_briefing_slot), inject
            # the C14 narration contract + the per-briefing dynamic
            # addendum. The composer is read-only against SAE; this
            # path adds no cost to the request and is fully reversible
            # via WLJ_DISABLE_HEALTH_BRIEFING_SLOT.
            try:
                briefing_slot = (cos_context or {}).get("health_briefing")
                if briefing_slot and briefing_slot.get("payload"):
                    from apps.core.health_briefing.narration_contract import (
                        HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE,
                        build_briefing_addendum_from_payload,
                    )
                    dyn = build_briefing_addendum_from_payload(
                        briefing_slot["payload"]
                    )
                    system_prompt += (
                        "\n\n" + HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE
                        + "\n\n" + dyn
                    )
                    logger.info(
                        "HEALTH_BRIEFING_ADDENDUM_INJECTED user=%s "
                        "briefing_id=%s",
                        self.user.id,
                        briefing_slot.get("briefing_id", "")[:12],
                    )
            except Exception as _hb_err:
                logger.warning(
                    "Health briefing addendum injection failed: %s", _hb_err,
                )
        except Exception as e:
            logger.warning("Executive briefing failed: %s", e)
        finally:
            if _ltrace:
                _ltrace.end('EXECUTIVE_BRIEFING')

        # Phase 7.1: Semantic memory retrieval — retrieve past conversations
        # relevant to the current message (cross-session, embedding-based).
        # Memory gating: skip embedding lookup for deterministic data routes.
        if _ltrace:
            _ltrace.start('SEMANTIC_MEMORY_RETRIEVAL')
        _skip_memory = False
        # v7: Skip semantic memory for check-in/task queries — embedding
        # similarity retrieves past conversations about completing tasks,
        # which contaminates deterministic "completed today" responses.
        if _is_checkin_early:
            _skip_memory = True
        elif route_result:
            try:
                from apps.ai.deterministic_router import should_skip_semantic_memory
                _skip_memory = should_skip_semantic_memory(route_result)
            except Exception:
                pass
        try:
            from apps.ai.memory_service import retrieve_relevant_memories
            relevant_memories = (
                retrieve_relevant_memories(
                    self.user, message, top_k=3, exclude_minutes=30,
                ) if not _skip_memory else []
            )
            if relevant_memories:
                mem_lines = [
                    "--- RELEVANT PAST CONVERSATIONS ---",
                    "You've discussed similar topics before with this user:",
                ]
                for mem in relevant_memories:
                    days_ago = (timezone.now() - mem['created_at']).days
                    if days_ago == 0:
                        time_label = "Earlier today"
                    elif days_ago == 1:
                        time_label = "Yesterday"
                    elif days_ago < 7:
                        time_label = f"{days_ago} days ago"
                    else:
                        time_label = mem['created_at'].strftime('%b %d')
                    corrected = " [CORRECTED]" if mem.get('was_corrected') else ""
                    mem_lines.append(
                        f"  [{time_label}]{corrected} User asked: "
                        f"\"{mem['user_message'][:150]}\" → "
                        f"You said: \"{mem['assistant_summary'][:150]}\""
                    )
                mem_lines.append(
                    "Reference these naturally if relevant. "
                    "Do NOT repeat previous mistakes marked [CORRECTED]."
                )
                mem_lines.append("--- END PAST CONVERSATIONS ---")
                system_prompt += "\n\n" + "\n".join(mem_lines)
        except ImportError:
            pass
        except Exception as e:
            logger.debug("Semantic memory retrieval skipped: %s", e)

        # Phase 7.1: Correction record retrieval — prioritize corrections
        # the user has made to prevent repeating the same mistakes.
        try:
            from apps.ai.correction_service import get_correction_context_block
            correction_block = get_correction_context_block(self.user, message)
            if correction_block:
                system_prompt += "\n\n" + correction_block
        except ImportError:
            pass
        except Exception as e:
            logger.debug("Correction retrieval skipped: %s", e)
        finally:
            if _ltrace:
                _ltrace.end('SEMANTIC_MEMORY_RETRIEVAL')
                _ltrace.set_meta('memory_skipped', _skip_memory)

        # Pending CoS prompts (proactive nudging)
        try:
            from apps.cos.services.prompt_service import CosPromptService
            prompt_injection = CosPromptService.get_pending_prompt_injection(self.user)
            if prompt_injection:
                system_prompt += "\n\n" + prompt_injection
        except ImportError:
            pass  # CosPromptService not installed — optional module
        except Exception as _cos_prompt_err:
            logger.warning(
                "COS_PROMPT_INJECTION user=%s — failed: %s",
                self.user.id, _cos_prompt_err, exc_info=True,
            )

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
        except ImportError:
            pass  # EAE not installed — feature-flagged
        except Exception as _eae_err:
            logger.warning(
                "EAE_ARBITRATION user=%s — failed: %s",
                self.user.id, _eae_err, exc_info=True,
            )  # EAE must never break chat

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
            # v4: Advisory planning queries that need full briefing data
            'prioritize', 'structure my day', 'should i do today',
            'my priorities', 'biggest improvement', 'biggest difference',
            'highest impact', 'most important', 'top priority',
            # v7: Completed-task queries (temporal contamination fix)
            'completed today', 'i completed', 'have completed',
            'i finished today', 'did i complete', 'did i finish',
            'what did i complete', 'what have i completed',
            'what did i finish', 'tasks i completed',
            'tasks i finished', 'tasks i have completed',
            'what got done', 'what have i done today',
        ])

        # v7: Safety heuristic — catch missed task-completion phrasings.
        # If the message mentions tasks AND completion, treat as deterministic.
        if not is_asking_about_tasks:
            _has_task_word = any(w in message_lower for w in ('task', 'tasks'))
            _has_done_word = any(w in message_lower for w in (
                'completed', 'finished', 'done', 'complete', 'finish',
            ))
            if _has_task_word and _has_done_word:
                is_asking_about_tasks = True

        # Also check for broader analysis questions about habits, consistency, focus areas
        is_asking_for_analysis = any(phrase in message_lower for phrase in [
            'need to focus', 'need to improve', 'need to work on',
            'strengthen', 'weakness', 'falling behind', 'doing well',
            'my habits', 'my consistency', 'my streaks', 'my patterns',
            'missed', 'skipped', 'how many days',
            'since i started', 'how consistent', 'how am i doing',
            'how have i been doing', 'how have i been',
            'how have i done', 'how did i do', 'how\'s my day',
            'where am i', 'where do i need', 'where should i',
            'what areas', 'which areas',
            # Health data visibility questions
            'health data', 'healthkit', 'health records', 'health metrics',
            'my health', 'my vitals', 'vital signs', 'see my data',
            'see any data', 'new data', 'new activity', 'synced data',
            'apple health',
            # v4: Habit and improvement queries
            'habits', 'my habits', 'habit', 'improve my life',
            'on track', 'am i on track',
        ])

        # Check-in / day assessment — user wants a full CoS briefing.
        # Uses the module-level CHECKIN_PATTERNS constant (single source of truth).
        is_requesting_checkin = any(
            phrase in message_lower for phrase in CHECKIN_PATTERNS
        )

        # Upgrade task queries to full check-in briefing. The lightweight
        # counts-only path ("2 tasks remaining") is useless — the user asking
        # "what do I have to do" deserves the same specificity as "check in".
        if is_asking_about_tasks and not is_requesting_checkin:
            is_requesting_checkin = True

        # Qualified/filtered status questions ("other than nutrition, anything
        # left?", "am I done?") must NOT trigger the full check-in assembly or
        # history wipe. These are questions ABOUT the state — the LLM answers
        # them using LOCKED CoS STATE + conversation history (the prior briefing).
        _is_qualified_status = False
        try:
            from apps.ai.deterministic_router import is_qualified_status_query
            _is_qualified_status = is_qualified_status_query(message_lower)
        except ImportError:
            pass
        if _is_qualified_status:
            is_requesting_checkin = False
            is_asking_about_tasks = False
            logger.info(
                "QUALIFIED_STATUS user=%s msg=%r — bypassing checkin assembly, "
                "preserving history for LLM direct answer",
                self.user.id, message[:80],
            )

        if is_asking_about_tasks or is_asking_for_analysis or is_requesting_checkin:
            # Drop ALL conversation history for check-in/task queries.
            # The system prompt injects AUTHORITATIVE current-state data
            # (tasks, calendar, meds, goals, prayers). Conversation history
            # — even just a few messages — contaminates the response with
            # stale task references the LLM parrots despite prompt guards.
            # Check-in responses are purely data-driven; zero history needed.
            logger.info(
                "CHECKIN_DETECT user=%s tasks=%s analysis=%s checkin=%s msg=%r",
                self.user.id, is_asking_about_tasks, is_asking_for_analysis,
                is_requesting_checkin, message[:80],
            )
            history = conversation.messages.none()

            # User is asking about tasks or wants analysis - include full state context
            # ── PROTECTED: entire check-in data assembly ────────────────
            # Any crash here used to propagate to the outer except (line 5797)
            # and silently return a fallback string. Now we catch, log the
            # real exception, and let the LLM be called with whatever system
            # prompt was built up to this point.
            _checkin_assembly_ok = True
            try:
                state = self.assess_current_state()
                time_context = self._get_time_context()
                tasks = state.get('tasks', {})
                # due_today = priority='now' count, which ALREADY includes
                # overdue tasks.  Adding overdue again double-counts them.
                remaining_tasks = tasks.get('due_today', 0)
            except Exception as _state_err:
                logger.error(
                    "CHECKIN_STATE_CRASH user=%s — assess_current_state or "
                    "_get_time_context failed: %s",
                    self.user.id, _state_err, exc_info=True,
                )
                _checkin_assembly_ok = False
                state = {}
                time_context = {'hours_remaining': 'unknown'}
                tasks = {}
                remaining_tasks = 0

            if is_requesting_checkin:
                # ── DETERMINISTIC CHECK-IN (no LLM) ──────────────────
                # The deterministic router normally catches check-ins
                # terminally. This fallback fires only when the router's
                # renderer threw an exception. Try the unified structured
                # output one more time — if it succeeds, return directly
                # without LLM involvement.
                try:
                    from apps.ai.beth_checkin_renderer import (
                        build_cos_structured_output,
                    )
                    _cos_output = build_cos_structured_output(self.user)
                    _deterministic_text = _cos_output.get('rendered_text', '')
                    if _deterministic_text and len(_deterministic_text) > 20:
                        logger.info(
                            "CHECKIN_FALLBACK_DETERMINISTIC user=%s — "
                            "structured output succeeded on retry",
                            self.user.id,
                        )
                        return _deterministic_text
                except Exception as _cos_err:
                    logger.error(
                        "CHECKIN_FALLBACK_STRUCTURED user=%s — structured "
                        "output also failed: %s. Using safe fallback.",
                        self.user.id, _cos_err, exc_info=True,
                    )
                    from apps.ai.beth_checkin_renderer import _SAFE_FALLBACK
                    return _SAFE_FALLBACK
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
Only reference tasks and items that appear in the current data above — ignore any tasks mentioned earlier in the conversation that are no longer listed.
NEVER give generic scheduling advice or life-coach templates. You have their ACTUAL data — use it.
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
        if not _skip_memory:
            try:
                from apps.ai.memory_service import get_memory_context_block
                memory_block = get_memory_context_block(self.user, message)
                if memory_block:
                    system_prompt += memory_block
            except Exception as mem_err:
                logger.debug("Memory retrieval skipped: %s", mem_err)

        # Phase 3b: Inject relevant corrections (higher priority than memories)
        try:
            from apps.ai.correction_service import get_correction_context_block
            correction_block = get_correction_context_block(self.user, message)
            if correction_block:
                system_prompt += correction_block
        except Exception as corr_err:
            logger.debug("Correction retrieval skipped: %s", corr_err)

        # Phase 3c: Inject detected behavioral patterns
        try:
            from apps.ai.pattern_detector import get_pattern_context_block
            pattern_block = get_pattern_context_block(self.user)
            if pattern_block:
                system_prompt += pattern_block
        except Exception as pat_err:
            logger.debug("Pattern injection skipped: %s", pat_err)

        # Phase 3d: Inject learned response preferences
        try:
            from apps.ai.response_optimizer import get_preference_prompt_block
            pref_block = get_preference_prompt_block(self.user)
            if pref_block:
                system_prompt += "\n" + pref_block
        except Exception as pref_err:
            logger.debug("Response preference injection skipped: %s", pref_err)

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
                            f"- The user is currently reading: {refs}\n"
                            f"- CRITICAL: You ALREADY KNOW which scripture the user is reading "
                            f"(listed above). When they say 'this scripture', 'break it down', "
                            f"'help me understand', etc., they mean {refs}. "
                            f"You MUST answer using your knowledge of {refs}. "
                            f"NEVER ask the user to share or provide the scripture — "
                            f"you know exactly what they are reading.\n"
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

                # Resolve domain hint for grounding
                _domain_hint = ''
                try:
                    from apps.ai.intent_service import IntentService
                    _domain_hint = IntentService._resolve_domain_hint(page_context)
                except Exception:
                    pass

                system_prompt += f"""
PAGE CONTEXT (where the user is currently viewing):
{chr(10).join('- ' + p for p in context_parts) if context_parts else ''}
{content_description}
{context_priority_instruction}
When the user asks about "this page", "this scripture", "this entry", etc., they are referring to the content above.
Use this context to provide relevant, contextual help. For scripture questions, explain the passage and its meaning.
{"DOMAIN GROUNDING: Active domain: " + _domain_hint + ". When the user references visible entities using pronouns or deictic language ('those', 'them', 'the ones listed', 'still pending', 'mark them'), resolve against the current page domain first. Only cross domains if the user explicitly names a different domain." if _domain_hint else ""}
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

        # If personal data was found, use the enhanced prompt with grounded data
        if personal_data_result['is_personal_query'] and personal_data_result['has_data']:
            system_prompt = personal_data_result['system_prompt']
            logger.debug(
                f"Personal data context injected for data types: {personal_data_result['data_types']}"
            )

        # If personal data was queried but NOT found, inject structured context
        # so CoS can respond intelligently instead of returning a template string.
        # The LLM sees the gap and can use secondary context (priorities, forecasts,
        # intelligence summaries, navigation links) to provide a helpful response.
        elif personal_data_result.get('needs_clarification'):
            system_prompt += _build_missing_data_context(personal_data_result)
            logger.info(
                f"Missing-data context injected for {personal_data_result.get('awaiting_data_type')}, "
                f"CoS will generate response"
            )

        # Check if this is a web search query (weather, news, etc.)
        # Handle these with web search before falling back to general AI.
        # v5: Skip web search if already identified as a personal data query —
        # those need the full CoS pipeline, not a generic LLM response.
        from apps.ai.web_search_service import needs_web_search, search_web, get_user_location

        _skip_web_search = (
            personal_data_result.get('is_personal_query')
            or personal_data_result.get('needs_clarification')
        )
        if not _skip_web_search and needs_web_search(message):
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

        # Build the user prompt, noting if image(s) are attached
        _img_count = len(all_images) if all_images else (1 if image_data and image_mime_type else 0)
        _vision_instruction = (
            "You CAN see and analyze images — you have full vision capability. "
            "Read ALL visible text, numbers, labels, and data from the image(s). "
            "If it shows health metrics (weight, BMI, body fat %, muscle mass, etc.), "
            "report the specific numbers you see and provide observations: trends, "
            "changes, what's improving, what needs attention. Be specific with data — "
            "e.g., 'Your weight is 285 lbs, down from 295 five days ago — that's a 3.4% decrease.' "
            "This is data reading and observation, not medical advice."
        )
        # Override vision instruction if PIE health analysis succeeded
        # (_health_analysis was set earlier in the method, before system prompt)
        if _health_analysis:
            _vision_instruction = (
                "You have ALREADY analyzed this health screenshot "
                "via the Pattern Intelligence Engine. Use the "
                "structured analysis injected into your system "
                "prompt under HEALTH SCREENSHOT ANALYSIS. "
                "Structure your response as:\n"
                "1. **Summary Insight** — one sentence key finding\n"
                "2. **Key Observations** — 2-3 data-driven points\n"
                "3. **What This Means** — connect to this person's life/goals\n"
                "4. **Recommendation** — one clear actionable step\n\n"
                "RULES: Do NOT just repeat numbers from the image. "
                "Do NOT give generic advice. Connect every observation "
                "to what it means for THIS person. You may reference "
                "numbers from the image to support your analysis."
            )

        if _img_count > 1:
            image_note = f"\n\n[The user has attached {_img_count} images. {_vision_instruction} Analyze each image and synthesize insights across all of them.]"
        elif _img_count == 1:
            image_note = f"\n\n[The user has attached an image. {_vision_instruction}]"
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

        # Health intelligence status: strict enum-only format
        _hi_keywords = [
            'fat loss phase', 'plateau risk', 'muscle preservation',
            'health intelligence status', 'body comp status',
        ]
        _is_health_intel_query = any(kw in message.lower() for kw in _hi_keywords)
        if _is_health_intel_query and response_mode == 'brief':
            # OVERRIDE: Replace the entire rules block with strict format.
            # This overrides "be conversational" and all other instructions.
            rules_block = (
                "- ABSOLUTE OVERRIDE — IGNORE ALL OTHER FORMATTING INSTRUCTIONS.\n"
                "- The user asked for health intelligence status and wants it SHORT.\n"
                "- Output EXACTLY these 4 lines and NOTHING ELSE:\n"
                "  Fat loss phase: <ENUM>\n"
                "  Plateau risk: <ENUM>\n"
                "  Muscle preservation: <ENUM>\n"
                "  Last updated: <date/time>\n"
                "- For each field, copy the EXACT value from HEALTH INTELLIGENCE STATUS in your context.\n"
                "- Valid fat_loss_phase enums: RAPID_INITIAL_LOSS, STABLE_FAT_LOSS, RECOMPOSITION, PLATEAU, REBOUND_RISK\n"
                "- Valid plateau_risk_label enums: LOW, RISING, HIGH\n"
                "- Valid muscle_preservation_status enums: HIGH_QUALITY, MODERATE_QUALITY, MUSCLE_RISK\n"
                "- If a value shows 'UNKNOWN (awaiting data)' in your context, output that exact string.\n"
                "- Do NOT paraphrase. Do NOT say 'rising' — say 'RISING'. Do NOT say 'stable' — say the enum.\n"
                "- Do NOT add schedule, sleep, calendar, suggestions, greetings, or any other content.\n"
                "- Do NOT be conversational. Just the 4 lines."
            )
        elif _is_health_intel_query:
            rules_block += (
                "\n- HEALTH INTELLIGENCE FORMAT: The user is asking about health "
                "intelligence status fields. Respond using ONLY the enum values from "
                "the HEALTH INTELLIGENCE STATUS block in your context. "
                "Copy the values EXACTLY as shown — do NOT paraphrase. "
                "Say 'RISING' not 'rising', 'HIGH_QUALITY' not 'good' or 'stable'. "
                "If a value is 'UNKNOWN (awaiting data)', say exactly that. "
                "Do NOT add unrelated content (schedule, sleep, calendar)."
            )

        # Qualified status query override: "other than X, anything left?",
        # "am I done?", "anything else?" — strict direct-answer mode.
        # Same pattern as health intel override: replace the rules block
        # with a dominant, specific instruction set.
        if _is_qualified_status:
            response_mode = 'brief'  # Force brief even for verbose phrasing
            rules_block = (
                "- DIRECT ANSWER MODE — the user asked a specific question about "
                "their remaining items. Answer ONLY what was asked.\n"
                "- Respond in 1-2 sentences MAXIMUM. No lists, no sections, no headers.\n"
                "- Do NOT summarize the day. Do NOT list completed items.\n"
                "- Do NOT repeat information from the prior briefing.\n"
                "- Do NOT add motivational commentary or coaching.\n"
                "- If they asked about exclusions (\"other than X\"), answer relative to "
                "that filter using the LOCKED CoS STATE.\n"
                "- If they asked yes/no (\"am I done?\"), answer yes or no with a count.\n"
                "- Examples of CORRECT responses:\n"
                "  Q: 'other than nutrition, anything left?' → 'No — just nutrition left.'\n"
                "  Q: 'am I done?' → 'Not yet — 1 item left: nutrition.'\n"
                "  Q: 'anything else?' → 'No, you're done for today.'"
            )

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
2. Is the user sharing a feeling, expressing gratitude, being vulnerable, or making a personal reflection? If YES — respond to the EMOTION first. Acknowledge it warmly. Do NOT re-explain or re-summarize content you already gave them.
3. If they ARE asking a question — what are they most likely asking about? The page content, their data, or a previous conversation topic?
4. What data or context do I have that's directly relevant?
4b. Check intelligence signals and momentum: What do the SIGNAL INTERPRETATION and MOMENTUM INTERPRETATION sections say about the user's domains? Lead with signal-level language (e.g., "Faith signals remain strong this week" or "Health momentum dipped slightly"). Reference specific tasks only as evidence supporting the signal narrative — never list tasks without signal framing.
5. Check the schedule/calendar data: Is anything tagged [SOON] (starting within ~15 min), [NOW] (happening right now), or [MISSED] (was supposed to happen but wasn't completed)? Are there any PENDING ACTIVITY PROMPTS due? If YES — weave a brief, natural mention into your response (e.g., "By the way, your medication is due in about 20 minutes" or "I also noticed your 5:15 prayer time passed — want to fit that in?"). Don't lecture — just a friendly heads-up.
6. What should I NOT talk about? (avoid mixing unrelated topics — don't mention routines when they're asking about scripture, don't discuss scripture when they're asking about tasks, and don't repeat an explanation when they're expressing how they feel about it)
7. PROACTIVE OPPORTUNITY: Based on the user's data, goals, and current context, is there ONE actionable suggestion I can weave in naturally? Examples: a streak at risk, a goal they haven't tracked recently, a health metric trending in a direction worth noting, or a next step that follows logically from what they just accomplished. Keep it brief and relevant — one sentence max, framed as a friendly nudge, not a lecture. Only suggest if it's genuinely useful right now; skip this step if nothing stands out.
Then give your response."""

        # =============================================================
        # Phase 4b: Reading Plan Scripture Context Enrichment
        # When the user is on a reading plan page, look up the scripture
        # references SERVER-SIDE and inject them directly into the user
        # prompt. This is more reliable than JavaScript DOM extraction
        # and ensures the AI always knows what scripture is being read.
        # =============================================================
        scripture_context_block = ""
        if page_context:
            _pc = page_context.get('page_content') or {}
            _pc_type = _pc.get('type', '')
            _pc_url = page_context.get('url', '')

            if _pc_type == 'reading_plan_progress' or (
                not _pc_type and _pc_url
                and '/faith/reading-plans/progress/' in _pc_url
            ):
                # Get references from client-side context first
                scripture_refs = _pc.get('scriptures', [])
                scripture_text = _pc.get('scripture_text', '')

                # Server-side fallback: look up from database if JS missed them
                if not scripture_refs:
                    try:
                        import re as _re_url
                        _url_match = _re_url.search(
                            r'/faith/reading-plans/progress/(\d+)', _pc_url
                        )
                        if _url_match:
                            _plan_id = int(_url_match.group(1))
                            from apps.faith.models import UserReadingPlan
                            _user_plan = UserReadingPlan.objects.filter(
                                pk=_plan_id, user=self.user,
                            ).select_related('template').first()
                            if _user_plan:
                                from apps.faith.models import ReadingPlanDay
                                _plan_day = ReadingPlanDay.objects.filter(
                                    plan=_user_plan.template,
                                    day_number=_user_plan.current_day,
                                ).first()
                                if _plan_day:
                                    scripture_refs = _plan_day.scripture_references or []
                                    # Also try to get pre-loaded text
                                    if not scripture_text and _plan_day.scripture_content:
                                        _texts = []
                                        for sc in _plan_day.scripture_content:
                                            if isinstance(sc, dict) and sc.get('text'):
                                                _texts.append(sc['text'][:1500])
                                        if _texts:
                                            scripture_text = '\n\n'.join(_texts)
                                    logger.info(
                                        "Server-side reading plan lookup: plan=%s day=%s refs=%s",
                                        _plan_id, _user_plan.current_day, scripture_refs,
                                    )
                    except Exception as _rp_err:
                        logger.warning(
                            "Reading plan server-side lookup failed: %s", _rp_err
                        )

                # Build context block injected directly into user prompt
                if scripture_refs:
                    refs_str = ', '.join(scripture_refs)
                    scripture_context_block = (
                        f"\n[SCRIPTURE CONTEXT: The user is currently on their "
                        f"Bible reading plan reading {refs_str}. "
                        f"When they say 'this scripture', 'break it down', "
                        f"'help me understand', 'it', or 'this', they mean "
                        f"{refs_str}. Answer about {refs_str} directly.]"
                    )
                    if scripture_text:
                        # Include actual text (truncated for token budget)
                        scripture_context_block += (
                            f"\n[SCRIPTURE TEXT:\n"
                            f"{scripture_text[:3000]}]"
                        )

        # For strict health intel + brief, suppress conversational instructions
        if _is_health_intel_query and response_mode == 'brief':
            _conversational_rules = ""
            _reasoning_block = ""  # Skip chain-of-thought too — just output the enums
        elif _is_qualified_status:
            # Direct answer mode: suppress conversational filler and
            # chain-of-thought reasoning. The answer is 1-2 sentences.
            _conversational_rules = ""
            _reasoning_block = ""
        else:
            _conversational_rules = (
                f"{style_nudge}- Be conversational and natural — speak like someone who knows this person\n"
                "- If they're sharing a feeling, expressing gratitude, or being vulnerable — respond to THAT. "
                "Don't re-explain what you just told them. A simple \"I'm glad that helped\" or "
                "\"that's completely normal\" is better than repeating content.\n"
                "- If following up on previous conversation, build on it naturally"
            )
            _reasoning_block = reasoning_instruction

        user_prompt = f"""{"The user's name is " + user_name + ". " if user_name else ""}{message}{image_note}{scripture_context_block}
{topic_threading_hint}
{_reasoning_block}

Rules for this response:
- Answer directly. Lead with the data when you have it.
{rules_block}
{_conversational_rules}"""

        # Dynamic token limit keyed to response mode
        # Larger budgets allow deeper, more thoughtful responses
        mode_tokens = {'brief': 400, 'adaptive': 800, 'deep': 1200}
        max_tokens = mode_tokens.get(response_mode, 800)

        # Health intel + brief: tiny budget constrains the LLM to just the enums
        if _is_health_intel_query and response_mode == 'brief':
            max_tokens = 100

        # Qualified status: 1-2 sentences = ~30-50 tokens. Cap at 150 for safety.
        if _is_qualified_status:
            max_tokens = 150

        # Scripture breakdowns need more tokens for thorough analysis
        if scripture_context_block and any(
            w in message.lower() for w in [
                'break it down', 'break down', 'explain', 'understand',
                'what does', 'teach me', 'walk me through',
            ]
        ):
            max_tokens = max(max_tokens, 1200)

        # Multi-image analysis needs more tokens for thorough per-image response
        if _img_count > 1:
            max_tokens = max(max_tokens, 1200)

        # Temperature: warm enough for natural conversation, lower for data accuracy
        has_personal_data = personal_data_result.get('has_data', False)
        temperature = 0.3 if (has_personal_data or is_analysis or is_asking_about_tasks) else 0.5

        # =====================================================================
        # Context-only mode: return assembled prompt for streaming callers.
        # Avoids duplicating the 1200+ lines of prompt assembly above.
        # =====================================================================
        if _return_context_only:
            return {
                'system_prompt': system_prompt,
                'user_prompt': user_prompt,
                'max_tokens': max_tokens,
                'temperature': temperature,
                'conversation_history': conversation_history,
            }

        try:
            import time as _t_llm
            _t_llm_start = _t_llm.monotonic()
            if _ltrace:
                _ltrace.start('LLM_REQUEST')
            from django.conf import settings as django_settings
            _cos_model = django_settings.COS_MODEL
            if _ltrace:
                _ltrace.set_meta('model', _cos_model)
            _llm_response = ai_service._call_api(
                system_prompt,
                user_prompt,
                max_tokens=max_tokens,
                image_data=image_data,
                image_mime_type=image_mime_type,
                temperature=temperature,
                endpoint='cos_chat',
                user=self.user,
                conversation_history=conversation_history,
                all_images=all_images,
                model=_cos_model,
            )
            if _ltrace:
                _ltrace.end('LLM_REQUEST')
                # Extract token usage from the AI service's last response
                try:
                    _last_usage = getattr(ai_service, '_last_usage', None)
                    if _last_usage:
                        _ltrace.set_meta('prompt_tokens', _last_usage.get('prompt_tokens', 0))
                        _ltrace.set_meta('completion_tokens', _last_usage.get('completion_tokens', 0))
                except Exception:
                    pass
            _used_fallback = not _llm_response
            response = _llm_response or self._get_fallback_response(message)
            logger.warning("COS LLM call took %.1f ms", (_t_llm.monotonic() - _t_llm_start) * 1000)

            # ── Phase 4.5: Hard Response Validator ───────────────────
            # Reject weak / generic / raw-data-only / trust-missing LLM
            # output and rebuild deterministically from SAE state +
            # trust. This is enforcement, not suggestion — weak answers
            # are blocked in code.
            if _llm_response and not _used_fallback:
                try:
                    from apps.ai.deterministic_router import (
                        validate_response,
                        regenerate_response_deterministic,
                        _infer_domain,
                        _is_decision_query,
                        _build_focus_query_response,
                    )
                    # Infer the domain the user was asking about. The
                    # validator is stricter when a domain is identified.
                    _msg_lower = (message or '').lower()
                    _detected_domain = _infer_domain(_msg_lower)
                    # Phase 8: decision queries trigger Rule 0 (action-first
                    # structural enforcement) inside validate_response.
                    _is_decision = _is_decision_query(_msg_lower)
                    _is_valid, _reason = validate_response(
                        response, user=self.user,
                        query_domain=_detected_domain,
                        is_decision_query=_is_decision,
                    )
                    if not _is_valid:
                        logger.warning(
                            "PHASE_4_5_VALIDATOR_REJECT user=%s domain=%s "
                            "is_decision=%s reason=%s preview=%s",
                            self.user.id, _detected_domain, _is_decision,
                            _reason, (response or '')[:120],
                        )
                        # Phase 8: for decision queries, skip the
                        # domain rebuilder and jump straight to the
                        # never-None focus handler. It always produces
                        # a valid Action-First response.
                        if _is_decision:
                            try:
                                _rebuilt = _build_focus_query_response(
                                    self.user,
                                )
                            except Exception:
                                _rebuilt = None
                        else:
                            _rebuilt = regenerate_response_deterministic(
                                self.user, _detected_domain,
                            )
                        if _rebuilt:
                            logger.info(
                                "PHASE_4_5_VALIDATOR_REBUILD user=%s domain=%s "
                                "is_decision=%s new_len=%d",
                                self.user.id, _detected_domain,
                                _is_decision, len(_rebuilt),
                            )
                            response = _rebuilt
                        else:
                            logger.info(
                                "PHASE_4_5_VALIDATOR_KEPT user=%s domain=%s "
                                "— no deterministic rebuilder for domain, "
                                "keeping original response",
                                self.user.id, _detected_domain,
                            )
                except Exception as e:
                    # Validator must NEVER break the chat. Fall through
                    # with the original LLM response on any error.
                    logger.warning(
                        "PHASE_4_5_VALIDATOR_ERROR user=%s: %s",
                        self.user.id, e,
                    )

            # ── Defensive: Log when briefing context is wasted ──────────
            # If a briefing was injected but the LLM returned nothing (or
            # a weak generic response), log prominently so we can detect
            # silent degradation patterns in production.
            if briefing and _used_fallback:
                logger.error(
                    "BRIEFING_LLM_FALLBACK user=%s — Executive briefing was "
                    "injected but LLM returned empty/null. The user will "
                    "receive a generic fallback instead of a morning briefing. "
                    "Briefing NOT marked as delivered; will retry on next message.",
                    self.user.id,
                )
            elif briefing and not _defer_briefing_marking:
                # Check for weak/generic responses that ignore briefing data
                _weak_indicators = [
                    "I'm here to help",
                    "I'm here to assist",
                    "How can I help",
                    "What can I help",
                    "What needs your attention",
                    "What do you need to get done",
                    "What's the priority right now",
                ]
                # Only flag as weak if the response is SHORT. Long responses
                # (200+ chars) contain real data even if they include a
                # common closing phrase — the executive briefing instruction
                # explicitly asks the LLM to end with an inviting question.
                _is_weak = len(response or '') < 200 and any(
                    ind in (response or '') for ind in _weak_indicators
                )
                if _is_weak:
                    logger.warning(
                        "BRIEFING_WEAK_RESPONSE user=%s len=%s — LLM returned "
                        "a generic response despite executive briefing injection. "
                        "Briefing NOT marked as delivered; will retry on next message. "
                        "Response preview: %s",
                        self.user.id, len(response or ''),
                        (response or '')[:120],
                    )
                    # Don't mark — let the next message get a fresh briefing attempt
                else:
                    # Good response with briefing data — mark as delivered
                    try:
                        from apps.ai.executive_briefing import mark_briefing_delivered
                        mark_briefing_delivered(conversation)
                    except Exception:
                        pass  # Non-fatal — briefing was still delivered

            # =============================================================
            # STRICT_HEALTH_STATUS: Deterministic 4-line enforcement
            # When strict mode is active, DISCARD LLM output entirely
            # and build the response from CoS context. This is the only
            # way to guarantee no appended schedule/sleep/coaching.
            # =============================================================
            if _is_health_intel_query and response_mode == 'brief':
                try:
                    from apps.ai.validators.health_response_validator import (
                        enforce_strict_health_status,
                    )
                    return enforce_strict_health_status(cos_context)
                except Exception as _shi_err:
                    logger.warning(
                        "Strict health status enforcement failed, "
                        "using LLM response: %s", _shi_err,
                    )

            # =============================================================
            # Qualified status failsafe: truncate verbose LLM responses.
            # Despite tight token budget (150) and explicit instructions,
            # the LLM may occasionally expand. Trim to first 2 sentences
            # as a hard ceiling. This mirrors the health intel enforcement
            # pattern — deterministic post-processing beats prompt-only.
            # =============================================================
            if _is_qualified_status and response:
                _qs_response = response.strip()
                # Split on sentence boundaries (. ! ?)
                import re as _qs_re
                _qs_sentences = _qs_re.split(r'(?<=[.!?])\s+', _qs_response)
                if len(_qs_sentences) > 3:
                    _qs_trimmed = ' '.join(_qs_sentences[:2])
                    logger.info(
                        "QUALIFIED_STATUS_TRIM user=%s sentences=%d→2 "
                        "original=%r trimmed=%r",
                        self.user.id, len(_qs_sentences),
                        _qs_response[:120], _qs_trimmed[:120],
                    )
                    response = _qs_trimmed

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

            # =============================================================
            # Phase 5: Signal Prioritization Guardrail
            # Check if the response acknowledges the dominant concern from
            # CoSSituationState. If not, log COS_PRIORITY_MISALIGNMENT.
            # This is observe-only — it doesn't block the response.
            # =============================================================
            if response and not _used_fallback:
                self._check_priority_alignment(response, cos_context)

            return response
        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return self._get_fallback_response(message)

    # -----------------------------------------------------------------
    # Fast context builder for streaming TTFB optimization
    # -----------------------------------------------------------------

    def _build_fast_context(self, message, conversation,
                            page_context=None, cos_context_cache=None,
                            route_result=None):
        """
        Build minimal LLM context using ONLY cached data — no rebuilds.

        Returns the same dict shape as _generate_response(_return_context_only=True)
        or None if the fast path is not viable (e.g. calibration active).

        This method must complete in <200ms. It reads:
        - Base system prompt (~5ms)
        - Governance instructions (~50-100ms)
        - Learned user profile (~50-100ms)
        - Cached CoS context (strict cache-only, never rebuild)
        - Conversation memory / rolling summary (~5ms)
        - Conversation history (~20-50ms)
        - Response mode classification (~5ms)
        """
        # --- a) Calibration gate: if active, return None → caller uses full path
        try:
            from apps.core.blueprint.cos_governance import get_calibration_state
            cal = get_calibration_state(self.user)
            if cal and cal.get('active') and not cal.get('paused'):
                return None  # Calibration requires full pipeline
        except Exception:
            pass  # If check fails, proceed with fast path

        # --- b) Base system prompt (~5ms)
        system_prompt = self._build_system_prompt(include_time_context=True)

        # --- c) Governance instructions (~50-100ms)
        try:
            from apps.core.blueprint.cos_governance import build_governance_instructions
            gov = build_governance_instructions(self.user)
            if gov:
                system_prompt = gov + "\n\n" + system_prompt
        except Exception:
            pass

        # --- d) Learned user profile (~50-100ms)
        try:
            from apps.core.ai_learning.learning_extractor import get_profile_system_prompt
            profile = get_profile_system_prompt(self.user)
            if profile:
                system_prompt = profile + "\n\n" + system_prompt
        except Exception:
            pass

        # --- e) STRICT cache-only CoS context — NEVER rebuild
        from apps.ai.readiness_cache import get_cached_cos_context

        cos_ctx = cos_context_cache or get_cached_cos_context(self.user)

        if cos_ctx:
            try:
                from apps.core.ai_orchestrator.cos_context import format_cos_system_injection
                # Inject affirmed completions into context for system prompt
                try:
                    from .affirmation_detector import get_affirmed_completions
                    _affirmed = get_affirmed_completions(conversation)
                    if _affirmed:
                        cos_ctx['affirmed_completions'] = _affirmed
                except Exception:
                    pass  # Affirmation context must never break streaming
                # Inject recent event context for follow-up continuity
                try:
                    from apps.core.ai_events.followup import get_event_context
                    _rec_evt_s = get_event_context(conversation) if conversation else None
                    if _rec_evt_s:
                        cos_ctx['recent_event_context'] = _rec_evt_s
                except Exception:
                    pass  # Non-critical
                cos_injection = format_cos_system_injection(cos_ctx, user_message=message)
                if cos_injection:
                    system_prompt += "\n\n" + cos_injection
                    # ── CoS prompt debug logging (stream fast path) ──
                    _tail = cos_injection[-600:] if len(cos_injection) > 600 else cos_injection
                    _has_anchor = 'FINAL EXECUTION STATUS' in cos_injection
                    logger.info(
                        "[CoS PROMPT DEBUG] user=%s path=stream_fast "
                        "len=%d has_truth_anchor=%s "
                        "context_builder=cos_context.format_cos_system_injection "
                        "last_500_chars=\n%s",
                        self.user.id, len(cos_injection),
                        _has_anchor, _tail,
                    )
                    if not _has_anchor:
                        logger.error(
                            "COS_TRUTH_ANCHOR_MISSING user=%s path=stream_fast — "
                            "FINAL TRUTH ANCHOR not found in prompt!",
                            self.user.id,
                        )
            except Exception:
                pass
        else:
            logger.info(
                "FAST_CTX_NO_COS_CACHE user=%s — skipping CoS injection "
                "(will warm in background)",
                self.user.id,
            )

        # --- f) Rolling summary / conversation memory (~5ms)
        try:
            from apps.ai.executive_briefing import get_conversation_memory
            memory = get_conversation_memory(conversation)
            if memory:
                system_prompt += "\n\n" + memory
        except Exception:
            pass

        # --- f2) Executive briefing (first-of-day or gap re-entry)
        _fast_briefing_built = False
        try:
            from apps.ai.executive_briefing import build_executive_briefing
            briefing = build_executive_briefing(self.user, conversation)
            if briefing:
                system_prompt += "\n\n" + briefing
                _fast_briefing_built = True
        except Exception:
            pass

        # --- f3) Phase 7.1: Semantic memory + correction retrieval (streaming)
        # Memory gating: skip embedding lookup for deterministic data routes.
        _skip_memory_fast = False
        if route_result:
            try:
                from apps.ai.deterministic_router import should_skip_semantic_memory
                _skip_memory_fast = should_skip_semantic_memory(route_result)
            except Exception:
                pass
        try:
            from apps.ai.memory_service import retrieve_relevant_memories
            relevant_memories = (
                retrieve_relevant_memories(
                    self.user, message, top_k=3, exclude_minutes=30,
                ) if not _skip_memory_fast else []
            )
            if relevant_memories:
                mem_lines = [
                    "--- RELEVANT PAST CONVERSATIONS ---",
                    "You've discussed similar topics before with this user:",
                ]
                for mem in relevant_memories:
                    days_ago = (timezone.now() - mem['created_at']).days
                    if days_ago == 0:
                        time_label = "Earlier today"
                    elif days_ago == 1:
                        time_label = "Yesterday"
                    elif days_ago < 7:
                        time_label = f"{days_ago} days ago"
                    else:
                        time_label = mem['created_at'].strftime('%b %d')
                    corrected = " [CORRECTED]" if mem.get('was_corrected') else ""
                    mem_lines.append(
                        f"  [{time_label}]{corrected} User asked: "
                        f"\"{mem['user_message'][:150]}\" → "
                        f"You said: \"{mem['assistant_summary'][:150]}\""
                    )
                mem_lines.append(
                    "Reference these naturally if relevant. "
                    "Do NOT repeat previous mistakes marked [CORRECTED]."
                )
                mem_lines.append("--- END PAST CONVERSATIONS ---")
                system_prompt += "\n\n" + "\n".join(mem_lines)
        except ImportError:
            pass
        except Exception:
            pass

        try:
            from apps.ai.correction_service import get_correction_context_block
            correction_block = get_correction_context_block(self.user, message)
            if correction_block:
                system_prompt += "\n\n" + correction_block
        except ImportError:
            pass
        except Exception:
            pass

        # --- f4) Pending CoS prompts (proactive nudging)
        try:
            from apps.cos.services.prompt_service import CosPromptService
            prompt_injection = CosPromptService.get_pending_prompt_injection(self.user)
            if prompt_injection:
                system_prompt += "\n\n" + prompt_injection
        except Exception:
            pass

        # --- g) Conversation history (~20-50ms)
        conversation_history = None
        try:
            history = conversation.messages.order_by('-created_at')[:20]
            from apps.ai.conversation.message_builder import build_messages_from_history
            conversation_history = build_messages_from_history(history, message)
        except Exception:
            pass

        # --- h) Response mode + user prompt (~5ms)
        response_mode = self._classify_response_mode(message, False, False)

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

        style_pref = getattr(self.prefs, 'cos_response_style', 'balanced')
        style_nudge = ''
        if style_pref == 'concise':
            style_nudge = '- Prefer the shortest accurate answer possible.\n'
        elif style_pref == 'strategic':
            style_nudge = '- Include strategic framing and next-step suggestions.\n'
        elif style_pref == 'deep_dive':
            style_nudge = '- Provide comprehensive analysis when data supports it.\n'

        reasoning_instruction = """
Before responding, silently reason through these steps (do NOT include this reasoning in your response):
1. What is the user's current context? (page they're viewing, time of day, recent session activity)
2. Is the user sharing a feeling, expressing gratitude, being vulnerable, or making a personal reflection? If YES — respond to the EMOTION first. Acknowledge it warmly. Do NOT re-explain or re-summarize content you already gave them.
3. If they ARE asking a question — what are they most likely asking about? The page content, their data, or a previous conversation topic?
4. What data or context do I have that's directly relevant?
4b. Check intelligence signals and momentum: What do the SIGNAL INTERPRETATION and MOMENTUM INTERPRETATION sections say about the user's domains? Lead with signal-level language (e.g., "Faith signals remain strong this week" or "Health momentum dipped slightly"). Reference specific tasks only as evidence supporting the signal narrative — never list tasks without signal framing.
5. Check the schedule/calendar data: Is anything tagged [SOON] (starting within ~15 min), [NOW] (happening right now), or [MISSED] (was supposed to happen but wasn't completed)? Are there any PENDING ACTIVITY PROMPTS due? If YES — weave a brief, natural mention into your response (e.g., "By the way, your medication is due in about 20 minutes" or "I also noticed your 5:15 prayer time passed — want to fit that in?"). Don't lecture — just a friendly heads-up.
6. What should I NOT talk about? (avoid mixing unrelated topics — don't mention routines when they're asking about scripture, don't discuss scripture when they're asking about tasks, and don't repeat an explanation when they're expressing how they feel about it)
7. PROACTIVE OPPORTUNITY: Based on the user's data, goals, and current context, is there ONE actionable suggestion I can weave in naturally? Examples: a streak at risk, a goal they haven't tracked recently, a health metric trending in a direction worth noting, or a next step that follows logically from what they just accomplished. Keep it brief and relevant — one sentence max, framed as a friendly nudge, not a lecture. Only suggest if it's genuinely useful right now; skip this step if nothing stands out.
Then give your response."""

        # --- h2) Page context injection (reading plan scripture, etc.)
        # Must also run on fast path — otherwise streaming misses page context entirely.
        scripture_context_block = ""
        if page_context:
            _pc = page_context.get('page_content') or {}
            _pc_type = _pc.get('type', '')
            _pc_url = page_context.get('url', '')

            if _pc_type == 'reading_plan_progress' or (
                not _pc_type and _pc_url
                and '/faith/reading-plans/progress/' in _pc_url
            ):
                scripture_refs = _pc.get('scriptures', [])
                scripture_text = _pc.get('scripture_text', '')

                # Server-side fallback: look up from database if JS missed them
                if not scripture_refs:
                    try:
                        import re as _re_url
                        _url_match = _re_url.search(
                            r'/faith/reading-plans/progress/(\d+)', _pc_url
                        )
                        if _url_match:
                            _plan_id = int(_url_match.group(1))
                            from apps.faith.models import UserReadingPlan, ReadingPlanDay
                            _user_plan = UserReadingPlan.objects.filter(
                                pk=_plan_id, user=self.user,
                            ).select_related('template').first()
                            if _user_plan:
                                _plan_day = ReadingPlanDay.objects.filter(
                                    plan=_user_plan.template,
                                    day_number=_user_plan.current_day,
                                ).first()
                                if _plan_day:
                                    scripture_refs = _plan_day.scripture_references or []
                                    if not scripture_text and _plan_day.scripture_content:
                                        _texts = []
                                        for sc in _plan_day.scripture_content:
                                            if isinstance(sc, dict) and sc.get('text'):
                                                _texts.append(sc['text'][:1500])
                                        if _texts:
                                            scripture_text = '\n\n'.join(_texts)
                    except Exception as _rp_err:
                        logger.warning("Fast-path reading plan lookup failed: %s", _rp_err)

                if scripture_refs:
                    refs_str = ', '.join(scripture_refs)
                    scripture_context_block = (
                        f"\n[SCRIPTURE CONTEXT: The user is currently on their "
                        f"Bible reading plan reading {refs_str}. "
                        f"When they say 'this scripture', 'break it down', "
                        f"'help me understand', 'it', or 'this', they mean "
                        f"{refs_str}. Answer about {refs_str} directly.]"
                    )
                    if scripture_text:
                        scripture_context_block += (
                            f"\n[SCRIPTURE TEXT:\n{scripture_text[:3000]}]"
                        )

            # Inject page context into system prompt for non-scripture pages too
            _page_title = page_context.get('page_title', '')
            _page_module = page_context.get('module', '')
            if _page_title or _page_module:
                # Resolve domain hint for grounding
                _fast_domain_hint = ''
                try:
                    from apps.ai.intent_service import IntentService
                    _fast_domain_hint = IntentService._resolve_domain_hint(page_context)
                except Exception:
                    pass
                system_prompt += f"\n\nPAGE CONTEXT: The user is viewing: {_page_title or _pc_url} (module: {_page_module})\n"
                if _fast_domain_hint:
                    system_prompt += f"DOMAIN GROUNDING: Active domain: {_fast_domain_hint}. When the user references visible entities using pronouns or deictic language ('those', 'them', 'the ones listed', 'still pending', 'mark them'), resolve against the current page domain first. Only cross domains if the user explicitly names a different domain.\n"

        user_name = self.user.first_name or self.user.get_short_name() or ""
        user_prompt = f"""{"The user's name is " + user_name + ". " if user_name else ""}{message}{scripture_context_block}
{reasoning_instruction}

Rules for this response:
- Answer directly. Lead with the data when you have it.
{rules_block}
{style_nudge}- Be conversational and natural — speak like someone who knows this person
- If they're sharing a feeling, expressing gratitude, or being vulnerable — respond to THAT. Don't re-explain what you just told them. A simple "I'm glad that helped" or "that's completely normal" is better than repeating content.
- If following up on previous conversation, build on it naturally"""

        mode_tokens = {'brief': 400, 'adaptive': 800, 'deep': 1200}
        max_tokens = mode_tokens.get(response_mode, 800)
        temperature = 0.5

        # Scripture breakdowns need more tokens
        if scripture_context_block and any(
            w in message.lower() for w in [
                'break it down', 'break down', 'explain', 'understand',
                'what does', 'teach me', 'walk me through', '30,000',
                '30000', 'overview', 'big picture',
            ]
        ):
            max_tokens = max(max_tokens, 1200)

        # --- i) Return context dict (same shape as _generate_response context-only)
        return {
            'system_prompt': system_prompt,
            'user_prompt': user_prompt,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'conversation_history': conversation_history,
            'briefing_built': _fast_briefing_built,
        }

    # -----------------------------------------------------------------
    # Deferred context warming (background thread)
    # -----------------------------------------------------------------

    def _run_deferred_context(self, message, conversation, page_context=None):
        """
        Background cache warming — ONLY warms caches, never modifies
        assistant_message or conversation state.

        Django DB connections are thread-local. This method explicitly
        closes connections at start (clean slate) and in finally (prevent leaks).
        """
        from django import db
        from apps.ai.readiness_cache import prewarm_cos_context

        import time as _t
        _start = _t.monotonic()

        try:
            # Ensure this thread starts with a clean DB connection state
            db.connections.close_all()

            prewarm_cos_context(self.user)

            logger.info(
                "DEFERRED_CTX_WARM ms=%.1f user=%s",
                (_t.monotonic() - _start) * 1000, self.user.id,
            )
        except Exception as e:
            logger.error("DEFERRED_CTX_WARM failed user=%s err=%s", self.user.id, e)
        finally:
            # CRITICAL: close any DB connections opened in this thread
            db.connections.close_all()

    # -----------------------------------------------------------------
    # Streaming response generation
    # -----------------------------------------------------------------

    def _generate_response_stream(
        self,
        message: str,
        conversation: AssistantConversation,
        page_context: dict = None,
        cos_context_cache: dict = None,
        assistant_message=None,
        is_checkin: bool = False,
        route_result=None,
        _ltrace=None,
    ):
        """
        Streaming version of _generate_response.

        Uses fast context path (cache-only, ~80-200ms) when viable, falling
        back to the full _generate_response pipeline when calibration is active
        or when the user is requesting a check-in (which needs direct DB queries
        and zero conversation history to avoid stale data contamination).
        Kicks off deferred cache warming in a background thread on fast path.

        Args:
            assistant_message: Optional pre-created AssistantMessage record.
                Created by send_message_stream() before streaming starts.
                Updated with final content after stream completes.
            is_checkin: If True, skip fast path and use full pipeline so that
                the check-in data injection (direct DB queries for tasks,
                calendar, meds) and zero-history treatment are applied.

        Yields: str chunks of the response text.
        """
        import time as _t_fast
        _t_fast_start = _t_fast.monotonic()
        full_text = ''
        first_token_logged = False

        try:
            # PHASE 1: Try fast context (80-200ms, cache-only)
            # Check-in queries MUST use the full pipeline to get:
            #   (a) Zero conversation history (prevents stale task contamination)
            #   (b) Direct DB queries for tasks, calendar, meds (not cached CoS)
            if _ltrace:
                _ltrace.start('COS_CONTEXT_BUILD_TOTAL')
            if is_checkin:
                ctx = None  # Force full pipeline path
                logger.info(
                    "FAST_CTX_SKIP user=%s reason=checkin_query",
                    self.user.id,
                )
            else:
                ctx = self._build_fast_context(
                    message, conversation,
                    page_context=page_context,
                    cos_context_cache=cos_context_cache,
                    route_result=route_result,
                )

            if ctx is None:
                # Fast path not viable (calibration active) → full pipeline
                logger.info("FAST_CTX_SKIP user=%s reason=calibration", self.user.id)
                ctx = self._generate_response(
                    message,
                    conversation,
                    page_context=page_context,
                    cos_context_cache=cos_context_cache,
                    _return_context_only=True,
                    route_result=route_result,
                    _ltrace=_ltrace,
                )
            else:
                if _ltrace:
                    _ltrace.end('COS_CONTEXT_BUILD_TOTAL')
                _fast_elapsed = (_t_fast.monotonic() - _t_fast_start) * 1000
                logger.warning(
                    "FAST_CTX_BUILD ms=%.1f user=%s", _fast_elapsed, self.user.id,
                )

                # Kick off deferred cache warming in background
                import threading
                threading.Thread(
                    target=self._run_deferred_context,
                    args=(message, conversation, page_context),
                    daemon=True,
                ).start()

            # If context building itself failed (returned a string fallback),
            # yield it as a single chunk
            if isinstance(ctx, str):
                # Fallback now uses Execution Truth Engine data — no replacement needed
                logger.warning(
                    "STREAM_CHECKIN_FALLBACK_GATE user=%s — context build "
                    "returned fallback string. Preview: %s",
                    self.user.id, (ctx or '')[:120],
                )
                full_text = ctx
                if assistant_message:
                    assistant_message.content = ctx
                    assistant_message.message_type = 'fallback'
                    assistant_message.save(update_fields=['content', 'message_type'])
                yield ctx
                return

            if not ctx:
                fallback = self._get_fallback_response(message)
                # _get_fallback_response now uses Execution Truth Engine data
                full_text = fallback
                logger.warning(
                    "STREAM_CTX_FALLBACK user=%s — context build returned "
                    "empty/None, returning fallback response to user",
                    self.user.id,
                )
                if assistant_message:
                    assistant_message.content = fallback
                    assistant_message.message_type = 'fallback'
                    assistant_message.save(update_fields=['content', 'message_type'])
                yield fallback
                return

            from .services import ai_service

            try:
                from django.conf import settings as django_settings
                _cos_model_stream = django_settings.COS_MODEL
                if _ltrace:
                    _ltrace.start('LLM_REQUEST')
                    _ltrace.set_meta('model', _cos_model_stream)
                for chunk in ai_service._call_api_stream(
                    ctx['system_prompt'],
                    ctx['user_prompt'],
                    max_tokens=ctx['max_tokens'],
                    temperature=ctx['temperature'],
                    endpoint='cos_chat',
                    user=self.user,
                    conversation_history=ctx['conversation_history'],
                    model=_cos_model_stream,
                ):
                    full_text += chunk

                    # First-token telemetry
                    if not first_token_logged:
                        logger.warning(
                            "STREAM_FIRST_TOKEN ms=%.1f user=%s",
                            (_t_fast.monotonic() - _t_fast_start) * 1000,
                            self.user.id,
                        )
                        if _ltrace:
                            _ltrace.start('LLM_FIRST_TOKEN')
                            _ltrace.end('LLM_FIRST_TOKEN')
                        first_token_logged = True

                    yield chunk

                if _ltrace:
                    _ltrace.end('LLM_REQUEST')

                # Normal completion — save full response to pre-created record
                if assistant_message and full_text:
                    assistant_message.content = full_text
                    assistant_message.save(update_fields=['content'])
                    logger.info(
                        "STREAM_MSG_SAVED id=%s len=%d user=%s",
                        assistant_message.id, len(full_text), self.user.id,
                    )

                # Mark executive briefing as delivered after successful stream
                if ctx and ctx.get('briefing_built') and full_text:
                    try:
                        from apps.ai.executive_briefing import mark_briefing_delivered
                        mark_briefing_delivered(conversation)
                    except Exception:
                        pass

                # Phase 5: Signal Prioritization Guardrail (observe-only)
                if full_text:
                    try:
                        cos_ctx = ctx.get('cos_context') if ctx else None
                        self._check_priority_alignment(full_text, cos_ctx)
                    except Exception:
                        pass

            finally:
                # GUARANTEE placeholder is finalized on ALL exit paths:
                # normal completion (already saved above → no-op),
                # exception, client disconnect (GeneratorExit), worker crash
                if assistant_message and not assistant_message.content:
                    if full_text:
                        # Partial response received — save what we have
                        assistant_message.content = full_text
                        try:
                            assistant_message.save(update_fields=['content'])
                        except Exception:
                            pass  # DB may be unavailable on worker crash
                        logger.warning(
                            "STREAM_MSG_FINALIZED id=%s len=%d user=%s partial=True",
                            assistant_message.id, len(full_text), self.user.id,
                        )
                    else:
                        # Zero tokens received (API failure, client disconnect).
                        # Leave content empty — send_message_stream's safety net
                        # will save a proper fallback if the generator exits
                        # normally. For GeneratorExit (client disconnect), the
                        # empty placeholder is filtered by the frontend.
                        logger.warning(
                            "STREAM_MSG_EMPTY id=%s user=%s — zero tokens received, "
                            "deferring to caller safety net",
                            assistant_message.id, self.user.id,
                        )

        except Exception as e:
            logger.error(
                "STREAM_EXCEPTION_FALLBACK user=%s error=%s — streaming "
                "generation failed, returning fallback response",
                self.user.id, e, exc_info=True,
            )
            fallback = self._get_fallback_response(message)
            if assistant_message and (not assistant_message.content or assistant_message.content == ''):
                assistant_message.content = full_text or fallback
                assistant_message.message_type = 'fallback'
                try:
                    assistant_message.save(update_fields=['content', 'message_type'])
                except Exception:
                    pass
            yield fallback

    def send_message_stream(
        self,
        message: str,
        conversation: AssistantConversation = None,
        page_context: dict = None,
    ):
        """
        Streaming variant of send_message. Yields SSE event dicts.

        Runs the same pre-processing as send_message (ECC, intents, calibration),
        then either:
        - Emits a direct response as a single token event (non-LLM path)
        - Streams tokens from the LLM via _generate_response_stream

        Post-processing (memory, rolling summary, undo tracking) runs after
        the stream completes, using the fully assembled response text.

        Does not support image attachments (use send_message for images).

        Yields:
            dict — Event dicts with keys:
                {'type': 'token', 'content': str}
                {'type': 'done', 'data': {'conversation_id': int, ...}}
                {'type': 'error', 'error': str}
        """
        import threading
        import uuid as _uuid

        # ── Latency tracer (diagnostic instrumentation) ──
        try:
            from apps.core.ai_observability.latency_trace import LatencyTrace
            _ltrace_s = LatencyTrace(user_id=self.user.id, path='stream')
        except Exception:
            _ltrace_s = None

        if not conversation:
            conversation = self.get_or_create_conversation()

        # Phase 6.7 + 6.8: duplicate-retry guard. If the same
        # (user, message) is already being processed (e.g., client
        # retried after a network blip), return a STRUCTURED payload
        # echoing the original message + submitted_at + request_id so
        # the frontend can render a dedicated "still working on it"
        # card with a "View latest result" button. No vague text
        # fallback per Phase 6.8.
        try:
            from apps.ai.idempotency import is_in_flight
            _existing = is_in_flight(self.user.id, message)
            if _existing:
                import time as _time
                logger.info(
                    "STREAM_DUPLICATE_SUPPRESSED user=%s request_id=%s — "
                    "in-flight marker detected, returning structured "
                    "duplicate payload",
                    self.user.id, _existing.get('request_id'),
                )
                _submitted_ms = _existing.get('submitted_at_ms') or 0
                _now_ms = int(_time.time() * 1000)
                _pending_seconds_ago = (
                    max(0, (_now_ms - _submitted_ms) // 1000)
                    if _submitted_ms else 0
                )
                _duplicate_payload = {
                    'conversation_id': conversation.id,
                    'request_id': _existing.get('request_id'),
                    'status': 'processing',
                    'duplicate_suppressed': True,
                    'original_message': (
                        _existing.get('original_message') or message
                    ),
                    'submitted_at_ms': _submitted_ms,
                    'pending_seconds_ago': _pending_seconds_ago,
                }
                yield {
                    'type': 'duplicate_pending',
                    'data': _duplicate_payload,
                }
                yield {
                    'type': 'done',
                    'data': _duplicate_payload,
                }
                return
        except Exception:
            pass  # Duplicate guard failure must not block the request

        # Save user message
        AssistantMessage.objects.create(
            conversation=conversation,
            role='user',
            content=message,
            message_type='text',
        )

        # Increment event context turn counter (for follow-up expiration)
        try:
            from apps.core.ai_events.followup import increment_turn_count
            increment_turn_count(conversation)
        except Exception:
            pass  # Non-critical

        # Phase 6.7: Execution Isolation — lifecycle tracking.
        # Every chat request gets a UUID request_id and a status field
        # on assistant_msg.metadata. Status transitions:
        #   processing → completed  (success)
        #   processing → failed     (exception)
        # If the SSE client disconnects, the try/finally at the bottom
        # of the generator still runs the status write so the UI can
        # recover the result via history polling.
        _request_id = str(_uuid.uuid4())
        _stream_interrupted = False
        _stream_status = 'processing'

        # Create assistant message placeholder BEFORE streaming.
        # Updated with final content after stream completes (or on interrupt).
        assistant_msg = AssistantMessage.objects.create(
            conversation=conversation,
            role='assistant',
            content='',
            message_type='text',
            metadata={
                'request_id': _request_id,
                'status': 'processing',
                'stream_interrupted': False,
                'page_context_captured': bool(page_context),
            },
        )

        # Phase 6.7: Mark request as in-flight so client retries during
        # processing see a "processing" marker instead of starting a
        # second execution.
        try:
            from apps.ai.idempotency import mark_in_flight
            mark_in_flight(self.user.id, message, _request_id)
        except Exception:
            pass

        # Phase 6.7: Hard intent lock. Once an actionable intent is
        # detected downstream, any remaining pre-processing branches
        # (ECC closure, proactive, check-in routing) are bypassed to
        # prevent fallback drift on retries.
        _intent_locked = False

        response_text = ""
        actions_taken = []
        # Phase 6.6: CRUD confirmation pills for streaming path.
        _pending_quick_replies = []

        # Phase 18.4: CRITICAL — update conversation mode from the
        # streaming path. Previously update_mode_from_message was
        # ONLY called in send_message (non-streaming). Since the
        # streaming path handles all production text messages, the
        # mode was NEVER persisted — causing reflective mode to be
        # lost between turns. This is why turn 3 of a faith thread
        # ("What does this mean for how I should live?") reverted
        # to execution ("Start Shower").
        try:
            from apps.core.blueprint.conversation_mode import (
                update_mode_from_message as _update_mode_stream,
            )
            _update_mode_stream(self.user, message)
        except Exception:
            pass

        try:
            # Check AI availability
            if not ai_service.is_available or not AIService.check_user_consent(self.user):
                response_text = self._get_fallback_response(message)
                logger.warning(
                    "STREAM_AI_UNAVAILABLE_FALLBACK user=%s available=%s consent=%s "
                    "— AI unavailable, returning fallback",
                    self.user.id, ai_service.is_available,
                    AIService.check_user_consent(self.user),
                )
                assistant_msg.content = response_text
                assistant_msg.message_type = 'fallback'
                assistant_msg.save(update_fields=['content', 'message_type'])
                yield {'type': 'token', 'content': response_text}
            else:
                # =====================================================
                # Pre-processing: ECC, proactive confirmations, intents
                # This mirrors the logic in send_message() but delegates
                # to the LLM streaming path when no short-circuit occurs.
                # =====================================================
                _cos_context_cache = None
                _direct_response = None
                _is_checkin_stream = False

                # ── RESPONSE GOVERNOR — central authority ───────────
                # Determines the single approved response type BEFORE
                # any pre-processing runs. When REFLECTIVE, all ECC,
                # proactive, affirmation, and intent layers are blocked.
                _reflective_mode_active = False
                try:
                    from apps.ai.response_governor import (
                        resolve_response_type as _resolve_rt,
                        ResponseType as _RT,
                    )
                    _gov_type = _resolve_rt(self.user, message)
                    _reflective_mode_active = (
                        _gov_type == _RT.REFLECTIVE
                    )
                except Exception:
                    pass

                # Build cos_context (same as send_message ECC section)
                try:
                    from apps.ai.readiness_cache import (
                        get_cached_cos_context as _rc_get,
                        get_layered_cos_context as _rc_get_layered,
                        set_readiness_state as _rc_set_state,
                        track_active_user as _rc_track,
                    )
                    _rc_set_state(self.user, 'active')
                    _rc_track(self.user)
                    _cos_context_cache = (
                        _rc_get_layered(self.user)
                        or _rc_get(self.user)
                    )
                except Exception:
                    pass

                if not _cos_context_cache:
                    try:
                        from apps.core.ai_orchestrator.cos_context import (
                            build_cos_context as _stream_build_cos,
                        )
                        _cos_context_cache = _stream_build_cos(self.user)
                    except Exception as e:
                        logger.warning("Streaming CoS context build failed: %s", e, exc_info=True)

                # ECC check (explicit commitment contract)
                try:
                    from apps.core.ai_orchestrator.commitment_contract import (
                        process_ecc_closure,
                        process_ecc_detection,
                        get_pending_commitments,
                    )
                    from apps.core.ai_orchestrator.cos_context import (
                        determine_activation_state as _ecc_determine_tier,
                        _build_trajectory_signals as _ecc_build_traj,
                    )

                    _ecc_traj = (_cos_context_cache or {}).get(
                        'trajectory_signals',
                        _ecc_build_traj(self.user),
                    )
                    _ecc_tier = _ecc_determine_tier(_ecc_traj, message)

                    _ecc_pending = list(get_pending_commitments(self.user))
                    if _ecc_pending and not _reflective_mode_active:
                        closure_result = process_ecc_closure(
                            self.user, message, _ecc_pending, _ecc_tier,
                        )
                        if closure_result:
                            _direct_response = closure_result

                    if not _direct_response and not _reflective_mode_active:
                        detection_result = process_ecc_detection(
                            self.user, message, _ecc_tier,
                        )
                        if detection_result:
                            _direct_response = detection_result
                except Exception as e:
                    logger.warning("Streaming ECC check failed: %s", e, exc_info=True)

                # Check-in pre-filter — detect "what's on my plate" queries
                # that should go to LLM (not intent service)
                # User-affirmed completion check — runs before proactive
                # confirmation to suppress reminders without CRUD execution.
                # Phase 18.4: skip in reflective mode
                if not _direct_response and not _reflective_mode_active:
                    try:
                        from .affirmation_detector import handle_affirmed_completion
                        _affirm_result = handle_affirmed_completion(
                            self.user, message, conversation,
                        )
                        if _affirm_result and _affirm_result.get('handled'):
                            _direct_response = _affirm_result['response']
                    except Exception:
                        logger.warning(
                            "Streaming affirmation detection failed",
                            exc_info=True,
                        )

                # Phase 18.4: skip proactive check-in in reflective mode
                if not _direct_response and not _reflective_mode_active:
                    try:
                        from .confirmation_detector import handle_proactive_confirmation
                        confirm_resp = handle_proactive_confirmation(
                            self.user, message, conversation,
                        )
                        if confirm_resp:
                            _direct_response = confirm_resp
                    except Exception:
                        pass

                # ── Pending CRUD action confirmation ──
                if not _direct_response:
                    try:
                        from apps.ai.intent_service import intent_service
                        _pending_crud = (
                            intent_service.get_pending_crud_action(self.user)
                        )
                        if _pending_crud:
                            _crud_result = (
                                intent_service.handle_crud_confirmation(
                                    self.user, message,
                                )
                            )
                            if _crud_result:
                                if _crud_result.action_type == 'confirmation_escaped':
                                    # User said something other than CONFIRM/CANCEL/EDIT.
                                    # Pending action already cancelled — let the message
                                    # fall through to normal AI processing.
                                    pass  # _direct_response stays None
                                elif _crud_result.action_type in (
                                    'cancelled', 'expired',
                                    'idempotent_skip',
                                ):
                                    _direct_response = _crud_result.message
                                else:
                                    _direct_response = (
                                        _crud_result.message
                                        + self._format_confirmation_detail(
                                            _crud_result
                                        )
                                    )
                                    if _crud_result.success:
                                        actions_taken.append(
                                            self._build_action_taken(
                                                _crud_result
                                            )
                                        )
                            else:
                                # Unrecognized — re-show the confirmation
                                # with its A/B/C pills (no plain-text fallback
                                # per Phase 6.6).
                                _crud_opts = _pending_crud.get('options', [])
                                _direct_response = _pending_crud['confirmation_message']
                                if _crud_opts:
                                    _pending_quick_replies = list(_crud_opts)
                    except Exception as crud_err:
                        logger.warning(
                            "Streaming CRUD confirmation check failed: %s",
                            crud_err, exc_info=True,
                        )

                # ── Pending disambiguation (multi-candidate selection) ──
                if not _direct_response:
                    try:
                        from apps.ai.intent_service import intent_service
                        _pending_disambig = (
                            intent_service.get_pending_disambiguation(self.user)
                        )
                        if _pending_disambig:
                            _disambig_result = (
                                intent_service.handle_disambiguation_response(
                                    self.user, message,
                                )
                            )
                            if _disambig_result:
                                if _disambig_result.action_type in (
                                    'cancelled', 'expired',
                                ):
                                    _direct_response = _disambig_result.message
                                elif _disambig_result.error == 'crud_confirmation_required':
                                    _direct_response = _disambig_result.message
                                else:
                                    _direct_response = (
                                        _disambig_result.message
                                        + self._format_confirmation_detail(
                                            _disambig_result
                                        )
                                    )
                                    if _disambig_result.success:
                                        actions_taken.append(
                                            self._build_action_taken(
                                                _disambig_result
                                            )
                                        )
                            else:
                                # Unrecognized — re-show disambiguation
                                _direct_response = (
                                    f"{_pending_disambig['confirmation_message']}"
                                    "\n\nPlease reply with a number, "
                                    "NONE, or CANCEL"
                                )
                    except Exception as disambig_err:
                        logger.warning(
                            "Streaming disambiguation check failed: %s",
                            disambig_err, exc_info=True,
                        )

                # ── Pending clarification check (entity disambiguation) ──
                if not _direct_response:
                    try:
                        from apps.ai.intent_service import intent_service
                        _stream_clarification = (
                            intent_service.get_pending_clarification(self.user)
                        )
                        if _stream_clarification:
                            _clar_result = (
                                intent_service.resolve_clarification(
                                    self.user, message,
                                )
                            )
                            if _clar_result:
                                _direct_response = (
                                    _clar_result.message
                                    + self._format_confirmation_detail(
                                        _clar_result
                                    )
                                )
                                if _clar_result.success:
                                    actions_taken.append(
                                        self._build_action_taken(_clar_result)
                                    )
                            else:
                                # Re-show numbered options
                                _cands = _stream_clarification['candidates']
                                _numbered = [
                                    f"{i + 1}. {c['title']}"
                                    for i, c in enumerate(_cands)
                                ]
                                _direct_response = (
                                    "I'm not sure which one you mean. "
                                    "Please choose:\n"
                                    + "\n".join(_numbered)
                                )
                    except Exception as clar_err:
                        logger.warning(
                            "Streaming clarification check failed: %s",
                            clar_err, exc_info=True,
                        )

                # ── Fast-path: Deterministic health summary (streaming) ──
                # Mirrors the non-streaming fast path. Health metric
                # queries skip the full LLM pipeline (~15-30s → ~200ms).
                # ── Shared Deterministic Router (streaming) ───────────
                # Same classify_and_route() as non-streaming path to
                # ensure parity. Handles data queries, health summary,
                # strict health status, and check-in prefilter detection.
                _route_result_stream = None
                if not _direct_response:
                    if _ltrace_s:
                        _ltrace_s.start('ROUTER_CLASSIFICATION')
                    try:
                        from apps.ai.deterministic_router import (
                            classify_and_route as _classify_route_s,
                            RouteCategory as _RC_s,
                        )
                        _route_result_stream = _classify_route_s(
                            message, self.user,
                            cos_context_cache=_cos_context_cache,
                            conversation=conversation,
                        )
                        if (_route_result_stream.is_terminal
                                and _route_result_stream.response):
                            _direct_response = _route_result_stream.response
                            # Store event context for follow-up continuity
                            if _route_result_stream.route_name in (
                                'event_missed_query',
                                'event_timeline_query',
                                'event_slippage_query',
                            ):
                                try:
                                    from apps.ai.deterministic_router import get_stashed_events
                                    from apps.core.ai_events.followup import store_event_context
                                    _stashed_s = get_stashed_events()
                                    if _stashed_s and conversation:
                                        store_event_context(
                                            conversation,
                                            _route_result_stream.route_name,
                                            _stashed_s,
                                            _direct_response,
                                        )
                                except Exception as _ec_s_err:
                                    logger.debug(
                                        "Event context storage (stream) failed: %s",
                                        _ec_s_err,
                                    )
                    except ImportError:
                        pass
                    except Exception as _router_s_err:
                        logger.warning(
                            "Deterministic router (stream) failed: %s",
                            _router_s_err, exc_info=True,
                        )
                    finally:
                        if _ltrace_s:
                            _ltrace_s.end('ROUTER_CLASSIFICATION')
                            if _route_result_stream:
                                _ltrace_s.set_meta('route_name', _route_result_stream.route_name)
                                _ltrace_s.set_meta('route_category', str(_route_result_stream.category))

                # ── Check-in prefilter (detected by shared router) ─────
                if not _direct_response and _route_result_stream is not None:
                    _is_checkin_stream = (
                        _route_result_stream.category == 'checkin_prefilter'
                    )
                    if _is_checkin_stream:
                        logger.info(
                            "CHECKIN_PREFILTER user=%s path=stream msg=%r",
                            self.user.id, message[:80],
                        )

                # ── Intent recognition (mirrors send_message Phase 7) ──
                # Run intent recognition BEFORE streaming so action
                # requests (create task, delete event, etc.) are handled
                # by the action pipeline, not the conversational LLM.
                # Intent bypass: skip when router detected no action signals.
                _skip_intent_stream = (
                    _route_result_stream is not None
                    and getattr(_route_result_stream, 'skip_intent', False)
                )
                if _skip_intent_stream and not _direct_response and not _is_checkin_stream:
                    logger.info(
                        "INTENT_BYPASS user=%s path=stream reason=no_action_signal msg=%r",
                        self.user.id, message[:80],
                    )
                    if _ltrace_s:
                        _ltrace_s.set_governance_decision('intent_bypassed')
                if (not _direct_response and not _is_checkin_stream
                        and not _skip_intent_stream
                        and not _reflective_mode_active):
                    try:
                        from apps.ai.intent_service import intent_service
                        from apps.core.ai_orchestrator.orchestrator import (
                            process_user_input as orchestrator_process,
                            enrich_and_execute,
                        )

                        # Build lean conversation history for intent context
                        _stream_history = None
                        try:
                            from apps.ai.conversation.message_builder import (
                                build_messages_from_history,
                            )
                            _stream_history = build_messages_from_history(
                                conversation.messages.order_by('-created_at'),
                                message,
                                max_messages=5,
                                max_content_chars=300,
                                token_budget=800,
                            )
                        except Exception:
                            pass

                        _stream_intent_domain = (
                            _route_result_stream.domain
                            if _route_result_stream else None
                        )
                        intent_results = intent_service.recognize_intents(
                            message, self.user,
                            conversation_history=_stream_history,
                            page_context=page_context,
                            domain=_stream_intent_domain,
                        )
                        actionable = [
                            ir for ir in intent_results
                            if ir.intent_type != 'no_action'
                        ]

                        # Domain mismatch telemetry (non-blocking)
                        self._log_intent_domain_mismatch(
                            self.user, actionable, page_context, message,
                        )

                        if actionable:
                            # Phase 6.7: Hard intent lock — record that an
                            # actionable intent was detected. Written to
                            # assistant_msg.metadata in the finally block so
                            # retries / audit can confirm the execution path
                            # was locked before any downstream work ran.
                            _intent_locked = True
                            # Execute via orchestrator pipeline
                            orch_result = orchestrator_process(
                                self.user, message,
                                page_context=page_context,
                            )

                            # If orchestrator needs clarification, ask user
                            if orch_result.needs_clarification:
                                _direct_response = (
                                    orch_result.clarification_question
                                )
                            else:
                                orch_actions = enrich_and_execute(
                                    self.user, actionable, orch_result,
                                )
                                parts = []
                                for ar in orch_actions:
                                    if ar.success:
                                        actions_taken.append(
                                            self._build_action_taken(ar)
                                        )
                                    parts.append(
                                        ar.message
                                        + self._format_confirmation_detail(
                                            ar
                                        )
                                    )
                                _direct_response = ' '.join(parts)

                                # Phase 6.6: Capture CRUD confirmation pills
                                # for streaming path so the final saved
                                # assistant message carries quick_replies.
                                _qr = self._extract_quick_replies(orch_actions)
                                if _qr:
                                    _pending_quick_replies = _qr

                                # Store clarification state for multiple_matches
                                for ar in orch_actions:
                                    if (ar.error == 'multiple_matches'
                                            and ar.created_object
                                            and ar.created_object.get(
                                                'candidates'
                                            )):
                                        _mi = next(
                                            (ir for ir in actionable
                                             if ir.intent_type
                                             == ar.action_type),
                                            None,
                                        )
                                        if _mi:
                                            intent_service \
                                                .store_pending_clarification(
                                                    self.user,
                                                    intent_type=(
                                                        _mi.intent_type
                                                    ),
                                                    parameters=(
                                                        _mi.parameters
                                                    ),
                                                    candidates=(
                                                        ar.created_object[
                                                            'candidates'
                                                        ]
                                                    ),
                                                )
                    except Exception as intent_err:
                        logger.error(
                            "send_message_stream intent error: %s",
                            intent_err, exc_info=True,
                        )

                # ── Strict health status now handled by shared router above ──

                # ── Invalidate in-request CoS cache after mutations ──
                if actions_taken:
                    _cos_context_cache = None

                if _direct_response:
                    # Pre-processing or intent produced a direct response
                    response_text = _direct_response
                    assistant_msg.content = response_text
                    assistant_msg.message_type = (
                        'action' if actions_taken else 'text'
                    )
                    # Phase 6.6: Persist A/B/C pills onto the assistant
                    # message so the chat widget renders them as buttons.
                    if _pending_quick_replies:
                        assistant_msg.quick_replies = _pending_quick_replies
                        assistant_msg.save(
                            update_fields=['content', 'message_type', 'quick_replies']
                        )
                    else:
                        assistant_msg.save(
                            update_fields=['content', 'message_type']
                        )
                    yield {'type': 'token', 'content': response_text}
                    if _pending_quick_replies:
                        yield {
                            'type': 'quick_replies',
                            'quick_replies': _pending_quick_replies,
                        }
                else:
                    # Stream from LLM (conversational — no action executed)
                    chunks = []
                    for chunk in self._generate_response_stream(
                        message, conversation,
                        page_context=page_context,
                        cos_context_cache=_cos_context_cache,
                        assistant_message=assistant_msg,
                        is_checkin=_is_checkin_stream,
                        route_result=_route_result_stream,
                        _ltrace=_ltrace_s,
                    ):
                        chunks.append(chunk)
                        yield {'type': 'token', 'content': chunk}
                    response_text = ''.join(chunks)

                    if not response_text:
                        response_text = self._get_fallback_response(message)
                        logger.warning(
                            "STREAM_EMPTY_FALLBACK user=%s — stream produced "
                            "zero tokens, returning fallback response",
                            self.user.id,
                        )
                        yield {'type': 'token', 'content': response_text}

                    # Safety net: ensure assistant_msg has final content
                    # (normally saved by _generate_response_stream, but guard here)
                    if response_text and not assistant_msg.content:
                        # Detect if this is a fallback
                        _is_fallback_text = self._is_fallback_response(response_text)
                        assistant_msg.content = response_text
                        if _is_fallback_text:
                            assistant_msg.message_type = 'fallback'
                        assistant_msg.save(update_fields=['content', 'message_type'])

                    # ── Post-stream validator gate ──
                    # Check for hallucinated action claims in the streamed
                    # response.  Since tokens were already sent, we can only
                    # update the saved message and emit a correction event.
                    try:
                        from apps.core.ai_governance.validator_gate import (
                            validate_response as _stream_validate,
                        )
                        _sv = _stream_validate(
                            response_text, self.user, conversation,
                            action_executed=bool(actions_taken),
                        )
                        if _sv['blocked']:
                            response_text = _sv['response']
                            assistant_msg.content = response_text
                            assistant_msg.save(update_fields=['content'])
                            yield {
                                'type': 'correction',
                                'content': response_text,
                            }
                            logger.warning(
                                "[STREAM_VALIDATOR] Blocked hallucination "
                                "in stream: %s",
                                _sv['violations'],
                            )
                    except Exception:
                        pass

                    # ── CoS Locked Facts Validation (stream path) ──
                    # Streaming: tokens already sent, so append correction.
                    try:
                        from apps.ai.cos_fact_statements import (
                            build_locked_facts as _stream_build_locked,
                        )
                        from apps.ai.cos_truth_validator import (
                            validate_locked_facts as _cos_validate_locked,
                            log_cos_debug_state as _cos_debug,
                        )
                        _cos_debug(self.user)
                        _stream_locked = _stream_build_locked(self.user)
                        _corrected, _cos_violations = _cos_validate_locked(
                            response_text, _stream_locked, self.user,
                            allow_regenerate=False,
                        )
                        if _cos_violations:
                            response_text = _corrected
                            assistant_msg.content = response_text
                            assistant_msg.save(update_fields=['content'])
                            yield {
                                'type': 'correction',
                                'content': response_text,
                            }
                            logger.error(
                                "COS_LOCKED_GUARDRAIL_STREAM user=%s "
                                "violations=%d domains=%s",
                                self.user.id, len(_cos_violations),
                                [v['domain'] for v in _cos_violations],
                            )
                    except Exception as _val_err:
                        # Log loudly — truth validation failure is critical
                        logger.error(
                            "COS_LOCKED_VALIDATOR_CRASHED user=%s error=%s "
                            "— truth validation could not run on stream response",
                            self.user.id, _val_err, exc_info=True,
                        )

                    # ── Health Intelligence validator (observe-only) ──
                    try:
                        from apps.ai.validators.health_response_validator import (
                            validate_health_response as _stream_health_validate,
                        )
                        _stream_health_validate(
                            response_text, _cos_context_cache, self.user,
                        )
                    except ImportError:
                        pass
                    except Exception:
                        pass

            # Phase 6.7: Reached the end of the try body without an
            # exception — mark the request as completed so the finally
            # block writes 'completed' to the lifecycle metadata.
            _stream_status = 'completed'

        except GeneratorExit:
            # Phase 6.7: Client disconnected mid-stream (tab switch, navigate,
            # network drop). GeneratorExit is raised at the yield point that
            # failed. We must NOT swallow it — Python's generator protocol
            # requires it to propagate — but we record the interruption on
            # the assistant_msg so the UI can recover via history polling.
            _stream_interrupted = True
            _stream_status = 'completed'  # we still have partial content
            logger.info(
                "STREAM_INTERRUPTED user=%s request_id=%s — client "
                "disconnected, finalizing in finally block",
                self.user.id, _request_id,
            )
            raise
        except Exception as e:
            _stream_status = 'failed'
            logger.error(
                "STREAM_TOPLEVEL_FALLBACK user=%s error=%s — top-level "
                "stream exception, returning fallback",
                self.user.id, e, exc_info=True,
            )
            if not response_text:
                response_text = self._get_fallback_response(message)
                try:
                    yield {'type': 'token', 'content': response_text}
                except GeneratorExit:
                    _stream_interrupted = True
                    raise
            # Ensure placeholder is not left empty on error — mark as fallback
            if not assistant_msg.content:
                assistant_msg.content = response_text or self._get_fallback_response(message)
                assistant_msg.message_type = 'fallback'
                try:
                    assistant_msg.save(update_fields=['content', 'message_type'])
                except Exception:
                    pass
        finally:
            # Phase 6.7: Guaranteed lifecycle write. This runs on success,
            # on exception, AND on GeneratorExit (client disconnect). The
            # assistant_msg row MUST reflect the best computed state so the
            # UI can recover via history polling when the client reconnects.
            try:
                _final_content = assistant_msg.content or response_text
                _existing_meta = dict(assistant_msg.metadata or {})
                _existing_meta.update({
                    'request_id': _request_id,
                    'status': _stream_status,
                    'stream_interrupted': _stream_interrupted,
                    'intent_locked': _intent_locked,
                })
                assistant_msg.metadata = _existing_meta
                if _final_content and not assistant_msg.content:
                    assistant_msg.content = _final_content
                if _pending_quick_replies and not assistant_msg.quick_replies:
                    assistant_msg.quick_replies = _pending_quick_replies
                assistant_msg.save(update_fields=[
                    'content', 'metadata', 'quick_replies',
                ])
            except Exception as _final_err:
                logger.error(
                    "STREAM_FINAL_SAVE_FAILED user=%s request_id=%s: %s",
                    self.user.id, _request_id, _final_err, exc_info=True,
                )
            # Clear in-flight marker so the next request isn't blocked.
            try:
                from apps.ai.idempotency import clear_in_flight
                clear_in_flight(self.user.id, message)
            except Exception:
                pass
            # NOTE: DB connection close happens at the very end of the
            # function (after post-processing) so that post-processing
            # can still query the DB in the success path.

        # =====================================================
        # Post-processing (identical to send_message)
        # =====================================================

        # Record calibration answer
        try:
            skip_recording = getattr(
                self, '_calibration_welcome_just_shown', False
            )
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
            pass

        # Update message type if actions were taken
        if actions_taken and assistant_msg.message_type != 'action':
            assistant_msg.message_type = 'action'
            assistant_msg.save(update_fields=['message_type'])

        # Update conversation timestamp
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])

        # Post-response: record interaction depth for Adaptive CoS Presence.
        try:
            from apps.ai.executive_briefing import record_interaction_depth
            _metadata_post = conversation.metadata or {}
            _briefing_was_delivered = (
                _metadata_post.get('last_briefing_date') == str(
                    timezone.now().date()
                )
            )
            _msg_lower_depth = (message or '').lower()
            _is_checkin_depth = any(
                p in _msg_lower_depth for p in [
                    'check in', 'checking in', 'status', 'refresh',
                    "how's my day", 'how does my day look',
                    "what's left", "what do i have",
                ]
            )
            record_interaction_depth(
                conversation, self.user,
                briefing_delivered=_briefing_was_delivered,
                is_checkin=_is_checkin_depth,
            )
        except Exception:
            pass  # Interaction depth tracking must never break chat

        # Background: rolling summary
        try:
            from apps.ai.executive_briefing import maybe_generate_rolling_summary

            def _rolling_summary_bg():
                try:
                    maybe_generate_rolling_summary(self.user, conversation)
                except Exception:
                    pass

            threading.Thread(target=_rolling_summary_bg, daemon=True).start()
        except Exception:
            pass

        # Background: memory storage
        try:
            from apps.ai.memory_service import store_memory

            def _store_memory_bg():
                try:
                    store_memory(
                        user=self.user,
                        user_message=message,
                        assistant_response=response_text,
                        conversation=conversation,
                        page_context=page_context,
                    )
                except Exception:
                    pass

            threading.Thread(target=_store_memory_bg, daemon=True).start()
        except Exception:
            pass

        # Store actions in conversation metadata for undo support
        if actions_taken:
            try:
                meta = conversation.metadata or {}
                stored_actions = meta.get('actions_taken', [])
                stored_actions.extend(actions_taken)
                meta['actions_taken'] = stored_actions[-10:]
                conversation.metadata = meta
                conversation.save(update_fields=['metadata', 'updated_at'])
            except Exception:
                pass

        # ── Deterministic critical signal injection (stream path) ──
        # Same enforcement as non-streaming: critical signals are guaranteed
        # regardless of LLM behavior. Uses structured idempotency + grouping.
        try:
            from apps.life.services.event_acknowledgment import (
                get_today_critical_events as _stream_get_events,
                check_response_acknowledges_events as _stream_check,
                build_grouped_acknowledgment as _stream_group,
            )

            _stream_events = _stream_get_events(self.user)
            if _stream_events and response_text:
                _unacked = _stream_check(response_text, _stream_events)
                _s_ack_count = len(_stream_events) - len(_unacked)

                if _unacked:
                    _injection = _stream_group(_unacked)
                    if _injection:
                        response_text = _injection + "\n\n" + response_text
                        assistant_msg.content = response_text
                        assistant_msg.save(update_fields=['content'])
                        yield {
                            'type': 'correction',
                            'content': response_text,
                        }
                        logger.warning(
                            "critical_signal_evaluation user=%s path=stream "
                            "events_found=%d acknowledged_by_llm=%d "
                            "injected=%d",
                            self.user.id,
                            len(_stream_events),
                            _s_ack_count,
                            len(_unacked),
                        )
                    else:
                        logger.error(
                            "CRITICAL: events_found=%d acknowledged=0 "
                            "injected=0 — stream event not acknowledged "
                            "or injected user=%s",
                            len(_stream_events), self.user.id,
                        )
                else:
                    logger.info(
                        "critical_signal_evaluation user=%s path=stream "
                        "events_found=%d acknowledged_by_llm=%d injected=0",
                        self.user.id,
                        len(_stream_events),
                        _s_ack_count,
                    )
        except Exception:
            logger.error(
                "CRITICAL_SIGNALS_STREAM_FAILED user=%s",
                self.user.id,
                exc_info=True,
            )

        # Done event — include options and navigation for front-end rendering
        result_data = {'conversation_id': conversation.id}
        if actions_taken:
            result_data['actions_taken'] = actions_taken

        # Structured options (A/B/C chips)
        _stream_options = self._extract_options_from_actions(actions_taken)
        if _stream_options:
            result_data['options'] = _stream_options
        elif '_pending_crud' in dir() and _pending_crud and _pending_crud.get('options'):
            result_data['options'] = _pending_crud['options']
        else:
            # Parse A/B/C patterns from streamed LLM text for general responses
            _, _text_options = self._extract_options_from_text(response_text)
            if _text_options:
                result_data['options'] = _text_options

        # Navigation hint
        _stream_nav = self._get_navigation_hint(actions_taken)
        if _stream_nav:
            result_data['navigation'] = _stream_nav

        # Phase 6.7: Include request_id so the frontend can correlate
        # this response with the pending request marker it stored at
        # submit time.
        result_data['request_id'] = _request_id

        # ── Latency report (diagnostic instrumentation) ──
        if _ltrace_s:
            try:
                _ltrace_s.report()
            except Exception:
                pass

        try:
            yield {'type': 'done', 'data': result_data}
        except GeneratorExit:
            # Client disconnected right before the done event. The inner
            # finally already persisted status/content, so we just let it
            # propagate.
            _stream_interrupted = True
            try:
                _meta = dict(assistant_msg.metadata or {})
                _meta['stream_interrupted'] = True
                assistant_msg.metadata = _meta
                assistant_msg.save(update_fields=['metadata'])
            except Exception:
                pass
            raise
        # Phase 6.7: Intentionally no explicit DB connection close here.
        # send_message_stream runs in the Django request thread, where
        # the framework's CONN_MAX_AGE / close_old_connections signal
        # handles cleanup automatically. An explicit close would break
        # the request's active connection (and the test transaction).
        # Background daemon threads spawned later in post-processing
        # manage their own connection lifecycles.

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
    # Phase 5: Signal Prioritization Guardrail
    # -----------------------------------------------------------------
    def _check_priority_alignment(self, response: str, cos_context: dict = None):
        """
        Check if the LLM response references the dominant concern.

        Observe-only — logs COS_PRIORITY_MISALIGNMENT if the response
        doesn't mention keywords from the dominant concern. Does NOT
        block or modify the response.

        This enables monitoring of how often the LLM ignores the
        highest-priority signal despite having it in context.
        """
        try:
            from apps.core.ai_state.models import CoSSituationState
            sit = CoSSituationState.objects.filter(user=self.user).first()

            if not sit or not sit.dominant_concern:
                return  # No concern to check against

            concern = sit.dominant_concern.lower()
            resp_lower = (response or '').lower()

            # Extract significant keywords from the dominant concern
            # (words longer than 3 chars, excluding common words)
            _stop_words = {
                'the', 'and', 'for', 'not', 'yet', 'but', 'has', 'have',
                'been', 'with', 'this', 'that', 'from', 'your', 'today',
                'still', 'more', 'than', 'just', 'also', 'about',
            }
            concern_keywords = [
                w for w in concern.split()
                if len(w) > 3 and w not in _stop_words
            ]

            if not concern_keywords:
                return

            # Check if ANY significant keyword appears in the response
            matched = any(kw in resp_lower for kw in concern_keywords)

            if not matched:
                logger.warning(
                    "COS_PRIORITY_MISALIGNMENT user=%s — LLM response does "
                    "not reference the dominant concern. "
                    "concern='%s' keywords=%s response_preview='%s'",
                    self.user.id,
                    sit.dominant_concern[:80],
                    concern_keywords[:5],
                    response[:120],
                )
        except Exception:
            pass  # Guardrail is non-blocking — never fail the response

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
        msg = message.strip()
        msg_lower = msg.lower()

        # Brief ALWAYS wins when user explicitly requests brevity — even for
        # analysis or task queries. The user said "keep it short" and means it.
        if any(kw in msg_lower for kw in [
            'keep it short', 'keep it brief', 'just the numbers',
            'just the status', 'short answer', 'tl;dr',
        ]):
            return 'brief'

        if is_analysis or is_task_query:
            return 'deep'
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

    # -----------------------------------------------------------------
    # Domain mismatch telemetry
    # -----------------------------------------------------------------
    @staticmethod
    def _log_intent_domain_mismatch(user, actionable_intents, page_context, message):
        """Log when recognized intents don't match the user's current page domain.

        Pure observability — never blocks execution. Helps identify cases
        where domain grounding either saved or missed a mismatch.
        """
        if not page_context or not actionable_intents:
            return

        try:
            from apps.ai.intent_service import IntentService
            from apps.core.ai_orchestrator.intent_engine import get_intent_module

            page_domain = IntentService._resolve_domain_hint(page_context)
            if not page_domain:
                return  # Neutral page — nothing to compare

            # Extract the primary domain word from page_domain
            # e.g. "intake/health (take_medication, ...)" → "intake", "health"
            page_domain_lower = page_domain.lower()

            for ir in actionable_intents:
                intent_module = get_intent_module(ir.intent_type)
                if not intent_module:
                    continue

                # Check if intent module aligns with page domain
                intent_module_lower = intent_module.lower()
                # Consider match if intent module appears in page domain string
                # or page domain contains intent module
                if (intent_module_lower in page_domain_lower
                        or page_domain_lower.split('/')[0].split('(')[0].strip()
                        in intent_module_lower):
                    continue  # Aligned — no mismatch

                logger.warning(
                    "DOMAIN_MISMATCH user=%s page_module=%s intent_type=%s "
                    "intent_domain=%s page_url=%s msg=%.100s",
                    getattr(user, 'id', '?'),
                    page_domain,
                    ir.intent_type,
                    intent_module,
                    page_context.get('url', ''),
                    message,
                )
        except Exception:
            pass  # Telemetry must never break the pipeline

    def _get_fallback_response(self, message: str) -> str:
        """
        Fallback when AI is unavailable — uses the canonical CoS renderer.

        Routes through the same deterministic pipeline as every other CoS
        path: build_cos_structured_output → rendered_text. No domain labels,
        no count dumps, no legacy formatting. Same voice as a normal briefing.
        """
        # Check if the message is a personal reflection/sharing (emotional content)
        if self._is_personal_reflection(message):
            return self._get_reflection_response(message)

        # Use the canonical CoS renderer — same path as briefing/check-in
        try:
            from apps.ai.beth_checkin_renderer import (
                build_cos_structured_output,
            )
            structured = build_cos_structured_output(self.user)
            rendered = structured.get('rendered_text', '')
            if rendered and len(rendered) > 20:
                logger.info(
                    "[CoS FALLBACK] user=%s — LLM unavailable, using "
                    "canonical CoS renderer",
                    self.user.id,
                )
                return rendered
        except Exception as e:
            logger.error(
                "[CoS FALLBACK] user=%s — canonical renderer failed: %s",
                self.user.id, e, exc_info=True,
            )

        # Emergency fallback — minimal safe message, no domain labels
        from apps.ai.beth_checkin_renderer import _SAFE_FALLBACK
        return _SAFE_FALLBACK

    # Fallback detection — the canonical CoS renderer produces normal
    # briefing text, so we detect fallback by the _SAFE_FALLBACK prefix.
    _FALLBACK_PREFIXES = (
        "I wasn't able to load your day right now",  # _SAFE_FALLBACK
        # Legacy strings for backward compat with saved messages
        "I'm having trouble connecting to AI right now",
        "I'm unable to load your status right now",
        "I wasn't able to pull your data",
        "Something went wrong on my end loading",
        "I hit a snag pulling your information",
        "I wasn't quite able to load your data",
        "I ran into an issue loading your status",
        "Something didn't connect right on my end",
    )

    def _is_fallback_response(self, text: str) -> bool:
        """Check if text is a fallback response (new or legacy)."""
        stripped = (text or '').strip()
        return any(stripped.startswith(prefix) for prefix in self._FALLBACK_PREFIXES)

    def _is_personal_reflection(self, message: str) -> bool:
        """
        Check if the message is a personal reflection or emotional sharing.

        v6: Tightened to avoid misclassifying strategic/advisory questions.
        Only catches genuine introspection and emotional processing, NOT:
        - improvement questions ("what would make the biggest improvement")
        - prioritization questions ("what should I focus on")
        - advisory questions ("should I work out today")
        - strategic planning questions ("how should I structure my day")
        """
        msg_lower = message.lower()

        # v6: EXCLUDE strategic/advisory/decision questions first.
        # These should NEVER be classified as reflections.
        strategic_indicators = [
            'what should', 'how should', 'should i',
            'what would', 'what could', 'what can',
            'what is the', 'what are the',
            'improve', 'improvement', 'prioritize', 'priority',
            'focus on', 'structure', 'recommend', 'biggest',
            'highest impact', 'single habit', 'best approach',
            'what do you think', 'what would you',
            'if you were', 'chief of staff',
            'start tracking', 'work out', 'workout',
            '?',  # Questions are almost never pure reflections
        ]
        if any(ind in msg_lower for ind in strategic_indicators):
            return False

        # Genuine reflection indicators — emotional processing, introspection
        # Use PHRASE-level matching (not substring) to avoid false positives
        reflection_phrases = [
            'i feel ', 'i felt ', 'i\'m feeling ',
            'i\'ve been struggling', 'i have been struggling',
            'i\'m struggling', 'i was struggling',
            'feeling overwhelmed', 'feeling anxious', 'feeling sad',
            'feeling stressed', 'feeling down', 'feeling lost',
            'today was hard', 'today was tough', 'today was rough',
            'i\'m grateful', 'i\'m thankful', 'i\'m blessed',
            'i\'m happy', 'i\'m sad', 'i\'m anxious',
            'i\'m proud', 'i\'m excited',
            'closer to god', 'my faith journey',
            'i\'ve been journaling', 'i\'ve been reflecting',
        ]

        # Require at least 1 genuine reflection phrase
        has_reflection_phrase = any(phrase in msg_lower for phrase in reflection_phrases)

        # Also require the message to be first-person emotional sharing
        # (starts with "I" or "My" and contains emotional content)
        emotional_words = [
            'struggling', 'overwhelmed', 'anxious', 'stressed',
            'sad', 'happy', 'grateful', 'thankful', 'blessed',
            'proud', 'excited', 'scared', 'worried', 'hurt',
            'lonely', 'frustrated', 'angry', 'peaceful', 'hopeful',
        ]
        has_emotion = any(word in msg_lower for word in emotional_words)
        starts_first_person = msg_lower.startswith('i ') or msg_lower.startswith('i\'')

        return has_reflection_phrase or (starts_first_person and has_emotion)

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


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def get_personal_assistant(user) -> PersonalAssistant:
    """Get a PersonalAssistant instance for a user."""
    return PersonalAssistant(user)
