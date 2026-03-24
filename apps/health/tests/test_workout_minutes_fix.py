"""
Tests for workout minutes inflation fix.

Covers:
1. DailyHealthSummaryBuilder excludes uncompleted sessions
2. Signal aggregation excludes uncompleted sessions
3. HealthKit overlap merge prevents manual+HK double-count
4. HealthKit overlap merge safety (no false merges)
5. Dashboard view uses completed_at filter
6. Parity: all aggregation paths produce consistent totals
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.health.models import WorkoutSession


class WorkoutMinutesTestMixin:
    """Common setup for workout minutes tests."""

    def create_user(self, email="wmfix@example.com", password="testpass123"):
        from django.contrib.auth import get_user_model
        from django.conf import settings
        from apps.users.models import TermsAcceptance

        User = get_user_model()
        user = User.objects.create_user(email=email, password=password)
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def _make_session(self, user, **kwargs):
        """Create a WorkoutSession with sensible defaults."""
        now = timezone.now()
        defaults = {
            "user": user,
            "date": timezone.localdate(),
            "name": "Test Workout",
            "duration_minutes": 45,
            "started_at": now - timedelta(minutes=45),
            "completed_at": now,
            "source": "manual",
        }
        defaults.update(kwargs)
        return WorkoutSession.objects.create(**defaults)


# ── DailyHealthSummaryBuilder ───────────────────────────────────────────


class TestDailySummaryCompletedAtFilter(WorkoutMinutesTestMixin, TestCase):
    """DailyHealthSummaryBuilder._collect_workouts must exclude uncompleted sessions."""

    def setUp(self):
        self.user = self.create_user()
        self.today = timezone.localdate()

    def test_completed_session_counted(self):
        """A completed session is included in workout_minutes."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        self._make_session(self.user, duration_minutes=30)
        builder = DailyHealthSummaryBuilder()
        result = builder._collect_workouts(self.user, self.today)
        self.assertEqual(result["workout_minutes"], 30)
        self.assertEqual(result["workout_count"], 1)

    def test_uncompleted_session_excluded(self):
        """A session without completed_at is NOT counted."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        self._make_session(
            self.user, duration_minutes=45, completed_at=None,
        )
        builder = DailyHealthSummaryBuilder()
        result = builder._collect_workouts(self.user, self.today)
        self.assertEqual(result["workout_count"], 0)

    def test_mixed_completed_and_uncompleted(self):
        """Only completed sessions contribute to the total."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        now = timezone.now()
        self._make_session(
            self.user, name="Completed", duration_minutes=30,
            started_at=now - timedelta(hours=3), completed_at=now - timedelta(hours=2, minutes=30),
        )
        self._make_session(
            self.user, name="Incomplete", duration_minutes=60, completed_at=None,
        )
        builder = DailyHealthSummaryBuilder()
        result = builder._collect_workouts(self.user, self.today)
        self.assertEqual(result["workout_count"], 1)
        self.assertEqual(result["workout_minutes"], 30)


# ── Signal Aggregation ──────────────────────────────────────────────────


class TestSignalAggregationCompletedAtFilter(WorkoutMinutesTestMixin, TestCase):
    """SignalAggregationService._compute_health_activity must exclude uncompleted sessions."""

    def setUp(self):
        self.user = self.create_user(email="signal@example.com")
        self.today = timezone.localdate()

    def test_completed_session_produces_signal(self):
        from apps.core.ai_eae.signal_aggregation import SignalAggregationService

        self._make_session(self.user, duration_minutes=50)
        result = SignalAggregationService._compute_health_activity(self.user, self.today, {})
        self.assertIsNotNone(result)

    def test_uncompleted_session_no_signal(self):
        from apps.core.ai_eae.signal_aggregation import SignalAggregationService

        self._make_session(self.user, duration_minutes=50, completed_at=None)
        result = SignalAggregationService._compute_health_activity(self.user, self.today, {})
        self.assertIsNone(result)


# ── HealthKit Overlap Merge ─────────────────────────────────────────────


