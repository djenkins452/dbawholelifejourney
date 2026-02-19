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
    - get_calibration_question(user) -> dict or None  [deprecated]
    - mark_calibration_question_asked(user, phase_key, question_text) -> None  [deprecated]
    - get_ongoing_relationship_question(user) -> dict or None
    - mark_ongoing_question_shown(user, category, question_text='') -> None
    - build_governance_instructions(user) -> str
    - advance_calibration_day(user) -> None  [deprecated]

    Conversational Calibration API (Phase 5):
    - get_calibration_state(user) -> dict or None
    - get_next_calibration_question(user) -> dict or None
    - advance_calibration_stage(user) -> None
    - record_calibration_answer(user, question_key, answer_text) -> None
    - mark_calibration_welcome_shown(user) -> None
    - pause_calibration(user) -> None
    - resume_calibration(user) -> None
    - reset_calibration_for_conversational(user) -> bool
    - build_calibration_system_injection(user) -> str

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
# CALIBRATION QUESTIONS — Conversational (Phase 5 rewrite)
# =============================================================================

# Flat ordered list — no day-range gating. Asked conversationally in chat.
CALIBRATION_QUESTIONS = [
    # Core people
    {
        'key': 'core_people_1',
        'category': 'core_people',
        'question': "Who are the most important people in your daily life?",
        'follow_up': "I'll remember them so I can help you stay connected.",
        'meaning_type': 'core_people',
    },
    {
        'key': 'core_people_2',
        'category': 'core_people',
        'question': "Is there anyone you've been meaning to reconnect with?",
        'follow_up': "I can help you find time for that.",
        'meaning_type': 'reconnection_target',
    },
    # Non-negotiables
    {
        'key': 'non_negotiables_1',
        'category': 'non_negotiables',
        'question': "What activities are sacred to you — things you'd never want to skip?",
        'follow_up': "Those are the first things I protect.",
        'meaning_type': 'sacred_activity',
    },
    {
        'key': 'non_negotiables_2',
        'category': 'non_negotiables',
        'question': "What time of day do you feel most productive?",
        'follow_up': "I'll keep that in mind when it matters most.",
        'meaning_type': 'peak_productivity',
    },
    # Preferred activities
    {
        'key': 'preferred_1',
        'category': 'preferred_activities',
        'question': "What do you enjoy doing when you have free time?",
        'follow_up': "I'll suggest these when I find open windows in your week.",
        'meaning_type': 'leisure_preference',
    },
    {
        'key': 'preferred_2',
        'category': 'preferred_activities',
        'question': "Do you prefer mornings or evenings for personal time?",
        'follow_up': "That helps me plan better.",
        'meaning_type': 'personal_time_preference',
    },
    # Negotiables
    {
        'key': 'negotiables_1',
        'category': 'negotiables',
        'question': "What can be moved or dropped when things get busy?",
        'follow_up': "Good — those stay flexible when curveballs hit.",
        'meaning_type': 'negotiable_activity',
    },
    {
        'key': 'checkin_time',
        'category': 'negotiables',
        'question': "When I check in with questions, do you prefer morning or evening?",
        'follow_up': "I'll time my questions accordingly.",
        'meaning_type': 'checkin_time_preference',
    },
    # Accountability & communication style
    {
        'key': 'accountability_style',
        'category': 'accountability',
        'question': (
            "When you fall behind on something important, how do you want me "
            "to handle it? Some people want a gentle nudge, others prefer a "
            "direct heads-up."
        ),
        'follow_up': "Got it. I'll match that energy.",
        'meaning_type': 'accountability_preference',
    },
    {
        'key': 'communication_frequency',
        'category': 'communication',
        'question': (
            "How often is it okay for me to reach out with questions or "
            "observations? Some people like regular check-ins, others prefer "
            "I keep it minimal."
        ),
        'follow_up': "Understood. I'll respect that boundary.",
        'meaning_type': 'communication_frequency',
    },
    # Focus areas
    {
        'key': 'module_focus',
        'category': 'focus_areas',
        'question': (
            "Of everything you track here — health, goals, journaling, faith, "
            "tasks — which areas matter most to you right now?"
        ),
        'follow_up': "I'll prioritize those in our conversations.",
        'meaning_type': 'module_priority',
    },
]

