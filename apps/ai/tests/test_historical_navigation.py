# ==============================================================================
# File: apps/ai/tests/test_historical_navigation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: HISTORICAL TRUTH NAVIGATION. Beth knows today's and yesterday's weight but
#   failed to navigate deterministic history: "Day before yesterday?" declined and
#   "July 1st?" errored — even though the canonical resolver + weight_queries already
#   support them. They were unreachable from the elliptical (referential) follow-up path.
#   These tests prove the canonical navigation (point-in-time, threshold, extremum,
#   aggregate) and the referential bridge that makes it reachable without restating
#   "weight".
# ==============================================================================
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.utils import get_user_today
from apps.health.models import WeightEntry
from apps.health.services import weight_queries
from apps.ai.chatgpt_cos import weight_history
from apps.ai.chatgpt_cos.referential import resolve_referential
from apps.ai.chatgpt_cos.date_reference import resolve_reference_date

User = get_user_model()


def _we(user, d, lb, hour=12):
    WeightEntry.objects.create(
        user=user, value=Decimal(str(lb)), unit="lb",
        recorded_at=timezone.make_aware(datetime.combine(d, time(hour, 0))))


class WeightQueriesTests(TestCase):
    """The canonical Layer 1 accessors — deterministic over an explicit series."""

    def setUp(self):
        self.u = User.objects.create_user(email="wq@t.com", password="x")
        _we(self.u, date(2026, 6, 10), 291)
        _we(self.u, date(2026, 6, 15), 292)
        _we(self.u, date(2026, 6, 20), 288)   # first day below 290
        _we(self.u, date(2026, 7, 2), 279)    # lowest overall
        _we(self.u, date(2026, 7, 4), 284.4)

    def test_series_is_one_per_day_oldest_first(self):
        self.assertEqual([r["date"] for r in weight_queries.series(self.u)],
                         [date(2026, 6, 10), date(2026, 6, 15), date(2026, 6, 20),
                          date(2026, 7, 2), date(2026, 7, 4)])

    def test_series_latest_reading_wins_per_day(self):
        _we(self.u, date(2026, 7, 4), 283.0, hour=20)   # later same day
        s = {r["date"]: r["value_lb"] for r in weight_queries.series(self.u)}
        self.assertEqual(s[date(2026, 7, 4)], 283.0)

    def test_first_crossing_below(self):
        r = weight_queries.first_crossing(self.u, 290, "below")
        self.assertEqual(r["date"], date(2026, 6, 20))
        self.assertEqual(r["value_lb"], 288.0)

    def test_extremum_lowest_and_windowed(self):
        self.assertEqual(weight_queries.extremum(self.u, "lowest")["value_lb"], 279.0)
        june = weight_queries.extremum(self.u, "lowest", date(2026, 6, 1), date(2026, 6, 30))
        self.assertEqual(june["value_lb"], 288.0)       # June-only minimum

    def test_average_over_window(self):
        a = weight_queries.average_over(self.u, date(2026, 6, 1), date(2026, 6, 30))
        self.assertEqual(a["n"], 3)
        self.assertEqual(a["avg_lb"], round((291 + 292 + 288) / 3, 1))


class NavigateTests(TestCase):
    """The weight navigator resolves every natural historical form deterministically."""

    def setUp(self):
        self.u = User.objects.create_user(email="nav@t.com", password="x")
        self.today = get_user_today(self.u)
        _we(self.u, self.today - timedelta(days=1), 284.4)   # yesterday
        _we(self.u, self.today - timedelta(days=2), 286.0)   # day before yesterday
        _we(self.u, self.today - timedelta(days=40), 295.0)
        _we(self.u, self.today - timedelta(days=30), 289.0)  # first below 290
        _we(self.u, self.today - timedelta(days=10), 279.0)  # lowest

    def test_point_in_time_yesterday_keeps_precision(self):
        self.assertIn("284.4", weight_history.navigate(self.u, "yesterday"))

    def test_point_in_time_day_before_yesterday(self):
        self.assertIn("286", weight_history.navigate(self.u, "day before yesterday"))

    def test_threshold_first_below(self):
        ans = weight_history.navigate(self.u, "when did I first drop below 290?")
        self.assertIn("289", ans)
        self.assertIn("dropped below 290", ans.lower())

    def test_extremum_lowest(self):
        ans = weight_history.navigate(self.u, "when did I reach my lowest weight?")
        self.assertIn("279", ans)
        self.assertIn("lowest", ans.lower())

    def test_average_window(self):
        ans = weight_history.navigate(self.u, "average weight over the last 30 days")
        self.assertIn("average", ans.lower())
        self.assertIn("lb", ans)

    def test_missing_day_is_honest_not_an_error(self):
        ans = weight_history.navigate(self.u, "5 days ago")
        self.assertIn("don't have a weight reading", ans.lower())

    def test_unrelated_message_returns_none(self):
        self.assertIsNone(weight_history.navigate(self.u, "how's my day going?"))


class ReferentialBridgeTests(TestCase):
    """Elliptical follow-ups (no 'weight' word) reach the SAME navigator via the active
    topic — the production failure path."""

    def setUp(self):
        self.u = User.objects.create_user(email="rb@t.com", password="x")
        self.today = get_user_today(self.u)
        _we(self.u, self.today - timedelta(days=2), 286.0)
        self.last = {"topic": "weight", "fact_key": "weight_yesterday",
                     "fact": {"value": 284.4, "unit": "lb"}}

    def test_day_before_yesterday_resolves_via_bridge(self):
        r = resolve_referential(self.u, "day before yesterday?", self.last)
        self.assertIsNotNone(r)
        self.assertIn("286", r["answer"])

    def test_explicit_calendar_date_resolves_via_bridge(self):
        jul1 = resolve_reference_date(self.u, "July 1", include_today=False)
        _we(self.u, jul1, 288.0)
        r = resolve_referential(self.u, "July 1st?", self.last)
        self.assertIsNotNone(r)
        self.assertIn("288", r["answer"])

    def test_threshold_question_resolves_via_bridge(self):
        _we(self.u, self.today - timedelta(days=20), 295.0)
        _we(self.u, self.today - timedelta(days=15), 289.0)
        r = resolve_referential(self.u, "when did I first drop below 290?", self.last)
        self.assertIsNotNone(r)
        self.assertIn("289", r["answer"])

    def test_non_navigable_topic_is_not_hijacked(self):
        last = {"topic": "steps", "fact_key": "steps_today", "fact": {}}
        self.assertIsNone(resolve_referential(self.u, "July 1st?", last))
