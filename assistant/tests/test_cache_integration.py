"""
Cache Integration Tests for the Personal Data Query System.

These tests verify caching behavior with Django's cache framework
rather than mocks, including cache hits, misses, and signal-based
invalidation.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.health.models import FoodEntry, Medicine, MedicineLog, WeightEntry
from apps.journal.models import JournalEntry
from assistant.data_service import (
    PERSONAL_DATA_CACHE_TTL,
    PersonalDataService,
    _generate_cache_key,
    invalidate_user_data_cache,
)


User = get_user_model()


# Use locmem cache for testing to ensure we have a real working cache
CACHE_SETTINGS = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}


@override_settings(CACHES=CACHE_SETTINGS)
class CacheKeyGenerationTest(TestCase):
    """Tests for cache key generation."""

    def test_generate_cache_key_without_date(self):
        """Test cache key generation without a date filter."""
        key = _generate_cache_key(1, 'weight')
        self.assertEqual(key, 'personal_data:1:weight:all')

    def test_generate_cache_key_with_datetime(self):
        """Test cache key generation with a datetime."""
        dt = timezone.make_aware(timezone.datetime(2024, 12, 15, 10, 30))
        key = _generate_cache_key(1, 'weight', dt)
        self.assertEqual(key, 'personal_data:1:weight:2024-12-15')

    def test_generate_cache_key_with_date(self):
        """Test cache key generation with a date object."""
        d = date(2024, 12, 15)
        key = _generate_cache_key(1, 'journal', d)
        self.assertEqual(key, 'personal_data:1:journal:2024-12-15')

    def test_cache_keys_are_unique_per_user(self):
        """Test that different users get different cache keys."""
        key1 = _generate_cache_key(1, 'weight')
        key2 = _generate_cache_key(2, 'weight')
        self.assertNotEqual(key1, key2)

    def test_cache_keys_are_unique_per_data_type(self):
        """Test that different data types get different cache keys."""
        key1 = _generate_cache_key(1, 'weight')
        key2 = _generate_cache_key(1, 'journal')
        self.assertNotEqual(key1, key2)


@override_settings(CACHES=CACHE_SETTINGS)
class CacheHitMissTest(TestCase):
    """Tests for cache hit/miss behavior."""

    def setUp(self):
        """Create test user and clear cache."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)
        cache.clear()

    def tearDown(self):
        """Clear cache after each test."""
        cache.clear()

    def test_first_query_is_cache_miss(self):
        """Test that first query doesn't come from cache."""
        # Create test data
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )

        # Verify cache is empty before query
        cache_key = _generate_cache_key(self.user.id, 'weight')
        self.assertIsNone(cache.get(cache_key))

        # Make query
        result = self.service.get_weight_data()

        # Verify result is correct
        self.assertIsNotNone(result)
        self.assertEqual(result['count'], 1)

        # Verify cache is now populated
        cached = cache.get(cache_key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached['count'], 1)

    def test_second_query_is_cache_hit(self):
        """Test that second query returns cached data."""
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )

        # First query - populates cache
        result1 = self.service.get_weight_data()

        # Add more data to database (but cache should return old data)
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("180.0"),
            unit="lb"
        )

        # Second query - should return cached data (count=1, not 2)
        result2 = self.service.get_weight_data()

        # Both results should be identical (from cache)
        self.assertEqual(result1['count'], result2['count'])
        self.assertEqual(result2['count'], 1)  # Cached value, not 2

    def test_cache_stores_correct_data_structure(self):
        """Test that cached data has the correct structure."""
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.5"),
            unit="lb",
            notes="Morning weight"
        )

        self.service.get_weight_data()

        cache_key = _generate_cache_key(self.user.id, 'weight')
        cached = cache.get(cache_key)

        self.assertIn('type', cached)
        self.assertIn('count', cached)
        self.assertIn('average', cached)
        self.assertIn('latest', cached)
        self.assertIn('entries', cached)
        self.assertEqual(cached['type'], 'weight')

    def test_journal_data_caching(self):
        """Test that journal data is cached correctly."""
        JournalEntry.objects.create(
            user=self.user,
            title="Test Entry",
            body="Test content"
        )

        # First query
        result1 = self.service.get_journal_data()
        self.assertEqual(result1['count'], 1)

        # Add more data
        JournalEntry.objects.create(
            user=self.user,
            title="Entry 2",
            body="More content"
        )

        # Second query should return cached data
        result2 = self.service.get_journal_data()
        self.assertEqual(result2['count'], 1)  # Still 1 from cache

    def test_different_date_filters_use_different_cache_keys(self):
        """Test that queries with different date filters are cached separately."""
        # Create entries for different dates
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=10)
        )
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("180.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=2)
        )

        # Query without date filter
        result_all = self.service.get_weight_data()
        self.assertEqual(result_all['count'], 2)

        # Query with date filter (last 5 days)
        since_date = timezone.now() - timedelta(days=5)
        result_recent = self.service.get_weight_data(since_date=since_date)
        self.assertEqual(result_recent['count'], 1)

        # Both should be cached with different keys
        key_all = _generate_cache_key(self.user.id, 'weight')
        key_recent = _generate_cache_key(self.user.id, 'weight', since_date)

        self.assertIsNotNone(cache.get(key_all))
        self.assertIsNotNone(cache.get(key_recent))
        self.assertNotEqual(key_all, key_recent)