# Backward-compat alias for old code referencing CALIBRATION_PHASES
CALIBRATION_PHASES = {}  # Deprecated — use CALIBRATION_QUESTIONS


# Welcome and completion messages for conversational calibration
# NOTE: This is a TEMPLATE — the actual welcome is built dynamically in
# build_calibration_system_injection() using real user data.
CALIBRATION_WELCOME_TEMPLATE = (
    "I've already been looking at what you've been doing here. "
    "{data_summary} "
    "But numbers only tell me so much. I want to understand what actually "
    "matters to you — what's a priority, what's secondary, what I should "
    "protect when things get busy. I've got a few questions to fill in "
    "the gaps. You can pause anytime by saying 'that's enough for now.'"
)

# Fallback for users with no data at all
CALIBRATION_WELCOME_NO_DATA = (
    "I'm your Chief of Staff — think of me as someone who pays attention "
    "to what matters to you and helps you stay on track. Before I can do "
    "that, I need to understand you. Not the surface stuff — what actually "
    "drives you, what your priorities are, and what you'd want me to protect "
    "when things get busy. A few quick questions and I'll be up to speed. "
    "You can pause anytime by saying 'that's enough for now.'"
)

# Backward-compat alias for dashboard views that import this name
CALIBRATION_WELCOME_MESSAGE = CALIBRATION_WELCOME_NO_DATA

