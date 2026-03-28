# ==============================================================================
# File: apps/core/ai_events/resolver.py
# Project: Whole Life Journey — Django 5.x Personal Wellness/Journaling App
# Description: Cross-domain event resolver — deterministic event truth access
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-28
# ==============================================================================
"""
Event Resolver — orchestrates domain adapters for cross-domain event queries.

This is the primary interface for the router and intent handlers to access
event-level truth. All methods return deterministic data from canonical
domain models.

Supports 16 domains covering every user-facing data entry model in WLJ.
"""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Domain adapter registry — maps domain name to adapter module path
_DOMAIN_ADAPTERS = {
    # Health — execution tracking
    'medication': 'apps.core.ai_events.adapters.medication',
    'routine': 'apps.core.ai_events.adapters.routine',
    'workout': 'apps.core.ai_events.adapters.workout',
    # Health — vitals & measurements
    'sleep': 'apps.core.ai_events.adapters.sleep',
    'weight': 'apps.core.ai_events.adapters.weight',
    'glucose': 'apps.core.ai_events.adapters.glucose',
    'blood_pressure': 'apps.core.ai_events.adapters.blood_pressure',
    'heart_rate': 'apps.core.ai_events.adapters.heart_rate',
    'steps': 'apps.core.ai_events.adapters.steps',
    'water': 'apps.core.ai_events.adapters.water',
    'nutrition': 'apps.core.ai_events.adapters.nutrition',
    'fasting': 'apps.core.ai_events.adapters.fasting',
    # Life domains
    'journal': 'apps.core.ai_events.adapters.journal',
    'faith': 'apps.core.ai_events.adapters.faith',
    'habits': 'apps.core.ai_events.adapters.habits',
    'finance': 'apps.core.ai_events.adapters.finance',
}

# Domains that support get_missed_events()
_MISSED_DOMAINS = ('medication', 'routine', 'habits')

# Domains to include in full-day timeline queries
_TIMELINE_DOMAINS = (
    'medication', 'routine', 'workout', 'sleep',
    'nutrition', 'journal', 'faith', 'habits',
)


def _get_adapter(domain):
    """Lazy-import a domain adapter module."""
    if domain not in _DOMAIN_ADAPTERS:
        raise ValueError(
            f"Unknown domain: {domain}. "
            f"Available: {sorted(_DOMAIN_ADAPTERS.keys())}"
        )
    import importlib
    return importlib.import_module(_DOMAIN_ADAPTERS[domain])


class EventResolver:
    """
    Cross-domain event resolver.

    All methods are stateless — the resolver holds no mutable state.
    Each call queries the database through the appropriate domain adapter.
    """

    def get_events(self, user, domain, start_date, end_date):
        """Get all events for a domain in date range."""
        adapter = _get_adapter(domain)
        return adapter.get_events(user, start_date, end_date)

    def get_latest(self, user, domain, count=1):
        """
        Get the most recent events for a domain.

        Used for "how was my sleep last night?", "what's my latest weight?",
        "last blood pressure reading?" type queries.

        Args:
            user: Django User instance
            domain: str — domain name
            count: int — how many recent entries to return

        Returns:
            list[EventRecord] — most recent events (newest first)
        """
        adapter = _get_adapter(domain)
        if hasattr(adapter, 'get_latest'):
            return adapter.get_latest(user, count=count)
        # Fallback: get last N days of events
        end = date.today()
        start = end - timedelta(days=7)
        events = adapter.get_events(user, start, end)
        return events[-count:] if events else []

    def get_missed_events(self, user, domain, start_date, end_date):
        """Get missed events for a specific domain."""
        adapter = _get_adapter(domain)
        if hasattr(adapter, 'get_missed_events'):
            return adapter.get_missed_events(user, start_date, end_date)
        # Domain doesn't track "missed" — return empty
        return []

    def get_all_missed(self, user, start_date, end_date):
        """Get all missed events across all trackable domains."""
        all_missed = []
        for domain in _MISSED_DOMAINS:
            try:
                adapter = _get_adapter(domain)
                if hasattr(adapter, 'get_missed_events'):
                    missed = adapter.get_missed_events(user, start_date, end_date)
                    all_missed.extend(missed)
            except Exception as e:
                logger.warning(
                    "Failed to get missed events for domain=%s user=%s: %s",
                    domain, user.id, e, exc_info=True,
                )
        all_missed.sort(key=lambda e: e.timestamp)
        return all_missed

    def get_day_timeline(self, user, target_date):
        """Get all events across domains for a specific date."""
        events = []
        for domain in _TIMELINE_DOMAINS:
            try:
                adapter = _get_adapter(domain)
                day_events = adapter.get_day_events(user, target_date)
                events.extend(day_events)
            except Exception as e:
                logger.warning(
                    "Failed to get day events for domain=%s user=%s date=%s: %s",
                    domain, user.id, target_date, e, exc_info=True,
                )
        events.sort(key=lambda e: e.timestamp)
        return events

    def get_routine_trend(self, user, lookback_days=14):
        """Get routine completion trend for slippage analysis."""
        from apps.core.ai_events.adapters.routine import get_completion_trend
        return get_completion_trend(user, lookback_days=lookback_days)

    @staticmethod
    def available_domains():
        """Return list of all registered domains."""
        return sorted(_DOMAIN_ADAPTERS.keys())
