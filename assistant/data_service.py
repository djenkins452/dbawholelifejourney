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

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from django.core.cache import cache
from django.db.models import Avg, Count, Sum
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

        # Get earliest entry for streak/consistency calculations
        earliest_entry = queryset.order_by('entry_date').first()
        earliest_date = earliest_entry.entry_date

        # Calculate days since first entry and missed days
        from apps.core.utils import get_user_today
        today = get_user_today(self.user)
        total_days = (today - earliest_date).days + 1  # inclusive

        # Get unique journal dates for streak and missed day calculations
        journal_dates = set(
            queryset.values_list('entry_date', flat=True).distinct()
        )
        days_with_entries = len(journal_dates)
        missed_days = total_days - days_with_entries

        # Calculate current streak (consecutive days ending today or yesterday)
        current_streak = 0
        check_date = today
        while check_date in journal_dates:
            current_streak += 1
            check_date -= timedelta(days=1)

        # If streak is 0, check if yesterday had an entry (user may not have
        # journaled yet today)
        if current_streak == 0:
            check_date = today - timedelta(days=1)
            while check_date in journal_dates:
                current_streak += 1
                check_date -= timedelta(days=1)

        # Calculate this week's entries (Mon-Sun)
        start_of_week = today - timedelta(days=today.weekday())
        this_week_count = queryset.filter(
            entry_date__gte=start_of_week
        ).count()

        # Consistency percentage
        consistency_pct = round((days_with_entries / total_days) * 100, 1) if total_days > 0 else 0

        # Calculate actual missed dates (cap at 30 most recent for prompt size)
        all_dates_in_range = set()
        d = earliest_date
        while d <= today:
            all_dates_in_range.add(d)
            d += timedelta(days=1)
        missed_date_list = sorted(all_dates_in_range - journal_dates, reverse=True)[:30]

        result = {
            'type': 'journal',
            'count': count,
            'latest_date': latest_date,
            'earliest_date': earliest_date,
            'total_days_since_start': total_days,
            'days_with_entries': days_with_entries,
            'missed_days': missed_days,
            'missed_dates': missed_date_list,
            'current_streak': current_streak,
            'this_week_count': this_week_count,
            'consistency_percent': consistency_pct,
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
        # Check cache first
        cache_key = _generate_cache_key(self.user.id, 'heart_rate', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        from apps.health.models import HeartRateEntry

        queryset = HeartRateEntry.objects.filter(user=self.user)

        if since_date:
            queryset = queryset.filter(recorded_at__gte=since_date)

        if not queryset.exists():
            return None

        count = queryset.count()
        avg_result = queryset.aggregate(avg_value=Avg('bpm'))
        average = float(avg_result['avg_value']) if avg_result['avg_value'] else 0.0

        latest_entry = queryset.first()
        latest_value = latest_entry.bpm
        latest_date = latest_entry.recorded_at
        latest_context = latest_entry.context

        recent_entries = list(
            queryset[:limit].values('bpm', 'recorded_at', 'context', 'notes')
        )

        entries = [
            {
                'bpm': entry['bpm'],
                'recorded_at': entry['recorded_at'],
                'context': entry['context'],
                'notes': entry['notes'],
            }
            for entry in recent_entries
        ]

        result = {
            'type': 'heart_rate',
            'count': count,
            'average': round(average, 1),
            'latest': latest_value,
            'latest_date': latest_date,
            'context': latest_context,
            'entries': entries,
        }

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

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
        cache_key = _generate_cache_key(self.user.id, 'blood_pressure', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        from apps.health.models import BloodPressureEntry

        queryset = BloodPressureEntry.objects.filter(user=self.user)

        if since_date:
            queryset = queryset.filter(recorded_at__gte=since_date)

        if not queryset.exists():
            return None

        count = queryset.count()
        avg_result = queryset.aggregate(
            avg_sys=Avg('systolic'),
            avg_dia=Avg('diastolic')
        )
        avg_systolic = float(avg_result['avg_sys']) if avg_result['avg_sys'] else 0.0
        avg_diastolic = float(avg_result['avg_dia']) if avg_result['avg_dia'] else 0.0

        latest_entry = queryset.first()
        latest_systolic = latest_entry.systolic
        latest_diastolic = latest_entry.diastolic
        latest_date = latest_entry.recorded_at

        recent_entries = list(
            queryset[:limit].values('systolic', 'diastolic', 'recorded_at', 'notes')
        )

        entries = [
            {
                'systolic': entry['systolic'],
                'diastolic': entry['diastolic'],
                'recorded_at': entry['recorded_at'],
                'notes': entry['notes'],
            }
            for entry in recent_entries
        ]

        result = {
            'type': 'blood_pressure',
            'count': count,
            'avg_systolic': round(avg_systolic, 1),
            'avg_diastolic': round(avg_diastolic, 1),
            'latest_systolic': latest_systolic,
            'latest_diastolic': latest_diastolic,
            'latest_date': latest_date,
            'entries': entries,
        }

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

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

        if since_date:
            queryset = queryset.filter(recorded_at__gte=since_date)

        if not queryset.exists():
            return None

        count = queryset.count()
        avg_result = queryset.aggregate(avg_value=Avg('spo2'))
        average = float(avg_result['avg_value']) if avg_result['avg_value'] else 0.0

        latest_entry = queryset.first()
        latest_value = latest_entry.spo2
        latest_date = latest_entry.recorded_at

        recent_entries = list(
            queryset[:limit].values('spo2', 'recorded_at', 'notes')
        )

        entries = [
            {
                'spo2': entry['spo2'],
                'recorded_at': entry['recorded_at'],
                'notes': entry['notes'],
            }
            for entry in recent_entries
        ]

        result = {
            'type': 'blood_oxygen',
            'count': count,
            'average': round(average, 1),
            'latest': latest_value,
            'latest_date': latest_date,
            'entries': entries,
        }

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

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
        cache_key = _generate_cache_key(self.user.id, 'workout', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        from apps.health.models import WorkoutSession

        queryset = WorkoutSession.objects.filter(user=self.user)

        if since_date:
            queryset = queryset.filter(date__gte=since_date)

        if not queryset.exists():
            return None

        count = queryset.count()

        # Calculate total and average duration
        total_minutes = 0
        for session in queryset:
            if session.duration_minutes:
                total_minutes += session.duration_minutes

        avg_duration = round(total_minutes / count, 1) if count > 0 else 0

        latest_entry = queryset.first()
        latest_date = latest_entry.date

        # Get recent workouts
        recent_sessions = queryset[:limit]
        workouts = [
            {
                'name': session.name,
                'date': session.date,
                'duration_minutes': session.duration_minutes,
                'notes': session.notes,
            }
            for session in recent_sessions
        ]

        result = {
            'type': 'workout',
            'count': count,
            'total_minutes': total_minutes,
            'avg_duration': avg_duration,
            'latest_date': latest_date,
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
        cache_key = _generate_cache_key(self.user.id, 'fasting', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        from apps.health.models import FastingWindow

        queryset = FastingWindow.objects.filter(user=self.user)

        if since_date:
            queryset = queryset.filter(started_at__gte=since_date)

        if not queryset.exists():
            return None

        # Check for active fast
        active_fast = None
        active_qs = queryset.filter(ended_at__isnull=True)
        if active_qs.exists():
            active = active_qs.first()
            from django.utils import timezone
            now = timezone.now()
            duration_hours = (now - active.started_at).total_seconds() / 3600
            active_fast = {
                'started_at': active.started_at,
                'fasting_type': active.fasting_type,
                'hours_elapsed': round(duration_hours, 1),
            }

        # Get completed fasts
        completed = queryset.filter(ended_at__isnull=False)
        total_fasts = completed.count()

        # Calculate durations
        durations = []
        for fast in completed:
            if fast.ended_at and fast.started_at:
                duration = (fast.ended_at - fast.started_at).total_seconds() / 3600
                durations.append(duration)

        avg_duration = round(sum(durations) / len(durations), 1) if durations else 0
        longest_fast = round(max(durations), 1) if durations else 0

        # Recent completed fasts
        recent = completed.order_by('-started_at')[:limit]
        recent_fasts = []
        for fast in recent:
            duration = 0
            if fast.ended_at and fast.started_at:
                duration = (fast.ended_at - fast.started_at).total_seconds() / 3600
            recent_fasts.append({
                'started_at': fast.started_at,
                'ended_at': fast.ended_at,
                'fasting_type': fast.fasting_type,
                'duration_hours': round(duration, 1),
            })

        result = {
            'type': 'fasting',
            'total_fasts': total_fasts,
            'active_fast': active_fast,
            'avg_duration_hours': avg_duration,
            'longest_fast_hours': longest_fast,
            'recent_fasts': recent_fasts,
        }

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

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
        cache_key = _generate_cache_key(self.user.id, 'water', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        from apps.health.models import WaterEntry
        from apps.core.utils import get_user_today
        from datetime import timedelta

        queryset = WaterEntry.objects.filter(user=self.user)

        if since_date:
            queryset = queryset.filter(recorded_at__gte=since_date)

        if not queryset.exists():
            return None

        today = get_user_today(self.user)
        total_entries = queryset.count()

        # Today's progress
        today_progress = WaterEntry.get_daily_goal_progress(self.user, today)

        # Calculate 7-day average
        week_ago = timezone.now() - timedelta(days=7)
        week_entries = queryset.filter(logged_date__gte=week_ago.date())
        avg_daily_oz = 0.0
        if week_entries.exists():
            daily_totals = {}
            for entry in week_entries:
                day = entry.logged_date
                if day not in daily_totals:
                    daily_totals[day] = 0
                daily_totals[day] += entry.amount_oz
            if daily_totals:
                avg_daily_oz = round(sum(daily_totals.values()) / len(daily_totals), 1)

        # Recent entries
        recent_entries = list(
            queryset[:limit].values('amount', 'unit', 'container', 'logged_date', 'recorded_at', 'notes')
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
            'total_entries': total_entries,
            'today_oz': today_progress['total_oz'],
            'today_percentage': today_progress['percentage'],
            'today_goal_met': today_progress['goal_met'],
            'avg_daily_oz': avg_daily_oz,
            'entries': entries,
        }

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

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
        cache_key = _generate_cache_key(self.user.id, 'task', since_date)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        from apps.life.models import Task
        from apps.core.utils import get_user_today

        queryset = Task.objects.filter(user=self.user)

        if since_date:
            queryset = queryset.filter(created_at__gte=since_date)

        if not queryset.exists():
            return None

        today = get_user_today(self.user)
        total = queryset.count()
        completed = queryset.filter(is_completed=True).count()
        pending = total - completed

        # Overdue: not completed, due date in the past
        overdue = queryset.filter(
            is_completed=False,
            due_date__lt=today
        ).count()

        # Due today: not completed, due date is today
        due_today = queryset.filter(
            is_completed=False,
            due_date=today
        ).count()

        completion_rate = round((completed / total) * 100, 1) if total > 0 else 0.0

        result = {
            'type': 'task',
            'total': total,
            'completed': completed,
            'pending': pending,
            'overdue': overdue,
            'due_today': due_today,
            'completion_rate': completion_rate,
        }

        cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)
        return result

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
