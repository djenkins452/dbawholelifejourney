# ==============================================================================
# File: apps/ai/readiness_cache.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: CoS Readiness Cache — TTL-based, user-scoped context pre-cache
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-28
# ==============================================================================
"""
CoS Readiness Cache

Stores pre-computed cos_context in Django's cache framework (Redis in prod)
so the chat endpoint can skip rebuild when context is fresh.

Cache Strategy:
- Key: "cos_ctx:v1:{user_id}"
- TTL: 45 seconds (short enough to stay fresh, long enough to survive typing)
- Invalidation: explicit via invalidate(), or natural TTL expiry
- Thread-safe: Redis operations are atomic
- Never blocks: cache miss = rebuild (existing behavior)

Public API:
- get_cached_cos_context(user) -> dict | None
- set_cached_cos_context(user, context, ttl=45)
- invalidate_cos_context(user)
- get_readiness_state(user) -> str  ('cold'|'warming'|'ready'|'active')
- set_readiness_state(user, state)
- prewarm_cos_context(user) -> dict  (builds + caches + returns)
- track_active_user(user)
- get_active_user_ids() -> list[int]
- warm_db_connection() -> bool
"""

import logging
import time

from django.core.cache import cache
from django.db import connection

logger = logging.getLogger(__name__)

# Cache key prefixes
CONTEXT_KEY_PREFIX = "cos_ctx:v1"
STABLE_KEY_PREFIX = "cos_ctx:stable:v1"
DYNAMIC_KEY_PREFIX = "cos_ctx:dynamic:v1"
READINESS_KEY_PREFIX = "cos_ready:v1"
ACTIVE_USERS_KEY = "cos_active_users:v1"

# TTL constants (seconds)
# Extended from 45s→90s: profiling showed slow typists consistently missed the
# 45s window, causing full rebuilds. Event-based invalidation (see
# invalidate_cos_context_on_action) handles freshness instead of tight TTL.
CONTEXT_CACHE_TTL = 90       # CoS context cache lifetime (flat/dynamic)
STABLE_CACHE_TTL = 300       # 5 minutes — slowly-changing context components
DYNAMIC_CACHE_TTL = 90       # 90 seconds — fast-changing components
READINESS_STATE_TTL = 120    # Readiness state tracking
ACTIVE_USER_TTL = 300        # 5 minutes — users considered "active"

# Keys that belong in the stable layer (long TTL, rarely change)
STABLE_CONTEXT_KEYS = frozenset({
    'blueprint_state', 'protected_tiers', 'persona_profile',
    'governance_profile', 'module_permissions', 'navigable_pages',
    'learned_profile_prompt', 'governance_strategy_prompt',
    'feedback_profiles',
})

# Valid readiness states
READINESS_STATES = ("cold", "warming", "ready", "active")


def _context_key(user):
    """Generate cache key for a user's cos_context (flat)."""
    return f"{CONTEXT_KEY_PREFIX}:{user.id}"


def _stable_key(user):
    """Generate cache key for a user's stable context layer."""
    return f"{STABLE_KEY_PREFIX}:{user.id}"


def _dynamic_key(user):
    """Generate cache key for a user's dynamic context layer."""
    return f"{DYNAMIC_KEY_PREFIX}:{user.id}"


def _readiness_key(user):
    """Generate cache key for a user's readiness state."""
    return f"{READINESS_KEY_PREFIX}:{user.id}"


def get_cached_cos_context(user):
    """
    Retrieve pre-computed cos_context from cache.

    Returns:
        dict or None — Cached context, or None if miss/expired.
    """
    try:
        result = cache.get(_context_key(user))
        if result is not None:
            from apps.ai.readiness_telemetry import log_cache_hit
            log_cache_hit(user.id)
            return result
        from apps.ai.readiness_telemetry import log_cache_miss
        log_cache_miss(user.id)
        return None
    except Exception:
        logger.debug("CoS readiness cache: get failed for user %s", user.id)
        return None


def set_cached_cos_context(user, context, ttl=CONTEXT_CACHE_TTL):
    """
    Store cos_context in cache with TTL.

    The context dict is serialized by Django's cache framework.
    The internal '_user' key (a Django User instance) is stripped
    before caching to avoid serialization issues.

    Args:
        user: Django User instance.
        context: dict — cos_context from build_cos_context().
        ttl: int — seconds until expiry (default 45).
    """
    try:
        # Strip non-serializable internal refs
        cacheable = {k: v for k, v in context.items() if not k.startswith("_")}
        cache.set(_context_key(user), cacheable, ttl)
    except Exception:
        logger.debug("CoS readiness cache: set failed for user %s", user.id)


def invalidate_cos_context(user):
    """Explicitly remove cached cos_context for a user (all layers)."""
    try:
        cache.delete(_context_key(user))
        cache.delete(_stable_key(user))
        cache.delete(_dynamic_key(user))
    except Exception:
        pass


# =========================================================================
# Layered Context Cache
# =========================================================================

