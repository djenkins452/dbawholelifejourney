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
import re
import time
from typing import List, Optional

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


def _try_daily_briefing_gate(user, conversation):
    """First-of-day hard override — Daily Briefing.

    Checks conversation.metadata['last_briefing_date'] against today
    (user timezone). If this is the first interaction of the day,
    renders a deterministic Daily Briefing and marks it delivered.

    This executes BEFORE all other routing phases. It is the highest
    priority gate in the pipeline.

    Returns:
        RouteResult if first-of-day briefing should fire, None otherwise.
    """
    try:
        from apps.core.utils import get_user_today
        from apps.ai.beth_checkin_renderer import render_daily_briefing
        from apps.ai.executive_briefing import mark_briefing_delivered

        today = get_user_today(user)
        metadata = conversation.metadata or {}
        last_briefing_date = metadata.get('last_briefing_date')

        if last_briefing_date == str(today):
            return None  # Already briefed today — normal routing

        # First interaction of the day — render Daily Briefing
        response = render_daily_briefing(user)
        if not response:
            return None  # Renderer failed — fall through to normal routing

        # Mark delivered AFTER successful render (never before)
        mark_briefing_delivered(conversation)

        logger.info(
            "DAILY_BRIEFING_GATE user=%s date=%s",
            user.id, today,
        )

        return RouteResult(
            category=RouteCategory.DETERMINISTIC_DATA,
            response=response,
            route_name='deterministic_daily_briefing',
            domain=None,
            is_terminal=True,
        )
    except Exception:
        logger.error(
            "[DAILY BRIEFING GATE] Failed for user=%s, falling through",
            user.id if user else '?', exc_info=True,
        )
        return None


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

    # ══════════════════════════════════════════════════════════
    # RESPONSE GOVERNOR — SINGLE RESPONSE AUTHORITY
    # This is the ABSOLUTE FIRST gate. No route, no briefing, no
    # pre-processing may fire before the governor approves it.
    # The governor determines exactly ONE response type per turn.
    # ══════════════════════════════════════════════════════════
    _governor_type = None
    try:
        from apps.ai.response_governor import (
            resolve_response_type,
            ResponseType,
        )
        _governor_type = resolve_response_type(user, message)

        if _governor_type == ResponseType.REFLECTIVE:
            result = RouteResult(
                route_name='governor_reflective',
                skip_intent=True,
            )
            result.elapsed_ms = (time.monotonic() - t_start) * 1000
            _log_route_decision(result, user, message)
            return result
    except ImportError:
        pass
    except Exception as gov_err:
        logger.warning(
            "RESPONSE_GOVERNOR failed: %s — proceeding (fail-open)",
            gov_err,
        )

    # ── Phase -2: DAILY BRIEFING — first-of-day hard override ─────
    # If this is the user's first interaction today, render a full
    # Daily Briefing BEFORE any other routing. This is non-negotiable:
    # the CoS must orient the user before reacting to their message.
    if conversation is not None and user is not None:
        result = _try_daily_briefing_gate(user, conversation)
        if result is not None:
            result.elapsed_ms = (time.monotonic() - t_start) * 1000
            _log_route_decision(result, user, message)
            return result

    # ── Phase -1: Event follow-up detection ────────────────────────
    if conversation is not None:
        result = _try_event_followup(msg_lower, conversation)
        if result is not None:
            result.elapsed_ms = (time.monotonic() - t_start) * 1000
            _log_route_decision(result, user, message)
            return result

    # Phase 18.3/18.4 reflective mode check: REMOVED. Superseded by
    # the Response Governor at the absolute top of this function.
    # The governor handles both REFLECTIVE and ALERT types centrally.

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

    # ── Phase 11.1: Decision query — RUNS FIRST (before focus query)
    # _is_decision_query is a SUPERSET of _is_focus_query. If we let
    # the Phase 4 focus route fire first, it catches "biggest risk"
    # and "fix first" queries and routes them ALL to the same
    # _build_focus_query_response — bypassing the Phase 11 intent
    # classification entirely. Moving the decision route FIRST
    # ensures every decision query gets classified by intent and
    # dispatched to the correct handler (EXECUTION_NOW / BIGGEST_RISK
    # / FIX_FIRST). Non-decision queries fall through to the focus
    # route below, which still handles "am I behind" etc.
    result = _try_decision_query_route(msg_lower, user)
    if result is not None:
        result.elapsed_ms = (time.monotonic() - t_start) * 1000
        _log_route_decision(result, user, message)
        return result

    # ── Phase 4: Focus / behind / status query — HARD OVERRIDE ───
    # Now runs AFTER Phase 11 decision routing. Only fires for
    # queries that _is_decision_query did NOT match (which is rare
    # since _is_decision_query is a superset, but kept for backward
    # compatibility with any edge-case phrase).
    result = _try_focus_query_route(msg_lower, user)
    if result is not None:
        result.elapsed_ms = (time.monotonic() - t_start) * 1000
        _log_route_decision(result, user, message)
        return result

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


# =============================================================================
# Phase 4 — Decision Enforcement: Focus Query Hard Override
# =============================================================================
#
# When the user asks "am I behind?" / "how am I doing?" / "what should I focus
# on?" / "what's left?", CoS MUST lead with the deterministic right_now_focus
# computed by the Phase 3 trust contract — never with a routine list, never
# with a generic encouragement, never with raw data.
#
# This matcher fires BEFORE the existing _NEXT_ACTION_PHRASES route and uses
# the same priority. The handler reads right_now_focus from the SAE state and
# layers in time intelligence (compute_time_status) to answer "am I behind"
# correctly — accounting for schedule buffers instead of saying "yes" the
# instant the clock passes a scheduled time.

_FOCUS_QUERY_PHRASES = (
    'am i behind',
    "i'm behind",
    'am i on track',
    "am i ok",
    'how am i doing',
    "how's my day",
    'hows my day',
    'how is my day',
    'how am i tracking',
    'how am i looking',
    'how am i progressing',
    'where am i at',
    'where do i stand',
    'whats my focus',
    "what's my focus",
    'what is my focus',
    'whats most important',
    "what's most important",
    'what matters most',
    'what should i prioritize right now',
)


def _is_focus_query(msg_lower):
    """Phase 4 — match the explicit focus / status / behind queries."""
    return any(phrase in msg_lower for phrase in _FOCUS_QUERY_PHRASES)


# ─────────────────────────────────────────────────────────────────────
# Phase 8 — Decision Query Classification (semantic + phrase-based)
# ─────────────────────────────────────────────────────────────────────
#
# Superset of the focus matcher. Covers the task spec's 5 categories:
#     "what should I do"
#     "what is the biggest risk"
#     "what is not working"
#     "help me decide"
#     "what should I fix first"
#
# Rule-based (no ML, no LLM). Uses word-level substring checks so we
# catch mild paraphrases like "whats not working" / "help me pick".

# Exact phrase anchors — broader than _FOCUS_QUERY_PHRASES.
_DECISION_QUERY_EXACT_PHRASES = (
    # Biggest risk / problem / concern
    'biggest risk',
    "what's my biggest",
    'whats my biggest',
    'what is my biggest',
    'biggest problem',
    'biggest concern',
    'biggest issue',
    'biggest threat',
    # Not working
    'not working',
    "isn't working",
    'isnt working',
    "what's broken",
    'whats broken',
    'what is broken',
    # Help me decide
    'help me decide',
    'help me pick',
    'help me choose',
    'decide for me',
    'make the call',
    'make the decision',
    "i can't decide",
    'i cannot decide',
    # Fix queries
    'what should i fix',
    'what do i fix',
    'what to fix',
    'fix first',
)


def _is_decision_query(msg_lower):
    """Phase 8 — deterministic decision-query classifier.

    Returns True if the message is asking for a decisive next action.
    Combines:

    1. The existing _FOCUS_QUERY_PHRASES anchors (Phase 4)
    2. The _NEXT_ACTION_PHRASES anchors
    3. The new _DECISION_QUERY_EXACT_PHRASES
    4. Semantic patterns that catch paraphrased forms:
        - "what" + ("do" or "fix" or "focus" or "should")
        - "biggest" + ("risk" / "problem" / "concern" / "issue")
        - "help" + "decide"/"pick"/"choose"

    This MUST be rule-based and fast — it gates every user message
    in the deterministic routing layer.
    """
    if not msg_lower or not isinstance(msg_lower, str):
        return False

    # Fast path: exact-phrase hits via the three established lists.
    if _is_focus_query(msg_lower):
        return True
    if _is_next_action_query(msg_lower):
        return True
    for phrase in _DECISION_QUERY_EXACT_PHRASES:
        if phrase in msg_lower:
            return True

    # Semantic pattern path — catches mild paraphrases.
    has_what = 'what' in msg_lower
    has_should = 'should' in msg_lower
    has_help = 'help' in msg_lower

    # "what should I X" where X implies action
    if has_what and has_should:
        for verb in ('do', 'fix', 'focus', 'tackle', 'start',
                     'prioritize', 'handle', 'address'):
            if verb in msg_lower:
                return True

    # "what do I X" where X implies action
    if has_what and ('do i' in msg_lower or 'i do' in msg_lower):
        for verb in ('fix', 'focus', 'tackle', 'start', 'prioritize'):
            if verb in msg_lower:
                return True

    # "biggest <concern>"
    if 'biggest' in msg_lower:
        for noun in ('risk', 'problem', 'concern', 'issue',
                     'threat', 'gap', 'worry'):
            if noun in msg_lower:
                return True

    # "help me <decide>"
    if has_help:
        for verb in ('decide', 'pick', 'choose', 'figure out',
                     'prioritize'):
            if verb in msg_lower:
                return True

    return False


# ─────────────────────────────────────────────────────────────────────
# Phase 11 — Decision Intent Classification
# ─────────────────────────────────────────────────────────────────────
#
# Different decision questions require different selection logic:
#   EXECUTION_NOW: "what should I do right now?" → overdue/upcoming task
#   BIGGEST_RISK:  "what is my biggest risk?"    → health/adherence risk
#   FIX_FIRST:     "what should I fix first?"    → hybrid (risk OR exec)
#
# The classifier is deterministic, rule-based, and fast. It maps the
# user's INTENT to one of three modes that route to different handlers.

# Phrase anchors for each intent.
_RISK_PHRASES = (
    'biggest risk', 'biggest concern', 'biggest problem',
    'biggest issue', 'biggest threat', 'biggest gap',
    'biggest worry', "what's my risk", 'whats my risk',
    'what is my risk', "what's at risk", 'health risk',
    'what am i risking', 'where am i most at risk',
    'not working', "isn't working", 'isnt working',
    "what's broken", 'whats broken', 'what is broken',
    # Phase 11.1: additional phrases from task spec
    'risk right now', 'what is wrong', "what's wrong",
    'whats wrong', 'what went wrong',
)

_FIX_PHRASES = (
    'fix first', 'fix next', 'what should i fix',
    'what do i fix', 'what to fix', 'what needs fixing',
    'what needs attention', 'what needs work',
    'help me decide', 'help me pick', 'help me choose',
    'help me prioritize', 'decide for me', 'make the call',
)


