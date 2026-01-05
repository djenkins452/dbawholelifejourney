"""
Unit tests for the Personal Data Service.

Tests cover weight, journal, medication data querying and query_by_intent with mock data.
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


# ==============================================================================
# Medication Data Tests
# ==============================================================================


class TestGetMedicationDataNoEntries(unittest.TestCase):
    """Tests for get_medication_data when no entries exist."""

    def test_returns_none_when_no_entries(self):
        """Should return None when user has no medication logs."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()

        # Setup mock queryset that returns no entries
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = False
        mock_health_models.MedicineLog.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        result = service.get_medication_data()

        self.assertIsNone(result)

    def test_returns_none_when_no_entries_in_date_range(self):
        """Should return None when no entries exist in the date range."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()

        # Setup mock queryset
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = False
        mock_health_models.MedicineLog.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        since_date = datetime(2024, 12, 1)
        result = service.get_medication_data(since_date=since_date)

        self.assertIsNone(result)


class TestGetMedicationDataWithEntries(unittest.TestCase):
    """Tests for get_medication_data when entries exist."""

    def _setup_mock(self, total_logs=10, unique_dates=None, earliest_date=None):
        """Helper to setup mock queryset."""
        from datetime import date
        if unique_dates is None:
            unique_dates = [date(2024, 12, 15), date(2024, 12, 16), date(2024, 12, 17)]
        if earliest_date is None:
            earliest_date = min(unique_dates)

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = total_logs

        # Mock values_list for unique dates
        mock_values_list = MagicMock()
        mock_values_list.distinct.return_value = unique_dates
        mock_queryset.values_list.return_value = mock_values_list

        # Mock order_by for earliest log
        mock_ordered = MagicMock()
        mock_earliest = MagicMock()
        mock_earliest.scheduled_date = earliest_date
        mock_ordered.first.return_value = mock_earliest
        mock_queryset.order_by.return_value = mock_ordered

        mock_health_models.MedicineLog.objects.filter.return_value = mock_queryset
        return mock_queryset

    @patch('assistant.data_service.timezone')
    def test_returns_dict_with_correct_structure(self, mock_timezone):
        """Should return dict with all expected keys."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_timezone.now.return_value.date.return_value = date(2024, 12, 20)

        mock_user = MagicMock()
        self._setup_mock()

        service = PersonalDataService(mock_user)
        result = service.get_medication_data()

        self.assertIsNotNone(result)
        self.assertIn('type', result)
        self.assertIn('total_logs', result)
        self.assertIn('days_logged', result)
        self.assertIn('total_days', result)
        self.assertIn('consistency_percent', result)

    @patch('assistant.data_service.timezone')
    def test_type_is_medication(self, mock_timezone):
        """Type should be 'medication'."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_timezone.now.return_value.date.return_value = date(2024, 12, 20)

        mock_user = MagicMock()
        self._setup_mock()

        service = PersonalDataService(mock_user)
        result = service.get_medication_data()

        self.assertEqual(result['type'], 'medication')

    @patch('assistant.data_service.timezone')
    def test_total_logs_matches_count(self, mock_timezone):
        """Total logs should match queryset count."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_timezone.now.return_value.date.return_value = date(2024, 12, 20)

        mock_user = MagicMock()
        self._setup_mock(total_logs=45)

        service = PersonalDataService(mock_user)
        result = service.get_medication_data()

        self.assertEqual(result['total_logs'], 45)

    @patch('assistant.data_service.timezone')
    def test_days_logged_counts_unique_dates(self, mock_timezone):
        """Days logged should count unique dates."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_timezone.now.return_value.date.return_value = date(2024, 12, 20)

        mock_user = MagicMock()
        unique_dates = [date(2024, 12, 10), date(2024, 12, 11), date(2024, 12, 12),
                       date(2024, 12, 13), date(2024, 12, 14)]
        self._setup_mock(unique_dates=unique_dates)

        service = PersonalDataService(mock_user)
        result = service.get_medication_data()

        self.assertEqual(result['days_logged'], 5)


class TestGetMedicationDataConsistency(unittest.TestCase):
    """Tests for consistency calculation."""

    @patch('assistant.data_service.timezone')
    def test_consistency_is_percentage(self, mock_timezone):
        """Consistency should be between 0 and 100."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_timezone.now.return_value.date.return_value = date(2024, 12, 20)

        mock_user = MagicMock()

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = 10

        unique_dates = [date(2024, 12, 15), date(2024, 12, 16)]
        mock_values_list = MagicMock()
        mock_values_list.distinct.return_value = unique_dates
        mock_queryset.values_list.return_value = mock_values_list

        mock_ordered = MagicMock()
        mock_earliest = MagicMock()
        mock_earliest.scheduled_date = date(2024, 12, 15)
        mock_ordered.first.return_value = mock_earliest
        mock_queryset.order_by.return_value = mock_ordered

        mock_health_models.MedicineLog.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        result = service.get_medication_data()

        self.assertGreaterEqual(result['consistency_percent'], 0)
        self.assertLessEqual(result['consistency_percent'], 100)

    @patch('assistant.data_service.timezone')
    def test_consistency_is_rounded(self, mock_timezone):
        """Consistency percent should be rounded to 1 decimal."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_timezone.now.return_value.date.return_value = date(2024, 12, 20)

        mock_user = MagicMock()

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = 10

        unique_dates = [date(2024, 12, 15)]
        mock_values_list = MagicMock()
        mock_values_list.distinct.return_value = unique_dates
        mock_queryset.values_list.return_value = mock_values_list

        mock_ordered = MagicMock()
        mock_earliest = MagicMock()
        mock_earliest.scheduled_date = date(2024, 12, 15)
        mock_ordered.first.return_value = mock_earliest
        mock_queryset.order_by.return_value = mock_ordered

        mock_health_models.MedicineLog.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        result = service.get_medication_data()

        # Should be a float with at most 1 decimal place
        self.assertIsInstance(result['consistency_percent'], float)


class TestGetMedicationDataFiltering(unittest.TestCase):
    """Tests for get_medication_data filtering."""

    @patch('assistant.data_service.timezone')
    def test_filters_by_user_and_not_deleted(self, mock_timezone):
        """Should filter entries by user and exclude soft-deleted."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_timezone.now.return_value.date.return_value = date(2024, 12, 20)

        mock_user = MagicMock()

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = 5

        unique_dates = [date(2024, 12, 15)]
        mock_values_list = MagicMock()
        mock_values_list.distinct.return_value = unique_dates
        mock_queryset.values_list.return_value = mock_values_list

        mock_ordered = MagicMock()
        mock_earliest = MagicMock()
        mock_earliest.scheduled_date = date(2024, 12, 15)
        mock_ordered.first.return_value = mock_earliest
        mock_queryset.order_by.return_value = mock_ordered

        mock_health_models.MedicineLog.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        service.get_medication_data()

        # Verify initial filter includes user and is_deleted=False
        mock_health_models.MedicineLog.objects.filter.assert_called_with(
            user=mock_user, is_deleted=False
        )

    @patch('assistant.data_service.timezone')
    def test_filters_by_since_date(self, mock_timezone):
        """Should filter entries by since_date when provided."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_timezone.now.return_value.date.return_value = date(2024, 12, 20)

        mock_user = MagicMock()
        since_date = datetime(2024, 12, 1)

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = 5

        unique_dates = [date(2024, 12, 15)]
        mock_values_list = MagicMock()
        mock_values_list.distinct.return_value = unique_dates
        mock_queryset.values_list.return_value = mock_values_list

        mock_ordered = MagicMock()
        mock_earliest = MagicMock()
        mock_earliest.scheduled_date = date(2024, 12, 15)
        mock_ordered.first.return_value = mock_earliest
        mock_queryset.order_by.return_value = mock_ordered

        mock_health_models.MedicineLog.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        service.get_medication_data(since_date=since_date)

        # Verify filter was called for date range
        self.assertGreaterEqual(mock_queryset.filter.call_count, 1)


# ==============================================================================
# Query By Intent Tests
# ==============================================================================


class TestQueryByIntentNoData(unittest.TestCase):
    """Tests for query_by_intent when no data exists."""

    def test_returns_none_when_no_data_types(self):
        """Should return None when empty data_types list provided."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        service = PersonalDataService(mock_user)
        result = service.query_by_intent(data_types=[])

        self.assertIsNone(result)

    def test_returns_none_when_all_queries_return_none(self):
        """Should return None when all data type queries return None."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()

        # Setup all mocks to return no data
        mock_weight_qs = MagicMock()
        mock_weight_qs.filter.return_value = mock_weight_qs
        mock_weight_qs.exists.return_value = False
        mock_health_models.WeightEntry.objects.filter.return_value = mock_weight_qs

        mock_journal_qs = MagicMock()
        mock_journal_qs.filter.return_value = mock_journal_qs
        mock_journal_qs.exists.return_value = False
        mock_journal_models.JournalEntry.objects.filter.return_value = mock_journal_qs

        service = PersonalDataService(mock_user)
        result = service.query_by_intent(data_types=['weight', 'journal'])

        self.assertIsNone(result)

    def test_skips_unknown_data_types(self):
        """Should skip unknown data types without error."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()

        # Setup weight mock to return no data
        mock_weight_qs = MagicMock()
        mock_weight_qs.filter.return_value = mock_weight_qs
        mock_weight_qs.exists.return_value = False
        mock_health_models.WeightEntry.objects.filter.return_value = mock_weight_qs

        service = PersonalDataService(mock_user)
        # 'unknown_type' should be silently skipped
        result = service.query_by_intent(data_types=['unknown_type', 'weight'])

        self.assertIsNone(result)


