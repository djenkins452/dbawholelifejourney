# ==============================================================================
# File: apps/core/ai_events/resolver.py
# Project: Whole Life Journey — Django 5.x Personal Wellness/Journaling App
# Description: Cross-domain event resolver — deterministic event truth access
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-28
# ==============================================================================
"""
Event Resolver — orchestrates domain adapters for cross-domain event queries.

This is the primary interface for the router to access event-level truth.
All methods return deterministic data from canonical domain models.

Usage:
    from apps.core.ai_events.resolver import EventResolver

    resolver = EventResolver()
    missed = resolver.get_missed_events(user, 'medication', start, end)
    timeline = resolver.get_day_timeline(user, date.today())
    trend = resolver.get_routine_trend(user, lookback_days=14)
"""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Domain adapter registry — maps domain name to adapter module path
_DOMAIN_ADAPTERS = {
    'medication': 'apps.core.ai_events.adapters.medication',
    'routine': 'apps.core.ai_events.adapters.routine',
    'workout': 'apps.core.ai_events.adapters.workout',
}

# Domains to include in "all missed" queries
_MISSED_DOMAINS = ('medication', 'routine')

# Domains to include in timeline queries
_TIMELINE_DOMAINS = ('medication', 'routine', 'workout')


def _get_adapter(domain):
    """Lazy-import a domain adapter module."""
    if domain not in _DOMAIN_ADAPTERS:
        raise ValueError(f"Unknown domain: {domain}. Available: {list(_DOMAIN_ADAPTERS.keys())}")
    import importlib
    return importlib.import_module(_DOMAIN_ADAPTERS[domain])


class EventResolver:
    """
    Cross-domain event resolver.

    All methods are stateless — the resolver holds no mutable state.
    Each call queries the database through the appropriate domain adapter.
    """

    def get_events(self, user, domain, start_date, end_date):
        """
        Get all events for a domain in date range.

        Args:
            user: Django User instance
            domain: str — domain name (e.g., 'medication')
            start_date: date
            end_date: date

        Returns:
            list[EventRecord]
        """
        adapter = _get_adapter(domain)
        return adapter.get_events(user, start_date, end_date)

    def get_missed_events(self, user, domain, start_date, end_date):
        """
        Get missed events for a specific domain.

        Args:
            user: Django User instance
            domain: str — domain name
            start_date: date
            end_date: date

        Returns:
            list[EventRecord] — missed events only
        """
        adapter = _get_adapter(domain)
        return adapter.get_missed_events(user, start_date, end_date)

    def get_all_missed(self, user, start_date, end_date):
        """
        Get all missed events across all trackable domains.

        Used for "what did I miss?" without domain specification.

        Args:
            user: Django User instance
            start_date: date
            end_date: date

        Returns:
            list[EventRecord] — missed events across all domains, sorted by time
        """
        all_missed = []
        for domain in _MISSED_DOMAINS:
            try:
                adapter = _get_adapter(domain)
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
        """
        Get all events across domains for a specific date.

        Used for "what happened yesterday?" type queries.

        Args:
            user: Django User instance
            target_date: date

        Returns:
            list[EventRecord] — all events for the date, sorted by time
        """
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
        """
        Get routine completion trend — for "when did my routine start slipping?"

        Args:
            user: Django User instance
            lookback_days: int — how far back to analyze

        Returns:
            dict with daily_rates, slippage_date, current_rate, prior_rate
        """
        from apps.core.ai_events.adapters.routine import get_completion_trend
        return get_completion_trend(user, lookback_days=lookback_days)
