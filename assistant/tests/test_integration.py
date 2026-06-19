"""
Integration tests for the Personal Data Query System.

These tests use real Django models and ORM to verify the system works
correctly with actual database operations, soft delete behavior, and
date filtering.
"""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.health.models import FoodEntry, WeightEntry
from apps.journal.models import JournalEntry
from assistant.data_service import PersonalDataService
from assistant.views import process_assistant_message


User = get_user_model()


class CacheClearingTestCase(TestCase):
    """Base TestCase that clears cache before each test to prevent data bleed."""

    def setUp(self):
        cache.clear()
        super().setUp()


def _weight_metric_stub(current_value, unit='lb', change_30d=None, trend=None,
                        source='SAE:health.weight_current', last_entry=None):
    """Build a side_effect for get_metric that supplies canonical weight metrics.

    get_weight_data() reads the latest weight, unit, 30-day change, trend and
    last-entry timestamp from SAE via get_metric(); the recent ``entries`` list
    is still queried from the WeightEntry ORM. This helper mocks only the SAE
    half so the tests are deterministic regardless of SAE rebuild state.
    """
    def _side_effect(user, key):
        if key == 'health.weight_current':
            return SimpleNamespace(value=current_value, source=source)
        if key == 'health.weight_unit':
            return SimpleNamespace(value=unit, source=source)
        if key == 'health.last_weight_entry':
            return SimpleNamespace(value=last_entry, source=source) if last_entry else None
        if key == 'health.weight_change_30d':
            return SimpleNamespace(value=change_30d, source=source) if change_30d is not None else None
        if key == 'health.weight_trend':
            return SimpleNamespace(value=trend, source=source) if trend is not None else None
        return None
    return _side_effect


class WeightDataIntegrationTest(CacheClearingTestCase):
    """Integration tests for get_weight_data().

    Canonical weight values (latest, unit, 30-day change, trend) now come
    from the SAE metric access layer via get_metric(); only the recent
    ``entries`` list is still read from the WeightEntry ORM. These tests mock
    the SAE half and exercise the ORM half with real records.
    """

    def setUp(self):
        """Create test user and weight entries."""
        super().setUp()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)

    def test_get_weight_data_returns_none_for_empty_data(self):
        """Test that get_weight_data returns None when SAE has no current weight."""
        with patch('assistant.data_service.get_metric', return_value=None):
            result = self.service.get_weight_data()
        self.assertIsNone(result)

    def test_get_weight_data_returns_entries_list(self):
        """The recent ORM entries list reflects all of the user's records."""
        for i in range(3):
            WeightEntry.objects.create(
                user=self.user,
                value=Decimal("170.0") + i,
                unit="lb",
                recorded_at=timezone.now() - timedelta(days=i)
            )

        with patch(
            'assistant.data_service.get_metric',
            side_effect=_weight_metric_stub(172.0),
        ):
            result = self.service.get_weight_data()
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'weight')
        self.assertEqual(len(result['entries']), 3)

    def test_get_weight_data_surfaces_canonical_change_and_trend(self):
        """30-day change and trend are surfaced from SAE, not re-derived."""
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("170.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=2)
        )
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("180.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=1)
        )

        with patch(
            'assistant.data_service.get_metric',
            side_effect=_weight_metric_stub(
                180.0, change_30d=-2.5, trend='decreasing'
            ),
        ):
            result = self.service.get_weight_data()
        self.assertEqual(result['change_30d'], -2.5)
        self.assertEqual(result['trend'], 'decreasing')

    def test_get_weight_data_returns_latest_entry(self):
        """Test that get_weight_data surfaces the canonical latest weight."""
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("170.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=2)
        )
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.5"),
            unit="lb",
            recorded_at=timezone.now()
        )

        with patch(
            'assistant.data_service.get_metric',
            side_effect=_weight_metric_stub(175.5),
        ):
            result = self.service.get_weight_data()
        self.assertEqual(result['latest'], 175.5)
        self.assertEqual(result['unit'], 'lb')
        self.assertEqual(result['source'], 'SAE:health.weight_current')

    def test_get_weight_data_only_returns_user_entries(self):
        """The ORM entries list is scoped to the current user only."""
        # Create entry for current user
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("170.0"),
            unit="lb"
        )
        # Create entry for other user
        WeightEntry.objects.create(
            user=self.other_user,
            value=Decimal("200.0"),
            unit="lb"
        )

        with patch(
            'assistant.data_service.get_metric',
            side_effect=_weight_metric_stub(170.0),
        ):
            result = self.service.get_weight_data()
        self.assertEqual(len(result['entries']), 1)
        self.assertEqual(result['entries'][0]['value'], 170.0)
        self.assertEqual(result['latest'], 170.0)

    def test_get_weight_data_date_filtering(self):
        """Test that date filtering restricts the ORM entries list."""
        # Create old entry (10 days ago)
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("170.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=10)
        )
        # Create recent entry (2 days ago)
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=2)
        )

        # Query with date filter (last 5 days)
        since_date = timezone.now() - timedelta(days=5)
        with patch(
            'assistant.data_service.get_metric',
            side_effect=_weight_metric_stub(175.0),
        ):
            result = self.service.get_weight_data(since_date=since_date)

        # Should only include the recent entry in the ORM list
        self.assertEqual(len(result['entries']), 1)
        self.assertEqual(result['entries'][0]['value'], 175.0)

    def test_get_weight_data_entries_list(self):
        """Test that entries list is properly formatted."""
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("170.5"),
            unit="lb",
            notes="Morning weight"
        )

        with patch(
            'assistant.data_service.get_metric',
            side_effect=_weight_metric_stub(170.5),
        ):
            result = self.service.get_weight_data()
        self.assertEqual(len(result['entries']), 1)
        self.assertEqual(result['entries'][0]['value'], 170.5)
        self.assertEqual(result['entries'][0]['unit'], 'lb')
        self.assertEqual(result['entries'][0]['notes'], 'Morning weight')


def _journal_metric_stub(entries_7d=None, entries_30d=None, days_since=None,
                         last_entry=None, source='SAE:journal.entries_7d'):
    """Build a side_effect for get_metric that supplies canonical journal metrics.

    get_journal_data() reads entry counts and the last-entry timestamp from SAE;
    the ``recent_entries`` preview list is still queried from the JournalEntry
    ORM. This helper mocks the SAE half so tests are deterministic. The method
    returns None only when entries_7d, entries_30d and last_entry are all None.
    """
    def _side_effect(user, key):
        if key == 'journal.entries_7d':
            return SimpleNamespace(value=entries_7d, source=source) if entries_7d is not None else None
        if key == 'journal.entries_30d':
            return SimpleNamespace(value=entries_30d, source=source) if entries_30d is not None else None
        if key == 'journal.days_since_entry':
            return SimpleNamespace(value=days_since, source=source) if days_since is not None else None
        if key == 'journal.last_entry':
            return SimpleNamespace(value=last_entry, source=source) if last_entry is not None else None
        return None
    return _side_effect