def _classify_decision_intent(msg_lower):
    """Phase 11 — classify a decision query into one of three modes.

    Returns:
        'BIGGEST_RISK'   — user is asking about risk / what's broken
        'FIX_FIRST'      — user is asking what to fix / help decide
        'EXECUTION_NOW'  — user is asking what to do (default)

    EXECUTION_NOW is the default for any decision query that doesn't
    match the more specific RISK or FIX patterns.
    """
    if not msg_lower:
        return 'EXECUTION_NOW'

    for phrase in _RISK_PHRASES:
        if phrase in msg_lower:
            return 'BIGGEST_RISK'

    for phrase in _FIX_PHRASES:
        if phrase in msg_lower:
            return 'FIX_FIRST'

    return 'EXECUTION_NOW'


# ═════════════════════════════════════════════════════════════════
# Phase 19 — CoS Decision Response Formatter
#
# The handlers below (_build_focus_query_response, _build_biggest_risk_response,
# _build_fix_first_response) all produce a deterministic string that the
# CoS uses as its reply for "what should I do right now" / "what's my
# biggest risk" / "what should I fix first". The previous format —
#
#     Do this next: <action>
#     Reason:
#     <why>
#     Priority: <label>
#
# — felt like a checklist. This layer rewrites output into the
# four-part CoS structure defined in the Phase 19 decision-layer brief:
#
#   (1) Quick wins       — optional, max 2, "<2 min each"
#   (2) Primary action   — required unless intentional shutdown
#   (3) Context          — optional short signal-based reason
#   (4) Stop condition   — late-evening shutdown when appropriate
#
# Selection logic (which items to surface) is unchanged. Only the
# assembly + phrasing and the quick-action stacking rule change.
# ═════════════════════════════════════════════════════════════════


def _is_late_evening(user) -> bool:
    """True when the user's local hour is >= 20 or < 5.

    Late-evening flips the decision frame: we stop suggesting heavy
    new work and favor intentional shutdown.
    """
    try:
        from apps.core.utils import get_user_now
        now = get_user_now(user)
        hour = now.hour
    except Exception:
        return False
    return hour >= 20 or hour < 5


def _strip_trailing_punct(text: str) -> str:
    if not text:
        return ""
    s = text.strip()
    while s and s[-1] in ".!?;":
        s = s[:-1]
    return s.strip()


def _lowercase_first(text: str) -> str:
    if not text:
        return ""
    return text[0].lower() + text[1:]


def _sentence_case(text: str) -> str:
    if not text:
        return ""
    return text[0].upper() + text[1:]


def _format_cos_decision_response(
    *,
    quick_wins: Optional[List[str]] = None,
    primary_action: Optional[str] = None,
    context_reason: Optional[str] = None,
    lead_with_context: bool = False,
) -> str:
    """Assemble the four-part CoS decision response.

    Args:
        quick_wins: Up to 2 short phrases (e.g. "your Magnesium").
            Narratively combined into one "Take X and Y now — quick
            and overdue." line. Extras beyond 2 are dropped (per
            brief: quick wins must never dominate).
        primary_action: Full sentence/clause for the main move.
            Required unless the caller is intentionally producing a
            shutdown-only message (edge case).
        context_reason: Short explanation of WHY, tied to signals.
        lead_with_context: If True, the context line precedes
            everything else (risk-driven openings like "Your glucose
            is trending up and your workout streak broke.").
    """
    qws = [q.strip() for q in (quick_wins or []) if q and q.strip()]
    qws = qws[:2]  # hard cap per brief
    lines: List[str] = []

    # (1 or 3a) Context leading — risk-mode openings only.
    if lead_with_context and context_reason:
        lines.append(_strip_trailing_punct(context_reason) + ".")

    # (1) Quick wins
    if qws:
        if len(qws) == 1:
            lines.append(f"Take {qws[0]} now — quick and overdue.")
        else:
            lines.append(
                f"Take {qws[0]} and {qws[1]} now — "
                "both are quick and overdue."
            )

    # (2) Primary action
    if primary_action:
        primary_clean = _strip_trailing_punct(primary_action)
        has_prefix = bool(qws) or (lead_with_context and context_reason)
        if has_prefix:
            lines.append(f"Then {_lowercase_first(primary_clean)}.")
        else:
            # Standalone primary — sentence-case so downstream
            # imperative detectors recognize it.
            lines.append(_sentence_case(primary_clean) + ".")

    # (3b) Trailing context — only when not already led with it.
    if context_reason and not lead_with_context:
        lines.append(_strip_trailing_punct(context_reason) + ".")

    # Deduplicate consecutive identical lines (edge case).
    dedup: List[str] = []
    for ln in lines:
        if not dedup or dedup[-1].strip() != ln.strip():
            dedup.append(ln)
    assembled = "\n".join(dedup)

    # Phase 19.1: tone refinement as the very last step of every
    # handler's output path. Every handler ends by calling this
    # formatter, so the refiner runs exactly once per response.
    return refine_cos_response(assembled)


# ═════════════════════════════════════════════════════════════════
# Phase 19.1 — CoS tone refinement (post-processing only)
#
# Applied at the tail of _format_cos_decision_response so every
# handler's output runs through it. All transformations are
# deterministic regex substitutions — no randomness, no reordering,
# no added actions, no removed actions. Meaning is preserved; only
# wording is tightened.
#
# Rules (from the Phase 19.1 brief):
#   1. Collapse "your X and your Y" → "your X and Y"
#   2. Strip "(scheduled at HH:MM)" parentheticals
#   3. Convert "and N more item(s) are also behind: A, B" →
#      "along with A and B"
#   4. Merge primary-line title with a context line that restates
#      it: "Then start X.\nX is overdue …" → "Then start X —
#      it's already overdue …"
#   5. Soften "… so tomorrow starts clean" → "… — tomorrow starts
#      clean" on the shutdown phrase
#   6. Safety scrub: strip "consider" (never allowed)
# ═════════════════════════════════════════════════════════════════

_REFINE_YOUR_AND_YOUR_RE = re.compile(
    r'\byour (.+?) and your\b'
)
_REFINE_SCHEDULED_AT_RE = re.compile(
    r'\s*\(scheduled at \d{1,2}:\d{2}\)'
)
_REFINE_N_MORE_ITEMS_RE = re.compile(
    r' and \d+ more item\(s\) are also behind: ([^.]+)'
)
_REFINE_SHUTDOWN_RE = re.compile(
    r'for the night so tomorrow starts clean'
)
_REFINE_CONSIDER_RE = re.compile(
    r'\b[Cc]onsider\s+'
)
# "Then start TITLE." / "Start TITLE." / "Complete TITLE." /
# "Get back on track by starting TITLE." / "Close this gap —
# complete TITLE."
_REFINE_PRIMARY_TITLE_RES = (
    re.compile(
        r'^(?:Then\s+)?'
        r'(?:[Ss]tart|[Cc]omplete|[Tt]ake)\s+'
        r'(.+?)\.$'
    ),
    re.compile(
        r'^(?:Then\s+)?'
        r'[Gg]et back on track by starting\s+(.+?)\.$'
    ),
    re.compile(
        r'^(?:Then\s+)?'
        r'[Cc]lose this gap — complete\s+(.+?)\.$'
    ),
)


def _refine_item_list(items_raw: str) -> str:
    """"X, Y, Z" → "X, Y, and Z" (Oxford) or "X and Y" for two.

    Used when rewriting "along with …" clauses after the
    "N more item(s) are also behind" transform.
    """
    items = [p.strip() for p in items_raw.split(',') if p.strip()]
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _refine_merge_primary_and_context(text: str) -> str:
    """Collapse adjacent primary + context lines that repeat the
    primary's task title. Preserves the section (primary remains on
    its own line); only the redundant title restatement is merged
    into a trailing clause."""
    lines = text.splitlines()
    if len(lines) < 2:
        return text

    out: list = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else None

        merged_line = None
        if nxt:
            title = None
            for pat in _REFINE_PRIMARY_TITLE_RES:
                m = pat.match(cur)
                if m:
                    title = m.group(1)
                    break

            if title and nxt.startswith(title):
                rest = nxt[len(title):].lstrip()
                # Case A: "<TITLE> is overdue[ along with X]."
                if rest.startswith('is overdue'):
                    tail = rest[len('is overdue'):]
                    tail = tail.rstrip('.')
                    merged_line = (
                        cur[:-1]  # strip trailing "."
                        + " — it's already overdue"
                        + tail
                        + "."
                    )
                # Case B: "<TITLE> is a … item that hasn't been
                # completed today."  (Priority 3 foundational branch)
                elif rest.startswith('is a ') or rest.startswith('is still'):
                    merged_line = cur[:-1] + " — " + rest
                # Case C: "<TITLE> is the fastest way to regain
                # momentum" (fix-first recovery branch)
                elif rest.startswith('is the fastest way'):
                    merged_line = cur[:-1] + " — " + rest
                # Case D: "<TITLE> is your next item" (upcoming)
                elif rest.startswith('is your next item'):
                    merged_line = cur[:-1] + " — " + rest

        if merged_line is not None:
            out.append(merged_line)
            i += 2
        else:
            out.append(cur)
            i += 1

    return '\n'.join(out)


def refine_cos_response(text: str) -> str:
    """Phase 19.1 — deterministic tone refinement.

    Post-processes the already-assembled CoS decision response.
    Does NOT change meaning, reorder sections, remove the primary
    action, or add new actions. Idempotent: ``refine(refine(x)) ==
    refine(x)`` for all inputs.
    """
    if not text:
        return text

    out = text

    # 1. Collapse "your X and your Y" → "your X and Y". Iterate
    #    until stable in case of nested occurrences (rare).
    prev = None
    while prev != out:
        prev = out
        out = _REFINE_YOUR_AND_YOUR_RE.sub(r'your \1 and', out)

    # 2. Strip "(scheduled at HH:MM)" parentheticals.
    out = _REFINE_SCHEDULED_AT_RE.sub('', out)

    # 3. "and N more item(s) are also behind: A, B" → "along with A and B"
    def _n_more_sub(m):
        return ' along with ' + _refine_item_list(m.group(1))
    out = _REFINE_N_MORE_ITEMS_RE.sub(_n_more_sub, out)

    # 4. Merge primary + duplicated-title context line.
    out = _refine_merge_primary_and_context(out)

    # 5. Soften the shutdown phrase.
    out = _REFINE_SHUTDOWN_RE.sub(
        'for the night — tomorrow starts clean', out,
    )

    # 6. Safety scrub: drop "consider".
    out = _REFINE_CONSIDER_RE.sub('', out)

    return out


_COS_DECISIVE_STARTS = (
    "Take", "Start", "Complete", "Get ", "Close ", "Address",
    "Log", "Plan", "Shut", "Stay ", "Clear ", "Then ",
    # Context-lead sentences commonly start with these (risk mode):
    "You", "Your", "Medication", "Health",
    "Cross-domain", "No ", "You're",
)


def _looks_like_cos_decision_response(resp) -> bool:
    """True if ``resp`` matches the Phase 19 CoS decision contract.

    Contract:
    * non-empty string,
    * no legacy format markers (``Do this next:`` / ``Reason:`` / ``Priority:``),
    * at least one line starts with a recognized decisive/context opener.

    Used by the decision-query gate to decide whether a handler output
    is healthy or should be swapped for the safe fallback.
    """
    if not resp or not isinstance(resp, str):
        return False
    stripped = resp.strip()
    if not stripped:
        return False
    # Reject legacy markers — those should have been removed.
    for marker in ("Do this next:", "Reason:\n", "Priority:"):
        if marker in resp:
            return False
    for line in (ln for ln in resp.splitlines() if ln.strip()):
        if any(line.startswith(v) for v in _COS_DECISIVE_STARTS):
            return True
    return False


