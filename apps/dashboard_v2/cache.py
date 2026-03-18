"""
Dashboard V2 cache service.

Provides section-based caching with independent invalidation per section.
Follows the same pattern as apps/dashboard/cache.py.
"""

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache TTLs in seconds
CACHE_TTLS = {
    "momentum": 300,     # 5 minutes
    "daily_prog": 120,   # 2 minutes
    "execution": 30,     # 30 seconds — action center must stay fresh
    "state": 300,        # 5 minutes
    "celebration": 600,  # 10 minutes
}

CACHE_PREFIX = "dashboard_v2"


class DashboardV2CacheService:
    """Section-based cache service for dashboard_v2."""

    @staticmethod
    def _key(user_id, section):
        return f"{CACHE_PREFIX}:{user_id}:{section}"

    @classmethod
    def get(cls, user_id, section):
        """Get cached data for a section. Returns None on miss."""
        return cache.get(cls._key(user_id, section))

    @classmethod
    def set(cls, user_id, section, data):
        """Cache data for a section with appropriate TTL."""
        ttl = CACHE_TTLS.get(section, 300)
        cache.set(cls._key(user_id, section), data, ttl)

    @classmethod
    def invalidate(cls, user_id, section):
        """Invalidate a specific cache section."""
        cache.delete(cls._key(user_id, section))

    @classmethod
    def invalidate_all(cls, user_id):
        """Invalidate all cache sections for a user."""
        for section in CACHE_TTLS:
            cache.delete(cls._key(user_id, section))