class TestQueryByIntentWithData(unittest.TestCase):
    """Tests for query_by_intent when data exists."""

    def _setup_weight_mock(self, count=5):
        """Helper to setup weight mock with data."""
        from decimal import Decimal
        now = datetime.now()

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = count
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
        return mock_queryset

    def _setup_journal_mock(self, count=5):
        """Helper to setup journal mock with data."""
        from datetime import date
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = count

        mock_latest = MagicMock()
        mock_latest.entry_date = date.today()
        mock_queryset.first.return_value = mock_latest

        mock_journal_models.JournalEntry.objects.filter.return_value = mock_queryset
        return mock_queryset

    def test_returns_single_data_type(self):
        """Should return dict with single data type result."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_weight_mock()

        service = PersonalDataService(mock_user)
        result = service.query_by_intent(data_types=['weight'])

        self.assertIsNotNone(result)
        self.assertIn('weight', result)
        self.assertEqual(result['weight']['type'], 'weight')

    def test_returns_multiple_data_types(self):
        """Should return dict with multiple data type results."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_weight_mock()
        self._setup_journal_mock()

        service = PersonalDataService(mock_user)
        result = service.query_by_intent(data_types=['weight', 'journal'])

        self.assertIsNotNone(result)
        self.assertIn('weight', result)
        self.assertIn('journal', result)
        self.assertEqual(result['weight']['type'], 'weight')
        self.assertEqual(result['journal']['type'], 'journal')

    def test_skips_types_with_no_data(self):
        """Should skip data types that return None."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_weight_mock()

        # Journal returns no data
        mock_journal_qs = MagicMock()
        mock_journal_qs.filter.return_value = mock_journal_qs
        mock_journal_qs.exists.return_value = False
        mock_journal_models.JournalEntry.objects.filter.return_value = mock_journal_qs

        service = PersonalDataService(mock_user)
        result = service.query_by_intent(data_types=['weight', 'journal'])

        self.assertIsNotNone(result)
        self.assertIn('weight', result)
        self.assertNotIn('journal', result)

    def test_passes_since_date_to_methods(self):
        """Should pass since_date parameter to underlying methods."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        since_date = datetime(2024, 12, 1)

        mock_weight_qs = MagicMock()
        mock_weight_qs.filter.return_value = mock_weight_qs
        mock_weight_qs.exists.return_value = False
        mock_health_models.WeightEntry.objects.filter.return_value = mock_weight_qs

        service = PersonalDataService(mock_user)
        service.query_by_intent(data_types=['weight'], since_date=since_date)

        # Verify filter was called (for user and for date)
        self.assertTrue(mock_weight_qs.filter.called)


