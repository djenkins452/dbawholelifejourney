# ==============================================================================
# File: apps/ai/readiness_telemetry.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: CoS Readiness Telemetry — Internal performance logging
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-28
# ==============================================================================
"""
CoS Readiness Telemetry

Logging-based telemetry for the CoS readiness/pre-warm pipeline.
Uses Python logging (not DB writes) to avoid adding latency.

All functions are fire-and-forget — failures are silently ignored.
"""

import logging

logger = logging.getLogger("cos.readiness")


def log_wake_request(user_id, cache_hit):
    """Log a wake endpoint hit."""
    logger.info(
        "cos.wake user=%s cache_hit=%s",
        user_id,
        cache_hit,
    )


def log_cache_hit(user_id):
    """Log a context cache hit."""
    logger.debug("cos.context.cache_hit user=%s", user_id)


def log_cache_miss(user_id):
    """Log a context cache miss."""
    logger.debug("cos.context.cache_miss user=%s", user_id)


def log_context_build(user_id, elapsed_ms):
    """Log time taken to build cos_context."""
    logger.info(
        "cos.context.build user=%s elapsed_ms=%.1f",
        user_id,
        elapsed_ms,
    )


def log_fast_path(user_id):
    """Log that fast-path execution was used (cached context in response path)."""
    logger.info("cos.response.fast_path user=%s", user_id)


def log_full_path(user_id):
    """Log that full-path execution was used (fresh context build in response path)."""
    logger.info("cos.response.full_path user=%s", user_id)


def log_readiness_state_change(user_id, old_state, new_state):
    """Log a readiness state transition."""
    logger.debug(
        "cos.readiness.state user=%s %s->%s",
        user_id,
        old_state,
        new_state,
    )


def log_keepalive_cycle(active_count, refreshed_count):
    """Log a keep-alive cycle execution."""
    logger.info(
        "cos.keepalive active_users=%d refreshed=%d",
        active_count,
        refreshed_count,
    )
