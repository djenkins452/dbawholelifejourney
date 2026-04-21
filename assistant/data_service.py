"""
Personal Data Service for WLJ Personal Data Query System.

This module provides methods to query and summarize user's personal
wellness data from various models (weight, journal, mood, etc.).

Soft Delete Pattern:
-------------------
IMPORTANT: Models in this codebase use a soft delete pattern via SoftDeleteManager.

- Models inheriting UserOwnedModel automatically filter out deleted records
- The default manager (objects) filters by status='active'
- DO NOT use is_deleted in filter() - it's a @property, not a database field
- DO NOT manually filter by status='active' - the manager handles this

Correct:
    queryset = JournalEntry.objects.filter(user=self.user)

Wrong:
    queryset = JournalEntry.objects.filter(user=self.user, is_deleted=False)  # FieldError!

See apps/core/models.py for SoftDeleteManager and SoftDeleteModel implementation.
See docs/wlj_claude_troubleshoot.md section 7 for full documentation.

Cache Invalidation Strategy:
---------------------------
This module uses a cache versioning approach to handle date-specific cache keys.
Instead of trying to delete all possible date-variant cache keys (which is
impossible to enumerate), we:

1. Store a version number per user/data_type combination
2. Include the version in all data cache keys
3. On invalidation, increment the version number

This makes all existing cache keys for that user/data_type effectively stale,
as new requests will use the incremented version in their cache key.

Benefits:
- Works with any cache backend (not just Redis)
- No need to enumerate all possible date combinations
- Guaranteed to invalidate all cached data for a user/data_type
- Minimal overhead (one extra cache lookup per request)

The version key format is: personal_data_version:{user_id}:{data_type}
The data cache key format is: personal_data:{user_id}:{data_type}:v{version}:{date}
"""

import logging
import warnings
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_metric(user, key):
    """
    Lazy wrapper around ``apps.core.ai_state.metric_access.get_metric``.

    The assistant package is imported during Django app loading
    (``assistant/__init__.py`` re-exports :class:`PersonalDataService`),
    so top-level imports of ``apps.core.ai_state`` trigger
    ``AppRegistryNotReady``. Deferring the import until call time
    avoids that boot-order problem without changing the facade's
    semantics.
    """
    from apps.core.ai_state.metric_access import get_metric
    return get_metric(user, key)


# Module-level alias so the existing call sites read as
# ``get_metric(user, key)`` while still going through the lazy loader.
get_metric = _get_metric


# Methods migrated to the canonical metric access layer. Aggregation
# has been removed from these and they now read from SAE state via
# get_metric(). Use this list to keep the deprecated-method warnings
# in the untouched methods consistent.
_MIGRATED_METHODS = frozenset({
    "get_glucose_data",
    "get_weight_data",
    "get_sleep_data",
    "get_food_data",
    "get_steps_data",
    "get_water_data",
    "get_workout_data",
    "get_journal_data",
    "get_mood_data",
    "get_medication_data",
})


def _warn_deprecated_personal_data_method(method_name: str) -> None:
    """
    Emit a deprecation warning for a non-migrated ``get_*_data`` method
    that still performs raw aggregation. Called at the top of each
    un-migrated method so operators see the warning in logs and in
    test output without breaking callers.
    """
    message = (
        f"PersonalDataService.{method_name}() still performs raw "
        "aggregation and is deprecated. It will be removed once the "
        "corresponding canonical metric is added to SAE. Do not call "
        "from new code — use apps.core.ai_state.metric_access.get_metric()."
    )
    warnings.warn(message, DeprecationWarning, stacklevel=3)
    logger.warning(
        "personal_data_service.deprecated_call",
        extra={
            "metric_access": True,
            "event": "deprecated_call",
            "method": method_name,
        },
    )