@override_settings(CACHES=CACHE_SETTINGS)
class CacheInvalidationTest(TestCase):
    """Tests for cache invalidation via invalidate_user_data_cache()."""

    def setUp(self):
        """Create test user and clear cache."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)
        cache.clear()

    def tearDown(self):
        """Clear cache after each test."""
        cache.clear()

    def test_invalidate_clears_all_key(self):
        """Test that invalidate clears the 'all' date key."""
        # Populate cache
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )
        self.service.get_weight_data()

        # Verify cache is populated
        cache_key = _generate_cache_key(self.user.id, 'weight')
        self.assertIsNotNone(cache.get(cache_key))

        # Invalidate
        invalidate_user_data_cache(self.user.id, 'weight')

        # Verify cache is cleared
        self.assertIsNone(cache.get(cache_key))

    def test_invalidate_only_affects_specified_data_type(self):
        """Test that invalidation only affects the specified data type."""
        # Create and cache weight data
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )
        self.service.get_weight_data()

        # Create and cache journal data
        JournalEntry.objects.create(
            user=self.user,
            title="Test",
            body="Content"
        )
        self.service.get_journal_data()

        # Invalidate only weight
        invalidate_user_data_cache(self.user.id, 'weight')

        # Weight cache should be cleared
        weight_key = _generate_cache_key(self.user.id, 'weight')
        self.assertIsNone(cache.get(weight_key))

        # Journal cache should still exist
        journal_key = _generate_cache_key(self.user.id, 'journal')
        self.assertIsNotNone(cache.get(journal_key))

    def test_invalidate_only_affects_specified_user(self):
        """Test that invalidation only affects the specified user."""
        other_user = User.objects.create_user(
            email="other@example.com",
            password="testpass123"
        )

        # Create and cache data for both users
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )
        self.service.get_weight_data()

        WeightEntry.objects.create(
            user=other_user,
            value=Decimal("180.0"),
            unit="lb"
        )
        other_service = PersonalDataService(other_user)
        other_service.get_weight_data()

        # Invalidate only first user
        invalidate_user_data_cache(self.user.id, 'weight')

        # First user's cache should be cleared
        self.assertIsNone(cache.get(_generate_cache_key(self.user.id, 'weight')))

        # Other user's cache should still exist
        self.assertIsNotNone(cache.get(_generate_cache_key(other_user.id, 'weight')))

    def test_invalidate_clears_today_date_key(self):
        """Test that invalidation also clears today's date key."""
        # Query with today's date filter
        today = timezone.now()
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb",
            recorded_at=today
        )
        self.service.get_weight_data(since_date=today)

        # Verify today's key is cached
        today_key = _generate_cache_key(self.user.id, 'weight', today)
        self.assertIsNotNone(cache.get(today_key))

        # Invalidate
        invalidate_user_data_cache(self.user.id, 'weight')

        # Today's key should be cleared
        self.assertIsNone(cache.get(today_key))


