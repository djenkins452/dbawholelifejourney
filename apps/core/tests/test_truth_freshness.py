# ==============================================================================
# File: apps/core/tests/test_truth_freshness.py
# Description: Platform capability — Freshness (apps.core.truth.freshness). Domain-
#   agnostic verdicts consumed by every domain. Tests the generic classifiers in
#   isolation so any future consumer (Finance, Faith, Calendar) inherits the contract.
# ==============================================================================
from datetime import date, datetime, timedelta

from django.test import SimpleTestCase

from apps.core.truth import freshness as F


class PeriodFreshnessTests(SimpleTestCase):
    def setUp(self):
        self.today = date(2026, 6, 27)
        self.yest = date(2026, 6, 26)

    def test_missing_when_no_data_for_a_past_day(self):
        self.assertEqual(
            F.classify_period_freshness(has_data=False, requested_date=self.yest,
                                        data_date=None, today=self.today), F.MISSING)

    def test_pending_when_no_data_for_today(self):
        self.assertEqual(
            F.classify_period_freshness(has_data=False, requested_date=self.today,
                                        data_date=None, today=self.today), F.PENDING)

    def test_partial_for_cumulative_today_value(self):
        self.assertEqual(
            F.classify_period_freshness(has_data=True, requested_date=self.today,
                                        data_date=self.today, today=self.today,
                                        is_cumulative=True), F.PARTIAL)

    def test_current_for_complete_past_day(self):
        self.assertEqual(
            F.classify_period_freshness(has_data=True, requested_date=self.yest,
                                        data_date=self.yest, today=self.today), F.CURRENT)

    def test_stale_when_data_is_older_than_asked(self):
        self.assertEqual(
            F.classify_period_freshness(has_data=True, requested_date=self.yest,
                                        data_date=date(2026, 6, 22), today=self.today),
            F.STALE)


class SyncFreshnessTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 27, 12, 0, 0)

    def test_missing_without_sync(self):
        self.assertEqual(F.classify_sync_freshness(
            has_data=False, last_sync=None, now=self.now, stale_after_seconds=3600),
            F.MISSING)

    def test_current_within_window(self):
        self.assertEqual(F.classify_sync_freshness(
            has_data=True, last_sync=self.now - timedelta(minutes=30),
            now=self.now, stale_after_seconds=3600), F.CURRENT)

    def test_stale_past_window(self):
        self.assertEqual(F.classify_sync_freshness(
            has_data=True, last_sync=self.now - timedelta(hours=5),
            now=self.now, stale_after_seconds=3600), F.STALE)


class HonestyMarkerTests(SimpleTestCase):
    def test_stale_requires_a_marker(self):
        self.assertTrue(F.satisfies_honesty(F.STALE, "Your weight, as of June 24, was 285."))
        self.assertFalse(F.satisfies_honesty(F.STALE, "Your weight is 285."))

    def test_current_needs_no_marker(self):
        self.assertTrue(F.satisfies_honesty(F.CURRENT, "You slept 7.2 hours last night."))