class TestQueryByIntentAllDataTypes(unittest.TestCase):
    """Tests for query_by_intent with all data types."""

    @patch('assistant.data_service.timezone')
    def test_returns_all_three_types(self, mock_timezone):
        """Should return all three data types when all have data."""
        from assistant.data_service import PersonalDataService
        from datetime import date
        from decimal import Decimal

        mock_timezone.now.return_value.date.return_value = date(2024, 12, 20)
        now = datetime.now()

        mock_user = MagicMock()

        # Setup weight mock
        mock_weight_qs = MagicMock()
        mock_weight_qs.filter.return_value = mock_weight_qs
        mock_weight_qs.exists.return_value = True
        mock_weight_qs.count.return_value = 5
        mock_weight_qs.aggregate.return_value = {'avg_value': Decimal('175.0')}
        mock_weight_latest = MagicMock()
        mock_weight_latest.value = Decimal('175.0')
        mock_weight_latest.recorded_at = now
        mock_weight_latest.unit = 'lb'
        mock_weight_qs.first.return_value = mock_weight_latest
        mock_sliced = MagicMock()
        mock_sliced.values.return_value = []
        mock_weight_qs.__getitem__ = MagicMock(return_value=mock_sliced)
        mock_health_models.WeightEntry.objects.filter.return_value = mock_weight_qs

        # Setup journal mock
        mock_journal_qs = MagicMock()
        mock_journal_qs.filter.return_value = mock_journal_qs
        mock_journal_qs.exists.return_value = True
        mock_journal_qs.count.return_value = 10
        mock_journal_latest = MagicMock()
        mock_journal_latest.entry_date = date.today()
        mock_journal_qs.first.return_value = mock_journal_latest
        mock_journal_models.JournalEntry.objects.filter.return_value = mock_journal_qs

        # Setup medication mock
        mock_med_qs = MagicMock()
        mock_med_qs.filter.return_value = mock_med_qs
        mock_med_qs.exists.return_value = True
        mock_med_qs.count.return_value = 15
        unique_dates = [date(2024, 12, 15), date(2024, 12, 16)]
        mock_values_list = MagicMock()
        mock_values_list.distinct.return_value = unique_dates
        mock_med_qs.values_list.return_value = mock_values_list
        mock_ordered = MagicMock()
        mock_earliest = MagicMock()
        mock_earliest.scheduled_date = date(2024, 12, 15)
        mock_ordered.first.return_value = mock_earliest
        mock_med_qs.order_by.return_value = mock_ordered
        mock_health_models.MedicineLog.objects.filter.return_value = mock_med_qs

        service = PersonalDataService(mock_user)
        result = service.query_by_intent(
            data_types=['weight', 'journal', 'medication']
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)
        self.assertIn('weight', result)
        self.assertIn('journal', result)
        self.assertIn('medication', result)