def _build_biggest_risk_response(user):
    """Phase 11 — deterministic BIGGEST_RISK response.

    Evaluates signals and health data to find the single highest-risk
    issue. Priority order:

    1. Medication adherence crisis (0 doses taken today + low 7d rate)
    2. Health intelligence risk flags (from trend_analyzer)
    3. Cross-domain correlation signals (from CDCE)
    4. Overdue critical commitments (foundational items missed)
    5. Signal-based focus (from trust contract)

    Always returns an Action-First string. Never None.
    """
    try:
        from apps.core.ai_orchestrator.cos_context import _fresh_module_state

        # ── 1. Medication adherence crisis ──────────────────────
        med = _fresh_module_state(user, 'medicine')
        expected = med.get('expected_today', 0) or 0
        taken = med.get('today_taken', 0) or 0
        adherence_7d = med.get('adherence_7d')

        if expected > 0 and taken == 0 and adherence_7d is not None:
            if adherence_7d < 80:
                return _format_cos_decision_response(
                    primary_action="Take your overdue medications now",
                    context_reason=(
                        f"Medication adherence is at {adherence_7d}% "
                        f"this week and you have 0 of {expected} doses "
                        f"taken today — missed doses compound"
                    ),
                    lead_with_context=True,
                )

        # ── 2. Health intelligence risk flags ───────────────────
        health = _fresh_module_state(user, 'health')
        hi = None
        try:
            from apps.health.services.cos_health_context import (
                build_health_intelligence,
            )
            hi = build_health_intelligence(user)
        except Exception:
            pass

        if hi:
            top_rec = hi.get('top_recommendation', '')
            risk_flags = hi.get('risk_flags') or []

            if risk_flags:
                # Pick the first risk flag (trend_analyzer ranks by severity)
                if isinstance(risk_flags[0], dict):
                    flag_text = risk_flags[0].get('message', str(risk_flags[0]))
                else:
                    flag_text = str(risk_flags[0])

                # Build an actionable response from the risk
                action = _risk_to_action(flag_text, med, health)
                ctx_text = (
                    f"Health intelligence flagged: {flag_text}. {top_rec}"
                    if top_rec else
                    f"Health intelligence flagged: {flag_text}"
                )
                return _format_cos_decision_response(
                    primary_action=_strip_trailing_punct(action),
                    context_reason=ctx_text,
                    lead_with_context=True,
                )

        # ── 3. Cross-domain signals ─────────────────────────────
        # These come from the CDCE (correlation detection engine).
        # Use them if no health-intelligence risk flags fired.
        try:
            from apps.core.ai_orchestrator.cos_context import build_cos_context
            ctx = build_cos_context(user)
            xd_signals = ctx.get('cross_domain_signals') or []
            # Prefer high-severity first
            high_sev = [s for s in xd_signals if s.get('severity') == 'high']
            med_sev = [s for s in xd_signals if s.get('severity') == 'medium']
            best_signal = (high_sev or med_sev or [None])[0]
            if best_signal:
                action = best_signal.get('recommended_action', '')
                summary = best_signal.get('summary', '')
                if action:
                    return _format_cos_decision_response(
                        primary_action=_strip_trailing_punct(action),
                        context_reason=(
                            f"Cross-domain pattern detected: {summary}"
                            if summary else
                            "Cross-domain pattern detected"
                        ),
                        lead_with_context=True,
                    )
        except Exception:
            pass

    except Exception as e:
        logger.warning(
            "[BIGGEST_RISK] risk evaluation failed for user=%s: %s",
            getattr(user, 'id', '?'), e,
        )

    # ── Fallback: no critical risk, but look for minor issues ──
    # Phase 11.2: never return generic "review signals" or None.
    # Instead, produce an explicit low-risk assessment with the
    # most relevant minor issue (consistency, routine slipping, etc.)
    try:
        # Check routine status
        from apps.core.ai_state.state_builder import MODULE_BUILDERS
        exec_builder = MODULE_BUILDERS.get('execution')
        if exec_builder:
            exec_state = exec_builder(user) or {}
            exec_items = exec_state.get('items', [])
            overdue_count = sum(
                1 for i in exec_items
                if i.get('time_status') == 'overdue'
                and not i.get('completed_today')
            )
            incomplete_foundational = sum(
                1 for i in exec_items
                if not i.get('completed_today')
                and i.get('importance') == 'foundational'
            )
            if overdue_count > 0:
                return _format_cos_decision_response(
                    primary_action=(
                        f"Clear your {overdue_count} overdue item(s) "
                        "now — falling behind is your biggest risk today"
                    ),
                    context_reason=(
                        "No critical health risks surfaced, but "
                        f"{overdue_count} item(s) are overdue. Letting "
                        "them accumulate erodes consistency"
                    ),
                )
            if incomplete_foundational > 0:
                return _format_cos_decision_response(
                    primary_action=(
                        f"Complete your remaining "
                        f"{incomplete_foundational} foundational "
                        "item(s) for the day"
                    ),
                    context_reason=(
                        "No critical health risks surfaced. Skipping "
                        "foundational commitments is your biggest risk"
                    ),
                )
    except Exception:
        pass

    # Truly no risks — explicit low-risk state
    return _format_cos_decision_response(
        primary_action="Stay on your current plan",
        context_reason=(
            "No major risks right now. Medication adherence is "
            "acceptable, no health flags surfaced, and no critical "
            "patterns detected"
        ),
        lead_with_context=True,
    )


def _risk_to_action(flag_text, med_state, health_state):
    """Convert a risk flag string into a concrete action."""
    flag_lower = flag_text.lower()
    if 'medication' in flag_lower or 'adherence' in flag_lower:
        return "Take your overdue medications now."
    if 'sleep' in flag_lower:
        return "Address your sleep debt — commit to 7+ hours tonight."
    if 'protein' in flag_lower:
        return "Increase your protein intake at your next meal."
    if 'glucose' in flag_lower or 'blood sugar' in flag_lower:
        return "Check your glucose level and adjust your next meal."
    if 'weight' in flag_lower:
        return "Review your nutrition plan for today."
    # Generic: make it active
    return f"Address this: {flag_text}"


def _build_fix_first_response(user):
    """Phase 11 / 11.2 — deterministic FIX_FIRST response (coach mode).

    Answers: "What will get me back on track fastest?"

    Unlike EXECUTION_NOW (operator — "do this next") and BIGGEST_RISK
    (analyst — "this is your risk"), FIX_FIRST speaks as a COACH:
    - Acknowledges drift when the user is behind
    - Frames the action as a recovery step, not just the next item
    - Uses corrective language ("get back on track", "close this gap")

    Priority order:
    1. Critical medication crisis → urgent recovery action
    2. Overdue execution items → recovery-framed version of top item
    3. Foundational execution gaps → gap-closure framing
    4. No gaps → "you're on track" acknowledgment
    """
    try:
        from apps.core.ai_orchestrator.cos_context import _fresh_module_state
        from apps.core.ai_state.state_builder import MODULE_BUILDERS

        # ── 1. Critical medication crisis ───────────────────────
        med = _fresh_module_state(user, 'medicine')
        expected = med.get('expected_today', 0) or 0
        taken = med.get('today_taken', 0) or 0
        adherence_7d = med.get('adherence_7d')

        if expected > 0 and taken == 0 and adherence_7d is not None:
            if adherence_7d < 70:
                return _format_cos_decision_response(
                    primary_action=(
                        "Take your overdue medications now — the "
                        "fastest way to close your biggest gap today"
                    ),
                    context_reason=(
                        f"You've drifted on medication consistency "
                        f"({adherence_7d}% this week, 0 of {expected} "
                        f"doses today). Every missed dose compounds"
                    ),
                    lead_with_context=True,
                )

        # ── 2. Quick-action + overdue stacking (Phase 19) ────────
        # Same stacking contract as EXECUTION_NOW: up to 2 quick wins
        # precede the primary recovery action — they never replace it.
        exec_builder = MODULE_BUILDERS.get('execution')
        quick_wins_titles: List[str] = []
        quick_ids: set = set()
        primary_action: Optional[str] = None
        context_reason: Optional[str] = None

        if exec_builder:
            exec_state = exec_builder(user) or {}
            exec_items = exec_state.get('items', [])

            _QUICK_TYPES_FF = frozenset({
                'medication_dose', 'supplement_dose',
            })
            quick_ff = [
                i for i in exec_items
                if i.get('source_type') in _QUICK_TYPES_FF
                and i.get('time_status') in ('overdue', 'in_progress')
                and not i.get('completed_today')
            ]
            if quick_ff:
                _qa_imp_ff = {
                    'foundational': 0, 'important': 1,
                    'standard': 1, 'flexible': 2,
                }
                quick_ff.sort(key=lambda x: (
                    0 if x.get('source_type') == 'medication_dose' else 1,
                    _qa_imp_ff.get(x.get('importance', 'flexible'), 2),
                    x.get('scheduled_time', '99:99'),
                ))
                for q in quick_ff[:2]:
                    t = q.get('title') or ''
                    if t:
                        quick_wins_titles.append(f"your {t}")
                # (source_type, source_id) of ALL quick candidates —
                # see EXECUTION_NOW dedup rationale.
                quick_ids = {
                    (q.get('source_type'), q.get('source_id'))
                    for q in quick_ff
                    if q.get('source_id') is not None
                }

            # ── Overdue execution items → recovery framing ──────
            _IMPLIED_DONE = frozenset({
                'wake up', 'go to bed', 'go to sleep',
                'lights out', 'get up', 'get out of bed',
            })

            overdue_raw = [
                i for i in exec_items
                if i.get('time_status') == 'overdue'
                and not i.get('completed_today')
                and (i.get('source_type'), i.get('source_id')) not in quick_ids
                and (i.get('title') or '').strip().lower()
                    not in _IMPLIED_DONE
            ]
            # Phase 12 + 15: filter blocked items in fix-first path.
            # Only enforce sequence for routine groups (not medication/
            # supplement windows which are parallel).
            _SEQUENTIAL_FF = frozenset({'routine'})
            _group_gates_ff = {}
            for i in exec_items:
                gid = i.get('execution_group_id')
                if gid is None or i.get('completed_today'):
                    continue
                gtype = i.get('execution_group_type', '')
                if gtype not in _SEQUENTIAL_FF:
                    continue
                tl = (i.get('title') or '').strip().lower()
                if tl in _IMPLIED_DONE:
                    continue
                st = i.get('scheduled_time', '99:99')
                if gid not in _group_gates_ff or st < _group_gates_ff[gid]:
                    _group_gates_ff[gid] = st

            overdue = []
            for item in overdue_raw:
                gid = item.get('execution_group_id')
                if gid is None:
                    overdue.append(item)
                    continue
                gtype = item.get('execution_group_type', '')
                if gtype not in _SEQUENTIAL_FF:
                    overdue.append(item)
                    continue
                gate = _group_gates_ff.get(gid)
                if gate is None or item.get('scheduled_time', '99:99') <= gate:
                    overdue.append(item)

            # Tasks before routine items, foundational first
            _imp_order = {
                'foundational': 0, 'important': 1, 'standard': 1, 'flexible': 2,
            }
            overdue.sort(key=lambda x: (
                0 if x.get('source_type') == 'task' else 1,
                _imp_order.get(x.get('importance', 'flexible'), 2),
                x.get('scheduled_time', '99:99'),
            ))

            if overdue:
                top = overdue[0]
                n = len(overdue)
                title = top['title']
                if n > 1:
                    others = ', '.join(
                        i['title'] for i in overdue[1:4]
                    )
                    drift_note = (
                        f"You're behind on {n} items ({others}). "
                        f"{title} is the fastest way to regain momentum"
                    )
                else:
                    drift_note = (
                        f"You've fallen behind. {title} is the "
                        f"fastest way to regain momentum"
                    )
                primary_action = f"Get back on track by starting {title}"
                context_reason = drift_note

            # ── Foundational gaps → gap-closure framing ─────────
            if not primary_action:
                incomplete_raw = [
                    i for i in exec_items
                    if not i.get('completed_today')
                    and (i.get('source_type'), i.get('source_id')) not in quick_ids
                    and i.get('importance') in ('foundational', 'important')
                    and (i.get('title') or '').strip().lower()
                        not in _IMPLIED_DONE
                ]
                # Phase 12 + 15: filter blocked items (routine only)
                incomplete = []
                for item in incomplete_raw:
                    gid = item.get('execution_group_id')
                    if gid is None:
                        incomplete.append(item)
                        continue
                    gtype = item.get('execution_group_type', '')
                    if gtype not in _SEQUENTIAL_FF:
                        incomplete.append(item)
                        continue
                    gate = _group_gates_ff.get(gid)
                    if gate is None or item.get('scheduled_time', '99:99') <= gate:
                        incomplete.append(item)
                incomplete.sort(key=lambda x: (
                    0 if x.get('source_type') == 'task' else 1,
                    _imp_order.get(x.get('importance', 'flexible'), 2),
                    x.get('scheduled_time', '99:99'),
                ))
                if incomplete:
                    top = incomplete[0]
                    primary_action = (
                        f"Close this gap — complete {top['title']}"
                    )
                    context_reason = (
                        f"No urgent overdue items, but {top['title']} "
                        f"is a {top.get('importance', 'required')} "
                        "commitment still open"
                    )

        # If we have quick wins or a primary action, assemble.
        if quick_wins_titles or primary_action:
            # Primary action is required. If only quick wins exist,
            # provide a recovery-framed close.
            if not primary_action:
                late = _is_late_evening(user)
                if late:
                    primary_action = (
                        "shut it down for the night so tomorrow "
                        "starts clean"
                    )
                else:
                    primary_action = (
                        "stay on your recovery plan — nothing else "
                        "is actively behind"
                    )
            return _format_cos_decision_response(
                quick_wins=quick_wins_titles,
                primary_action=primary_action,
                context_reason=context_reason,
            )

    except Exception as e:
        logger.warning(
            "[FIX_FIRST] evaluation failed for user=%s: %s",
            getattr(user, 'id', '?'), e,
        )

    # ── Nothing to fix — you're on track ─────────────────────
    return _format_cos_decision_response(
        primary_action="Stay on your current plan",
        context_reason=(
            "You're on track — no overdue items, no critical health "
            "risks, and your foundational commitments are accounted for"
        ),
        lead_with_context=True,
    )


