"""
Resilient Redis cache backend that degrades gracefully on connection failure.

When Redis is unreachable (e.g., during Railway deploy or Redis outage),
all cache operations silently return cache-miss defaults instead of crashing.
This prevents the entire site from going down due to a cache service issue.

Circuit breaker: After the first Redis failure, skips all Redis calls for
60 seconds to avoid 3-second timeout delays on every cache operation.
"""

import logging
import time

from django.core.cache.backends.redis import RedisCache

logger = logging.getLogger(__name__)

# Circuit breaker: timestamp of when Redis was last unreachable
_circuit_open_until = 0
_CIRCUIT_BREAKER_SECONDS = 60


def _circuit_is_open():
    return time.monotonic() < _circuit_open_until


def _trip_circuit():
    global _circuit_open_until
    if not _circuit_is_open():
        logger.warning("Redis unreachable — circuit breaker open for %ds", _CIRCUIT_BREAKER_SECONDS)
    _circuit_open_until = time.monotonic() + _CIRCUIT_BREAKER_SECONDS


class SafeRedisCache(RedisCache):
    """Redis cache backend with circuit breaker for connection failures."""

    def get(self, key, default=None, version=None):
        if _circuit_is_open():
            return default
        try:
            return super().get(key, default, version)
        except Exception:
            _trip_circuit()
            return default

    def set(self, key, value, timeout=None, version=None):
        if _circuit_is_open():
            return False
        try:
            return super().set(key, value, timeout, version)
        except Exception:
            _trip_circuit()
            return False

    def delete(self, key, version=None):
        if _circuit_is_open():
            return False
        try:
            return super().delete(key, version)
        except Exception:
            _trip_circuit()
            return False

    def get_many(self, keys, version=None):
        if _circuit_is_open():
            return {}
        try:
            return super().get_many(keys, version)
        except Exception:
            _trip_circuit()
            return {}

    def set_many(self, mapping, timeout=None, version=None):
        if _circuit_is_open():
            return []
        try:
            return super().set_many(mapping, timeout, version)
        except Exception:
            _trip_circuit()
            return []

    def delete_many(self, keys, version=None):
        if _circuit_is_open():
            return
        try:
            return super().delete_many(keys, version)
        except Exception:
            _trip_circuit()

    def has_key(self, key, version=None):
        if _circuit_is_open():
            return False
        try:
            return super().has_key(key, version)
        except Exception:
            _trip_circuit()
            return False

    def incr(self, key, delta=1, version=None):
        if _circuit_is_open():
            return None
        try:
            return super().incr(key, delta, version)
        except Exception:
            _trip_circuit()
            return None

    def clear(self):
        if _circuit_is_open():
            return
        try:
            return super().clear()
        except Exception:
            _trip_circuit()
