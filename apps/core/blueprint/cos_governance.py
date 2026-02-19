"""
Whole Life Journey — CoS Governance Decision Layer

Project: Whole Life Journey
Path: apps/core/blueprint/cos_governance.py
Purpose: Adaptive authority framework for CoS behavior governance

Description:
    Every CoS output passes through this layer to decide:
    a) Ask vs don't ask (question gating)
    b) Suggest vs enforce (tier-based)
    c) Tone intensity (persona + tolerance + sensitivity)
    d) Delivery channel via DNE

    The governance profile is stored on PersonalOperatingBlueprint and
    learned over time via SLCME. Users control 5 simple settings; everything
    else is learned through conversation.

Public API:
    - evaluate_governance(user, action_type, context) -> GovernanceDecision
    - should_ask_question(user, question_category) -> bool
    - record_governance_interaction(user, question_category, user_response) -> None
    - get_calibration_question(user) -> dict or None
    - mark_calibration_question_asked(user, phase_key, question_text) -> None
    - get_ongoing_relationship_question(user) -> dict or None
    - mark_ongoing_question_shown(user, category, question_text='') -> None
    - build_governance_instructions(user) -> str
    - advance_calibration_day(user) -> None

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================


class GovernanceDecision:
    """Result of a governance evaluation."""
    __slots__ = (
        'should_ask', 'tone_intensity', 'delivery_channel',
        'explanation', 'sensitivity_active', 'accountability_level',
    )

    def __init__(self, **kwargs):
        self.should_ask = kwargs.get('should_ask', True)
        self.tone_intensity = kwargs.get('tone_intensity', 'standard')
        self.delivery_channel = kwargs.get('delivery_channel', 'in_app')
        self.explanation = kwargs.get('explanation', '')
        self.sensitivity_active = kwargs.get('sensitivity_active', False)
        self.accountability_level = kwargs.get('accountability_level', 'standard')


# =============================================================================
# CALIBRATION QUESTIONS
# =============================================================================

# High-leverage questions organized by calibration phase.
# Each phase runs for ~3 days. Max 2 questions per day.
CALIBRATION_PHASES = {
    # Days 1-3: Core people
    'core_people': {
        'day_range': (0, 3),
        'questions': [
            {
                'category': 'core_people',
                'question': "Who are the most important people in your daily life?",
                'follow_up': "I'll remember them so I can help you stay connected.",
                'meaning_type': 'core_people',
            },
            {
                'category': 'core_people',
                'question': "Is there anyone you've been meaning to reconnect with?",
                'follow_up': "I can help you find time for that.",
                'meaning_type': 'reconnection_target',
            },
        ],
    },
    # Days 4-6: Non-negotiables
    'non_negotiables': {
        'day_range': (3, 6),
        'questions': [
            {
                'category': 'non_negotiables',
                'question': "What activities are sacred to you — things you'd never want to skip?",
                'follow_up': "Those become Tier 1 — I'll protect them first.",
                'meaning_type': 'sacred_activity',
            },
            {
                'category': 'non_negotiables',
                'question': "What time of day do you feel most productive?",
                'follow_up': "I'll schedule your most important work there.",
                'meaning_type': 'peak_productivity',
            },
        ],
    },
    # Days 7-10: Preferred activities
    'preferred_activities': {
        'day_range': (6, 10),
        'questions': [
            {
                'category': 'preferred_activities',
                'question': "What do you enjoy doing when you have free time?",
                'follow_up': "I'll suggest these when I find open windows in your week.",
                'meaning_type': 'leisure_preference',
            },
            {
                'category': 'preferred_activities',
                'question': "Do you prefer mornings or evenings for personal time?",
                'follow_up': "That helps me plan better opportunity windows.",
                'meaning_type': 'personal_time_preference',
            },
        ],
    },
    # Days 11-14: Negotiables
    'negotiables': {
        'day_range': (10, 14),
        'questions': [
            {
                'category': 'negotiables',
                'question': "What can be moved or dropped when things get busy?",
                'follow_up': "Good — those stay flexible when curveballs hit.",
                'meaning_type': 'negotiable_activity',
            },
            {
                'category': 'negotiables',
                'question': "When I check in with questions, do you prefer morning or evening?",
                'follow_up': "I'll time my questions accordingly.",
                'meaning_type': 'checkin_time_preference',
            },
        ],
    },
}

# Standard "why" response — used when user asks why CoS is asking something
WHY_RESPONSE = (
    "The more I understand what matters to you, the better I can protect it — "
    "share only what you're comfortable with."
)

# Daily question caps by frequency setting
DAILY_QUESTION_CAPS = {
    'low': 1,
    'medium': 2,
    'high': 3,
}

# Tone intensity mapping by accountability style
TONE_MAP = {
    'light': {
        'general': 'gentle',
        'tier1': 'warm_but_firm',
        'tier2': 'gentle',
        'reminder': 'soft',
    },
    'standard': {
        'general': 'standard',
        'tier1': 'firm',
        'tier2': 'standard',
        'reminder': 'standard',
    },
    'firm': {
        'general': 'direct',
        'tier1': 'very_firm',
        'tier2': 'direct',
        'reminder': 'direct',
    },
}


# =============================================================================
# PUBLIC API
# =============================================================================


def evaluate_governance(user, action_type, context=None):
    """
    Evaluate governance rules for a CoS action.

    Consults the blueprint governance profile and intervention engine
    to decide how the CoS should behave.

    Args:
        user: Django User instance.
        action_type: str — 'question', 'suggestion', 'reminder', 'nudge', 'intervention'
        context: dict — optional context (trigger_type, behavior_key, sensitivity, etc.)

    Returns:
        GovernanceDecision
    """
    context = context or {}
    blueprint = _get_blueprint(user)
    if not blueprint:
        return GovernanceDecision()

    style = blueprint.accountability_style
    sensitivity_tags = blueprint.sensitivity_tags or []
    topic = context.get('topic', '')

    # Check if topic is sensitive
    is_sensitive = topic in sensitivity_tags

    # Determine tone intensity
    tier = context.get('tier', 4)
    if tier == 1:
        tone_key = 'tier1'
    elif tier == 2:
        tone_key = 'tier2'
    elif action_type == 'reminder':
        tone_key = 'reminder'
    else:
        tone_key = 'general'

    tone = TONE_MAP.get(style, TONE_MAP['standard']).get(tone_key, 'standard')

    # Soften tone for sensitive topics
    if is_sensitive and tone in ('firm', 'very_firm', 'direct'):
        tone = 'warm_but_firm' if tier == 1 else 'gentle'

    # Should we ask or skip?
    should_ask = True
    if action_type == 'question':
        should_ask = should_ask_question(user, context.get('category', ''))

    # Delivery channel — consult user preferences
    channel = _get_preferred_channel(user)

    return GovernanceDecision(
        should_ask=should_ask,
        tone_intensity=tone,
        delivery_channel=channel,
        sensitivity_active=is_sensitive,
        accountability_level=style,
        explanation=f"Style: {style}, tone: {tone}, sensitive: {is_sensitive}",
    )


def should_ask_question(user, question_category=''):
    """
    Determine if CoS should ask a question right now.

    Checks:
    1. Daily question count vs frequency cap
    2. Whether user previously declined this category
    3. Calibration status

    Args:
        user: Django User instance.
        question_category: str — category of question being considered.

    Returns:
        bool — True if question is appropriate.
    """
    blueprint = _get_blueprint(user)
    if not blueprint:
        return False

    # Check daily cap
    cap = DAILY_QUESTION_CAPS.get(blueprint.question_frequency, 2)
    today_count = _get_today_question_count(user)
    if today_count >= cap:
        return False

    # Check if user has declined this category
    overrides = blueprint.governance_overrides or {}
    declined = overrides.get('declined_categories', [])
    if question_category in declined:
        return False

    return True


def record_governance_interaction(user, question_category, user_response):
    """
    Record a governance interaction and update preferences.

    If user declines, stores category in declined list.
    If user answers, stores via SLCME for future reference.

    Args:
        user: Django User instance.
        question_category: str — what was asked about.
        user_response: str — 'answered', 'declined', 'skip'
    """
    blueprint = _get_blueprint(user)
    if not blueprint:
        return

    overrides = blueprint.governance_overrides or {}

    if user_response in ('declined', 'skip'):
        declined = overrides.get('declined_categories', [])
        if question_category not in declined:
            declined.append(question_category)
            overrides['declined_categories'] = declined
    elif user_response == 'answered':
        # Remove from declined if previously declined
        declined = overrides.get('declined_categories', [])
        if question_category in declined:
            declined.remove(question_category)
            overrides['declined_categories'] = declined

    # Record in overrides
    history = overrides.get('interaction_history', [])
    history.append({
        'category': question_category,
        'response': user_response,
        'timestamp': timezone.now().isoformat(),
    })
    # Keep last 50 interactions
    overrides['interaction_history'] = history[-50:]
    overrides['last_interaction'] = timezone.now().isoformat()

    blueprint.governance_overrides = overrides
    blueprint.save(update_fields=['governance_overrides', 'updated_at'])

    # Also store in SLCME if answered
    if user_response == 'answered':
        try:
            from apps.core.ai_memory.memory_engine import store_learned_mapping
            store_learned_mapping(
                user=user,
                phrase=f"governance_{question_category}",
                meaning_type='governance_preference',
                meaning_identifier=question_category,
                confidence=0.8,
            )
        except Exception as e:
            logger.debug("SLCME store skipped for governance: %s", e)


def get_calibration_question(user):
    """
    Get the next calibration question for the user.

    Only returns a question if:
    - Calibration is not complete
    - User hasn't hit daily question cap
    - Current day maps to a calibration phase

    Returns:
        dict with 'question', 'category', 'follow_up', 'meaning_type'
        or None if no question should be asked.
    """
    blueprint = _get_blueprint(user)
    if not blueprint:
        return None

    if blueprint.calibration_complete:
        return None

    day = blueprint.calibration_day

    # Find active phase
    for phase_key, phase in CALIBRATION_PHASES.items():
        start, end = phase['day_range']
        if start <= day < end:
            # Check if we've already asked from this phase today
            if not should_ask_question(user, phase_key):
                return None

            # Find an unasked question in this phase
            overrides = blueprint.governance_overrides or {}
            asked = overrides.get('calibration_asked', [])

            for q in phase['questions']:
                q_key = f"{phase_key}:{q['question'][:30]}"
                if q_key not in asked:
                    return q

            # All questions in this phase asked — move on
            return None

    # Past all phases — mark calibration complete
    if day >= 14:
        blueprint.calibration_complete = True
        blueprint.save(update_fields=['calibration_complete', 'updated_at'])

    return None


def advance_calibration_day(user):
    """
    Advance the calibration day counter by 1.

    Called once per day on first interaction.
    """
    blueprint = _get_blueprint(user)
    if not blueprint or blueprint.calibration_complete:
        return

    blueprint.calibration_day = min(14, blueprint.calibration_day + 1)
    if blueprint.calibration_day >= 14:
        blueprint.calibration_complete = True

    blueprint.save(update_fields=[
        'calibration_day', 'calibration_complete', 'updated_at',
    ])


def mark_calibration_question_asked(user, phase_key, question_text):
    """
    Record that a calibration question was surfaced to the user.

    Writes to governance_overrides['calibration_asked'] to prevent the same
    question from being shown again. Also creates an InterventionLog entry
    so _get_today_question_count() reflects the daily cap.
    """
    blueprint = _get_blueprint(user)
    if not blueprint:
        return

    overrides = blueprint.governance_overrides or {}
    asked = overrides.get('calibration_asked', [])
    q_key = f"{phase_key}:{question_text[:30]}"
    if q_key not in asked:
        asked.append(q_key)
        overrides['calibration_asked'] = asked
        blueprint.governance_overrides = overrides
        blueprint.save(update_fields=['governance_overrides', 'updated_at'])

    # Record in InterventionLog so daily cap is respected
    try:
        from .models import InterventionLog
        InterventionLog.objects.create(
            user=user,
            level=InterventionLog.LEVEL_NUDGE,
            trigger_type='governance_calibration',
            behavior_key=phase_key,
            message=question_text,
        )
    except Exception as e:
        logger.debug("InterventionLog write skipped: %s", e)


def mark_ongoing_question_shown(user, category, question_text=''):
    """
    Record that an ongoing relationship question was shown today.

    Sets last_cos_question_date to today and appends the category
    to ongoing_asked (capped at 20 entries for rotation).
    """
    blueprint = _get_blueprint(user)
    if not blueprint:
        return

    overrides = blueprint.governance_overrides or {}
    overrides['last_cos_question_date'] = timezone.now().date().isoformat()

    ongoing_asked = overrides.get('ongoing_asked', [])
    if category not in ongoing_asked:
        ongoing_asked.append(category)
    # Cap at 20 — when full, oldest categories become eligible again
    if len(ongoing_asked) > 20:
        ongoing_asked = ongoing_asked[-20:]
    overrides['ongoing_asked'] = ongoing_asked

    blueprint.governance_overrides = overrides
    blueprint.save(update_fields=['governance_overrides', 'updated_at'])

    # Record in InterventionLog for daily cap
    try:
        from .models import InterventionLog
        InterventionLog.objects.create(
            user=user,
            level=InterventionLog.LEVEL_NUDGE,
            trigger_type='governance_ongoing',
            behavior_key=category,
            message=question_text or category,
        )
    except Exception as e:
        logger.debug("InterventionLog write skipped: %s", e)


# Ongoing relationship questions — used after calibration is complete.
# Priority: profile gaps first, then relationship follow-ups, then contextual.
ONGOING_QUESTIONS = [
    {
        'category': 'motivational_triggers',
        'profile_field': 'motivational_triggers',
        'question': "What gets you energized to push through hard days?",
        'follow_up': "I'll keep that in mind when things get tough.",
        'meaning_type': 'motivational_trigger',
    },
    {
        'category': 'identity_statements',
        'profile_field': 'identity_statements',
        'question': "How would you describe yourself at your best?",
        'follow_up': "That's a strong identity anchor.",
        'meaning_type': 'identity_statement',
    },
    {
        'category': 'avoidance_patterns',
        'profile_field': 'avoidance_patterns',
        'question': "Is there something you keep putting off that you wish you'd tackle?",
        'follow_up': "I'll help you build momentum toward it.",
        'meaning_type': 'avoidance_pattern',
    },
    {
        'category': 'stated_values',
        'profile_field': 'stated_values',
        'question': "What matters most to you right now — what are you protecting?",
        'follow_up': "I'll make sure those stay front and center.",
        'meaning_type': 'stated_value',
    },
    {
        'category': 'recurring_goals',
        'profile_field': 'recurring_goals',
        'question': "What's one thing you're working toward that you'd like me to help track?",
        'follow_up': "I'll keep an eye on that for you.",
        'meaning_type': 'recurring_goal',
    },
]


def get_ongoing_relationship_question(user):
    """
    Generate a relationship-building question after calibration is complete.

    Priority:
    1. Profile gaps (categories with no data yet)
    2. Relationship follow-up (if relationship_priorities exist)
    3. Day-of-week contextual questions (Monday / Friday)

    Returns dict with 'question', 'category', 'follow_up', 'meaning_type'
    or None if no question is appropriate today.
    """
    blueprint = _get_blueprint(user)
    if not blueprint:
        return None

    # Respect daily cap
    if not should_ask_question(user, 'ongoing'):
        return None

    # Only 1 CoS question per calendar day
    overrides = blueprint.governance_overrides or {}
    last_question_date = overrides.get('last_cos_question_date')
    today_str = timezone.now().date().isoformat()
    if last_question_date == today_str:
        return None

    declined = overrides.get('declined_categories', [])
    recently_asked = overrides.get('ongoing_asked', [])

    # Try profile-gap questions first
    try:
        from apps.core.ai_learning.learning_extractor import get_learned_profile
        profile = get_learned_profile(user)

        for q_def in ONGOING_QUESTIONS:
            category = q_def['category']
            profile_field = q_def.get('profile_field')

            if category in declined or category in recently_asked:
                continue

            if profile_field and not getattr(profile, profile_field, []):
                return {
                    'question': q_def['question'],
                    'category': category,
                    'follow_up': q_def['follow_up'],
                    'meaning_type': q_def['meaning_type'],
                }

        # Relationship follow-up — if we know who matters to the user
        if 'relationship_followup' not in declined \
                and 'relationship_followup' not in recently_asked:
            rel_priorities = getattr(profile, 'relationship_priorities', [])
            if rel_priorities:
                person = rel_priorities[0].split()[0] if rel_priorities[0] else ''
                q = (f"How are things going with {person}?"
                     if person
                     else "How are things with the people who matter most to you?")
                return {
                    'question': q,
                    'category': 'relationship_followup',
                    'follow_up': "Good to hear — those connections matter.",
                    'meaning_type': 'relationship_checkin',
                }

    except Exception as e:
        logger.debug("Ongoing question profile check failed: %s", e)

    # Day-of-week contextual fallback
    day = timezone.now().weekday()  # 0=Monday
    if day == 0 and 'weekly_intention' not in recently_asked:
        return {
            'question': "What's one thing you want to make sure happens this week?",
            'category': 'weekly_intention',
            'follow_up': "I'll keep that front of mind.",
            'meaning_type': 'recurring_goal',
        }
    elif day == 4 and 'weekly_reflection' not in recently_asked:
        return {
            'question': "What went well this week that you want to remember?",
            'category': 'weekly_reflection',
            'follow_up': "Good to note — pattern recognition builds momentum.",
            'meaning_type': 'stated_value',
        }

    return None


def build_governance_instructions(user):
    """
    Build system prompt instructions for governance compliance.

    Returns a compact instruction block that tells the LLM how to
    modulate its behavior based on the user's governance profile.

    Returns:
        str — governance instructions for system prompt.
    """
    blueprint = _get_blueprint(user)
    if not blueprint:
        return ""

    lines = []
    lines.append("--- GOVERNANCE PROFILE ---")

    # Accountability style
    style = blueprint.accountability_style
    if style == 'light':
        lines.append("Accountability: LIGHT — be gentle, suggest rather than push. "
                     "Frame everything as optional. Use soft language.")
    elif style == 'firm':
        lines.append("Accountability: FIRM — be direct and hold the user accountable. "
                     "Name missed commitments. Use confident language. "
                     "Don't sugarcoat, but stay respectful.")
    else:
        lines.append("Accountability: STANDARD — balanced approach. "
                     "Suggest clearly, note missed items without judgment, "
                     "encourage follow-through.")

    # Question frequency
    freq = blueprint.question_frequency
    if freq == 'low':
        lines.append("Questions: MINIMAL — only ask when essential. "
                     "Prefer to act on what you already know.")
    elif freq == 'high':
        lines.append("Questions: OPEN — feel free to ask clarifying questions "
                     "and check in regularly. The user welcomes it.")
    else:
        lines.append("Questions: MODERATE — ask when helpful, "
                     "but don't over-question. 1-2 questions per session max.")

    # Sensitivity tags
    tags = blueprint.sensitivity_tags or []
    if tags:
        tag_str = ', '.join(tags)
        lines.append(f"Sensitivity: Be extra gentle with these topics: {tag_str}. "
                     "No pressure, no judgment, respect boundaries.")

    # Calibration status
    if not blueprint.calibration_complete:
        lines.append("Calibration: Still learning this user's preferences. "
                     "You may ask ONE getting-to-know-you question per session "
                     "if it feels natural.")

    # Declined categories
    overrides = blueprint.governance_overrides or {}
    declined = overrides.get('declined_categories', [])
    if declined:
        lines.append(f"Off-limits topics (user declined): {', '.join(declined)}. "
                     "Do NOT ask about these again unless the user brings them up.")

    # Reflections and relationships
    if blueprint.event_reflections_enabled:
        lines.append("Post-event reflections: ENABLED — you may follow up "
                     "after meetings, workouts, and social events.")
    else:
        lines.append("Post-event reflections: DISABLED — do not follow up after events.")

    if blueprint.relationship_suggestions_enabled:
        lines.append("Relationship suggestions: ENABLED — suggest "
                     "reconnection and scheduling time with important people.")
    else:
        lines.append("Relationship suggestions: DISABLED — do not suggest "
                     "relationship actions unless explicitly asked.")

    # Standard "why" response
    lines.append("If the user asks 'why are you asking' about ANY question, "
                 f'respond: "{WHY_RESPONSE}"')

    lines.append("--- END GOVERNANCE ---")

    return '\n'.join(lines)


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _get_blueprint(user):
    """Get or create blueprint for user, with ImportError guard."""
    try:
        from .models import PersonalOperatingBlueprint
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(user)
        return blueprint
    except Exception as e:
        logger.debug("Governance: blueprint unavailable: %s", e)
        return None


def _get_today_question_count(user):
    """Count CoS questions asked today (via intervention log or SLCME)."""
    try:
        from .models import InterventionLog
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return InterventionLog.objects.filter(
            user=user,
            trigger_type__startswith='governance_',
            created_at__gte=today_start,
        ).count()
    except Exception:
        return 0


def _get_preferred_channel(user):
    """Get user's preferred notification channel."""
    try:
        prefs = user.preferences
        if prefs.intelligence_sms_enabled:
            return 'sms'
        if prefs.intelligence_email_enabled:
            return 'email'
        return 'in_app'
    except Exception:
        return 'in_app'
