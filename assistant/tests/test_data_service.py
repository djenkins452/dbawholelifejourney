"""
Unit tests for the Personal Data Service.

Tests cover weight and journal data querying with mock data.
"""

import sys
import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch


# Create mocks for model modules before importing PersonalDataService
mock_health_models = MagicMock()
mock_journal_models = MagicMock()
sys.modules['apps.health.models'] = mock_health_models
sys.modules['apps.journal.models'] = mock_journal_models


class TestPersonalDataServiceInit(unittest.TestCase):
    """Tests for PersonalDataService initialization."""

    def test_init_stores_user(self):
        """Should store user in instance."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        service = PersonalDataService(mock_user)
        self.assertEqual(service.user, mock_user)


class TestGetWeightDataNoEntries(unittest.TestCase):
    """Tests for get_weight_data when no entries exist."""

    def test_returns_none_when_no_entries(self):
        """Should return None when user has no weight entries."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()

        # Setup mock queryset that returns no entries
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = False
        mock_health_models.WeightEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        result = service.get_weight_data()

        self.assertIsNone(result)

    def test_returns_none_when_no_entries_in_date_range(self):
        """Should return None when no entries exist in the date range."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()

        # Setup mock queryset
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = False
        mock_health_models.WeightEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        since_date = datetime(2024, 12, 1)
        result = service.get_weight_data(since_date=since_date)

        self.assertIsNone(result)


class TestGetWeightDataWithEntries(unittest.TestCase):
    """Tests for get_weight_data when entries exist."""

    def _setup_mock(self, count=5, avg_value=Decimal('175.5'),
                    latest_value=Decimal('174.0'), unit='lb', now=None):
        """Helper to setup mock queryset."""
        if now is None:
            now = datetime.now()

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = count
        mock_queryset.aggregate.return_value = {'avg_value': avg_value}

        mock_latest = MagicMock()
        mock_latest.value = latest_value
        mock_latest.recorded_at = now
        mock_latest.unit = unit
        mock_queryset.first.return_value = mock_latest

        mock_sliced = MagicMock()
        mock_sliced.values.return_value = [
            {'value': latest_value, 'unit': unit, 'recorded_at': now, 'notes': ''},
        ]
        mock_queryset.__getitem__ = MagicMock(return_value=mock_sliced)

        mock_health_models.WeightEntry.objects.filter.return_value = mock_queryset
        return mock_queryset, now

    def test_returns_dict_with_correct_structure(self):
        """Should return dict with all expected keys."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_mock()

        service = PersonalDataService(mock_user)
        result = service.get_weight_data()

        self.assertIsNotNone(result)
        self.assertIn('type', result)
        self.assertIn('count', result)
        self.assertIn('average', result)
        self.assertIn('latest', result)
        self.assertIn('latest_date', result)
        self.assertIn('unit', result)
        self.assertIn('entries', result)

    def test_type_is_weight(self):
        """Type should be 'weight'."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_mock()

        service = PersonalDataService(mock_user)
        result = service.get_weight_data()

        self.assertEqual(result['type'], 'weight')

    def test_count_matches_queryset_count(self):
        """Count should match the number of entries."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_mock(count=15)

        service = PersonalDataService(mock_user)
        result = service.get_weight_data()

        self.assertEqual(result['count'], 15)

    def test_average_is_calculated_correctly(self):
        """Average should be calculated from aggregate and rounded."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_mock(avg_value=Decimal('175.333'))

        service = PersonalDataService(mock_user)
        result = service.get_weight_data()

        # Average should be rounded to 1 decimal place
        self.assertEqual(result['average'], 175.3)

    def test_latest_values_from_first_entry(self):
        """Latest value and date should come from first entry."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        now = datetime(2024, 12, 18, 8, 30)
        self._setup_mock(
            latest_value=Decimal('174.5'),
            unit='kg',
            now=now
        )

        service = PersonalDataService(mock_user)
        result = service.get_weight_data()

        self.assertEqual(result['latest'], 174.5)
        self.assertEqual(result['latest_date'], now)
        self.assertEqual(result['unit'], 'kg')