def _build_focus_query_response(user):
    """
    Phase 4 / Phase 8 / Phase 14 / Phase 19 — deterministic
    EXECUTION_NOW response.

    Phase 9: execution-first priority stack (overdue → upcoming →
    foundational-gap → signal-focus).
    Phase 10: intelligent item selection (tasks over toggles).
    Phase 12: dependency-aware filtering (blocked items excluded).
    Phase 14: output sanitization (no internal schedule data shown).

    Phase 19 (CoS decision-layer upgrade):
    * Quick wins (meds/supps overdue, ≤2 min) NO LONGER short-circuit
      the priority stack. They are collected into a narrative line
      (max 2) that precedes the primary action — never replaces it.
    * Late-evening context (user local hour >= 20 or < 5) flips the
      default primary to an intentional shutdown when nothing else
      is pressing.
    * Output uses `_format_cos_decision_response` — the old
      ``Do this next: … / Reason: … / Priority: …`` shape is gone.

    Phase 8 never-None guarantee still holds: even when no focus
    exists, no trust reports load, or the signal pipeline is empty,
    this returns a non-empty CoS-style response. Decision queries
    never fall through to the LLM.
    """
    # ══════════════════════════════════════════════════════════
    # Phase 9 — EXECUTION-FIRST selection (Phase 19 stacking).
    #
    # Priority stack for the PRIMARY action (strict order):
    #   1. OVERDUE items (time relevance > signal priority)
    #   2. UPCOMING items (0-90 minutes out)
    #   3. FOUNDATIONAL execution gaps
    #   4. SIGNAL-BASED focus (trust reports)
    #
    # Separately, up to 2 med/supp "quick wins" may be stacked
    # in front of the primary.
    # ══════════════════════════════════════════════════════════

    primary_action: Optional[str] = None
    context_reason: Optional[str] = None

    quick_wins_titles: List[str] = []
    quick_ids: set = set()

    try:
        from apps.core.ai_state.state_builder import MODULE_BUILDERS
        exec_builder = MODULE_BUILDERS.get('execution')
        if exec_builder:
            exec_state = exec_builder(user) or {}
            exec_items = exec_state.get('items', [])

            # ── Phase 19: collect quick-win candidates ───────────
            # Meds/supps overdue or in-progress. ≤2 min each, so
            # they ride alongside the primary action — never replace it.
            _QUICK_SOURCE_TYPES = frozenset({
                'medication_dose', 'supplement_dose',
            })
            quick_candidates = [
                i for i in exec_items
                if i.get('source_type') in _QUICK_SOURCE_TYPES
                and i.get('time_status') in ('overdue', 'in_progress')
                and not i.get('completed_today')
            ]
            if quick_candidates:
                _qa_imp = {
                    'foundational': 0, 'important': 1,
                    'standard': 1, 'flexible': 2,
                }
                quick_candidates.sort(key=lambda x: (
                    0 if x.get('source_type') == 'medication_dose' else 1,
                    _qa_imp.get(x.get('importance', 'flexible'), 2),
                    x.get('scheduled_time', '99:99'),
                ))
                # Cap at 2 per brief (quick wins must never dominate).
                for q in quick_candidates[:2]:
                    title = q.get('title') or ''
                    if title:
                        quick_wins_titles.append(f"your {title}")
                # Track (source_type, source_id) of ALL quick-action
                # candidates so none of them can become the primary.
                # The primary is reserved for a non-quick item (task,
                # routine, foundational gap, or intentional shutdown).
                # Execution items carry `source_id`, not `id`.
                quick_ids = {
                    (q.get('source_type'), q.get('source_id'))
                    for q in quick_candidates
                    if q.get('source_id') is not None
                }

            all_overdue = [
                i for i in exec_items
                if i.get('time_status') == 'overdue'
                and not i.get('completed_today')
                and (i.get('source_type'), i.get('source_id')) not in quick_ids
            ]
            upcoming = [
                i for i in exec_items
                if i.get('time_status') in ('upcoming', 'in_progress')
                and not i.get('completed_today')
                and (i.get('source_type'), i.get('source_id')) not in quick_ids
            ]

            # ── Phase 10: intelligent item selection ──────────────
            # Raw bucket sort is not enough. The system must behave
            # like a disciplined human operator, not a sorted-list
            # processor. Selection rules, in order:
            #
            # 1. Filter out non-actionable items (status-toggle
            #    routine items like "Wake up" / "Go to bed" that
            #    are implied-done when the user is interacting).
            # 2. Separate TASKS (explicit commitments) from
            #    ROUTINE_ITEMS (daily maintenance toggles). Tasks
            #    are anchor activities; routines are supporting.
            # 3. Within each group: foundational → important →
            #    flexible, then earliest scheduled_time as
            #    tiebreaker only.
            # 4. Tasks always selected before routine_items.

            # Status-toggle routine items that are never the right
            # answer for "what should I do right now?". These are
            # implied by the user being awake/interacting.
            _IMPLIED_DONE_TITLES = frozenset({
                'wake up', 'go to bed', 'go to sleep',
                'lights out', 'get up', 'get out of bed',
            })

            def _is_actionable(item):
                """Phase 10: an item is actionable if it's not
                a status-toggle that's implied-done."""
                if item.get('completed_today'):
                    return False
                title_lower = (item.get('title') or '').strip().lower()
                if title_lower in _IMPLIED_DONE_TITLES:
                    return False
                return True

            # ── Phase 12: dependency-aware blocked filter ────────
            # Within a routine group (execution_group_id), items
            # have an implied sequence defined by scheduled_time.
            # An item is BLOCKED if any earlier item in the same
            # group is still incomplete. Example: Shower (07:00)
            # is blocked if Workout (06:15) hasn't been done yet.
            #
            # Standalone tasks (execution_group_type='standalone')
            # are never blocked — they have no predecessor.

            # Phase 15: group types where sequence matters vs not.
            # Routine groups (Morning Routine, Nightly Routine) have
            # a strict implied sequence: Wake up → Prayer → Workout
            # → Shower. Later items are blocked by earlier incomplete
            # items.
            #
            # Medication/supplement windows are PARALLEL — you don't
            # need to take Perfect Amino before THORNE Creatine. All
            # items in the window are independently actionable.
            _SEQUENTIAL_GROUP_TYPES = frozenset({
                'routine',
            })

            def _filter_blocked(items, all_items):
                """Remove items that are blocked by an incomplete
                predecessor in their routine group.

                Returns only items that are either:
                - standalone (no group)
                - in a non-sequential group (medication/supplement
                  window — all items are independently actionable)
                - the FIRST incomplete item in a sequential group
                """
                if not items:
                    return items

                # Build a map: group_id → earliest incomplete
                # scheduled_time (the "gate"), but ONLY for groups
                # that have sequential dependencies (routines).
                _group_gates = {}
                for i in all_items:
                    gid = i.get('execution_group_id')
                    if gid is None:
                        continue
                    # Phase 15: only enforce sequence for routine groups
                    gtype = i.get('execution_group_type', '')
                    if gtype not in _SEQUENTIAL_GROUP_TYPES:
                        continue
                    if i.get('completed_today'):
                        continue
                    title_lower = (i.get('title') or '').strip().lower()
                    if title_lower in _IMPLIED_DONE_TITLES:
                        continue
                    sched = i.get('scheduled_time', '99:99')
                    if gid not in _group_gates or sched < _group_gates[gid]:
                        _group_gates[gid] = sched

                result = []
                for item in items:
                    gid = item.get('execution_group_id')
                    # Standalone items are never blocked
                    if gid is None:
                        result.append(item)
                        continue
                    # Non-sequential groups: always selectable
                    gtype = item.get('execution_group_type', '')
                    if gtype not in _SEQUENTIAL_GROUP_TYPES:
                        result.append(item)
                        continue
                    # Sequential routine items: only selectable if
                    # they ARE the earliest incomplete item (the gate)
                    gate_time = _group_gates.get(gid)
                    item_time = item.get('scheduled_time', '99:99')
                    if gate_time is None or item_time <= gate_time:
                        result.append(item)
                    # else: blocked
                return result

            _imp_order = {
                'foundational': 0, 'important': 1, 'standard': 1, 'flexible': 2,
            }

            def _rank_key(item):
                """Phase 10 + 18.2: sort key with governance tier as
                PRIMARY. Faith (tier 0) always outranks health (tier 1)
                which outranks work (tier 2), regardless of source_type.
                Within the same tier, earliest scheduled_time wins
                (most overdue first), then importance, then task vs
                routine as final tiebreaker."""
                from apps.ai.decision_governor import _infer_tier
                tier = _infer_tier(item)
                sched = item.get('scheduled_time', '99:99')
                imp = _imp_order.get(
                    item.get('importance', 'flexible'), 2,
                )
                is_task = 0 if item.get('source_type') == 'task' else 1
                return (tier, sched, imp, is_task)

            # Apply filter + dependency check + rank
            overdue = sorted(
                _filter_blocked(
                    [i for i in all_overdue if _is_actionable(i)],
                    exec_items,
                ),
                key=_rank_key,
            )

            # Priority 1: overdue items
            if overdue:
                top = overdue[0]
                primary_action = f"Start {top['title']}"
                n_overdue = len(overdue)
                sched = top.get('scheduled_time', '')
                sched_str = f" (scheduled at {sched})" if sched else ''
                if n_overdue > 1:
                    others = ', '.join(
                        i['title'] for i in overdue[1:4]
                    )
                    context_reason = (
                        f"{top['title']}{sched_str} is overdue "
                        f"and {n_overdue - 1} more item(s) are "
                        f"also behind: {others}"
                    )
                else:
                    context_reason = (
                        f"{top['title']}{sched_str} is overdue"
                    )

            # Priority 2: upcoming items (nothing overdue)
            elif upcoming:
                upcoming_filtered = sorted(
                    _filter_blocked(
                        [i for i in upcoming if _is_actionable(i)],
                        exec_items,
                    ),
                    key=_rank_key,
                )
                if upcoming_filtered:
                    top = upcoming_filtered[0]
                    sched = top.get('scheduled_time', '')
                    primary_action = f"Start {top['title']}"
                    context_reason = (
                        f"Nothing is overdue. {top['title']} is "
                        f"your next item (scheduled at {sched})"
                    )

            # Priority 3: foundational execution gaps (no overdue,
            # no upcoming, but some required items are not done)
            if not primary_action and exec_items:
                incomplete = sorted(
                    _filter_blocked(
                        [
                            i for i in exec_items
                            if _is_actionable(i)
                            and (i.get('source_type'), i.get('source_id')) not in quick_ids
                            and i.get('importance') in (
                                'foundational', 'important',
                            )
                        ],
                        exec_items,
                    ),
                    key=_rank_key,
                )
                if incomplete:
                    top = incomplete[0]
                    primary_action = f"Complete {top['title']}"
                    context_reason = (
                        f"No schedule pressure right now, but "
                        f"{top['title']} is a "
                        f"{top.get('importance', 'required')} item "
                        f"that hasn't been completed today"
                    )
    except Exception as e:
        logger.warning(
            "[FOCUS_QUERY] execution-first lookup failed for user=%s: "
            "%s — falling through to signal layer",
            getattr(user, 'id', '?'), e,
        )

    # ── Priority 4: signal-based focus (ONLY if no execution items) ──
    if not primary_action:
        focus = None
        try:
            from apps.core.ai_state.right_now import compute_right_now_focus
            from apps.core.ai_state.state_engine import get_module_state

            trust_reports = {}
            for module_name in (
                'health', 'fitness', 'nutrition', 'medicine',
                'fasting', 'journal', 'faith',
            ):
                try:
                    ms = get_module_state(user, module_name) or {}
                except Exception:
                    continue
                for k, v in (ms.get('_trust') or {}).items():
                    if v:
                        trust_reports[k] = v

            focus = compute_right_now_focus(trust_reports)
        except Exception as e:
            logger.warning(
                "[FOCUS_QUERY] right_now_focus failed for user=%s: %s",
                getattr(user, 'id', '?'), e,
            )

        action_hints = {
            'workouts': 'Log a workout or move a session into today',
            'medication': "Take any missed dose now if it's safe to do so",
            'medicine': "Take any missed dose now if it's safe to do so",
            'fasting': 'Log your current fast or start the next one',
            'nutrition': 'Log a meal or check your macro targets',
            'sleep': 'Plan an earlier wind-down tonight',
            'body_composition': 'Add a measurement',
            'journal': 'Write a short entry — even one sentence',
            'faith': "Open your reading plan and complete today's passage",
        }

        if focus and focus.get('status') == 'focused':
            domain = focus.get('domain', '') or ''
            primary_action = action_hints.get(domain)
            if not primary_action:
                clean = domain.replace('_', ' ').strip()
                primary_action = f"Address {clean}" if clean else None
            context_reason = focus.get('reason', '') or context_reason

    # ── Phase 19 never-None fallback: late-evening aware ──────────
    # If nothing pressing surfaced, the response shape depends on
    # the time of day AND whether quick wins exist.
    late = _is_late_evening(user)
    if not primary_action:
        if late:
            # Intentional shutdown replaces primary action.
            primary_action = (
                "shut it down for the night so tomorrow starts clean"
            )
            # Suppress any partial context — shutdown line stands alone.
            context_reason = None
        elif quick_wins_titles:
            # Daytime + only quick wins. Keep momentum forward.
            primary_action = "stay on your next scheduled block"
            if not context_reason:
                context_reason = "No other overdue items — use the momentum"
        else:
            # Daytime, truly nothing pressing.
            primary_action = (
                "Complete your highest-priority foundational habit — "
                "prayer, movement, or a quick journal entry"
            )
            if not context_reason:
                context_reason = (
                    "No overdue items, no upcoming schedule pressure, "
                    "and no high-priority focus surfaced"
                )
    elif late and primary_action and not quick_wins_titles:
        # Late evening but a real primary exists (e.g. unfinished
        # foundational). Nudge toward close-the-day framing — context
        # still explains why.
        pass  # Keep primary as-is; formatter handles late-evening tone.

    return _format_cos_decision_response(
        quick_wins=quick_wins_titles,
        primary_action=primary_action,
        context_reason=context_reason,
    )