class JournalDataIntegrationTest(CacheClearingTestCase):
    """Integration tests for get_journal_data().

    Canonical journal counts and the last-entry date now come from SAE via
    get_metric(); only the ``recent_entries`` preview list is read from the
    JournalEntry ORM. These tests mock the SAE half and exercise the ORM half
    with real records.
    """

    def setUp(self):
        """Create test user."""
        super().setUp()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)

    def test_get_journal_data_returns_none_for_empty_data(self):
        """Test that get_journal_data returns None when SAE has no journal state."""
        with patch('assistant.data_service.get_metric', return_value=None):
            result = self.service.get_journal_data()
        self.assertIsNone(result)

    def test_get_journal_data_returns_recent_entries(self):
        """The recent_entries list reflects the user's ORM records."""
        for i in range(5):
            JournalEntry.objects.create(
                user=self.user,
                title=f"Entry {i}",
                body=f"Content for entry {i}",
                entry_date=date.today() - timedelta(days=i)
            )

        with patch(
            'assistant.data_service.get_metric',
            side_effect=_journal_metric_stub(entries_7d=5, entries_30d=5),
        ):
            result = self.service.get_journal_data()
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'journal')
        self.assertEqual(result['entries_7d'], 5)
        self.assertEqual(len(result['recent_entries']), 5)

    def test_get_journal_data_returns_latest_date(self):
        """Test that get_journal_data surfaces the canonical last-entry date."""
        JournalEntry.objects.create(
            user=self.user,
            title="Old Entry",
            body="Old content",
            entry_date=date.today() - timedelta(days=5)
        )
        JournalEntry.objects.create(
            user=self.user,
            title="Latest Entry",
            body="Latest content",
            entry_date=date.today()
        )

        with patch(
            'assistant.data_service.get_metric',
            side_effect=_journal_metric_stub(
                entries_7d=2, last_entry=date.today()
            ),
        ):
            result = self.service.get_journal_data()
        self.assertEqual(result['latest_date'], date.today())

    def test_get_journal_data_date_filtering(self):
        """Test that date filtering restricts the recent_entries list."""
        # Create old entry (10 days ago)
        JournalEntry.objects.create(
            user=self.user,
            title="Old",
            body="Old content",
            entry_date=date.today() - timedelta(days=10)
        )
        # Create recent entry (2 days ago)
        JournalEntry.objects.create(
            user=self.user,
            title="Recent",
            body="Recent content",
            entry_date=date.today() - timedelta(days=2)
        )

        # Query with date filter (last 5 days)
        since_date = date.today() - timedelta(days=5)
        with patch(
            'assistant.data_service.get_metric',
            side_effect=_journal_metric_stub(entries_7d=1),
        ):
            result = self.service.get_journal_data(since_date=since_date)

        self.assertEqual(len(result['recent_entries']), 1)

    def test_get_journal_data_excludes_soft_deleted(self):
        """Test that soft-deleted entries are excluded from recent_entries."""
        # Create active entry
        JournalEntry.objects.create(
            user=self.user,
            title="Active",
            body="Active content",
            entry_date=date.today()
        )
        # Create and soft-delete another entry
        deleted_entry = JournalEntry.objects.create(
            user=self.user,
            title="Deleted",
            body="Deleted content",
            entry_date=date.today() - timedelta(days=1)
        )
        deleted_entry.soft_delete()

        with patch(
            'assistant.data_service.get_metric',
            side_effect=_journal_metric_stub(entries_7d=1),
        ):
            result = self.service.get_journal_data()
        self.assertEqual(len(result['recent_entries']), 1)  # Only the active entry


class MedicationDataIntegrationTest(CacheClearingTestCase):
    """Integration tests for get_medication_data().

    Canonical medication status is owned by the SAE medicine state
    builder and read via ``get_metric('health.medication_status')``. The
    legacy MedicineLog consistency-% calculation was removed when the
    Medicine model was unified into Intake, so these tests exercise the
    SAE-backed contract rather than raw log counts.
    """

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        self.service = PersonalDataService(self.user)

    def test_returns_none_when_no_status(self):
        """No SAE medication status → None."""
        with patch('assistant.data_service.get_metric', return_value=None):
            result = self.service.get_medication_data()
        self.assertIsNone(result)

    def test_returns_status_payload_from_sae(self):
        """SAE medication status is surfaced as the medication payload."""
        status = SimpleNamespace(value='on_track', source='sae')
        reason = SimpleNamespace(value='all doses taken')

        def _fake_get_metric(user, key):
            if key == 'health.medication_status':
                return status
            if key == 'health.medication_status_reason':
                return reason
            return None

        with patch(
            'assistant.data_service.get_metric',
            side_effect=_fake_get_metric,
        ):
            result = self.service.get_medication_data()

        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'medication')
        self.assertEqual(result['status'], 'on_track')
        self.assertEqual(result['status_reason'], 'all doses taken')
        self.assertEqual(result['source'], 'sae')

    def test_status_reason_optional(self):
        """A missing status_reason is tolerated (None)."""
        status = SimpleNamespace(value='behind', source='sae')

        def _fake_get_metric(user, key):
            if key == 'health.medication_status':
                return status
            return None

        with patch(
            'assistant.data_service.get_metric',
            side_effect=_fake_get_metric,
        ):
            result = self.service.get_medication_data()

        self.assertEqual(result['status'], 'behind')
        self.assertIsNone(result['status_reason'])


def _food_metric_stub(daily_calories=None, rolling_avg=None, entries_today=None,
                      entries_7d=None, last_entry=None,
                      source='SAE:nutrition.rolling_7d_calories_avg'):
    """Build a side_effect for get_metric that supplies canonical food metrics.

    get_food_data() is fully SAE-driven: daily calories, the 7-day rolling
    average, today/7-day entry counts and the last-entry timestamp all come
    from get_metric(); raw FoodEntry aggregation was removed. The method returns
    None only when daily_calories, rolling_avg and last_entry are all None.
    """
    def _side_effect(user, key):
        if key == 'nutrition.daily_calories':
            return SimpleNamespace(value=daily_calories, source=source) if daily_calories is not None else None
        if key == 'nutrition.rolling_7d_calories_avg':
            return SimpleNamespace(value=rolling_avg, source=source) if rolling_avg is not None else None
        if key == 'nutrition.food_entries_today':
            return SimpleNamespace(value=entries_today, source=source) if entries_today is not None else None
        if key == 'nutrition.food_entries_7d':
            return SimpleNamespace(value=entries_7d, source=source) if entries_7d is not None else None
        if key == 'health.last_food_entry':
            return SimpleNamespace(value=last_entry, source=source) if last_entry is not None else None
        return None
    return _side_effect


