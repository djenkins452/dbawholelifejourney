# ==============================================================================
# File: apps/ai/idempotency.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Message-level idempotency guard to prevent duplicate actions
#              from network retries or double-clicks.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-09
# ==============================================================================
"""
Idempotency Guard

Prevents duplicate intent execution when the same message is sent twice
within a short window (e.g., network retry, double-click).

Strategy:
- Compute a hash of (user_id, message_text_normalized, minute_bucket)
- Check Django cache for recent duplicate
- If found, return the cached response
- If not, store the response after processing

The minute_bucket uses 2-minute windows to handle messages that span
a minute boundary.
"""

import hashlib
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache key prefix and TTL
IDEMPOTENCY_PREFIX = "cos_idem:v1"
IDEMPOTENCY_TTL = 120  # 2 minutes


def _compute_key(user_id: int, message: str) -> str:
    """
    Compute a cache key for deduplication.

    Uses user_id + normalized message text (stripped, lowered).
    The key does NOT include a time bucket — we rely on TTL expiry
    so that genuinely repeated messages (e.g., "log 150" twice in
    10 minutes) are allowed after the window expires.
    """
    normalized = message.strip().lower()
    content = f"{user_id}:{normalized}"
    digest = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"{IDEMPOTENCY_PREFIX}:{user_id}:{digest}"


def check_duplicate(user_id: int, message: str):
    """
    Check if this message was recently processed.

    Returns:
        dict or None — Cached response if duplicate, None if new.
    """
    try:
        key = _compute_key(user_id, message)
        return cache.get(key)
    except Exception:
        # Cache failures must never block the pipeline
        return None


def store_result(user_id: int, message: str, result: dict):
    """
    Store the response for a processed message.

    Args:
        user_id: User ID.
        message: Original message text.
        result: Serializable response dict to cache.
    """
    try:
        key = _compute_key(user_id, message)
        cache.set(key, result, IDEMPOTENCY_TTL)
    except Exception:
        # Cache failures must never block the pipeline
        pass


# ── Phase 6.7: In-flight marker ───────────────────────────────────────
# Tracks requests that are currently being processed so a retry from
# the client (e.g., after a network blip) returns a "processing" marker
# instead of starting a second execution.

IN_FLIGHT_PREFIX = "cos_idem_inflight:v1"
IN_FLIGHT_TTL = 180  # 3 minutes — generous cap for long LLM responses


def _in_flight_key(user_id: int, message: str) -> str:
    normalized = (message or '').strip().lower()
    digest = hashlib.sha256(f"{user_id}:{normalized}".encode()).hexdigest()[:16]
    return f"{IN_FLIGHT_PREFIX}:{user_id}:{digest}"


def mark_in_flight(user_id: int, message: str, request_id: str):
    """
    Mark a request as currently processing. Called at the start of
    send_message / send_message_stream. Retries during this window will
    see a 'processing' marker via is_in_flight().
    """
    try:
        cache.set(
            _in_flight_key(user_id, message),
            {'request_id': request_id, 'status': 'processing'},
            IN_FLIGHT_TTL,
        )
    except Exception:
        pass


def is_in_flight(user_id: int, message: str):
    """
    Return the in-flight marker dict if a request is currently processing,
    or None if not. Callers use this to avoid duplicate execution on
    network retries.
    """
    try:
        return cache.get(_in_flight_key(user_id, message))
    except Exception:
        return None


def clear_in_flight(user_id: int, message: str):
    """Clear the in-flight marker once processing completes (or fails)."""
    try:
        cache.delete(_in_flight_key(user_id, message))
    except Exception:
        pass