def _try_focus_query_route(msg_lower, user):
    """Phase 4 — focus query hard override. Returns RouteResult or None."""
    if user is None or not _is_focus_query(msg_lower):
        return None
    try:
        response = _build_focus_query_response(user)
        if not response:
            return None
        return RouteResult(
            category=RouteCategory.DETERMINISTIC_DATA,
            response=response,
            route_name='focus_query',
            domain='execution',
            is_terminal=True,
        )
    except Exception as e:
        logger.warning(
            "[FOCUS_QUERY] route failed for user=%s: %s",
            getattr(user, 'id', '?'), e,
        )
        return None


def _try_decision_query_route(msg_lower, user):
    """Phase 8 / 11 — decision-query hard override with never-None
    guarantee and intent-aware routing.

    Phase 11 addition: classifies the decision intent and routes to
    the appropriate handler:
        EXECUTION_NOW → _build_focus_query_response (Phase 10)
        BIGGEST_RISK  → _build_biggest_risk_response (Phase 11)
        FIX_FIRST     → _build_fix_first_response (Phase 11)

    For any message that classifies as a decision query, this ALWAYS
    returns a valid RouteResult with an Action-First response. It
    never returns None and never falls through to the LLM.

    Returns RouteResult or None (only if not a decision query).
    """
    if user is None or not _is_decision_query(msg_lower):
        return None

    # Phase 11 / 11.1: classify the intent and pick the right handler.
    intent = _classify_decision_intent(msg_lower)
    logger.info(
        "DECISION_INTENT: %s | query=%r | user=%s",
        intent, msg_lower[:120],
        getattr(user, 'id', '?'),
    )

    # Phase 19: new-format fallback (no "Do this next:" / "Reason:"
    # / "Priority:" markers). Still decisive.
    _SAFE_FALLBACK = _format_cos_decision_response(
        primary_action=(
            "Complete your highest-priority foundational habit — "
            "prayer, movement, or a quick journal entry"
        ),
        context_reason=(
            "Decision-query fallback — no concrete focus surfaced"
        ),
    )

    try:
        # Phase 11.1 / Phase 19: HARD ENFORCE routing. Each handler
        # MUST produce a non-empty decisive response. If it comes
        # back empty, log and fall back to the safe default.
        if intent == 'BIGGEST_RISK':
            response = _build_biggest_risk_response(user)
            if not _looks_like_cos_decision_response(response):
                logger.warning(
                    "DECISION_INTENT_FALLBACK: BIGGEST_RISK handler "
                    "returned empty for user=%s",
                    getattr(user, 'id', '?'),
                )
                response = _SAFE_FALLBACK
        elif intent == 'FIX_FIRST':
            response = _build_fix_first_response(user)
            if not _looks_like_cos_decision_response(response):
                logger.warning(
                    "DECISION_INTENT_FALLBACK: FIX_FIRST handler "
                    "returned empty for user=%s — using safe fallback "
                    "(NOT execution handler)",
                    getattr(user, 'id', '?'),
                )
                response = _SAFE_FALLBACK
        else:  # EXECUTION_NOW
            response = _build_focus_query_response(user)
            if not _looks_like_cos_decision_response(response):
                response = _SAFE_FALLBACK

        # ── Phase 18.2: Decision Governance Gate ────────────────
        # Every recommendation passes through validate_decision()
        # before reaching the user. If it violates reality
        # constraints, priority hierarchy, or logical consistency,
        # it is rejected and recomputed.
        try:
            from apps.ai.decision_governor import (
                validate_decision,
                GovernanceViolation,
            )
            # Load execution items for governance checks
            _gov_items = None
            try:
                from apps.core.ai_state.state_builder import MODULE_BUILDERS
                _exec_builder = MODULE_BUILDERS.get('execution')
                if _exec_builder:
                    _gov_items = (_exec_builder(user) or {}).get('items', [])
            except Exception:
                pass

            try:
                response = validate_decision(
                    response, exec_items=_gov_items, user=user,
                )
            except GovernanceViolation as gv:
                logger.warning(
                    "GOVERNANCE_REJECTED: rule=%s intent=%s "
                    "reason=%s user=%s — recomputing",
                    gv.rule, intent, gv.reason,
                    getattr(user, 'id', '?'),
                )
                # Recompute: the governor identified a specific
                # violation. Use the safe fallback rather than
                # trusting the original handler's output.
                response = _SAFE_FALLBACK
        except ImportError:
            pass  # Governor not yet deployed
        except Exception as gov_err:
            logger.warning(
                "GOVERNANCE_ERROR: %s — passing through (fail-open "
                "on governance errors to avoid blocking chat)",
                gov_err,
            )

        logger.info(
            "DECISION_ROUTED: intent=%s route=decision_query_%s "
            "action=%r user=%s",
            intent, intent.lower(),
            (response or '')[:80],
            getattr(user, 'id', '?'),
        )

    except Exception as e:
        logger.warning(
            "[DECISION_QUERY] intent=%s handler raised for user=%s: "
            "%s — emitting safe fallback",
            intent, getattr(user, 'id', '?'), e,
        )
        response = _SAFE_FALLBACK

    return RouteResult(
        category=RouteCategory.DETERMINISTIC_DATA,
        response=response,
        route_name=f'decision_query_{intent.lower()}',
        domain='execution',
        is_terminal=True,
    )


