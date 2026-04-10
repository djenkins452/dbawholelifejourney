"""
Conversation Mode Persistence.

Detects and locks the user's current conversation topic so CoS
stays focused and doesn't inject unrelated tasks or nudges.

Mode is stored in PersonalOperatingBlueprint.governance_overrides
under the key 'conversation_mode'. No migration required.

Modes:
    general  — no lock, normal behavior
    faith    — Bible, prayer, spiritual topics
    health   — workouts, nutrition, vitals, medical
    journal  — journaling, reflection, mood
    coaching — goal setting, habits, accountability
    planning — schedule, calendar, task planning
    qa       — user asking factual questions

Rules:
    - Mode auto-detected from message content
    - Mode persists across turns until:
      * User changes topic explicitly
      * 10+ minutes of silence
      * User says "what's next" / "what else"
    - Proactive messages suppressed if domain doesn't match mode
    - Critical health gates (medication overdue) bypass suppression
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Mode detection keywords (checked against lowered message)
_MODE_SIGNALS = {
    'faith': [
        'bible', 'scripture', 'proverbs', 'psalm', 'verse', 'prayer',
        'pray', 'devotion', 'faith', 'god', 'jesus', 'church',
        'worship', 'spiritual', 'sermon', 'reading plan',
        # Phase 18.3: reflective faith keywords that must trigger
        # faith mode so the router doesn't hijack them with
        # execution responses.
        'idol', 'idols', 'righteousness', 'sin', 'commandment',
        'what does god say', 'what does the bible say', 'holy spirit',
        'salvation', 'grace', 'forgiveness', 'repentance', 'gospel',
        'heaven', 'eternal', 'disciple', 'parable', 'sermon on the mount',
        'covenant', 'blessing', 'temptation', 'wisdom',
        # Phase 18.3 hardening: reflective question patterns
        'my priority', 'god my priority', 'give up', 'sacrifice',
        'obedience', 'obey', 'surrender', 'kingdom', 'calling',
        'purpose in life', 'will of god',
    ],
    'health': [
        'workout', 'exercise', 'calories', 'weight', 'macros',
        'protein', 'nutrition', 'glucose', 'blood pressure',
        'heart rate', 'sleep', 'steps', 'fasting', 'medication',
        'supplement', 'lab result', 'vitals',
    ],
    'journal': [
        'journal', 'journaling', 'reflect', 'reflection', 'mood',
        'feeling', 'gratitude', 'write about', 'dear diary',
        # Phase 18.3: reflective/emotional keywords
        'what does it mean', 'how do i know if', 'struggling with',
        'afraid', 'anxious', 'worried', 'thankful', 'grateful',
        'identity', 'purpose', 'meaning', 'why do i', 'who am i',
    ],
    'coaching': [
        'goal', 'habit', 'accountability', 'streak', 'discipline',
        'commitment', 'progress', 'milestone', 'transformation',
    ],
    'planning': [
        'schedule', 'calendar', 'tomorrow', 'this week', 'plan',
        'routine', 'organize', 'task', 'deadline', 'reschedule',
    ],
}

# Phrases that break mode lock (return to general)
_MODE_BREAK_PHRASES = [
    "what's next", "whats next", "what else",
    "anything else", "change topic", "never mind",
    "show me my day", "check in", "daily briefing",
]

# Mode silence timeout (minutes)
_MODE_TIMEOUT_MINUTES = 10


def detect_conversation_mode(message: str) -> str:
    """
    Detect conversation mode from message content.

    Returns:
        Mode string if keywords matched, 'general' ONLY if a mode-break
        phrase was detected. Returns 'undetected' if no keywords matched
        and no break phrase found — callers use this to preserve the
        existing mode (persistence).
    """
    msg_lower = message.lower().strip()

    # Check for mode-break phrases first
    if any(phrase in msg_lower for phrase in _MODE_BREAK_PHRASES):
        return 'general'

    # Score each mode by keyword matches
    best_mode = 'undetected'
    best_score = 0

    for mode, keywords in _MODE_SIGNALS.items():
        score = sum(1 for kw in keywords if kw in msg_lower)
        if score > best_score:
            best_score = score
            best_mode = mode

    return best_mode


def get_active_mode(user) -> str:
    """
    Get the user's current conversation mode.

    Returns 'general' if no mode is active or mode has timed out.
    """
    try:
        blueprint = user.operating_blueprint
    except Exception:
        return 'general'

    overrides = blueprint.governance_overrides or {}
    mode_data = overrides.get('conversation_mode', {})

    if not mode_data or not mode_data.get('mode'):
        return 'general'

    # Check timeout
    locked_at = mode_data.get('locked_at')
    if locked_at:
        try:
            from django.utils.dateparse import parse_datetime
            lock_time = parse_datetime(locked_at)
            if lock_time and timezone.now() - lock_time > timedelta(
                minutes=_MODE_TIMEOUT_MINUTES
            ):
                # Mode expired — clear it
                _clear_mode(blueprint)
                return 'general'
        except Exception:
            pass

    return mode_data.get('mode', 'general')


def set_conversation_mode(user, mode: str) -> None:
    """
    Lock the user into a conversation mode.

    Stores mode + timestamp in governance_overrides JSON.
    """
    if mode == 'general':
        clear_conversation_mode(user)
        return

    try:
        blueprint = user.operating_blueprint
    except Exception:
        return

    overrides = blueprint.governance_overrides or {}
    overrides['conversation_mode'] = {
        'mode': mode,
        'locked_at': timezone.now().isoformat(),
    }
    blueprint.governance_overrides = overrides
    blueprint.save(update_fields=['governance_overrides'])


def clear_conversation_mode(user) -> None:
    """Clear the conversation mode lock."""
    try:
        blueprint = user.operating_blueprint
        _clear_mode(blueprint)
    except Exception:
        pass


def update_mode_from_message(user, message: str) -> str:
    """
    Update conversation mode based on the user's message.

    Called on each user message. Returns the active mode after update.
    """
    current_mode = get_active_mode(user)
    detected_mode = detect_conversation_mode(message)

    if detected_mode == 'general':
        # Explicit mode-break phrase — clear lock
        clear_conversation_mode(user)
        return 'general'

    if detected_mode == 'undetected':
        # Phase 18.3: no keywords matched AND no break phrase.
        # PRESERVE the current mode (persistence). This is the key
        # fix — previously "undetected" was conflated with "general"
        # and cleared the mode lock on follow-up questions like
        # "How do I apply that to my life?"
        return current_mode

    if detected_mode != current_mode:
        # New mode detected — lock it
        set_conversation_mode(user, detected_mode)
    else:
        # Same mode — refresh the timeout
        set_conversation_mode(user, detected_mode)
    return detected_mode


def should_suppress_proactive(user, proactive_domain: str) -> bool:
    """
    Check if a proactive message should be suppressed based on
    active conversation mode.

    Returns True if the message should be suppressed.
    Critical health gates (medication) are NEVER suppressed.
    """
    # Medication overdue is NEVER suppressed
    if proactive_domain in ('medication', 'medicine', 'intake'):
        return False

    mode = get_active_mode(user)
    if mode == 'general':
        return False  # No mode lock — allow everything

    # Map proactive domains to conversation modes
    domain_to_mode = {
        'workout': 'health',
        'health': 'health',
        'nutrition': 'health',
        'journal': 'journal',
        'faith': 'faith',
        'bible': 'faith',
        'prayer': 'faith',
        'task': 'planning',
        'routine': 'planning',
        'goal': 'coaching',
        'habit': 'coaching',
        'relationship': 'general',  # Relationship nudges always allowed
        'finance': 'general',  # Finance always allowed
    }

    proactive_mode = domain_to_mode.get(proactive_domain, 'general')

    # Suppress if proactive domain doesn't match active mode
    return proactive_mode != mode and proactive_mode != 'general'


def _clear_mode(blueprint) -> None:
    """Internal: clear mode from blueprint overrides."""
    overrides = blueprint.governance_overrides or {}
    overrides.pop('conversation_mode', None)
    blueprint.governance_overrides = overrides
    blueprint.save(update_fields=['governance_overrides'])