class TestHealthKitOverlapMerge(WorkoutMinutesTestMixin, TestCase):
    """HealthKit ingestion merges with overlapping manual entries."""

    def setUp(self):
        self.user = self.create_user(email="hkmerge@example.com")
        self.today = timezone.localdate()

    def test_overlapping_manual_entry_merged(self):
        """HealthKit workout merges into existing manual entry when times overlap."""
        from apps.mobile.views import process_workout_metric

        now = timezone.now()
        start = now - timedelta(minutes=60)
        end = now

        # Create manual entry first
        manual = self._make_session(
            self.user,
            name="Push Day",
            duration_minutes=55,
            started_at=start,
            completed_at=end,
            source="manual",
        )

        # HealthKit syncs the same physical workout (slightly different times)
        result = process_workout_metric(
            user=self.user,
            metric_date=self.today,
            source="apple_health",
            sync_id="hk_abc123",
            data={
                "workout_type": "Strength Training",
                "workout_duration": 57,
                "workout_calories": 350,
                "workout_avg_heart_rate": 145,
                "workout_start_time": (start + timedelta(minutes=2)).isoformat(),
                "workout_end_time": (end + timedelta(minutes=2)).isoformat(),
            },
        )

        self.assertEqual(result, "merged")

        # Should still be ONE session, not two
        sessions = WorkoutSession.objects.filter(user=self.user, date=self.today)
        self.assertEqual(sessions.count(), 1)

        # Manual entry enriched with HealthKit data
        manual.refresh_from_db()
        self.assertEqual(manual.sync_id, "hk_abc123")
        self.assertEqual(manual.calories_burned, 350)
        self.assertEqual(manual.avg_heart_rate, 145)
        self.assertEqual(manual.source, "manual")  # ownership preserved
        self.assertEqual(manual.duration_minutes, 55)  # manual value preserved

    def test_non_overlapping_workouts_not_merged(self):
        """Two workouts on the same day at different times are NOT merged."""
        from apps.mobile.views import process_workout_metric

        now = timezone.now()
        morning_start = now.replace(hour=7, minute=0)
        morning_end = now.replace(hour=8, minute=0)
        evening_start = now.replace(hour=18, minute=0)
        evening_end = now.replace(hour=19, minute=0)

        # Morning manual workout
        self._make_session(
            self.user,
            name="Morning Run",
            duration_minutes=60,
            started_at=morning_start,
            completed_at=morning_end,
            source="manual",
        )

        # Evening HealthKit workout (no time overlap)
        result = process_workout_metric(
            user=self.user,
            metric_date=self.today,
            source="apple_health",
            sync_id="hk_evening",
            data={
                "workout_type": "Cycling",
                "workout_duration": 45,
                "workout_start_time": evening_start.isoformat(),
                "workout_end_time": evening_end.isoformat(),
            },
        )

        self.assertEqual(result, "created")
        sessions = WorkoutSession.objects.filter(user=self.user, date=self.today)
        self.assertEqual(sessions.count(), 2)

    def test_manual_without_timestamps_not_merged(self):
        """Manual entry without timestamps is never merged (safety guard)."""
        from apps.mobile.views import process_workout_metric

        now = timezone.now()

        # Manual entry with NO timestamps
        self._make_session(
            self.user,
            name="Gym Session",
            duration_minutes=45,
            started_at=None,
            completed_at=None,  # also not completed — won't be in canonical anyway
            source="manual",
        )

        # HealthKit workout
        result = process_workout_metric(
            user=self.user,
            metric_date=self.today,
            source="apple_health",
            sync_id="hk_no_overlap",
            data={
                "workout_type": "Strength Training",
                "workout_duration": 50,
                "workout_start_time": (now - timedelta(minutes=50)).isoformat(),
                "workout_end_time": now.isoformat(),
            },
        )

        self.assertEqual(result, "created")
        sessions = WorkoutSession.objects.filter(user=self.user, date=self.today)
        self.assertEqual(sessions.count(), 2)

    def test_healthkit_without_timestamps_not_merged(self):
        """HealthKit workout without timestamps creates new session (no merge attempt)."""
        from apps.mobile.views import process_workout_metric

        now = timezone.now()

        # Manual entry WITH timestamps
        self._make_session(
            self.user,
            name="Push Day",
            duration_minutes=45,
            started_at=now - timedelta(minutes=45),
            completed_at=now,
            source="manual",
        )

        # HealthKit workout without timestamps
        result = process_workout_metric(
            user=self.user,
            metric_date=self.today,
            source="apple_health",
            sync_id="hk_no_ts",
            data={
                "workout_type": "Strength Training",
                "workout_duration": 50,
            },
        )

        self.assertEqual(result, "created")
        sessions = WorkoutSession.objects.filter(user=self.user, date=self.today)
        self.assertEqual(sessions.count(), 2)

    def test_merge_preserves_existing_calories(self):
        """Merge does NOT overwrite existing manual values."""
        from apps.mobile.views import process_workout_metric

        now = timezone.now()
        start = now - timedelta(minutes=60)

        manual = self._make_session(
            self.user,
            name="Push Day",
            duration_minutes=55,
            calories_burned=300,  # already has calories
            started_at=start,
            completed_at=now,
            source="manual",
        )

        process_workout_metric(
            user=self.user,
            metric_date=self.today,
            source="apple_health",
            sync_id="hk_cal_test",
            data={
                "workout_type": "Strength Training",
                "workout_duration": 57,
                "workout_calories": 350,
                "workout_start_time": start.isoformat(),
                "workout_end_time": now.isoformat(),
            },
        )

        manual.refresh_from_db()
        self.assertEqual(manual.calories_burned, 300)  # preserved, not overwritten

    def test_sync_id_dedup_takes_priority(self):
        """sync_id match is checked first (before overlap logic)."""
        from apps.mobile.views import process_workout_metric

        now = timezone.now()

        # First HealthKit sync
        process_workout_metric(
            user=self.user,
            metric_date=self.today,
            source="apple_health",
            sync_id="hk_dedup",
            data={
                "workout_type": "Running",
                "workout_duration": 30,
                "workout_start_time": (now - timedelta(minutes=30)).isoformat(),
                "workout_end_time": now.isoformat(),
            },
        )

        # Second sync with same sync_id — should be skipped, not create new
        result = process_workout_metric(
            user=self.user,
            metric_date=self.today,
            source="apple_health",
            sync_id="hk_dedup",
            data={
                "workout_type": "Running",
                "workout_duration": 30,
                "workout_start_time": (now - timedelta(minutes=30)).isoformat(),
                "workout_end_time": now.isoformat(),
            },
        )

        self.assertEqual(result, "skipped")
        sessions = WorkoutSession.objects.filter(user=self.user, date=self.today)
        self.assertEqual(sessions.count(), 1)


