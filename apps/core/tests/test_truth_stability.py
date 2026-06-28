# ==============================================================================
# File: apps/core/tests/test_truth_stability.py
# Description: Platform capability — Stability (Architecture Law 5). Deterministic
#   signatures of truth objects + verify_stable (no drift across repeated reads).
#   Backs the acceptance `unstable_fact` rule. No OpenAI.
# ==============================================================================
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.core.truth import freshness as F
from apps.core.truth import stability as S
from apps.core.truth.current import CurrentTruth
from apps.core.utils import get_user_today
from apps.health.models import StepsEntry

User = get_user_model()


class SignatureTests(SimpleTestCase):
    def test_same_data_same_signature(self):
        a = CurrentTruth.found("health", "steps_yesterday", 8123, F.CURRENT)
        b = CurrentTruth.found("health", "steps_yesterday", 8123, F.STALE)  # diff freshness
        # Signature is over DATA, not the now-relative freshness → identical.
        self.assertEqual(S.truth_signature(a), S.truth_signature(b))

    def test_different_value_different_signature(self):
        a = CurrentTruth.found("health", "steps_yesterday", 8123, F.CURRENT)
        b = CurrentTruth.found("health", "steps_yesterday", 9000, F.CURRENT)
        self.assertNotEqual(S.truth_signature(a), S.truth_signature(b))

    def test_absent_is_stable_and_distinct_from_present(self):
        absent = CurrentTruth.absent("health", "steps_yesterday")
        present = CurrentTruth.found("health", "steps_yesterday", 0, F.CURRENT)
        self.assertNotEqual(S.truth_signature(absent), S.truth_signature(present))


class VerifyStableTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="stab@test.com", password="x")
        self.today = get_user_today(self.user)
        self.yest = self.today - timedelta(days=1)
        StepsEntry.objects.create(user=self.user, count=8123, logged_date=self.yest)

    def test_current_truth_does_not_drift_across_reads(self):
        from apps.core.truth.domain import get_domain_truth
        truth = get_domain_truth(self.user, "health")
        result = S.verify_stable(lambda: truth.current("steps_yesterday"), rounds=3)
        self.assertTrue(result["stable"])
        self.assertEqual(len(set(result["signatures"])), 1)

    def test_history_series_does_not_drift(self):
        from apps.health.services.health_history import HealthHistory
        result = S.verify_stable(
            lambda: HealthHistory.steps(self.user, "last_7_days", today=self.today),
            rounds=3)
        self.assertTrue(result["stable"])
