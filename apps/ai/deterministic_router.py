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
        'is_terminal', 'metadata', 'elapsed_ms', 'skip_intent',
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
        skip_intent=False,
    ):
        self.category = category
        self.response = response
        self.route_name = route_name
        self.domain = domain
        self.is_terminal = is_terminal
        self.metadata = metadata or {}
        self.elapsed_ms = elapsed_ms
        self.skip_intent = skip_intent


# =============================================================================
# Event Context Stash (thread-local, per-request)
# =============================================================================
# When an event route resolves, it stashes the EventRecord list here so
# personal_assistant.py can store it in conversation.metadata for follow-ups.
# This avoids modifying handler return signatures or RouteResult structure.

import threading

_thread_local = threading.local()


def _stash_resolved_events(events):
    """Stash resolved events for follow-up context storage."""
    _thread_local.resolved_events = events


def get_stashed_events():
    """Retrieve and clear stashed events. Called by personal_assistant.py."""
    events = getattr(_thread_local, 'resolved_events', None)
    _thread_local.resolved_events = None
    return events


# =============================================================================
# Qualified Status Query Detection
# =============================================================================
# When a user asks a FILTERED or FOLLOW-UP question about their day state
# ("other than nutrition, anything left?", "am I done?"), it must NOT match
# terminal deterministic routes. These are questions ABOUT the state, not
# requests to render the full state. They fall through to the LLM which
# answers using LOCKED CoS STATE from the system prompt.
#
# Centralized here for reuse by status_query, checkin_prefilter, and
# the LLM-path check-in detector in personal_assistant.py.

# Exclusion prepositions and imperative exclusion verbs.
# English has a small, closed set of ways to say "exclude X":
#   prepositional: "other than X", "besides X", "apart from X"
#   imperative: "skip X", "leave out X", "ignore X", "forget X"
# This list is exhaustive for natural English — new exclusion
# prepositions are not being invented.
QUALIFIED_STATUS_PREFIXES = (
    # Prepositional exclusions
    'other than ',
    'besides ',
    'except for ',
    'except ',
    'excluding ',
    'apart from ',
    'aside from ',
    'not counting ',
    'not including ',
    'outside of ',
    'without counting ',
    'without ',
    # Imperative exclusions
    'leave out ',
    'leaving out ',
    'skip ',
    'skipping ',
    'forget ',
    'forget about ',
    'forgetting ',
    'ignore ',
    'ignoring ',
    'setting aside ',
    'minus ',
    'take away ',
    'taking away ',
)

# Yes/no closers — "am I done?", "is that everything?"
QUALIFIED_STATUS_QUESTIONS = (
    'am i done',
    'is that it',
    'is that everything',
    'is that all',
    'anything else',
    'nothing else',
    'all done',
    'am i finished',
    'is there anything else',
    'did i miss anything',
    'have i missed anything',
)


def is_qualified_status_query(msg_lower: str) -> bool:
    """Detect if a message is a filtered/follow-up status question.

    Returns True for: "other than nutrition, anything left?",
    "am I done?", "besides meds, what's remaining?"
    """
    if any(msg_lower.startswith(p) or (', ' + p) in msg_lower or (' ' + p) in msg_lower
           for p in QUALIFIED_STATUS_PREFIXES):
        return True
    return any(p in msg_lower for p in QUALIFIED_STATUS_QUESTIONS)


def _extract_exclusion_term(msg_lower: str):
    """Extract the excluded domain/item from a filtered status query.

    "other than nutrition, anything left?" → "nutrition"
    "besides meds, what's remaining?"     → "meds"
    "skip workout, am I done?"            → "workout"

    Returns None if no exclusion prefix matched.
    """
    import re
    # Sort longest-first so "forget about" matches before "forget"
    sorted_prefixes = sorted(QUALIFIED_STATUS_PREFIXES, key=len, reverse=True)
    for prefix in sorted_prefixes:
        # Check if prefix appears in the message
        idx = -1
        if msg_lower.startswith(prefix):
            idx = 0
        elif (', ' + prefix) in msg_lower:
            idx = msg_lower.index(', ' + prefix) + 2
        elif (' ' + prefix) in msg_lower:
            idx = msg_lower.index(' ' + prefix) + 1

        if idx >= 0:
            after = msg_lower[idx + len(prefix):]
            # Extract the term — everything up to the next punctuation or
            # status-query keyword (", anything", ", what's", "— anything")
            match = re.match(
                r'([a-z0-9 ]+?)(?:\s*[,—–\-?!]|\s+(?:anything|what|is|am|do|how))',
                after,
            )
            if match:
                return match.group(1).strip()
            # Fallback: take first 1-3 words
            words = after.split()[:3]
            term = ' '.join(words).rstrip('.,?!—–-')
            return term.strip() if term.strip() else None
    return None


