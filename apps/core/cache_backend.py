"""
Resilient Redis cache backend that degrades gracefully on connection failure.

When Redis is unreachable (e.g., during Railway deploy or Redis outage),
all cache operations silently return cache-miss defaults instead of crashing.
This prevents the entire site from going down due to a cache service issue.
"""

import logging

from django.core.cache.backends.redis import RedisCache

logger = logging.getLogger(__name__)


class SafeRedisCache(RedisCache):
    """Redis cache backend that catches connection errors instead of crashing."""

    def get(self, key, default=None, version=None):
        try:
            return super().get(key, default, version)
        except Exception:
            return default

    def set(self, key, value, timeout=None, version=None):
        try:
            return super().set(key, value, timeout, version)
        except Exception:
            return False

    def delete(self, key, version=None):
        try:
            return super().delete(key, version)
        except Exception:
            return False

    def get_many(self, keys, version=None):
        try:
            return super().get_many(keys, version)
        except Exception:
            return {}

    def set_many(self, mapping, timeout=None, version=None):
        try:
            return super().set_many(mapping, timeout, version)
        except Exception:
            return []

    def delete_many(self, keys, version=None):
        try:
            return super().delete_many(keys, version)
        except Exception:
            pass

    def has_key(self, key, version=None):
        try:
            return super().has_key(key, version)
        except Exception:
            return False

    def incr(self, key, delta=1, version=None):
        try:
            return super().incr(key, delta, version)
        except Exception:
            return None

    def clear(self):
        try:
            return super().clear()
        except Exception:
            pass
