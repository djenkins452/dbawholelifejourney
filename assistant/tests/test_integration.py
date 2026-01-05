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
            frequency="daily"
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
            dose="100mg"
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

    def test_archived_entries_are_included(self):
        """Test that archived (but not deleted) entries are still included."""
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
        self.assertEqual(result['count'], 2)


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