def _build_qualified_status_response(msg_lower: str, user):
    """Build a deterministic response for qualified status queries.

    Uses Today Engine data to answer directly. No LLM involved.

    Query types:
      FILTERED: "other than nutrition, anything left?" → exclude term, report rest
      BOOLEAN:  "am I done?" → yes/no with count
      DELTA:    "anything else?" / "is that everything?" → yes/no with count

    Returns a 1-2 sentence response string, or None on failure.
    """
    try:
        from apps.core.today.today_engine import get_today_context
    except ImportError:
        return None

    try:
        ctx = get_today_context(user)
    except Exception:
        logger.warning(
            "[QUALIFIED STATUS] Today Engine failed for user=%s",
            user.id, exc_info=True,
        )
        return None

    # Collect all remaining (incomplete) items
    remaining = []
    for bucket in ('overdue', 'coming_up', 'later', 'foundation'):
        for entry in ctx.get(bucket, []):
            item = entry.get('item', entry)
            name = item.get('name', entry.get('label', ''))
            if name and not item.get('completed', False):
                remaining.append(name)

    # Deduplicate while preserving order
    seen = set()
    unique_remaining = []
    for name in remaining:
        if name.lower() not in seen:
            seen.add(name.lower())
            unique_remaining.append(name)
    remaining = unique_remaining

    total_remaining = len(remaining)

    # ── FILTERED: "other than X, anything left?" ──────────────────
    exclusion = _extract_exclusion_term(msg_lower)
    if exclusion:
        excl_lower = exclusion.lower()
        # Filter out items matching the exclusion term (fuzzy substring)
        filtered = [
            name for name in remaining
            if excl_lower not in name.lower()
        ]

        if not filtered:
            # Everything remaining IS the excluded item(s)
            return f"No — just {exclusion} left."
        elif len(filtered) == 1:
            return f"Yes — {filtered[0]} is also remaining."
        else:
            items_str = ', '.join(filtered)
            return f"Yes — {len(filtered)} other items: {items_str}."

    # ── BOOLEAN: "am I done?" / "am I finished?" ─────────────────
    boolean_phrases = ('am i done', 'am i finished', 'all done')
    if any(p in msg_lower for p in boolean_phrases):
        if total_remaining == 0:
            return "Yes — you're done for today."
        elif total_remaining == 1:
            return f"Not yet — 1 item left: {remaining[0]}."
        else:
            items_str = ', '.join(remaining[:4])
            suffix = '.' if total_remaining <= 4 else f' (and {total_remaining - 4} more).'
            return f"Not yet — {total_remaining} items left: {items_str}{suffix}"

    # ── DELTA: "anything else?" / "is that it?" / "is that everything?" ──
    if total_remaining == 0:
        return "No — you're done for today."
    elif total_remaining == 1:
        return f"Just {remaining[0]} left."
    else:
        items_str = ', '.join(remaining[:4])
        suffix = '.' if total_remaining <= 4 else f' (and {total_remaining - 4} more).'
        return f"{total_remaining} items left: {items_str}{suffix}"


# =============================================================================
# Event Follow-Up Resolution
# =============================================================================


def _try_event_followup(msg_lower, conversation):
    """
    Check if the message is a follow-up to a previous event query.

    Uses stored event context from conversation.metadata. Returns a
    terminal RouteResult if resolved, None otherwise (safe fallthrough).
    """
    try:
        from apps.core.ai_events.followup import (
            is_followup_query,
            get_event_context,
            resolve_followup,
        )

        if not is_followup_query(msg_lower):
            return None

        event_context = get_event_context(conversation)
        if event_context is None:
            return None

        response = resolve_followup(msg_lower, event_context)
        if response is None:
            return None

        logger.info(
            "EVENT_FOLLOWUP_RESOLVED user=%s route=%s msg=%r",
            conversation.user_id,
            event_context.get('route_name', 'unknown'),
            msg_lower[:60],
        )
        return RouteResult(
            category=RouteCategory.DETERMINISTIC_DATA,
            response=response,
            route_name='event_followup',
            domain='execution',
            is_terminal=True,
        )
    except Exception as e:
        logger.warning(
            "Event follow-up resolution failed: %s", e, exc_info=True,
        )
        return None


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


