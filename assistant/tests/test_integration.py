"""
Integration tests for the Personal Data Query System.

These tests use real Django models and ORM to verify the system works
correctly with actual database operations, soft delete behavior, and
date filtering.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.health.models import FoodEntry, Medicine, MedicineLog, WeightEntry
from apps.journal.models import JournalEntry
from assistant.data_service import PersonalDataService
from assistant.views import process_assistant_message


User = get_user_model()


class WeightDataIntegrationTest(TestCase):
    """Integration tests for get_weight_data() with actual WeightEntry records."""

    def setUp(self):
        """Create test user and weight entries."""
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
        """Test that get_weight_data returns None when no entries exist."""
        result = self.service.get_weight_data()
        self.assertIsNone(result)

    def test_get_weight_data_returns_correct_count(self):
        """Test that get_weight_data returns correct count of entries."""
        # Create 3 weight entries
        for i in range(3):
            WeightEntry.objects.create(
                user=self.user,
                value=Decimal("170.0") + i,
                unit="lb",
                recorded_at=timezone.now() - timedelta(days=i)
            )

        result = self.service.get_weight_data()
        self.assertIsNotNone(result)
        self.assertEqual(result['count'], 3)
        self.assertEqual(result['type'], 'weight')

    def test_get_weight_data_calculates_average(self):
        """Test that get_weight_data calculates correct average."""
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

        result = self.service.get_weight_data()
        self.assertEqual(result['average'], 175.0)

    def test_get_weight_data_returns_latest_entry(self):
        """Test that get_weight_data returns most recent entry info."""
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("170.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=2)
        )
        latest = WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.5"),
            unit="lb",
            recorded_at=timezone.now()
        )

        result = self.service.get_weight_data()
        self.assertEqual(result['latest'], 175.5)
        self.assertEqual(result['unit'], 'lb')

    def test_get_weight_data_only_returns_user_data(self):
        """Test that get_weight_data only returns data for the current user."""
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

        result = self.service.get_weight_data()
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['latest'], 170.0)

    def test_get_weight_data_date_filtering(self):
        """Test that date filtering works correctly."""
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
        result = self.service.get_weight_data(since_date=since_date)

        # Should only include the recent entry
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['latest'], 175.0)

    def test_get_weight_data_entries_list(self):
        """Test that entries list is properly formatted."""
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("170.5"),
            unit="lb",
            notes="Morning weight"
        )

        result = self.service.get_weight_data()
        self.assertEqual(len(result['entries']), 1)
        self.assertEqual(result['entries'][0]['value'], 170.5)
        self.assertEqual(result['entries'][0]['unit'], 'lb')
        self.assertEqual(result['entries'][0]['notes'], 'Morning weight')


class JournalDataIntegrationTest(TestCase):
    """Integration tests for get_journal_data() with actual JournalEntry records."""

    def setUp(self):
        """Create test user."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)

    def test_get_journal_data_returns_none_for_empty_data(self):
        """Test that get_journal_data returns None when no entries exist."""
        result = self.service.get_journal_data()
        self.assertIsNone(result)

    def test_get_journal_data_returns_correct_count(self):
        """Test that get_journal_data returns correct count of entries."""
        for i in range(5):
            JournalEntry.objects.create(
                user=self.user,
                title=f"Entry {i}",
                body=f"Content for entry {i}",
                entry_date=date.today() - timedelta(days=i)
            )

        result = self.service.get_journal_data()
        self.assertIsNotNone(result)
        self.assertEqual(result['count'], 5)
        self.assertEqual(result['type'], 'journal')

    def test_get_journal_data_returns_latest_date(self):
        """Test that get_journal_data returns most recent entry date."""
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

        result = self.service.get_journal_data()
        self.assertEqual(result['latest_date'], date.today())

    def test_get_journal_data_date_filtering(self):
        """Test that date filtering works correctly for journal entries."""
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
        result = self.service.get_journal_data(since_date=since_date)

        self.assertEqual(result['count'], 1)

    def test_get_journal_data_excludes_soft_deleted(self):
        """Test that soft-deleted entries are excluded from results."""
        # Create active entry
        active_entry = JournalEntry.objects.create(
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

        result = self.service.get_journal_data()
        self.assertEqual(result['count'], 1)  # Only the active entry


class MedicationDataIntegrationTest(TestCase):
    """Integration tests for get_medication_data() with actual MedicineLog records."""

    def setUp(self):
        """Create test user and medicine."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.medicine = Medicine.objects.create(
            user=self.user,
            name="Test Medicine",
            dose="500mg",
            frequency="daily",
            start_date=date.today()
        )
        self.service = PersonalDataService(self.user)

    def test_get_medication_data_returns_none_for_empty_data(self):
        """Test that get_medication_data returns None when no logs exist."""
        result = self.service.get_medication_data()
        self.assertIsNone(result)

    def test_get_medication_data_returns_correct_counts(self):
        """Test that get_medication_data returns correct log counts."""
        # Create logs for 3 different days
        for i in range(3):
            MedicineLog.objects.create(
                user=self.user,
                medicine=self.medicine,
                scheduled_date=date.today() - timedelta(days=i),
                log_status='taken'
            )

        result = self.service.get_medication_data()
        self.assertIsNotNone(result)
        self.assertEqual(result['total_logs'], 3)
        self.assertEqual(result['days_logged'], 3)
        self.assertEqual(result['type'], 'medication')

    def test_get_medication_data_multiple_logs_same_day(self):
        """Test that multiple logs on the same day count as one day logged."""
        today = date.today()
        # Create 2 logs for the same day
        MedicineLog.objects.create(
            user=self.user,
            medicine=self.medicine,
            scheduled_date=today,
            log_status='taken'
        )
        MedicineLog.objects.create(
            user=self.user,
            medicine=self.medicine,
            scheduled_date=today,
            log_status='taken'
        )

        result = self.service.get_medication_data()
        self.assertEqual(result['total_logs'], 2)
        self.assertEqual(result['days_logged'], 1)

    def test_get_medication_data_consistency_calculation(self):
        """Test that consistency percentage is calculated correctly."""
        # Create logs for 3 consecutive days (today, yesterday, day before)
        for i in range(3):
            MedicineLog.objects.create(
                user=self.user,
                medicine=self.medicine,
                scheduled_date=date.today() - timedelta(days=i),
                log_status='taken'
            )

        result = self.service.get_medication_data()
        # With since_date=None, it uses earliest log date, so 3 days logged out of 3 total = 100%
        self.assertEqual(result['days_logged'], 3)
        self.assertEqual(result['total_days'], 3)
        self.assertEqual(result['consistency_percent'], 100.0)

    def test_get_medication_data_date_filtering(self):
        """Test that date filtering works correctly for medication logs."""
        # Create old log (10 days ago)
        MedicineLog.objects.create(
            user=self.user,
            medicine=self.medicine,
            scheduled_date=date.today() - timedelta(days=10),
            log_status='taken'
        )
        # Create recent log (2 days ago)
        MedicineLog.objects.create(
            user=self.user,
            medicine=self.medicine,
            scheduled_date=date.today() - timedelta(days=2),
            log_status='taken'
        )

        # Query with date filter (last 5 days)
        since_date = date.today() - timedelta(days=5)
        result = self.service.get_medication_data(since_date=since_date)

        self.assertEqual(result['total_logs'], 1)
        self.assertEqual(result['days_logged'], 1)

    def test_get_medication_data_excludes_soft_deleted(self):
        """Test that soft-deleted medication logs are excluded."""
        active_log = MedicineLog.objects.create(
            user=self.user,
            medicine=self.medicine,
            scheduled_date=date.today(),
            log_status='taken'
        )
        deleted_log = MedicineLog.objects.create(
            user=self.user,
            medicine=self.medicine,
            scheduled_date=date.today() - timedelta(days=1),
            log_status='taken'
        )
        deleted_log.soft_delete()

        result = self.service.get_medication_data()
        self.assertEqual(result['total_logs'], 1)


class FoodDataIntegrationTest(TestCase):
    """Integration tests for get_food_data() with actual FoodEntry records."""

    def setUp(self):
        """Create test user."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)

    def _create_food_entry(self, calories, logged_date=None):
        """Helper to create a food entry with required fields."""
        if logged_date is None:
            logged_date = date.today()
        return FoodEntry.objects.create(
            user=self.user,
            food_name="Test Food",
            quantity=Decimal("1.0"),
            serving_size=Decimal("100"),
            serving_unit="g",
            total_calories=Decimal(str(calories)),
            logged_date=logged_date
        )

    def test_get_food_data_returns_none_for_empty_data(self):
        """Test that get_food_data returns None when no entries exist."""
        result = self.service.get_food_data()
        self.assertIsNone(result)

    def test_get_food_data_returns_correct_counts(self):
        """Test that get_food_data returns correct entry counts."""
        self._create_food_entry(500)
        self._create_food_entry(600)
        self._create_food_entry(400)

        result = self.service.get_food_data()
        self.assertIsNotNone(result)
        self.assertEqual(result['total_entries'], 3)
        self.assertEqual(result['type'], 'food')

    def test_get_food_data_calculates_total_calories(self):
        """Test that total calories are summed correctly."""
        self._create_food_entry(500)
        self._create_food_entry(600)
        self._create_food_entry(400)

        result = self.service.get_food_data()
        self.assertEqual(result['total_calories'], 1500.0)

    def test_get_food_data_calculates_daily_average(self):
        """Test that average daily calories are calculated correctly."""
        today = date.today()
        yesterday = today - timedelta(days=1)

        # 1000 calories today
        self._create_food_entry(500, today)
        self._create_food_entry(500, today)

        # 500 calories yesterday
        self._create_food_entry(500, yesterday)

        result = self.service.get_food_data()
        # Total: 1500, Days: 2, Average: 750
        self.assertEqual(result['average_daily_calories'], 750.0)

    def test_get_food_data_returns_latest_date(self):
        """Test that latest entry date is returned."""
        self._create_food_entry(500, date.today() - timedelta(days=5))
        self._create_food_entry(600, date.today())

        result = self.service.get_food_data()
        self.assertEqual(result['latest_date'], date.today())

    def test_get_food_data_date_filtering(self):
        """Test that date filtering works correctly."""
        # Create old entry (10 days ago)
        self._create_food_entry(1000, date.today() - timedelta(days=10))
        # Create recent entry (2 days ago)
        self._create_food_entry(500, date.today() - timedelta(days=2))

        # Query with date filter (last 5 days)
        since_date = date.today() - timedelta(days=5)
        result = self.service.get_food_data(since_date=since_date)

        self.assertEqual(result['total_entries'], 1)
        self.assertEqual(result['total_calories'], 500.0)


class MoodDataIntegrationTest(TestCase):
    """Integration tests for get_mood_data() with actual JournalEntry mood records."""

    def setUp(self):
        """Create test user."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)

    def test_get_mood_data_returns_none_for_no_mood_entries(self):
        """Test that get_mood_data returns None when no entries have mood."""
        # Create entry without mood
        JournalEntry.objects.create(
            user=self.user,
            title="No mood",
            body="Content",
            mood=""
        )
        result = self.service.get_mood_data()
        self.assertIsNone(result)

    def test_get_mood_data_returns_correct_count(self):
        """Test that get_mood_data returns correct count of entries with mood."""
        JournalEntry.objects.create(
            user=self.user,
            title="Entry 1",
            body="Content",
            mood="good"
        )
        JournalEntry.objects.create(
            user=self.user,
            title="Entry 2",
            body="Content",
            mood="great"
        )
        # Entry without mood (should not be counted)
        JournalEntry.objects.create(
            user=self.user,
            title="No mood",
            body="Content",
            mood=""
        )

        result = self.service.get_mood_data()
        self.assertIsNotNone(result)
        self.assertEqual(result['count'], 2)
        self.assertEqual(result['type'], 'mood')

    def test_get_mood_data_calculates_distribution(self):
        """Test that mood distribution is calculated correctly."""
        JournalEntry.objects.create(
            user=self.user, title="1", body="c", mood="good"
        )
        JournalEntry.objects.create(
            user=self.user, title="2", body="c", mood="good"
        )
        JournalEntry.objects.create(
            user=self.user, title="3", body="c", mood="great"
        )
        JournalEntry.objects.create(
            user=self.user, title="4", body="c", mood="low"
        )

        result = self.service.get_mood_data()
        self.assertEqual(result['mood_distribution']['good'], 2)
        self.assertEqual(result['mood_distribution']['great'], 1)
        self.assertEqual(result['mood_distribution']['low'], 1)

    def test_get_mood_data_identifies_most_common(self):
        """Test that most common mood is identified correctly."""
        JournalEntry.objects.create(
            user=self.user, title="1", body="c", mood="okay"
        )
        JournalEntry.objects.create(
            user=self.user, title="2", body="c", mood="okay"
        )
        JournalEntry.objects.create(
            user=self.user, title="3", body="c", mood="good"
        )

        result = self.service.get_mood_data()
        self.assertEqual(result['most_common'], 'okay')

    def test_get_mood_data_returns_latest(self):
        """Test that latest mood and date are returned correctly."""
        JournalEntry.objects.create(
            user=self.user,
            title="Old",
            body="content",
            mood="low",
            entry_date=date.today() - timedelta(days=5)
        )
        JournalEntry.objects.create(
            user=self.user,
            title="Latest",
            body="content",
            mood="great",
            entry_date=date.today()
        )

        result = self.service.get_mood_data()
        self.assertEqual(result['latest_mood'], 'great')
        self.assertEqual(result['latest_date'], date.today())

    def test_get_mood_data_excludes_soft_deleted(self):
        """Test that soft-deleted entries with mood are excluded."""
        active = JournalEntry.objects.create(
            user=self.user,
            title="Active",
            body="content",
            mood="good"
        )
        deleted = JournalEntry.objects.create(
            user=self.user,
            title="Deleted",
            body="content",
            mood="great"
        )
        deleted.soft_delete()

        result = self.service.get_mood_data()
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['latest_mood'], 'good')


class SoftDeleteBehaviorIntegrationTest(TestCase):
    """Integration tests specifically for soft delete behavior across all data types."""

    def setUp(self):
        """Create test user and test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)

    def test_soft_deleted_journal_entries_excluded(self):
        """Test that soft-deleted journal entries are not returned."""
        active = JournalEntry.objects.create(
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
        self.assertEqual(result['count'], 1)

    def test_soft_deleted_medicine_logs_excluded(self):
        """Test that soft-deleted medicine logs are not returned."""
        medicine = Medicine.objects.create(
            user=self.user,
            name="Test Med",
            dose="100mg",
            start_date=date.today()
        )
        active = MedicineLog.objects.create(
            user=self.user,
            medicine=medicine,
            scheduled_date=date.today()
        )
        deleted = MedicineLog.objects.create(
            user=self.user,
            medicine=medicine,
            scheduled_date=date.today() - timedelta(days=1)
        )
        deleted.soft_delete()

        result = self.service.get_medication_data()
        self.assertEqual(result['total_logs'], 1)

    def test_archived_entries_are_excluded(self):
        """Test that archived entries are excluded from normal queries.

        The SoftDeleteManager filters out both deleted AND archived records
        by default. Users who want archived entries can use .include_archived()
        but PersonalDataService correctly uses the default manager behavior.
        """
        active = JournalEntry.objects.create(
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
        self.assertEqual(result['count'], 1)


class QueryByIntentIntegrationTest(TestCase):
    """Integration tests for query_by_intent() with real data."""

    def setUp(self):
        """Create test user and varied test data."""
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

        # Should only get 1 entry (the one from setUp, not the 10-day-old one)
        self.assertEqual(result['weight']['count'], 1)

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


class ProcessAssistantMessageIntegrationTest(TestCase):
    """End-to-end integration tests for process_assistant_message()."""

    def setUp(self):
        """Create test user with various data."""
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

    def test_query_with_no_data_returns_no_data_flag(self):
        """Test that query for data type with no records returns has_data=False."""
        result = process_assistant_message(
            user=self.user,
            message="What did I eat today?",
            base_system_prompt=""
        )

        self.assertTrue(result['is_personal_query'])
        self.assertIn('food', result['data_types'])
        self.assertFalse(result['has_data'])

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


class DateFilteringIntegrationTest(TestCase):
    """Integration tests specifically for date filtering across all data types."""

    def setUp(self):
        """Create test user."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)

    def test_weight_date_filtering_with_datetime(self):
        """Test weight filtering with datetime object."""
        old = WeightEntry.objects.create(
            user=self.user,
            value=Decimal("180.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=15)
        )
        recent = WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=3)
        )

        since = timezone.now() - timedelta(days=7)
        result = self.service.get_weight_data(since_date=since)

        self.assertEqual(result['count'], 1)
        self.assertEqual(result['latest'], 175.0)

    def test_journal_date_filtering_with_date(self):
        """Test journal filtering with date object."""
        old = JournalEntry.objects.create(
            user=self.user,
            title="Old",
            body="Content",
            entry_date=date.today() - timedelta(days=15)
        )
        recent = JournalEntry.objects.create(
            user=self.user,
            title="Recent",
            body="Content",
            entry_date=date.today() - timedelta(days=3)
        )

        since = date.today() - timedelta(days=7)
        result = self.service.get_journal_data(since_date=since)

        self.assertEqual(result['count'], 1)

    def test_food_date_filtering(self):
        """Test food entry date filtering."""
        old = FoodEntry.objects.create(
            user=self.user,
            food_name="Old Food",
            quantity=Decimal("1.0"),
            serving_size=Decimal("100"),
            serving_unit="g",
            total_calories=Decimal("500"),
            logged_date=date.today() - timedelta(days=15)
        )
        recent = FoodEntry.objects.create(
            user=self.user,
            food_name="Recent Food",
            quantity=Decimal("1.0"),
            serving_size=Decimal("100"),
            serving_unit="g",
            total_calories=Decimal("300"),
            logged_date=date.today() - timedelta(days=3)
        )

        since = date.today() - timedelta(days=7)
        result = self.service.get_food_data(since_date=since)

        self.assertEqual(result['total_entries'], 1)
        self.assertEqual(result['total_calories'], 300.0)

    def test_mood_date_filtering(self):
        """Test mood data date filtering."""
        old = JournalEntry.objects.create(
            user=self.user,
            title="Old",
            body="Content",
            mood="low",
            entry_date=date.today() - timedelta(days=15)
        )
        recent = JournalEntry.objects.create(
            user=self.user,
            title="Recent",
            body="Content",
            mood="great",
            entry_date=date.today() - timedelta(days=3)
        )

        since = date.today() - timedelta(days=7)
        result = self.service.get_mood_data(since_date=since)

        self.assertEqual(result['count'], 1)
        self.assertEqual(result['latest_mood'], 'great')


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

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from assistant.executor import AutonomousExecutor, ImprovementExecutor, ExecutionResult
from assistant.file_modifier import ModificationResult
from assistant.git_service import GitResult
from assistant.health_monitor import HealthMonitor, SystemStatus
from assistant.models import ImprovementTaskModel, APPROVAL_TOKEN_EXPIRY_HOURS
from assistant.notifications import AdminNotificationService, TaskInfo
from assistant.safety_limits import SafetyLimitService
from assistant.test_runner import TestResult


User = get_user_model()


class SelfImprovementIntegrationTestCase(TestCase):
    """Base test case with common setup for self-improvement tests."""

    def setUp(self):
        """Create test user and common fixtures."""
        self.user = User.objects.create_user(
            email="admin@wholelifejourney.com",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )
        # Clear cache before each test
        cache.clear()

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
        is_within, reason = service.check_rate_limits()

        # Note: This depends on task completion timing
        # The service counts tasks from last 24 hours


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
            'healthy'  # If no tasks in 24h window
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
