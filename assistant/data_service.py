"""
Personal Data Service for WLJ Personal Data Query System.

This module provides methods to query and summarize user's personal
wellness data from various models (weight, journal, mood, etc.).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import Avg, QuerySet


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