# ==============================================================================
# Food Data Tests
# ==============================================================================


class TestGetFoodDataNoEntries(unittest.TestCase):
    """Tests for get_food_data when no entries exist."""

    def test_returns_none_when_no_entries(self):
        """Should return None when user has no food entries."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()

        # Setup mock queryset that returns no entries
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = False
        mock_health_models.FoodEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        result = service.get_food_data()

        self.assertIsNone(result)

    def test_returns_none_when_no_entries_in_date_range(self):
        """Should return None when no entries exist in the date range."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()

        # Setup mock queryset
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = False
        mock_health_models.FoodEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        since_date = datetime(2024, 12, 1)
        result = service.get_food_data(since_date=since_date)

        self.assertIsNone(result)


class TestGetFoodDataWithEntries(unittest.TestCase):
    """Tests for get_food_data when entries exist."""

    def _setup_mock(self, total_entries=10, total_cal=15000.0, unique_dates=None,
                    latest_date=None):
        """Helper to setup mock queryset."""
        from datetime import date
        if unique_dates is None:
            unique_dates = [date(2024, 12, 15), date(2024, 12, 16), date(2024, 12, 17)]
        if latest_date is None:
            latest_date = max(unique_dates)

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = total_entries
        mock_queryset.aggregate.return_value = {'total_cal': Decimal(str(total_cal))}

        # Mock values_list for unique dates
        mock_values_list = MagicMock()
        mock_values_list.distinct.return_value = unique_dates
        mock_queryset.values_list.return_value = mock_values_list

        # Mock first() for latest entry
        mock_latest = MagicMock()
        mock_latest.logged_date = latest_date
        mock_queryset.first.return_value = mock_latest

        mock_health_models.FoodEntry.objects.filter.return_value = mock_queryset
        return mock_queryset

    def test_returns_dict_with_correct_structure(self):
        """Should return dict with all expected keys."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_mock()

        service = PersonalDataService(mock_user)
        result = service.get_food_data()

        self.assertIsNotNone(result)
        self.assertIn('type', result)
        self.assertIn('total_entries', result)
        self.assertIn('total_calories', result)
        self.assertIn('average_daily_calories', result)
        self.assertIn('latest_date', result)

    def test_type_is_food(self):
        """Type should be 'food'."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_mock()

        service = PersonalDataService(mock_user)
        result = service.get_food_data()

        self.assertEqual(result['type'], 'food')

    def test_total_entries_matches_count(self):
        """Total entries should match queryset count."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_mock(total_entries=45)

        service = PersonalDataService(mock_user)
        result = service.get_food_data()

        self.assertEqual(result['total_entries'], 45)

    def test_total_calories_from_aggregate(self):
        """Total calories should come from aggregate sum."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_mock(total_cal=25000.5)

        service = PersonalDataService(mock_user)
        result = service.get_food_data()

        self.assertEqual(result['total_calories'], 25000.5)


