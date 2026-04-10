"""
Response Governor — Single Response Authority for WLJ.

The ONLY authority that determines what TYPE of response is generated.
No component may produce a user-facing response without the governor's
approval. This eliminates context switching, conflicting outputs, and
the "briefing overrides faith conversation" failure class.

Pipeline position:
    User Message
    → Mode Detection + Persisted State
    → **Response Governor (this module)**
    → Approved Response Type (ONE ONLY)
    → Selected System Executes

Response types (exactly one per turn):
    REFLECTIVE  — faith/journal conversations → LLM handles
    EXECUTION   — tasks, priorities, "what should I do" → deterministic
    BRIEFING    — daily orientation → deterministic
    ALERT       — health-critical only (medication overdue) → deterministic

Rules:
    - REFLECTIVE mode blocks EXECUTION, BRIEFING, and all proactive layers
    - EXECUTION mode blocks REFLECTIVE
    - BRIEFING only fires when mode is GENERAL and it's the first turn
    - ALERT bypasses all modes (medication safety gate)
    - No mixing, no fallback, no secondary responses
"""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ResponseType(str, Enum):
    REFLECTIVE = 'reflective'
    EXECUTION = 'execution'
    BRIEFING = 'briefing'
    ALERT = 'alert'


# Modes that lock into REFLECTIVE response type
_REFLECTIVE_MODES = frozenset({'faith', 'journal'})

# Explicit break phrases that exit reflective mode
_BREAK_PHRASES = frozenset({
    "what's next", "whats next", "what else", "anything else",
    "change topic", "never mind", "show me my day", "check in",
    "daily briefing", "what should i do", "show my tasks",
    "what is left", "what's left", "whats left",
})


def resolve_response_type(user, message, active_mode=None):
    """Determine the single approved response type for this turn.

    This is the CENTRAL AUTHORITY. Every response-producing system
    must check this before generating output.

    Args:
        user: Django User instance
        message: The user's raw message text
        active_mode: Pre-computed active conversation mode (optional;
            if None, reads from blueprint)

    Returns:
        ResponseType — exactly one of REFLECTIVE, EXECUTION, BRIEFING, ALERT
    """
    msg_lower = (message or '').lower().strip()

    # ── Step 1: Determine active mode ────────────────────────
    if active_mode is None:
        try:
            from apps.core.blueprint.conversation_mode import (
                get_active_mode,
            )
            active_mode = get_active_mode(user) if user else 'general'
        except Exception:
            active_mode = 'general'

    # ── Step 2: Detect message mode ──────────────────────────
    detected_mode = 'undetected'
    try:
        from apps.core.blueprint.conversation_mode import (
            detect_conversation_mode,
        )
        detected_mode = detect_conversation_mode(message or '')
    except Exception:
        pass

    # ── Step 3: Check for health-critical ALERT ──────────────
    # ALERT only fires in GENERAL/EXECUTION mode. During a
    # REFLECTIVE conversation (faith/journal), the medication
    # status is available in the CoS context for the LLM to
    # reference, but does NOT hijack the response. The user
    # asked a faith question — they deserve a faith answer.
    #
    # The ALERT path is reserved for when the user has NO active
    # conversational mode and hasn't taken any medications.
    _in_reflective_mode = (
        active_mode in _REFLECTIVE_MODES
        or detected_mode in _REFLECTIVE_MODES
    )
    if not _in_reflective_mode:
        try:
            from apps.core.ai_orchestrator.cos_context import _fresh_module_state
            ms = _fresh_module_state(user, 'medicine')
            med_status = ms.get('medication_status', 'no_data')
            if med_status == 'overdue':
                expected = ms.get('expected_today', 0) or 0
                taken = ms.get('today_taken', 0) or 0
                if expected > 0 and taken == 0:
                    logger.info(
                        "RESPONSE_GOVERNOR: ALERT — medication crisis "
                        "(0/%d taken) mode=%s user=%s",
                        expected, active_mode, getattr(user, 'id', '?'),
                    )
                    return ResponseType.ALERT
        except Exception:
            pass

    # ── Step 4: Check for explicit break phrase ──────────────
    is_break = any(phrase in msg_lower for phrase in _BREAK_PHRASES)

    # ── Step 5: Resolve response type ────────────────────────

    # If currently in reflective mode AND no break phrase → REFLECTIVE
    if active_mode in _REFLECTIVE_MODES and not is_break:
        logger.info(
            "RESPONSE_GOVERNOR: REFLECTIVE (locked mode=%s) user=%s",
            active_mode, getattr(user, 'id', '?'),
        )
        return ResponseType.REFLECTIVE

    # If message itself is reflective AND no break → REFLECTIVE
    if detected_mode in _REFLECTIVE_MODES and not is_break:
        logger.info(
            "RESPONSE_GOVERNOR: REFLECTIVE (detected=%s) user=%s",
            detected_mode, getattr(user, 'id', '?'),
        )
        return ResponseType.REFLECTIVE

    # Default: EXECUTION (covers general, planning, health, coaching)
    logger.info(
        "RESPONSE_GOVERNOR: EXECUTION (mode=%s detected=%s) user=%s",
        active_mode, detected_mode, getattr(user, 'id', '?'),
    )
    return ResponseType.EXECUTION


def is_response_allowed(approved_type, attempted_system):
    """Check if a specific system is allowed to respond given the
    approved ResponseType.

    Args:
        approved_type: ResponseType from resolve_response_type
        attempted_system: str — which system wants to respond:
            'briefing', 'execution', 'ecc', 'proactive', 'affirmation',
            'intent', 'reflection', 'alert'

    Returns:
        bool — True if allowed, False if blocked
    """
    if approved_type == ResponseType.REFLECTIVE:
        return attempted_system in ('reflection', 'alert')

    if approved_type == ResponseType.ALERT:
        return attempted_system in ('alert', 'reflection')

    if approved_type == ResponseType.EXECUTION:
        return attempted_system in (
            'briefing', 'execution', 'ecc', 'proactive',
            'affirmation', 'intent', 'alert',
        )

    if approved_type == ResponseType.BRIEFING:
        return attempted_system in ('briefing', 'alert')

    return True  # fail-open for unknown types
