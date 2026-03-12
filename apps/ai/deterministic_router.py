# ==============================================================================
# File: apps/ai/deterministic_router.py
# Project: Whole Life Journey — Django 5.x Personal Wellness/Journaling App
# Description: Shared routing layer for LLM-last architecture
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-11
# ==============================================================================
"""
Deterministic Router — shared message routing for streaming & non-streaming paths.

This module implements a unified routing layer that classifies user messages
and returns deterministic responses where possible, bypassing the full LLM
pipeline. Messages that cannot be answered deterministically fall through to
the existing intent recognition / LLM pipeline.

Architecture:
    1. Both send_message() and send_message_stream() call classify_and_route()
    2. The router checks deterministic data routes first (fast, no LLM)
    3. Then checks the health summary fast path
    4. Then checks the strict health status path
    5. Then checks the check-in prefilter (routes to LLM but skips intents)
    6. If nothing matches → FALLTHROUGH to existing pipeline

Design principles:
    - Fast when safe, thoughtful when needed
    - False negatives are safe (fall through to LLM)
    - False positives are dangerous (wrong deterministic response)
    - Narrow, high-confidence lexical matching only
    - Observable: every route decision is logged with timing
    - Reversible: feature flags control new behavior

Public API:
    classify_and_route(message, user, cos_context_cache=None) -> RouteResult
"""

import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Route Categories
# =============================================================================

class RouteCategory:
    """Route type constants. Not an enum to avoid import overhead."""
    DETERMINISTIC_DATA = 'deterministic_data'
    DETERMINISTIC_HEALTH_SUMMARY = 'deterministic_health_summary'
    DETERMINISTIC_STRICT_HEALTH = 'deterministic_strict_health'
    CHECKIN_PREFILTER = 'checkin_prefilter'
    FALLTHROUGH = 'fallthrough'


class RouteResult:
    """
    Result of a routing decision.

    Attributes:
        category: RouteCategory constant
        response: str or None — deterministic response text, if available
        route_name: str — specific route that matched (e.g., 'weight_query')
        domain: str or None — primary domain for context scoping
        is_terminal: bool — if True, response is complete; if False, needs LLM
        metadata: dict — extra info for logging/observability
        elapsed_ms: float — time spent in routing decision
    """
    __slots__ = (
        'category', 'response', 'route_name', 'domain',
        'is_terminal', 'metadata', 'elapsed_ms',
    )

    def __init__(
        self,
        category=RouteCategory.FALLTHROUGH,
        response=None,
        route_name='none',
        domain=None,
        is_terminal=False,
        metadata=None,
        elapsed_ms=0.0,
    ):
        self.category = category
        self.response = response
        self.route_name = route_name
        self.domain = domain
        self.is_terminal = is_terminal
        self.metadata = metadata or {}
        self.elapsed_ms = elapsed_ms


# =============================================================================
# Feature Flags
# =============================================================================

def _is_router_enabled():
    """Check if the deterministic router is enabled."""
    return getattr(settings, 'WLJ_DETERMINISTIC_ROUTER_ENABLED', True)


def _is_data_routes_enabled():
    """Check if deterministic data routes (L2) are enabled."""
    return getattr(settings, 'WLJ_DETERMINISTIC_DATA_ROUTES_ENABLED', True)


def _is_domain_scoping_enabled():
    """Check if domain-scoped context loading is enabled."""
    return getattr(settings, 'WLJ_DOMAIN_SCOPED_CONTEXT_ENABLED', False)


def _is_memory_gating_enabled():
    """Check if semantic memory gating is enabled."""
    return getattr(settings, 'WLJ_MEMORY_GATING_ENABLED', False)


# =============================================================================
# Main Entry Point
# =============================================================================