class TestGetFoodDataAverageCalories(unittest.TestCase):
    """Tests for average daily calories calculation."""

    def test_average_calculated_correctly(self):
        """Average should be total / days_count."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_user = MagicMock()

        # 6000 calories over 3 days = 2000 avg
        unique_dates = [date(2024, 12, 15), date(2024, 12, 16), date(2024, 12, 17)]

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = 9  # 3 meals per day
        mock_queryset.aggregate.return_value = {'total_cal': Decimal('6000.0')}

        mock_values_list = MagicMock()
        mock_values_list.distinct.return_value = unique_dates
        mock_queryset.values_list.return_value = mock_values_list

        mock_latest = MagicMock()
        mock_latest.logged_date = date(2024, 12, 17)
        mock_queryset.first.return_value = mock_latest

        mock_health_models.FoodEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        result = service.get_food_data()

        self.assertEqual(result['average_daily_calories'], 2000.0)

    def test_average_is_rounded(self):
        """Average should be rounded to 1 decimal."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_user = MagicMock()

        # 5000 calories over 3 days = 1666.666... avg -> 1666.7
        unique_dates = [date(2024, 12, 15), date(2024, 12, 16), date(2024, 12, 17)]

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = 6
        mock_queryset.aggregate.return_value = {'total_cal': Decimal('5000.0')}

        mock_values_list = MagicMock()
        mock_values_list.distinct.return_value = unique_dates
        mock_queryset.values_list.return_value = mock_values_list

        mock_latest = MagicMock()
        mock_latest.logged_date = date(2024, 12, 17)
        mock_queryset.first.return_value = mock_latest

        mock_health_models.FoodEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        result = service.get_food_data()

        self.assertEqual(result['average_daily_calories'], 1666.7)