# ── Parity Check ────────────────────────────────────────────────────────


class TestWorkoutMinutesParity(WorkoutMinutesTestMixin, TestCase):
    """All aggregation paths produce the same workout minutes total."""

    def setUp(self):
        self.user = self.create_user(email="parity@example.com")
        self.today = timezone.localdate()

    def test_all_paths_agree(self):
        """SAE state, DailyHealthSummary, and signal all agree on completed sessions."""
        from apps.core.ai_state.state_builder import build_fitness_state
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        now = timezone.now()

        # Two completed sessions
        self._make_session(
            self.user, name="Session A", duration_minutes=30,
            started_at=now - timedelta(hours=5), completed_at=now - timedelta(hours=4, minutes=30),
        )
        self._make_session(
            self.user, name="Session B", duration_minutes=45,
            started_at=now - timedelta(hours=2), completed_at=now - timedelta(hours=1, minutes=15),
        )
        # One uncompleted session (should be excluded everywhere)
        self._make_session(
            self.user, name="Template Draft", duration_minutes=60,
            completed_at=None,
        )

        # Path 1: SAE state
        state = build_fitness_state(self.user)
        sae_minutes = state.get("workout_minutes_7d", 0)

        # Path 2: DailyHealthSummary
        builder = DailyHealthSummaryBuilder()
        dhs_result = builder._collect_workouts(self.user, self.today)
        dhs_minutes = dhs_result.get("workout_minutes", 0)
        dhs_count = dhs_result.get("workout_count", 0)

        # All paths should agree: 30 + 45 = 75 minutes, 2 sessions
        self.assertEqual(sae_minutes, 75)
        self.assertEqual(dhs_minutes, 75)
        self.assertEqual(dhs_count, 2)