def classify_and_route(message, user, cos_context_cache=None):
    """
    Classify a user message and return a routing decision.

    Called by BOTH send_message() and send_message_stream() to ensure
    parity between streaming and non-streaming paths.

    This function ONLY handles post-pending-state routing. The caller
    must still check ECC, pending confirmations, disambiguation, and
    clarification BEFORE calling this function.

    Args:
        message: User's raw message text.
        user: Django User instance.
        cos_context_cache: Pre-built CoS context dict (for strict health
            status which needs it). May be None.

    Returns:
        RouteResult with routing decision and optional response.
    """
    if not _is_router_enabled():
        return RouteResult(route_name='router_disabled')

    if not message or not message.strip():
        return RouteResult(route_name='empty_message')

    t_start = time.monotonic()
    msg_lower = message.lower()

    # ── Phase 1: Deterministic data routes (new L2 paths) ─────────
    if _is_data_routes_enabled():
        result = _try_deterministic_data_routes(msg_lower, user)
        if result is not None:
            result.elapsed_ms = (time.monotonic() - t_start) * 1000
            _log_route_decision(result, user, message)
            return result

    # ── Phase 2: Health summary fast path (existing) ──────────────
    result = _try_health_summary(message, msg_lower, user)
    if result is not None:
        result.elapsed_ms = (time.monotonic() - t_start) * 1000
        _log_route_decision(result, user, message)
        return result

    # ── Phase 3: Strict health status (existing) ──────────────────
    result = _try_strict_health_status(msg_lower, cos_context_cache)
    if result is not None:
        result.elapsed_ms = (time.monotonic() - t_start) * 1000
        _log_route_decision(result, user, message)
        return result

    # ── Phase 4: Check-in prefilter ───────────────────────────────
    result = _try_checkin_prefilter(msg_lower)
    if result is not None:
        result.elapsed_ms = (time.monotonic() - t_start) * 1000
        _log_route_decision(result, user, message)
        return result

    # ── Fallthrough ───────────────────────────────────────────────
    elapsed = (time.monotonic() - t_start) * 1000
    fallthrough = RouteResult(
        route_name='no_match',
        elapsed_ms=elapsed,
        domain=_infer_domain(msg_lower),
    )
    _log_route_decision(fallthrough, user, message)
    return fallthrough


# =============================================================================
# Deterministic Data Routes (Phase 2 — new L2 paths)
# =============================================================================

# Each route: (route_name, match_function, handler_function, domain)
# Match functions take msg_lower, return True/False
# Handler functions take user, return response string or None

_DATA_ROUTES = []  # Populated by register_data_route()


def register_data_route(route_name, matcher, handler, domain):
    """
    Register a deterministic data route.

    Args:
        route_name: Unique identifier (e.g., 'weight_query')
        matcher: callable(msg_lower) -> bool
        handler: callable(user) -> str or None
        domain: Primary domain string (e.g., 'health')
    """
    _DATA_ROUTES.append((route_name, matcher, handler, domain))


def _try_deterministic_data_routes(msg_lower, user):
    """Try all registered deterministic data routes."""
    for route_name, matcher, handler, domain in _DATA_ROUTES:
        try:
            if matcher(msg_lower):
                response = handler(user)
                if response is not None:
                    return RouteResult(
                        category=RouteCategory.DETERMINISTIC_DATA,
                        response=response,
                        route_name=route_name,
                        domain=domain,
                        is_terminal=True,
                    )
        except Exception as e:
            logger.warning(
                "Deterministic data route %s failed: %s",
                route_name, e, exc_info=True,
            )
    return None


# =============================================================================
# Health Summary Fast Path (existing — migrated here)
# =============================================================================

def _try_health_summary(message, msg_lower, user):
    """Try the existing deterministic health summary fast path."""
    try:
        from apps.ai.deterministic_health_summary import (
            is_health_summary_query,
            build_health_summary_response,
        )
        if is_health_summary_query(message):
            response = build_health_summary_response(user)
            if response:
                return RouteResult(
                    category=RouteCategory.DETERMINISTIC_HEALTH_SUMMARY,
                    response=response,
                    route_name='health_summary',
                    domain='health',
                    is_terminal=True,
                )
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Health summary fast path failed: %s", e, exc_info=True)
    return None