def _is_intent_bypass_enabled():
    """Check if intent recognition bypass for conversational messages is enabled."""
    return getattr(settings, 'WLJ_INTENT_BYPASS_ENABLED', False)


# =============================================================================
# Intent Bypass — Action Signal Detection
# =============================================================================

import re as _re

# Verbs that indicate the user wants to LOG or CREATE data
_LOGGING_VERBS = frozenset({
    'log', 'record', 'track', 'enter', 'save', 'add', 'took', 'had',
    'ate', 'drank', 'slept', 'weighed', 'ran', 'walked', 'biked',
    'swam', 'lifted', 'jogged', 'measured', 'fasted',
})

# Verbs that indicate the user wants to MUTATE existing data
_MUTATION_VERBS = frozenset({
    'delete', 'remove', 'cancel', 'update', 'change', 'edit',
    'reschedule', 'move', 'create', 'schedule', 'book', 'complete',
    'finish', 'done', 'skip', 'mark', 'start', 'end', 'set', 'pause',
    'resume', 'snooze', 'undo',
})

# Multi-word action phrases that need exact substring matching
_ACTION_PHRASES = (
    'took my', 'take my', 'taking my', 'mark as done', 'mark complete',
    'mark it done', 'check off', 'checked off', 'sign me up',
    'set a reminder', 'set reminder', 'add a reminder', 'create a task',
    'create task', 'create an event', 'create event', 'log a', 'log my',
    'start a fast', 'end my fast', 'end fast',
)

# Numeric+unit patterns (e.g., "185 lbs", "98 bpm", "120/80")
_NUMERIC_UNIT_RE = _re.compile(
    r'\b\d+(?:\.\d+)?'
    r'\s*(?:lbs?|lb|kg|bpm|mg|mmhg|oz|ml|cups?|steps?|hours?|hrs?|'
    r'minutes?|mins?|cal|kcal|calories|%|mmol|units?)\b',
    _re.IGNORECASE,
)

# Blood pressure pattern (e.g., "120/80")
_BP_RE = _re.compile(r'\b\d{2,3}\s*/\s*\d{2,3}\b')


def has_action_signal(msg_lower):
    """
    Detect whether a message contains signals that it's an action request
    (data logging, task mutation, etc.) rather than a conversational message.

    Returns True if the message likely needs intent recognition.
    Returns False if the message is purely conversational/analytical.

    Conservative: when in doubt, return True (which keeps intent recognition).
    """
    words = set(msg_lower.split())

    # Check individual action verbs
    if words & _LOGGING_VERBS:
        return True
    if words & _MUTATION_VERBS:
        return True

    # Check multi-word action phrases
    if any(phrase in msg_lower for phrase in _ACTION_PHRASES):
        return True

    # Check numeric+unit patterns (e.g., "185 lbs", "98 bpm")
    if _NUMERIC_UNIT_RE.search(msg_lower):
        return True

    # Blood pressure pattern
    if _BP_RE.search(msg_lower):
        return True

    return False


# =============================================================================
# Main Entry Point
# =============================================================================