@override_settings(CACHES=CACHE_SETTINGS)
class SignalCacheInvalidationTest(TestCase):
    """Tests for cache invalidation via Django signals."""

    def setUp(self):
        """Create test user and clear cache."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)
        cache.clear()

    def tearDown(self):
        """Clear cache after each test."""
        cache.clear()

    def test_weight_save_signal_invalidates_cache(self):
        """Test that saving a weight entry invalidates the cache."""
        # Create initial entry and cache it
        entry = WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )
        self.service.get_weight_data()

        # Verify cache is populated
        cache_key = _generate_cache_key(self.user.id, 'weight')
        cached_before = cache.get(cache_key)
        self.assertIsNotNone(cached_before)
        self.assertEqual(cached_before['count'], 1)

        # Save another entry - signal should invalidate cache
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("176.0"),
            unit="lb"
        )

        # Cache should be invalidated
        self.assertIsNone(cache.get(cache_key))

        # Query again should return fresh data
        result = self.service.get_weight_data()
        self.assertEqual(result['count'], 2)

    def test_weight_delete_signal_invalidates_cache(self):
        """Test that deleting a weight entry invalidates the cache."""
        # Create entry and cache it
        entry = WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )
        self.service.get_weight_data()

        # Verify cache is populated
        cache_key = _generate_cache_key(self.user.id, 'weight')
        self.assertIsNotNone(cache.get(cache_key))

        # Delete entry - signal should invalidate cache
        entry.delete()

        # Cache should be invalidated
        self.assertIsNone(cache.get(cache_key))

    def test_journal_save_signal_invalidates_cache(self):
        """Test that saving a journal entry invalidates the cache."""
        # Create and cache
        JournalEntry.objects.create(
            user=self.user,
            title="Entry 1",
            body="Content"
        )
        self.service.get_journal_data()

        cache_key = _generate_cache_key(self.user.id, 'journal')
        self.assertIsNotNone(cache.get(cache_key))

        # Save another - should invalidate
        JournalEntry.objects.create(
            user=self.user,
            title="Entry 2",
            body="More content"
        )

        self.assertIsNone(cache.get(cache_key))

    def test_journal_save_with_mood_invalidates_mood_cache(self):
        """Test that saving a journal entry with mood invalidates mood cache."""
        # Create and cache mood data
        JournalEntry.objects.create(
            user=self.user,
            title="Entry",
            body="Content",
            mood="good"
        )
        self.service.get_mood_data()

        mood_key = _generate_cache_key(self.user.id, 'mood')
        self.assertIsNotNone(cache.get(mood_key))

        # Save entry with mood - should invalidate mood cache
        JournalEntry.objects.create(
            user=self.user,
            title="Entry 2",
            body="Content",
            mood="great"
        )

        self.assertIsNone(cache.get(mood_key))

    def test_journal_delete_signal_invalidates_cache(self):
        """Test that deleting a journal entry invalidates the cache."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title="Entry",
            body="Content"
        )
        self.service.get_journal_data()

        cache_key = _generate_cache_key(self.user.id, 'journal')
        self.assertIsNotNone(cache.get(cache_key))

        # Hard delete (for signal test)
        entry.delete()

        self.assertIsNone(cache.get(cache_key))

    def test_medicine_log_save_invalidates_medication_cache(self):
        """Test that saving a medicine log invalidates the medication cache."""
        medicine = Medicine.objects.create(
            user=self.user,
            name="Test Med",
            dose="100mg"
        )
        MedicineLog.objects.create(
            user=self.user,
            medicine=medicine,
            scheduled_date=date.today()
        )
        self.service.get_medication_data()

        cache_key = _generate_cache_key(self.user.id, 'medication')
        self.assertIsNotNone(cache.get(cache_key))

        # Save another log
        MedicineLog.objects.create(
            user=self.user,
            medicine=medicine,
            scheduled_date=date.today() - timedelta(days=1)
        )

        self.assertIsNone(cache.get(cache_key))

    def test_medicine_log_delete_invalidates_medication_cache(self):
        """Test that deleting a medicine log invalidates the medication cache."""
        medicine = Medicine.objects.create(
            user=self.user,
            name="Test Med",
            dose="100mg"
        )
        log = MedicineLog.objects.create(
            user=self.user,
            medicine=medicine,
            scheduled_date=date.today()
        )
        self.service.get_medication_data()

        cache_key = _generate_cache_key(self.user.id, 'medication')
        self.assertIsNotNone(cache.get(cache_key))

        log.delete()

        self.assertIsNone(cache.get(cache_key))

    def test_food_entry_save_invalidates_food_cache(self):
        """Test that saving a food entry invalidates the food cache."""
        FoodEntry.objects.create(
            user=self.user,
            food_name="Test Food",
            quantity=Decimal("1.0"),
            serving_size=Decimal("100"),
            serving_unit="g",
            total_calories=Decimal("200"),
            logged_date=date.today()
        )
        self.service.get_food_data()

        cache_key = _generate_cache_key(self.user.id, 'food')
        self.assertIsNotNone(cache.get(cache_key))

        # Save another entry
        FoodEntry.objects.create(
            user=self.user,
            food_name="Another Food",
            quantity=Decimal("1.0"),
            serving_size=Decimal("100"),
            serving_unit="g",
            total_calories=Decimal("150"),
            logged_date=date.today()
        )

        self.assertIsNone(cache.get(cache_key))

    def test_food_entry_delete_invalidates_food_cache(self):
        """Test that deleting a food entry invalidates the food cache."""
        entry = FoodEntry.objects.create(
            user=self.user,
            food_name="Test Food",
            quantity=Decimal("1.0"),
            serving_size=Decimal("100"),
            serving_unit="g",
            total_calories=Decimal("200"),
            logged_date=date.today()
        )
        self.service.get_food_data()

        cache_key = _generate_cache_key(self.user.id, 'food')
        self.assertIsNotNone(cache.get(cache_key))

        entry.delete()

        self.assertIsNone(cache.get(cache_key))


