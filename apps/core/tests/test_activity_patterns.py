"""
User Activity Pattern Tests

Tests for UserDailyActivity and UserActivityPattern models,
including the compute logic and integration with middleware.

Location: apps/core/tests/test_activity_patterns.py
"""

from datetime import date, time, timedelta
from unittest.mock import patch

from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.models import UserDailyActivity, UserActivityPattern

User = get_user_model()


class ActivityTestMixin:
    """Common setup for activity pattern tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        user = User.objects.create_user(email=email, password=password)
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user


class UserDailyActivityTest(ActivityTestMixin, TestCase):
    """Tests for UserDailyActivity model."""

    def setUp(self):
        self.user = self.create_user()

    def test_record_activity_creates_new_record(self):
        """First interaction of the day creates a new record."""
        now = timezone.now().replace(hour=9, minute=30)
        UserDailyActivity.record_activity(self.user, now)

        activity = UserDailyActivity.objects.get(user=self.user, date=now.date())
        self.assertEqual(activity.first_seen, now.time())
        self.assertEqual(activity.last_seen, now.time())
        self.assertEqual(activity.interaction_count, 1)

    def test_record_activity_updates_last_seen(self):
        """Later interactions update last_seen but not first_seen."""
        morning = timezone.now().replace(hour=7, minute=0, second=0, microsecond=0)
        afternoon = timezone.now().replace(hour=14, minute=30, second=0, microsecond=0)

        UserDailyActivity.record_activity(self.user, morning)
        UserDailyActivity.record_activity(self.user, afternoon)

        activity = UserDailyActivity.objects.get(user=self.user, date=morning.date())
        self.assertEqual(activity.first_seen, morning.time())
        self.assertEqual(activity.last_seen, afternoon.time())
        self.assertEqual(activity.interaction_count, 2)

    def test_record_activity_updates_first_seen_if_earlier(self):
        """If an earlier time comes in (edge case), first_seen updates."""
        later = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        earlier = timezone.now().replace(hour=6, minute=0, second=0, microsecond=0)

        UserDailyActivity.record_activity(self.user, later)
        UserDailyActivity.record_activity(self.user, earlier)

        activity = UserDailyActivity.objects.get(user=self.user, date=later.date())
        self.assertEqual(activity.first_seen, earlier.time())
        self.assertEqual(activity.interaction_count, 2)

    def test_different_days_create_separate_records(self):
        """Each calendar day gets its own record."""
        today = timezone.now().replace(hour=9)
        yesterday = today - timedelta(days=1)

        UserDailyActivity.record_activity(self.user, today)
        UserDailyActivity.record_activity(self.user, yesterday)

        self.assertEqual(
            UserDailyActivity.objects.filter(user=self.user).count(), 2
        )

    def test_cleanup_old_records(self):
        """Records older than retention period are removed."""
        now = timezone.now()

        # Create old and recent records
        UserDailyActivity.objects.create(
            user=self.user,
            date=now.date() - timedelta(days=100),
            first_seen=time(8, 0),
            last_seen=time(22, 0),
        )
        UserDailyActivity.objects.create(
            user=self.user,
            date=now.date(),
            first_seen=time(8, 0),
            last_seen=time(22, 0),
        )

        deleted = UserDailyActivity.cleanup_old_records(days_to_keep=90)
        self.assertEqual(deleted, 1)
        self.assertEqual(
            UserDailyActivity.objects.filter(user=self.user).count(), 1
        )

    def test_str_representation(self):
        """String representation is readable."""
        now = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
        UserDailyActivity.record_activity(self.user, now)
        activity = UserDailyActivity.objects.get(user=self.user)
        self.assertIn(self.user.email, str(activity))


class UserActivityPatternTest(ActivityTestMixin, TestCase):
    """Tests for UserActivityPattern model and computation."""

    def setUp(self):
        self.user = self.create_user()

    def _create_activity_days(self, start_hours, end_hours, start_date=None):
        """Helper to create multiple days of activity data."""
        if start_date is None:
            start_date = timezone.now().date()

        for i, (start_h, end_h) in enumerate(zip(start_hours, end_hours)):
            activity_date = start_date - timedelta(days=i)
            start_m = int((start_h % 1) * 60)
            end_m = int((end_h % 1) * 60)
            UserDailyActivity.objects.create(
                user=self.user,
                date=activity_date,
                first_seen=time(int(start_h), start_m),
                last_seen=time(int(end_h), end_m),
            )

    def test_compute_with_no_data_returns_none(self):
        """No activity data returns None."""
        result = UserActivityPattern.compute_for_user(self.user)
        self.assertIsNone(result)

    def test_compute_basic_pattern(self):
        """Computes correct average start/end from activity data."""
        # User starts at 7am every day, ends at 10pm
        self._create_activity_days(
            start_hours=[7.0] * 10,
            end_hours=[22.0] * 10,
        )

        pattern = UserActivityPattern.compute_for_user(self.user)
        self.assertIsNotNone(pattern)
        self.assertAlmostEqual(pattern.typical_start_hour, 7.0, places=1)
        self.assertAlmostEqual(pattern.typical_end_hour, 22.0, places=1)
        self.assertEqual(pattern.sample_days, 10)

    def test_compute_varied_pattern(self):
        """Handles varying start times correctly."""
        # Mix of start times: 6, 7, 8, 6, 7, 8, 6, 7, 8, 6 → avg ~6.9
        starts = [6.0, 7.0, 8.0, 6.0, 7.0, 8.0, 6.0, 7.0, 8.0, 6.0]
        ends = [22.0] * 10
        self._create_activity_days(start_hours=starts, end_hours=ends)

        pattern = UserActivityPattern.compute_for_user(self.user)
        self.assertAlmostEqual(pattern.typical_start_hour, 6.9, places=1)
        # Earliest 10th percentile should be 6.0
        self.assertAlmostEqual(pattern.earliest_start_hour, 6.0, places=1)

    def test_is_reliable_with_few_days(self):
        """Pattern is not reliable with fewer than MIN_SAMPLE_DAYS."""
        self._create_activity_days(
            start_hours=[7.0] * 3,
            end_hours=[22.0] * 3,
        )
        pattern = UserActivityPattern.compute_for_user(self.user)
        self.assertFalse(pattern.is_reliable)

    def test_is_reliable_with_enough_days(self):
        """Pattern is reliable with MIN_SAMPLE_DAYS or more."""
        self._create_activity_days(
            start_hours=[7.0] * 10,
            end_hours=[22.0] * 10,
        )
        pattern = UserActivityPattern.compute_for_user(self.user)
        self.assertTrue(pattern.is_reliable)

    def test_get_early_morning_threshold_unreliable(self):
        """Falls back to 8.0 when pattern is not reliable."""
        self._create_activity_days(
            start_hours=[6.0] * 3,
            end_hours=[22.0] * 3,
        )
        pattern = UserActivityPattern.compute_for_user(self.user)
        self.assertEqual(pattern.get_early_morning_threshold(), 8.0)

    def test_get_early_morning_threshold_reliable(self):
        """Uses personalized threshold when pattern is reliable."""
        # User consistently starts at 6am
        self._create_activity_days(
            start_hours=[6.0] * 10,
            end_hours=[22.0] * 10,
        )
        pattern = UserActivityPattern.compute_for_user(self.user)
        threshold = pattern.get_early_morning_threshold()
        self.assertEqual(threshold, 6.0)

    def test_compute_updates_existing_pattern(self):
        """Re-computing updates the existing pattern, not creating a new one."""
        self._create_activity_days(
            start_hours=[7.0] * 10,
            end_hours=[22.0] * 10,
        )
        UserActivityPattern.compute_for_user(self.user)
        self.assertEqual(UserActivityPattern.objects.filter(user=self.user).count(), 1)

        # Add more data and recompute
        UserDailyActivity.objects.create(
            user=self.user,
            date=timezone.now().date() - timedelta(days=15),
            first_seen=time(5, 0),
            last_seen=time(23, 0),
        )
        UserActivityPattern.compute_for_user(self.user)
        self.assertEqual(UserActivityPattern.objects.filter(user=self.user).count(), 1)

    def test_format_hour(self):
        """Hour formatting produces readable strings."""
        self.assertEqual(UserActivityPattern._format_hour(6.0), '6am')
        self.assertEqual(UserActivityPattern._format_hour(6.5), '6:30am')
        self.assertEqual(UserActivityPattern._format_hour(12.0), '12pm')
        self.assertEqual(UserActivityPattern._format_hour(13.25), '1:15pm')
        self.assertEqual(UserActivityPattern._format_hour(0.0), '12am')

    def test_str_representation(self):
        """String representation is readable."""
        self._create_activity_days(
            start_hours=[7.0] * 10,
            end_hours=[22.0] * 10,
        )
        pattern = UserActivityPattern.compute_for_user(self.user)
        s = str(pattern)
        self.assertIn(self.user.email, s)
        self.assertIn('10 days', s)

    def test_lookback_respects_window(self):
        """Only data within the lookback window is used."""
        # Old data (60 days ago)
        UserDailyActivity.objects.create(
            user=self.user,
            date=timezone.now().date() - timedelta(days=60),
            first_seen=time(5, 0),
            last_seen=time(23, 0),
        )
        # Recent data
        self._create_activity_days(
            start_hours=[8.0] * 10,
            end_hours=[21.0] * 10,
        )

        pattern = UserActivityPattern.compute_for_user(self.user, lookback_days=30)
        # Should only count the 10 recent days, not the old one
        self.assertEqual(pattern.sample_days, 10)
        self.assertAlmostEqual(pattern.typical_start_hour, 8.0, places=1)
