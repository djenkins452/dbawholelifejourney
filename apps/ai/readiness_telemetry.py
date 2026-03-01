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


# =========================================================================
# Instant-Response Layer Telemetry
# =========================================================================

def log_layered_cache_hit(user_id, stable_hit, dynamic_hit):
    """Log layered cache layer hits."""
    logger.debug(
        "cos.context.layered_hit user=%s stable=%s dynamic=%s",
        user_id, stable_hit, dynamic_hit,
    )


def log_stream_start(user_id, ttft_ms):
    """Log when first token is emitted to the client (time to first token)."""
    logger.info(
        "cos.stream.start user=%s ttft_ms=%.1f",
        user_id, ttft_ms,
    )


def log_stream_complete(user_id, total_ms, token_count):
    """Log when stream is fully complete."""
    logger.info(
        "cos.stream.complete user=%s total_ms=%.1f tokens=%d",
        user_id, total_ms, token_count,
    )


def log_stream_fallback(user_id, reason):
    """Log when stream fell back to non-streaming."""
    logger.info(
        "cos.stream.fallback user=%s reason=%s",
        user_id, reason,
    )


def log_parallel_build(user_id, elapsed_ms, builder_count):
    """Log context build with parallel indicator."""
    logger.info(
        "cos.context.parallel_build user=%s elapsed_ms=%.1f builders=%d",
        user_id, elapsed_ms, builder_count,
    )
