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


# Imperative-exclusion prefixes that ALSO read as standalone commands
# ("skip shower", "ignore prayer"). For these, a qualified-status match
# is only valid when a status closer is ALSO present — otherwise the
# message is a bare command that must reach intent recognition (e.g.
# skip_routine). The prepositional prefixes ("other than", "besides")
# are NOT in this set because they never stand alone as commands.
_IMPERATIVE_COMMAND_PREFIXES = frozenset({
    'skip ', 'skipping ',
    'forget ', 'forget about ', 'forgetting ',
    'ignore ', 'ignoring ',
    'leave out ', 'leaving out ',
    'take away ', 'taking away ',
})

# Unpunctuated status-question fragments. These confirm the message is a
# QUESTION about state, not a command. Kept to distinctive multi-word
# fragments so they can never collide with a real skip target.
_STATUS_CLOSER_PHRASES = (
    'anything left', 'anything else', 'anything remaining',
    "what's left", 'whats left', 'what is left', 'what remains',
    "what's remaining", 'whats remaining', 'left to do', 'still left',
)


def _has_status_closer(msg_lower: str) -> bool:
    """True when the message carries a status-question component.

    Distinguishes an exclusion-FILTER status question
    ("skip workout, am I done?") from a bare imperative command
    ("skip shower"). A closer is a "?", a yes/no status question, or a
    distinctive remaining-fragment.
    """
    if '?' in msg_lower:
        return True
    if any(q in msg_lower for q in QUALIFIED_STATUS_QUESTIONS):
        return True
    return any(ph in msg_lower for ph in _STATUS_CLOSER_PHRASES)


# "How many do I have left?" style COUNT questions. Routed deterministically
# so the count is grounded in canonical state (count == listed items) instead
# of an LLM guess — the check-in-vs-followup divergence (trust bug 2026-06-15:
# check-in implied 11 ahead, LLM said "5 tasks left"). Domain-specific counts
# (calories/steps/workouts/…) are excluded — they have their own routes.
_REMAINING_COUNT_CUES = (
    'left', 'remaining', 'to do', 'to go', 'still have', 'have left',
    'still got', 'outstanding',
)
_REMAINING_COUNT_DOMAIN_EXCL = (
    'calorie', 'protein', 'carb', 'fat ', 'fiber', 'sugar', 'step',
    'workout', 'glucose', 'blood sugar', 'dose', 'medication', 'medicine',
    'water', 'fast', 'mile', 'rep', 'set ', 'prayer request',
)


def _is_remaining_count_query(msg_lower: str) -> bool:
    """True for 'how many things/tasks/items do I have left' style questions."""
    if 'how many' not in msg_lower and 'how much' not in msg_lower:
        return False
    if any(d in msg_lower for d in _REMAINING_COUNT_DOMAIN_EXCL):
        return False
    return any(c in msg_lower for c in _REMAINING_COUNT_CUES)


def is_qualified_status_query(msg_lower: str) -> bool:
    """Detect if a message is a filtered/follow-up status question.

    Returns True for: "other than nutrition, anything left?",
    "am I done?", "besides meds, what's remaining?", and grounded
    remaining-count questions ("how many things do I have left?").

    Bare imperative commands that merely START with an exclusion verb
    ("skip shower", "ignore prayer") are NOT status queries — they must
    reach intent recognition (e.g. skip_routine). Such prefixes only
    qualify when a status closer is also present. See trust investigation
    2026-05-31 (skip-routine interception).
    """
    for p in QUALIFIED_STATUS_PREFIXES:
        matched = (
            msg_lower.startswith(p)
            or (', ' + p) in msg_lower
            or (' ' + p) in msg_lower
        )
        if not matched:
            continue
        if p in _IMPERATIVE_COMMAND_PREFIXES and not _has_status_closer(msg_lower):
            continue
        return True
    if any(p in msg_lower for p in QUALIFIED_STATUS_QUESTIONS):
        return True
    return _is_remaining_count_query(msg_lower)


# "List everything still remaining today" — an EXHAUSTIVE enumeration request,
# distinct from the count/qualified routes. Must list every item (no "+N more").
_ENUMERATE_VERBS = ('list ', 'show ', 'show me ', 'enumerate', 'give me a list',
                    'what are all', 'tell me everything')
_ENUMERATE_REMAINING_CUES = ('remaining', 'left', 'still', 'everything',
                             'to do', 'to-do', 'outstanding', 'all my')


def _is_enumerate_remaining_query(msg_lower: str) -> bool:
    """True for 'list everything still remaining today' style requests."""
    if not msg_lower:
        return False
    # Domain-specific list requests have their own handling — don't hijack.
    if any(d in msg_lower for d in (
        'calorie', 'protein', 'macro', 'step', 'workout', 'glucose',
        'medication', 'medicine', 'dose', 'prayer request', 'goal',
    )):
        return False
    has_verb = any(v in msg_lower for v in _ENUMERATE_VERBS)
    has_cue = any(c in msg_lower for c in _ENUMERATE_REMAINING_CUES)
    return has_verb and has_cue


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


def _canonical_remaining_items(user):
    """THE canonical list of incomplete items remaining today, from Today
    Engine (overdue + coming_up + later + foundation), deduped, order-preserved.

    Single source for BOTH the remaining-count answer and the enumerate-all
    answer so the count and the list can never diverge (trust contract:
    count == len(list)). Returns a list of item names, or None on failure.
    """
    try:
        from apps.core.today.today_engine import get_today_context
    except ImportError:
        return None
    try:
        ctx = get_today_context(user)
    except Exception:
        logger.warning(
            "[REMAINING ITEMS] Today Engine failed for user=%s",
            getattr(user, 'id', '?'), exc_info=True,
        )
        return None

    remaining = []
    for bucket in ('overdue', 'coming_up', 'later', 'foundation'):
        for entry in ctx.get(bucket, []):
            item = entry.get('item', entry)
            name = item.get('name', entry.get('label', ''))
            if name and not item.get('completed', False):
                remaining.append(name)

    seen = set()
    unique = []
    for name in remaining:
        if name.lower() not in seen:
            seen.add(name.lower())
            unique.append(name)
    return unique


def _build_enumerate_remaining_response(user):
    """Deterministic EXHAUSTIVE enumeration of everything remaining today.

    "List everything still remaining today." must list ALL items — no
    summarization, no "+N more", no generic check-in copy (trust bug
    2026-06-15). Shares `_canonical_remaining_items` with the count route so
    the count and the list reconcile exactly. Returns a string or None.
    """
    items = _canonical_remaining_items(user)
    if items is None:
        return None
    if not items:
        return "You're all clear — nothing remaining today."
    n = len(items)
    header = f"You have {n} item{'s' if n != 1 else ''} remaining today:"
    return header + "\n" + "\n".join(f"• {name}" for name in items)


# ── Explicit user deferral ("I won't do X today") — temporary, today-only ──
# Detect a declarative decision to defer an activity for today. Tight by
# design: requires a defer cue AND a today/tonight/tomorrow scope, excludes
# questions, and only ACTS on an unambiguous match against today's real
# incomplete items — so "I hate studying" (no defer cue) and ambiguous
# references never trigger a mutation.
_DEFER_CUES = (
    "won't", "wont", "will not", "not going to", "not gonna", "won't be",
    "wont be", "not doing", "can't do", "cant do", "cannot do", "not able to",
    "skip", "skipping", "not happening", "no time for", "too late",
    "getting late", "not today", "not tonight", "maybe tomorrow",
    "do it tomorrow", "do that tomorrow", "tomorrow instead",
    "leave it for tomorrow", "leave that for tomorrow", "push it to tomorrow",
    "save it for tomorrow", "save that for tomorrow", "put off",
)
_DEFER_SCOPE = ("today", "tonight", "tomorrow", "late", "this morning",
                "this afternoon", "this evening")


def _is_defer_today_intent(msg_lower):
    """True for an explicit statement deferring an activity for today."""
    if not msg_lower or "?" in msg_lower:
        return False  # a question is not a deferral command
    if not any(c in msg_lower for c in _DEFER_CUES):
        return False
    return any(s in msg_lower for s in _DEFER_SCOPE)


def _resolve_defer_target(user, msg_lower):
    """Find the SINGLE today-incomplete item the user is deferring, grounded in
    canonical state. Returns the today_engine item dict or None (0 / ambiguous)."""
    try:
        from apps.core.today.today_engine import get_today_context
        ctx = get_today_context(user)
    except Exception:
        return None
    # Scan all_items (not just time buckets) so an unscheduled task — which
    # never enters overdue/coming_up/later/foundation — is still deferrable.
    candidates = {}
    for item in ctx.get('all_items', []):
        if not isinstance(item, dict) or item.get('completed'):
            continue
        name = (item.get('name') or '').strip()
        if name:
            candidates.setdefault(name.lower(), item)
    matches = []
    for key, item in candidates.items():
        if key in msg_lower:
            matches.append(item)
            continue
        tokens = [t for t in re.split(r'[^a-z0-9]+', key) if len(t) >= 4]
        if any(t in msg_lower for t in tokens):
            matches.append(item)
    return matches[0] if len(matches) == 1 else None


def _invalidate_cos(user):
    try:
        from apps.ai.readiness_cache import invalidate_cos_context_on_action
        invalidate_cos_context_on_action(user)
    except Exception:
        logger.debug("defer: CoS cache invalidation skipped", exc_info=True)