def classify_and_route(message, user, cos_context_cache=None, conversation=None):
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
        conversation: AssistantConversation instance (optional). When
            provided, enables event follow-up detection from stored
            recent_event_context in metadata.

    Returns:
        RouteResult with routing decision and optional response.
    """
    if not _is_router_enabled():
        return RouteResult(route_name='router_disabled')

    if not message or not message.strip():
        return RouteResult(route_name='empty_message')

    t_start = time.monotonic()
    msg_lower = message.lower()

    # ── Phase -1: Event follow-up detection ────────────────────────
    # If a previous turn resolved an event query and the user is now
    # asking a follow-up ("what date was that?"), resolve deterministically
    # from the stored context. No re-query, no LLM.
    if conversation is not None:
        result = _try_event_followup(msg_lower, conversation)
        if result is not None:
            result.elapsed_ms = (time.monotonic() - t_start) * 1000
            _log_route_decision(result, user, message)
            return result

    # ── Phase 0a: Today status query (bypasses LLM entirely) ──────
    result = _try_status_query_route(msg_lower, user)
    if result is not None:
        result.elapsed_ms = (time.monotonic() - t_start) * 1000
        _log_route_decision(result, user, message)
        return result

    # ── Phase 0a.1: Qualified status query (deterministic) ───────
    # "other than X, anything left?", "am I done?", "anything else?"
    # Answered directly from Today Engine — no LLM involvement.
    if is_qualified_status_query(msg_lower) and user is not None:
        try:
            response = _build_qualified_status_response(msg_lower, user)
            if response:
                result = RouteResult(
                    category=RouteCategory.DETERMINISTIC_DATA,
                    response=response,
                    route_name='qualified_status',
                    domain='execution',
                    is_terminal=True,
                )
                result.elapsed_ms = (time.monotonic() - t_start) * 1000
                _log_route_decision(result, user, message)
                return result
        except Exception as e:
            logger.warning(
                "Qualified status route failed, falling through: %s",
                e, exc_info=True,
            )

    # ── Phase 0b: Locked next-action (bypasses LLM entirely) ──────
    result = _try_next_action_route(msg_lower, user)
    if result is not None:
        result.elapsed_ms = (time.monotonic() - t_start) * 1000
        _log_route_decision(result, user, message)
        return result

    # ── Phase 0c: Day agenda (deterministic, terminal) ───────────
    result = _try_day_agenda_route(msg_lower, user)
    if result is not None:
        result.elapsed_ms = (time.monotonic() - t_start) * 1000
        _log_route_decision(result, user, message)
        return result

    # ── Phase 1: Deterministic data routes (new L2 paths) ─────────
    if _is_data_routes_enabled():
        result = _try_deterministic_data_routes(msg_lower, user)
        if result is not None:
            result.elapsed_ms = (time.monotonic() - t_start) * 1000
            _log_route_decision(result, user, message)
            return result

    # ── Phase 1b: Routine time queries ("when is my workout?") ───
    # Must run BEFORE check-in prefilter to prevent misclassification.
    _item_kw = _match_routine_time_query(msg_lower)
    if _item_kw and user is not None:
        _time_resp = _handle_routine_time_query(user, item_keyword=_item_kw)
        if _time_resp:
            result = RouteResult(
                category=RouteCategory.DETERMINISTIC_DATA,
                response=_time_resp,
                route_name='routine_time_query',
                domain='execution',
                is_terminal=True,
            )
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

    # ── Phase 4: Check-in — deterministic renderer (terminal) ────
    result = _try_checkin_prefilter(msg_lower, user=user)
    if result is not None:
        result.elapsed_ms = (time.monotonic() - t_start) * 1000
        _log_route_decision(result, user, message)
        return result

    # ── Fallthrough ───────────────────────────────────────────────
    elapsed = (time.monotonic() - t_start) * 1000
    _domain = _infer_domain(msg_lower)
    _skip = (
        _is_intent_bypass_enabled()
        and not has_action_signal(msg_lower)
    )
    fallthrough = RouteResult(
        route_name='no_match',
        elapsed_ms=elapsed,
        domain=_domain,
        skip_intent=_skip,
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


# =============================================================================
# Next-Action Route — bypasses LLM entirely
# =============================================================================

# Phrases that clearly ask "what should I do next?"
_NEXT_ACTION_PHRASES = (
    'what should i focus on',
    'what should i do next',
    'what should i work on',
    'what do i do next',
    'what\'s next',
    "what's next",
    'whats next',
    'what is next',
    'what next',
    'what should i start',
    'where should i start',
    'what should i tackle',
    'what to focus on',
    'what to do next',
    'what do i focus on',
    'give me my next action',
    'next action',
    'what\'s my priority',
    "what's my priority",
    'what is my priority',
    'what should i prioritize',
)


def _is_next_action_query(msg_lower):
    """Detect if message is asking for next action recommendation."""
    return any(phrase in msg_lower for phrase in _NEXT_ACTION_PHRASES)


def _build_next_action_response(user):
    """Build deterministic next-action response from Today Engine.

    STRICT priority — evaluated in order, returns IMMEDIATELY on first match:
    1. Overdue now → earliest by time
    2. Coming up next → earliest by time
    3. Later today → earliest by time
    4. Incomplete foundational (not in time buckets) → earliest by time
    5. Empty → "You're clear right now."

    Returns EXACTLY ONE item. No plans, no lists, no sequencing.
    """
    try:
        from apps.core.today.today_engine import get_today_context

        ctx = get_today_context(user)

        # PRIORITY 1: Overdue — return FIRST (earliest) immediately
        overdue = ctx.get("overdue", [])
        if overdue:
            # Already sorted by sort_time ASC from Today Engine,
            # but enforce defensive sort for absolute correctness
            overdue = sorted(overdue, key=lambda e: e["sort_time"])
            selected = overdue[0]["label"]
            logger.info(
                "[NEXT ACTION] user=%s OVERDUE selected=%s from=%d",
                user.id, selected, len(overdue),
            )
            return f"Start {selected}."

        # PRIORITY 2: Coming up next — return FIRST immediately
        coming_up = ctx.get("coming_up", [])
        if coming_up:
            coming_up = sorted(coming_up, key=lambda e: e["sort_time"])
            selected = coming_up[0]["label"]
            logger.info(
                "[NEXT ACTION] user=%s COMING_UP selected=%s from=%d",
                user.id, selected, len(coming_up),
            )
            return f"Start {selected}."

        # PRIORITY 3: Later today — return FIRST immediately
        later = ctx.get("later", [])
        if later:
            later = sorted(later, key=lambda e: e["sort_time"])
            selected = later[0]["label"]
            logger.info(
                "[NEXT ACTION] user=%s LATER selected=%s from=%d",
                user.id, selected, len(later),
            )
            return f"Start {selected}."

        # PRIORITY 4: Incomplete foundational (no scheduled time)
        foundation = ctx.get("foundation", [])
        if foundation:
            selected = foundation[0]["label"]
            logger.info(
                "[NEXT ACTION] user=%s FOUNDATION selected=%s",
                user.id, selected,
            )
            return f"Start {selected}."

        # PRIORITY 5: Nothing actionable
        logger.info("[NEXT ACTION] user=%s ALL_CLEAR", user.id)
        return "You're clear right now."

    except Exception:
        logger.warning(
            "[NEXT ACTION] Failed for user=%s, falling back",
            user.id, exc_info=True,
        )
        from apps.ai.cos_fact_statements import build_locked_next_action
        return build_locked_next_action(user)


def _try_next_action_route(msg_lower, user):
    """Try the next-action deterministic route."""
    if not _is_next_action_query(msg_lower):
        return None
    try:
        response = _build_next_action_response(user)
        if response:
            return RouteResult(
                category=RouteCategory.DETERMINISTIC_DATA,
                response=response,
                route_name='next_action',
                domain='execution',
                is_terminal=True,
            )
    except Exception as e:
        logger.warning(
            "Next-action route failed: %s", e, exc_info=True,
        )
    return None


# =============================================================================
# Status Query Route — "What's left today?" (bypasses LLM entirely)
# =============================================================================

def _try_status_query_route(msg_lower, user):
    """Try the today-status deterministic route.

    Produces a strict, contract-enforced response for "what's left today?"
    type queries. No LLM involvement. See beth_status_renderer.py.

    Qualified queries ("other than X, what's left?") are excluded — they
    need the LLM to interpret the filter against locked state.
    """
    if is_qualified_status_query(msg_lower):
        return None

    try:
        from apps.ai.beth_status_renderer import is_status_query, build_status_response
    except ImportError:
        return None

    if not is_status_query(msg_lower):
        return None

    try:
        response = build_status_response(user)
        if response:
            return RouteResult(
                category=RouteCategory.DETERMINISTIC_DATA,
                response=response,
                route_name='status_query',
                domain='execution',
                is_terminal=True,
            )
    except Exception as e:
        logger.warning(
            "Status query route failed: %s", e, exc_info=True,
        )
    return None


def _try_deterministic_data_routes(msg_lower, user):
    """Try all registered deterministic data routes."""
    import inspect
    for route_name, matcher, handler, domain in _DATA_ROUTES:
        try:
            if matcher(msg_lower):
                # Support handlers that accept (user) or (user, msg_lower)
                try:
                    sig = inspect.signature(handler)
                    if len(sig.parameters) >= 2:
                        response = handler(user, msg_lower)
                    else:
                        response = handler(user)
                except (ValueError, TypeError):
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

# Day agenda patterns — high-priority deterministic route
_DAY_AGENDA_PATTERNS = frozenset([
    "my day", "show me my day", "what does my day look like",
    "how does my day look", "what's my day look like",
    "whats my day look like", "day agenda", "today's agenda",
    "todays agenda", "show my agenda", "what's on today",
    "whats on today", "run down my day", "rundown my day",
    "walk me through my day", "what do i have today",
])

# "today" alone is too broad — only match if it's the entire message
# or clearly asking about the day overview
_DAY_AGENDA_EXACT = frozenset(["today", "today?"])


def _try_day_agenda_route(msg_lower, user=None):
    """Detect day agenda requests and return deterministic response.

    Terminal route — the LLM is never called for day overview.
    """
    msg_stripped = msg_lower.strip().rstrip('?!.')

    is_day_request = (
        any(p in msg_lower for p in _DAY_AGENDA_PATTERNS)
        or msg_stripped in _DAY_AGENDA_EXACT
    )

    if not is_day_request:
        return None

    if user is None:
        return None

    try:
        from apps.ai.beth_day_renderer import render_day_agenda
        response = render_day_agenda(user)
    except Exception:
        logger.error(
            "[ROUTER] Day agenda renderer failed",
            exc_info=True,
        )
        response = None

    if response:
        return RouteResult(
            category=RouteCategory.DETERMINISTIC_DATA,
            response=response,
            route_name='deterministic_day_agenda',
            domain=None,
            is_terminal=True,
        )

    return None


def _try_checkin_prefilter(msg_lower, user=None):
    """Detect check-in/status queries and return deterministic response.

    Phase 5.2+: Check-in is now TERMINAL — the deterministic renderer
    produces the response directly. The LLM is never involved in
    generating state descriptions for check-in flows.

    Qualified queries ("other than X, anything left?", "am I done?")
    are excluded — they need the LLM to answer a specific question.
    """
    if is_qualified_status_query(msg_lower):
        return None

    from apps.ai.personal_assistant import CHECKIN_PATTERNS

    if any(p in msg_lower for p in CHECKIN_PATTERNS):
        response = None
        if user is not None:
            try:
                from apps.ai.beth_checkin_renderer import render_checkin_for_time
                response = render_checkin_for_time(user)
            except Exception:
                logger.error(
                    "[ROUTER] Deterministic check-in renderer failed, "
                    "falling through to LLM",
                    exc_info=True,
                )

        if response:
            return RouteResult(
                category=RouteCategory.DETERMINISTIC_DATA,
                response=response,
                route_name='deterministic_checkin',
                domain=None,
                is_terminal=True,
            )
        else:
            # Fallback: non-terminal if renderer failed
            return RouteResult(
                category=RouteCategory.CHECKIN_PREFILTER,
                response=None,
                route_name='checkin_prefilter',
                domain=None,
                is_terminal=False,
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
    'health': {'health', 'meals', 'medical', 'brain_training'},
    'faith': {'faith'},
    'journal': set(),  # No dedicated journal builder; relies on core context
    'goals': {'purpose', 'calendar'},
    'tasks': {'calendar'},
    'finance': {'finance'},
    'relationships': {'relationships'},
    'meals': {'meals'},
}

# Builder tags that always run regardless of domain (core situation awareness).
# These are system-level builders (domain_key=None in _TAGGED_BUILDERS).
# Domain builders (health, faith, etc.) are NOT in this set — they are
# included via DOMAIN_CONTEXT_BUILDERS when domain-scoped.
CORE_BUILDERS = {
    'blueprint', 'plan', 'pressure', 'intelligence',
    'loops', 'strategy', 'operating_profile',
    'signals', 'compensatory', 'capture',
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


def _match_routine_time_query(msg_lower):
    """Match direct time questions about routine items.

    Examples: "when is my workout?", "what time is prayer?",
    "when is shower scheduled?"
    """
    import re
    # More specific patterns first (with trailing keyword), then catch-all
    _TIME_PATTERNS = (
        r'when(?:\'s| is) (?:my |the )?(\w[\w\s]*?) scheduled',
        r'when(?:\'s| is) (?:my |the )?(\w[\w\s]*?) today',
        r'what time is (?:my |the )?(\w[\w\s]*?)[\?\.\!]*$',
        r'when is (?:my |the )?(\w[\w\s]*?)[\?\.\!]*$',
    )
    for pattern in _TIME_PATTERNS:
        m = re.search(pattern, msg_lower)
        if m:
            return m.group(1).strip()
    return None


def _handle_routine_time_query(user, item_keyword=None):
    """Build a deterministic response for routine time queries."""
    if not item_keyword:
        return None
    try:
        from apps.life.services._routine_internal import get_todays_routine_items
        result = get_todays_routine_items(user)
        items_by_window = result.get('items_by_window', {})
        logs = result.get('logs_by_schedule', {})
        keyword_lower = item_keyword.lower()

        for _window, items in items_by_window.items():
            for item in items:
                name = (item.get('item_name') or '').lower()
                if keyword_lower in name or name in keyword_lower:
                    display_time = item.get('display_time') or item.get('scheduled_time')
                    status = item.get('status', 'pending')
                    item_name = item.get('item_name', item_keyword)
                    rescheduled = item.get('rescheduled_time')

                    if status == 'completed':
                        return f"{item_name} is already done for today."
                    elif rescheduled:
                        return (
                            f"{item_name} was rescheduled to "
                            f"{rescheduled} today."
                        )
                    elif display_time:
                        return f"{item_name} is scheduled for {display_time} today."
                    else:
                        return f"{item_name} is on your schedule today (no specific time set)."
    except Exception as e:
        logger.warning("Routine time query failed: %s", e, exc_info=True)
    return None


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
    """Build a deterministic medication response from SAE state.

    CoS purity: reads from SAE medicine state instead of live
    calculate_medicine_adherence() computation.
    """
    try:
        from apps.core.ai_state.state_engine import get_module_state
        med_state = get_module_state(user, 'medicine') or {}
    except Exception as e:
        logger.warning("Medication SAE state read failed: %s", e, exc_info=True)
        return None

    active_count = med_state.get('active_count', 0)
    if active_count == 0:
        return "No active medication schedules found."

    adherence_7d = med_state.get('adherence_7d')
    today_taken = med_state.get('today_taken', 0)
    today_missed = med_state.get('today_missed', 0)
    today_pending = med_state.get('today_pending', 0)
    expected_today = med_state.get('expected_today', 0)

    parts = []

    # 7-day adherence rate
    if adherence_7d is not None:
        rate_pct = adherence_7d * 100  # SAE stores 0-1
        parts.append(
            f"Your medication adherence this week is **{rate_pct:.0f}%**."
        )
        if rate_pct >= 90:
            parts.append("Great consistency.")
        elif rate_pct >= 70:
            parts.append("Room for improvement — a few missed doses.")
        else:
            parts.append("Several doses were missed this week.")

    # Today's status
    if expected_today > 0:
        parts.append(
            f"Today: {today_taken} taken, {today_missed} missed, "
            f"{today_pending} pending out of {expected_today} scheduled."
        )

    return " ".join(parts) if parts else f"You have {active_count} active medications."


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
    # ── Event-level truth routes (Truth Depth: EVENT) ──
    # These handle "what did I miss?", "what happened yesterday?", etc.
    # Registered first because they answer questions the summary routes can't.
    register_data_route('event_missed_query', _match_event_missed_query, _handle_event_missed_query, 'execution')
    register_data_route('event_timeline_query', _match_event_timeline_query, _handle_event_timeline_query, 'execution')
    register_data_route('event_slippage_query', _match_event_slippage_query, _handle_event_slippage_query, 'execution')

    # ── Summary-level routes (Truth Depth: SUMMARY) ──
    register_data_route('weight_query', _match_weight_query, _handle_weight_query, 'health')
    register_data_route('workout_query', _match_workout_query, _handle_workout_query, 'health')
    register_data_route('sleep_query', _match_sleep_query, _handle_sleep_query, 'health')
    register_data_route('glucose_query', _match_glucose_query, _handle_glucose_query, 'health')
    register_data_route('medication_query', _match_medication_query, _handle_medication_query, 'health')
    register_data_route('steps_query', _match_steps_query, _handle_steps_query, 'health')
    register_data_route('blood_pressure_query', _match_blood_pressure_query, _handle_blood_pressure_query, 'health')
    register_data_route('heart_rate_query', _match_heart_rate_query, _handle_heart_rate_query, 'health')


# =============================================================================
# Event-Level Truth Routes (Truth Depth: EVENT)
# =============================================================================
# These routes provide deterministic event-level answers by reading directly
# from canonical domain models (MedicineLog, RoutineLog, etc.) via the
# Event Access Layer (apps.core.ai_events).
#
# They bypass SAE state — which only has aggregates — and return the specific
# events that the CoS needs to answer questions like "what did I miss?"

def _match_event_missed_query(msg_lower):
    """Match queries asking about missed events."""
    from apps.core.ai_events.truth_depth import needs_event_access, classify_event_query_type
    if not needs_event_access(msg_lower):
        return False
    return classify_event_query_type(msg_lower) == 'missed'


def _handle_event_missed_query(user, msg_lower=None):
    """Handle "what did I miss?" with deterministic event-level data."""
    from datetime import date, timedelta
    from apps.core.ai_events.resolver import EventResolver
    from apps.core.ai_events.formatters import format_missed_events
    from apps.core.ai_events.truth_depth import detect_domain_hint

    try:
        resolver = EventResolver()
        end = date.today()
        start = end - timedelta(days=7)

        # Check if user is asking about a specific domain
        domain_hint = detect_domain_hint(msg_lower) if msg_lower else None

        if domain_hint:
            missed = resolver.get_missed_events(user, domain_hint, start, end)
            response = format_missed_events(missed, domain=domain_hint)
        else:
            missed = resolver.get_all_missed(user, start, end)
            response = format_missed_events(missed)

        # Stash events on module-level for follow-up context storage.
        # personal_assistant.py reads this after terminal route.
        _stash_resolved_events(missed)
        return response
    except Exception as e:
        logger.warning(
            "Event missed query failed for user=%s: %s",
            user.id, e, exc_info=True,
        )
        return None  # Fall through to existing pipeline


def _match_event_timeline_query(msg_lower):
    """Match queries asking about day timeline."""
    from apps.core.ai_events.truth_depth import needs_event_access, classify_event_query_type
    if not needs_event_access(msg_lower):
        return False
    return classify_event_query_type(msg_lower) == 'timeline'


def _handle_event_timeline_query(user, msg_lower=None):
    """Handle "what happened yesterday?" with deterministic event data."""
    from datetime import date, timedelta
    from apps.core.ai_events.resolver import EventResolver
    from apps.core.ai_events.formatters import format_day_timeline

    try:
        # Determine target date from message
        target = _parse_timeline_date(msg_lower) if msg_lower else None
        if target is None:
            target = date.today() - timedelta(days=1)  # Default: yesterday

        resolver = EventResolver()
        events = resolver.get_day_timeline(user, target)
        response = format_day_timeline(events, target)
        _stash_resolved_events(events)
        return response
    except Exception as e:
        logger.warning(
            "Event timeline query failed for user=%s: %s",
            user.id, e, exc_info=True,
        )
        return None  # Fall through


def _parse_timeline_date(msg_lower):
    """Extract target date from a timeline query message.

    Deterministic date parsing — no LLM inference.
    Returns date or None.
    """
    from datetime import date, timedelta

    today = date.today()

    if 'today' in msg_lower:
        return today
    if 'yesterday' in msg_lower:
        return today - timedelta(days=1)
    if 'this week' in msg_lower:
        # Return start of current week (Monday)
        return today - timedelta(days=today.weekday())
    if 'last week' in msg_lower:
        return today - timedelta(days=today.weekday() + 7)

    # Day name matching (e.g., "what happened monday")
    _DAYS = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6,
    }
    for day_name, day_num in _DAYS.items():
        if day_name in msg_lower:
            # Find the most recent occurrence of this day
            days_back = (today.weekday() - day_num) % 7
            if days_back == 0:
                days_back = 7  # If today is that day, assume last week
            return today - timedelta(days=days_back)

    return None  # Can't determine — caller uses default


def _match_event_slippage_query(msg_lower):
    """Match queries asking about routine slippage."""
    from apps.core.ai_events.truth_depth import needs_event_access, classify_event_query_type
    if not needs_event_access(msg_lower):
        return False
    return classify_event_query_type(msg_lower) == 'slippage'


def _handle_event_slippage_query(user, msg_lower=None):
    """Handle "when did my routine start slipping?" with deterministic trend data."""
    from apps.core.ai_events.resolver import EventResolver
    from apps.core.ai_events.formatters import format_slippage_trend

    try:
        resolver = EventResolver()
        trend = resolver.get_routine_trend(user, lookback_days=14)
        return format_slippage_trend(trend)
    except Exception as e:
        logger.warning(
            "Event slippage query failed for user=%s: %s",
            user.id, e, exc_info=True,
        )
        return None  # Fall through


_register_builtin_routes()
