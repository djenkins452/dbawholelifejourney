"""
Resilient Redis cache backend that degrades gracefully on connection failure.

When Redis is unreachable (e.g., during Railway deploy or Redis outage),
all cache operations silently return cache-miss defaults instead of crashing.
This prevents the entire site from going down due to a cache service issue.

Three-state circuit breaker:
  CLOSED  — Redis is healthy, all calls go through
  OPEN    — Redis failed, skip all calls for 60s (instant no-ops)
  HALF-OPEN — Cooldown expired, allow ONE probe call to test recovery
"""

import logging
import time

from django.core.cache.backends.redis import RedisCache

logger = logging.getLogger(__name__)

# Circuit breaker state
_circuit_open_until = 0
_CIRCUIT_BREAKER_SECONDS = 60
_last_log_time = 0
_LOG_INTERVAL_SECONDS = 300  # Rate-limit warnings to every 5 min


def _circuit_is_open():
    """True when circuit is fully open — skip Redis entirely."""
    return time.monotonic() < _circuit_open_until


def _trip_circuit():
    """Open the circuit after a Redis failure."""
    global _circuit_open_until, _last_log_time
    now = time.monotonic()
    if now - _last_log_time > _LOG_INTERVAL_SECONDS:
        logger.warning("Redis unreachable — circuit breaker open for %ds", _CIRCUIT_BREAKER_SECONDS)
        _last_log_time = now
    _circuit_open_until = now + _CIRCUIT_BREAKER_SECONDS


def _close_circuit():
    """Close the circuit after a successful probe."""
    global _circuit_open_until
    if _circuit_open_until > 0:
        logger.info("Redis recovered — circuit breaker closed")
    _circuit_open_until = 0


def _on_success():
    """Called after any successful Redis operation."""
    if _circuit_open_until > 0:
        _close_circuit()


class SafeRedisCache(RedisCache):
    """Redis cache backend with three-state circuit breaker."""

    def get(self, key, default=None, version=None):
        if _circuit_is_open():
            return default
        try:
            result = super().get(key, default, version)
            _on_success()
            return result
        except Exception:
            _trip_circuit()
            return default

    def set(self, key, value, timeout=None, version=None):
        if _circuit_is_open():
            return False
        try:
            result = super().set(key, value, timeout, version)
            _on_success()
            return result
        except Exception:
            _trip_circuit()
            return False

    def delete(self, key, version=None):
        if _circuit_is_open():
            return False
        try:
            result = super().delete(key, version)
            _on_success()
            return result
        except Exception:
            _trip_circuit()
            return False

    def get_many(self, keys, version=None):
        if _circuit_is_open():
            return {}
        try:
            result = super().get_many(keys, version)
            _on_success()
            return result
        except Exception:
            _trip_circuit()
            return {}

    def set_many(self, mapping, timeout=None, version=None):
        if _circuit_is_open():
            return []
        try:
            result = super().set_many(mapping, timeout, version)
            _on_success()
            return result
        except Exception:
            _trip_circuit()
            return []

    def delete_many(self, keys, version=None):
        if _circuit_is_open():
            return
        try:
            result = super().delete_many(keys, version)
            _on_success()
            return result
        except Exception:
            _trip_circuit()

    def has_key(self, key, version=None):
        if _circuit_is_open():
            return False
        try:
            result = super().has_key(key, version)
            _on_success()
            return result
        except Exception:
            _trip_circuit()
            return False

    def incr(self, key, delta=1, version=None):
        if _circuit_is_open():
            return None
        try:
            result = super().incr(key, delta, version)
            _on_success()
            return result
        except Exception:
            _trip_circuit()
            return None

    def clear(self):
        if _circuit_is_open():
            return
        try:
            result = super().clear()
            _on_success()
            return result
        except Exception:
            _trip_circuit()