@override_settings(CACHES=CACHE_SETTINGS)
class CacheTTLTest(TestCase):
    """Tests for cache TTL (Time To Live) behavior."""

    def setUp(self):
        """Create test user and clear cache."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)
        cache.clear()

    def tearDown(self):
        """Clear cache after each test."""
        cache.clear()

    def test_cache_ttl_constant_is_correct(self):
        """Test that the cache TTL constant is set to 5 minutes."""
        self.assertEqual(PERSONAL_DATA_CACHE_TTL, 300)

    def test_cache_is_set_with_ttl(self):
        """Test that cache.set is called with the correct TTL."""
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )

        # Patch cache.set to verify TTL is passed
        with patch.object(cache, 'set', wraps=cache.set) as mock_set:
            self.service.get_weight_data()

            # Verify cache.set was called with TTL
            mock_set.assert_called()
            call_args = mock_set.call_args
            # TTL is the third positional argument
            self.assertEqual(call_args[0][2], PERSONAL_DATA_CACHE_TTL)

    def test_cache_returns_none_for_empty_data(self):
        """Test that None is returned (not cached) when no data exists."""
        result = self.service.get_weight_data()
        self.assertIsNone(result)

        # Verify nothing was cached
        cache_key = _generate_cache_key(self.user.id, 'weight')
        self.assertIsNone(cache.get(cache_key))


@override_settings(CACHES=CACHE_SETTINGS)
class QueryByIntentCacheTest(TestCase):
    """Tests for caching behavior with query_by_intent()."""

    def setUp(self):
        """Create test user and varied test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.service = PersonalDataService(self.user)
        cache.clear()

        # Create test data
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )
        JournalEntry.objects.create(
            user=self.user,
            title="Test",
            body="Content",
            mood="good"
        )

    def tearDown(self):
        """Clear cache after each test."""
        cache.clear()

    def test_query_by_intent_caches_each_type(self):
        """Test that query_by_intent caches each requested data type."""
        result = self.service.query_by_intent(data_types=['weight', 'journal'])

        # Both should be cached
        weight_key = _generate_cache_key(self.user.id, 'weight')
        journal_key = _generate_cache_key(self.user.id, 'journal')

        self.assertIsNotNone(cache.get(weight_key))
        self.assertIsNotNone(cache.get(journal_key))

    def test_partial_cache_hit(self):
        """Test query_by_intent when some data is cached and some isn't."""
        # Cache only weight
        self.service.get_weight_data()

        # Add new journal entry
        JournalEntry.objects.create(
            user=self.user,
            title="New Entry",
            body="New content"
        )

        # Query both - weight should come from cache, journal from DB
        result = self.service.query_by_intent(data_types=['weight', 'journal'])

        # Weight count should be 1 (from cache before we added more)
        self.assertEqual(result['weight']['count'], 1)

        # Journal count should reflect current DB state (2 entries)
        self.assertEqual(result['journal']['count'], 2)
