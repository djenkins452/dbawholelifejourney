# ==============================================================================
# File: apps/core/tests/test_truth_history.py
# Description: Platform capability — Point-in-Time History (apps.core.truth.history,
#   .periods). Period resolution + the HistorySeries object + aggregates, plus Health
#   and Workout (a second domain) consuming the SAME capability. No OpenAI.
# ==============================================================================
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.truth.history import HistorySeries, series_from_rows
from apps.core.truth.periods import resolve_period, Period
from apps.core.utils import get_user_today
from apps.health.models import StepsEntry, WorkoutSession
from apps.health.services.health_history import HealthHistory
from apps.health.services.workout_history import WorkoutHistory

User = get_user_model()


class PeriodResolutionTests(SimpleTestCase):
    def setUp(self):
        self.today = date(2026, 6, 17)          # a Wednesday

    def test_yesterday(self):
        p = resolve_period("yesterday", self.today)
        self.assertEqual((p.start, p.end), (date(2026, 6, 16), date(2026, 6, 16)))

    def test_last_7_days_is_inclusive_window(self):
        p = resolve_period("last_7_days", self.today)
        self.assertEqual((p.start, p.end), (date(2026, 6, 11), date(2026, 6, 17)))
        self.assertEqual(p.days(), 7)

    def test_this_week_starts_monday(self):
        p = resolve_period("this_week", self.today)
        self.assertEqual(p.start, date(2026, 6, 15))   # Monday
        self.assertEqual(p.end, self.today)

    def test_last_month(self):
        p = resolve_period("last_month", self.today)
        self.assertEqual((p.start, p.end), (date(2026, 5, 1), date(2026, 5, 31)))

    def test_last_quarter(self):
        p = resolve_period("last_quarter", self.today)   # Q2 today → Q1
        self.assertEqual((p.start, p.end), (date(2026, 1, 1), date(2026, 3, 31)))

    def test_this_year(self):
        p = resolve_period("this_year", self.today)
        self.assertEqual(p.start, date(2026, 1, 1))

    def test_custom_range(self):
        p = resolve_period("custom", self.today,
                           start=date(2026, 2, 1), end=date(2026, 2, 14))
        self.assertEqual(p.days(), 14)

    def test_unknown_period_raises(self):
        with self.assertRaises(ValueError):
            resolve_period("fortnight", self.today)


class HistorySeriesTests(SimpleTestCase):
    def _series(self, vals):
        p = Period("x", date(2026, 6, 1), date(2026, 6, 3), "x")
        rows = [{"date": date(2026, 6, 1 + i), "value": v} for i, v in enumerate(vals)]
        return series_from_rows("d", "m", p, rows)

    def test_aggregates(self):
        s = self._series([10, 30, 20])
        self.assertEqual(s.total(), 60)
        self.assertEqual(s.average(), 20)
        self.assertEqual(s.maximum(), 30)
        self.assertEqual(s.minimum(), 10)
        self.assertEqual(s.count(), 3)
        self.assertEqual(s.latest().value, 20)      # sorted by date
        self.assertEqual(s.earliest().value, 10)

    def test_empty_is_safe(self):
        s = self._series([])
        self.assertFalse(s.present())
        self.assertEqual(s.total(), 0)
        self.assertIsNone(s.average())
        self.assertIsNone(s.maximum())


class HealthHistoryConsumerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="hh@test.com", password="x")
        self.today = get_user_today(self.user)

    def test_steps_history_over_last_7_days(self):
        for i, c in enumerate([5000, 6000, 7000]):
            StepsEntry.objects.create(user=self.user, count=c,
                                      logged_date=self.today - timedelta(days=i))
        s = HealthHistory.steps(self.user, "last_7_days", today=self.today)
        self.assertEqual(s.count(), 3)
        self.assertEqual(s.total(), 18000)
        self.assertEqual(s.maximum(), 7000)
        self.assertEqual(s.domain, "health")

    def test_specific_date_range_excludes_outside(self):
        StepsEntry.objects.create(user=self.user, count=9999,
                                  logged_date=self.today - timedelta(days=30))
        s = HealthHistory.steps(self.user, "last_7_days", today=self.today)
        self.assertFalse(s.present())     # the 30-day-old entry is outside the window


class WorkoutHistoryConsumerTests(TestCase):
    """Second domain consuming the SAME History capability via the existing
    WorkoutQueries.completed_in_range contract."""

    def setUp(self):
        self.user = User.objects.create_user(email="wh@test.com", password="x")
        self.today = get_user_today(self.user)

    def test_workout_sessions_over_a_week(self):
        for i in (1, 3, 5):
            WorkoutSession.objects.create(user=self.user, duration_minutes=30,
                                          date=self.today - timedelta(days=i))
        s = WorkoutHistory.sessions(self.user, "last_7_days", today=self.today)
        self.assertEqual(s.total(), 3)     # 3 sessions
        self.assertEqual(s.count(), 3)     # on 3 distinct days
        self.assertEqual(s.domain, "fitness")