# =============================================================================
# Strict Health Status (existing — migrated here)
# =============================================================================

_HI_KEYWORDS = frozenset([
    'fat loss phase', 'plateau risk',
    'muscle preservation', 'health intelligence status',
    'body comp status',
])
_BREVITY_KEYWORDS = frozenset([
    'keep it short', 'keep it brief',
    'just the numbers', 'just the status',
    'short answer', 'tl;dr',
])


def _try_strict_health_status(msg_lower, cos_context_cache):
    """Try the strict 4-line health intelligence status response."""
    if (any(k in msg_lower for k in _HI_KEYWORDS)
            and any(k in msg_lower for k in _BREVITY_KEYWORDS)):
        try:
            from apps.ai.validators.health_response_validator import (
                enforce_strict_health_status,
            )
            response = enforce_strict_health_status(cos_context_cache)
            if response:
                return RouteResult(
                    category=RouteCategory.DETERMINISTIC_STRICT_HEALTH,
                    response=response,
                    route_name='strict_health_status',
                    domain='health',
                    is_terminal=True,
                )
        except Exception as e:
            logger.warning("Strict health status failed: %s", e, exc_info=True)
    return None


# =============================================================================
# Check-in Prefilter (existing — migrated here)
# =============================================================================

def _try_checkin_prefilter(msg_lower):
    """Detect check-in/status queries that should skip intent recognition."""
    from apps.ai.personal_assistant import CHECKIN_PATTERNS

    if any(p in msg_lower for p in CHECKIN_PATTERNS):
        return RouteResult(
            category=RouteCategory.CHECKIN_PREFILTER,
            response=None,  # Caller must still call _generate_response()
            route_name='checkin_prefilter',
            domain=None,  # Cross-domain
            is_terminal=False,  # Needs LLM
        )
    return None


# =============================================================================
# Domain Inference (for context scoping on fallthrough)
# =============================================================================

_DOMAIN_KEYWORDS = {
    'health': frozenset([
        'weight', 'workout', 'workouts', 'exercise', 'sleep',
        'glucose', 'blood sugar', 'fitness', 'vitals', 'body',
        'nutrition', 'diet', 'calories', 'protein', 'steps',
        'heart rate', 'blood pressure', 'fasting', 'medication',
        'meds', 'medicine', 'blood oxygen', 'bmi',
    ]),
    'faith': frozenset([
        'bible', 'scripture', 'prayer', 'devotion', 'faith',
        'reading plan', 'verse', 'chapter', 'psalm',
    ]),
    'journal': frozenset([
        'journal', 'journaling', 'diary', 'entry', 'mood',
        'gratitude', 'reflection',
    ]),
    'goals': frozenset([
        'goal', 'goals', 'milestone', 'target', 'habit',
        'habits', 'streak',
    ]),
    'tasks': frozenset([
        'task', 'tasks', 'to-do', 'todo', 'to do',
        'calendar', 'event', 'schedule', 'appointment',
    ]),
    'finance': frozenset([
        'finance', 'finances', 'budget', 'money', 'spending',
        'savings', 'income', 'expense',
    ]),
}


def _infer_domain(msg_lower):
    """Infer the primary domain from message keywords. Returns None if ambiguous."""
    matches = []
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            matches.append(domain)
    return matches[0] if len(matches) == 1 else None


# =============================================================================
# Domain Scoping Helpers (for callers that build CoS context)
# =============================================================================

# Maps domain to the CoS context builder tags that are relevant.
# Tags must match _TAGGED_BUILDERS keys in cos_context.py.
DOMAIN_CONTEXT_BUILDERS = {
    'health': {'health', 'meals', 'medical'},
    'faith': {'faith'},
    'journal': set(),  # No dedicated journal builder; relies on core context
    'goals': {'purpose', 'calendar'},
    'tasks': {'calendar'},
    'finance': {'finance'},
}