# =============================================================================
# Phase 4.5 — Hard Response Enforcement
# =============================================================================
#
# Phase 4 added behavioral guidance via the system prompt. Phase 4.5 makes
# weak responses impossible by enforcing response construction in CODE.
#
# Every Phase 4.5 handler builds a response in the mandatory shape:
#
#     Situation:
#     <what is happening — facts from state>
#
#     Interpretation:
#     <what it means — includes confidence + sufficiency from _trust>
#
#     Action:
#     <what to do next — deterministic, not generic>
#
# When a high-priority right_now_focus is a DIFFERENT domain than the one
# the user is asking about, the handler prepends a one-line priority note
# so the user cannot discuss workouts while ignoring a missed medication.

_GENERIC_PHRASES = frozenset([
    'keep it up',
    'great job',
    'awesome job',
    'nice job',
    'good job',
    'consistent effort',
    'keep going',
    'you got this',
    "you're doing great",
    'you are doing great',
    'stay consistent',
    "that's amazing",
    'stay on track',
    'hang in there',
])

# Phase 7 — forbidden softening language. The Decision Contract says
# CoS must use direct language ("Do this next", "Your priority is").
# These softeners dilute every action into a suggestion the user can
# ignore, and they're explicitly prohibited by the task spec. Checked
# with whole-word / phrase boundaries to avoid false positives on
# substrings inside legitimate words (e.g. "maybe" inside "maybeline").
_WEASEL_PHRASES = frozenset([
    'you might want to',
    'you might consider',
    'you may want to',
    'you could consider',
    'it could help',
    'it might help',
    'consider doing',
    'consider taking',
    'consider trying',
    'perhaps you',
    'maybe you should',
    'maybe try',
])

# Phase 8 — passive-action phrases. Responses that tell the user to
# "keep logging" or "continue tracking" or "monitor this" are
# non-actionable on decision queries. They're accepted only when the
# user explicitly asked about logging/tracking/monitoring.
_PASSIVE_PHRASES = frozenset([
    'keep logging',
    'continue logging',
    'keep tracking',
    'continue tracking',
    'monitor this',
    'monitor your',
    'keep an eye on',
    'keep watching',
    'stay the course',
    'maintain your current',
    'keep doing what you',
])

# Phase 9 — future-tense action words. These are time-horizon
# violations when there are overdue / today items remaining.
# A response telling the user to "plan tonight" or "try tomorrow"
# when they have 5 overdue items right now is a wrong decision.
_FUTURE_ACTION_PHRASES = frozenset([
    'tonight',
    'tomorrow',
    'this evening',
    'later today',
    'this week',
    'next week',
    'going forward',
    'in the future',
    'over the coming days',
    'wind-down',
    'wind down',
])

# Phase 8 — forbidden response starters. If ANY of these appear as
# the first non-empty line, the response fails the Action-First
# contract for decision queries. Summary-first responses are
# explicitly banned for "what should I do" / "biggest risk" queries.
_FORBIDDEN_STARTERS = (
    'end of day',
    "here's what happened",
    'heres what happened',
    'here is what happened',
    'today you',
    'you completed',
    'summary',
    'your day so far',
    'let me summarize',
    'let me recap',
    'so far today',
)

# Phase 8 — required action-first prefixes. The first non-empty line
# of a decision-query response MUST start with one of these.
_ACTION_FIRST_PREFIXES = (
    'do this next:',
    'your priority is:',
)


def _get_all_trust_reports(user):
    """Read every domain's _trust sub-dict from SAE. Returns flat dict."""
    reports = {}
    try:
        from apps.core.ai_state.state_engine import get_module_state
        for module_name in (
            'health', 'fitness', 'nutrition', 'medicine',
            'fasting', 'journal', 'faith',
        ):
            try:
                ms = get_module_state(user, module_name) or {}
            except Exception:
                continue
            for k, v in (ms.get('_trust') or {}).items():
                if v:
                    reports[k] = v
    except Exception as e:
        logger.warning("trust read failed for user=%s: %s", getattr(user, 'id', '?'), e)
    return reports


def _get_domain_trust(user, domain_key):
    """Fetch a single domain's Trust Report or None."""
    return _get_all_trust_reports(user).get(domain_key)


def _get_high_priority_note(user, exclude_domain=None):
    """Phase 4.5 — strict right_now_focus dominance.

    If the user has a high-priority focus in a DIFFERENT domain than the
    one they are asking about, return a one-line note that every domain
    response prepends. This enforces the rule: "If right_now_focus.priority
    == 'high', ALL responses must acknowledge it even if user asks another
    domain."
    """
    try:
        from apps.core.ai_state.right_now import compute_right_now_focus
        reports = _get_all_trust_reports(user)
        focus = compute_right_now_focus(reports)
    except Exception:
        return None
    if not focus or focus.get('status') != 'focused':
        return None
    if focus.get('priority') != 'high':
        return None
    domain = focus.get('domain')
    if domain == exclude_domain:
        return None
    return (
        f"> **Priority note:** Your highest-priority focus right now is "
        f"**{domain.replace('_', ' ')}** — {focus.get('reason', '')}."
    )


def _format_decision_response(
    *,
    situation,
    interpretation,
    action,
    trust=None,
    priority_note=None,
):
    """Phase 4.5 canonical response shape.

    Mandatory structure:
        > **Priority note:** ... (optional, only when high-priority in
        > different domain)

        **Situation**
        <facts>

        **Interpretation**
        <meaning including confidence + sufficiency when trust is provided>

        **Action**
        <specific next step>
    """
    lines = []
    if priority_note:
        lines.append(priority_note)
        lines.append('')

    lines.append('**Situation**')
    lines.append(situation.strip() if situation else 'Not enough data to describe the situation.')
    lines.append('')

    # Interpretation gets a trust suffix automatically if provided.
    lines.append('**Interpretation**')
    interp = interpretation.strip() if interpretation else 'Insufficient data to interpret.'
    if trust:
        confidence = trust.get('confidence')
        sufficiency = trust.get('sufficiency')
        suffix_parts = []
        if confidence is not None:
            suffix_parts.append(f"{confidence}% confidence")
        if sufficiency:
            suffix_parts.append(f"sufficiency: {sufficiency}")
        if suffix_parts:
            interp = f"{interp} ({', '.join(suffix_parts)})"
    lines.append(interp)
    lines.append('')

    lines.append('**Action**')
    lines.append(action.strip() if action else 'Stay consistent — nothing urgent.')

    return '\n'.join(lines)


# ── Phase 4.5 domain matchers (new) ──────────────────────────────

def _match_body_composition_query(msg_lower):
    """Match body composition / fat / lean mass status questions."""
    if _is_future_tense_query(msg_lower):
        return False
    _BC_INTENT = frozenset([
        'body fat', 'my body fat', "what's my body fat",
        'whats my body fat', 'what is my body fat',
        'body composition', 'my body composition',
        'lean mass', 'my lean mass', 'fat mass', 'my fat mass',
        'how is my body fat', 'how is my body composition',
    ])
    if any(p in msg_lower for p in _BC_INTENT):
        _EXCLUDE = ['log', 'record', 'add', 'set', 'enter', 'update']
        if not any(e in msg_lower for e in _EXCLUDE):
            return True
    return False


def _handle_body_composition_query(user):
    """Phase 4.5 — deterministic body composition response."""
    try:
        from apps.core.ai_state.state_engine import get_module_state
        health = get_module_state(user, 'health') or {}
    except Exception as e:
        logger.warning("body_comp query: SAE read failed: %s", e)
        return None

    body_fat = health.get('body_fat_current')
    lean_mass = health.get('lean_mass_current')
    fat_mass = health.get('fat_mass_current')

    if body_fat is None and lean_mass is None and fat_mass is None:
        return None  # No data → fall through

    # ── Situation ──
    parts = []
    if body_fat is not None:
        parts.append(f"Body fat: **{body_fat:.1f}%**")
    if lean_mass is not None:
        parts.append(f"Lean mass: **{lean_mass:.1f} lb**")
    if fat_mass is not None:
        parts.append(f"Fat mass: **{fat_mass:.1f} lb**")
    last_entry = health.get('last_body_fat_entry')
    if last_entry:
        parts.append(f"Last measurement: {last_entry[:10]}")
    situation = '. '.join(parts) + '.'

    # ── Interpretation ──
    trust = _get_domain_trust(user, 'body_composition')
    phase = health.get('fat_loss_phase') or ''
    plateau = health.get('plateau_risk_label') or ''
    muscle_risk = health.get('muscle_loss_risk_level') or ''
    interp_bits = []
    if phase:
        interp_bits.append(f"Fat loss phase: {phase.lower().replace('_', ' ')}")
    if plateau:
        interp_bits.append(f"plateau risk: {plateau.lower()}")
    if muscle_risk:
        interp_bits.append(f"muscle-loss risk: {muscle_risk.lower()}")
    if not interp_bits:
        if trust and trust.get('sufficiency') == 'low':
            interp_bits.append("Limited data — trend not yet reliable")
        else:
            interp_bits.append("Trend holding steady")
    interpretation = '. '.join(interp_bits) + '.'

    # ── Action ──
    if trust and trust.get('priority_level') == 'high':
        action = trust.get('priority_reason', 'Address the risk flagged above.')
    elif trust and trust.get('sufficiency') == 'low':
        action = "Log another measurement this week to improve trust in the trend."
    elif phase == 'PLATEAU':
        action = "Consider adjusting intake or training load to break the plateau."
    else:
        action = "Keep logging regular measurements — weekly is ideal."

    return _format_decision_response(
        situation=situation,
        interpretation=interpretation,
        action=action,
        trust=trust,
        priority_note=_get_high_priority_note(user, exclude_domain='body_composition'),
    )


def _match_nutrition_query(msg_lower):
    """Match nutrition / macro / calorie status questions."""
    if _is_future_tense_query(msg_lower):
        return False
    _NUT_INTENT = frozenset([
        'how is my nutrition', "how's my nutrition", 'my nutrition',
        'my macros', 'macro status', 'how are my macros',
        'my calories', 'calorie count', 'how many calories',
        'nutrition status', 'nutrition summary', 'nutrition this week',
        'macros today', 'calories today', 'how much protein',
    ])
    if any(p in msg_lower for p in _NUT_INTENT):
        _EXCLUDE = ['log', 'record', 'add', 'set', 'enter', 'track ']
        if not any(e in msg_lower for e in _EXCLUDE):
            return True
    return False