CALIBRATION_COMPLETION_MESSAGE = (
    "That's everything I needed to ask. I have a much better picture of what "
    "matters to you now. If I ever see your actions drifting from what you told "
    "me matters, I will say something."
)

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
    1. During conversational calibration: always allow (no daily cap)
    2. Daily question count vs frequency cap
    3. Whether user previously declined this category

    Args:
        user: Django User instance.
        question_category: str — category of question being considered.

    Returns:
        bool — True if question is appropriate.
    """
    blueprint = _get_blueprint(user)
    if not blueprint:
        return False

    # During active conversational calibration, skip daily cap
    if not blueprint.calibration_complete:
        overrides = blueprint.governance_overrides or {}
        if not overrides.get('calibration_paused', False):
            return True

    # Check daily cap (post-calibration only)
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


# =============================================================================
# CONVERSATIONAL CALIBRATION (Phase 5 Rewrite)
# =============================================================================


def get_calibration_state(user):
    """
    Get the full calibration state for a user.

    Returns:
        dict with keys: active, paused, welcome_shown, stage,
        total_questions, complete, next_question — or None if no blueprint.
    """
    blueprint = _get_blueprint(user)
    if not blueprint:
        return None

    overrides = blueprint.governance_overrides or {}

    return {
        'active': not blueprint.calibration_complete,
        'paused': overrides.get('calibration_paused', False),
        'welcome_shown': overrides.get('calibration_welcome_shown', False),
        'stage': overrides.get('calibration_stage', 0),
        'total_questions': len(CALIBRATION_QUESTIONS),
        'complete': blueprint.calibration_complete,
        'next_question': get_next_calibration_question(user),
    }


def get_next_calibration_question(user):
    """
    Get the next unanswered calibration question regardless of day.

    No day-range gating, no daily cap. Returns None if calibration
    is complete, paused, or all questions have been asked.

    Returns:
        dict with key, question, category, follow_up, meaning_type,
        question_number, total_questions — or None.
    """
    blueprint = _get_blueprint(user)
    if not blueprint:
        return None
    if blueprint.calibration_complete:
        return None

    overrides = blueprint.governance_overrides or {}
    if overrides.get('calibration_paused', False):
        return None

    stage = overrides.get('calibration_stage', 0)
    if stage >= len(CALIBRATION_QUESTIONS):
        # All questions asked — mark complete
        _complete_calibration(user, blueprint)
        return None

    q = CALIBRATION_QUESTIONS[stage]
    return {
        **q,
        'question_number': stage + 1,
        'total_questions': len(CALIBRATION_QUESTIONS),
    }


def advance_calibration_stage(user):
    """
    Advance to the next calibration question.
    Called after the user answers a calibration question.
    """
    blueprint = _get_blueprint(user)
    if not blueprint:
        return

    overrides = blueprint.governance_overrides or {}
    stage = overrides.get('calibration_stage', 0)
    overrides['calibration_stage'] = stage + 1

    if stage + 1 >= len(CALIBRATION_QUESTIONS):
        blueprint.governance_overrides = overrides
        _complete_calibration(user, blueprint)
    else:
        blueprint.governance_overrides = overrides
        blueprint.save(update_fields=['governance_overrides', 'updated_at'])


def record_calibration_answer(user, question_key, answer_text):
    """
    Record a user's answer to a calibration question.

    Stores in governance_overrides['calibration_answers'], advances
    the calibration stage, and logs to InterventionLog + SLCME.
    """
    blueprint = _get_blueprint(user)
    if not blueprint:
        return

    overrides = blueprint.governance_overrides or {}
    answers = overrides.get('calibration_answers', {})
    answers[question_key] = answer_text[:500]
    overrides['calibration_answers'] = answers
    blueprint.governance_overrides = overrides
    blueprint.save(update_fields=['governance_overrides', 'updated_at'])

    # Find question definition for metadata
    q_def = next(
        (q for q in CALIBRATION_QUESTIONS if q['key'] == question_key), None
    )

    # Store in SLCME for long-term learning
    if q_def:
        try:
            from apps.core.ai_memory.memory_engine import store_learned_mapping
            store_learned_mapping(
                user=user,
                phrase=f"calibration_{question_key}",
                meaning_type=q_def.get('meaning_type', 'calibration_response'),
                meaning_identifier=question_key,
                confidence=0.9,
            )
        except Exception as e:
            logger.debug("SLCME store skipped for calibration: %s", e)

    # Record in InterventionLog for audit trail
    try:
        from .models import InterventionLog
        InterventionLog.objects.create(
            user=user,
            level=InterventionLog.LEVEL_NUDGE,
            trigger_type='governance_calibration',
            behavior_key=question_key,
            message=answer_text[:500],
        )
    except Exception:
        pass

    # Advance to next question
    advance_calibration_stage(user)


def mark_calibration_welcome_shown(user):
    """Mark that the calibration welcome message has been shown."""
    blueprint = _get_blueprint(user)
    if not blueprint:
        return
    overrides = blueprint.governance_overrides or {}
    overrides['calibration_welcome_shown'] = True
    blueprint.governance_overrides = overrides
    blueprint.save(update_fields=['governance_overrides', 'updated_at'])


def pause_calibration(user):
    """Pause calibration. User can resume next session."""
    blueprint = _get_blueprint(user)
    if not blueprint:
        return
    overrides = blueprint.governance_overrides or {}
    overrides['calibration_paused'] = True
    blueprint.governance_overrides = overrides
    blueprint.save(update_fields=['governance_overrides', 'updated_at'])


def resume_calibration(user):
    """Resume calibration from saved stage."""
    blueprint = _get_blueprint(user)
    if not blueprint:
        return
    overrides = blueprint.governance_overrides or {}
    overrides['calibration_paused'] = False
    blueprint.governance_overrides = overrides
    blueprint.save(update_fields=['governance_overrides', 'updated_at'])


def reset_calibration_for_conversational(user):
    """
    Reset calibration for users who completed the old 14-day trickle
    but never did conversational onboarding.

    Only resets if calibration_complete is True but no 'calibration_stage'
    key exists in governance_overrides (old system indicator).

    Returns:
        bool — True if reset was performed.
    """
    blueprint = _get_blueprint(user)
    if not blueprint:
        return False

    overrides = blueprint.governance_overrides or {}

    # Only reset if they completed the OLD system (no calibration_stage key)
    if blueprint.calibration_complete and 'calibration_stage' not in overrides:
        blueprint.calibration_complete = False
        overrides['calibration_stage'] = 0
        overrides['calibration_paused'] = False
        overrides['calibration_welcome_shown'] = False
        overrides['calibration_reset_from_old'] = True
        overrides['calibration_reset_at'] = timezone.now().isoformat()
        blueprint.governance_overrides = overrides
        blueprint.save(update_fields=[
            'calibration_complete', 'governance_overrides', 'updated_at',
        ])
        return True
    return False


def _gather_user_snapshot(user):
    """
    Gather what the system already knows about a user for calibration.

    Returns a dict with data points the AI can reference when asking
    calibration questions, so it sounds informed rather than generic.
    """
    snapshot = {
        'has_data': False,
        'modules_active': [],
        'health': {},
        'goals': {},
        'journal': {},
        'faith': {},
        'tasks': {},
        'habits': {},
        'relationships': [],
    }

    # Health data
    try:
        from apps.core.ai_state.state_engine import get_state_value
        weight = get_state_value(user, 'health.weight_current')
        if weight:
            snapshot['health']['weight'] = weight
            snapshot['health']['weight_trend'] = get_state_value(
                user, 'health.weight_trend') or 'unknown'
            snapshot['has_data'] = True
    except Exception:
        pass

    # Medicines (Medicine model, not MedicineSchedule — schedules have no user FK)
    try:
        from apps.health.models import Medicine
        med_count = Medicine.objects.filter(
            user=user, is_active=True).count()
        if med_count:
            snapshot['health']['medicine_count'] = med_count
            snapshot['modules_active'].append('medicines')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Workouts (WorkoutSession, not FitnessLog)
    try:
        from apps.health.models import WorkoutSession
        from django.utils import timezone as tz
        week_ago = tz.now() - tz.timedelta(days=7)
        workout_count = WorkoutSession.objects.filter(
            user=user, date__gte=week_ago.date()).count()
        if workout_count:
            snapshot['health']['workouts_7d'] = workout_count
            snapshot['modules_active'].append('fitness')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Goals (LifeGoal, not Goal)
    try:
        from apps.purpose.models import LifeGoal
        active_goals = LifeGoal.objects.filter(
            user=user, status='active'
        ).values_list('title', flat=True)[:5]
        if active_goals:
            snapshot['goals']['active'] = list(active_goals)
            snapshot['goals']['count'] = len(active_goals)
            snapshot['modules_active'].append('goals')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Journal
    try:
        from apps.journal.models import JournalEntry
        from django.utils import timezone as tz
        total_entries = JournalEntry.objects.filter(user=user).count()
        if total_entries:
            week_entries = JournalEntry.objects.filter(
                user=user,
                entry_date__gte=(tz.now() - tz.timedelta(days=7)).date()
            ).count()
            snapshot['journal']['total'] = total_entries
            snapshot['journal']['week'] = week_entries
            snapshot['modules_active'].append('journal')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Faith (PrayerRequest, not Prayer)
    try:
        from apps.faith.models import PrayerRequest
        prayer_count = PrayerRequest.objects.filter(user=user).count()
        if prayer_count:
            snapshot['faith']['prayer_count'] = prayer_count
            snapshot['modules_active'].append('faith')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Tasks (is_completed=False, not status='pending')
    try:
        from apps.life.models import Task
        overdue = Task.objects.filter(
            user=user, is_completed=False,
            due_date__lt=timezone.now().date()
        ).count()
        active = Task.objects.filter(
            user=user, is_completed=False).count()
        if active:
            snapshot['tasks']['active'] = active
            snapshot['tasks']['overdue'] = overdue
            snapshot['modules_active'].append('tasks')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Habit goals (status='active', not is_active=True)
    try:
        from apps.purpose.models import HabitGoal
        habits = HabitGoal.objects.filter(
            user=user, status='active'
        ).values_list('name', flat=True)[:5]
        if habits:
            snapshot['habits']['active'] = list(habits)
            snapshot['modules_active'].append('habits')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Sleep tracking
    try:
        from apps.health.models import SleepEntry
        from django.utils import timezone as tz
        week_ago = tz.now() - tz.timedelta(days=7)
        sleep_count = SleepEntry.objects.filter(
            user=user, date__gte=week_ago.date()).count()
        if sleep_count:
            snapshot['health']['sleep_entries_7d'] = sleep_count
            if 'sleep' not in snapshot['modules_active']:
                snapshot['modules_active'].append('sleep')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Steps tracking
    try:
        from apps.health.models import StepsEntry
        from django.utils import timezone as tz
        week_ago = tz.now() - tz.timedelta(days=7)
        steps_count = StepsEntry.objects.filter(
            user=user, date__gte=week_ago.date()).count()
        if steps_count:
            snapshot['health']['steps_entries_7d'] = steps_count
            if 'steps' not in snapshot['modules_active']:
                snapshot['modules_active'].append('steps')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Nutrition / food tracking
    try:
        from apps.health.models import FoodEntry
        from django.utils import timezone as tz
        week_ago = tz.now() - tz.timedelta(days=7)
        food_count = FoodEntry.objects.filter(
            user=user, date__gte=week_ago.date()).count()
        if food_count:
            snapshot['health']['food_entries_7d'] = food_count
            snapshot['modules_active'].append('nutrition')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Fasting
    try:
        from apps.health.models import FastingWindow
        from django.utils import timezone as tz
        month_ago = tz.now() - tz.timedelta(days=30)
        fast_count = FastingWindow.objects.filter(
            user=user, start_time__gte=month_ago).count()
        if fast_count:
            snapshot['health']['fasts_30d'] = fast_count
            snapshot['modules_active'].append('fasting')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Vitals (blood pressure, glucose, heart rate)
    try:
        from apps.health.models import (
            BloodPressureEntry, GlucoseEntry, HeartRateEntry,
        )
        vitals = []
        if BloodPressureEntry.objects.filter(user=user).exists():
            vitals.append('blood pressure')
        if GlucoseEntry.objects.filter(user=user).exists():
            vitals.append('glucose')
        if HeartRateEntry.objects.filter(user=user).exists():
            vitals.append('heart rate')
        if vitals:
            snapshot['health']['vitals_tracked'] = vitals
            snapshot['modules_active'].append('vitals')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Medical providers
    try:
        from apps.health.models import MedicalProvider
        provider_count = MedicalProvider.objects.filter(user=user).count()
        if provider_count:
            snapshot['health']['provider_count'] = provider_count
            snapshot['modules_active'].append('providers')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Lab results
    try:
        from apps.medical.models import LabResult
        lab_count = LabResult.objects.filter(user=user).count()
        if lab_count:
            snapshot['health']['lab_results'] = lab_count
            snapshot['modules_active'].append('labs')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Bible reading plans
    try:
        from apps.faith.models import UserReadingPlan
        reading_plans = UserReadingPlan.objects.filter(
            user=user, status='active').count()
        if reading_plans:
            snapshot['faith']['reading_plans'] = reading_plans
            if 'faith' not in snapshot['modules_active']:
                snapshot['modules_active'].append('faith')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Annual direction / word of the year
    try:
        from apps.purpose.models import AnnualDirection
        from django.utils import timezone as tz
        current_year = tz.now().year
        direction = AnnualDirection.objects.filter(
            user=user, year=current_year).first()
        if direction:
            snapshot['purpose'] = {}
            if direction.word_of_year:
                snapshot['purpose']['word_of_year'] = direction.word_of_year
            if direction.theme:
                snapshot['purpose']['theme'] = direction.theme
            snapshot['has_data'] = True
    except Exception:
        pass

    # Finance
    try:
        from apps.finance.models import FinancialAccount, Budget
        accounts = FinancialAccount.objects.filter(user=user).count()
        budgets = Budget.objects.filter(user=user, is_active=True).count()
        if accounts or budgets:
            snapshot['finance'] = {
                'accounts': accounts,
                'budgets': budgets,
            }
            snapshot['modules_active'].append('finance')
            snapshot['has_data'] = True
    except Exception:
        pass

    # Change intentions
    try:
        from apps.purpose.models import ChangeIntention
        intentions = ChangeIntention.objects.filter(
            user=user, status='active'
        ).values_list('intention', flat=True)[:3]
        if intentions:
            snapshot['goals']['intentions'] = list(intentions)
            snapshot['has_data'] = True
    except Exception:
        pass

    return snapshot


def _build_data_summary(snapshot):
    """
    Build a natural-language summary of what the system knows about the user.
    Used in the calibration welcome message and system prompt injection.
    """
    parts = []

    # Weight
    if snapshot['health'].get('weight'):
        trend = snapshot['health'].get('weight_trend', '')
        trend_str = f" and it's trending {trend}" if trend and trend != 'unknown' else ""
        parts.append(
            f"You're tracking your weight at {snapshot['health']['weight']} lb{trend_str}."
        )

    # Medicines
    if snapshot['health'].get('medicine_count'):
        parts.append(
            f"You're managing {snapshot['health']['medicine_count']} medicines."
        )

    # Workouts
    if snapshot['health'].get('workouts_7d'):
        parts.append(
            f"You logged {snapshot['health']['workouts_7d']} workouts this week."
        )

    # Sleep
    if snapshot['health'].get('sleep_entries_7d'):
        parts.append(
            f"You've logged sleep {snapshot['health']['sleep_entries_7d']} times this week."
        )

    # Steps
    if snapshot['health'].get('steps_entries_7d'):
        parts.append("You're tracking your steps.")

    # Nutrition
    if snapshot['health'].get('food_entries_7d'):
        parts.append(
            f"You've logged {snapshot['health']['food_entries_7d']} food entries this week."
        )

    # Fasting
    if snapshot['health'].get('fasts_30d'):
        parts.append(
            f"You've done {snapshot['health']['fasts_30d']} fasts in the last month."
        )

    # Vitals
    if snapshot['health'].get('vitals_tracked'):
        vitals = snapshot['health']['vitals_tracked']
        parts.append(
            f"You're tracking {', '.join(vitals)}."
        )

    # Providers
    if snapshot['health'].get('provider_count'):
        parts.append(
            f"You have {snapshot['health']['provider_count']} medical providers on file."
        )

    # Lab results
    if snapshot['health'].get('lab_results'):
        parts.append(
            f"You have {snapshot['health']['lab_results']} lab results stored."
        )

    # Goals — show ALL of them
    if snapshot['goals'].get('active'):
        goal_names = snapshot['goals']['active']
        names = ', '.join(f'"{g}"' for g in goal_names)
        parts.append(f"Your active goals: {names}.")

    # Change intentions
    if snapshot['goals'].get('intentions'):
        intentions = snapshot['goals']['intentions']
        parts.append(
            f"You've set intentions: {', '.join(intentions)}."
        )

    # Habits
    if snapshot['habits'].get('active'):
        habit_names = snapshot['habits']['active']
        parts.append(
            f"You're building habits: {', '.join(habit_names)}."
        )

    # Journal
    if snapshot['journal'].get('total'):
        parts.append(
            f"You've written {snapshot['journal']['total']} journal entries"
            f" ({snapshot['journal'].get('week', 0)} this week)."
        )

    # Faith
    faith_parts = []
    if snapshot['faith'].get('prayer_count'):
        faith_parts.append(
            f"{snapshot['faith']['prayer_count']} prayer requests")
    if snapshot['faith'].get('reading_plans'):
        faith_parts.append(
            f"{snapshot['faith']['reading_plans']} active reading plans")
    if faith_parts:
        parts.append(f"Faith: {', '.join(faith_parts)}.")

    # Purpose / word of the year
    if snapshot.get('purpose'):
        if snapshot['purpose'].get('word_of_year'):
            parts.append(
                f"Your word of the year is \"{snapshot['purpose']['word_of_year']}\"."
            )
        if snapshot['purpose'].get('theme'):
            parts.append(
                f"Your annual theme: \"{snapshot['purpose']['theme']}\"."
            )

    # Tasks
    if snapshot['tasks'].get('active'):
        task_str = f"You have {snapshot['tasks']['active']} active tasks"
        if snapshot['tasks'].get('overdue'):
            task_str += f" ({snapshot['tasks']['overdue']} overdue)"
        parts.append(task_str + ".")

    # Finance
    if snapshot.get('finance'):
        finance_parts = []
        if snapshot['finance'].get('accounts'):
            finance_parts.append(
                f"{snapshot['finance']['accounts']} financial accounts")
        if snapshot['finance'].get('budgets'):
            finance_parts.append(
                f"{snapshot['finance']['budgets']} active budgets")
        if finance_parts:
            parts.append(f"Finance: {', '.join(finance_parts)}.")

    return ' '.join(parts) if parts else ''


def _build_question_context(question_key, snapshot):
    """
    Build data-aware context for a specific calibration question.

    Returns a string the AI can use to make the question informed,
    or empty string if no relevant data exists.
    """
    contexts = {
        'core_people_1': lambda s: (
            f"You have {', '.join(s['relationships'])} marked as important relationships. "
            "Use this when asking about the people in their life — confirm or expand."
        ) if s.get('relationships') else '',

        'non_negotiables_1': lambda s: (
            "DATA YOU HAVE: "
            + (f"They work out ~{s['health']['workouts_7d']}x/week. " if s['health'].get('workouts_7d') else '')
            + (f"They journal ~{s['journal']['week']}x/week. " if s['journal'].get('week') else '')
            + (f"They track {s['faith']['prayer_count']} prayers. " if s['faith'].get('prayer_count') else '')
            + (f"They manage {s['health']['medicine_count']} medicines daily. " if s['health'].get('medicine_count') else '')
            + "Reference what you see them doing consistently when asking what's sacred to them."
        ) if any([
            s['health'].get('workouts_7d'),
            s['journal'].get('week'),
            s['faith'].get('prayer_count'),
            s['health'].get('medicine_count'),
        ]) else '',

        'module_focus': lambda s: (
            f"MODULES THEY ACTIVELY USE: {', '.join(s['modules_active'])}. "
            "Don't ask generically which areas matter — tell them what you see them using "
            "and ask which of those they want you to prioritize and protect."
        ) if s.get('modules_active') else '',
    }

    builder = contexts.get(question_key)
    if builder:
        try:
            return builder(snapshot)
        except Exception:
            return ''
    return ''


def build_calibration_system_injection(user):
    """
    Build system prompt injection for conversational calibration.

    Uses actual user data to make the conversation intelligent — the AI
    references what it already knows about the user rather than asking
    generic questions.

    Returns:
        str — system prompt block, or empty string if not in calibration.
    """
    blueprint = _get_blueprint(user)
    if not blueprint:
        return ""
    if blueprint.calibration_complete:
        return ""

    overrides = blueprint.governance_overrides or {}
    if overrides.get('calibration_paused', False):
        return ""

    # Auto-complete stale alignment sessions — calibration replaces them.
    try:
        from apps.core.ai_governance.models import GovernanceAlignmentSession
        session = GovernanceAlignmentSession.objects.filter(user=user).first()
        if session and not session.is_complete:
            session.is_complete = True
            session.save(update_fields=['is_complete', 'updated_at'])
            logger.info(
                "Auto-completed stale alignment session for %s "
                "(superseded by calibration)", user.email
            )
    except Exception:
        pass

    next_q = get_next_calibration_question(user)
    if not next_q:
        return ""

    # Gather what the system already knows
    snapshot = _gather_user_snapshot(user)
    data_summary = _build_data_summary(snapshot)

    lines = [
        "##############################################################",
        "# MANDATORY OVERRIDE — GETTING TO KNOW YOU SESSION           #",
        "# This section SUPERSEDES all other instructions below.      #",
        "# You are in a calibration conversation. Your ONLY job is    #",
        "# to follow these instructions. Ignore the base prompt's     #",
        "# 'OPENING A NEW CONVERSATION' section entirely.             #",
        "##############################################################",
    ]
    lines.append("")

    welcome_shown = overrides.get('calibration_welcome_shown', False)

    if not welcome_shown:
        # First interaction — introduce yourself WITH what you already know
        if snapshot['has_data'] and data_summary:
            welcome = CALIBRATION_WELCOME_TEMPLATE.format(
                data_summary=data_summary)
        else:
            welcome = CALIBRATION_WELCOME_NO_DATA

        lines.append("## YOUR ROLE RIGHT NOW")
        lines.append(
            "This is your FIRST conversation with this person. You are their "
            "Chief of Staff — someone who has already analyzed everything they "
            "have been doing in this app. You are NOT a blank slate. You have "
            "studied their data and you are coming to THEM with observations."
        )
        lines.append("")
        lines.append("## WHAT TO SAY (follow this structure closely)")
        lines.append(
            f'"{welcome}"'
        )
        lines.append("")
        lines.append(
            "Then naturally transition into the first question below."
        )
        lines.append("")
        lines.append("## ABSOLUTE PROHIBITIONS FOR THIS MESSAGE")
        lines.append(
            "- Do NOT say 'What area would you like to focus on today?'\n"
            "- Do NOT say 'Let me know how I can help'\n"
            "- Do NOT give a data dump and then ask a generic question\n"
            "- Do NOT ask 'What are your goals?' — you already KNOW their goals\n"
            "- Do NOT summarize their data without connecting it to a question\n"
            "- Your response MUST end with the calibration question below"
        )
        lines.append("")
    else:
        # Continuing calibration — stay focused
        lines.append("## YOUR ROLE RIGHT NOW")
        lines.append(
            "You are in an active getting-to-know-you conversation. "
            "Your ONLY job is to ask the question below. Do NOT give "
            "general advice, data overviews, or helpful suggestions. "
            "Stay in THIS conversation."
        )
        lines.append("")

    # Inject what the system knows so the AI can reference it
    if snapshot['has_data']:
        lines.append("## WHAT YOU ALREADY KNOW ABOUT THIS PERSON")
        lines.append(data_summary)
        if snapshot.get('modules_active'):
            lines.append(
                f"Modules in active use: {', '.join(snapshot['modules_active'])}")
        lines.append("")
        lines.append(
            "USE THIS DATA when asking questions. Do not ask things you "
            "already know — instead state what you see and ask them to "
            "confirm, correct, or expand. Example: if you see they work "
            "out 5 days a week, do not ask 'do you exercise?' — instead "
            "say 'your workouts look pretty consistent — is fitness one "
            "of your non-negotiables or is something else more sacred to "
            "you?'"
        )
        lines.append("")

    # Include what we've learned so far from calibration answers
    answers = overrides.get('calibration_answers', {})
    if answers:
        lines.append("## WHAT THEY HAVE TOLD YOU SO FAR")
        for key, answer in answers.items():
            q_def = next(
                (q for q in CALIBRATION_QUESTIONS if q['key'] == key), None
            )
            if q_def:
                label = q_def['category'].replace('_', ' ').title()
                lines.append(f"  - {label}: {answer[:200]}")
        lines.append("")

    # Build data-aware question context
    q_context = _build_question_context(next_q['key'], snapshot)

    lines.append("## QUESTION YOU MUST ASK")
    lines.append(
        f"Question {next_q['question_number']} of {next_q['total_questions']}: "
        f"{next_q['question']}"
    )
    if q_context:
        lines.append(f"Data context for this question: {q_context}")
    lines.append("")
    lines.append(
        "Rephrase this question in your own words using what you know "
        "about this person. Your message MUST contain this question. "
        "This is mandatory — do not skip it or replace it with something else."
    )

    # Preview next question so AI can transition naturally
    next_stage = overrides.get('calibration_stage', 0) + 1
    if next_stage < len(CALIBRATION_QUESTIONS):
        peek_q = CALIBRATION_QUESTIONS[next_stage]
        lines.append(
            f"(After they answer, the next question will be: {peek_q['question']})"
        )
    else:
        lines.append(
            "This is the LAST question. After they answer, say something like: "
            f'"{CALIBRATION_COMPLETION_MESSAGE}"'
        )

    lines.append("")
    lines.append("## RULES")
    lines.append(
        "1. Your message MUST end with the question above (rephrased naturally).\n"
        "2. ONE question per message — never batch multiple questions.\n"
        "3. If the user just said hello or is resuming, briefly greet them "
        "with a data-informed observation, then ask the question.\n"
        "4. If the user gave a thoughtful answer, briefly acknowledge it "
        "(1 sentence) then ask the next question.\n"
        "5. If they say 'pause', 'enough', 'later', or similar, respect "
        "it immediately.\n"
        "6. Never use words like 'calibration', 'governance', 'stage', "
        "'tier', 'module classification', or 'identity pillar'.\n"
        "7. Keep it conversational — you're getting to know a person, "
        "not filling out a form.\n"
        "8. NEVER ask something you can already answer from their data. "
        "State what you see, then ask them to confirm or correct."
    )
    lines.append("")
    lines.append("##############################################################")
    lines.append("# END MANDATORY OVERRIDE                                     #")
    lines.append("##############################################################")

    return '\n'.join(lines)


def _complete_calibration(user, blueprint=None):
    """Mark calibration as complete and set final state."""
    if not blueprint:
        blueprint = _get_blueprint(user)
    if not blueprint:
        return

    blueprint.calibration_complete = True
    overrides = blueprint.governance_overrides or {}
    overrides['calibration_completed_at'] = timezone.now().isoformat()
    overrides['calibration_version'] = 'conversational_v1'
    blueprint.governance_overrides = overrides
    blueprint.save(update_fields=[
        'calibration_complete', 'governance_overrides', 'updated_at',
    ])


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
        overrides_gov = blueprint.governance_overrides or {}
        if overrides_gov.get('calibration_paused', False):
            lines.append("Calibration: Paused by user. Do not ask calibration "
                         "questions unless the user says they want to continue.")
        else:
            stage = overrides_gov.get('calibration_stage', 0)
            total = len(CALIBRATION_QUESTIONS)
            lines.append(f"Calibration: In progress ({stage}/{total} questions answered). "
                         "Getting-to-know-you conversation is active.")

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