def get_layered_cos_context(user):
    """
    Retrieve cos_context composed from stable + dynamic cache layers.

    The stable layer (blueprint, persona, governance) has a longer TTL (5 min)
    so it survives dynamic layer expiry. The dynamic layer (calendar, health,
    signals) has a short TTL (45s) matching the flat cache.

    Returns:
        dict or None — Composed context, or None if both layers miss.
    """
    try:
        stable = cache.get(_stable_key(user))
        dynamic = cache.get(_dynamic_key(user))
        if stable is None and dynamic is None:
            return None
        context = {}
        if stable:
            context.update(stable)
        if dynamic:
            context.update(dynamic)
        from apps.ai.readiness_telemetry import log_layered_cache_hit
        log_layered_cache_hit(user.id, stable is not None, dynamic is not None)
        return context
    except Exception:
        logger.debug("CoS readiness cache: layered get failed for user %s", user.id)
        return None


def set_layered_cos_context(user, context):
    """
    Split cos_context into stable/dynamic layers and cache separately.

    Stable layer (5 min TTL): blueprint, persona, governance, permissions.
    Dynamic layer (45s TTL): calendar, health, medications, signals, etc.

    Args:
        user: Django User instance.
        context: dict — full cos_context from build_cos_context().
    """
    try:
        stable = {}
        dynamic = {}
        for k, v in context.items():
            if k.startswith("_"):
                continue  # Skip internal refs (_user)
            if k in STABLE_CONTEXT_KEYS:
                stable[k] = v
            else:
                dynamic[k] = v
        if stable:
            cache.set(_stable_key(user), stable, STABLE_CACHE_TTL)
        if dynamic:
            cache.set(_dynamic_key(user), dynamic, DYNAMIC_CACHE_TTL)
    except Exception:
        logger.debug("CoS readiness cache: layered set failed for user %s", user.id)


def get_readiness_state(user):
    """
    Get the current readiness state for a user.

    Returns:
        str — One of: 'cold', 'warming', 'ready', 'active'.
    """
    try:
        state = cache.get(_readiness_key(user))
        return state if state in READINESS_STATES else "cold"
    except Exception:
        return "cold"


def set_readiness_state(user, state):
    """
    Update the readiness state for a user.

    Args:
        state: str — One of: 'cold', 'warming', 'ready', 'active'.
    """
    if state not in READINESS_STATES:
        return
    try:
        cache.set(_readiness_key(user), state, READINESS_STATE_TTL)
    except Exception:
        pass


def prewarm_cos_context(user):
    """
    Build cos_context, cache it, and return it.

    This is the main pre-warm function called by the wake endpoint
    and the keep-alive task. It calls build_cos_context() which is
    a read-only operation (no LLM calls, no memory writes).

    Args:
        user: Django User instance.

    Returns:
        dict — The assembled cos_context.
    """
    from apps.ai.readiness_telemetry import log_context_build

    set_readiness_state(user, "warming")
    start = time.monotonic()

    try:
        from apps.core.ai_orchestrator.cos_context import build_cos_context
        context = build_cos_context(user)
        elapsed_ms = (time.monotonic() - start) * 1000
        log_context_build(user.id, elapsed_ms)

        set_cached_cos_context(user, context)
        set_layered_cos_context(user, context)
        set_readiness_state(user, "ready")
        return context
    except Exception:
        logger.warning(
            "CoS readiness cache: prewarm failed for user %s",
            user.id,
            exc_info=True,
        )
        set_readiness_state(user, "cold")
        return {}


def track_active_user(user):
    """
    Mark a user as recently active (for keep-alive targeting).

    Maintains a cached set of user IDs who have interacted in the last 5 minutes.
    """
    try:
        active_ids = cache.get(ACTIVE_USERS_KEY) or set()
        active_ids.add(user.id)
        cache.set(ACTIVE_USERS_KEY, active_ids, ACTIVE_USER_TTL)
    except Exception:
        pass


def remove_active_user(user_id):
    """Remove a user from the active set."""
    try:
        active_ids = cache.get(ACTIVE_USERS_KEY) or set()
        active_ids.discard(user_id)
        if active_ids:
            cache.set(ACTIVE_USERS_KEY, active_ids, ACTIVE_USER_TTL)
        else:
            cache.delete(ACTIVE_USERS_KEY)
    except Exception:
        pass


def get_active_user_ids():
    """
    Get IDs of recently active users.

    Returns:
        list[int] — User IDs who have interacted recently.
    """
    try:
        active_ids = cache.get(ACTIVE_USERS_KEY) or set()
        return list(active_ids)
    except Exception:
        return []


def warm_db_connection():
    """
    Execute a lightweight query to warm the DB connection pool.

    Returns:
        bool — True if connection is warm.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except Exception:
        logger.debug("CoS readiness cache: DB warm-up failed")
        return False


def warm_openai_client():
    """
    Pre-initialize the shared OpenAI client (connection pool).

    Returns:
        bool — True if client is ready.
    """
    try:
        from apps.ai.services import warm_openai_client as _warm
        return _warm()
    except Exception:
        logger.debug("CoS readiness cache: OpenAI client warm-up failed")
        return False


def invalidate_cos_context_on_action(user):
    """
    Invalidate CoS context cache when user takes an action that changes state.

    Call this after: task completion, medicine logging, weight entry, journal
    save, calendar event changes, or any CRUD action that affects guidance.
    With the TTL extended from 45s→90s, event-based invalidation ensures
    freshness without relying solely on short TTL windows.

    This is intentionally lightweight — just 3 Redis DELETEs (O(1) each).
    """
    try:
        invalidate_cos_context(user)
        logger.debug(
            "CoS readiness cache: invalidated on action for user %s", user.id,
        )
    except Exception:
        pass  # Best-effort — never block user actions