def _handle_defer_today(user, msg_lower):
    """Apply a today-only deferral and return a truthful acknowledgement.

    Task → reschedule due_date to tomorrow (returns naturally tomorrow, stays
    'pending' — NOT completed/skipped-forever). Routine → skip today's log (it
    recurs tomorrow). Returns None when no unambiguous target (caller falls
    through to the normal pipeline). Never inflates adherence.
    """
    item = _resolve_defer_target(user, msg_lower)
    if not item:
        return None
    name = (item.get('name') or '').strip()
    source = item.get('source')
    item_id = item.get('id') or ''
    try:
        from datetime import timedelta
        from apps.core.utils import get_user_today
        today = get_user_today(user)
        tomorrow = today + timedelta(days=1)

        if source == 'task' and item_id.startswith('task:'):
            from apps.life.models import Task
            task = Task.objects.filter(
                user=user, pk=item_id.split(':', 1)[1]).first()
            if not task:
                return None
            task.due_date = tomorrow
            task.save(update_fields=['due_date', 'updated_at'])
            _invalidate_cos(user)
            logger.info("[DEFER] user=%s task='%s' → tomorrow", user.id, name)
            return (
                f"Got it — I've moved **{name}** to tomorrow. It's off today's "
                f"list, so I won't nudge you on it tonight. We'll pick it back "
                f"up tomorrow. (Deferred, not done.)"
            )

        if source == 'routine' and item_id.startswith('routine:'):
            from apps.life.models import RoutineSchedule
            from apps.life.services.routine_helpers import skip_routine
            sched = RoutineSchedule.objects.filter(
                id=item_id.split(':', 1)[1], routine__user=user).first()
            if not sched:
                return None
            skip_routine(user, sched, today)
            _invalidate_cos(user)
            logger.info("[DEFER] user=%s routine='%s' skipped today", user.id, name)
            return (
                f"Got it — **{name}** is off for today. It'll come back around "
                f"tomorrow. (Deferred for tonight, not skipped for good.)"
            )
    except Exception:
        logger.warning(
            "[DEFER] failed for user=%s item='%s'",
            getattr(user, 'id', '?'), name, exc_info=True)
        return None
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
    remaining = _canonical_remaining_items(user)
    if remaining is None:
        return None

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
            # Factual faith-status recognition ("do you see I've been reading?")
            # must be answered from canonical execution truth, NOT handed to the
            # reflective/LLM turn — recognition must never depend on the LLM, and
            # Beth must never contradict completion history (trust contract
            # 2026-06-16). The governor stays the authority; it just routes a
            # factual recognition to the deterministic grounded answer.
            if _is_faith_status_query(msg_lower) and user is not None:
                _faith_resp = _handle_faith_status_query(user, msg_lower)
                if _faith_resp:
                    result = RouteResult(
                        category=RouteCategory.DETERMINISTIC_DATA,
                        response=_faith_resp,
                        route_name='faith_status',
                        domain='faith',
                        is_terminal=True,
                    )
                    result.elapsed_ms = (time.monotonic() - t_start) * 1000
                    _log_route_decision(result, user, message)
                    return result
            # A grounded GLUCOSE diagnostic ("what's causing my blood sugar to be
            # high overnight?") is cause-seeking but must be answered from real
            # glucose signals, not handed to the reflective LLM — same principle
            # as faith-status recognition (Phase 2a, 2026-06-18). The governor
            # stays the authority; it just routes a grounded diagnostic to the
            # deterministic handler.
            if _match_glucose_diagnostic_query(msg_lower) and user is not None:
                _glu_resp = _handle_glucose_diagnostic_query(user, msg_lower)
                if _glu_resp:
                    result = RouteResult(
                        category=RouteCategory.DETERMINISTIC_DATA,
                        response=_glu_resp,
                        route_name='glucose_diagnostic_query',
                        domain='health',
                        is_terminal=True,
                    )
                    result.elapsed_ms = (time.monotonic() - t_start) * 1000
                    _log_route_decision(result, user, message)
                    return result
            # A strategic / executive-lens question must be answered from the
            # single executive layer (build_executive_summary), not the reflective
            # LLM — same carve-out pattern as faith / glucose (Phase 1). Standalone
            # risk stays on the decision engine.
            if _match_executive_query(msg_lower) and user is not None:
                _exec_resp = _handle_executive_query(user, msg_lower)
                if _exec_resp:
                    result = RouteResult(
                        category=RouteCategory.DETERMINISTIC_DATA,
                        response=_exec_resp,
                        route_name='executive_summary_query',
                        domain='executive',
                        is_terminal=True,
                    )
                    result.elapsed_ms = (time.monotonic() - t_start) * 1000
                    _log_route_decision(result, user, message)
                    return result
            result = RouteResult(
                route_name='governor_reflective',
                skip_intent=True,
                # Still infer the domain so downstream context scoping works on a
                # reflective fallthrough (mirrors the final no_match fallthrough).
                domain=_infer_domain(msg_lower),
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

    # ── EXECUTIVE-LENS route (Phase 1) — single executive reasoning layer ──
    # Strategic / executive-lens questions answered from build_executive_summary
    # (the layer the dashboard uses) BEFORE the daily-briefing / health-analyze /
    # decision / focus / check-in gates can grab them by wording. Execution and
    # standalone-risk questions are NOT matched (Phase 1 boundary). (2026-06-18)
    if user is not None and _match_executive_query(msg_lower):
        _exec_resp = _handle_executive_query(user, msg_lower)
        if _exec_resp:
            result = RouteResult(
                category=RouteCategory.DETERMINISTIC_DATA,
                response=_exec_resp,
                route_name='executive_summary_query',
                domain='executive',
                is_terminal=True,
            )
            result.elapsed_ms = (time.monotonic() - t_start) * 1000
            _log_route_decision(result, user, message)
            return result

    # ── Event-stream attention routes — answer "what needs my attention /
    # what am I late on / what's coming up" from the unified GuidanceItem event
    # stream FIRST (execution state is a supplemental fallback), BEFORE the
    # legacy execution / focus / check-in handlers can grab them by wording.
    # One coherent CoS stream for strategic + operational. (2026-06-21)
    if user is not None:
        _evt_handler = _evt_name = None
        if _match_late_query(msg_lower):
            _evt_handler, _evt_name = _handle_late_query, 'late_events_query'
        elif _match_upcoming_query(msg_lower):
            _evt_handler, _evt_name = _handle_upcoming_query, 'upcoming_events_query'
        elif _match_attention_now_query(msg_lower):
            _evt_handler, _evt_name = _handle_attention_now_query, 'attention_now_query'
        if _evt_handler is not None:
            _evt_resp = _evt_handler(user, msg_lower)
            if _evt_resp:
                result = RouteResult(
                    category=RouteCategory.DETERMINISTIC_DATA,
                    response=_evt_resp,
                    route_name=_evt_name,
                    domain='cos',
                    is_terminal=True,
                )
                result.elapsed_ms = (time.monotonic() - t_start) * 1000
                _log_route_decision(result, user, message)
                return result

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

    # ══════════════════════════════════════════════════════════
    # STABILIZATION SPRINT — Analyze intent override (Fix 1 + Fix 4)
    # High-confidence Analyze phrasing ("what do you think about my
    # weight history", "how am I doing overall") must NOT be swallowed
    # by the greedy status/data/retrieve routes below, must NEVER reach
    # task mutation, and must NOT contaminate into Execute. We intercept
    # here, before all of those.
    # ══════════════════════════════════════════════════════════
    try:
        from apps.ai.cognitive_mode import stabilization as _stab
        from apps.ai.cognitive_mode import health_analyze_v1 as _hv1
        if _stab.stabilization_enabled() and user is not None:
            # Continuity: a follow-up ("why?", "tell me more", "what would you
            # do?") within an active health thread deepens it instead of
            # restarting. Bounded: only fires when a fresh thread context exists.
            # Page-awareness precedence: if the user is actively on a content page
            # (Faith reading/journey), a generic follow-up should stay grounded in
            # the PAGE, not be hijacked by an earlier health thread — so defer to
            # the page-aware LLM path (which still has health data anyway).
            # Explicit health-status intent ("how am I doing with my health?",
            # "how is my health?", "am I healthy?", "how am I doing physically?")
            # ALWAYS outranks continuity / check-in / operational routing. Without
            # this, these phrasings miss the analyze detector (is_analyze_request)
            # and fall through to the CoS execution / status routes, which answer
            # with the operational task backlog. Continuity enriches — never hijacks
            # the domain.
            _explicit_health = _hv1.is_explicit_health_intent(msg_lower)
            _hctx = _hv1.get_health_context(conversation) if conversation is not None else None
            try:
                from apps.ai.page_context_state import active_page_present as _page_active
                _on_content_page = _page_active(conversation)
            except Exception:
                _on_content_page = False
            if (_hctx and _hv1.is_health_followup(msg_lower)
                    and not _on_content_page and not _explicit_health):
                _dresp = _hv1.build_deepen(user, msg_lower, conversation)
                if _dresp:
                    result = RouteResult(
                        category=RouteCategory.DETERMINISTIC_HEALTH_SUMMARY,
                        response=_dresp, route_name='analyze_health_followup',
                        domain='health', is_terminal=True,
                    )
                    result.elapsed_ms = (time.monotonic() - t_start) * 1000
                    _log_route_decision(result, user, message)
                    return result

            _is_analyze = _stab.is_analyze_request(msg_lower)
            _is_judgment = _hv1.is_health_judgment_request(msg_lower)
            _is_coaching = _hv1.is_health_coaching_request(msg_lower)
            _health_ctx = _stab.is_health_context(msg_lower)
            # Beth is a health coach: coaching phrasings ("what concerns you most",
            # "if you picked one thing", "should I change anything") route to v1's
            # leverage reasoning by DEFAULT — unless the question clearly targets
            # another domain (finance/tasks/faith/...). This is the root fix for
            # coaching falling through to the macro-compliance decision route.
            _coaching_ok = _is_coaching and not _hv1.mentions_non_health_domain(msg_lower)
            if _is_analyze or _is_judgment or _coaching_ok or _explicit_health:
                _stab_health = (_health_ctx or _is_judgment or _coaching_ok
                                or _explicit_health)
                if _stab_health:
                    try:
                        from apps.ai.cognitive_mode.health_truth import ensure_health_fresh
                        ensure_health_fresh(user)  # fresh-by-design before analysis
                    except Exception:
                        pass
                    _resp = _hv1.build_health_analyze(user, msg_lower, conversation=conversation)
                    _rname = 'analyze_health_v1'
                    if _resp is None:
                        _resp = _stab.build_health_analyze_v0(user)
                        _rname = 'analyze_health_v0'
                    if _resp:
                        result = RouteResult(
                            category=RouteCategory.DETERMINISTIC_HEALTH_SUMMARY,
                            response=_resp,
                            route_name=_rname,
                            domain='health',
                            is_terminal=True,
                        )
                        result.elapsed_ms = (time.monotonic() - t_start) * 1000
                        _log_route_decision(result, user, message)
                        return result
                # Analyze without a terminal package (non-health, or health
                # returned nothing): skip the intent classifier (no mutation, no
                # execute) and answer via LLM with a domain hint.
                result = RouteResult(
                    route_name='analyze_override',
                    domain='health' if _stab_health else None,
                    skip_intent=True,
                )
                result.elapsed_ms = (time.monotonic() - t_start) * 1000
                _log_route_decision(result, user, message)
                return result
    except Exception as _stab_err:
        logger.warning("STABILIZATION analyze override failed (fail-open): %s", _stab_err)

    # ── Phase 0a: Today status query (bypasses LLM entirely) ──────
    result = _try_status_query_route(msg_lower, user)
    if result is not None:
        result.elapsed_ms = (time.monotonic() - t_start) * 1000
        _log_route_decision(result, user, message)
        return result

    # ── Enumerate-remaining query (deterministic, exhaustive) ────
    # "List everything still remaining today." → list ALL items from the same
    # canonical Today-Engine source as the count route (count == list), never a
    # summarized check-in with "+N more" (trust bug 2026-06-15). Runs before the
    # qualified-status route and before the LLM check-in prefilter.
    if _is_enumerate_remaining_query(msg_lower) and user is not None:
        try:
            response = _build_enumerate_remaining_response(user)
            if response:
                result = RouteResult(
                    category=RouteCategory.DETERMINISTIC_DATA,
                    response=response,
                    route_name='enumerate_remaining',
                    domain='execution',
                    is_terminal=True,
                )
                result.elapsed_ms = (time.monotonic() - t_start) * 1000
                _log_route_decision(result, user, message)
                return result
        except Exception as e:
            logger.warning(
                "Enumerate-remaining route failed, falling through: %s",
                e, exc_info=True,
            )

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

    # ── Phase 0a.2: Nutrition status query — HARD DETERMINISTIC ──
    # Nutrition status MUST win over generic decision/focus/execution
    # routing. "How am I doing on protein today?" embeds "how am i
    # doing", which Phase 11.1 (_is_decision_query) / Phase 4
    # (_is_focus_query) would otherwise grab and route to execution
    # coaching ("Go straight into Bike Ride…"). A nutrient + status
    # query is unambiguously a nutrition status request and is answered
    # deterministically from the same FoodEntry-derived state the
    # dashboard reads. Food-estimate / logging phrasing is excluded
    # inside _match_nutrition_query, so "I had 8 oysters, how much
    # protein?" still falls through to the log/estimate path. If the
    # handler returns None (no data, or the confidence guard refuses a
    # contradictory snapshot), we fall through to the normal pipeline.
    if (
        user is not None
        and _is_data_routes_enabled()
        and _match_nutrition_query(msg_lower)
    ):
        try:
            _nut_resp = _handle_nutrition_query(user, msg_lower)
            if _nut_resp:
                result = RouteResult(
                    category=RouteCategory.DETERMINISTIC_DATA,
                    response=_nut_resp,
                    route_name='nutrition_query',
                    domain='health',
                    is_terminal=True,
                )
                result.elapsed_ms = (time.monotonic() - t_start) * 1000
                _log_route_decision(result, user, message)
                return result
        except Exception as e:
            logger.warning(
                "Nutrition status route failed, falling through: %s",
                e, exc_info=True,
            )

    # ── Faith-status recognition (deterministic, canonical-first) ──
    # "Do you see I've been reading?" / "how consistent have I been with Bible
    # reading?" / "how is my faith lately?" / "am I on track spiritually?".
    # Trust-critical factual recognition must NOT depend on LLM synthesis — it
    # resolves from canonical execution truth (the same source as dashboard /
    # adherence / routine completion) so Beth can never contradict completion
    # history (trust contract 2026-06-16). Runs BEFORE the decision/focus route
    # because these can contain "how am I doing".
    if _is_faith_status_query(msg_lower) and user is not None:
        _faith_resp = _handle_faith_status_query(user, msg_lower)
        if _faith_resp:
            result = RouteResult(
                category=RouteCategory.DETERMINISTIC_DATA,
                response=_faith_resp,
                route_name='faith_status',
                domain='faith',
                is_terminal=True,
            )
            result.elapsed_ms = (time.monotonic() - t_start) * 1000
            _log_route_decision(result, user, message)
            return result

    # ── PLANNING intent (Goals/Life) — RUNS BEFORE the execution gates ──
    # Long-range planning ("what should I focus on next month / this quarter /
    # be building toward?") is NOT execution and must NEVER be answered with
    # today's overdue tasks. Intercept planning-category questions here, ahead of
    # the next-step / decision / focus gates, and answer from grounded goal
    # strategy only (Phase 1, 2026-06-18). Always terminal once matched — a
    # planning question never falls through to the execution path.
    if user is not None and _match_planning_query(msg_lower):
        _resp = _handle_planning_query(user, msg_lower)
        if _resp:
            result = RouteResult(
                category=RouteCategory.DETERMINISTIC_DATA,
                response=_resp,
                route_name='planning_query',
                domain='purpose',
                is_terminal=True,
            )
            result.elapsed_ms = (time.monotonic() - t_start) * 1000
            _log_route_decision(result, user, message)
            return result

    # ── Canonical next-step route (unified selector) ────────────
    # "What should I do next?" / "Next step" answer from the SAME selector the
    # check-in uses (build_locked_next_action → get_next_action over
    # build_execution_state). Runs BEFORE the decision route so a pure
    # next-step query is never answered by a different engine (right_now_focus)
    # than the check-in — they must agree (trust bug 2026-06-15). Decision
    # queries (biggest risk / fix first / focus) still fall through below.
    if _is_next_step_query(msg_lower) and user is not None:
        try:
            from apps.ai.cos_fact_statements import build_locked_next_action
            _resp = build_locked_next_action(user)
            if _resp:
                result = RouteResult(
                    category=RouteCategory.DETERMINISTIC_DATA,
                    response=_resp,
                    route_name='next_action_canonical',
                    domain='execution',
                    is_terminal=True,
                )
                result.elapsed_ms = (time.monotonic() - t_start) * 1000
                _log_route_decision(result, user, message)
                return result
        except Exception as e:
            logger.warning(
                "Canonical next-step route failed, falling through: %s",
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

    # ── Phase 1a2: Actual wake-time ("what time did I wake up?") ──
    # Past-tense ACTUAL wake question. Answers from Tier-1 truth (wake-routine
    # performed_at / sleep wake_time), NEVER the scheduled time, and states
    # uncertainty when unverifiable (trust bug 2026-06-16: scheduled answered
    # as actual). Distinct from the present-tense routine-time route below.
    if _match_actual_wake_query(msg_lower) and user is not None:
        _wake_resp = _handle_actual_wake_query(user)
        if _wake_resp:
            result = RouteResult(
                category=RouteCategory.DETERMINISTIC_DATA,
                response=_wake_resp,
                route_name='actual_wake_time',
                domain='execution',
                is_terminal=True,
            )
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

    # ── Explicit deferral ("I won't do X today") — terminal ──────
    # User agency outranks optimization: an explicit decision to defer an
    # activity for today must MODIFY today's plan deterministically (reschedule
    # the task to tomorrow / skip the routine for today), not just produce
    # empathetic text that the execution engines then ignore (trust bug
    # 2026-06-15). Runs before the LLM check-in prefilter. Grounded + bounded:
    # only acts on an unambiguous single match against today's incomplete items;
    # otherwise returns None and falls through (no false action).
    if _is_defer_today_intent(msg_lower) and user is not None:
        try:
            response = _handle_defer_today(user, msg_lower)
            if response:
                result = RouteResult(
                    category=RouteCategory.DETERMINISTIC_DATA,
                    response=response,
                    route_name='defer_today',
                    domain='execution',
                    is_terminal=True,
                )
                result.elapsed_ms = (time.monotonic() - t_start) * 1000
                _log_route_decision(result, user, message)
                return result
        except Exception as e:
            logger.warning(
                "Defer-today route failed, falling through: %s", e, exc_info=True)

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


# Faith-status recognition. Trust-critical factual questions answered from
# canonical execution truth (NOT LLM synthesis) so Beth never contradicts
# completion history (trust contract 2026-06-16).
_FAITH_STATUS_TOKENS = (
    'bible', 'scripture', 'devotional', 'faith', 'prayer', 'pray',
    'spiritual', 'gospel', 'quiet time', 'reading',
)
_FAITH_STATUS_CUES = (
    'do you see', 'do you know', 'have i been', 'have i read', 'have i completed',
    "i've completed", "i've been", 'did i', 'how consistent', 'how is my',
    "how's my", 'how has my', 'how have i', 'how am i doing', 'how am i tracking',
    'lately', 'recently', 'on track', 'staying on track', 'this week',
    'these days', 'been doing', 'keeping up',
)


def _is_faith_status_query(msg_lower):
    """True for a faith-status RECOGNITION question (not logging/mutation)."""
    if not msg_lower:
        return False
    if any(x in msg_lower for x in ('log ', 'record ', 'mark ', 'add ', 'remind')):
        return False
    return (
        any(t in msg_lower for t in _FAITH_STATUS_TOKENS)
        and any(c in msg_lower for c in _FAITH_STATUS_CUES)
    )


def _handle_faith_status_query(user, msg_lower=None):
    """Deterministic faith-status answer from canonical execution truth.

    Recognizes Bible-reading + prayer completion + recent consistency from the
    SAME source as dashboard/adherence/routine completion, so the answer can
    never contradict completion history. Returns a grounded string, or None.
    """
    from datetime import timedelta

    from apps.core.utils import get_user_now, get_user_today
    from apps.faith.services.faith_queries import FaithQueries

    try:
        today = get_user_today(user)
    except Exception:
        return None
    try:
        from apps.core.execution.execution_truth_engine import get_execution_truth
        faith = (get_execution_truth(user) or {}).get('domains', {}).get('faith', {})
    except Exception:
        faith = {}
    bible_today = bool(faith.get('bible_reading_completed'))
    prayer_today = bool(faith.get('prayer_completed'))

    dates = FaithQueries.bible_completion_dates(user, limit=30)
    last7 = sum(1 for d in dates if d and d >= today - timedelta(days=7))
    try:
        from apps.core.ai_state.state_builder import _calculate_reading_streak
        streak = _calculate_reading_streak(user, get_user_now(user))
    except Exception:
        streak = 0

    parts = []
    if bible_today:
        parts.append("Yes — you've completed your Bible reading today.")
    elif dates and (today - dates[0]).days <= 1:
        parts.append(
            "You haven't logged Bible reading yet today, but you read yesterday.")
    elif dates:
        parts.append(
            f"Your most recent Bible reading was {(today - dates[0]).days} days "
            f"ago ({dates[0].isoformat()})."
        )
    else:
        parts.append("I don't see any Bible reading logged recently.")

    if dates:
        c = f"Over the last 7 days you've read on {last7} day{'s' if last7 != 1 else ''}"
        if streak >= 2:
            c += f", and you're on a {streak}-day streak"
        parts.append(c + ".")

    if any(k in (msg_lower or '') for k in ('faith', 'prayer', 'pray', 'spiritual', 'on track')):
        parts.append(
            "Prayer is complete today." if prayer_today
            else "Prayer isn't logged yet today.")
    return " ".join(parts)


# Pure "what is the single next step?" phrases. These are unified onto the ONE
# canonical execution selector (build_locked_next_action) so the answer matches
# the check-in exactly (trust bug 2026-06-15: competing next-action engines).
# Deliberately tighter than _NEXT_ACTION_PHRASES — focus/priority phrasing is
# left to the decision/focus route so its broader behavior is unchanged.
_NEXT_STEP_CANONICAL_PHRASES = (
    'what should i do next', 'what do i do next', 'what to do next',
    "what's next", 'whats next', 'what is next', 'what next',
    'next step', 'next action', 'give me my next action',
    'what should i start', 'where should i start', 'what should i tackle',
    'what should i work on',
)


def _is_next_step_query(msg_lower):
    """True for a pure 'what's my next step?' question (unified selector)."""
    if not msg_lower:
        return False
    return any(p in msg_lower for p in _NEXT_STEP_CANONICAL_PHRASES)


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
# Phase 19.1 / 19.2 — CoS tone refinement (post-processing only)
#
# Applied at the tail of _format_cos_decision_response so every
# handler's output runs through it. All transformations are
# deterministic regex / string substitutions — no randomness, no
# reordering, no added actions, no removed actions. Meaning is
# preserved; only wording is tightened.
#
# Phase 19.1 rules:
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
#
# Phase 19.2 rules (leadership-voice polish, runs AFTER 19.1):
#   7. Strengthen verbs: "Start …" / "Then start …" →
#      "Go straight into …" / "Then go straight into …"; same for
#      "begin" → "move into". Narrow patterns (line-anchored or
#      after "Then ") so titles that happen to contain the word
#      "Start" aren't rewritten.
#   8. Leadership framing: "it's already overdue" →
#      "you're behind on it already"
#   9. Normalize "N item(s)" to plural English: "1 item", "2 items"
#  10. Add consequence framing to the two specific biggest-risk
#      fallback phrases (idempotent — the tags are only appended
#      when they are not already present).
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

    # ── Phase 19.2 — leadership-voice polish ────────────────────
    # Applied AFTER 19.1 so these rules operate on the already-
    # merged, already-cleaned text. Each transformation is
    # idempotent: applying refine twice produces the same result
    # as applying it once.

    # 7a. "Start X" / "Then start X" → "Go straight into X" /
    #     "Then go straight into X". Anchored to line start or
    #     "Then " prefix so titles containing the word "Start"
    #     are not accidentally rewritten.
    out = re.sub(r'(^|\n)Start ', r'\1Go straight into ', out)
    out = re.sub(r'\bThen start ', 'Then go straight into ', out)

    # 7b. "Begin X" / "Then begin X" → "Move into X" /
    #     "Then move into X".
    out = re.sub(r'(^|\n)Begin ', r'\1Move into ', out)
    out = re.sub(r'\bThen begin ', 'Then move into ', out)

    # 8. Leadership framing — shift "it's" subject to "you".
    out = out.replace(
        "it's already overdue",
        "you're behind on it already",
    )

    # 9. Pluralize "item(s)" deterministically. Real outputs have
    #    the count separated from "item(s)" by adjectives like
    #    "overdue" / "foundational", so we default to the plural
    #    form globally and then fix the singular "1 items" case
    #    with a word-boundary anchor (so "11 items" stays plural).
    out = out.replace('item(s)', 'items')
    # Fix singular "1 items" even when adjectives sit between the
    # count and "items" (e.g. "1 overdue foundational items").
    # \b1\b keeps "11 items" / "21 items" as plural.
    out = re.sub(r'\b1 ((?:\w+ )*)items\b', r'1 \1item', out)

    # 10. Consequence framing on biggest-risk fallback phrases.
    #     Only appended when not already present (idempotent).
    if (
        "falling behind is your biggest risk today" in out
        and "this compounds quickly" not in out
    ):
        out = out.replace(
            "falling behind is your biggest risk today",
            "falling behind is your biggest risk today — "
            "this compounds quickly",
            1,
        )
    if (
        "Skipping foundational commitments is your biggest risk" in out
        and "slip further" not in out
    ):
        out = out.replace(
            "Skipping foundational commitments is your biggest risk",
            "Skipping foundational commitments is your biggest risk — "
            "it'll slip further if you leave it",
            1,
        )

    return out


# ═════════════════════════════════════════════════════════════════
# Phase 19.3 — Single-action fallback resolver
#
# The decision contract requires ONE concrete next action, never a
# category or list of options. When the main priority stack in
# _build_focus_query_response returns None (no overdue / upcoming /
# foundational exec item / signal focus), this resolver picks a
# single habit — or the hard-coded concrete default — to surface.
#
# Do NOT change this function's return shape without updating both
# callers (_build_focus_query_response and _try_decision_query_route).
# ═════════════════════════════════════════════════════════════════


# Bare fallback string — used directly by the safety guard at the
# end of _build_focus_query_response. The resolver below layers an
# optional time-aware suffix on top of this base for the common
# path. Both forms are a single concrete action; never a category.
_FINAL_DEFAULT_ACTION = "Pause and pray now"


def _time_aware_final_default(user) -> str:
    """Return the final-default action with an optional time-of-day
    flavor clause. Morning / evening add a short purpose line;
    other hours keep the bare anchor. Never returns a multi-option
    string. Any failure in the time lookup falls back to the bare
    ``_FINAL_DEFAULT_ACTION`` so the contract is preserved.
    """
    try:
        from apps.core.utils import get_user_now
        hour = get_user_now(user).hour
    except Exception:
        return _FINAL_DEFAULT_ACTION

    if 5 <= hour < 12:
        return f"{_FINAL_DEFAULT_ACTION} — set the tone for your day"
    if hour >= 20 or hour < 5:
        return f"{_FINAL_DEFAULT_ACTION} — close out your day"
    return _FINAL_DEFAULT_ACTION


def resolve_fallback_action(user) -> dict:
    """Return a concrete single-action fallback: ``{primary_action,
    context_reason}``. Never returns a category, never multi-option,
    never None.

    Priority (narrow — the main stack already tried tasks, upcoming,
    foundational exec items, and signal focus before this resolver
    runs):

        3. Highest-priority foundational habit from SAE
           ``habits.streaks_per_habit``. Foundational first, then
           longest current streak as the tiebreaker so the user is
           nudged to protect an established streak.
        5. Hard-coded concrete default — ``_FINAL_DEFAULT_ACTION``
           ("Pause and pray now"), optionally decorated with a
           time-of-day purpose clause (morning / evening).
    """
    # 3. Habit lookup via canonical SAE state.
    try:
        from apps.core.ai_state.state_engine import get_module_state
        habits_state = get_module_state(user, 'habits') or {}
        streaks = habits_state.get('streaks_per_habit') or []
        ranked = sorted(
            streaks,
            key=lambda h: (
                not h.get('is_foundational', False),
                -(h.get('current_streak') or 0),
            ),
        )
        if ranked:
            top = ranked[0]
            name = (top.get('name') or '').strip()
            streak = int(top.get('current_streak') or 0)
            if name:
                primary = f"Do your {name} now"
                context = (
                    f"Protect your {streak}-day streak"
                    if streak >= 3 else None
                )
                return {
                    'primary_action': primary,
                    'context_reason': context,
                }
    except Exception:
        logger.debug(
            "resolve_fallback_action: habit lookup failed for user=%s",
            getattr(user, 'id', '?'),
            exc_info=True,
        )

    # 5. Hard-coded concrete default, optionally time-aware.
    return {
        'primary_action': _time_aware_final_default(user),
        'context_reason': None,
    }


_COS_DECISIVE_STARTS = (
    "Take", "Start", "Complete", "Get ", "Close ", "Address",
    "Log", "Plan", "Shut", "Stay ", "Clear ", "Then ",
    "Pause", "Do ", "Go straight into", "Move into",
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

            from apps.core.ai_state.right_now import _execution_completed_domains
            focus = compute_right_now_focus(
                trust_reports,
                completed_today=_execution_completed_domains(user),
            )
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
            # Phase 19.3: no category fallback, no multi-option
            # wording. Deterministic single-action resolver.
            fb = resolve_fallback_action(user)
            primary_action = fb['primary_action']
            # Resolver owns the context — do not re-layer the old
            # "no concrete focus surfaced" debug line.
            context_reason = fb.get('context_reason')
    elif late and primary_action and not quick_wins_titles:
        # Late evening but a real primary exists (e.g. unfinished
        # foundational). Nudge toward close-the-day framing — context
        # still explains why.
        pass  # Keep primary as-is; formatter handles late-evening tone.

    # Safety guard: the contract requires exactly one concrete
    # primary action. Every branch above must populate it. If a
    # future edit introduces a path that leaves primary_action None,
    # fail closed to the hard-coded final default so the user never
    # receives an empty response.
    if not primary_action:
        primary_action = _FINAL_DEFAULT_ACTION
        context_reason = None

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

    # Phase 19.3: concrete single-action fallback. No category,
    # no "A, B, or C" options, no debug leakage. The resolver
    # picks the user's highest-priority foundational habit (or
    # the hard-coded concrete default) and returns one clear
    # next step.
    _fallback = resolve_fallback_action(user)
    _SAFE_FALLBACK = _format_cos_decision_response(
        primary_action=_fallback['primary_action'],
        context_reason=_fallback.get('context_reason'),
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
        from apps.core.ai_state.right_now import (
            compute_right_now_focus, _execution_completed_domains,
        )
        reports = _get_all_trust_reports(user)
        focus = compute_right_now_focus(
            reports, completed_today=_execution_completed_domains(user))
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


# Consumption phrasing — the user is reporting/asking about a SPECIFIC food
# they ate, not their daily nutrition status. These must fall through to the
# log_food / estimate path, never the deterministic status route.
_FOOD_CONSUMPTION_PHRASES = (
    'i had ', 'i ate ', 'i just had ', 'i just ate ', 'i consumed ',
    'i drank ', 'i just drank ', "i've had ", "i've eaten ", 'i had a ',
    'i had an ', 'i had some ', 'i ate a ', 'i ate an ', 'i ate some ',
    'ate a ', 'ate an ', 'ate some ', 'had a serving',
)
# "<macro> in/of <food>" estimate phrasing — asking the nutrient content of a
# named food, not a status summary.
_FOOD_ESTIMATE_PHRASES = (
    'protein in ', 'calories in ', 'carbs in ', 'carbohydrates in ',
    'fat in ', 'macros in ', 'fiber in ', 'sugar in ', 'sodium in ',
    'protein of ', 'calories of ', 'carbs of ', 'macros of ',
    'how much protein is in ', 'how many calories in ',
    'how many calories are in ', 'how many calories does ',
)


def _is_food_estimate_query(msg_lower):
    """True when the user is asking about a SPECIFIC food's macros or reporting
    that they ate something — an estimate/log request, not a status query.

    Phase 5 FIX 1: food-entity + quantity awareness. Prevents substring hijack
    (e.g. 'how much protein' inside 'I had 8 oysters how much protein') from
    routing a logging/estimate intent into the deterministic status responder.
    """
    if any(p in msg_lower for p in _FOOD_CONSUMPTION_PHRASES):
        return True
    if any(p in msg_lower for p in _FOOD_ESTIMATE_PHRASES):
        return True
    return False


def _match_nutrition_query(msg_lower):
    """Match nutrition / macro / calorie STATUS questions.

    Two-tier match:
      1. Established exact-phrase anchors (``_NUT_INTENT``).
      2. Compositional — a nutrient keyword + a status anchor
         ("protein today", "how am I doing on protein", "macro
         compliance", "nutrition today"). This tier is REQUIRED because
         status phrasing like "how am I doing on protein today?" embeds
         "how am i doing", which the decision/focus routers (Phase 11.1 /
         Phase 4) would otherwise grab and send to execution coaching.

    Food-estimate / logging / "calories burned" phrasing is excluded so
    "I had 8 oysters, how much protein?" still falls through to the
    log/estimate path.
    """
    if _is_future_tense_query(msg_lower):
        return False

    # Logging intent or exercise-calorie phrasing is never a status read.
    _EXCLUDE = ('log', 'record', 'add', 'set', 'enter', 'track ',
                'burn', 'burned', 'burnt')
    if any(e in msg_lower for e in _EXCLUDE):
        return False

    # A clear logged-total STATUS question ("how many calories today / so far",
    # "protein today", "calories right now") is never a food estimate — answer it
    # deterministically even when the food-estimate heuristic would trip on
    # "have I had" (Phase 1 matcher fix, 2026-06-19). Without this, "how many
    # calories have I had today?" fell through to the LLM and was answered with
    # the rolling 7-day average. Checked BEFORE the food-estimate exclusion.
    _STATUS_TODAY = ('today', 'so far', 'this week', 'right now', 'currently')
    if (any(k in msg_lower for k in (
                'calorie', 'calories', 'protein', 'macro', 'macros',
                'carb', 'carbs', 'nutrition'))
            and any(t in msg_lower for t in _STATUS_TODAY)):
        return True

    # FIX 1: a specific-food estimate / consumption report is NOT a status query.
    if _is_food_estimate_query(msg_lower):
        return False

    _NUT_INTENT = (
        'how is my nutrition', "how's my nutrition", 'my nutrition',
        'my macros', 'macro status', 'how are my macros',
        'my calories', 'calorie count', 'how many calories',
        'nutrition status', 'nutrition summary', 'nutrition this week',
        'macros today', 'calories today', 'how much protein',
    )
    if any(p in msg_lower for p in _NUT_INTENT):
        return True

    # Compositional: nutrient keyword + status framing.
    _NUTRIENT_KEYWORDS = (
        'protein', 'calorie', 'calories', 'macro', 'macros',
        'carb', 'carbs', 'carbohydrate', 'nutrition', 'fiber',
    )
    _STATUS_ANCHORS = (
        'today', 'how am i doing', 'how are my', 'how is my',
        "how's my", 'how much', 'status', 'compliance', 'this week',
        'so far', 'have i had', 'am i at', 'where am i',
    )
    if any(k in msg_lower for k in _NUTRIENT_KEYWORDS):
        if any(a in msg_lower for a in _STATUS_ANCHORS):
            return True
    return False


_NUTRITION_COACHING_REQUEST = (
    'what should i', 'what do i do', 'how do i', 'how can i',
    'help me', 'what can i do', 'should i eat', 'give me advice',
    'recommend', 'fix my', 'improve my', 'what next', 'what now',
)


def _is_nutrition_coaching_request(msg_lower):
    """True only when the user explicitly asks for guidance/coaching rather
    than a bare factual status question. Fact mode (answer-first) is the
    default; the full decision/coaching template is the exception."""
    if not msg_lower:
        return False
    return any(p in msg_lower for p in _NUTRITION_COACHING_REQUEST)


def _nutrition_fact_response(nut, msg_lower):
    """Answer-first response for a direct factual nutrition status question.

    Trust contract (2026-06-02): a narrow factual question gets a grounded
    answer ONLY — no cross-domain priority note, no macro-score
    interpretation, no execution coaching. Just the totals the user asked
    for plus a neutral target comparison when a target exists. Same-domain
    only. Returns None when the asked nutrient has no groundable value so the
    caller falls through rather than emitting the coaching template.
    """
    cal = nut.get('daily_calories')
    protein = nut.get('daily_protein_g')
    cal_target = nut.get('calorie_target')
    protein_target = nut.get('protein_target')

    text = msg_lower or ''
    asked_protein = 'protein' in text
    asked_calories = 'calorie' in text  # covers 'calorie' and 'calories'
    # Generic phrasing ("nutrition today", "my macros") → report both.
    if not asked_protein and not asked_calories:
        show_protein = show_calories = True
    else:
        show_protein, show_calories = asked_protein, asked_calories

    # Distinguish "logged 0" from "nothing logged yet" — a 0 with no food
    # entries is an empty log, not a tracked zero. Preserve truth, no inference
    # (trust bug 2026-06-15: "0 calories today" read as a real measurement).
    food_count = nut.get('food_entries_today', 0) or 0

    blocks = []

    if show_protein and protein is not None:
        if not food_count and int(protein) == 0:
            blocks.append(
                "I don't see nutrition logged today yet, so I'm currently "
                "showing 0g tracked protein.")
        elif food_count and int(protein) == 0:
            # Entries exist today but total 0 — honest about the inconsistency,
            # never a bare confident 0, never abstain to the LLM (Phase 1).
            blocks.append(
                f"You've logged {food_count} item{'s' if food_count != 1 else ''} "
                f"today, but they total **0g** protein so far — the entries may "
                f"not have macro data yet.")
        else:
            block = [f"You're at **{int(protein)}g** protein today."]
            if protein_target:
                delta = int(protein) - int(protein_target)
                block.append(f"Target: **{int(protein_target)}g**.")
                if delta >= 0:
                    block.append(f"That's **{delta}g over** target.")
                else:
                    block.append(f"That's **{abs(delta)}g under** target.")
            blocks.append('\n'.join(block))

    if show_calories and cal is not None:
        if not food_count and int(cal) == 0:
            blocks.append(
                "I don't see nutrition logged today yet, so I'm currently "
                "showing 0 tracked calories.")
        elif food_count and int(cal) == 0:
            # Entries exist today but total 0 — honest about the inconsistency,
            # never a bare confident 0, never abstain to the LLM (Phase 1).
            blocks.append(
                f"You've logged {food_count} item{'s' if food_count != 1 else ''} "
                f"today, but they total **0** calories so far — the entries may "
                f"not have calorie data yet.")
        else:
            block = [f"You're at **{int(cal)}** calories today."]
            if cal_target:
                delta = int(cal) - int(cal_target)
                block.append(f"Target: **{int(cal_target)}**.")
                if delta >= 0:
                    block.append(f"That's **{delta} over** target.")
                else:
                    block.append(f"That's **{abs(delta)} under** target.")
            blocks.append('\n'.join(block))

    if not blocks:
        return None  # Nothing grounded for the asked nutrient → fall through
    return '\n\n'.join(blocks)


def _handle_nutrition_query(user, msg_lower=None):
    """Phase 4.5 — deterministic nutrition response.

    Answer-first by default (``msg_lower`` factual status question) → grounded
    totals only. The Situation/Interpretation/Action decision template is
    reserved for explicit coaching requests ("what should I do about my
    macros?"). See _nutrition_fact_response / _is_nutrition_coaching_request.
    """
    # FIX 3 (nutrition-only): refresh the nutrition snapshot from raw FoodEntry
    # writes before reading it, so Beth and the dashboard cannot diverge on
    # "today". Scoped to nutrition deliberately — NOT a global freshness change.
    try:
        from apps.core.ai_state.state_freshness import ensure_fresh
        ensure_fresh(user, ["nutrition"])
    except Exception as e:
        logger.warning("nutrition query: freshness refresh failed: %s", e)

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
    food_entries_today = nut.get('food_entries_today')

    # ── No-abstain for trust-critical factual retrieval (Phase 1, 2026-06-19) ──
    # A direct factual nutrition status question ("calories today?", "protein
    # today?") MUST return a grounded today answer or an honest "nothing logged
    # today" — NEVER None. Returning None drops the question to the LLM, where
    # the rolling 7-day average lives and gets parroted as "today" (the 0-vs-1355
    # trust bug). The snapshot was refreshed from raw FoodEntry above
    # (ensure_fresh), so daily_calories is canonical and matches the nutrition
    # page. _nutrition_fact_response already distinguishes "logged 0" from
    # "nothing logged today yet" — it does NOT substitute the rolling average.
    # (Replaces the prior contradictory/suspicious "refuse → fall through" guard,
    # which abstained to the LLM exactly when it should have said 0.)
    if not _is_nutrition_coaching_request(msg_lower):
        resp = _nutrition_fact_response(nut, msg_lower)
        if resp:
            return resp
        return (
            "I don't see any nutrition logged today yet — nothing is tracked "
            "so far today."
        )

    # Coaching path is non-factual (Situation/Interpretation/Action). With
    # genuinely no data it may defer to the coaching pipeline.
    if cal is None and food_entries_7d == 0:
        return None

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

        from apps.core.ai_state.right_now import _execution_completed_domains
        focus = compute_right_now_focus(
            trust_reports,
            completed_today=_execution_completed_domains(user),
        )
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

        # PRIORITY 1: Overdue — earliest still-ACTIONABLE item only.
        # A long-stale overdue item (e.g. 5:30 AM routine at 1:48 PM) must
        # not be surfaced as "next" — it belongs in Risk/Fix (trust bug
        # 2026-06-15). Same block-eligibility gate as the check-in path.
        overdue = ctx.get("overdue", [])
        if overdue:
            overdue = sorted(overdue, key=lambda e: e["sort_time"])
            selected = None
            try:
                from apps.core.execution.active_block import (
                    get_active_block, first_eligible_overdue,
                )
                from apps.core.utils import get_user_now
                _now = get_user_now(user)
                ab = get_active_block(user, now=_now)
                entry = first_eligible_overdue(overdue, ab, _now.time())
                if entry:
                    selected = entry["label"]
            except Exception:
                logger.debug("[NEXT ACTION] overdue gate failed", exc_info=True)
            if selected:
                logger.info(
                    "[NEXT ACTION] user=%s OVERDUE selected=%s from=%d",
                    user.id, selected, len(overdue),
                )
                return f"Start {selected}."
            # No actionable overdue → fall through to coming-up / later.

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
    try:
        from apps.ai.cognitive_mode.health_truth import ensure_health_fresh
        ensure_health_fresh(user)
    except Exception:
        pass
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


# Past-tense ACTUAL wake-time questions. Distinct from the present-tense
# routine-time matcher (which answers scheduled time). These ask what actually
# happened and must be answered from Tier-1 truth, never the scheduled value.
_ACTUAL_WAKE_PATTERNS = (
    "what time did i wake", "when did i wake", "what time did i get up",
    "when did i get up", "what time did i actually wake", "how early did i wake",
    "what time was i up", "time i woke up", "when i woke up", "what time i woke",
    "did i wake up at", "what time did i rise",
)


def _match_actual_wake_query(msg_lower):
    """Match a past-tense 'what time did I actually wake up?' question."""
    return bool(msg_lower) and any(p in msg_lower for p in _ACTUAL_WAKE_PATTERNS)


def _handle_actual_wake_query(user):
    """Deterministic ACTUAL wake-time answer — Tier-1 truth, never scheduled.

    Source precedence (2026-06-16 fix): SLEEP `wake_time` is the real biometric
    and WINS; wake-routine `RoutineLog.performed_at` is only a FALLBACK because
    it auto-fills from the click/marked time (which can equal the scheduled
    time, so it must never beat sleep). The scheduled time is shown separately
    for transparency. Honest uncertainty when neither actual source exists —
    never substitutes scheduled for actual. Returns a string, or None.
    """
    from django.utils import timezone

    from apps.core.utils import get_user_today

    def _fmt(dt):
        try:
            dt = timezone.localtime(dt)
        except Exception:
            pass
        try:
            return dt.strftime("%I:%M %p").lstrip("0")
        except Exception:
            return None

    try:
        today = get_user_today(user)
    except Exception:
        return None

    scheduled = None
    routine_actual = None
    sleep_actual = None

    # Scheduled wake time + routine completion. performed_at is the marked/click
    # time (auto-filled from completed_at) — NOT reliable as actual wake, so it
    # is only a fallback below.
    try:
        from apps.life.models import RoutineLog
        log = (
            RoutineLog.objects.filter(
                user=user, scheduled_date=today,
                log_status__in=[
                    RoutineLog.STATUS_COMPLETED, RoutineLog.STATUS_COMPLETED_LATE],
                schedule__name__iregex=r'wake|get up|rise',
            )
            .select_related('schedule')
            .order_by('performed_at', 'completed_at')
            .first()
        )
        if log:
            if log.schedule and log.schedule.scheduled_time:
                scheduled = log.schedule.scheduled_time.strftime(
                    "%I:%M %p").lstrip("0")
            ts = log.performed_at or log.completed_at
            if ts:
                routine_actual = _fmt(ts)
    except Exception:
        logger.debug("wake query: routine source failed", exc_info=True)

    # Sleep wake timestamp — the real biometric; PREFERRED actual source.
    # CRITICAL: SleepEntry.sleep_date is the NIGHT-OF (e.g. last night = 16th
    # when you wake on the 17th), so a `sleep_date=today` filter MISSES this
    # morning's wake (2026-06-17 fix — the bug behind the prod 5:00 answer).
    # Search the night-of window (yesterday + today) and take the most recent
    # wake within ~36h.
    try:
        from datetime import timedelta

        from apps.health.models import SleepEntry
        cutoff = timezone.now() - timedelta(hours=36)
        se = (
            SleepEntry.objects.filter(
                user=user, sleep_date__in=[today, today - timedelta(days=1)])
            .exclude(wake_time__isnull=True)
            .order_by('-wake_time')
            .first()
        )
        if se and se.wake_time and se.wake_time >= cutoff:
            sleep_actual = _fmt(se.wake_time)
    except Exception:
        logger.debug("wake query: sleep source failed", exc_info=True)

    # Precedence: sleep wins; routine performed_at is the fallback.
    if sleep_actual:
        actual, source = sleep_actual, "your sleep/wake data"
    elif routine_actual:
        actual, source = routine_actual, "your wake-up routine completion"
    else:
        actual, source = None, None

    # Honest uncertainty — never substitute scheduled for actual.
    if actual is None:
        if scheduled:
            return (
                f"I don't have a confirmed actual wake-up time logged for today "
                f"— you were scheduled for {scheduled}, but I can't verify when "
                f"you actually woke, so I won't guess."
            )
        return (
            "I don't have a confirmed wake-up time for today — nothing's logged "
            "from sleep data or a wake routine, so I'd be guessing."
        )

    if scheduled and scheduled != actual:
        return (
            f"You were scheduled to wake at {scheduled}, but based on {source} "
            f"you actually woke around {actual}."
        )
    return f"Based on {source}, you woke around {actual} today."


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


_LAST_WORKOUT_TRIGGERS = (
    'last workout', 'latest workout', 'most recent workout',
    'what was my last workout', 'my last workout', 'previous workout',
    'last training session', 'last gym session', 'last lift', 'last session',
    'last exercise session',
)


def _match_last_workout_query(msg_lower):
    """Match event-style 'what was my LAST workout?' queries (vs aggregates)."""
    if _is_future_tense_query(msg_lower):
        return False
    if any(e in msg_lower for e in ('log', 'record', 'start', 'begin', 'create', 'add', 'plan')):
        return False
    return any(p in msg_lower for p in _LAST_WORKOUT_TRIGGERS)


def _handle_last_workout_query(user):
    """Deterministic LATEST workout from canonical SAE `fitness.last_workout`.

    Pure retrieval — never the LLM, so journal/conversation memory can NEVER
    contaminate this answer.
    """
    from apps.core.ai_state.state_engine import get_module_state
    fitness = get_module_state(user, 'fitness') or {}
    lw = fitness.get('last_workout') or {}
    if not lw.get('name'):
        # No-abstain (Phase 1, 2026-06-19): the SAE snapshot hasn't captured the
        # latest session — read it LIVE from WorkoutSession (the same source the
        # workout page shows), mirroring the SAE last_workout computation. A
        # "last workout" question must never drop to the LLM, which narrates
        # contaminated journal/conversation memory ("you got up early…").
        try:
            from datetime import timedelta as _td
            from apps.core.utils import get_user_now
            from apps.health.services.workout_queries import WorkoutQueries
            _now = get_user_now(user)
            sess = (WorkoutQueries.completed_in_range(
                        user, _now.date() - _td(days=365), _now.date())
                    .order_by("-date", "-id")
                    .prefetch_related("workout_exercises__sets").first())
            if sess is not None:
                _exs = list(sess.workout_exercises.all())
                lw = {
                    "name": sess.name,
                    "date": str(sess.date),
                    "minutes": sess.duration_minutes,
                    "exercise_count": len(_exs),
                    "set_count": sum(len(we.sets.all()) for we in _exs),
                }
        except Exception:
            logger.warning("last workout live fallback failed", exc_info=True)
    name = lw.get('name')
    if not name:
        # Truly no workout logged — honest, never abstain to the LLM.
        return ("I don't see any completed workouts logged yet — log one and "
                "I'll keep track of it.")

    when = ''
    date_str = lw.get('date')
    if date_str:
        try:
            from datetime import date as _date
            d = _date.fromisoformat(date_str)
            when = f" on {d.strftime('%b')} {d.day}"
        except Exception:
            when = f" on {date_str}"

    resp = f"Your last workout was **{name}**{when}."

    detail = []
    ex = lw.get('exercise_count')
    sets = lw.get('set_count')
    mins = lw.get('minutes')
    if ex:
        detail.append(f"{ex} exercise{'s' if ex != 1 else ''}")
    if sets:
        detail.append(f"{sets} set{'s' if sets != 1 else ''}")
    if mins:
        detail.append(f"{mins} min")
    if detail:
        resp += " It included " + ", ".join(detail) + "."
    return resp


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
        if not fitness:
            return None  # No fitness data at all → fall through
        # Has fitness state but zero activity this week → explicit zero answer
        # (deterministic, never a fallthrough) so the query is always grounded.
        return _format_decision_response(
            situation="No workouts logged this week yet.",
            interpretation="No training activity recorded in the last 7 days.",
            action="Log a short session today to restart the rhythm.",
            trust=_get_domain_trust(user, 'workouts'),
            priority_note=_get_high_priority_note(user, exclude_domain='workouts'),
        )

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
        interp_bits.append(f"Strong week — {workouts_7d} {session_word}")
    elif workouts_7d >= 3:
        interp_bits.append(f"On track — {workouts_7d} {session_word}")
    else:
        interp_bits.append(f"Limited activity this week — {workouts_7d} {session_word}")

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

    response = _format_decision_response(
        situation=situation,
        interpretation=interpretation,
        action=action,
        trust=trust,
        priority_note=_get_high_priority_note(user, exclude_domain='workouts'),
    )

    # Insight invitation for an active training week (progress domain) —
    # mirrors the weight-trend invitation. Only offered when there is enough
    # activity to make a pattern read meaningful.
    if workouts_7d >= 3 or (completed_7d and completed_7d >= 3):
        response += (
            "\n\nWant me to look at your training patterns and recovery?"
        )

    return response


# ─────────────────────────────────────────────────────────────────────
# Shared deterministic intent classifier (Phase 0, 2026-06-18).
#
# Beth must recognise WHAT KIND of question is being asked before deciding HOW
# to answer it. This is a shared CONVENTION, not a router: it returns the single
# intent CATEGORY for a message, and domain routes consult it (as the sleep
# routes do below) before dispatching to their own grounded handlers. It is NOT
# a universal router, an LLM planner, or a central dispatcher — routing order in
# classify_and_route() is unchanged; this only de-duplicates the cue sets that
# previously lived per-domain (sleep / nutrition / health-analyze / decision).
#
# Categories, highest precedence first (order of the checks below IS the
# precedence — approved 2026-06-17/18):
#   recognition — "do you see I've…", "have I been…"   (factual acknowledgement)
#   planning    — future horizon: "next month", "this quarter", "build toward"
#   coaching    — action / how-to: "how can I improve…", "best way", "tips"
#   diagnostic  — cause-seeking: "why…", "what's causing…", "what's limiting…"
#   execution   — immediate next step: "what should I do next", "what's next"
#   status      — default floor: factual current-state lookup
#
# Approved precedence rules: PLANNING beats EXECUTION when a future horizon
# exists; COACHING (action verb) beats DIAGNOSTIC; RECOGNITION beats STATUS;
# STATUS is the floor.
# ─────────────────────────────────────────────────────────────────────

_RECOGNITION_CUES = (
    'do you see', 'do you notice', 'did you notice', 'do you know that',
    'can you see i', 'can you tell i', 'do you recognize', 'do you acknowledge',
    'have i been', "i've been doing", 'am i staying on track',
    'how consistent have i',
)

# Future-horizon cues ONLY — deliberately excludes "this week" / "this month",
# which are STATUS windows (e.g. "how is my sleep this week").
_PLANNING_CUES = (
    'next month', 'next week', 'next quarter', 'this quarter', 'next year',
    'over the next', 'in the coming', 'coming weeks', 'coming months',
    'few weeks', 'next few weeks', 'few months', 'weeks ahead', 'months ahead',
    'long term', 'long-term', 'longer term', 'going forward', 'down the road',
    'build toward', 'building toward', 'work toward', 'working toward',
    'be building', 'should i be building',
)

# Action / how-to verbs. Intentionally excludes the bare "what should I do" /
# "what should I" stems, which collide with the EXECUTION next-step phrasings.
_COACHING_CUES = (
    'how can i', 'how do i', 'how to improve', 'how should i', 'improve my',
    'best way', 'tips', 'ways to', 'recommend', 'give me advice', 'help me',
    'what can i do', 'what actions', 'fix my', 'what should i change',
    'do differently', 'should i change', 'should i adjust', 'what would you do',
    'what should i do to', 'what should i do about',
)

# Cause-seeking ("why / what's causing / what's limiting / what's driving").
_DIAGNOSTIC_CUES = (
    'why', "what's causing", 'what is causing', 'whats causing', 'causing my',
    'cause of', "what's behind", 'what is behind', "what's limiting",
    'what is limiting', 'limiting my', 'holding me back', 'holding my',
    'struggling with', "what's wrong", 'what is wrong', 'whats wrong',
    'reason for', 'reason my', "why can't i", 'why cant i', 'root cause',
    'what is hurting', "what's hurting", 'what is driving', "what's driving",
    'whats driving', 'driving my',
)

# Immediate next-step ("what now / what's next / next action").
_EXECUTION_CUES = (
    'what should i do next', 'what do i do next', 'what to do next',
    "what's next", 'whats next', 'what is next', 'what next', 'next step',
    'next action', 'right now', 'what now', 'what should i start',
    'where should i start', 'what should i tackle', 'what should i work on',
)


def classify_query_intent(msg_lower):
    """Return the single intent CATEGORY for a message (precedence as documented
    above). Pure and deterministic — no DB, no LLM. Domain routes consult this
    and then dispatch to their own grounded handlers."""
    if not msg_lower:
        return 'status'
    m = msg_lower
    if any(c in m for c in _RECOGNITION_CUES):
        return 'recognition'
    if any(c in m for c in _PLANNING_CUES):
        return 'planning'
    if any(c in m for c in _COACHING_CUES):
        return 'coaching'
    if any(c in m for c in _DIAGNOSTIC_CUES):
        return 'diagnostic'
    if any(c in m for c in _EXECUTION_CUES):
        return 'execution'
    return 'status'


# ─────────────────────────────────────────────────────────────────────
# PLANNING intent (Phase 1, 2026-06-18) — Goals/Life long-range direction.
#
# "What should I focus on next month / this quarter / be building toward?" is a
# PLANNING question, NOT execution. The trust bug: these matched the decision /
# focus / next-step gates and were answered with TODAY's overdue tasks. This
# route intercepts planning-category questions (via the shared classifier)
# BEFORE those gates and answers from grounded goal sources only — the active
# Primary Mission + its next milestone + the nightly momentum snapshot — never
# today's task list.
# ─────────────────────────────────────────────────────────────────────

# Planning-horizon questions scoped to a specific tracked DOMAIN (sleep, glucose,
# weight, …) are out of Phase 1 scope — they are NOT goal planning, so we let the
# domain / LLM handle them rather than answering with goal strategy.
_PLANNING_DOMAIN_EXCLUSIONS = (
    'sleep', 'glucose', 'blood sugar', 'a1c', 'weight', 'nutrition', 'calorie',
    'macro', 'workout', 'exercise', 'training', 'running', 'steps',
    'prayer', 'bible', 'scripture', 'devotion', 'medication',
    'blood pressure', 'heart rate',
)


def _match_planning_query(msg_lower):
    """Match GENERAL life-direction PLANNING questions (future horizon), so they
    are answered from goal strategy — never today's tasks. Domain-scoped planning
    ("improve my sleep next month") is excluded (Phase 1 scope)."""
    if not msg_lower:
        return False
    if classify_query_intent(msg_lower) != 'planning':
        return False
    if any(t in msg_lower for t in _PLANNING_DOMAIN_EXCLUSIONS):
        return False
    return True


def _handle_planning_query(user, msg_lower=None):
    """Grounded long-range planning answer: strategic priority → why it matters →
    near-term milestone → next practical step. Reads canonical sources only (the
    same Primary-Mission selector the dashboard/CoS use; momentum is the persisted
    nightly snapshot trend, no request-path compute). NEVER uses today's task
    list. Honest when no mission is set; never guesses a direction."""
    try:
        from apps.purpose.mission_selection import select_active_mission_goal
        from apps.core.utils import get_user_today
        goal = select_active_mission_goal(user)
        if goal is None:
            return (
                "You don't have a Primary Mission set right now, so I can't point "
                "you at a strategic focus yet. Pick the goal that matters most in "
                "Goals and mark it your Primary Mission — then I can map out what "
                "to build toward over the coming weeks."
            )
        today = get_user_today(user)
        # 1) Strategic priority — the mission itself.
        parts = [
            f"Over the longer arc, your highest-leverage focus is your mission: "
            f"**{goal.title}**."
        ]
        # 2) Why it matters — the user's OWN words (never generated); else the
        #    target-date framing.
        why = (goal.why_it_matters or "").strip()
        if why:
            parts.append(f"Why it matters: {why}")
        elif goal.target_date and goal.target_date > today:
            days = (goal.target_date - today).days
            parts.append(
                f"You set a target date of {goal.target_date:%b %d, %Y} — about "
                f"{days} days out — so that's the horizon to steer by."
            )
        # Momentum — persisted nightly snapshot trend only (no live compute).
        snap = goal.momentum_snapshots.first()
        trend_word = {
            'rising': 'building', 'stable': 'steady', 'falling': 'slipping',
        }.get(getattr(snap, 'momentum_trend', None) or '', '')
        # 3) Near-term milestone — the next incomplete checkpoint.
        nm = goal.next_milestone
        if nm:
            ms = f"Your near-term milestone is **{nm.title}**"
            if nm.target_date:
                ms += f", targeted for {nm.target_date:%b %d}"
                if nm.target_date > today:
                    ms += f" ({(nm.target_date - today).days} days out)"
            ms += "."
            if trend_word:
                ms += f" Momentum on the mission is {trend_word}."
            parts.append(ms)
            # 4) Next practical step — tied to the milestone (its own detail when
            #    present), never today's unrelated task list.
            step = (nm.description or "").strip()
            if step:
                parts.append(f"Practical next step: {step}")
            else:
                parts.append(
                    f"Practical next step: put your effort into moving "
                    f"\"{nm.title}\" forward — that's the concrete thing that "
                    f"advances the mission."
                )
        else:
            if trend_word:
                parts.append(f"Momentum on the mission is {trend_word}.")
            parts.append(
                "You haven't broken this mission into milestones yet — the most "
                "useful planning step is to define the next concrete milestone so "
                "there's a checkpoint to aim at."
            )
        return " ".join(parts)
    except Exception:
        logger.warning("planning route failed", exc_info=True)
        # Fail SAFE, not wrong: honest uncertainty, never today's task list.
        return (
            "I can't pull your mission and milestones together right now to give "
            "you a grounded plan — try again in a moment. (I won't guess at a "
            "direction from today's task list.)"
        )


# ─────────────────────────────────────────────────────────────────────
# EXECUTIVE-LENS route (Phase 1, 2026-06-18) — single executive layer.
#
# Strategic / executive-lens questions (biggest win / opportunity / improvement
# / decline, most important trend, what to protect, the story, overall &
# strategic status, executive / Chief-of-Staff briefing) are answered from the
# ONE executive reasoning layer the dashboard uses — build_executive_summary —
# so they stop scattering across the decision engine / health-analyze / check-in
# / LLM by wording. EXECUTION questions (next step, am I behind, check in, list
# remaining, daily checklist) are NOT matched and stay on the execution path.
# Standalone "biggest risk" / "fix first" / "what needs attention" remain on the
# decision engine (Phase 1 boundary — risk reconciliation is Phase 2).
# ─────────────────────────────────────────────────────────────────────
_EXECUTIVE_LENS_PHRASES = (
    'biggest win', 'biggest opportunity', 'biggest improvement',
    'biggest decline', 'most important trend', 'most important improvement',
    'what should i protect', 'protect the most', 'what do i protect',
    'what story do the data', 'story do the data', 'what story does the data',
    'story the data tell', 'story of my life',
    'how am i doing overall', 'how am i doing in life', 'overall how am i',
    "how's my life overall", 'how is my life going', 'how is my life overall',
    'most important things happening', 'most important things in my life',
    'things happening in my life', 'most important things right now',
    'executive briefing', 'chief of staff briefing', 'strategic briefing',
    'executive summary', 'strategic status', 'strategic overview',
    'overall strategic',
    # Trajectory / life-direction (2026-06-20 reclassification — these were
    # falling through to the LLM).
    'trajectory', 'where am i headed', 'moving in the right direction',
    'right direction', 'on the right path',
    # Strategic / executive assessment phrasings (were falling to the LLM).
    'executive assessment', 'strategic assessment', 'assess my life',
    'assess my trajectory', 'overall assessment', 'assess my overall',
)

# Holistic "how am I doing" / "how are things going" stems route to the
# executive OVERALL lens — but ONLY when the question is NOT qualified by a
# specific domain or an operational time-window. "How am I doing on protein?" /
# "how am I doing with sleep?" / "how am I doing today?" must keep routing to
# their domain status / execution paths (2026-06-20 reclassification, guarded).
_EXECUTIVE_HOLISTIC_AMBIGUOUS = (
    'how am i doing', "how'm i doing", 'how are things going',
    'how is everything going', 'how are things',
)
_EXEC_DOMAIN_GUARD_TOKENS = (
    # domain tokens — domain status questions own these
    'protein', 'calorie', 'calories', 'macro', 'macros', 'carb', 'carbs',
    'sleep', 'workout', 'exercise', 'training', 'lifting', 'cardio',
    'glucose', 'blood sugar', 'a1c', 'nutrition', 'weight', 'weigh',
    'medication', 'meds', 'supplement', 'goal', 'financ', 'money', 'budget',
    'spending', 'net worth', 'faith', 'prayer', 'scripture', 'bible',
    'journal', 'mood', 'steps', 'hydration', 'water', 'heart rate',
    'blood pressure', 'vitals', 'health', 'work',
    # operational time-windows stay on the execution / today path
    'today', 'this week', 'right now', 'this morning',
)


# Cross-domain Chief-of-Staff COACHING questions (2026-06-21). Outcome / goal /
# leverage-level questions that require synthesising ACROSS domains ("what do I
# need to do to keep losing weight?", "what's the highest-leverage thing I can
# do?", "what's helping and what's hurting?"). The cross-domain answer already
# exists in the executive lens layer (win=helping, decline=hurting, opportunity=
# highest-leverage) — these phrasings just route there and render as coaching.
# Deliberately strategic/outcome phrasings only, so single-domain coaching
# ("how can I improve my sleep") keeps its own route.
_COS_COACHING_PHRASES = (
    'what do i need to do to continue', 'what do i need to do to keep',
    'what do i need to do to lose', 'what do i need to do to hit',
    'what do i need to do to reach', 'what do i need to do to stay',
    'what should i do to keep', 'what should i do to continue',
    'what should i focus on to keep', 'what should i focus on to continue',
    'highest leverage', 'highest-leverage', 'biggest lever',
    "what's helping and what's hurting", 'what is helping and what is hurting',
    "what's working and what's not", "what's working and what isn't",
    'most important thing i can do', 'most important thing i could do',
    'what matters most for my', 'continue losing', 'keep losing weight',
    'how do i keep losing', 'what one thing',
)


def _match_executive_query(msg_lower):
    """Match strategic / executive-lens questions (answered from the single
    executive_summary layer). Deliberately excludes standalone risk / fix-first /
    attention (decision engine) and all execution / check-in phrasings.

    Holistic "how am I doing" forms match too, but ONLY when not domain- or
    time-qualified (guard) — so domain status questions keep their own routes.
    Cross-domain CoS coaching questions also match (rendered as coaching)."""
    if not msg_lower:
        return False
    if _cos_mode_for(msg_lower):
        return True
    if any(p in msg_lower for p in _EXECUTIVE_LENS_PHRASES):
        return True
    if any(p in msg_lower for p in _COS_COACHING_PHRASES):
        return True
    if any(p in msg_lower for p in _EXECUTIVE_HOLISTIC_AMBIGUOUS):
        return not any(t in msg_lower for t in _EXEC_DOMAIN_GUARD_TOKENS)
    return False


def _executive_lens_for(msg_lower):
    m = msg_lower or ''
    if any(p in m for p in _COS_COACHING_PHRASES):
        return 'coaching'
    if 'biggest win' in m:
        return 'biggest_win'
    if 'biggest improvement' in m or 'most important improvement' in m:
        return 'biggest_improvement'
    if 'biggest decline' in m:
        return 'biggest_decline'
    if 'biggest opportunity' in m:
        return 'biggest_opportunity'
    if 'most important trend' in m:
        return 'most_important_trend'
    if 'protect' in m:
        return 'protect'
    if 'story' in m:
        return 'story'
    if any(p in m for p in (
            'chief of staff briefing', 'executive briefing', 'strategic briefing',
            'executive summary', 'strategic status', 'strategic overview',
            'brief me')):
        return 'briefing'
    return 'overall'  # overall / how-am-i-doing-overall / most-important-things


def _exec_field_msg(d):
    if not isinstance(d, dict):
        return None
    return (d.get('message') or d.get('why') or d.get('headline')
            or d.get('title'))


_EXEC_TRAJECTORY = {
    'improving': "Your trajectory is improving.",
    'steady': "Your trajectory is steady.",
    'slipping': "Your trajectory is slipping.",
    'mixed': "Your trajectory is mixed — moving in more than one direction.",
    'at_risk': "Your trajectory is under pressure right now.",
}


def _render_executive_overall(es):
    """Overall / strategic / executive (CoS) briefing synthesis: trajectory →
    Win → Watch → also-going-well, from the executive_summary fields only. The
    briefing MAY reference biggest_risk (allowed in synthesis). Omits any part
    with no grounded signal; honest when nothing is available yet."""
    win_d = es.get('biggest_win') or {}
    win = _exec_field_msg(win_d)
    decline = _exec_field_msg(es.get('biggest_decline'))
    risk = _exec_field_msg(es.get('biggest_risk'))
    traj = es.get('trajectory')
    gw = [g.get('title') for g in (es.get('going_well') or []) if g.get('title')]
    extra = [t for t in gw if t != win_d.get('title')][:3]
    parts = []
    if _EXEC_TRAJECTORY.get(traj):
        parts.append(_EXEC_TRAJECTORY[traj])
    if win:
        parts.append(f"Win: {win}")
    if decline:
        parts.append(f"Watch: {decline}")
    elif risk:
        parts.append(f"Watch: {risk}")
    if extra:
        parts.append("Also going well: " + "; ".join(extra) + ".")
    if not parts:
        return ("I don't have enough grounded standing signal to give you a "
                "strategic read yet — keep logging and the picture will fill in.")
    return " ".join(parts)


def _render_executive_protect(es):
    """What to protect = the strongest standing positive to sustain + the decline
    that threatens it. Grounded only; honest when there's no win."""
    win = _exec_field_msg(es.get('biggest_win'))
    decline = _exec_field_msg(es.get('biggest_decline'))
    if not win and not decline:
        return ("I don't have a clear standing win or risk to point to yet — "
                "keep logging and I'll tell you what's most worth protecting.")
    if win:
        msg = f"Protect your momentum here: {win}"
        if decline:
            msg += f" The main thing that could undercut it: {decline}"
        return msg
    return f"What's most at risk of slipping: {decline}"


def _render_executive_story(es):
    """The story the data tell = trajectory framing + the win + the watch, as a
    short grounded narrative. No speculation; only fields that exist."""
    win = _exec_field_msg(es.get('biggest_win'))
    decline = _exec_field_msg(es.get('biggest_decline'))
    trend = _exec_field_msg(es.get('most_important_trend'))
    traj = es.get('trajectory')
    bits = [b for b in (win, decline) if b] or ([trend] if trend else [])
    if not bits:
        return ("The data don't yet tell a clear story — keep logging and the "
                "throughline will emerge.")
    lead = {
        'improving': "The throughline right now is positive: ",
        'mixed': "The story is mixed: ",
        'slipping': "The throughline right now is concerning: ",
        'at_risk': "The story right now is one of pressure: ",
        'steady': "The story right now is steady: ",
    }.get(traj, "Here's the throughline right now: ")
    return lead + " ".join(bits)


def _render_cos_coaching(es, lenses):
    """Cross-domain Chief-of-Staff coaching from the executive lenses: what's
    helping (win + improvement), what's working against you (decline), and the
    highest-leverage move (opportunity, leverage-framed). Grounded only —
    honest when there isn't enough signal to coach."""
    win = _exec_field_msg(lenses.get('biggest_win')) or _exec_field_msg(
        es.get('biggest_win'))
    imp = _exec_field_msg(lenses.get('biggest_improvement'))
    dec = _exec_field_msg(lenses.get('biggest_decline')) or _exec_field_msg(
        es.get('biggest_decline'))
    opp = lenses.get('opportunity')
    helping = [h for h in (win, imp) if h]
    parts = []
    if helping:
        parts.append("Here's the read across your data — what's working for "
                     "you: " + " ".join(helping))
    if dec:
        parts.append("What's working against you: " + dec)
    if opp:
        parts.append("Highest-leverage move: " + opp)
    if not parts:
        return ("I don't have enough grounded signal across your data yet to "
                "coach this well — keep logging and I'll tell you what's "
                "helping, what's hurting, and the single highest-leverage move.")
    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────
# ACCOUNTABILITY LOOP (2026-06-21) — Chief-of-Staff memory of progress.
# "Have we made progress on my sleep?" → compares the metric now vs ~3–4 weeks
# ago from EXISTING history and judges whether the focus is working. Grounded;
# NO new model, NO stored recommendations — the metric's own history is the
# record. Plausibility-guarded so noisy/sparse data degrades to honest
# uncertainty instead of a false verdict.
# ─────────────────────────────────────────────────────────────────────
_ACCT_PROGRESS_CUES = (
    'made progress', 'making progress', 'is it improving', 'is improving',
    'has it improved', 'have i improved', 'getting better', 'gotten better',
    'improved over', 'improving over', 'over the last few weeks',
    'over the past few weeks', 'better than last week',
    'better than a few weeks', 'moving the needle', 'trending the right way',
    'is the focus working', 'focus working', 'is this working', 'is it working',
    'getting any better', 'going down', 'coming down', 'gone down',
    'is it moving', 'have we improved', 'are we improving',
)
_ACCT_DOMAINS = {
    'sleep': ('sleep',),
    'weight': ('weight', 'weigh'),
    'glucose': ('glucose', 'blood sugar', 'a1c'),
}
_ACCT_FLAT = {'sleep': 0.3, 'weight': 1.0, 'glucose': 5.0}


def _accountability_domain(msg_lower):
    for dom, toks in _ACCT_DOMAINS.items():
        if any(t in msg_lower for t in toks):
            return dom
    return None


def _match_accountability_query(msg_lower):
    """Progress-over-time questions about a tracked metric ('have we made
    progress on my sleep', 'is my weight coming down')."""
    if not msg_lower or _is_future_tense_query(msg_lower):
        return False
    if not any(c in msg_lower for c in _ACCT_PROGRESS_CUES):
        return False
    return _accountability_domain(msg_lower) is not None


def _accountability_assessment(user, domain):
    """Grounded progress sentence for `domain` (last ~week vs ~4 weeks ago), or
    honest uncertainty when there isn't clean history. Never raises."""
    from datetime import timedelta
    from django.db.models import Avg
    from django.utils import timezone
    now = timezone.now()
    unit = ''
    lower_better = False
    recent = past = None
    try:
        if domain == 'sleep':
            from apps.health.models import SleepEntry
            unit, lower_better = 'h', False

            def _savg(d0, d1):
                qs = SleepEntry.objects.filter(
                    user=user, sleep_date__gt=d0, sleep_date__lte=d1)
                vals = [e.total_duration_minutes / 60 for e in qs
                        if e.total_duration_minutes
                        and 3.0 <= e.total_duration_minutes / 60 <= 12.0]
                return round(sum(vals) / len(vals), 1) if vals else None
            recent = _savg((now - timedelta(days=7)).date(), now.date())
            past = _savg((now - timedelta(days=35)).date(),
                         (now - timedelta(days=21)).date())
        elif domain == 'weight':
            from apps.health.models import WeightEntry
            unit, lower_better = ' lb', True
            qs = WeightEntry.objects.filter(
                user=user, status='active').order_by('recorded_at')
            last = qs.last()
            recent = round(float(last.value_in_lb), 1) if last else None
            older = qs.filter(
                recorded_at__lte=now - timedelta(days=28)).last()
            past = round(float(older.value_in_lb), 1) if older else None
        elif domain == 'glucose':
            from apps.health.models import GlucoseEntry
            unit, lower_better = ' mg/dL', True

            def _gavg(d0, d1):
                a = GlucoseEntry.objects.filter(
                    user=user, recorded_at__gte=d0,
                    recorded_at__lt=d1).aggregate(a=Avg('value'))['a']
                return round(float(a)) if a is not None else None
            recent = _gavg(now - timedelta(days=7), now)
            past = _gavg(now - timedelta(days=35), now - timedelta(days=28))
    except Exception:
        logger.warning("accountability assessment failed", exc_info=True)
        return None

    if recent is None or past is None:
        return (f"I don't have enough clean {domain} history yet to judge "
                f"whether it's improving — keep logging and I'll track the "
                f"trend over the coming weeks.")
    delta = round(recent - past, 1)
    span = f"from {past}{unit} to {recent}{unit}"
    if abs(delta) < _ACCT_FLAT.get(domain, 0.3):
        return (f"Your {domain} has been roughly flat over the last few weeks "
                f"({span}). It hasn't really moved — worth a different approach.")
    improved = (delta < 0) if lower_better else (delta > 0)
    if improved:
        return (f"Your {domain} has improved over the last few weeks ({span}). "
                f"What you're doing is working — keep it up.")
    return (f"Your {domain} has gone the wrong way over the last few weeks "
            f"({span}). The current approach isn't working — let's change tack.")


def _handle_accountability_query(user, msg_lower=None):
    dom = _accountability_domain(msg_lower or '')
    if dom is None:
        return ("I can track progress on your sleep, weight, and glucose over "
                "time — which would you like a read on?")
    return _accountability_assessment(user, dom)


# ── Recommendation tracking + effectiveness (2026-06-21) ──
# Beth as an OUTCOME engine: she records the constraint she's steering you toward
# and later judges whether it worked. Persistence reuses GuidanceItem (no schema
# change); see apps/ai/cos_recommendations.py.
_REC_EFFECTIVENESS_CUES = (
    'is your recommendation working', 'is the recommendation working',
    'is your advice working', 'is the advice working',
    'is what you told me working', 'did the recommendation work',
    'has the recommendation been effective', 'is the recommendation effective',
    'has your advice worked', 'are your recommendations working',
    'has the focus been effective', 'is the plan working',
    'has your advice been working', 'is your guidance working',
)
_REC_LIST_CUES = (
    'what advice have you given', 'what advice have you been giving',
    'what have you been telling me', 'what have you recommended',
    'what are you having me focus on', 'what recommendations have you',
    'what have you been recommending', 'what is the plan you gave me',
    'what advice are you giving me', 'what have you been steering me',
    'what should i be focusing on lately',
)


def _match_rec_effectiveness_query(msg_lower):
    return bool(msg_lower) and any(c in msg_lower for c in _REC_EFFECTIVENESS_CUES)


def _match_recommendation_list_query(msg_lower):
    return bool(msg_lower) and any(c in msg_lower for c in _REC_LIST_CUES)


def _handle_rec_effectiveness_query(user, msg_lower=None):
    from apps.ai.cos_recommendations import evaluate_active_recommendations
    return evaluate_active_recommendations(user) or (
        "I haven't been tracking a specific recommendation long enough to judge "
        "yet — ask me what to focus on and I'll start measuring whether it works.")


def _handle_recommendation_list_query(user, msg_lower=None):
    from apps.ai.cos_recommendations import list_recommendations
    return list_recommendations(user)


# ── Goal trajectory / pace (Capability 5, 2026-06-21) ──
_PACE_CUES = (
    'on pace', 'on track to', 'when will i reach', 'when will i hit',
    'reach my goal', 'hit my goal', 'hit my target', 'reach my target',
    'what pace', 'current pace', 'pace am i', 'how fast am i losing',
    'will i hit my target', 'am i on track for my goal', 'on track to hit',
    'projected to reach', 'rate am i losing', 'how long until i reach',
    'how long to reach my goal', 'am i on pace', 'still on pace',
)


def _match_goal_pace_query(msg_lower):
    return bool(msg_lower) and any(c in msg_lower for c in _PACE_CUES)


def _handle_goal_pace_query(user, msg_lower=None):
    from apps.ai.cos_intelligence import goal_pace, goal_pace_narrative
    return goal_pace_narrative(goal_pace(user)) or (
        "I don't see a weight goal with enough history to project a pace yet — "
        "set a goal with a target date and I'll track your trajectory.")


# ── Event-stream attention routes (2026-06-21) ──
# "What needs my attention / what am I late on / what's coming up" answer from
# the unified GuidanceItem event stream FIRST (strategic + operational), with
# execution state as a supplemental fallback only when the stream is empty.
# This makes the three legacy execution questions part of the one CoS stream.
_ATTENTION_NOW_CUES = (
    'what needs my attention', 'needs my attention', 'need my attention',
    'what requires my attention', 'what needs attention', 'requires attention',
    'what should i focus on right now', 'what should i focus on now',
    'what should i deal with', 'what should i be focused on right now',
    'what should i be doing right now',
)
_LATE_CUES = (
    'what am i late on', 'what am i behind on', "what's overdue",
    'what is overdue', 'what have i missed', 'what am i late for',
    'what am i overdue on', "what's late", 'what did i miss today',
    'what have i not done', 'am i behind on anything',
)
_UPCOMING_CUES = (
    'what is coming up', "what's coming up", 'coming up soon',
    'what is coming up soon', 'what is next today', "what's next today",
    'what is approaching', 'what do i have coming up', 'what is due soon',
    "what's due soon", 'what is due later', 'what is on my plate',
    "what's on my plate", 'what should i prepare for',
)


def _match_attention_now_query(m):
    return bool(m) and any(c in m for c in _ATTENTION_NOW_CUES)


def _match_late_query(m):
    return bool(m) and any(c in m for c in _LATE_CUES)


def _match_upcoming_query(m):
    return bool(m) and any(c in m for c in _UPCOMING_CUES)


def _execution_actions(user):
    """Fallback source: (overdue, now, upcoming) action titles from the canonical
    execution state. Used ONLY when the event stream has no relevant events."""
    try:
        from apps.core.execution.execution_state import build_execution_state
        es = build_execution_state(user) or {}
    except Exception:
        return [], [], []

    def _titles(key):
        return [a.get('title') for a in (es.get(key) or []) if a.get('title')]
    return (_titles('overdue_actions'), _titles('now_actions'),
            _titles('upcoming_actions'))


def _evt_bullets(items):
    return "\n".join(f"• {t}" for t in items)


def _handle_attention_now_query(user, msg_lower=None):
    from apps.ai.cos_event_engine import (
        active_events, STRATEGIC_RISK, DUE_NOW, PAST_DUE, RECURRING_PROBLEM)
    evs = active_events(user)
    strat = [e for e in evs if e['category'] == STRATEGIC_RISK]
    oper = [e for e in evs if e['category'] in (DUE_NOW, PAST_DUE, RECURRING_PROBLEM)]
    if strat or oper:
        parts = []
        if strat:
            parts.append("Strategic attention:\n"
                         + _evt_bullets(e['title'] for e in strat[:3]))
        if oper:
            parts.append("Operational attention:\n"
                         + _evt_bullets(e['title'] for e in oper[:5]))
        return "\n\n".join(parts)
    overdue, now, _ = _execution_actions(user)  # fallback
    items = overdue + now
    if items:
        return "Right now, focus on:\n" + _evt_bullets(items[:5])
    return "Nothing is flagged for your attention right now — you're clear."


def _handle_late_query(user, msg_lower=None):
    from apps.ai.cos_event_engine import active_events, PAST_DUE, RECURRING_PROBLEM
    evs = active_events(user)
    late = [e for e in evs if e['category'] in (PAST_DUE, RECURRING_PROBLEM)]
    if late:
        def _label(e):
            return e['title'] + (" — recurring"
                                 if e['category'] == RECURRING_PROBLEM else "")
        return "You're late on:\n" + _evt_bullets(_label(e) for e in late[:6])
    overdue, _, _ = _execution_actions(user)  # fallback
    if overdue:
        return "You're late on:\n" + _evt_bullets(overdue[:6])
    return "You're not late on anything tracked right now — nicely done."


def _handle_upcoming_query(user, msg_lower=None):
    from apps.ai.cos_event_engine import (
        active_events, APPROACHING, DUE_NOW, STRATEGIC_RISK)
    evs = active_events(user)
    appr = [e for e in evs if e['category'] == APPROACHING]
    due = [e for e in evs if e['category'] == DUE_NOW]
    focus = [e for e in evs if e['category'] == STRATEGIC_RISK]
    items = [e['title'] for e in (due + appr)]
    if items or focus:
        out = ("Coming up:\n" + _evt_bullets(items[:6])) if items \
            else "Nothing operational is queued up shortly."
        if focus:
            out += (f"\n\nStrategically, {focus[0]['domain']} remains your "
                    f"highest-leverage focus.")
        return out
    _, _, upcoming = _execution_actions(user)  # fallback
    if upcoming:
        return "Coming up:\n" + _evt_bullets(upcoming[:6])
    return "Nothing is coming up in your tracked items right now."


# ── CoS REASONING MODES (2026-06-21) — one brain, distinct projections. ──
# Each mode reads the SAME unified state (build_cos_intelligence + the event
# stream) and answers a DIFFERENT executive question, so status / trajectory /
# direction / risk / opportunity / decision / pattern / blind-spot / constraint
# never collapse to one string. Only the BROKEN or MISSING modes are mapped here
# — biggest_win/opportunity, highest-leverage coaching, accountability and pace
# keep their existing (already-distinct) renderers.
_COS_MODE_PHRASES = {
    'trajectory': ('trajectory', 'where am i headed', 'where am i going',
                   'headed in the right'),
    'direction': ('moving in the right direction', 'right direction',
                  'on the right path', 'going the right way'),
    'prioritization_today': ('focus on today', 'focus today',
                             'what should i do today', 'priority today',
                             'most important thing today', 'focus on right now'),
    'prioritization': ('focus on this week', 'focus this week',
                       'what should i prioritize', 'what should i prioritise',
                       'what deserves my attention', 'what deserves attention',
                       'where should i put my energy'),
    'risk': ('biggest risk', 'what concerns you most', 'what concerns you',
             'what could hurt me', 'what worries you', 'what should i worry about',
             'what is my biggest risk', "what's my biggest risk"),
    'opportunity_soft': ('gives you confidence', 'what could help me',
                         'most optimistic about', 'what makes you optimistic'),
    'decision': ('what would you do if you were me', 'if you were me',
                 'in my shoes', 'what would you do in my'),
    'pattern': ('what patterns do you see', 'what patterns', 'recurring theme',
                'recurring themes', 'what trends do you see'),
    'blindspot': ('what am i ignoring', 'what am i not seeing', 'what am i missing',
                  'area of my life needs attention', 'area needs attention',
                  'what am i overlooking', 'blind spot', 'blindspot'),
    'bottleneck': ('next bottleneck', 'bottleneck', 'what comes after',
                   'what is next after'),
    'constraint': ('what is holding me back', "what's holding me back",
                   'where am i stuck', 'what is limiting me',
                   "what's limiting me"),
    'progress': ('where am i making progress', 'where am i progressing',
                 'where am i winning'),
    'stop': ('what should i stop doing', 'what should i stop', 'should i stop'),
    'start': ('what should i start doing', 'what should i start'),
    'honest': ('honest assessment', 'give it to me straight', 'be honest with me',
               'your honest take', 'brutal assessment'),
}
_COS_THIN = ("I don't have enough grounded standing signal to give you that read "
             "yet — keep logging and the picture will fill in.")


def _cos_mode_for(msg_lower):
    m = msg_lower or ''
    for mode, phrases in _COS_MODE_PHRASES.items():
        if any(p in m for p in phrases):
            return mode
    return None


def _render_cos_mode(user, mode):
    """Render a distinct executive answer for `mode` from ONE shared state."""
    from apps.ai.cos_intelligence import build_cos_intelligence
    from apps.ai.cos_event_engine import (
        active_events, STRATEGIC_RISK, STRATEGIC_OPPORTUNITY, MAJOR_WIN,
        PAST_DUE, RECURRING_PROBLEM)
    intel = build_cos_intelligence(user) or {}
    events = active_events(user)
    overall = intel.get('overall')
    pace_n = intel.get('goal_pace_narrative')
    gp = intel.get('goal_pace') or {}
    eff = intel.get('recommendation_effectiveness')
    R = [e for e in events if e['category'] == STRATEGIC_RISK]
    O = [e for e in events if e['category'] == STRATEGIC_OPPORTUNITY]
    W = [e for e in events if e['category'] == MAJOR_WIN]
    OD = [e for e in events if e['category'] in (PAST_DUE, RECURRING_PROBLEM)]
    REC = [e for e in events if e['category'] == RECURRING_PROBLEM
           or e.get('occurrence_count', 1) >= 3]
    pace = gp.get('current_pace_lb_wk')

    def j(lst, n=2):
        return "; ".join(e['title'] for e in lst[:n])

    if mode == 'trajectory':
        parts = []
        if pace_n:
            parts.append(f"Where you're headed: {pace_n}")
        if W:
            parts.append(f"The momentum is real — {W[0]['title'].lower()}.")
        if R:
            parts.append(f"The weak point in that trajectory is {R[0]['domain']}: "
                         f"{R[0]['message']}")
        if gp.get('target_passed') or gp.get('on_pace') is False:
            parts.append("Net read: you're moving the right way, just slower than "
                         "your original plan — the lever is the date or the pace, "
                         "not your effort.")
        return " ".join(parts) or overall or _COS_THIN

    if mode == 'direction':
        if not (W or R or pace_n):
            return overall or _COS_THIN
        good = bool(W) or (pace or 0) > 0
        parts = ["Overall, yes." if (good and R) else
                 ("Yes — clearly." if good else "Honestly, not yet.")]
        if W:
            cap = f"You're proving you can do this — {W[0]['title'].lower()}"
            if any(e['domain'] == 'medication' for e in O):
                cap += ", and you're holding your medication adherence steady"
            parts.append(cap + ".")
        if R:
            parts.append(f"What concerns me is the opposite move on {R[0]['domain']}: "
                         f"{R[0]['message']}")
        if gp.get('target_passed') or gp.get('on_pace') is False:
            parts.append("At this pace you'll likely still reach the goal — just "
                         "not on the timeline you originally set.")
        if R:
            push = W[0]['domain'] if W else "the number"
            parts.append(f"If I were prioritising your next move, I'd put less "
                         f"effort into pushing {push} further and more into "
                         f"protecting {R[0]['domain']}, so the progress you've "
                         f"made stays sustainable.")
        return " ".join(parts)

    if mode == 'prioritization':
        # WEEK = strategic-first. Leverage = the CONSTRAINT to fix (risk).
        parts = []
        lead = R[0] if R else (O[0] if O else None)
        if lead:
            parts.append(f"This week, put your energy into {lead['domain']}: "
                         f"{lead['message']}")
        if OD:
            parts.append(f"Operationally, clear what's slipping: {j(OD, 3)}.")
        if W:
            parts.append(f"And protect what's already working ({W[0]['title'].lower()}) "
                         f"— don't trade it away chasing the next gain.")
        return " ".join(parts) or overall or _COS_THIN

    if mode == 'prioritization_today':
        # TODAY = immediate-first: clear what's slipping NOW, then tie to the
        # strategic constraint. Distinct from the weekly strategic-first read.
        parts = []
        if OD:
            parts.append(f"Today, knock out what's already slipping: {j(OD, 3)}.")
        else:
            parts.append("Nothing operational is overdue today — you're current.")
        if R:
            parts.append(f"And keep it tied to the one thing that matters most — "
                         f"{R[0]['domain']} ({R[0]['title'].lower()}).")
        return " ".join(parts) or overall or _COS_THIN

    if mode == 'risk':
        if R:
            out = f"What concerns me most: {R[0]['message']}"
            if len(R) > 1:
                out += f" I'm also watching {R[1]['domain']} ({R[1]['title'].lower()})."
            return out
        if gp.get('target_passed') or gp.get('on_pace') is False:
            return f"Your main strategic risk is the goal trajectory. {pace_n}"
        return ("Honestly, nothing strategic is flashing red right now — your "
                "trend is working. " + (overall or "")).strip()

    if mode == 'opportunity_soft':
        parts = []
        if O:
            parts.append(f"Your biggest opening: {O[0]['message']}")
        if W:
            parts.append(f"What gives me confidence: {j(W, 2)}.")
        return " ".join(parts) or overall or _COS_THIN

    if mode == 'decision':
        move = R[0] if R else (O[0] if O else None)
        parts = ["If I were you, here's where I'd put my energy:"]
        if move:
            parts.append(f"the highest-leverage move is {move['domain']} — "
                         f"{move['message']}")
        if gp.get('target_passed') or gp.get('on_pace') is False:
            parts.append(f"I'd also reset the weight plan to a realistic date — {pace_n}")
        if W:
            parts.append(f"And keep protecting the win that proves the system "
                         f"works: {W[0]['title'].lower()}.")
        return " ".join(parts) if len(parts) > 1 else (overall or _COS_THIN)

    if mode == 'pattern':
        if REC:
            return (f"The recurring theme I keep flagging: {j(REC, 3)}. "
                    + (eff or "")).strip()
        if eff:
            return f"The pattern across our conversations: {eff}"
        if R:
            return (f"The throughline lately is {R[0]['domain']} — "
                    f"{R[0]['title'].lower()}.")
        return "No strong recurring pattern yet — I'll flag one the moment it forms."

    if mode == 'blindspot':
        if R:
            ride = (W[0]['title'].lower() if W else "your progress")
            return (f"What you may be under-weighting: {j(R, 2)}. It's easy to "
                    f"ride the wins ({ride}) and let this quietly slide.")
        if gp.get('target_passed'):
            return (f"The blind spot: your weight target date has passed and the "
                    f"plan hasn't been reset. {pace_n}")
        return ("I don't see an obvious blind spot right now — but ask again as "
                "the week unfolds and I'll keep watching.")

    if mode == 'constraint':
        c = R[0] if R else (O[0] if O else None)
        if c:
            return f"The thing holding you back most is {c['domain']}: {c['message']}"
        return overall or _COS_THIN

    if mode == 'bottleneck':
        # Forward-looking: the CURRENT constraint, then what's next behind it.
        if R:
            out = (f"Right now the bottleneck is {R[0]['domain']} — "
                   f"{R[0]['title'].lower()}.")
            if len(R) > 1:
                out += (f" Clear that and the next one waiting is {R[1]['domain']} "
                        f"({R[1]['title'].lower()}).")
            elif pace_n and (gp.get('target_passed') or gp.get('on_pace') is False):
                out += f" After that, the next thing to address is your goal pace — {pace_n}"
            return out
        return overall or _COS_THIN

    if mode == 'progress':
        if W or O:
            parts = ["Where you're making real progress: " + j(W + O, 3) + "."]
            parts.append("That matters more than the number itself — it proves "
                         "you can hold a plan and move the metric, which is the "
                         "hard part.")
            if R:
                parts.append(f"Just don't let it mask the one area that isn't "
                             f"moving: {R[0]['domain']} — {R[0]['title'].lower()}.")
            return " ".join(parts)
        return ("Progress is thin in the tracked data this week — let's change "
                "that. " + (overall or "")).strip()

    if mode == 'stop':
        if R:
            return (f"If you're going to stop something, ease off whatever is "
                    f"feeding {R[0]['domain']}'s slide — {R[0]['title'].lower()}. "
                    f"That's costing you more than it's giving.")
        return ("Nothing's clearly worth stopping right now — your habits are "
                "mostly working for you.")

    if mode == 'start':
        s = R[0] if R else (O[0] if O else None)
        if s:
            return (f"The one thing worth starting: protect {s['domain']} — "
                    f"{s['title'].lower()}. That's your highest-leverage new habit.")
        return overall or _COS_THIN

    if mode == 'honest':
        parts = []
        if overall:
            parts.append(overall)
        if R:
            parts.append(f"Straight talk — your real exposure is {R[0]['domain']}: "
                         f"{R[0]['message']}")
        elif pace_n:
            parts.append(pace_n)
        if W:
            parts.append(f"Credit where it's due — {W[0]['title'].lower()}.")
        if R:
            parts.append(f"If you do one thing, protect {R[0]['domain']}; it's the "
                         f"hinge the rest of your goals swing on.")
        return " ".join(parts) or _COS_THIN

    return None


def _handle_executive_query(user, msg_lower=None):
    """Answer an executive-lens question from build_executive_summary — the one
    executive reasoning layer the dashboard uses. Read-only over cached SAE
    state; never raises; honest when a lens has no grounded signal yet."""
    # CoS reasoning-mode layer first — distinct projection per mode (status /
    # trajectory / risk / opportunity / decision / blind-spot / …) so executive
    # questions never collapse to one answer.
    _mode = _cos_mode_for(msg_lower)
    if _mode:
        try:
            _mode_resp = _render_cos_mode(user, _mode)
            if _mode_resp:
                return _mode_resp
        except Exception:
            logger.warning("cos mode render failed (%s)", _mode, exc_info=True)
    try:
        from apps.core.cos_briefing import build_executive_summary
        es = build_executive_summary(user) or {}
    except Exception:
        logger.warning("executive route failed", exc_info=True)
        return None
    lens = _executive_lens_for(msg_lower)
    lenses = es.get('executive_lenses') or {}

    # Single-signal lenses read the differentiated top-level fields.
    _SINGLE = {
        'biggest_win': "a clear standing win",
        'biggest_improvement': "a clear improvement",
        'biggest_decline': "a clear decline",
        'most_important_trend': "a single most-important trend",
    }
    if lens in _SINGLE:
        msg = _exec_field_msg(es.get(lens))
        if msg:
            return msg
        return (f"I don't have enough grounded standing signal to name "
                f"{_SINGLE[lens]} right now — keep logging and I'll surface it "
                f"as the data builds.")

    # Cross-domain Chief-of-Staff COACHING — synthesise what's helping, what's
    # hurting, and the highest-leverage move from the executive lenses (which
    # already reason across weight / sleep / glucose / medication / faith /
    # relationships). Coaches, doesn't report. (2026-06-21)
    if lens == 'coaching':
        # Record the constraint Beth is steering toward, so effectiveness can be
        # judged later (idempotent, never breaks the answer).
        try:
            from apps.ai.cos_recommendations import record_top_recommendation
            record_top_recommendation(user)
        except Exception:
            logger.debug("record_top_recommendation failed", exc_info=True)
        return _render_cos_coaching(es, lenses)

    # Differentiated synthesis/leverage lenses read executive_lenses (the layer
    # already built). Opportunity reads the LEVERAGE-framed string, NOT the
    # legacy event field. (2026-06-19 render-consumption fix.)
    _LENS_KEY = {
        'biggest_opportunity': ('opportunity', "a clear opportunity"),
        'protect': ('protect', "what's most worth protecting"),
        'story': ('story', "the story your data tell"),
        'overall': ('overall', "an overall read"),
        'briefing': ('chief_of_staff_briefing', "a strategic briefing"),
    }
    key, label = _LENS_KEY.get(lens, ('overall', "an overall read"))
    msg = lenses.get(key)
    if msg:
        # STATUS: a net verdict alone is a dashboard. Add the cross-domain
        # implication + the single next move from the event stream.
        if key == 'overall':
            return _cos_status_enrich(user, msg)
        return msg
    return (f"I don't have enough grounded standing signal to give you "
            f"{label} yet — keep logging and the picture will fill in.")


def _cos_status_enrich(user, base):
    """Turn a net status verdict into a CoS read: headline + the one thing that
    could undo it + a single recommendation. Reuses the event stream; never
    raises; returns base unchanged if there's nothing grounded to add."""
    try:
        from apps.ai.cos_event_engine import (
            active_events, STRATEGIC_RISK, MAJOR_WIN)
        evs = active_events(user)
        R = [e for e in evs if e['category'] == STRATEGIC_RISK]
        W = [e for e in evs if e['category'] == MAJOR_WIN]
    except Exception:
        return base
    parts = [base] if base else []
    if W and R:
        parts.append(f"The headline is that you're proving the plan works — "
                     f"{W[0]['title'].lower()} — but {R[0]['domain']} is the thing "
                     f"that could quietly undo it.")
    elif R:
        parts.append(f"The thing I'd watch is {R[0]['domain']} — {R[0]['title'].lower()}.")
    if R:
        parts.append(f"My one piece of advice: protect {R[0]['domain']} now, "
                     f"before it starts dragging on everything else.")
    return " ".join(parts) if len(parts) > 1 else base


# Sleep COACHING intent — "how to improve my sleep" — distinct from a STATUS
# question ("how did I sleep"). Routing keys on INTENT, not just the "sleep"
# keyword (F4, 2026-06-17). Now delegates category recognition to the shared
# classifier above (Phase 0); behaviour is unchanged for sleep.
def _is_sleep_coaching_request(msg_lower):
    """True when the user asks HOW TO IMPROVE sleep (coaching), not status."""
    if not msg_lower or 'sleep' not in msg_lower:
        return False
    return classify_query_intent(msg_lower) == 'coaching'


def _match_sleep_coaching_query(msg_lower):
    """Match sleep coaching/action requests (checked BEFORE the status route)."""
    if _is_future_tense_query(msg_lower):
        return False
    return _is_sleep_coaching_request(msg_lower)


def _handle_sleep_coaching_query(user, msg_lower=None):
    """Deterministic sleep coaching when sleep is the identified constraint,
    from the existing HealthTrendAnalyzer (severity-scored, grounded). Returns
    None when sleep isn't the primary constraint → falls through to the LLM
    coaching path (per approved F4 plan). Never returns status-only metrics."""
    try:
        from apps.core.utils import get_user_today
        from apps.health.services.trend_analyzer import HealthTrendAnalyzer
        res = HealthTrendAnalyzer.analyze(user, get_user_today(user)) or {}
        coaching = res.get("coaching") or {}
        if coaching.get("primary_constraint") == "sleep":
            parts = [coaching.get("insight"), coaching.get("primary_action"),
                     coaching.get("secondary_action")]
            msg = " ".join(p for p in parts if p)
            if msg.strip():
                return msg
    except Exception:
        logger.debug("sleep coaching route failed", exc_info=True)
    return None  # not the constraint / no data → LLM gives general sleep tips


# Sleep DIAGNOSTIC intent — "why is my sleep holding me back?" / "what's
# causing my poor sleep?" — recognized as a CATEGORY (cause-seeking), not the
# literal example phrases (2026-06-17). Coaching (action verbs) takes precedence
# when both appear ("why is my sleep bad and how do I fix it" → coaching); the
# shared classifier enforces that precedence (Phase 0).
def _is_sleep_diagnostic_request(msg_lower):
    """True for a cause-seeking ('why/what's causing/what's limiting') question
    about sleep — the DIAGNOSTIC category. Coaching wins when an action verb is
    present (classifier precedence: coaching is checked before diagnostic)."""
    if not msg_lower or 'sleep' not in msg_lower:
        return False
    return classify_query_intent(msg_lower) == 'diagnostic'


def _match_sleep_diagnostic_query(msg_lower):
    """Match sleep diagnostic/root-cause requests (before coaching & status)."""
    if _is_future_tense_query(msg_lower):
        return False
    return _is_sleep_diagnostic_request(msg_lower)


def _handle_sleep_diagnostic_query(user, msg_lower=None):
    """Grounded sleep root-cause: names the actual limiting factor(s) from real
    signals (duration deficit, quality-vs-quantity, consistency, trend) via
    HealthTrendAnalyzer. NO speculative psychology — only signals that exist.
    Honest uncertainty when there isn't enough data (never falls to a guess)."""
    try:
        from apps.core.utils import get_user_today
        from apps.health.services.trend_analyzer import HealthTrendAnalyzer
        res = HealthTrendAnalyzer.analyze(user, get_user_today(user)) or {}
        rolling = res.get("rolling_7d") or {}
        avg = rolling.get("sleep_hours")
        if avg is None:
            return (
                "I don't have enough recent sleep data to pinpoint what's "
                "holding your sleep back yet — log a few more nights and I can "
                "break down the limiting factors."
            )
        avg = float(avg)
        weaknesses = res.get("weaknesses") or []
        trends = res.get("trends") or {}
        factors = []
        if avg < 7:
            gap_min = round((7.0 - avg) * 60)
            factors.append(
                f"the main constraint is **duration** — you're averaging "
                f"{avg:.1f}h against a 7-hour target (about {gap_min} minutes "
                f"short each night)"
            )
        else:
            factors.append(f"your sleep duration is on target ({avg:.1f}h)")
        # Quality vs quantity — grounded only when a quality score exists.
        try:
            from apps.core.ai_state.state_engine import get_module_state
            _h = get_module_state(user, 'health') or {}
            q = _h.get('sleep_quality_avg_7d')
            if q is None:
                q = _h.get('sleep_last_night_quality')
            if q is not None:
                q = float(q)
                if avg < 7 and q >= 80:
                    factors.append(
                        f"quality isn't the issue (score ~{int(q)}) — it's quantity")
                elif q < 70:
                    factors.append(f"sleep quality is also low (score ~{int(q)})")
        except Exception:
            pass
        if any('inconsistent' in (w or '').lower() and 'sleep' in (w or '').lower()
               for w in weaknesses):
            factors.append("your nightly duration has also been inconsistent recently")
        if trends.get('sleep') == 'declining':
            factors.append("and the trend is declining")
        return "Looking at your sleep data, " + "; ".join(factors) + "."
    except Exception:
        logger.debug("sleep diagnostic route failed", exc_info=True)
        return (
            "I don't have enough recent sleep data to diagnose what's holding "
            "your sleep back yet."
        )


def _match_sleep_query(msg_lower):
    """Match direct sleep STATUS questions (coaching/diagnostic handled separately)."""
    if _is_future_tense_query(msg_lower):
        return False
    # Coaching (action) and diagnostic (cause-seeking) are NOT status — let
    # their routes handle them so neither returns bare metrics (F4 + diagnostic).
    if _is_sleep_coaching_request(msg_lower) or _is_sleep_diagnostic_request(msg_lower):
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


_SLEEP_SUMMARY_ANCHORS = (
    'this week', 'average', 'avg', 'how has', 'how have', 'lately',
    'trend', 'past week', 'last 7', 'weekly', 'on average', 'been sleeping',
)


def _handle_sleep_query(user, msg_lower=None):
    """Deterministic sleep response from SAE state.

    Latest-vs-summary discipline:
      - "how did I sleep" / "last night" → LAST NIGHT event first, with the
        7-day average as context.
      - "this week" / "average" / "how have I been sleeping" → 7-day summary.
    Reads canonical SAE fields; never a direct DB query.
    """
    try:
        from apps.ai.cognitive_mode.health_truth import ensure_health_fresh
        ensure_health_fresh(user)
    except Exception:
        pass
    from apps.core.ai_state.state_engine import get_module_state
    health = get_module_state(user, 'health') or {}

    avg_min = health.get('sleep_avg_duration_7d')
    avg_hrs = round(float(avg_min) / 60, 1) if avg_min is not None else None
    trend = health.get('sleep_trend', '')
    trend_str = {
        'improving': ' and improving',
        'declining': ' and declining',
        'stable': ' and consistent',
    }.get(trend, '')

    m = msg_lower or ''
    summary_intent = any(a in m for a in _SLEEP_SUMMARY_ANCHORS)

    # ── Summary path ("how has my sleep been this week?") ──
    if summary_intent:
        if avg_hrs is None:
            return None
        resp = f"You're averaging **{avg_hrs} hours** of sleep this week{trend_str}."
        resp += (" That's below the 7-hour target." if avg_hrs < 7
                 else " That's in a solid range.")
        return resp

    # ── Latest path ("how did I sleep?" / "last night") ──
    last_hrs = health.get('sleep_last_night_hours')
    last_q = health.get('sleep_last_night_quality')
    last_label = "last night"
    if last_hrs is None:
        # No-abstain (Phase 1, 2026-06-19): the SAE snapshot hasn't captured the
        # latest night — read the newest SleepEntry LIVE (the same row the sleep
        # page shows) BEFORE degrading to an average. A "last night" question
        # must never be answered with the 7-day mean.
        try:
            from apps.health.models import SleepEntry
            from apps.core.utils import get_user_today
            se = (SleepEntry.objects.filter(user=user)
                  .order_by('-sleep_date', '-created_at').first())
            if se and se.total_duration_minutes:
                last_hrs = round(float(se.total_duration_minutes) / 60, 1)
                last_q = se.quality_score
                _days = (get_user_today(user) - se.sleep_date).days
                last_label = ("last night" if _days <= 1
                              else f"your most recent night ({se.sleep_date:%b %d})")
        except Exception:
            logger.warning("sleep live fallback failed", exc_info=True)
    if last_hrs is None:
        # Truly no sleep data — honest, never abstain to the LLM.
        if avg_hrs is None:
            return ("I don't see any sleep logged yet — log a night and I can "
                    "break it down for you.")
        return (f"I don't have last night's sleep logged yet. Your 7-day "
                f"average is **{avg_hrs} hours**.")

    resp = f"You slept **{last_hrs} hours** {last_label}"
    if last_q is not None:
        resp += f" with a quality score of **{last_q}**"
    resp += "."
    if last_q is not None and last_q >= 85:
        resp += " That was a solid night."
    elif last_hrs < 6:
        resp += " That was a short night."
    if avg_hrs is not None:
        resp += (f" Your 7-day average is {avg_hrs} hours"
                 + (", still below your 7-hour target." if avg_hrs < 7
                    else " — right on target."))
    return resp


# ── Glucose query routing — Layer B trust fix (2026-06-07) ──────────
#
# Hard split between event-style ("what was my last reading?") and
# summary-style ("how is my glucose this week?") questions. LATEST
# wins on overlap so a question like "what was my last glucose" is
# never answered with the 7-day average.
#
# Ambiguity rules (locked by test_glucose_routing.py):
#   "this week" / "this month" / "average" / "trend" / "a1c" /
#   "time in range" / "how is" / "how have" → SUMMARY anchors (win
#   even when "glucose" appears).
#   "last" / "latest" / "most recent" / "right now" / "current" /
#   "what time" / "when was" → LATEST anchors.
#   Bare "my glucose" / "my blood sugar" → SUMMARY (conservative
#   default — never claims to be latest).

_GLUCOSE_LATEST_TRIGGERS = frozenset([
    "last glucose", "last blood sugar", "last reading",
    "latest glucose", "latest blood sugar", "latest reading",
    "most recent glucose", "most recent blood sugar",
    "most recent reading",
    "what was my last", "what was the last",
    "when was my glucose", "when was my last glucose",
    "what time was my glucose", "what time was my last reading",
    "what time was that reading", "what time was that",
    "glucose right now", "blood sugar right now",
    "current glucose", "current blood sugar",
])

# Phrases that, when present, force SUMMARY interpretation regardless
# of any LATEST trigger that might also appear. Example:
# "what was my glucose this week" → "this week" wins → SUMMARY.
_GLUCOSE_SUMMARY_ANCHORS = frozenset([
    "this week", "this month", "last week", "last month",
    "average", "trend", "a1c", "time in range",
    "how is my glucose", "how is my blood sugar",
    "how have my numbers", "how have i been",
    "weekly", "monthly",
    # Concept/timeframe anchors so fasting / wake-up / multi-month glucose
    # questions route deterministically to the grounded-proxy summary handler
    # instead of falling through to the LLM (the "fasting over several months"
    # trust gap). Each still requires a glucose token via the catch-all.
    "fasting", "wake up", "wake-up", "waking", "overnight", "months",
])

# Markers that tell us WHICH glucose concept the user asked for, so the
# handler returns the closest grounded metric (or an explicit proxy) instead
# of silently substituting the all-day average.
_GLUCOSE_FASTING_MARKERS = (
    "fasting", "fasted", "before eating", "before breakfast",
    "empty stomach", "before food",
)
_GLUCOSE_WAKEUP_MARKERS = (
    "wake up", "wake-up", "waking", "when i wake", "after i wake",
    "shortly after i wake", "first thing", "morning glucose",
    "glucose in the morning", "overnight", "before i get up",
)


def _glucose_concept(msg_lower):
    """Classify the glucose concept asked about: fasting | wake_up | general."""
    if any(m in msg_lower for m in _GLUCOSE_FASTING_MARKERS):
        return "fasting"
    if any(m in msg_lower for m in _GLUCOSE_WAKEUP_MARKERS):
        return "wake_up"
    return "general"


# User-facing phrase for each concept, used in proxy acknowledgment copy.
_GLUCOSE_CONCEPT_PHRASE = {
    "fasting": "fasting glucose",
    "wake_up": "wake-up glucose",
    "general": "glucose",
}

_GLUCOSE_SUMMARY_TRIGGERS = frozenset([
    "what's my glucose", 'whats my glucose', 'what is my glucose',
    'my glucose', 'glucose level', 'blood sugar',
    'glucose average', 'glucose this week', 'glucose this month',
    'glucose trend', 'weekly glucose', 'monthly glucose',
    'estimated a1c', 'a1c', 'time in range',
    'show my glucose', 'glucose check', 'glucose stats',
    'my blood sugar', "what's my blood sugar", 'whats my blood sugar',
    'how is my glucose', 'how is my blood sugar',
    'how have my numbers been', 'how have my numbers',
])


# ─────────────────────────────────────────────────────────────────────
# Glucose DIAGNOSTIC intent (Phase 2a, 2026-06-18) — "why is my fasting
# glucose elevated?" / "what's causing my blood sugar to be high overnight?".
# A cause-seeking question, NOT a status lookup. The trust bug: these matched
# the glucose STATUS route (glucose token + "fasting"/"overnight" summary
# anchor) and returned a bare number. Recognized as the DIAGNOSTIC CATEGORY via
# the shared classifier (mirrors sleep). Status/latest now exclude it.
# ─────────────────────────────────────────────────────────────────────
def _has_glucose_token(msg_lower):
    return bool(msg_lower) and (
        'glucose' in msg_lower or 'blood sugar' in msg_lower or 'a1c' in msg_lower
    )


def _is_glucose_diagnostic_request(msg_lower):
    """True for a cause-seeking ('why/what's causing/what's driving') question
    about glucose — the DIAGNOSTIC category. Keys on the shared classifier."""
    if not _has_glucose_token(msg_lower):
        return False
    return classify_query_intent(msg_lower) == 'diagnostic'


def _match_glucose_diagnostic_query(msg_lower):
    """Match glucose diagnostic/root-cause requests (before status & latest)."""
    if _is_future_tense_query(msg_lower):
        return False
    return _is_glucose_diagnostic_request(msg_lower)


def _match_glucose_latest_query(msg_lower):
    """Match event-style ("what was my LAST reading?") glucose queries."""
    if _is_future_tense_query(msg_lower):
        return False
    # Diagnostic (cause-seeking) is NOT a latest-reading lookup.
    if _is_glucose_diagnostic_request(msg_lower):
        return False
    if any(e in msg_lower for e in ('log', 'record', 'enter')):
        return False
    # Summary anchors override LATEST triggers — "what was my glucose
    # THIS WEEK" is a summary question even though it contains "last".
    if any(a in msg_lower for a in _GLUCOSE_SUMMARY_ANCHORS):
        return False
    return any(p in msg_lower for p in _GLUCOSE_LATEST_TRIGGERS)


def _match_glucose_query(msg_lower):
    """Match summary-style glucose questions (averages, A1C, TIR).

    Kept under the original name so any external caller continues to
    work. Latest-style queries are matched separately by
    ``_match_glucose_latest_query`` and dispatched first.
    """
    if _is_future_tense_query(msg_lower):
        return False
    # Diagnostic (cause-seeking) is NOT a status summary — let its dedicated
    # route answer so "why is my fasting glucose elevated" never returns a
    # bare number (Phase 2a).
    if _is_glucose_diagnostic_request(msg_lower):
        return False
    # If the message is a LATEST-style question, leave it for the
    # latest matcher — don't double-match.
    if _match_glucose_latest_query(msg_lower):
        return False
    _EXCLUDE = ['log ', 'record ', 'enter ']
    if any(e in msg_lower for e in _EXCLUDE):
        return False
    if any(p in msg_lower for p in _GLUCOSE_SUMMARY_TRIGGERS):
        return True
    # Catch-all: any summary anchor + any glucose/blood-sugar token
    # is a summary question, even if the exact phrase isn't in the
    # trigger list. Examples: "average glucose", "a1c trend",
    # "weekly blood sugar".
    has_glucose_token = (
        "glucose" in msg_lower
        or "blood sugar" in msg_lower
        or "a1c" in msg_lower
    )
    if has_glucose_token and any(
        a in msg_lower for a in _GLUCOSE_SUMMARY_ANCHORS
    ):
        return True
    return False


def _handle_glucose_latest_query(user):
    """Return the deterministic LATEST glucose event response.

    Routes through the canonical snapshot — NEVER queries GlucoseEntry
    directly. Returns the trust-preserving copy when only summary data
    is available. Returns ``None`` only when NO glucose data exists at
    all (so the LLM can take over with a generic empty-state answer if
    appropriate).
    """
    try:
        from apps.core.ai_events.adapters.glucose import get_latest_message
        return get_latest_message(user)
    except Exception:
        logger.warning("Glucose latest handler failed", exc_info=True)
        return None


def _handle_glucose_diagnostic_query(user, msg_lower=None):
    """Grounded glucose root-cause: explains an elevated / abnormal level from
    the actual glucose SUMMARY signals ONLY — trend direction (7d vs 30d),
    overnight (fasting-proxy) level and whether the elevation is concentrated
    overnight, time-in-range, and a sample-size caveat. NO speculative
    physiology — never invents stress / hormones / dawn-phenomenon as a cause.
    Honest uncertainty when the grounded signal is too thin to explain a cause
    (never returns a bare number / status summary)."""
    insufficient = (
        "I don't have enough grounded glucose signal to explain the cause "
        "confidently. Log a few more readings over a week or so — including "
        "some overnight — and I can break down what's driving it."
    )
    try:
        from apps.health.services.glucose_snapshot import build_glucose_summary
        summary = build_glucose_summary(user)
    except Exception:
        logger.warning("glucose diagnostic route failed", exc_info=True)
        return insufficient

    if not summary:
        return insufficient

    avg7 = summary.get("average_7d")
    avg30 = summary.get("average_30d")
    trend = summary.get("trend_7d_vs_30d") or ""
    tir7 = summary.get("time_in_range_pct_7d")
    overnight = summary.get("overnight_avg")
    count90 = summary.get("reading_count_90d") or 0
    concept = _glucose_concept(msg_lower or "")
    fasting_ctx = concept in ("fasting", "wake_up")

    # Without a grounded recent level there's nothing to explain.
    if avg7 is None and overnight is None:
        return insufficient

    # The backbone of a "why is it elevated" answer is the grounded TREND. With
    # no trend signal we cannot attribute a CAUSE — be honest, give the grounded
    # context, and explicitly decline to claim causation.
    if not trend:
        ctx = []
        if avg7 is not None:
            ctx.append(f"your 7-day average is {avg7} mg/dL")
        if fasting_ctx and overnight is not None:
            ctx.append(
                f"your overnight readings (midnight–6am, the closest grounded "
                f"signal to fasting) average {overnight:.0f} mg/dL")
        if tir7 is not None:
            ctx.append(f"you're in range (70–180) {tir7:.0f}% of the time")
        if not ctx:
            return insufficient
        return (
            "I can see " + ", ".join(ctx) + ", but I don't have a strong enough "
            "trend signal yet to pin down WHY it's elevated with confidence. A "
            "bit more data — especially overnight readings — would let me explain "
            "the driver rather than just the level."
        )

    # Trend present → grounded explanation.
    factors = []
    if trend == "worsening" and avg7 is not None and avg30 is not None:
        factors.append(
            f"the recent direction is upward — your 7-day average ({avg7} mg/dL) "
            f"is running above your 30-day average ({avg30} mg/dL)")
    elif trend == "improving" and avg7 is not None and avg30 is not None:
        factors.append(
            f"the recent trend is actually downward, not up — your 7-day average "
            f"({avg7} mg/dL) is below your 30-day average ({avg30} mg/dL)")
    elif trend == "stable" and avg7 is not None:
        factors.append(
            f"your levels have been steady (7-day average {avg7} mg/dL), so this "
            f"reads as your baseline rather than a recent spike")

    # Overnight / fasting — grounded, and whether elevation is concentrated there.
    if overnight is not None:
        if fasting_ctx:
            factors.append(
                f"your overnight average (midnight–6am, the closest grounded "
                f"fasting signal) is {overnight:.0f} mg/dL")
        if avg7 is not None and (overnight - avg7) >= 8:
            factors.append(
                "and it's running higher overnight than during the day, so the "
                "elevation is concentrated in the fasting window")

    if tir7 is not None:
        factors.append(
            f"you're in range (70–180) {tir7:.0f}% of the time over the last week")

    if not factors:
        return insufficient

    caveat = ""
    if count90 < 14:
        caveat = (
            " One caveat: this is based on a small number of readings, so treat "
            "it as a provisional read rather than a firm cause.")

    return "Looking at your glucose data, " + "; ".join(factors) + "." + caveat


def _handle_glucose_query(user, msg_lower=None):
    """Build a deterministic glucose SUMMARY response from SAE state.

    2026-06-07: rewritten to route through the canonical glucose
    snapshot. The response is ALWAYS explicitly framed as average /
    trend / estimate — NEVER labels itself as "latest" or "most
    recent." That separation is the architectural fix locked at
    Layer A; this is the surface that enforces it at the router level.
    Falls back to the legacy SAE-keyed response only when the snapshot
    has nothing (true no-data case).

    2026-06-15 (grounded proxy): when the user asks for a SPECIFIC glucose
    concept (fasting / wake-up), answer with the closest grounded metric and
    EXPLICITLY acknowledge any proxy — never silently substitute the all-day
    average. The generic "how's my glucose this week" path is unchanged.
    """
    # Grounded-proxy path for concept-specific questions (fasting / wake-up).
    concept = _glucose_concept(msg_lower or "")
    if concept != "general":
        try:
            from apps.health.services.glucose_snapshot import (
                build_glucose_proxy_answer,
                render_glucose_proxy_message,
            )
            answer = build_glucose_proxy_answer(user, concept)
            if answer is not None:
                msg = render_glucose_proxy_message(
                    answer, _GLUCOSE_CONCEPT_PHRASE[concept],
                )
                if msg:
                    return msg
        except Exception:
            logger.warning("Glucose proxy handler failed", exc_info=True)
        # answer is None → no glucose data at all → fall through to generic.

    try:
        from apps.core.ai_events.adapters.glucose import get_summary_message
        from apps.health.services.glucose_snapshot import build_glucose_summary
        if build_glucose_summary(user) is not None:
            return get_summary_message(user)
    except Exception:
        logger.warning("Glucose summary snapshot failed", exc_info=True)

    # Legacy fallback — SAE flat keys. Preserved so no-data /
    # snapshot-error users still get a deterministic reply rather than
    # a generic "no data" string.
    from apps.core.ai_state.state_engine import get_module_state
    health = get_module_state(user, 'health') or {}
    glucose = health.get('glucose_avg_7d')
    if glucose is None:
        return None
    response = f"Your **7-day average glucose** is **{int(glucose)} mg/dL**."
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
        rate_pct = round(adherence_7d * 100)
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

    # ── Recommendation tracking + effectiveness (outcome engine, 2026-06-21).
    # "What advice have you given me?" / "is your recommendation working?"
    register_data_route('recommendation_list_query', _match_recommendation_list_query, _handle_recommendation_list_query, 'cos')
    register_data_route('rec_effectiveness_query', _match_rec_effectiveness_query, _handle_rec_effectiveness_query, 'cos')
    register_data_route('goal_pace_query', _match_goal_pace_query, _handle_goal_pace_query, 'health')

    # ── Accountability (progress-over-time) — BEFORE domain status routes so
    # "have we made progress on my sleep?" gets a multi-week verdict, not a
    # single-night status. (2026-06-21)
    register_data_route('accountability_query', _match_accountability_query, _handle_accountability_query, 'health')

    # ── Summary-level routes (Truth Depth: SUMMARY) ──
    register_data_route('weight_query', _match_weight_query, _handle_weight_query, 'health')
    # Last-workout (event) MUST register before the aggregate workout route so
    # "what was my last workout" hits the latest-event handler, not the summary.
    register_data_route('last_workout_query', _match_last_workout_query, _handle_last_workout_query, 'health')
    register_data_route('workout_query', _match_workout_query, _handle_workout_query, 'health')
    # Sleep intent precedence: COACHING (action) → DIAGNOSTIC (cause-seeking) →
    # STATUS (metrics). Coaching/diagnostic must be checked BEFORE status so
    # neither returns bare metrics (F4 + diagnostic, 2026-06-17).
    register_data_route('sleep_coaching_query', _match_sleep_coaching_query, _handle_sleep_coaching_query, 'health')
    register_data_route('sleep_diagnostic_query', _match_sleep_diagnostic_query, _handle_sleep_diagnostic_query, 'health')
    register_data_route('sleep_query', _match_sleep_query, _handle_sleep_query, 'health')
    # 2026-06-18 (Phase 2a) — glucose DIAGNOSTIC ("why is my fasting glucose
    # elevated?") registered BEFORE the latest/summary status routes so a
    # cause-seeking question is answered with a grounded explanation, never a
    # bare number. Status/latest matchers exclude the diagnostic category.
    register_data_route(
        'glucose_diagnostic_query',
        _match_glucose_diagnostic_query,
        _handle_glucose_diagnostic_query,
        'health',
    )
    # 2026-06-07 — glucose LATEST event route registered BEFORE the
    # summary route so it's checked first. Latest-style questions
    # ("what was my last reading?", "what time?", "glucose right now")
    # MUST never fall into the summary handler.
    register_data_route(
        'glucose_latest_query',
        _match_glucose_latest_query,
        _handle_glucose_latest_query,
        'health',
    )
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