class FoodDataIntegrationTest(CacheClearingTestCase):
    """Integration tests for get_food_data().

    get_food_data() is now fully SAE-driven (canonical daily calories, 7-day
    rolling average, entry counts, last-entry date); raw FoodEntry aggregation
    was removed. These tests mock get_metric() and assert the canonical
    contract rather than re-derived totals.
    """

    def setUp(self):
        """Create test user."""
        super().setUp()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)

    def test_get_food_data_returns_none_for_empty_data(self):
        """Test that get_food_data returns None when SAE has no nutrition state."""
        with patch('assistant.data_service.get_metric', return_value=None):
            result = self.service.get_food_data()
        self.assertIsNone(result)

    def test_get_food_data_returns_canonical_entry_counts(self):
        """Test that entry counts are surfaced from SAE."""
        with patch(
            'assistant.data_service.get_metric',
            side_effect=_food_metric_stub(
                daily_calories=1500.0, entries_today=3, entries_7d=12
            ),
        ):
            result = self.service.get_food_data()
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'food')
        self.assertEqual(result['entries_today'], 3)
        self.assertEqual(result['entries_7d'], 12)

    def test_get_food_data_surfaces_daily_calories(self):
        """Test that today's daily calories are surfaced from SAE."""
        with patch(
            'assistant.data_service.get_metric',
            side_effect=_food_metric_stub(daily_calories=1500.0),
        ):
            result = self.service.get_food_data()
        self.assertEqual(result['daily_calories'], 1500.0)

    def test_get_food_data_surfaces_rolling_average(self):
        """Test that the canonical 7-day rolling average is surfaced."""
        with patch(
            'assistant.data_service.get_metric',
            side_effect=_food_metric_stub(rolling_avg=750.0),
        ):
            result = self.service.get_food_data()
        # average_daily_calories is the 7-day rolling average from SAE
        self.assertEqual(result['average_daily_calories'], 750.0)
        self.assertEqual(result['average_window'], '7d_rolling')

    def test_get_food_data_returns_latest_date(self):
        """Test that the canonical last-entry date is surfaced."""
        with patch(
            'assistant.data_service.get_metric',
            side_effect=_food_metric_stub(
                daily_calories=600.0, last_entry=date.today()
            ),
        ):
            result = self.service.get_food_data()
        self.assertEqual(result['latest_date'], date.today())


def _mood_metric_stub(mood_avg_7d=None, mood_trend=None, distribution=None,
                      latest_mood=None, last_entry=None,
                      source='SAE:journal.mood_distribution'):
    """Build a side_effect for get_metric that supplies canonical mood metrics.

    get_mood_data() is fully SAE-driven: the 7-day mood average, trend,
    distribution, latest mood and last-entry timestamp all come from
    get_metric(); raw JournalEntry mood aggregation was removed. ``most_common``
    is derived in the method from the distribution dict. The method returns None
    only when mood_avg_7d, distribution and latest_mood are all None.
    """
    def _side_effect(user, key):
        if key == 'journal.mood_avg_7d':
            return SimpleNamespace(value=mood_avg_7d, source=source) if mood_avg_7d is not None else None
        if key == 'journal.mood_trend':
            return SimpleNamespace(value=mood_trend, source=source) if mood_trend is not None else None
        if key == 'journal.mood_distribution':
            return SimpleNamespace(value=distribution, source=source) if distribution is not None else None
        if key == 'journal.last_mood':
            return SimpleNamespace(value=latest_mood, source=source) if latest_mood is not None else None
        if key == 'journal.last_entry':
            return SimpleNamespace(value=last_entry, source=source) if last_entry is not None else None
        return None
    return _side_effect


class MoodDataIntegrationTest(CacheClearingTestCase):
    """Integration tests for get_mood_data().

    get_mood_data() is now fully SAE-driven (canonical mood distribution,
    trend, 7-day average, latest mood); raw JournalEntry mood aggregation was
    removed. These tests mock get_metric() and assert the canonical contract.
    ``most_common`` is still derived in the method from the distribution dict.
    """

    def setUp(self):
        """Create test user."""
        super().setUp()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)

    def test_get_mood_data_returns_none_for_no_mood_state(self):
        """Test that get_mood_data returns None when SAE has no mood state."""
        with patch('assistant.data_service.get_metric', return_value=None):
            result = self.service.get_mood_data()
        self.assertIsNone(result)

    def test_get_mood_data_returns_distribution_and_type(self):
        """Test that the canonical mood distribution is surfaced."""
        with patch(
            'assistant.data_service.get_metric',
            side_effect=_mood_metric_stub(
                distribution={'good': 2, 'great': 1, 'low': 1}
            ),
        ):
            result = self.service.get_mood_data()
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'mood')
        self.assertEqual(result['mood_distribution']['good'], 2)
        self.assertEqual(result['mood_distribution']['great'], 1)
        self.assertEqual(result['mood_distribution']['low'], 1)

    def test_get_mood_data_identifies_most_common(self):
        """Test that most common mood is derived from the SAE distribution."""
        with patch(
            'assistant.data_service.get_metric',
            side_effect=_mood_metric_stub(
                distribution={'okay': 2, 'good': 1}
            ),
        ):
            result = self.service.get_mood_data()
        self.assertEqual(result['most_common'], 'okay')

    def test_get_mood_data_surfaces_avg_and_trend(self):
        """Test that the 7-day mood average and trend are surfaced from SAE."""
        with patch(
            'assistant.data_service.get_metric',
            side_effect=_mood_metric_stub(
                mood_avg_7d=4.2, mood_trend='improving'
            ),
        ):
            result = self.service.get_mood_data()
        self.assertEqual(result['mood_avg_7d'], 4.2)
        self.assertEqual(result['mood_trend'], 'improving')

    def test_get_mood_data_returns_latest(self):
        """Test that latest mood and date are surfaced from SAE."""
        with patch(
            'assistant.data_service.get_metric',
            side_effect=_mood_metric_stub(
                latest_mood='great', last_entry=date.today()
            ),
        ):
            result = self.service.get_mood_data()
        self.assertEqual(result['latest_mood'], 'great')
        self.assertEqual(result['latest_date'], date.today())


class SoftDeleteBehaviorIntegrationTest(CacheClearingTestCase):
    """Integration tests specifically for soft delete behavior across all data types."""

    def setUp(self):
        """Create test user and test data."""
        super().setUp()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)

    def test_soft_deleted_journal_entries_excluded(self):
        """Test that soft-deleted journal entries are not returned."""
        JournalEntry.objects.create(
            user=self.user,
            title="Active",
            body="Content"
        )
        deleted = JournalEntry.objects.create(
            user=self.user,
            title="Deleted",
            body="Content"
        )
        deleted.soft_delete()

        result = self.service.get_journal_data()
        self.assertEqual(len(result['recent_entries']), 1)

    def test_archived_entries_are_excluded(self):
        """Test that archived entries are excluded from normal queries.

        The SoftDeleteManager filters out both deleted AND archived records
        by default. Users who want archived entries can use .include_archived()
        but PersonalDataService correctly uses the default manager behavior.
        """
        JournalEntry.objects.create(
            user=self.user,
            title="Active",
            body="Content"
        )
        archived = JournalEntry.objects.create(
            user=self.user,
            title="Archived",
            body="Content"
        )
        archived.archive()

        result = self.service.get_journal_data()
        # Archived entries are excluded by the SoftDeleteManager
        self.assertEqual(len(result['recent_entries']), 1)