# Builder tags that always run regardless of domain (core situation awareness)
CORE_BUILDERS = {
    'blueprint', 'plan', 'pressure', 'intelligence',
    'people', 'loops', 'strategy', 'operating_profile',
}


def get_scoped_builders(domain):
    """
    Get the set of CoS builder keys for a given domain.

    Returns None if domain is None (meaning: build all).
    Returns the domain-specific builders + core builders otherwise.

    Args:
        domain: str or None

    Returns:
        set of builder key strings, or None for full build.
    """
    if not _is_domain_scoping_enabled():
        return None  # Full build
    if domain is None:
        return None  # Ambiguous domain → full build
    domain_keys = DOMAIN_CONTEXT_BUILDERS.get(domain)
    if domain_keys is None:
        return None  # Unknown domain → full build
    return domain_keys | CORE_BUILDERS


def should_skip_semantic_memory(route_result):
    """
    Determine if semantic memory retrieval can be safely skipped.

    Skips memory for:
    - Deterministic data routes (pure data lookup)
    - Deterministic health summary (pre-computed metrics)
    - Strict health status (pre-computed enums)

    Does NOT skip for:
    - Check-in prefilter (may benefit from context)
    - Fallthrough (conversational, analytical, coaching)

    Args:
        route_result: RouteResult from classify_and_route()

    Returns:
        bool — True if semantic memory can be skipped.
    """
    if not _is_memory_gating_enabled():
        return False  # Feature disabled → never skip
    return route_result.category in {
        RouteCategory.DETERMINISTIC_DATA,
        RouteCategory.DETERMINISTIC_HEALTH_SUMMARY,
        RouteCategory.DETERMINISTIC_STRICT_HEALTH,
    }


# =============================================================================
# Observability
# =============================================================================

def _log_route_decision(result, user, message):
    """Log the routing decision for observability."""
    user_id = getattr(user, 'id', '?')
    logger.info(
        "ROUTE_DECISION user=%s category=%s route=%s domain=%s "
        "terminal=%s elapsed=%.1fms msg=%r",
        user_id,
        result.category,
        result.route_name,
        result.domain,
        result.is_terminal,
        result.elapsed_ms,
        message[:80],
    )


# =============================================================================
# Built-in Deterministic Data Routes
# =============================================================================

def _match_weight_query(msg_lower):
    """Match direct weight status questions."""
    _WEIGHT_INTENT_PHRASES = frozenset([
        "what's my weight", 'whats my weight', 'what is my weight',
        'how much do i weigh', 'current weight', 'my weight',
        'weight check', 'show my weight', 'show me my weight',
    ])
    # Must match a weight intent phrase
    if any(p in msg_lower for p in _WEIGHT_INTENT_PHRASES):
        # Exclude logging intents ("log my weight at 300")
        _EXCLUDE = ['log', 'record', 'set', 'update', 'change', 'enter']
        if not any(e in msg_lower for e in _EXCLUDE):
            return True
    return False


def _handle_weight_query(user):
    """Build a deterministic weight response from SAE state."""
    from apps.core.ai_state.state_engine import get_module_state
    health = get_module_state(user, 'health') or {}

    weight = health.get('weight_current')
    if weight is None:
        return None  # No data → fall through to LLM

    unit = health.get('weight_unit', 'lb')
    unit_label = 'lbs' if unit == 'lb' else 'kg'
    trend = health.get('weight_trend', '')

    trend_str = ''
    if trend == 'decreasing':
        trend_str = ' and trending down'
    elif trend == 'increasing':
        trend_str = ' and trending up'
    elif trend == 'stable':
        trend_str = ' and holding steady'

    response = f"Your current weight is **{weight:.1f} {unit_label}**{trend_str}."

    # Add goal context if available
    goal = health.get('weight_goal')
    if goal is not None:
        remaining = health.get('weight_goal_remaining')
        on_track = health.get('weight_goal_on_track')
        goal_unit = health.get('weight_goal_unit', 'lb')
        goal_label = 'lbs' if goal_unit == 'lb' else 'kg'
        if remaining is not None:
            track_str = 'on track' if on_track else 'behind pace'
            response += (
                f" Your goal is {goal:.0f} {goal_label} — "
                f"{abs(remaining):.1f} {goal_label} to go ({track_str})."
            )

    # Insight invitation for weight (progress domain)
    if trend in ('decreasing', 'increasing'):
        response += (
            "\n\nWant me to break down what's driving the trend?"
        )

    return response


