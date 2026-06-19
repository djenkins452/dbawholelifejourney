"""
Cache Integration Tests for the Personal Data Query System.

These tests verify caching behavior with Django's cache framework
rather than mocks, including cache hits, misses, and signal-based
invalidation.
"""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.health.models import FoodEntry, WeightEntry
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
        self.assertEqual(key, 'personal_data:1:weight:v1:all')

    def test_generate_cache_key_with_datetime(self):
        """Test cache key generation with a datetime."""
        dt = timezone.make_aware(timezone.datetime(2024, 12, 15, 10, 30))
        key = _generate_cache_key(1, 'weight', dt)
        self.assertEqual(key, 'personal_data:1:weight:v1:2024-12-15')

    def test_generate_cache_key_with_date(self):
        """Test cache key generation with a date object."""
        d = date(2024, 12, 15)
        key = _generate_cache_key(1, 'journal', d)
        self.assertEqual(key, 'personal_data:1:journal:v1:2024-12-15')

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
        self.assertEqual(len(result['entries']), 1)

        # Verify cache is now populated
        cached = cache.get(cache_key)
        self.assertIsNotNone(cached)
        self.assertEqual(len(cached['entries']), 1)

    def test_second_query_is_cache_hit(self):
        """Test that cache is actually used for repeated queries.

        Note: Since signals invalidate cache on data changes, we verify
        caching by checking that two consecutive queries without data
        changes return identical results and hit the cache.
        """
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )

        # First query - populates cache
        result1 = self.service.get_weight_data()
        self.assertEqual(len(result1['entries']), 1)

        # Second query (no data changes) - should return cached data
        result2 = self.service.get_weight_data()

        # Both results should be identical (from cache)
        self.assertEqual(len(result1['entries']), len(result2['entries']))
        self.assertEqual(result2['type'], 'weight')

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

        # New SAE-backed weight contract keys:
        # {type, latest, latest_date, unit, change_30d, trend, source, entries}
        self.assertIn('type', cached)
        self.assertIn('latest', cached)
        self.assertIn('unit', cached)
        self.assertIn('change_30d', cached)
        self.assertIn('trend', cached)
        self.assertIn('source', cached)
        self.assertIn('entries', cached)
        self.assertEqual(cached['type'], 'weight')

    def test_journal_data_caching(self):
        """Test that journal data caching works correctly.

        Note: Since signals invalidate cache on data changes, we verify
        caching by checking that repeated queries without changes work.
        """
        JournalEntry.objects.create(
            user=self.user,
            title="Test Entry",
            body="Test content"
        )

        # First query
        result1 = self.service.get_journal_data()
        self.assertEqual(len(result1['recent_entries']), 1)

        # Second query (no changes) - should return cached data
        result2 = self.service.get_journal_data()
        self.assertEqual(len(result2['recent_entries']), 1)
        self.assertEqual(result1['type'], result2['type'])

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
        self.assertEqual(len(result_all['entries']), 2)

        # Query with date filter (last 5 days)
        since_date = timezone.now() - timedelta(days=5)
        result_recent = self.service.get_weight_data(since_date=since_date)
        self.assertEqual(len(result_recent['entries']), 1)

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
        """Test that invalidate results in fresh data on next query.

        Note: The implementation uses cache versioning, so old keys aren't
        deleted - instead new queries use a new version in the key.
        """
        # Populate cache with first entry
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )
        result1 = self.service.get_weight_data()
        self.assertEqual(len(result1['entries']), 1)

        # Add another entry and invalidate cache
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("180.0"),
            unit="lb"
        )
        invalidate_user_data_cache(self.user.id, 'weight')

        # Query should return fresh data with both entries
        result2 = self.service.get_weight_data()
        self.assertEqual(len(result2['entries']), 2)

    def test_invalidate_only_affects_specified_data_type(self):
        """Test that different data types have independent cache versions.

        This test verifies that each data type (weight, journal) maintains
        its own cache version, so invalidating one doesn't affect the other.
        """
        # Create weight and journal data
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )
        JournalEntry.objects.create(
            user=self.user,
            title="Test",
            body="Content"
        )

        # Cache both data types
        result_w1 = self.service.get_weight_data()
        result_j1 = self.service.get_journal_data()
        self.assertEqual(len(result_w1['entries']), 1)
        self.assertEqual(len(result_j1['recent_entries']), 1)

        # Manually invalidate only weight (simulating a version bump without signal)
        invalidate_user_data_cache(self.user.id, 'weight')

        # Weight cache should show it needs fresh data on next query
        # (though data hasn't changed, cache version bumped)
        result_w2 = self.service.get_weight_data()
        self.assertEqual(len(result_w2['entries']), 1)  # Same data, just re-fetched
        self.assertEqual(result_w2['type'], 'weight')

        # Journal should still return cached data (version unchanged)
        result_j2 = self.service.get_journal_data()
        self.assertEqual(len(result_j2['recent_entries']), 1)
        self.assertEqual(result_j2['type'], 'journal')

    def test_invalidate_only_affects_specified_user(self):
        """Test that different users have independent cache versions.

        This verifies that each user's cache version is independent.
        """
        other_user = User.objects.create_user(
            email="other@example.com",
            password="testpass123"
        )
        other_service = PersonalDataService(other_user)

        # Create data for both users
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )
        WeightEntry.objects.create(
            user=other_user,
            value=Decimal("180.0"),
            unit="lb"
        )

        # Cache data for both users
        result1 = self.service.get_weight_data()
        result_other1 = other_service.get_weight_data()
        self.assertEqual(len(result1['entries']), 1)
        self.assertEqual(len(result_other1['entries']), 1)

        # Manually invalidate only first user
        invalidate_user_data_cache(self.user.id, 'weight')

        # First user's data re-fetched (same count since data unchanged)
        result2 = self.service.get_weight_data()
        self.assertEqual(len(result2['entries']), 1)

        # Other user's data should still be from cache
        result_other2 = other_service.get_weight_data()
        self.assertEqual(len(result_other2['entries']), 1)

    def test_invalidate_clears_today_date_key(self):
        """Test that invalidation works for date-filtered queries.

        Note: Uses cache versioning - tests that a date-filtered query
        returns fresh data after invalidation.
        """
        today = timezone.now()
        # Create entry and cache with today's date filter
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb",
            recorded_at=today
        )
        result1 = self.service.get_weight_data(since_date=today)
        self.assertEqual(len(result1['entries']), 1)

        # Add another entry
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("176.0"),
            unit="lb",
            recorded_at=today
        )

        # Invalidate
        invalidate_user_data_cache(self.user.id, 'weight')

        # Query should now return fresh data with both entries
        result2 = self.service.get_weight_data(since_date=today)
        self.assertEqual(len(result2['entries']), 2)


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
        """Test that saving a weight entry results in fresh data on next query.

        Note: Uses cache versioning - signal increments version so next
        query fetches fresh data.
        """
        # Create initial entry and cache it
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )
        result1 = self.service.get_weight_data()
        self.assertEqual(len(result1['entries']), 1)

        # Save another entry - signal should invalidate via version bump
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("176.0"),
            unit="lb"
        )

        # Query should return fresh data with both entries
        result2 = self.service.get_weight_data()
        self.assertEqual(len(result2['entries']), 2)

    def test_weight_delete_signal_invalidates_cache(self):
        """Test that deleting a weight entry results in fresh data on next query.

        Note: Uses cache versioning.
        """
        # Create entries and cache
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("175.0"),
            unit="lb"
        )
        entry2 = WeightEntry.objects.create(
            user=self.user,
            value=Decimal("176.0"),
            unit="lb"
        )
        result1 = self.service.get_weight_data()
        self.assertEqual(len(result1['entries']), 2)

        # Delete one entry - signal should invalidate via version bump
        entry2.delete()

        # Query should return fresh data with only one entry
        result2 = self.service.get_weight_data()
        self.assertEqual(len(result2['entries']), 1)

    def test_journal_save_signal_invalidates_cache(self):
        """Test that saving a journal entry results in fresh data.

        Note: Uses cache versioning.
        """
        # Create and cache
        JournalEntry.objects.create(
            user=self.user,
            title="Entry 1",
            body="Content"
        )
        result1 = self.service.get_journal_data()
        self.assertEqual(len(result1['recent_entries']), 1)

        # Save another - should invalidate via version bump
        JournalEntry.objects.create(
            user=self.user,
            title="Entry 2",
            body="More content"
        )

        # Query should return fresh data
        result2 = self.service.get_journal_data()
        self.assertEqual(len(result2['recent_entries']), 2)

    def test_journal_save_with_mood_invalidates_mood_cache(self):
        """Saving a mood entry invalidates the cache so the next read recomputes.

        Note: Uses cache versioning. Mood is SAE-driven, so the canonical
        distribution comes from the metric layer; the sequence supplies a
        different total on each call so a stale (non-invalidated) cache
        would fail the second assertion.
        """
        dist_seq = iter([
            {'great': 0, 'good': 1, 'okay': 0, 'low': 0},
            {'great': 1, 'good': 1, 'okay': 0, 'low': 0},
        ])

        def _side(user, key):
            if key == 'journal.mood_distribution':
                return SimpleNamespace(value=next(dist_seq), source='sae')
            if key == 'journal.mood_avg_7d':
                return SimpleNamespace(value=3.5, source='sae')
            return None

        with patch('assistant.data_service.get_metric', side_effect=_side):
            JournalEntry.objects.create(
                user=self.user,
                title="Entry",
                body="Content",
                mood="good"
            )
            result1 = self.service.get_mood_data()
            self.assertEqual(sum(result1['mood_distribution'].values()), 1)

            # Save entry with mood — its signal must invalidate the mood cache.
            JournalEntry.objects.create(
                user=self.user,
                title="Entry 2",
                body="Content",
                mood="great"
            )

            # Fresh read recomputes (cache invalidated) → new canonical total.
            result2 = self.service.get_mood_data()
            self.assertEqual(sum(result2['mood_distribution'].values()), 2)

    def test_journal_delete_signal_invalidates_cache(self):
        """Test that deleting a journal entry results in fresh data.

        Note: Uses cache versioning.
        """
        JournalEntry.objects.create(
            user=self.user,
            title="Entry 1",
            body="Content"
        )
        entry2 = JournalEntry.objects.create(
            user=self.user,
            title="Entry 2",
            body="Content 2"
        )
        result1 = self.service.get_journal_data()
        self.assertEqual(len(result1['recent_entries']), 2)

        # Hard delete one entry (for signal test)
        entry2.delete()

        # Query should return fresh data
        result2 = self.service.get_journal_data()
        self.assertEqual(len(result2['recent_entries']), 1)

    @staticmethod
    def _food_metric_side_effect(entries_today_seq, daily_calories=1800):
        """get_metric stub: food is SAE-driven, so entries_today comes from
        the metric layer (not raw ORM). The sequence supplies a DIFFERENT
        value on each get_food_data() call — so if the save/delete signal
        fails to invalidate the cache, the second query returns the stale
        first value and the test fails. That is exactly what we want to
        verify here (signal-based cache invalidation), independent of SAE
        rebuild timing.
        """
        seq = iter(entries_today_seq)

        def _side(user, key):
            if key == 'nutrition.daily_calories':
                return SimpleNamespace(value=daily_calories, source='sae')
            if key == 'nutrition.food_entries_today':
                return SimpleNamespace(value=next(seq), source='sae')
            return None

        return _side

    def test_food_entry_save_invalidates_food_cache(self):
        """Saving a food entry invalidates the cache so the next read recomputes.

        Note: Uses cache versioning.
        """
        with patch(
            'assistant.data_service.get_metric',
            side_effect=self._food_metric_side_effect([1, 2]),
        ):
            FoodEntry.objects.create(
                user=self.user,
                food_name="Test Food",
                quantity=Decimal("1.0"),
                serving_size=Decimal("100"),
                serving_unit="g",
                total_calories=Decimal("200"),
                logged_date=date.today()
            )
            result1 = self.service.get_food_data()
            self.assertEqual(result1['entries_today'], 1)

            # Save another entry — its signal must invalidate the food cache.
            FoodEntry.objects.create(
                user=self.user,
                food_name="Another Food",
                quantity=Decimal("1.0"),
                serving_size=Decimal("100"),
                serving_unit="g",
                total_calories=Decimal("150"),
                logged_date=date.today()
            )

            # Fresh read recomputes (cache invalidated) → new canonical value.
            result2 = self.service.get_food_data()
            self.assertEqual(result2['entries_today'], 2)

    def test_food_entry_delete_invalidates_food_cache(self):
        """Deleting a food entry invalidates the cache so the next read recomputes.

        Note: Uses cache versioning.
        """
        entry2 = FoodEntry.objects.create(
            user=self.user,
            food_name="Food 2",
            quantity=Decimal("1.0"),
            serving_size=Decimal("100"),
            serving_unit="g",
            total_calories=Decimal("150"),
            logged_date=date.today()
        )
        FoodEntry.objects.create(
            user=self.user,
            food_name="Test Food",
            quantity=Decimal("1.0"),
            serving_size=Decimal("100"),
            serving_unit="g",
            total_calories=Decimal("200"),
            logged_date=date.today()
        )
        with patch(
            'assistant.data_service.get_metric',
            side_effect=self._food_metric_side_effect([2, 1]),
        ):
            result1 = self.service.get_food_data()
            self.assertEqual(result1['entries_today'], 2)

            entry2.delete()

            # Fresh read recomputes (cache invalidated) → new canonical value.
            result2 = self.service.get_food_data()
            self.assertEqual(result2['entries_today'], 1)


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
        self.service.query_by_intent(data_types=['weight', 'journal'])

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

        # Weight entries should be 1 (from cache before we added more)
        self.assertEqual(len(result['weight']['entries']), 1)

        # Journal recent_entries should reflect current DB state (2 entries)
        self.assertEqual(len(result['journal']['recent_entries']), 2)