def _handle_nutrition_query(user):
    """Phase 4.5 — deterministic nutrition response."""
    try:
        from apps.core.ai_state.state_engine import get_module_state
        nut = get_module_state(user, 'nutrition') or {}
    except Exception as e:
        logger.warning("nutrition query: SAE read failed: %s", e)
        return None

    cal = nut.get('daily_calories')
    protein = nut.get('daily_protein_g')
    cal_target = nut.get('calorie_target')
    macro_score = nut.get('macro_compliance_score')
    food_entries_7d = nut.get('food_entries_7d', 0)

    if cal is None and food_entries_7d == 0:
        return None  # No data → fall through

    # ── Situation ──
    parts = []
    if cal is not None:
        if cal_target:
            parts.append(f"Calories today: **{int(cal)} / {int(cal_target)}**")
        else:
            parts.append(f"Calories today: **{int(cal)}**")
    if protein is not None:
        protein_target = nut.get('protein_target')
        if protein_target:
            parts.append(f"protein: **{int(protein)}g / {int(protein_target)}g**")
        else:
            parts.append(f"protein: **{int(protein)}g**")
    if food_entries_7d:
        parts.append(f"{food_entries_7d} meals logged this week")
    situation = '. '.join(parts) + '.'

    # ── Interpretation ──
    trust = _get_domain_trust(user, 'nutrition')
    interp_bits = []
    if macro_score is not None:
        if macro_score >= 80:
            interp_bits.append(f"Macro compliance {int(macro_score)}/100 — on target")
        elif macro_score >= 50:
            interp_bits.append(f"Macro compliance {int(macro_score)}/100 — slipping")
        else:
            interp_bits.append(f"Macro compliance {int(macro_score)}/100 — well off target")
    elif cal_target and cal is not None:
        delta_pct = int((cal - cal_target) / cal_target * 100)
        if abs(delta_pct) <= 10:
            interp_bits.append("Within target range")
        elif delta_pct > 10:
            interp_bits.append(f"{delta_pct}% above target")
        else:
            interp_bits.append(f"{abs(delta_pct)}% below target")
    else:
        interp_bits.append("Tracking in progress")

    if trust and trust.get('sufficiency') == 'low':
        interp_bits.append("need more days logged for trustworthy guidance")
    interpretation = '. '.join(interp_bits) + '.'

    # ── Action ──
    if trust and trust.get('priority_level') == 'high':
        action = trust.get('priority_reason', 'Address the nutrition gap above.')
    elif macro_score is not None and macro_score < 50:
        action = "Review macro targets and log your next meal with intent."
    elif food_entries_7d < 3:
        action = "Log at least 3 meals this week for reliable tracking."
    else:
        action = "Stay consistent — log your next meal at its usual time."

    return _format_decision_response(
        situation=situation,
        interpretation=interpretation,
        action=action,
        trust=trust,
        priority_note=_get_high_priority_note(user, exclude_domain='nutrition'),
    )


def _match_fasting_query(msg_lower):
    """Match fasting status questions."""
    if _is_future_tense_query(msg_lower):
        return False
    _FAST_INTENT = frozenset([
        'am i fasting', 'my fast', 'my fasting', 'fasting status',
        'how long have i been fasting', 'fasting summary',
        'how is my fast going', "how's my fast going", 'fasting adherence',
        'my fasting compliance', 'how many fasts this week',
    ])
    if any(p in msg_lower for p in _FAST_INTENT):
        _EXCLUDE = ['log', 'record', 'start ', 'end ', 'break ']
        if not any(e in msg_lower for e in _EXCLUDE):
            return True
    return False


def _handle_fasting_query(user):
    """Phase 4.5 — deterministic fasting response."""
    try:
        from apps.core.ai_state.state_engine import get_module_state
        fst = get_module_state(user, 'fasting') or {}
    except Exception as e:
        logger.warning("fasting query: SAE read failed: %s", e)
        return None

    if fst.get('enabled') is False:
        # Domain gated off — return a deterministic disabled response
        return _format_decision_response(
            situation="You have fasting tracking turned off.",
            interpretation="No fasting trust signal is computed for users who do not fast.",
            action="Enable fasting in settings if you'd like me to track this domain.",
        )

    current_active = fst.get('current_fast_active', False)
    current_hours = fst.get('current_fast_hours')
    target_hours = fst.get('current_fast_target_hours')
    fasts_7d = fst.get('fasts_7d', 0)
    compliance = fst.get('fasting_compliance_score')
    last_end = fst.get('last_fast_end')

    if fasts_7d == 0 and not current_active and not last_end:
        return None  # No data → fall through

    # ── Situation ──
    parts = []
    if current_active and current_hours is not None:
        if target_hours:
            parts.append(
                f"Currently fasting: **{current_hours}h elapsed / {int(target_hours)}h target**"
            )
        else:
            parts.append(f"Currently fasting: **{current_hours}h elapsed**")
    if fasts_7d:
        parts.append(f"{fasts_7d} completed fasts this week")
    if last_end:
        parts.append(f"Last fast ended: {last_end[:10]}")
    situation = '. '.join(parts) + '.' if parts else 'No recent fasting activity.'

    # ── Interpretation ──
    trust = _get_domain_trust(user, 'fasting')
    if compliance is not None:
        if compliance >= 80:
            interp = f"7-day compliance {int(compliance)}% — on protocol"
        elif compliance >= 50:
            interp = f"7-day compliance {int(compliance)}% — slipping"
        else:
            interp = f"7-day compliance {int(compliance)}% — well off protocol"
    else:
        interp = "No compliance score yet — insufficient data in the last 7 days"
    interpretation = interp + '.'

    # ── Action ──
    if trust and trust.get('priority_level') == 'high':
        action = trust.get('priority_reason', 'Log your next fast.')
    elif current_active:
        action = "Stay the course — end your current fast at its target."
    elif fasts_7d == 0:
        action = "Start a fast today to re-establish the rhythm."
    else:
        action = "Continue your protocol — log each fast as you complete it."

    return _format_decision_response(
        situation=situation,
        interpretation=interpretation,
        action=action,
        trust=trust,
        priority_note=_get_high_priority_note(user, exclude_domain='fasting'),
    )


# ── Phase 4.5 validator ───────────────────────────────────────────

def _first_non_empty_line(text):
    """Return the first stripped non-empty line, or empty string."""
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped:
            return stripped
    return ''


def _count_action_first_lines(text):
    """Count lines that start with one of the Action-First prefixes.

    Used by the single-action validator rule. A compliant
    decision-query response has EXACTLY ONE such line.
    """
    count = 0
    for raw in text.splitlines():
        stripped_lower = raw.strip().lower()
        for prefix in _ACTION_FIRST_PREFIXES:
            if stripped_lower.startswith(prefix):
                count += 1
                break
    return count


def validate_response(
    response_text, user=None, query_domain=None, is_decision_query=False,
):
    """Phase 4.5 hard response validator (extended in Phase 7 and Phase 8).

    Rejects LLM responses that:
        - Phase 8 Rule 0: when is_decision_query=True, first
          non-empty line must start with "Do this next:" or
          "Your priority is:", and there must be exactly ONE such
          line (no multi-action menus, no buried actions)
        - Phase 8 Rule 0-b: when is_decision_query=True, first
          non-empty line must NOT start with any summary-first
          forbidden starter ("End of day", "Today you", etc.)
        - Phase 8 Rule 1c: passive-action phrases ("keep logging",
          "continue tracking", "monitor this", etc.) are rejected
          on decision queries AND on responses where the user did
          not explicitly ask to log/track/monitor
        - Phase 4.5 Rule 1: generic coaching phrases
        - Phase 7 Rule 1b: forbidden softening / weasel language
        - Phase 4.5 Rule 2: too short to contain interp + action
        - Phase 4.5 Rule 3: domain response without trust markers
        - Phase 4.5 Rule 4: missing interpretive language

    Returns ``(is_valid, reason)``. The caller regenerates via a
    deterministic builder when invalid.
    """
    if not response_text or not isinstance(response_text, str):
        return (False, 'empty or non-string response')

    text = response_text.strip()
    lower = text.lower()

    # ─────────────────────────────────────────────────────────
    # Phase 8 Rule 0 — ACTION-FIRST STRUCTURAL ENFORCEMENT
    # Runs BEFORE every other rule. For decision queries, the
    # response structure is non-negotiable.
    # ─────────────────────────────────────────────────────────
    if is_decision_query:
        first_line = _first_non_empty_line(text)
        first_lower = first_line.lower()

        # Rule 0-b: forbidden summary-first starters.
        for starter in _FORBIDDEN_STARTERS:
            if first_lower.startswith(starter):
                return (
                    False,
                    f'decision query rejected: summary-first starter '
                    f'{starter!r}',
                )

        # Rule 0: first non-empty line must start with an
        # Action-First prefix.
        if not any(
            first_lower.startswith(prefix)
            for prefix in _ACTION_FIRST_PREFIXES
        ):
            return (
                False,
                "decision query rejected: first line does not start "
                "with 'Do this next:' or 'Your priority is:'",
            )

        # Rule 0-c: exactly ONE Action-First line. Multiple means
        # the LLM produced a menu; buried action means summary-first.
        action_count = _count_action_first_lines(text)
        if action_count == 0:
            return (
                False,
                'decision query rejected: no Action-First line found',
            )
        if action_count > 1:
            return (
                False,
                f'decision query rejected: {action_count} action '
                f'lines (expected exactly 1)',
            )

        # Rule 0-d (Phase 9): time-horizon validation. If the
        # response's action line mentions future-tense words
        # ("tonight", "tomorrow", "wind-down"), reject — the
        # deterministic handler should already have picked an
        # execution-first item. This catches LLM responses that
        # slipped through the router and chose a trend signal
        # over an overdue task.
        first_action_lower = first_lower  # first non-empty line
        for future_word in _FUTURE_ACTION_PHRASES:
            if future_word in first_action_lower:
                return (
                    False,
                    f'decision query rejected: time-horizon '
                    f'violation — first action references '
                    f'{future_word!r} (must be a NOW action)',
                )

    # Rule 1: generic coaching phrases are automatic rejections.
    for phrase in _GENERIC_PHRASES:
        if phrase in lower:
            return (False, f'generic phrase: {phrase!r}')

    # Rule 1b (Phase 7): forbidden softening language. The CoS must
    # produce decisive actions — not suggestions the user can ignore.
    for phrase in _WEASEL_PHRASES:
        if phrase in lower:
            return (False, f'weasel phrase: {phrase!r}')

    # Rule 1c (Phase 8): passive-action phrases. Responses that tell
    # the user to "keep logging" / "continue tracking" / "monitor this"
    # are non-actionable filler. Always rejected — the task spec
    # allows a carve-out when the user explicitly asked to log/track,
    # but without access to the original query string at this layer
    # we take the stricter path. Deterministic handlers that emit
    # legitimate tracking guidance use different phrasing.
    for phrase in _PASSIVE_PHRASES:
        if phrase in lower:
            return (False, f'passive phrase: {phrase!r}')

    # Rule 2: too short to contain interpretation + action.
    # A compliant Phase 4.5 response is at least ~80 chars.
    if len(text) < 60:
        return (False, f'response too short ({len(text)} chars)')

    # Rule 3: if a domain is identified, the response MUST include at
    # least one trust-indicating phrase (percentage, confidence, trend
    # words, or explicit interpretation markers).
    if query_domain:
        trust_markers = (
            '%', 'confidence', 'sufficiency', 'priority',
            'ahead of', 'behind', 'on track', 'trend',
            'limited data', 'early signal', 'slipping',
            'on target', 'off target', 'off protocol', 'on protocol',
            'plateau', 'above target', 'below target',
        )
        if not any(marker in lower for marker in trust_markers):
            return (False, f'{query_domain} response lacks trust/interpretation markers')

    # Rule 4: the response must contain at least one interpretive verb
    # or judgment word. Pure raw-data lists without interpretation fail.
    interpretive_markers = (
        'you', 'mean', 'indicat', 'suggest', 'shows', 'is ',
        'below', 'above', 'within', 'ahead', 'behind',
        'track', 'plan', 'focus', 'priority',
        'interpretation', 'situation', 'action', 'next step',
    )
    if not any(marker in lower for marker in interpretive_markers):
        return (False, 'response lacks interpretive language')

    return (True, 'ok')