def _match_workout_query(msg_lower):
    """Match direct workout status questions."""
    _WORKOUT_INTENT = frozenset([
        'how many workouts', 'workout count', 'workouts this week',
        'workout summary', 'my workouts', 'show my workouts',
        'how many times did i work out', 'how many times have i worked out',
        'exercise this week', 'training this week',
        'how much have i exercised', 'how much did i exercise',
    ])
    if any(p in msg_lower for p in _WORKOUT_INTENT):
        _EXCLUDE = ['log', 'record', 'start', 'begin', 'create', 'add']
        if not any(e in msg_lower for e in _EXCLUDE):
            return True
    return False


def _handle_workout_query(user):
    """Build a deterministic workout response from SAE state."""
    from apps.core.ai_state.state_engine import get_module_state
    fitness = get_module_state(user, 'fitness') or {}

    workouts_7d = fitness.get('workouts_7d', 0)
    if workouts_7d == 0:
        # Check if we have any data at all
        if not fitness:
            return None  # No fitness data → fall through
        return "No workouts logged this week yet."

    session_word = 'session' if workouts_7d == 1 else 'sessions'
    response = f"You've logged **{workouts_7d} {session_word}** this week."

    minutes = fitness.get('workout_minutes_7d')
    if minutes:
        hours = minutes / 60
        if hours >= 1:
            response += f" That's {hours:.1f} hours of training."
        else:
            response += f" That's {int(minutes)} minutes of training."

    avg_duration = fitness.get('avg_workout_duration')
    if avg_duration and workouts_7d > 1:
        response += f" Average session: {int(avg_duration)} minutes."

    # Insight invitation
    if workouts_7d >= 3:
        response += (
            "\n\nWant me to look at your training patterns and recovery?"
        )

    return response


def _match_sleep_query(msg_lower):
    """Match direct sleep status questions."""
    _SLEEP_INTENT = frozenset([
        'how did i sleep', "how's my sleep", 'how is my sleep',
        'my sleep', 'sleep average', 'sleep this week',
        'sleep quality', 'how much sleep', 'am i sleeping enough',
        'show my sleep', 'sleep summary', 'sleep stats',
    ])
    if any(p in msg_lower for p in _SLEEP_INTENT):
        _EXCLUDE = ['log', 'record', 'set', 'track']
        if not any(e in msg_lower for e in _EXCLUDE):
            return True
    return False


def _handle_sleep_query(user):
    """Build a deterministic sleep response from SAE state."""
    from apps.core.ai_state.state_engine import get_module_state
    health = get_module_state(user, 'health') or {}

    sleep_min = health.get('sleep_avg_duration_7d')
    if sleep_min is None:
        return None  # No data → fall through

    sleep_hrs = round(float(sleep_min) / 60, 1)
    trend = health.get('sleep_trend', '')

    trend_str = ''
    if trend == 'improving':
        trend_str = ' and improving'
    elif trend == 'declining':
        trend_str = ' and declining'
    elif trend == 'stable':
        trend_str = ' and consistent'

    response = f"You're averaging **{sleep_hrs} hours** of sleep this week{trend_str}."

    if sleep_hrs < 7:
        response += " That's below the 7-hour target."
    elif sleep_hrs >= 7:
        response += " That's in a solid range."

    return response