def _to_date(value: Optional[datetime]) -> Optional[date]:
    """
    Convert a datetime to a date for safe DateField comparisons.

    When filtering Django DateField columns, passing a timezone-aware datetime
    can cause incorrect comparisons: PostgreSQL casts the DateField value to
    timestamp at midnight UTC, while the datetime may represent midnight in a
    different timezone (e.g., CST). This mismatch causes date >= queries to
    miss same-day records.

    Always use this helper when filtering DateField with a since_date parameter.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


# Cache TTL for personal data queries (5 minutes)
PERSONAL_DATA_CACHE_TTL = 300

# Cache TTL for version keys (longer than data TTL to ensure consistency)
# Version keys should persist longer to prevent stale data from being served
VERSION_CACHE_TTL = 86400  # 24 hours


def _get_version_key(user_id: int, data_type: str) -> str:
    """
    Generate the cache key for storing the version number.

    Args:
        user_id: The user's ID.
        data_type: The type of data.

    Returns:
        The version cache key string.
    """
    return f"personal_data_version:{user_id}:{data_type}"


def _get_cache_version(user_id: int, data_type: str) -> int:
    """
    Get the current cache version for a user/data_type combination.

    If no version exists, returns 1 (initial version).

    Args:
        user_id: The user's ID.
        data_type: The type of data.

    Returns:
        The current version number (integer >= 1).
    """
    version_key = _get_version_key(user_id, data_type)
    version = cache.get(version_key)
    if version is None:
        # Initialize version to 1 if not set
        cache.set(version_key, 1, VERSION_CACHE_TTL)
        return 1
    return version


def _generate_cache_key(user_id: int, data_type: str, since_date: Optional[datetime] = None) -> str:
    """
    Generate a versioned cache key for personal data queries.

    The key includes a version number that is incremented when data changes,
    effectively invalidating all date-variant cache keys at once.

    Args:
        user_id: The user's ID.
        data_type: The type of data (weight, journal, medication, food, mood, etc.).
        since_date: Optional date filter. If None, uses 'all'.

    Returns:
        A unique, versioned cache key string.

    Key format: personal_data:{user_id}:{data_type}:v{version}:{date}
    """
    # Get current version for this user/data_type
    version = _get_cache_version(user_id, data_type)

    # Format the date part
    date_part = 'all'
    if since_date:
        if isinstance(since_date, datetime):
            date_part = since_date.strftime('%Y-%m-%d')
        elif isinstance(since_date, date):
            date_part = since_date.strftime('%Y-%m-%d')
        else:
            date_part = str(since_date)

    return f"personal_data:{user_id}:{data_type}:v{version}:{date_part}"


def invalidate_user_data_cache(user_id: int, data_type: str) -> None:
    """
    Invalidate all cached data for a user and data type.

    This uses a cache versioning strategy: instead of trying to delete
    all possible cache keys (with various date combinations), we increment
    the version number. All existing cache keys become stale because new
    requests will use the new version in their cache key.

    This approach:
    - Works with any cache backend (LocMemCache, Redis, Memcached, etc.)
    - Guarantees all date-variant cache keys are invalidated
    - Avoids the need to enumerate all possible date combinations

    Args:
        user_id: The user's ID.
        data_type: The type of data to invalidate.
    """
    version_key = _get_version_key(user_id, data_type)

    # Get current version (or 0 if not set)
    current_version = cache.get(version_key, 0)

    # Increment version - this invalidates all existing cache keys
    # because they use the old version number
    new_version = current_version + 1
    cache.set(version_key, new_version, VERSION_CACHE_TTL)


class PersonalDataService:
    """
    Service for querying and summarizing user's personal data.

    This service provides methods to retrieve data from various WLJ models
    and return summarized results suitable for AI-assisted responses.
    """

    def __init__(self, user):
        """
        Initialize the PersonalDataService.

        Args:
            user: The User object whose data will be queried.
        """
        self.user = user

    def get_weight_data(
        self,
        since_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's weight log data.

        Args:
            since_date: Optional datetime to filter entries from this date.
                       If None, returns all entries.
            limit: Maximum number of recent entries to include (default 10).

        Returns:
            None if no weight entries exist for the user.
            Otherwise, a dictionary containing:
                - type (str): 'weight'
                - count (int): Total number of entries matching criteria
                - average (float): Average weight value
                - latest (float): Most recent weight value
                - latest_date (datetime): Date of most recent entry
                - unit (str): Unit of measurement (lb or kg)
                - entries (list): Last N entries as dicts with value, unit,
                                 recorded_at, and notes

        Example:
            >>> service = PersonalDataService(user)
            >>> data = service.get_weight_data(since_date=datetime(2024, 12, 1))
            >>> print(data)
            {
                'type': 'weight',
                'count': 15,
                'average': 175.5,
                'latest': 174.0,
                'latest_date': datetime(2024, 12, 18, 8, 30),
                'unit': 'lb',
                'entries': [...]
            }
        """
        # Canonical values come from SAE state; no average is computed
        # here because no canonical weight average exists yet. Recent
        # entries are still queried as a non-aggregated list so the
        # LLM can see specific values for narrative context.
        cache_key = _generate_cache_key(self.user.id, 'weight', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        weight_current = get_metric(self.user, 'health.weight_current')
        if weight_current is None:
            return None

        weight_unit = get_metric(self.user, 'health.weight_unit')
        last_entry = get_metric(self.user, 'health.last_weight_entry')
        change_30d = get_metric(self.user, 'health.weight_change_30d')
        trend = get_metric(self.user, 'health.weight_trend')

        from apps.health.models import WeightEntry
        entries_qs = WeightEntry.objects.filter(user=self.user)
        if since_date:
            entries_qs = entries_qs.filter(recorded_at__gte=since_date)
        recent_entries = list(
            entries_qs[:limit].values('value', 'unit', 'recorded_at', 'notes')
        )
        entries = [
            {
                'value': float(e['value']),
                'unit': e['unit'],
                'recorded_at': e['recorded_at'],
                'notes': e['notes'],
            }
            for e in recent_entries
        ]

        result = {
            'type': 'weight',
            'latest': float(weight_current.value),
            'latest_date': last_entry.value if last_entry else None,
            'unit': (
                weight_unit.value if weight_unit
                else (entries[0]['unit'] if entries else 'lb')
            ),
            'change_30d': change_30d.value if change_30d else None,
            'trend': trend.value if trend else None,
            'source': weight_current.source,
            'entries': entries,
        }

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

    def get_journal_data(
        self,
        since_date: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's journal entry data.

        Args:
            since_date: Optional datetime to filter entries from this date.
                       If None, returns all entries.

        Returns:
            None if no journal entries exist for the user.
            Otherwise, a dictionary containing:
                - type (str): 'journal'
                - count (int): Total number of entries matching criteria
                - latest_date (date): Date of most recent entry

        Example:
            >>> service = PersonalDataService(user)
            >>> data = service.get_journal_data(since_date=datetime(2024, 12, 1))
            >>> print(data)
            {
                'type': 'journal',
                'count': 15,
                'latest_date': date(2024, 12, 18)
            }
        """
        # Canonical journal counts and last-entry date come from SAE
        # journal state. Streak, consistency %, and missed-day
        # calculations previously derived here are NOT rebuilt — they
        # have no canonical equivalent yet. A recent-entries list is
        # still fetched as non-aggregated row data for narrative use.
        cache_key = _generate_cache_key(self.user.id, 'journal', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        entries_7d = get_metric(self.user, 'journal.entries_7d')
        entries_30d = get_metric(self.user, 'journal.entries_30d')
        days_since = get_metric(self.user, 'journal.days_since_entry')
        last_entry_ts = get_metric(self.user, 'journal.last_entry')

        if (
            entries_7d is None
            and entries_30d is None
            and last_entry_ts is None
        ):
            return None

        from apps.journal.models import JournalEntry
        entries_qs = JournalEntry.objects.filter(user=self.user)
        if since_date:
            entries_qs = entries_qs.filter(entry_date__gte=_to_date(since_date))
        recent_entries = []
        for entry in entries_qs.prefetch_related('tags')[:14]:
            tags = [t.name for t in entry.tags.all()]
            preview = (
                entry.body[:200] + '...' if len(entry.body) > 200 else entry.body
            )
            recent_entries.append({
                'date': entry.entry_date,
                'title': entry.title,
                'mood': entry.mood or '',
                'tags': tags,
                'preview': preview,
                'word_count': entry.word_count or 0,
            })

        result = {
            'type': 'journal',
            'entries_7d': entries_7d.value if entries_7d else None,
            'entries_30d': entries_30d.value if entries_30d else None,
            'days_since_entry': days_since.value if days_since else None,
            'latest_date': last_entry_ts.value if last_entry_ts else None,
            'source': (
                entries_7d.source if entries_7d
                else (last_entry_ts.source if last_entry_ts else None)
            ),
            'recent_entries': recent_entries,
        }

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

    def get_medication_data(
        self,
        since_date: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's medication log data with consistency.

        Args:
            since_date: Optional datetime to filter entries from this date.
                       If None, returns all entries.

        Returns:
            None if no medication logs exist for the user.
            Otherwise, a dictionary containing:
                - type (str): 'medication'
                - total_logs (int): Total number of log entries matching criteria
                - days_logged (int): Number of unique days with logs
                - total_days (int): Total days in the period
                - consistency_percent (float): (days_logged / total_days) * 100

        Example:
            >>> service = PersonalDataService(user)
            >>> data = service.get_medication_data(since_date=datetime(2024, 12, 1))
            >>> print(data)
            {
                'type': 'medication',
                'total_logs': 45,
                'days_logged': 15,
                'total_days': 18,
                'consistency_percent': 83.3
            }
        """
        # Canonical medication adherence status is owned by the SAE
        # medicine state builder (health.medication_status). Raw
        # MedicineLog consistency-% calculation has been removed; a
        # canonical adherence % has not yet been promoted into SAE,
        # so we surface only the status for now.
        cache_key = _generate_cache_key(self.user.id, 'medication', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        status = get_metric(self.user, 'health.medication_status')
        status_reason = get_metric(self.user, 'health.medication_status_reason')
        if status is None:
            return None

        result = {
            'type': 'medication',
            'status': status.value,
            'status_reason': status_reason.value if status_reason else None,
            'source': status.source,
        }

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

    def get_food_data(
        self,
        since_date: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's food entry data with calorie summaries.

        Args:
            since_date: Optional datetime to filter entries from this date.
                       If None, returns all entries.

        Returns:
            None if no food entries exist for the user.
            Otherwise, a dictionary containing:
                - type (str): 'food'
                - total_entries (int): Total number of entries matching criteria
                - total_calories (float): Sum of all calories in the period
                - average_daily_calories (float): Average calories per day
                - latest_date (date): Date of most recent entry

        Example:
            >>> service = PersonalDataService(user)
            >>> data = service.get_food_data(since_date=datetime(2024, 12, 1))
            >>> print(data)
            {
                'type': 'food',
                'total_entries': 45,
                'total_calories': 67500.0,
                'average_daily_calories': 1875.0,
                'latest_date': date(2024, 12, 18)
            }
        """
        # Canonical daily calories and 7-day rolling average come from
        # the SAE nutrition state. Raw FoodEntry aggregation has been
        # removed; we no longer re-derive totals here.
        cache_key = _generate_cache_key(self.user.id, 'food', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        daily_calories = get_metric(self.user, 'nutrition.daily_calories')
        rolling_avg = get_metric(self.user, 'nutrition.rolling_7d_calories_avg')
        entries_today = get_metric(self.user, 'nutrition.food_entries_today')
        entries_7d = get_metric(self.user, 'nutrition.food_entries_7d')
        last_entry_ts = get_metric(self.user, 'health.last_food_entry')

        if (
            daily_calories is None
            and rolling_avg is None
            and last_entry_ts is None
        ):
            return None

        result = {
            'type': 'food',
            'daily_calories': daily_calories.value if daily_calories else None,
            'average_daily_calories': (
                rolling_avg.value if rolling_avg else None
            ),
            'average_window': '7d_rolling',
            'entries_today': entries_today.value if entries_today else None,
            'entries_7d': entries_7d.value if entries_7d else None,
            'latest_date': last_entry_ts.value if last_entry_ts else None,
            'source': (
                rolling_avg.source if rolling_avg
                else (daily_calories.source if daily_calories else None)
            ),
        }

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

    def get_glucose_data(
        self,
        since_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's blood glucose data.

        Args:
            since_date: Optional datetime to filter entries from this date.
                       If None, returns all entries.
            limit: Maximum number of recent entries to include (default 10).

        Returns:
            None if no glucose entries exist for the user.
            Otherwise, a dictionary containing:
                - type (str): 'glucose'
                - count (int): Total number of entries matching criteria
                - average (float): Average glucose value
                - latest (float): Most recent glucose value
                - latest_date (datetime): Date of most recent entry
                - unit (str): Unit of measurement (mg/dL or mmol/L)
                - entries (list): Last N entries as dicts with value, unit,
                                 recorded_at, context, and trend

        Example:
            >>> service = PersonalDataService(user)
            >>> data = service.get_glucose_data(since_date=datetime(2024, 12, 1))
            >>> print(data)
            {
                'type': 'glucose',
                'count': 100,
                'average': 120.5,
                'latest': 115.0,
                'latest_date': datetime(2024, 12, 18, 8, 30),
                'unit': 'mg/dL',
                'entries': [...]
            }
        """
        # Canonical 7-day glucose average and latest reading come from
        # SAE state. We do not re-aggregate GlucoseEntry here — doing so
        # produced the 141 vs 145 divergence that triggered this layer.
        cache_key = _generate_cache_key(self.user.id, 'glucose', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        glucose_avg_7d = get_metric(self.user, 'health.glucose_avg_7d')
        latest = get_metric(self.user, 'health.latest_glucose')
        if glucose_avg_7d is None and latest is None:
            return None

        latest_unit = get_metric(self.user, 'health.latest_glucose_unit')
        variability = get_metric(self.user, 'health.glucose_variability_level')

        from apps.health.models import GlucoseEntry
        entries_qs = GlucoseEntry.objects.filter(user=self.user)
        if since_date:
            entries_qs = entries_qs.filter(recorded_at__gte=since_date)
        recent_entries = list(
            entries_qs[:limit].values(
                'value', 'unit', 'recorded_at', 'context', 'trend'
            )
        )
        entries = [
            {
                'value': float(e['value']),
                'unit': e['unit'],
                'recorded_at': e['recorded_at'],
                'context': e['context'],
                'trend': e['trend'],
            }
            for e in recent_entries
        ]

        result = {
            'type': 'glucose',
            'average': glucose_avg_7d.value if glucose_avg_7d else None,
            'average_window': '7d_rolling',
            'latest': latest.value if latest else None,
            'unit': (
                latest_unit.value if latest_unit
                else (entries[0]['unit'] if entries else 'mg/dL')
            ),
            'variability_level': variability.value if variability else None,
            'source': glucose_avg_7d.source if glucose_avg_7d else (
                latest.source if latest else None
            ),
            'entries': entries,
        }
        if entries:
            result['latest_date'] = entries[0]['recorded_at']

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

    def get_faith_data(
        self,
        since_date: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's faith activity data.

        Combines data from prayer requests, saved verses, faith milestones,
        and reading plan progress.

        Args:
            since_date: Optional datetime to filter entries from this date.
                       If None, returns all entries.

        Returns:
            None if no faith activity exists for the user.
            Otherwise, a dictionary containing:
                - type (str): 'faith'
                - prayer_requests (dict): Prayer request summary
                    - total (int): Total prayer requests
                    - active (int): Unanswered prayer requests
                    - answered (int): Answered prayer requests
                    - latest_date (datetime): Date of most recent request
                - saved_verses (int): Number of saved Scripture verses
                - milestones (int): Number of faith milestones
                - reading_plans (dict): Reading plan summary
                    - active (int): Number of active reading plans
                    - completed (int): Number of completed plans

        Example:
            >>> service = PersonalDataService(user)
            >>> data = service.get_faith_data(since_date=datetime(2024, 12, 1))
            >>> print(data)
            {
                'type': 'faith',
                'prayer_requests': {
                    'total': 15,
                    'active': 10,
                    'answered': 5,
                    'latest_date': datetime(2024, 12, 18)
                },
                'saved_verses': 20,
                'milestones': 3,
                'reading_plans': {'active': 1, 'completed': 2}
            }
        """
        # DEPRECATED: no canonical faith counts exist in SAE yet.
        # Rebuilding prayer/verse/milestone counters here bypasses the
        # signals/state layer. Until SAE exposes faith counts this
        # method returns None — surfacing the gap rather than fabricating.
        _warn_deprecated_personal_data_method("get_faith_data")
        return None

    def get_goals_data(
        self,
        since_date: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's life goals data.

        Queries LifeGoal from the purpose module and returns goal counts
        by status, completion rates, and recent achievements.

        Args:
            since_date: Optional datetime to filter entries from this date.
                       If None, returns all entries.

        Returns:
            None if no goals exist for the user.
            Otherwise, a dictionary containing:
                - type (str): 'goals'
                - total (int): Total number of goals
                - by_status (dict): Counts per status (active, paused, completed, released)
                - by_timeframe (dict): Counts per timeframe
                - completion_rate (float): Percentage of completed goals
                - recent_completed (list): Recently completed goals (title, completed_date)
                - domains (list): Unique domains with goal counts

        Example:
            >>> service = PersonalDataService(user)
            >>> data = service.get_goals_data()
            >>> print(data)
            {
                'type': 'goals',
                'total': 10,
                'by_status': {'active': 5, 'paused': 2, 'completed': 2, 'released': 1},
                'by_timeframe': {'year_1': 4, 'year_2': 3, 'ongoing': 3},
                'completion_rate': 20.0,
                'recent_completed': [
                    {'title': 'Learn Spanish', 'completed_date': date(2024, 11, 15)}
                ],
                'domains': [{'name': 'Health', 'count': 3}, {'name': 'Faith', 'count': 2}]
            }
        """
        # DEPRECATED: goals-based completion_rate (derived from
        # status counts) is a different definition from the canonical
        # milestone-based goals.completion_rate already in SAE. Until
        # the two are reconciled in SAE, this method returns None to
        # avoid narrating a conflicting rate to the LLM.
        _warn_deprecated_personal_data_method("get_goals_data")
        return None

    def get_mood_data(
        self,
        since_date: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's mood data from journal entries.

        Args:
            since_date: Optional datetime to filter entries from this date.
                       If None, returns all entries.

        Returns:
            None if no journal entries with mood exist for the user.
            Otherwise, a dictionary containing:
                - type (str): 'mood'
                - count (int): Total number of entries with mood data
                - mood_distribution (dict): Counts per mood level
                - most_common (str): The most frequently recorded mood
                - latest_mood (str): The most recent mood recorded
                - latest_date (date): Date of most recent entry with mood

        Example:
            >>> service = PersonalDataService(user)
            >>> data = service.get_mood_data(since_date=datetime(2024, 12, 1))
            >>> print(data)
            {
                'type': 'mood',
                'count': 15,
                'mood_distribution': {'great': 3, 'good': 7, 'okay': 4, 'low': 1},
                'most_common': 'good',
                'latest_mood': 'good',
                'latest_date': date(2024, 12, 18)
            }
        """
        # Canonical mood distribution, trend, and latest mood come
        # from SAE journal state. Raw JournalEntry.annotate(Count) has
        # been removed — see journal.mood_* in the metric registry.
        cache_key = _generate_cache_key(self.user.id, 'mood', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        mood_avg_7d = get_metric(self.user, 'journal.mood_avg_7d')
        mood_trend = get_metric(self.user, 'journal.mood_trend')
        distribution = get_metric(self.user, 'journal.mood_distribution')
        latest_mood = get_metric(self.user, 'journal.last_mood')
        last_entry_ts = get_metric(self.user, 'journal.last_entry')

        if (
            mood_avg_7d is None
            and distribution is None
            and latest_mood is None
        ):
            return None

        most_common = None
        dist_value = distribution.value if distribution else None
        if isinstance(dist_value, dict) and dist_value:
            most_common = max(dist_value.items(), key=lambda kv: kv[1])[0]

        result = {
            'type': 'mood',
            'mood_avg_7d': mood_avg_7d.value if mood_avg_7d else None,
            'mood_trend': mood_trend.value if mood_trend else None,
            'mood_distribution': dist_value,
            'most_common': most_common,
            'latest_mood': latest_mood.value if latest_mood else None,
            'latest_date': last_entry_ts.value if last_entry_ts else None,
            'source': (
                distribution.source if distribution
                else (mood_avg_7d.source if mood_avg_7d else None)
            ),
        }

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

    def get_heart_rate_data(
        self,
        since_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's heart rate data.

        Args:
            since_date: Optional datetime to filter entries from this date.
                       If None, returns all entries.
            limit: Maximum number of recent entries to include (default 10).

        Returns:
            None if no heart rate entries exist for the user.
            Otherwise, a dictionary containing:
                - type (str): 'heart_rate'
                - count (int): Total number of entries matching criteria
                - average (float): Average heart rate value
                - latest (int): Most recent heart rate value
                - latest_date (datetime): Date of most recent entry
                - context (str): Context of latest reading (resting, active, etc.)
                - entries (list): Last N entries
        """
        # DEPRECATED: not in the priority-10 migration set. SAE does
        # hold heart_rate_avg_7d and latest_heart_rate as canonical
        # signals — this method should be removed in favor of a direct
        # get_metric() call at the caller, or migrated in a later
        # phase. Until then, return None to avoid parallel-truth
        # injection into the LLM prompt.
        _warn_deprecated_personal_data_method("get_heart_rate_data")
        return None

    def get_blood_pressure_data(
        self,
        since_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's blood pressure data.

        Args:
            since_date: Optional datetime to filter entries from this date.
            limit: Maximum number of recent entries to include (default 10).

        Returns:
            None if no blood pressure entries exist for the user.
            Otherwise, a dictionary containing:
                - type (str): 'blood_pressure'
                - count (int): Total number of entries
                - avg_systolic (float): Average systolic value
                - avg_diastolic (float): Average diastolic value
                - latest_systolic (int): Most recent systolic value
                - latest_diastolic (int): Most recent diastolic value
                - latest_date (datetime): Date of most recent entry
                - entries (list): Last N entries
        """
        # DEPRECATED: no canonical BP 7-day/30-day average exists in
        # SAE. BP averaging was re-derived here and also in dashboard
        # views — a divergence we accept losing temporarily rather
        # than rebuilding. The next step is to add bp_systolic_avg_7d
        # / bp_diastolic_avg_7d to SAE build_health_state.
        _warn_deprecated_personal_data_method("get_blood_pressure_data")
        return None

    def get_blood_oxygen_data(
        self,
        since_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's blood oxygen (SpO2) data.

        Args:
            since_date: Optional datetime to filter entries from this date.
            limit: Maximum number of recent entries to include (default 10).

        Returns:
            None if no blood oxygen entries exist for the user.
            Otherwise, a dictionary containing:
                - type (str): 'blood_oxygen'
                - count (int): Total number of entries
                - average (float): Average SpO2 value
                - latest (int): Most recent SpO2 value
                - latest_date (datetime): Date of most recent entry
                - entries (list): Last N entries
        """
        cache_key = _generate_cache_key(self.user.id, 'blood_oxygen', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        from apps.health.models import BloodOxygenEntry

        queryset = BloodOxygenEntry.objects.filter(user=self.user)

        # DEPRECATED: not in the priority-10 migration set. SAE has
        # canonical blood_oxygen_avg_7d and latest_blood_oxygen — a
        # follow-up phase should wire this method (or its callers)
        # through get_metric(). Return None in the meantime.
        _warn_deprecated_personal_data_method("get_blood_oxygen_data")
        return None

    def get_workout_data(
        self,
        since_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's workout session data.

        Args:
            since_date: Optional datetime to filter entries from this date.
            limit: Maximum number of recent entries to include (default 10).

        Returns:
            None if no workout sessions exist for the user.
            Otherwise, a dictionary containing:
                - type (str): 'workout'
                - count (int): Total number of sessions
                - total_minutes (int): Total workout time in minutes
                - avg_duration (float): Average workout duration
                - latest_date (date): Date of most recent session
                - workouts (list): Last N sessions
        """
        # Canonical workout counts and minutes come from SAE fitness
        # state. Raw WorkoutSession aggregation has been removed — see
        # fitness.workouts_7d, fitness.workouts_30d, and
        # fitness.workout_minutes_7d in the metric registry.
        cache_key = _generate_cache_key(self.user.id, 'workout', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        workouts_7d = get_metric(self.user, 'fitness.workouts_7d')
        workouts_30d = get_metric(self.user, 'fitness.workouts_30d')
        minutes_7d = get_metric(self.user, 'fitness.workout_minutes_7d')
        last_workout_date = get_metric(self.user, 'fitness.last_workout_date')

        if workouts_7d is None and workouts_30d is None and last_workout_date is None:
            return None

        from apps.health.models import WorkoutSession
        entries_qs = WorkoutSession.objects.filter(user=self.user)
        if since_date:
            entries_qs = entries_qs.filter(date__gte=_to_date(since_date))
        recent_sessions = entries_qs[:limit]
        workouts = [
            {
                'name': session.name,
                'date': session.date,
                'duration_minutes': session.duration_minutes,
                'calories_burned': session.calories_burned,
                'distance_miles': (
                    float(session.distance_miles)
                    if session.distance_miles else None
                ),
                'avg_heart_rate': session.avg_heart_rate,
                'workout_type': session.workout_type,
                'source': session.source,
                'notes': session.notes,
            }
            for session in recent_sessions
        ]

        result = {
            'type': 'workout',
            'workouts_7d': workouts_7d.value if workouts_7d else None,
            'workouts_30d': workouts_30d.value if workouts_30d else None,
            'total_minutes_7d': minutes_7d.value if minutes_7d else None,
            'latest_date': (
                last_workout_date.value if last_workout_date
                else (workouts[0]['date'] if workouts else None)
            ),
            'source': (
                workouts_7d.source if workouts_7d
                else (last_workout_date.source if last_workout_date else None)
            ),
            'workouts': workouts,
        }

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

    def get_fasting_data(
        self,
        since_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's fasting window data.

        Args:
            since_date: Optional datetime to filter entries from this date.
            limit: Maximum number of recent entries to include (default 10).

        Returns:
            None if no fasting windows exist for the user.
            Otherwise, a dictionary containing:
                - type (str): 'fasting'
                - total_fasts (int): Total number of completed fasts
                - active_fast (dict or None): Currently active fast if any
                - avg_duration_hours (float): Average fast duration in hours
                - longest_fast_hours (float): Longest fast duration
                - recent_fasts (list): Last N completed fasts
        """
        # DEPRECATED: SAE has canonical fasting.rolling_7d_avg_fast_duration,
        # fasting.fasts_7d, and fasting.current_fast_* keys. This method
        # was not in the priority-10 scope. Return None until the
        # fasting method is migrated in a later phase.
        _warn_deprecated_personal_data_method("get_fasting_data")
        return None

    def get_water_data(
        self,
        since_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's water/hydration data.

        Args:
            since_date: Optional datetime to filter entries from this date.
            limit: Maximum number of recent entries to include (default 10).

        Returns:
            None if no water entries exist for the user.
            Otherwise, a dictionary containing:
                - type (str): 'water'
                - total_entries (int): Total number of water entries
                - today_oz (float): Today's total water intake in ounces
                - today_percentage (float): Percentage of daily goal achieved
                - today_goal_met (bool): Whether today's goal is met
                - avg_daily_oz (float): 7-day average daily intake
                - entries (list): Recent water entries
        """
        # Canonical today + 7-day water values come from SAE. Raw
        # WaterEntry aggregation has been removed — see
        # health.water_today_oz / water_avg_oz_7d in the metric registry.
        cache_key = _generate_cache_key(self.user.id, 'water', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        today_oz = get_metric(self.user, 'health.water_today_oz')
        today_pct = get_metric(self.user, 'health.water_today_pct')
        avg_oz_7d = get_metric(self.user, 'health.water_avg_oz_7d')

        if today_oz is None and avg_oz_7d is None:
            return None

        from apps.health.models import WaterEntry
        entries_qs = WaterEntry.objects.filter(user=self.user)
        if since_date:
            entries_qs = entries_qs.filter(recorded_at__gte=since_date)
        recent_entries = list(
            entries_qs[:limit].values(
                'amount', 'unit', 'container', 'logged_date', 'recorded_at', 'notes'
            )
        )
        entries = [
            {
                'amount': float(entry['amount']),
                'unit': entry['unit'],
                'container': entry['container'],
                'logged_date': entry['logged_date'],
                'recorded_at': entry['recorded_at'],
                'notes': entry['notes'],
            }
            for entry in recent_entries
        ]

        result = {
            'type': 'water',
            'today_oz': today_oz.value if today_oz else None,
            'today_percentage': today_pct.value if today_pct else None,
            'avg_daily_oz': avg_oz_7d.value if avg_oz_7d else None,
            'avg_window': '7d_rolling',
            'source': (
                today_oz.source if today_oz
                else (avg_oz_7d.source if avg_oz_7d else None)
            ),
            'entries': entries,
        }

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

    def get_steps_data(
        self,
        since_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve and summarize the user's steps data.

        Canonical 7-day average steps come from SAE state. We do not
        re-aggregate StepsEntry here.
        """
        cache_key = _generate_cache_key(self.user.id, 'steps', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        avg_7d = get_metric(self.user, 'health.steps_avg_7d')
        entries_7d = get_metric(self.user, 'health.steps_entries_7d')
        if avg_7d is None and entries_7d is None:
            return None

        from apps.health.models import StepsEntry
        entries_qs = StepsEntry.objects.filter(user=self.user)
        if since_date:
            entries_qs = entries_qs.filter(logged_date__gte=_to_date(since_date))
        recent_entries = entries_qs.order_by('-logged_date')[:limit]
        entries = [
            {
                'count': entry.count,
                'logged_date': entry.logged_date,
                'distance_miles': (
                    float(entry.distance_miles) if entry.distance_miles else None
                ),
                'calories_burned': entry.calories_burned,
                'exercise_minutes': entry.exercise_minutes,
                'flights_climbed': entry.flights_climbed,
            }
            for entry in recent_entries
        ]

        result = {
            'type': 'steps',
            'average': avg_7d.value if avg_7d else None,
            'average_window': '7d_rolling',
            'entries_7d': entries_7d.value if entries_7d else None,
            'latest': entries[0]['count'] if entries else None,
            'latest_date': entries[0]['logged_date'] if entries else None,
            'source': avg_7d.source if avg_7d else None,
            'entries': entries,
        }

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

    def get_sleep_data(
        self,
        since_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve and summarize the user's sleep data.

        Canonical 7-day average and last-night hours are read from SAE
        state. Recent entries are returned as a non-aggregated list so
        the LLM can narrate specific nights.
        """
        cache_key = _generate_cache_key(self.user.id, 'sleep', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        avg_7d = get_metric(self.user, 'health.sleep_avg_hours_7d')
        last_night = get_metric(self.user, 'health.sleep_last_night_hours')
        entries_7d = get_metric(self.user, 'health.sleep_entries_7d')
        last_entry_ts = get_metric(self.user, 'health.last_sleep_entry')
        if avg_7d is None and last_night is None and last_entry_ts is None:
            return None

        from apps.health.models import SleepEntry
        entries_qs = SleepEntry.objects.filter(user=self.user)
        if since_date:
            entries_qs = entries_qs.filter(sleep_date__gte=_to_date(since_date))
        recent_entries = entries_qs.order_by('-sleep_date')[:limit]
        entries = [
            {
                'sleep_date': entry.sleep_date,
                'hours': (
                    round(entry.asleep_duration_minutes / 60, 1)
                    if entry.asleep_duration_minutes else 0
                ),
                'quality': entry.quality,
                'notes': entry.notes,
            }
            for entry in recent_entries
        ]

        result = {
            'type': 'sleep',
            'avg_hours': avg_7d.value if avg_7d else None,
            'avg_window': '7d_rolling',
            'latest_hours': last_night.value if last_night else None,
            'latest_date': last_entry_ts.value if last_entry_ts else None,
            'entries_7d': entries_7d.value if entries_7d else None,
            'source': avg_7d.source if avg_7d else (
                last_night.source if last_night else None
            ),
            'entries': entries,
        }
        if entries:
            result['latest_quality'] = entries[0].get('quality')

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

    def get_mobility_data(
        self,
        since_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """DEPRECATED — no canonical mobility metrics in SAE yet."""
        _warn_deprecated_personal_data_method("get_mobility_data")
        return None

    def get_heart_rate_events_data(
        self,
        since_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """DEPRECATED — no canonical HR-event counters in SAE yet."""
        _warn_deprecated_personal_data_method("get_heart_rate_events_data")
        return None

    def get_audio_exposure_data(
        self,
        since_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """DEPRECATED — no canonical audio-exposure metrics in SAE yet."""
        _warn_deprecated_personal_data_method("get_audio_exposure_data")
        return None

    def get_dietary_nutrients_data(
        self,
        since_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """DEPRECATED — HealthKit dietary nutrient averages are not
        yet a canonical SAE signal. Canonical nutrition metrics live
        on the nutrition module (daily_calories, rolling_7d_*)."""
        _warn_deprecated_personal_data_method("get_dietary_nutrients_data")
        return None

    def get_task_data(
        self,
        since_date: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and summarize the user's task data.

        Args:
            since_date: Optional datetime to filter entries from this date.

        Returns:
            None if no tasks exist for the user.
            Otherwise, a dictionary containing:
                - type (str): 'task'
                - total (int): Total number of tasks
                - completed (int): Number of completed tasks
                - pending (int): Number of pending tasks
                - overdue (int): Number of overdue tasks
                - due_today (int): Number of tasks due today
                - completion_rate (float): Percentage of completed tasks
        """
        # DEPRECATED: SAE build_task_state() already computes
        # overdue_count, completed_today, due_today, and time-horizon
        # task buckets. Consumers should read from get_module_state(
        # user, 'tasks') directly or migrate to a canonical task
        # metric access path.
        _warn_deprecated_personal_data_method("get_task_data")
        return None

    def get_user_data(
        self,
        since_date: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve the user's profile data (non-sensitive information).

        This method returns user profile information that the assistant
        can use to personalize responses (e.g., name, location, timezone).

        Args:
            since_date: Not used for user data, but accepted for API consistency.

        Returns:
            None if user has no preferences set.
            Otherwise, a dictionary containing:
                - type (str): 'user'
                - name (str): User's full name or email
                - first_name (str): User's first name
                - location_city (str): User's city (if set)
                - location_country (str): User's country (if set)
                - timezone (str): User's timezone
                - gender (str): User's gender preference (if set)

        Example:
            >>> service = PersonalDataService(user)
            >>> data = service.get_user_data()
            >>> print(data)
            {
                'type': 'user',
                'name': 'Danny Jenkins',
                'first_name': 'Danny',
                'location_city': 'Maryville',
                'location_country': 'United States',
                'timezone': 'America/New_York',
                'gender': 'male'
            }
        """
        # Check cache first
        cache_key = _generate_cache_key(self.user.id, 'user', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        # Get user preferences from database (avoid cached relation)
        from apps.users.models import UserPreferences
        try:
            prefs = UserPreferences.objects.get(user=self.user)
        except UserPreferences.DoesNotExist:
            prefs = None

        result = {
            'type': 'user',
            'name': self.user.get_full_name() or self.user.email,
            'first_name': self.user.first_name or '',
            'location_city': prefs.location_city if prefs else '',
            'location_country': prefs.location_country if prefs else '',
            'timezone': prefs.timezone_iana if prefs else 'UTC',
            'gender': prefs.gender if prefs else None,
        }

        # Cache the result
        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)

        return result

    def get_health_summary_data(
        self,
        since_date: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a comprehensive summary across ALL health data types.

        This is triggered when users ask generic questions like "what health data
        do you have?" or "can you see my HealthKit data?" — it pulls from every
        health model and provides a consolidated overview.

        Args:
            since_date: Optional datetime to filter entries from this date.

        Returns:
            A dict with summaries from each health type that has data, or None.
        """
        # DEPRECATED: this method re-aggregated 15+ health tables at
        # request time — a second analytics layer that duplicated SAE.
        # It was the single largest parallel-truth violation flagged
        # in the 2026-04-20 metric access audit. Callers should read
        # individual canonical metrics via get_metric() instead.
        _warn_deprecated_personal_data_method("get_health_summary_data")
        return None

    def query_by_intent(
        self,
        data_types: List[str],
        since_date: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Query multiple data types based on detected intent.

        This is the unified entry point for fetching user data based on
        the data types identified by the intent detector.

        Args:
            data_types: List of data type strings from the intent detector.
                       Supported types: 'weight', 'journal', 'medication', 'food', 'mood'
            since_date: Optional datetime to filter entries from this date.
                       Passed to all underlying query methods.

        Returns:
            None if no data exists for any of the requested types.
            Otherwise, a dictionary with data type keys mapped to their
            respective query results.

        Example:
            >>> service = PersonalDataService(user)
            >>> data = service.query_by_intent(
            ...     data_types=['weight', 'journal'],
            ...     since_date=datetime(2024, 12, 1)
            ... )
            >>> print(data)
            {
                'weight': {'type': 'weight', 'count': 15, ...},
                'journal': {'type': 'journal', 'count': 10, ...}
            }
        """
        # Map data type strings to method references
        query_map: Dict[str, callable] = {
            'weight': self.get_weight_data,
            'journal': self.get_journal_data,
            'medication': self.get_medication_data,
            'food': self.get_food_data,
            'mood': self.get_mood_data,
            'glucose': self.get_glucose_data,
            'faith': self.get_faith_data,
            'goals': self.get_goals_data,
            'user': self.get_user_data,
            # New data types
            'heart_rate': self.get_heart_rate_data,
            'blood_pressure': self.get_blood_pressure_data,
            'blood_oxygen': self.get_blood_oxygen_data,
            'workout': self.get_workout_data,
            'fasting': self.get_fasting_data,
            'water': self.get_water_data,
            'task': self.get_task_data,
            'steps': self.get_steps_data,
            'sleep': self.get_sleep_data,
            'mobility': self.get_mobility_data,
            'heart_rate_events': self.get_heart_rate_events_data,
            'audio_exposure': self.get_audio_exposure_data,
            'dietary_nutrients': self.get_dietary_nutrients_data,
            'health_summary': self.get_health_summary_data,
        }

        # Collect results
        results: Dict[str, Any] = {}

        for data_type in data_types:
            # Get the corresponding method
            method = query_map.get(data_type)
            if method is None:
                # Unknown data type, skip
                continue

            # Call the method with since_date
            result = method(since_date=since_date)

            # Only add to results if data exists (not None)
            if result is not None:
                results[data_type] = result

        # Return None if no data found for any type
        if not results:
            return None

        return results
