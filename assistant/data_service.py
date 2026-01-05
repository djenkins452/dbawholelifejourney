"""
Personal Data Service for WLJ Personal Data Query System.

This module provides methods to query and summarize user's personal
wellness data from various models (weight, journal, mood, etc.).

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

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Count, QuerySet, Sum
from django.utils import timezone


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
        # Check cache first
        cache_key = _generate_cache_key(self.user.id, 'weight', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        # Import here to avoid circular imports and allow testing without Django
        from apps.health.models import WeightEntry

        # Build base queryset
        queryset = WeightEntry.objects.filter(user=self.user)

        # Apply date filter if provided
        if since_date:
            queryset = queryset.filter(recorded_at__gte=since_date)

        # Check if any entries exist
        if not queryset.exists():
            return None

        # Get aggregate statistics
        count = queryset.count()
        avg_result = queryset.aggregate(avg_value=Avg('value'))
        average = float(avg_result['avg_value']) if avg_result['avg_value'] else 0.0

        # Get latest entry (queryset is ordered by -recorded_at by default)
        latest_entry = queryset.first()
        latest_value = float(latest_entry.value)
        latest_date = latest_entry.recorded_at
        latest_unit = latest_entry.unit

        # Get recent entries for context
        recent_entries = list(
            queryset[:limit].values('value', 'unit', 'recorded_at', 'notes')
        )

        # Convert Decimal values to float for JSON serialization
        entries = []
        for entry in recent_entries:
            entries.append({
                'value': float(entry['value']),
                'unit': entry['unit'],
                'recorded_at': entry['recorded_at'],
                'notes': entry['notes'],
            })

        result = {
            'type': 'weight',
            'count': count,
            'average': round(average, 1),
            'latest': latest_value,
            'latest_date': latest_date,
            'unit': latest_unit,
            'entries': entries,
        }

        # Cache the result
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
        # Check cache first
        cache_key = _generate_cache_key(self.user.id, 'journal', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        # Import here to avoid circular imports and allow testing without Django
        from apps.journal.models import JournalEntry

        # Build base queryset - filter by user (SoftDeleteManager excludes deleted records)
        queryset = JournalEntry.objects.filter(user=self.user)

        # Apply date filter if provided
        if since_date:
            queryset = queryset.filter(entry_date__gte=since_date)

        # Check if any entries exist
        if not queryset.exists():
            return None

        # Get count
        count = queryset.count()

        # Get latest entry (queryset is ordered by -entry_date, -created_at by default)
        latest_entry = queryset.first()
        latest_date = latest_entry.entry_date

        result = {
            'type': 'journal',
            'count': count,
            'latest_date': latest_date,
        }

        # Cache the result
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
        # Check cache first
        cache_key = _generate_cache_key(self.user.id, 'medication', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        # Import here to avoid circular imports and allow testing without Django
        from apps.health.models import MedicineLog

        # Build base queryset - filter by user (SoftDeleteManager excludes deleted records)
        queryset = MedicineLog.objects.filter(user=self.user)

        # Apply date filter if provided
        if since_date:
            queryset = queryset.filter(scheduled_date__gte=since_date)

        # Check if any entries exist
        if not queryset.exists():
            return None

        # Get total log count
        total_logs = queryset.count()

        # Get unique days with logs using dates() aggregation
        unique_dates = queryset.values_list('scheduled_date', flat=True).distinct()
        days_logged = len(set(unique_dates))

        # Calculate total_days from since_date or first log date to now
        if since_date:
            # Use since_date as the start
            start_date = since_date.date() if isinstance(since_date, datetime) else since_date
        else:
            # Use the earliest log date as start
            earliest_log = queryset.order_by('scheduled_date').first()
            start_date = earliest_log.scheduled_date

        # Get today's date for the end of the period
        today = timezone.now().date()
        total_days = (today - start_date).days + 1  # +1 to include both start and end dates

        # Calculate consistency percentage
        if total_days > 0:
            consistency_percent = round((days_logged / total_days) * 100, 1)
        else:
            consistency_percent = 0.0

        result = {
            'type': 'medication',
            'total_logs': total_logs,
            'days_logged': days_logged,
            'total_days': total_days,
            'consistency_percent': consistency_percent,
        }

        # Cache the result
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
        # Check cache first
        cache_key = _generate_cache_key(self.user.id, 'food', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        # Import here to avoid circular imports and allow testing without Django
        from apps.health.models import FoodEntry

        # Build base queryset - filter by user
        queryset = FoodEntry.objects.filter(user=self.user)

        # Apply date filter if provided
        if since_date:
            queryset = queryset.filter(logged_date__gte=since_date)

        # Check if any entries exist
        if not queryset.exists():
            return None

        # Get total entry count
        total_entries = queryset.count()

        # Get total calories
        cal_result = queryset.aggregate(total_cal=Sum('total_calories'))
        total_calories = float(cal_result['total_cal']) if cal_result['total_cal'] else 0.0

        # Get unique days for average calculation
        unique_dates = queryset.values_list('logged_date', flat=True).distinct()
        days_count = len(set(unique_dates))

        # Calculate average daily calories
        if days_count > 0:
            average_daily_calories = round(total_calories / days_count, 1)
        else:
            average_daily_calories = 0.0

        # Get latest entry (queryset is ordered by -logged_date by default)
        latest_entry = queryset.first()
        latest_date = latest_entry.logged_date

        result = {
            'type': 'food',
            'total_entries': total_entries,
            'total_calories': round(total_calories, 1),
            'average_daily_calories': average_daily_calories,
            'latest_date': latest_date,
        }

        # Cache the result
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
        # Check cache first
        cache_key = _generate_cache_key(self.user.id, 'glucose', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        # Import here to avoid circular imports and allow testing without Django
        from apps.health.models import GlucoseEntry

        # Build base queryset
        queryset = GlucoseEntry.objects.filter(user=self.user)

        # Apply date filter if provided
        if since_date:
            queryset = queryset.filter(recorded_at__gte=since_date)

        # Check if any entries exist
        if not queryset.exists():
            return None

        # Get aggregate statistics
        count = queryset.count()
        avg_result = queryset.aggregate(avg_value=Avg('value'))
        average = float(avg_result['avg_value']) if avg_result['avg_value'] else 0.0

        # Get latest entry (queryset is ordered by -recorded_at by default)
        latest_entry = queryset.first()
        latest_value = float(latest_entry.value)
        latest_date = latest_entry.recorded_at
        latest_unit = latest_entry.unit

        # Get recent entries for context
        recent_entries = list(
            queryset[:limit].values('value', 'unit', 'recorded_at', 'context', 'trend')
        )

        # Convert Decimal values to float for JSON serialization
        entries = []
        for entry in recent_entries:
            entries.append({
                'value': float(entry['value']),
                'unit': entry['unit'],
                'recorded_at': entry['recorded_at'],
                'context': entry['context'],
                'trend': entry['trend'],
            })

        result = {
            'type': 'glucose',
            'count': count,
            'average': round(average, 1),
            'latest': latest_value,
            'latest_date': latest_date,
            'unit': latest_unit,
            'entries': entries,
        }

        # Cache the result
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
        # Check cache first
        cache_key = _generate_cache_key(self.user.id, 'faith', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        # Import here to avoid circular imports and allow testing without Django
        from apps.faith.models import (
            FaithMilestone, PrayerRequest, SavedVerse, UserReadingPlan
        )

        # Initialize result structure
        result = {
            'type': 'faith',
            'prayer_requests': None,
            'saved_verses': 0,
            'milestones': 0,
            'reading_plans': {'active': 0, 'completed': 0},
        }

        has_data = False

        # Query prayer requests
        prayer_qs = PrayerRequest.objects.filter(user=self.user)
        if since_date:
            prayer_qs = prayer_qs.filter(created_at__gte=since_date)

        if prayer_qs.exists():
            has_data = True
            total_prayers = prayer_qs.count()
            answered_prayers = prayer_qs.filter(is_answered=True).count()
            active_prayers = total_prayers - answered_prayers
            latest_prayer = prayer_qs.first()

            result['prayer_requests'] = {
                'total': total_prayers,
                'active': active_prayers,
                'answered': answered_prayers,
                'latest_date': latest_prayer.created_at,
            }

        # Query saved verses
        verse_qs = SavedVerse.objects.filter(user=self.user)
        if since_date:
            verse_qs = verse_qs.filter(created_at__gte=since_date)

        verse_count = verse_qs.count()
        if verse_count > 0:
            has_data = True
            result['saved_verses'] = verse_count

        # Query faith milestones
        milestone_qs = FaithMilestone.objects.filter(user=self.user)
        if since_date:
            milestone_qs = milestone_qs.filter(created_at__gte=since_date)

        milestone_count = milestone_qs.count()
        if milestone_count > 0:
            has_data = True
            result['milestones'] = milestone_count

        # Query reading plans (status-based, not date-based)
        active_plans = UserReadingPlan.objects.filter(
            user=self.user, status='active'
        ).count()
        completed_plans = UserReadingPlan.objects.filter(
            user=self.user, status='completed'
        ).count()

        if active_plans > 0 or completed_plans > 0:
            has_data = True
            result['reading_plans'] = {
                'active': active_plans,
                'completed': completed_plans,
            }

        # Return None if no faith data exists
        if not has_data:
            return None

        # Cache the result
        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)

        return result

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
        # Check cache first
        cache_key = _generate_cache_key(self.user.id, 'goals', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        # Import here to avoid circular imports and allow testing without Django
        from apps.purpose.models import LifeGoal

        # Build base queryset
        queryset = LifeGoal.objects.filter(user=self.user)

        # Apply date filter if provided (based on created_at)
        if since_date:
            queryset = queryset.filter(created_at__gte=since_date)

        # Check if any goals exist
        if not queryset.exists():
            return None

        # Get total count
        total = queryset.count()

        # Get counts by status
        status_counts = queryset.values('status').annotate(count=Count('status'))
        by_status = {item['status']: item['count'] for item in status_counts}

        # Get counts by timeframe
        timeframe_counts = queryset.values('timeframe').annotate(count=Count('timeframe'))
        by_timeframe = {item['timeframe']: item['count'] for item in timeframe_counts}

        # Calculate completion rate
        completed_count = by_status.get('completed', 0)
        if total > 0:
            completion_rate = round((completed_count / total) * 100, 1)
        else:
            completion_rate = 0.0

        # Get recently completed goals (up to 5)
        completed_goals = queryset.filter(
            status='completed',
            completed_date__isnull=False
        ).order_by('-completed_date')[:5]

        recent_completed = [
            {
                'title': goal.title,
                'completed_date': goal.completed_date,
            }
            for goal in completed_goals
        ]

        # Get domains with goal counts (only for goals that have a domain)
        domain_counts = queryset.filter(
            domain__isnull=False
        ).values('domain__name').annotate(count=Count('domain')).order_by('-count')

        domains = [
            {'name': item['domain__name'], 'count': item['count']}
            for item in domain_counts
        ]

        result = {
            'type': 'goals',
            'total': total,
            'by_status': by_status,
            'by_timeframe': by_timeframe,
            'completion_rate': completion_rate,
            'recent_completed': recent_completed,
            'domains': domains,
        }

        # Cache the result
        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)

        return result

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
        # Check cache first
        cache_key = _generate_cache_key(self.user.id, 'mood', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        # Import here to avoid circular imports and allow testing without Django
        from apps.journal.models import JournalEntry

        # Build base queryset - filter by user and has mood (SoftDeleteManager excludes deleted records)
        queryset = JournalEntry.objects.filter(
            user=self.user
        ).exclude(mood='')

        # Apply date filter if provided
        if since_date:
            queryset = queryset.filter(entry_date__gte=since_date)

        # Check if any entries exist
        if not queryset.exists():
            return None

        # Get count of entries with mood
        count = queryset.count()

        # Get mood distribution (counts per mood level)
        mood_counts = queryset.values('mood').annotate(
            count=Count('mood')
        ).order_by('-count')

        mood_distribution = {}
        most_common = None
        for item in mood_counts:
            mood_distribution[item['mood']] = item['count']
            if most_common is None:
                most_common = item['mood']

        # Get latest entry with mood (queryset is ordered by -entry_date, -created_at)
        latest_entry = queryset.first()
        latest_mood = latest_entry.mood
        latest_date = latest_entry.entry_date

        result = {
            'type': 'mood',
            'count': count,
            'mood_distribution': mood_distribution,
            'most_common': most_common,
            'latest_mood': latest_mood,
            'latest_date': latest_date,
        }

        # Cache the result
        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)

        return result

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