def _match_glucose_query(msg_lower):
    """Match direct glucose/blood sugar status questions."""
    _GLUCOSE_INTENT = frozenset([
        "what's my glucose", 'whats my glucose', 'what is my glucose',
        'my glucose', 'glucose level', 'blood sugar',
        'glucose average', 'glucose this week',
        'show my glucose', 'glucose check', 'glucose stats',
        'my blood sugar', "what's my blood sugar", 'whats my blood sugar',
    ])
    if any(p in msg_lower for p in _GLUCOSE_INTENT):
        _EXCLUDE = ['log', 'record', 'set', 'enter']
        if not any(e in msg_lower for e in _EXCLUDE):
            return True
    return False


def _handle_glucose_query(user):
    """Build a deterministic glucose response from SAE state."""
    from apps.core.ai_state.state_engine import get_module_state
    health = get_module_state(user, 'health') or {}

    glucose = health.get('glucose_avg_7d')
    if glucose is None:
        return None  # No data → fall through

    response = f"Your 7-day average glucose is **{int(glucose)} mg/dL**."

    if glucose < 100:
        response += " That's in the normal range."
    elif glucose < 126:
        response += " That's in the pre-diabetic range — worth watching."
    else:
        response += " That's elevated — something to discuss with your doctor."

    return response


def _match_medication_query(msg_lower):
    """Match direct medication status questions."""
    # Query patterns — asking about medication status
    _MED_QUERY = frozenset([
        'did i take my meds', 'did i take my medicine',
        'did i take my medication', 'medication status',
        'med status', 'meds status', 'medicine adherence',
        'medication adherence', 'have i taken my meds',
        'have i taken my medicine', 'have i taken my medication',
        'am i on track with meds', 'am i on track with medication',
        'med check', 'meds check', 'medication check',
    ])
    # These are inherently queries (past tense / status) — no exclude needed
    if any(p in msg_lower for p in _MED_QUERY):
        return True

    # Generic ownership patterns — need exclusion for action intents
    _MED_GENERIC = frozenset([
        'my medication', 'my meds', 'my medicine',
    ])
    if any(p in msg_lower for p in _MED_GENERIC):
        _EXCLUDE = ['log', 'record', 'take ', 'mark', 'add', 'set',
                     'prescribe', 'skip', 'took']
        if not any(e in msg_lower for e in _EXCLUDE):
            return True
    return False


def _get_medicine_adherence(user, start_date, end_date):
    """Wrapper for medicine_utils.calculate_medicine_adherence (patchable for tests)."""
    from apps.health.medicine_utils import calculate_medicine_adherence
    return calculate_medicine_adherence(user, start_date, end_date)


def _handle_medication_query(user):
    """Build a deterministic medication response."""
    from datetime import date, timedelta

    today = date.today()
    week_ago = today - timedelta(days=7)

    try:
        adh = _get_medicine_adherence(user, week_ago, today)
    except Exception as e:
        logger.warning("Medication adherence calc failed: %s", e, exc_info=True)
        return None

    expected = adh.get('expected_doses', 0)
    if expected == 0:
        return "No active medication schedules found."

    taken = adh.get('taken_doses', 0)
    rate = adh.get('adherence_rate')

    if rate is not None:
        response = (
            f"Your medication adherence this week is **{rate:.0f}%** "
            f"({taken} of {expected} scheduled doses taken)."
        )
        if rate >= 90:
            response += " Great consistency."
        elif rate >= 70:
            response += " Room for improvement — a few missed doses."
        else:
            response += " Several doses were missed this week."
    else:
        response = f"You've taken {taken} of {expected} scheduled doses this week."

    return response


def _match_steps_query(msg_lower):
    """Match direct steps status questions."""
    _STEPS_INTENT = frozenset([
        'how many steps', 'my steps', 'step count',
        'steps today', 'steps this week', 'daily steps',
        'show my steps', 'step average', 'steps average',
    ])
    if any(p in msg_lower for p in _STEPS_INTENT):
        _EXCLUDE = ['log', 'record', 'set', 'goal']
        if not any(e in msg_lower for e in _EXCLUDE):
            return True
    return False