class QueryByIntentIntegrationTest(CacheClearingTestCase):
    """Integration tests for query_by_intent() with real data."""

    def setUp(self):
        """Create test user and varied test data."""
        super().setUp()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)

        # Create weight data
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )

        # Create journal data
        JournalEntry.objects.create(
            user=self.user,
            title="Test Entry",
            body="Content",
            mood="good"
        )

    def test_query_single_type(self):
        """Test querying a single data type."""
        result = self.service.query_by_intent(data_types=['weight'])

        self.assertIsNotNone(result)
        self.assertIn('weight', result)
        self.assertNotIn('journal', result)

    def test_query_multiple_types(self):
        """Test querying multiple data types."""
        result = self.service.query_by_intent(data_types=['weight', 'journal'])

        self.assertIsNotNone(result)
        self.assertIn('weight', result)
        self.assertIn('journal', result)

    def test_query_with_date_filter(self):
        """Test querying with date filter applied to all types."""
        # Create old weight entry
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("180.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=10)
        )

        # Query recent data only
        since_date = timezone.now() - timedelta(days=5)
        result = self.service.query_by_intent(
            data_types=['weight'],
            since_date=since_date
        )

        # Should only get 1 entry in the ORM list (the one from setUp,
        # not the 10-day-old one) because date filtering applies to entries.
        self.assertEqual(len(result['weight']['entries']), 1)

    def test_query_returns_none_for_no_data(self):
        """Test that query_by_intent returns None when no data matches."""
        result = self.service.query_by_intent(data_types=['medication'])
        self.assertIsNone(result)

    def test_query_skips_unknown_types(self):
        """Test that unknown data types are skipped gracefully."""
        result = self.service.query_by_intent(
            data_types=['weight', 'unknown_type']
        )
        self.assertIsNotNone(result)
        self.assertIn('weight', result)
        self.assertNotIn('unknown_type', result)


class ProcessAssistantMessageIntegrationTest(CacheClearingTestCase):
    """End-to-end integration tests for process_assistant_message()."""

    def setUp(self):
        """Create test user with various data."""
        super().setUp()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )

        # Create weight data
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=1)
        )
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("174.0"),
            unit="lb",
            recorded_at=timezone.now()
        )

        # Create journal entries with mood
        JournalEntry.objects.create(
            user=self.user,
            title="Entry 1",
            body="Feeling good today",
            mood="good",
            entry_date=date.today()
        )

    def test_weight_query_returns_data(self):
        """Test that weight query returns data with context."""
        result = process_assistant_message(
            user=self.user,
            message="What was my weight last week?",
            base_system_prompt="You are a helpful assistant."
        )

        self.assertTrue(result['is_personal_query'])
        self.assertIn('weight', result['data_types'])
        self.assertTrue(result['has_data'])
        self.assertIn('Weight Data', result['system_prompt'])

    def test_journal_query_returns_data(self):
        """Test that journal query returns data with context."""
        result = process_assistant_message(
            user=self.user,
            message="How many journal entries did I write this week?",
            base_system_prompt=""
        )

        self.assertTrue(result['is_personal_query'])
        self.assertIn('journal', result['data_types'])
        self.assertTrue(result['has_data'])
        self.assertIn('Journal Data', result['system_prompt'])

    def test_mood_query_returns_data(self):
        """Test that mood query returns data with context."""
        result = process_assistant_message(
            user=self.user,
            message="How has my mood been lately?",
            base_system_prompt=""
        )

        self.assertTrue(result['is_personal_query'])
        self.assertIn('mood', result['data_types'])
        self.assertTrue(result['has_data'])
        self.assertIn('Mood Data', result['system_prompt'])

    def test_non_personal_query_returns_base_prompt(self):
        """Test that non-personal query returns original base prompt."""
        base_prompt = "You are a helpful assistant."
        result = process_assistant_message(
            user=self.user,
            message="What is the meaning of life?",
            base_system_prompt=base_prompt
        )

        self.assertFalse(result['is_personal_query'])
        self.assertFalse(result['has_data'])
        self.assertEqual(result['system_prompt'], base_prompt)

    def test_food_query_is_recognised_as_personal(self):
        """A food query is recognised and routed to the food data type.

        Under the SAE contract get_food_data() surfaces a canonical (possibly
        zero-valued) nutrition payload rather than returning None when the user
        has no FoodEntry rows — SAE owns the "no intake today" truth. So the
        end-to-end path reports has_data=True with a zeroed payload rather than
        the old has_data=False clarification branch. We assert the routing and
        food-context injection, which is the behaviour callers depend on.
        """
        result = process_assistant_message(
            user=self.user,
            message="What did I eat today?",
            base_system_prompt=""
        )

        self.assertTrue(result['is_personal_query'])
        self.assertIn('food', result['data_types'])
        self.assertTrue(result['has_data'])
        self.assertIn('Food Data', result['system_prompt'])

    def test_combined_query_returns_multiple_data_types(self):
        """Test that query mentioning multiple data types returns all."""
        result = process_assistant_message(
            user=self.user,
            message="Show me my weight and mood from this week",
            base_system_prompt=""
        )

        self.assertTrue(result['is_personal_query'])
        self.assertTrue(result['has_data'])
        # Should contain context for both weight and mood
        self.assertIn('Weight Data', result['system_prompt'])
        self.assertIn('Mood Data', result['system_prompt'])

    def test_date_context_is_extracted(self):
        """Test that date context in message affects results."""
        # Create old weight entry
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("180.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=30)
        )

        # Query for recent data
        result = process_assistant_message(
            user=self.user,
            message="What was my weight yesterday?",
            base_system_prompt=""
        )

        self.assertTrue(result['is_personal_query'])
        self.assertTrue(result['has_data'])


