# ==============================================================================
# File: apps/core/tests/test_truth_confidence.py
# Description: Platform capability — Confidence (Architecture Law 2). Domain-agnostic
#   high/medium/low/none verdicts derived from freshness, coverage, and source; and
#   their composition into Current Truth + History objects. No OpenAI.
# ==============================================================================
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.core.truth import confidence as C
from apps.core.truth import freshness as F
from apps.core.truth.current import CurrentTruth
from apps.core.truth.history import series_from_rows
from apps.core.truth.periods import resolve_period
from apps.core.utils import get_user_today
from apps.health.models import StepsEntry

User = get_user_model()


class ConfidenceClassifierTests(SimpleTestCase):
    def test_from_freshness(self):
        self.assertEqual(C.confidence_from_freshness(F.CURRENT), C.HIGH)
        self.assertEqual(C.confidence_from_freshness(F.PARTIAL), C.MEDIUM)
        self.assertEqual(C.confidence_from_freshness(F.STALE), C.LOW)
        self.assertEqual(C.confidence_from_freshness(F.MISSING), C.NONE)

    def test_from_coverage(self):
        self.assertEqual(C.confidence_from_coverage(7, 7), C.HIGH)
        self.assertEqual(C.confidence_from_coverage(3, 7), C.MEDIUM)
        self.assertEqual(C.confidence_from_coverage(1, 7), C.LOW)
        self.assertEqual(C.confidence_from_coverage(0, 7), C.NONE)

    def test_from_source(self):
        self.assertEqual(C.confidence_from_source("device"), C.HIGH)
        self.assertEqual(C.confidence_from_source("manual"), C.MEDIUM)
        self.assertEqual(C.confidence_from_source("estimated"), C.LOW)

    def test_combine_takes_weakest(self):
        self.assertEqual(C.combine(C.HIGH, C.LOW, C.MEDIUM), C.LOW)
        self.assertEqual(C.combine(), C.NONE)
        self.assertTrue(C.is_at_least(C.HIGH, C.MEDIUM))
        self.assertFalse(C.is_at_least(C.LOW, C.HIGH))


class CurrentTruthConfidenceTests(SimpleTestCase):
    def test_current_value_is_high_confidence(self):
        ct = CurrentTruth.found("health", "steps_yesterday", 8123, F.CURRENT,
                                source="device")
        self.assertEqual(ct.confidence, C.HIGH)
        self.assertEqual(ct.to_fact_dict()["confidence"], C.HIGH)

    def test_stale_lowers_confidence(self):
        ct = CurrentTruth.found("health", "weight_yesterday", 285, F.STALE)
        self.assertEqual(ct.confidence, C.LOW)

    def test_absent_truth_is_none_confidence(self):
        ct = CurrentTruth.absent("health", "sleep_last_night", F.MISSING)
        self.assertEqual(ct.confidence, C.NONE)


class HistoryConfidenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="conf@test.com", password="x")
        self.today = get_user_today(self.user)

    def test_full_coverage_is_high_confidence(self):
        for i in range(7):
            StepsEntry.objects.create(user=self.user, count=5000,
                                      logged_date=self.today - timedelta(days=i))
        from apps.health.services.health_history import HealthHistory
        s = HealthHistory.steps(self.user, "last_7_days", today=self.today)
        self.assertEqual(s.confidence(), C.HIGH)

    def test_sparse_coverage_is_low_confidence(self):
        StepsEntry.objects.create(user=self.user, count=5000, logged_date=self.today)
        from apps.health.services.health_history import HealthHistory
        s = HealthHistory.steps(self.user, "last_7_days", today=self.today)
        self.assertEqual(s.confidence(), C.LOW)        # 1 of 7 days