def _handle_steps_query(user):
    """Build a deterministic steps response from SAE state."""
    from apps.core.ai_state.state_engine import get_module_state
    health = get_module_state(user, 'health') or {}

    steps = health.get('steps_avg_7d')
    if steps is None:
        return None  # No data → fall through

    response = f"You're averaging **{int(steps):,} steps** per day this week."

    if steps >= 10000:
        response += " That's excellent — above the 10K target."
    elif steps >= 7500:
        response += " Solid activity level."
    elif steps >= 5000:
        response += " That's moderate — pushing toward 7,500+ would help."

    return response


def _match_blood_pressure_query(msg_lower):
    """Match direct blood pressure questions."""
    _BP_INTENT = frozenset([
        'blood pressure', 'my bp', "what's my bp",
        'whats my bp', 'what is my bp', 'bp reading',
        'bp check', 'show my blood pressure',
    ])
    if any(p in msg_lower for p in _BP_INTENT):
        _EXCLUDE = ['log', 'record', 'set', 'enter']
        if not any(e in msg_lower for e in _EXCLUDE):
            return True
    return False


def _handle_blood_pressure_query(user):
    """Build a deterministic blood pressure response from SAE state."""
    from apps.core.ai_state.state_engine import get_module_state
    health = get_module_state(user, 'health') or {}

    sys_val = health.get('bp_systolic')
    dia_val = health.get('bp_diastolic')
    if sys_val is None or dia_val is None:
        return None

    response = f"Your most recent blood pressure reading is **{sys_val}/{dia_val}**."

    if sys_val < 120 and dia_val < 80:
        response += " That's in the normal range."
    elif sys_val < 130 and dia_val < 80:
        response += " That's elevated — keep monitoring."
    elif sys_val < 140 or dia_val < 90:
        response += " That's in the Stage 1 hypertension range."
    else:
        response += " That's in the Stage 2 hypertension range — worth discussing with your doctor."

    return response


def _match_heart_rate_query(msg_lower):
    """Match direct heart rate questions."""
    _HR_INTENT = frozenset([
        'heart rate', 'my heart rate', "what's my heart rate",
        'whats my heart rate', 'what is my heart rate',
        'resting heart rate', 'hr average', 'bpm',
        'my bpm', 'show my heart rate',
    ])
    if any(p in msg_lower for p in _HR_INTENT):
        _EXCLUDE = ['log', 'record', 'set', 'enter']
        if not any(e in msg_lower for e in _EXCLUDE):
            return True
    return False


def _handle_heart_rate_query(user):
    """Build a deterministic heart rate response from SAE state."""
    from apps.core.ai_state.state_engine import get_module_state
    health = get_module_state(user, 'health') or {}

    hr = health.get('heart_rate_avg_7d')
    if hr is None:
        return None

    response = f"Your 7-day average heart rate is **{int(hr)} bpm**."

    if hr < 60:
        response += " That's on the low side — may indicate strong cardiovascular fitness."
    elif hr <= 100:
        response += " That's in the normal resting range."
    else:
        response += " That's elevated — worth monitoring."

    return response


# =============================================================================
# Route Registration (runs at module import)
# =============================================================================

def _register_builtin_routes():
    """Register all built-in deterministic data routes."""
    register_data_route('weight_query', _match_weight_query, _handle_weight_query, 'health')
    register_data_route('workout_query', _match_workout_query, _handle_workout_query, 'health')
    register_data_route('sleep_query', _match_sleep_query, _handle_sleep_query, 'health')
    register_data_route('glucose_query', _match_glucose_query, _handle_glucose_query, 'health')
    register_data_route('medication_query', _match_medication_query, _handle_medication_query, 'health')
    register_data_route('steps_query', _match_steps_query, _handle_steps_query, 'health')
    register_data_route('blood_pressure_query', _match_blood_pressure_query, _handle_blood_pressure_query, 'health')
    register_data_route('heart_rate_query', _match_heart_rate_query, _handle_heart_rate_query, 'health')


_register_builtin_routes()