def regenerate_response_deterministic(user, query_domain):
    """Rebuild a response using the Phase 4.5 deterministic handler.

    Called when validate_response rejects an LLM output. Dispatches to
    the correct handler based on the detected domain. Returns None if
    no handler applies (caller should keep the original response in
    that case rather than blanking the user's chat).
    """
    handlers = {
        'workouts': _handle_workout_query,
        'workout': _handle_workout_query,
        'fitness': _handle_workout_query,
        'medication': _handle_medication_query,
        'meds': _handle_medication_query,
        'body_composition': _handle_body_composition_query,
        'nutrition': _handle_nutrition_query,
        'macros': _handle_nutrition_query,
        'fasting': _handle_fasting_query,
    }
    handler = handlers.get(query_domain)
    if handler is None:
        return None
    try:
        return handler(user)
    except Exception as e:
        logger.warning(
            "[VALIDATOR] regenerate failed for domain=%s user=%s: %s",
            query_domain, getattr(user, 'id', '?'), e,
        )
        return None


def _build_next_action_response(user):
    """Build deterministic next-action response.

    Phase 4 (decision enforcement): if a Phase 3 right_now_focus exists with
    a HIGH priority, it OVERRIDES the routine fallback. Trust beats schedule.
    The user gets steered to the most important domain regardless of which
    routine item happens to be next on the clock.

    Otherwise (no high-priority focus, or trust unavailable), falls through
    to the Today Engine priority order:
        1. Overdue now → earliest by time
        2. Coming up next → earliest by time
        3. Later today → earliest by time
        4. Incomplete foundational (not in time buckets) → earliest by time
        5. Empty → "You're clear right now."

    Returns EXACTLY ONE item. No plans, no lists, no sequencing.
    """
    # ── Phase 4: trust override ──────────────────────────────────
    # A high-priority right_now_focus pre-empts the routine fallback.
    # Medium / low priority do NOT override — those defer to schedule.
    try:
        from apps.core.ai_state.right_now import compute_right_now_focus
        from apps.core.ai_state.state_engine import get_module_state

        trust_reports = {}
        for module_name in (
            'health', 'fitness', 'nutrition', 'medicine',
            'fasting', 'journal', 'faith',
        ):
            try:
                ms = get_module_state(user, module_name) or {}
            except Exception:
                continue
            for k, v in (ms.get('_trust') or {}).items():
                if v:
                    trust_reports[k] = v

        focus = compute_right_now_focus(trust_reports)
        if (
            focus
            and focus.get('status') == 'focused'
            and focus.get('priority') == 'high'
        ):
            domain = focus.get('domain', 'unknown').replace('_', ' ').title()
            reason = focus.get('reason', '')
            logger.info(
                "[NEXT ACTION] user=%s TRUST_OVERRIDE focus=%s priority=high",
                user.id, focus.get('domain'),
            )
            return f"Focus on **{domain}** — {reason}."
    except Exception as e:
        logger.warning(
            "[NEXT ACTION] trust override check failed for user=%s: %s",
            getattr(user, 'id', '?'), e,
        )
        # Fall through to routine fallback below

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

# Generic future-tense detector. Used as a one-line gate at the top of each
# per-domain "current state / historical summary" matcher to prevent the
# deterministic router from hijacking forward-looking questions like
# "what is my workout tomorrow?". Future-tense messages fall through to the
# intent classifier, which routes them to query_event_history → the
# date-aware adapter → deterministic empty-state contract. This is the
# generalization of the bug fix: every summary matcher gets the same
# protection from a single helper, with no domain-specific string lists.
_FUTURE_TOKENS = frozenset([
    'tomorrow', 'next ', 'upcoming', 'scheduled', 'planned', 'plan for',
    "what's my next", 'what is my next', 'going to',
])
_FUTURE_VERB_HINTS = (' will ', " i'll ", ' am i going ', ' do i have ')


def _is_future_tense_query(msg_lower: str) -> bool:
    """Return True if the message is forward-looking. Generic, not domain-tied."""
    if any(tok in msg_lower for tok in _FUTURE_TOKENS):
        return True
    padded = f' {msg_lower} '
    if any(hint in padded for hint in _FUTURE_VERB_HINTS):
        return True
    return False


def _match_weight_query(msg_lower):
    """Match direct weight status questions."""
    if _is_future_tense_query(msg_lower):
        return False
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
    if _is_future_tense_query(msg_lower):
        return False
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
    """Phase 4.5 — deterministic workout response with trust enforcement."""
    try:
        from apps.core.ai_state.state_engine import get_module_state
        fitness = get_module_state(user, 'fitness') or {}
    except Exception as e:
        logger.warning("workout query: SAE read failed: %s", e)
        return None

    workouts_7d = fitness.get('workouts_7d', 0) or 0
    expected_7d = fitness.get('workout_expected_7d') or 0
    completed_7d = fitness.get('workout_completed_7d') or workouts_7d
    missed_7d = fitness.get('workout_missed_7d') or 0
    adherence = fitness.get('workout_adherence_score')
    minutes = fitness.get('workout_minutes_7d')
    last_workout = fitness.get('last_workout_date')

    if workouts_7d == 0 and expected_7d == 0 and not last_workout:
        return None  # No fitness data at all → fall through

    # ── Situation ──
    parts = []
    session_word = 'session' if workouts_7d == 1 else 'sessions'
    if expected_7d:
        parts.append(f"**{completed_7d} of {expected_7d} planned {session_word} completed** this week")
    else:
        parts.append(f"**{workouts_7d} {session_word}** logged this week")
    if minutes:
        hours = minutes / 60
        if hours >= 1:
            parts.append(f"{hours:.1f} hours of training")
        else:
            parts.append(f"{int(minutes)} minutes of training")
    if missed_7d:
        parts.append(f"{missed_7d} missed")
    situation = ', '.join(parts) + '.'

    # ── Interpretation ──
    trust = _get_domain_trust(user, 'workouts')
    interp_bits = []
    if adherence is not None:
        if adherence >= 100:
            interp_bits.append(f"Ahead of plan ({int(adherence)}% adherence)")
        elif adherence >= 80:
            interp_bits.append(f"On plan ({int(adherence)}% adherence)")
        elif adherence >= 50:
            interp_bits.append(f"Slipping ({int(adherence)}% adherence)")
        else:
            interp_bits.append(f"Well behind plan ({int(adherence)}% adherence)")
    elif workouts_7d >= 5:
        interp_bits.append(f"Strong week — {workouts_7d} sessions")
    elif workouts_7d >= 3:
        interp_bits.append(f"On track — {workouts_7d} sessions")
    else:
        interp_bits.append(f"Limited activity this week — {workouts_7d} sessions")

    strength_trend = fitness.get('strength_trend_score')
    if strength_trend is not None:
        if strength_trend >= 110:
            interp_bits.append("strength trending up")
        elif strength_trend <= 90:
            interp_bits.append("strength trending down")

    interpretation = ', '.join(interp_bits) + '.'

    # ── Action ──
    if trust and trust.get('priority_level') == 'high':
        action = trust.get('priority_reason', 'Log a workout or move a session into today.')
    elif adherence is not None and adherence >= 100:
        action = "Shift focus to recovery — you've exceeded plan."
    elif adherence is not None and adherence < 60:
        action = "Schedule your next session and protect the time block."
    elif workouts_7d == 0:
        action = "Log a short session today to restart the rhythm."
    else:
        action = "Keep the cadence — your next session is on track."

    return _format_decision_response(
        situation=situation,
        interpretation=interpretation,
        action=action,
        trust=trust,
        priority_note=_get_high_priority_note(user, exclude_domain='workouts'),
    )


def _match_sleep_query(msg_lower):
    """Match direct sleep status questions."""
    if _is_future_tense_query(msg_lower):
        return False
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
    if _is_future_tense_query(msg_lower):
        return False
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
    if _is_future_tense_query(msg_lower):
        return False
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
    """Phase 4.5 — deterministic medication response with trust enforcement.

    CoS purity: reads from SAE medicine state; never live-computes.
    """
    try:
        from apps.core.ai_state.state_engine import get_module_state
        med_state = get_module_state(user, 'medicine') or {}
    except Exception as e:
        logger.warning("Medication SAE state read failed: %s", e, exc_info=True)
        return None

    active_count = med_state.get('active_count', 0)
    if active_count == 0:
        return _format_decision_response(
            situation="No active medication schedules found.",
            interpretation="There is nothing to track — you have no scheduled doses.",
            action="Add a medication schedule in settings if you want me to track it.",
        )

    adherence_7d = med_state.get('adherence_7d')
    today_taken = med_state.get('today_taken', 0) or 0
    today_missed = med_state.get('today_missed', 0) or 0
    today_pending = med_state.get('today_pending', 0) or 0
    expected_today = med_state.get('expected_today', 0) or 0
    missed_7d = med_state.get('missed_7d') or 0
    completed_7d = med_state.get('completed_7d') or 0
    expected_7d = med_state.get('expected_7d') or 0

    # ── Situation ──
    parts = []
    if expected_today > 0:
        parts.append(
            f"Today: **{today_taken}/{expected_today} taken**, "
            f"{today_missed} missed, {today_pending} pending"
        )
    if expected_7d > 0:
        parts.append(
            f"this week: {completed_7d}/{expected_7d} taken, {missed_7d} missed"
        )
    if not parts:
        parts.append(f"{active_count} active medication schedules")
    situation = '; '.join(parts) + '.'

    # ── Interpretation ──
    trust = _get_domain_trust(user, 'medication')
    interp_bits = []
    if adherence_7d is not None:
        rate_pct = int(adherence_7d * 100)
        if rate_pct >= 95:
            interp_bits.append(f"Excellent adherence ({rate_pct}%)")
        elif rate_pct >= 85:
            interp_bits.append(f"Good adherence ({rate_pct}%)")
        elif rate_pct >= 70:
            interp_bits.append(f"Slipping — {rate_pct}% adherence")
        else:
            interp_bits.append(f"Poor adherence ({rate_pct}%) — doses are being missed")
    elif today_missed > 0:
        interp_bits.append(f"{today_missed} doses missed today")
    else:
        interp_bits.append("On schedule")
    interpretation = '. '.join(interp_bits) + '.'

    # ── Action ──
    if trust and trust.get('priority_level') == 'high':
        action = trust.get('priority_reason', 'Take missed doses now if safe to do so.')
    elif today_missed > 0 and today_pending > 0:
        action = "Take pending doses now; log missed doses if already skipped."
    elif today_missed > 0:
        action = "Review what caused today's misses to prevent repeats."
    elif today_pending > 0:
        action = f"Take your next pending dose — {today_pending} remaining today."
    else:
        action = "Continue your schedule — nothing urgent right now."

    return _format_decision_response(
        situation=situation,
        interpretation=interpretation,
        action=action,
        trust=trust,
        priority_note=_get_high_priority_note(user, exclude_domain='medication'),
    )


def _match_steps_query(msg_lower):
    """Match direct steps status questions."""
    if _is_future_tense_query(msg_lower):
        return False
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
    if _is_future_tense_query(msg_lower):
        return False
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
    if _is_future_tense_query(msg_lower):
        return False
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
    # Phase 4.5 — hard domain override routes
    register_data_route('body_composition_query', _match_body_composition_query, _handle_body_composition_query, 'health')
    register_data_route('nutrition_query', _match_nutrition_query, _handle_nutrition_query, 'health')
    register_data_route('fasting_query', _match_fasting_query, _handle_fasting_query, 'health')


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