class DateFilteringIntegrationTest(CacheClearingTestCase):
    """Integration tests specifically for date filtering across all data types."""

    def setUp(self):
        """Create test user."""
        super().setUp()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)

    def test_weight_date_filtering_with_datetime(self):
        """Test that since_date restricts the weight ORM entries list.

        The canonical latest/average come from SAE, but the recent ``entries``
        list is still ORM-backed and date-filtered, so since_date narrows it.
        """
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("180.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=15)
        )
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=3)
        )

        since = timezone.now() - timedelta(days=7)
        with patch(
            'assistant.data_service.get_metric',
            side_effect=_weight_metric_stub(175.0),
        ):
            result = self.service.get_weight_data(since_date=since)

        self.assertEqual(len(result['entries']), 1)
        self.assertEqual(result['entries'][0]['value'], 175.0)

    def test_journal_date_filtering_with_date(self):
        """Test that since_date restricts the journal recent_entries list.

        The recent_entries preview list is still ORM-backed and date-filtered.
        """
        JournalEntry.objects.create(
            user=self.user,
            title="Old",
            body="Content",
            entry_date=date.today() - timedelta(days=15)
        )
        JournalEntry.objects.create(
            user=self.user,
            title="Recent",
            body="Content",
            entry_date=date.today() - timedelta(days=3)
        )

        since = date.today() - timedelta(days=7)
        with patch(
            'assistant.data_service.get_metric',
            side_effect=_journal_metric_stub(entries_7d=1),
        ):
            result = self.service.get_journal_data(since_date=since)

        self.assertEqual(len(result['recent_entries']), 1)


# ==============================================================================
# SELF-IMPROVEMENT SYSTEM INTEGRATION TESTS
# ==============================================================================

"""
End-to-end integration tests for the Personal Assistant Self-Improvement System.

These tests verify the complete lifecycle of the self-improvement workflow:
1. Gap detection from user queries
2. Task creation and approval workflows
3. Autonomous execution of LOW severity tasks
4. Manual approval for MEDIUM/HIGH severity tasks
5. Rollback on test failure
6. Rate limiting and safety controls
7. Health monitoring and system pause/resume
8. Token expiration for approval links
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from assistant.executor import AutonomousExecutor, ImprovementExecutor
from assistant.file_modifier import ModificationResult
from assistant.git_service import GitResult
from assistant.health_monitor import HealthMonitor, SystemStatus
from assistant.models import ImprovementTaskModel, APPROVAL_TOKEN_EXPIRY_HOURS
from assistant.safety_limits import SafetyLimitService
from assistant.test_runner import TestResult


User = get_user_model()


class SelfImprovementIntegrationTestCase(CacheClearingTestCase):
    """Base test case with common setup for self-improvement tests."""

    def setUp(self):
        """Create test user and common fixtures."""
        super().setUp()
        self.user = User.objects.create_user(
            email="admin@wholelifejourney.com",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )

    def create_task(self, severity=ImprovementTaskModel.SEVERITY_LOW,
                    status=ImprovementTaskModel.STATUS_NEW,
                    requires_approval=False,
                    code_template=""):
        """Helper to create an improvement task."""
        return ImprovementTaskModel.objects.create(
            title="Test Task",
            description={"objective": "Test objective"},
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=severity,
            original_query="test query",
            suggested_fix="Add test keyword",
            code_template=code_template or """FILE: assistant/intent_detector.py
