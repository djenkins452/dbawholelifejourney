"""
Phase 3 — Signal Completion tests.

Covers the signals added to build_health_state / build_fitness_state
to close the orphan-signal gap identified in the Phase 3 audit:

    sleep_trend            (from SleepEntry.total_duration_minutes)
    sleep_quality_avg_7d   (from SleepEntry.quality_score)
    body_fat_trend         (from BodyCompositionEntry metric_name='body_fat_pct')
    waist_trend            (from BodyCompositionEntry metric_name='waist')
    last_workout_days_ago  (from Workout completion date)
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.users.models import User


def _make_user(email):
    """Create a fully-onboarded test user."""
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(
        email=email, password="testpass123", date_of_birth=date(1990, 1, 1),
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ── Sleep signals ────────────────────────────────────────────────────

class SleepTrendTests(TestCase):
    """sleep_trend must classify week-over-week sleep changes."""

    def setUp(self):
        self.user = _make_user("sleep_trend@test.com")

    def _seed_sleep(self, days_ago, minutes, quality=None):
        from apps.health.models import SleepEntry
        wake = timezone.now() - timedelta(days=days_ago)
        bed = wake - timedelta(minutes=minutes)
        SleepEntry.objects.create(
            user=self.user,
            sleep_date=wake.date(),
            bedtime=bed,
            wake_time=wake,
            total_duration_minutes=minutes,
            quality_score=quality,
        )

    def test_sleep_trend_stable(self):
        # 7 nights at ~7h in both windows → stable
        for d in range(1, 8):
            self._seed_sleep(d, 420)          # last 7 days
        for d in range(8, 15):
            self._seed_sleep(d, 425)          # prior 7 days (within 15-min threshold)
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertEqual(state.get("sleep_trend"), "stable")

    def test_sleep_trend_decreasing(self):
        # Last 7 days avg ~6h, prior 7 days avg ~8h → decreasing
        for d in range(1, 8):
            self._seed_sleep(d, 360)  # 6h
        for d in range(8, 15):
            self._seed_sleep(d, 480)  # 8h
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertEqual(state.get("sleep_trend"), "decreasing")

    def test_sleep_trend_increasing(self):
        for d in range(1, 8):
            self._seed_sleep(d, 480)  # 8h
        for d in range(8, 15):
            self._seed_sleep(d, 360)  # 6h
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertEqual(state.get("sleep_trend"), "increasing")

    def test_sleep_trend_insufficient_data_when_prior_window_sparse(self):
        # 7 nights in last week, only 1 night in prior week
        for d in range(1, 8):
            self._seed_sleep(d, 420)
        self._seed_sleep(10, 420)
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertEqual(state.get("sleep_trend"), "insufficient_data")

    def test_sleep_trend_insufficient_data_when_recent_window_sparse(self):
        # Only 2 nights in the last week → below threshold
        self._seed_sleep(1, 420)
        self._seed_sleep(3, 420)
        for d in range(8, 15):
            self._seed_sleep(d, 420)
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertEqual(state.get("sleep_trend"), "insufficient_data")


class SleepQualityAvgTests(TestCase):
    """sleep_quality_avg_7d must aggregate quality_score across the week."""

    def setUp(self):
        self.user = _make_user("sleep_quality@test.com")

    def _seed(self, days_ago, minutes, quality):
        from apps.health.models import SleepEntry
        wake = timezone.now() - timedelta(days=days_ago)
        bed = wake - timedelta(minutes=minutes)
        return SleepEntry.objects.create(
            user=self.user,
            sleep_date=wake.date(),
            bedtime=bed,
            wake_time=wake,
            total_duration_minutes=minutes,
            quality_score=quality,
        )

    def test_quality_avg_computed(self):
        for d, q in zip(range(1, 4), [70, 80, 90]):
            self._seed(d, 420, q)
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertAlmostEqual(state.get("sleep_quality_avg_7d"), 80.0, places=1)

    def test_quality_avg_none_when_no_scores(self):
        self._seed(1, 420, 70)
        # SleepEntry auto-computes quality_score on save — clear it to
        # exercise the "no score" path (simulates HealthKit imports).
        from apps.health.models import SleepEntry
        SleepEntry.objects.filter(user=self.user).update(quality_score=None)
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertIsNone(state.get("sleep_quality_avg_7d"))


# ── Body composition trend signals ───────────────────────────────────

class BodyFatTrendTests(TestCase):
    def setUp(self):
        self.user = _make_user("body_fat@test.com")

    def _seed_bf(self, days_ago, value):
        from apps.health.models import BodyCompositionEntry
        BodyCompositionEntry.objects.create(
            user=self.user,
            metric_name="body_fat_pct",
            value=Decimal(str(value)),
            unit="%",
            measurement_date=timezone.now().date() - timedelta(days=days_ago),
        )

    def test_body_fat_trend_decreasing(self):
        self._seed_bf(0, 18.0)     # latest
        self._seed_bf(35, 22.0)    # 35 days ago
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertEqual(state.get("body_fat_trend"), "decreasing")

    def test_body_fat_trend_stable_within_threshold(self):
        self._seed_bf(0, 20.0)
        self._seed_bf(40, 20.3)
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertEqual(state.get("body_fat_trend"), "stable")

    def test_body_fat_trend_increasing(self):
        self._seed_bf(0, 22.0)
        self._seed_bf(35, 18.0)
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertEqual(state.get("body_fat_trend"), "increasing")

    def test_body_fat_trend_insufficient_when_no_baseline(self):
        self._seed_bf(0, 20.0)  # only one entry
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertEqual(state.get("body_fat_trend"), "insufficient_data")


class WaistTrendTests(TestCase):
    def setUp(self):
        self.user = _make_user("waist@test.com")

    def _seed_waist(self, days_ago, value):
        from apps.health.models import BodyCompositionEntry
        BodyCompositionEntry.objects.create(
            user=self.user,
            metric_name="waist",
            value=Decimal(str(value)),
            unit="in",
            measurement_date=timezone.now().date() - timedelta(days=days_ago),
        )

    def test_waist_trend_decreasing(self):
        self._seed_waist(0, 34.0)
        self._seed_waist(35, 36.0)
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertEqual(state.get("waist_trend"), "decreasing")

    def test_waist_trend_stable(self):
        self._seed_waist(0, 34.0)
        self._seed_waist(35, 34.1)
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertEqual(state.get("waist_trend"), "stable")

    def test_waist_trend_insufficient_data(self):
        self._seed_waist(0, 34.0)
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertEqual(state.get("waist_trend"), "insufficient_data")

    def test_waist_current_surfaced(self):
        self._seed_waist(0, 33.5)
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        self.assertEqual(state.get("waist_current"), 33.5)


# ── Workout recency ──────────────────────────────────────────────────

class LastWorkoutDaysAgoTests(TestCase):
    def setUp(self):
        self.user = _make_user("last_workout@test.com")

    def _seed_workout(self, days_ago):
        from apps.health.models import WorkoutSession
        today = timezone.now().date()
        return WorkoutSession.objects.create(
            user=self.user,
            date=today - timedelta(days=days_ago),
            completed_at=timezone.now() - timedelta(days=days_ago),
        )

    def test_last_workout_days_ago_today(self):
        self._seed_workout(0)
        from apps.core.ai_state.state_builder import build_fitness_state
        state = build_fitness_state(self.user)
        self.assertEqual(state.get("last_workout_days_ago"), 0)

    def test_last_workout_days_ago_three_days(self):
        self._seed_workout(3)
        from apps.core.ai_state.state_builder import build_fitness_state
        state = build_fitness_state(self.user)
        self.assertEqual(state.get("last_workout_days_ago"), 3)

    def test_last_workout_days_ago_uses_most_recent(self):
        self._seed_workout(10)
        self._seed_workout(2)
        self._seed_workout(5)
        from apps.core.ai_state.state_builder import build_fitness_state
        state = build_fitness_state(self.user)
        self.assertEqual(state.get("last_workout_days_ago"), 2)

    def test_last_workout_days_ago_absent_when_no_workouts(self):
        from apps.core.ai_state.state_builder import build_fitness_state
        state = build_fitness_state(self.user)
        self.assertNotIn("last_workout_days_ago", state)