class TestGetWeightDataFiltering(unittest.TestCase):
    """Tests for get_weight_data date filtering."""

    def test_filters_by_since_date(self):
        """Should filter entries by since_date."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        since_date = datetime(2024, 12, 1)
        now = datetime.now()

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = 5
        mock_queryset.aggregate.return_value = {'avg_value': Decimal('175.0')}

        mock_latest = MagicMock()
        mock_latest.value = Decimal('175.0')
        mock_latest.recorded_at = now
        mock_latest.unit = 'lb'
        mock_queryset.first.return_value = mock_latest
        mock_sliced = MagicMock()
        mock_sliced.values.return_value = []
        mock_queryset.__getitem__ = MagicMock(return_value=mock_sliced)

        mock_health_models.WeightEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        service.get_weight_data(since_date=since_date)

        # Verify filter was called (at least twice - once for user, once for date)
        self.assertGreaterEqual(mock_queryset.filter.call_count, 1)


class TestGetWeightDataEntries(unittest.TestCase):
    """Tests for entries list in get_weight_data result."""

    def test_entries_contain_expected_fields(self):
        """Each entry should have value, unit, recorded_at, notes."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        now = datetime.now()

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = 1
        mock_queryset.aggregate.return_value = {'avg_value': Decimal('175.0')}

        mock_latest = MagicMock()
        mock_latest.value = Decimal('175.0')
        mock_latest.recorded_at = now
        mock_latest.unit = 'lb'
        mock_queryset.first.return_value = mock_latest

        mock_entries = [
            {'value': Decimal('175.0'), 'unit': 'lb', 'recorded_at': now, 'notes': 'Test note'}
        ]
        mock_sliced = MagicMock()
        mock_sliced.values.return_value = mock_entries
        mock_queryset.__getitem__ = MagicMock(return_value=mock_sliced)

        mock_health_models.WeightEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        result = service.get_weight_data()

        self.assertEqual(len(result['entries']), 1)
        entry = result['entries'][0]
        self.assertIn('value', entry)
        self.assertIn('unit', entry)
        self.assertIn('recorded_at', entry)
        self.assertIn('notes', entry)

    def test_decimal_values_converted_to_float(self):
        """Decimal values should be converted to float for JSON serialization."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        now = datetime.now()

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = 1
        mock_queryset.aggregate.return_value = {'avg_value': Decimal('175.0')}

        mock_latest = MagicMock()
        mock_latest.value = Decimal('175.5')
        mock_latest.recorded_at = now
        mock_latest.unit = 'lb'
        mock_queryset.first.return_value = mock_latest

        mock_entries = [
            {'value': Decimal('175.5'), 'unit': 'lb', 'recorded_at': now, 'notes': ''}
        ]
        mock_sliced = MagicMock()
        mock_sliced.values.return_value = mock_entries
        mock_queryset.__getitem__ = MagicMock(return_value=mock_sliced)

        mock_health_models.WeightEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        result = service.get_weight_data()

        # Values should be float, not Decimal
        self.assertIsInstance(result['latest'], float)
        self.assertIsInstance(result['average'], float)
        self.assertIsInstance(result['entries'][0]['value'], float)


class TestGetWeightDataDefaultLimit(unittest.TestCase):
    """Tests for default limit behavior."""

    def test_default_limit_is_10(self):
        """Default limit should be 10."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        now = datetime.now()

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = 20
        mock_queryset.aggregate.return_value = {'avg_value': Decimal('175.0')}

        mock_latest = MagicMock()
        mock_latest.value = Decimal('175.0')
        mock_latest.recorded_at = now
        mock_latest.unit = 'lb'
        mock_queryset.first.return_value = mock_latest

        mock_sliced = MagicMock()
        mock_sliced.values.return_value = []
        mock_queryset.__getitem__ = MagicMock(return_value=mock_sliced)

        mock_health_models.WeightEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        service.get_weight_data()

        # Default should slice to 10
        mock_queryset.__getitem__.assert_called_with(slice(None, 10, None))

    def test_custom_limit_is_respected(self):
        """Custom limit should be used when provided."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        now = datetime.now()

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = 20
        mock_queryset.aggregate.return_value = {'avg_value': Decimal('175.0')}

        mock_latest = MagicMock()
        mock_latest.value = Decimal('175.0')
        mock_latest.recorded_at = now
        mock_latest.unit = 'lb'
        mock_queryset.first.return_value = mock_latest

        mock_sliced = MagicMock()
        mock_sliced.values.return_value = []
        mock_queryset.__getitem__ = MagicMock(return_value=mock_sliced)

        mock_health_models.WeightEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        service.get_weight_data(limit=5)

        # Should slice to 5
        mock_queryset.__getitem__.assert_called_with(slice(None, 5, None))


# ==============================================================================
# Journal Data Tests
# ==============================================================================


class TestGetJournalDataNoEntries(unittest.TestCase):
    """Tests for get_journal_data when no entries exist."""

    def test_returns_none_when_no_entries(self):
        """Should return None when user has no journal entries."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()

        # Setup mock queryset that returns no entries
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = False
        mock_journal_models.JournalEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        result = service.get_journal_data()

        self.assertIsNone(result)

    def test_returns_none_when_no_entries_in_date_range(self):
        """Should return None when no entries exist in the date range."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()

        # Setup mock queryset
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = False
        mock_journal_models.JournalEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        since_date = datetime(2024, 12, 1)
        result = service.get_journal_data(since_date=since_date)

        self.assertIsNone(result)


class TestGetJournalDataWithEntries(unittest.TestCase):
    """Tests for get_journal_data when entries exist."""

    def _setup_mock(self, count=5, latest_date=None):
        """Helper to setup mock queryset."""
        from datetime import date
        if latest_date is None:
            latest_date = date.today()

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = count

        mock_latest = MagicMock()
        mock_latest.entry_date = latest_date
        mock_queryset.first.return_value = mock_latest

        mock_journal_models.JournalEntry.objects.filter.return_value = mock_queryset
        return mock_queryset, latest_date

    def test_returns_dict_with_correct_structure(self):
        """Should return dict with all expected keys."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_mock()

        service = PersonalDataService(mock_user)
        result = service.get_journal_data()

        self.assertIsNotNone(result)
        self.assertIn('type', result)
        self.assertIn('count', result)
        self.assertIn('latest_date', result)

    def test_type_is_journal(self):
        """Type should be 'journal'."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_mock()

        service = PersonalDataService(mock_user)
        result = service.get_journal_data()

        self.assertEqual(result['type'], 'journal')

    def test_count_matches_queryset_count(self):
        """Count should match the number of entries."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_mock(count=15)

        service = PersonalDataService(mock_user)
        result = service.get_journal_data()

        self.assertEqual(result['count'], 15)

    def test_latest_date_from_first_entry(self):
        """Latest date should come from first entry."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_user = MagicMock()
        expected_date = date(2024, 12, 18)
        self._setup_mock(latest_date=expected_date)

        service = PersonalDataService(mock_user)
        result = service.get_journal_data()

        self.assertEqual(result['latest_date'], expected_date)


class TestGetJournalDataFiltering(unittest.TestCase):
    """Tests for get_journal_data filtering."""

    def test_filters_by_user_and_not_deleted(self):
        """Should filter entries by user and exclude soft-deleted."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_user = MagicMock()

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = 5

        mock_latest = MagicMock()
        mock_latest.entry_date = date.today()
        mock_queryset.first.return_value = mock_latest

        mock_journal_models.JournalEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        service.get_journal_data()

        # Verify initial filter includes user and is_deleted=False
        mock_journal_models.JournalEntry.objects.filter.assert_called_with(
            user=mock_user, is_deleted=False
        )

    def test_filters_by_since_date(self):
        """Should filter entries by since_date when provided."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_user = MagicMock()
        since_date = datetime(2024, 12, 1)

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = 5

        mock_latest = MagicMock()
        mock_latest.entry_date = date.today()
        mock_queryset.first.return_value = mock_latest

        mock_journal_models.JournalEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        service.get_journal_data(since_date=since_date)

        # Verify filter was called for date range
        self.assertGreaterEqual(mock_queryset.filter.call_count, 1)


if __name__ == '__main__':
    unittest.main()