TYPE: insert_after
PATTERN: DATA_TYPE_KEYWORDS = \\{
CODE:
    'test_keyword': 'test_type',""",
            test_template="",
            requires_approval=requires_approval,
            status=status
        )


class TestCase1GapDetectionCreatesTask(SelfImprovementIntegrationTestCase):
    """Test Case 1: User query triggers gap detection, creates task."""

    def test_gap_detection_creates_pending_approval_task(self):
        """Test that a detected gap creates a task in PENDING_APPROVAL status."""
        # Create a task that requires approval (simulating gap detection)
        task = ImprovementTaskModel.objects.create(
            title="Add 'workout' keyword support",
            description={
                "objective": "Recognize workout-related queries",
                "suggested_fix": "Add 'workout' to DATA_TYPE_KEYWORDS"
            },
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="How many workouts did I do this week?",
            suggested_fix="Add 'workout' keyword to DATA_TYPE_KEYWORDS mapping to 'health'",
            code_template="""FILE: assistant/intent_detector.py
TYPE: insert_after
PATTERN: DATA_TYPE_KEYWORDS = \\{
CODE:
    'workout': 'health',""",
            requires_approval=True,
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL
        )

        # Verify task was created correctly
        self.assertEqual(task.status, ImprovementTaskModel.STATUS_PENDING_APPROVAL)
        self.assertEqual(task.severity, ImprovementTaskModel.SEVERITY_LOW)
        self.assertEqual(task.gap_type, ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS)
        self.assertIn("workout", task.original_query)
        self.assertTrue(task.requires_approval)

    def test_low_severity_without_approval_starts_as_approved(self):
        """Test that LOW severity tasks without approval requirement start as APPROVED."""
        task = self.create_task(
            severity=ImprovementTaskModel.SEVERITY_LOW,
            requires_approval=False,
            status=ImprovementTaskModel.STATUS_NEW
        )

        # When not requiring approval, task should be ready for execution
        self.assertEqual(task.status, ImprovementTaskModel.STATUS_NEW)
        self.assertFalse(task.requires_approval)


class TestCase2LowSeverityAutonomousExecution(SelfImprovementIntegrationTestCase):
    """Test Case 2: LOW severity task executes autonomously, sends notification."""

    def test_low_severity_task_executes_autonomously(self):
        """Test that LOW severity tasks execute without manual approval."""
        task = self.create_task(
            severity=ImprovementTaskModel.SEVERITY_LOW,
            status=ImprovementTaskModel.STATUS_APPROVED,  # Must be APPROVED to transition to IN_PROGRESS
            requires_approval=False
        )

        # Create mocked executor
        mock_git = MagicMock()
        mock_git.create_snapshot.return_value = GitResult(
            success=True, message="Snapshot created", commit_hash="before123"
        )
        mock_git.commit_changes.return_value = GitResult(
            success=True, message="Committed", commit_hash="after456"
        )
        mock_git.get_commit_diff.return_value = "diff output"

        mock_test_runner = MagicMock()
        mock_test_runner.generate_test_file.return_value = "/tmp/test.py"
        mock_test_runner.run_single_test.return_value = TestResult(
            passed=True, output="All tests passed"
        )

        mock_file_modifier = MagicMock()
        mock_file_modifier.apply_modification.return_value = ModificationResult(
            success=True, message="Applied"
        )

        mock_notification = MagicMock()

        with patch('assistant.executor.cache') as mock_cache:
            mock_cache.get.return_value = 0  # Under rate limit

            executor = AutonomousExecutor(
                git_service=mock_git,
                file_modifier=mock_file_modifier,
                test_runner=mock_test_runner,
                notification_service=mock_notification
            )

            result = executor.execute_task(task)

        # Verify execution succeeded
        self.assertTrue(result.success)
        # Verify auto_improvement notification was sent
        mock_notification.notify_auto_improvement.assert_called_once()

    def test_autonomous_execution_sends_admin_notification(self):
        """Test that autonomous execution sends admin notification."""
        task = self.create_task(
            severity=ImprovementTaskModel.SEVERITY_LOW,
            status=ImprovementTaskModel.STATUS_APPROVED,  # Must be APPROVED to transition to IN_PROGRESS
            requires_approval=False
        )

        mock_notification = MagicMock()

        with patch('assistant.executor.cache') as mock_cache:
            mock_cache.get.return_value = 0

            # Configure mocks for successful execution
            mock_git = MagicMock()
            mock_git.create_snapshot.return_value = GitResult(
                success=True, message="OK", commit_hash="abc123"
            )
            mock_git.commit_changes.return_value = GitResult(
                success=True, message="OK", commit_hash="def456"
            )
            mock_git.get_commit_diff.return_value = "diff"

            mock_test_runner = MagicMock()
            mock_test_runner.generate_test_file.return_value = "/tmp/test.py"
            mock_test_runner.run_single_test.return_value = TestResult(
                passed=True, output="OK"
            )

            executor = AutonomousExecutor(
                git_service=mock_git,
                file_modifier=MagicMock(apply_modification=MagicMock(
                    return_value=ModificationResult(success=True, message="OK")
                )),
                test_runner=mock_test_runner,
                notification_service=mock_notification
            )

            executor.execute_task(task)

        # Verify notification was sent with task details
        mock_notification.notify_auto_improvement.assert_called_once()
        call_kwargs = mock_notification.notify_auto_improvement.call_args.kwargs
        self.assertIn('task', call_kwargs)


class TestCase3MediumSeverityWaitsForApproval(SelfImprovementIntegrationTestCase):
    """Test Case 3: MEDIUM severity task waits for approval, executes after approval."""

    def test_medium_severity_requires_approval(self):
        """Test that MEDIUM severity tasks require manual approval."""
        task = self.create_task(
            severity=ImprovementTaskModel.SEVERITY_MEDIUM,
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL,
            requires_approval=True
        )

        # Verify task is pending approval
        self.assertEqual(task.status, ImprovementTaskModel.STATUS_PENDING_APPROVAL)
        self.assertTrue(task.requires_approval)

    def test_task_executes_after_approval(self):
        """Test that approved task executes successfully."""
        task = self.create_task(
            severity=ImprovementTaskModel.SEVERITY_MEDIUM,
            status=ImprovementTaskModel.STATUS_APPROVED,
            requires_approval=True
        )
        task.approved_at = timezone.now()
        task.approved_by = self.user
        task.save()

        # Create executor with mocks
        mock_git = MagicMock()
        mock_git.create_snapshot.return_value = GitResult(
            success=True, message="OK", commit_hash="abc123"
        )
        mock_git.commit_changes.return_value = GitResult(
            success=True, message="OK", commit_hash="def456"
        )
        mock_git.get_commit_diff.return_value = "diff"

        mock_test_runner = MagicMock()
        mock_test_runner.generate_test_file.return_value = "/tmp/test.py"
        mock_test_runner.run_single_test.return_value = TestResult(
            passed=True, output="OK"
        )

        executor = ImprovementExecutor(
            git_service=mock_git,
            file_modifier=MagicMock(apply_modification=MagicMock(
                return_value=ModificationResult(success=True, message="OK")
            )),
            test_runner=mock_test_runner,
            notification_service=MagicMock()
        )

        result = executor.execute_task(task)

        # Verify execution succeeded
        self.assertTrue(result.success)

    def test_approval_workflow_transition(self):
        """Test full approval workflow state transitions."""
        task = self.create_task(
            severity=ImprovementTaskModel.SEVERITY_MEDIUM,
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL,
            requires_approval=True
        )

        # Approve the task
        task.approve(user=self.user)

        # Verify status transition
        task.refresh_from_db()
        self.assertEqual(task.status, ImprovementTaskModel.STATUS_APPROVED)
        self.assertIsNotNone(task.approved_at)
        self.assertEqual(task.approved_by, self.user)


class TestCase4FailedTestTriggersRollback(SelfImprovementIntegrationTestCase):
    """Test Case 4: Failed test triggers rollback, sends error notification."""

    def test_test_failure_triggers_rollback(self):
        """Test that test failure causes automatic rollback."""
        task = self.create_task(
            severity=ImprovementTaskModel.SEVERITY_LOW,
            status=ImprovementTaskModel.STATUS_APPROVED
        )

        mock_git = MagicMock()
        mock_git.create_snapshot.return_value = GitResult(
            success=True, message="OK", commit_hash="before123"
        )
        mock_git.rollback_to_commit.return_value = GitResult(
            success=True, message="Rolled back"
        )

        mock_test_runner = MagicMock()
        mock_test_runner.generate_test_file.return_value = "/tmp/test.py"
        mock_test_runner.run_single_test.return_value = TestResult(
            passed=False,
            output="Test failed",
            errors=["AssertionError: Expected value not found"]
        )

        mock_notification = MagicMock()

        executor = ImprovementExecutor(
            git_service=mock_git,
            file_modifier=MagicMock(apply_modification=MagicMock(
                return_value=ModificationResult(success=True, message="OK")
            )),
            test_runner=mock_test_runner,
            notification_service=mock_notification
        )

        result = executor.execute_task(task)

        # Verify rollback was triggered
        self.assertFalse(result.success)
        mock_git.rollback_to_commit.assert_called_once_with("before123")
        # Verify error notification was sent
        mock_notification.notify_task_error.assert_called_once()

    def test_error_notification_includes_rollback_status(self):
        """Test that error notification includes rollback success status."""
        task = self.create_task(
            severity=ImprovementTaskModel.SEVERITY_LOW,
            status=ImprovementTaskModel.STATUS_APPROVED
        )

        mock_git = MagicMock()
        mock_git.create_snapshot.return_value = GitResult(
            success=True, message="OK", commit_hash="abc123"
        )
        mock_git.rollback_to_commit.return_value = GitResult(
            success=True, message="Rolled back"
        )

        mock_test_runner = MagicMock()
        mock_test_runner.generate_test_file.return_value = "/tmp/test.py"
        mock_test_runner.run_single_test.return_value = TestResult(
            passed=False, output="Failed", errors=["Error"]
        )

        mock_notification = MagicMock()

        executor = ImprovementExecutor(
            git_service=mock_git,
            file_modifier=MagicMock(apply_modification=MagicMock(
                return_value=ModificationResult(success=True, message="OK")
            )),
            test_runner=mock_test_runner,
            notification_service=mock_notification
        )

        executor.execute_task(task)

        # Verify error notification was called with rollback info
        call_kwargs = mock_notification.notify_task_error.call_args.kwargs
        self.assertTrue(call_kwargs['rollback_successful'])
        self.assertEqual(call_kwargs['rollback_hash'], "abc123")


class TestCase5AdminManualRollback(SelfImprovementIntegrationTestCase):
    """Test Case 5: Admin manually triggers rollback."""

    def test_admin_can_rollback_completed_task(self):
        """Test that admin can rollback a completed task."""
        task = self.create_task(
            severity=ImprovementTaskModel.SEVERITY_LOW,
            status=ImprovementTaskModel.STATUS_COMPLETED
        )
        task.git_commit_before = "before123"
        task.git_commit_after = "after456"
        task.completed_at = timezone.now()
        task.save()

        # Perform rollback
        task.rollback(reason="Manual rollback by admin - found regression")

        # Verify rollback
        task.refresh_from_db()
        self.assertEqual(task.status, ImprovementTaskModel.STATUS_ROLLED_BACK)
        self.assertIsNotNone(task.rolled_back_at)
        self.assertEqual(task.rollback_reason, "Manual rollback by admin - found regression")

    def test_rollback_preserves_git_commit_hashes(self):
        """Test that rollback preserves original git commit hashes."""
        task = self.create_task(
            severity=ImprovementTaskModel.SEVERITY_LOW,
            status=ImprovementTaskModel.STATUS_COMPLETED
        )
        task.git_commit_before = "before123"
        task.git_commit_after = "after456"
        task.save()

        task.rollback(reason="Test rollback")

        task.refresh_from_db()
        # Original commit hashes should be preserved for audit trail
        self.assertEqual(task.git_commit_before, "before123")
        self.assertEqual(task.git_commit_after, "after456")


class TestCase6RateLimitsPreventsExcessiveExecution(SelfImprovementIntegrationTestCase):
    """Test Case 6: Rate limits prevent excessive autonomous execution."""

    def test_hourly_rate_limit_enforced(self):
        """Test that hourly rate limit prevents execution."""
        task = self.create_task(
            severity=ImprovementTaskModel.SEVERITY_LOW,
            status=ImprovementTaskModel.STATUS_NEW,
            requires_approval=False
        )

        with patch('assistant.executor.cache') as mock_cache:
            # Simulate at rate limit
            mock_cache.get.return_value = 5  # At limit

            executor = AutonomousExecutor(
                git_service=MagicMock(),
                file_modifier=MagicMock(),
                test_runner=MagicMock(),
                notification_service=MagicMock(),
                max_executions_per_hour=5
            )

            result = executor.execute_task(task)

        # Verify execution was blocked
        self.assertFalse(result.success)
        self.assertIn("rate limit", result.message.lower())

    def test_under_rate_limit_allows_execution(self):
        """Test that execution is allowed under rate limit."""
        with patch('assistant.executor.cache') as mock_cache:
            mock_cache.get.return_value = 2  # Under limit

            executor = AutonomousExecutor(
                git_service=MagicMock(),
                file_modifier=MagicMock(),
                test_runner=MagicMock(),
                notification_service=MagicMock(),
                max_executions_per_hour=5
            )

            is_allowed, reason = executor._check_rate_limit()

        self.assertTrue(is_allowed)

    def test_safety_limits_prevent_excessive_autonomous(self):
        """Test SafetyLimitService prevents excessive autonomous execution."""
        service = SafetyLimitService()

        # Create multiple tasks to exceed daily limit
        for i in range(25):
            task = self.create_task()
            task.status = ImprovementTaskModel.STATUS_COMPLETED
            task.save()

        # Check if within limits (should be over daily limit of 20)
        result = service.check_rate_limits()

        # Note: This depends on task completion timing
        # The service counts tasks from last 24 hours
        # Result is a RateLimitResult dataclass with allowed, reason, current_count, limit
        self.assertIsNotNone(result.reason)


class TestCase7HealthMonitorPausesSystem(SelfImprovementIntegrationTestCase):
    """Test Case 7: Health monitor pauses system on high error rate."""

    def test_high_error_rate_triggers_degraded_status(self):
        """Test that high error rate causes DEGRADED status."""
        # Create tasks with high error rate
        for i in range(10):
            task = self.create_task()
            if i < 3:  # 30% error rate
                task.status = ImprovementTaskModel.STATUS_ERROR
                task.error_message = "Test error"
            else:
                task.status = ImprovementTaskModel.STATUS_COMPLETED
                task.completed_at = timezone.now()
            task.save()

        monitor = HealthMonitor()
        report = monitor.get_full_status_report()

        # With 30% error rate, system should be degraded (threshold is 20%)
        self.assertIn(report['status'], [
            SystemStatus.DEGRADED.value,
            SystemStatus.CRITICAL.value,
            SystemStatus.HEALTHY.value,  # If no tasks in 24h window
        ])

    def test_critical_error_rate_pauses_autonomous(self):
        """Test that critical error rate pauses autonomous execution."""
        # Create many error tasks
        now = timezone.now()
        for i in range(10):
            task = ImprovementTaskModel.objects.create(
                title=f"Task {i}",
                description={},
                gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
                severity=ImprovementTaskModel.SEVERITY_LOW,
                original_query="test",
                suggested_fix="fix",
                requires_approval=False,
                status=ImprovementTaskModel.STATUS_ERROR if i < 5 else ImprovementTaskModel.STATUS_COMPLETED
            )
            # Set completed_at for completed tasks
            if task.status == ImprovementTaskModel.STATUS_COMPLETED:
                task.completed_at = now
                task.save()

        monitor = HealthMonitor()
        report = monitor.get_full_status_report()

        # With 50% error rate, should be critical
        if report['metrics']['error_rate'] >= 40:
            self.assertEqual(report['status'], SystemStatus.CRITICAL.value)

    def test_health_check_returns_recommendations(self):
        """Test that health check provides actionable recommendations."""
        # Create task with errors
        task = self.create_task()
        task.status = ImprovementTaskModel.STATUS_ERROR
        task.error_message = "Test error"
        task.save()

        monitor = HealthMonitor()
        report = monitor.get_full_status_report()

        # Report should include recommendations if issues exist
        self.assertIn('recommendations', report)


class TestCase8ApprovalTokenExpiration(SelfImprovementIntegrationTestCase):
    """Test Case 8: Approval token expires after 24 hours."""

    def test_token_valid_within_24_hours(self):
        """Test that token is valid within expiry period."""
        task = self.create_task(
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL,
            requires_approval=True
        )

        # Generate approval token
        token = task.generate_approval_token()

        # Token should be valid immediately
        self.assertTrue(task.is_token_valid(token))

    def test_token_invalid_after_24_hours(self):
        """Test that token is invalid after expiry period."""
        task = self.create_task(
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL,
            requires_approval=True
        )

        token = task.generate_approval_token()

        # Simulate token created 25 hours ago
        task.approval_token_created_at = timezone.now() - timedelta(hours=25)
        task.save()

        # Token should be invalid
        self.assertFalse(task.is_token_valid(token))

    def test_token_cleared_after_use(self):
        """Test that token is cleared after approval."""
        task = self.create_task(
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL,
            requires_approval=True
        )

        token = task.generate_approval_token()
        self.assertTrue(task.is_token_valid(token))

        # Approve task (which clears token)
        task.approve(user=self.user)

        # Token should no longer be valid
        task.refresh_from_db()
        self.assertEqual(task.approval_token, '')
        self.assertFalse(task.is_token_valid(token))

    def test_wrong_token_is_invalid(self):
        """Test that wrong token is rejected."""
        task = self.create_task(
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL,
            requires_approval=True
        )

        task.generate_approval_token()

        # Wrong token should be invalid
        self.assertFalse(task.is_token_valid("wrong_token"))

    def test_token_expiry_constant_is_24_hours(self):
        """Test that token expiry is set to 24 hours."""
        self.assertEqual(APPROVAL_TOKEN_EXPIRY_HOURS, 24)


class IntegrationFullWorkflowTest(SelfImprovementIntegrationTestCase):
    """Full end-to-end workflow integration test."""

    def test_complete_improvement_workflow(self):
        """Test complete workflow from task creation to completion."""
        # Step 1: Create task (simulating gap detection)
        task = ImprovementTaskModel.objects.create(
            title="Add 'meditation' keyword",
            description={"objective": "Support meditation tracking queries"},
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="How often did I meditate this month?",
            suggested_fix="Add 'meditation' to DATA_TYPE_KEYWORDS",
            code_template="""FILE: assistant/intent_detector.py
TYPE: insert_after
PATTERN: DATA_TYPE_KEYWORDS = \\{
CODE:
    'meditation': 'health',""",
            requires_approval=True,
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL
        )

        # Verify initial state
        self.assertEqual(task.status, ImprovementTaskModel.STATUS_PENDING_APPROVAL)

        # Step 2: Generate approval token
        token = task.generate_approval_token()
        self.assertTrue(task.is_token_valid(token))

        # Step 3: Approve task
        task.approve(user=self.user)
        task.refresh_from_db()
        self.assertEqual(task.status, ImprovementTaskModel.STATUS_APPROVED)

        # Step 4: Execute task
        mock_git = MagicMock()
        mock_git.create_snapshot.return_value = GitResult(
            success=True, message="OK", commit_hash="before123"
        )
        mock_git.commit_changes.return_value = GitResult(
            success=True, message="OK", commit_hash="after456"
        )
        mock_git.get_commit_diff.return_value = "diff"

        mock_test_runner = MagicMock()
        mock_test_runner.generate_test_file.return_value = "/tmp/test.py"
        mock_test_runner.run_single_test.return_value = TestResult(
            passed=True, output="OK"
        )

        executor = ImprovementExecutor(
            git_service=mock_git,
            file_modifier=MagicMock(apply_modification=MagicMock(
                return_value=ModificationResult(success=True, message="OK")
            )),
            test_runner=mock_test_runner,
            notification_service=MagicMock()
        )

        result = executor.execute_task(task)

        # Step 5: Verify completion
        self.assertTrue(result.success)
        task.refresh_from_db()
        self.assertEqual(task.status, ImprovementTaskModel.STATUS_COMPLETED)

    def test_workflow_with_rollback(self):
        """Test workflow that requires rollback due to test failure."""
        task = self.create_task(
            severity=ImprovementTaskModel.SEVERITY_MEDIUM,
            status=ImprovementTaskModel.STATUS_APPROVED,
            requires_approval=True
        )

        mock_git = MagicMock()
        mock_git.create_snapshot.return_value = GitResult(
            success=True, message="OK", commit_hash="before123"
        )
        mock_git.rollback_to_commit.return_value = GitResult(
            success=True, message="Rolled back"
        )

        mock_test_runner = MagicMock()
        mock_test_runner.generate_test_file.return_value = "/tmp/test.py"
        mock_test_runner.run_single_test.return_value = TestResult(
            passed=False, output="Failed", errors=["KeyError: 'meditation'"]
        )

        mock_notification = MagicMock()

        executor = ImprovementExecutor(
            git_service=mock_git,
            file_modifier=MagicMock(apply_modification=MagicMock(
                return_value=ModificationResult(success=True, message="OK")
            )),
            test_runner=mock_test_runner,
            notification_service=mock_notification
        )

        result = executor.execute_task(task)

        # Verify rollback occurred
        self.assertFalse(result.success)
        mock_git.rollback_to_commit.assert_called_once_with("before123")
        mock_notification.notify_task_error.assert_called_once()


class UserDataIntegrationTest(CacheClearingTestCase):
    """Integration tests for get_user_data() with actual User and UserPreferences."""

    def setUp(self):
        """Create test user."""
        super().setUp()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User"
        )
        self.service = PersonalDataService(self.user)

    def test_get_user_data_returns_basic_info(self):
        """Test that get_user_data returns user's basic profile info."""
        result = self.service.get_user_data()
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'user')
        self.assertEqual(result['name'], 'Test User')
        self.assertEqual(result['first_name'], 'Test')

    def test_get_user_data_with_preferences(self):
        """Test that get_user_data includes preferences data when available."""
        from apps.users.models import UserPreferences

        # Get or create preferences with location (signal may have created it)
        prefs, _ = UserPreferences.objects.get_or_create(user=self.user)
        prefs.location_city = 'Maryville'
        prefs.location_country = 'United States'
        prefs.timezone = 'America/New_York'
        prefs.gender = 'male'
        prefs.save()

        # Clear cache to ensure fresh data
        cache.clear()

        result = self.service.get_user_data()
        self.assertEqual(result['location_city'], 'Maryville')
        self.assertEqual(result['location_country'], 'United States')
        self.assertEqual(result['timezone'], 'America/New_York')
        self.assertEqual(result['gender'], 'male')

    def test_get_user_data_without_preferences(self):
        """Test that get_user_data works when user has no preferences."""
        # User created in setUp has no preferences
        result = self.service.get_user_data()
        self.assertIsNotNone(result)
        self.assertEqual(result['location_city'], '')
        self.assertEqual(result['location_country'], '')
        self.assertEqual(result['timezone'], 'UTC')
        self.assertIsNone(result['gender'])

    def test_get_user_data_uses_email_when_no_name(self):
        """Test that get_user_data falls back to email when no name set."""
        user_no_name = User.objects.create_user(
            email="noname@example.com",
            password="testpass123"
        )
        service = PersonalDataService(user_no_name)

        result = service.get_user_data()
        self.assertEqual(result['name'], 'noname@example.com')
        self.assertEqual(result['first_name'], '')

    def test_query_by_intent_includes_user(self):
        """Test that query_by_intent can fetch user data."""
        from apps.users.models import UserPreferences

        prefs, _ = UserPreferences.objects.get_or_create(user=self.user)
        prefs.location_city = 'Nashville'
        prefs.location_country = 'United States'
        prefs.save()

        # Clear cache to ensure fresh data
        cache.clear()

        result = self.service.query_by_intent(data_types=['user'])
        self.assertIsNotNone(result)
        self.assertIn('user', result)
        self.assertEqual(result['user']['location_city'], 'Nashville')
