"""
Personal Data Service for WLJ Personal Data Query System.

This module provides methods to query and summarize user's personal
wellness data from various models (weight, journal, mood, etc.).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import Avg, QuerySet
from django.utils import timezone


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

        return {
            'type': 'weight',
            'count': count,
            'average': round(average, 1),
            'latest': latest_value,
            'latest_date': latest_date,
            'unit': latest_unit,
            'entries': entries,
        }

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
        # Import here to avoid circular imports and allow testing without Django
        from apps.journal.models import JournalEntry

        # Build base queryset - filter by user and exclude soft-deleted
        queryset = JournalEntry.objects.filter(user=self.user, is_deleted=False)

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

        return {
            'type': 'journal',
            'count': count,
            'latest_date': latest_date,
        }

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
        # Import here to avoid circular imports and allow testing without Django
        from apps.health.models import MedicineLog

        # Build base queryset - filter by user and exclude soft-deleted
        queryset = MedicineLog.objects.filter(user=self.user, is_deleted=False)

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

        return {
            'type': 'medication',
            'total_logs': total_logs,
            'days_logged': days_logged,
            'total_days': total_days,
            'consistency_percent': consistency_percent,
        }