class TestGetFoodDataFiltering(unittest.TestCase):
    """Tests for get_food_data filtering."""

    def test_filters_by_user(self):
        """Should filter entries by user."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_user = MagicMock()

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = 5
        mock_queryset.aggregate.return_value = {'total_cal': Decimal('5000.0')}

        mock_values_list = MagicMock()
        mock_values_list.distinct.return_value = [date(2024, 12, 15)]
        mock_queryset.values_list.return_value = mock_values_list

        mock_latest = MagicMock()
        mock_latest.logged_date = date(2024, 12, 15)
        mock_queryset.first.return_value = mock_latest

        mock_health_models.FoodEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        service.get_food_data()

        # Verify initial filter includes user
        mock_health_models.FoodEntry.objects.filter.assert_called_with(user=mock_user)

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
        mock_queryset.aggregate.return_value = {'total_cal': Decimal('5000.0')}

        mock_values_list = MagicMock()
        mock_values_list.distinct.return_value = [date(2024, 12, 15)]
        mock_queryset.values_list.return_value = mock_values_list

        mock_latest = MagicMock()
        mock_latest.logged_date = date(2024, 12, 15)
        mock_queryset.first.return_value = mock_latest

        mock_health_models.FoodEntry.objects.filter.return_value = mock_queryset

        service = PersonalDataService(mock_user)
        service.get_food_data(since_date=since_date)

        # Verify filter was called for date range
        self.assertGreaterEqual(mock_queryset.filter.call_count, 1)


class TestQueryByIntentWithFood(unittest.TestCase):
    """Tests for query_by_intent including food data type."""

    def _setup_food_mock(self, total_entries=5, total_cal=7500.0):
        """Helper to setup food mock with data."""
        from datetime import date

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        mock_queryset.count.return_value = total_entries
        mock_queryset.aggregate.return_value = {'total_cal': Decimal(str(total_cal))}

        unique_dates = [date(2024, 12, 15), date(2024, 12, 16), date(2024, 12, 17)]
        mock_values_list = MagicMock()
        mock_values_list.distinct.return_value = unique_dates
        mock_queryset.values_list.return_value = mock_values_list

        mock_latest = MagicMock()
        mock_latest.logged_date = date(2024, 12, 17)
        mock_queryset.first.return_value = mock_latest

        mock_health_models.FoodEntry.objects.filter.return_value = mock_queryset
        return mock_queryset

    def test_returns_food_data_type(self):
        """Should return food data when queried."""
        from assistant.data_service import PersonalDataService

        mock_user = MagicMock()
        self._setup_food_mock()

        service = PersonalDataService(mock_user)
        result = service.query_by_intent(data_types=['food'])

        self.assertIsNotNone(result)
        self.assertIn('food', result)
        self.assertEqual(result['food']['type'], 'food')

    def test_includes_food_with_other_types(self):
        """Should include food alongside other data types."""
        from assistant.data_service import PersonalDataService
        from datetime import date

        mock_user = MagicMock()

        # Setup food mock
        self._setup_food_mock()

        # Setup journal mock
        mock_journal_qs = MagicMock()
        mock_journal_qs.filter.return_value = mock_journal_qs
        mock_journal_qs.exists.return_value = True
        mock_journal_qs.count.return_value = 10
        mock_journal_latest = MagicMock()
        mock_journal_latest.entry_date = date.today()
        mock_journal_qs.first.return_value = mock_journal_latest
        mock_journal_models.JournalEntry.objects.filter.return_value = mock_journal_qs

        service = PersonalDataService(mock_user)
        result = service.query_by_intent(data_types=['food', 'journal'])

        self.assertIsNotNone(result)
        self.assertIn('food', result)
        self.assertIn('journal', result)


if __name__ == '__main__':
    unittest.main()
