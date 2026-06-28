# ==============================================================================
# File: apps/core/tests/test_current_truth.py
# Description: Platform capability — Current Truth Objects (apps.core.truth.current).
#   One authoritative value object composing a value + a freshness verdict, consumed
#   by every domain. Tests the object + that Health and Finance both consume it.
# ==============================================================================
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.truth import freshness as F
from apps.core.truth.current import CurrentTruth
from apps.core.utils import get_user_today
from apps.health.models import StepsEntry, SleepEntry
from apps.health.services.current_health import CurrentHealth

User = get_user_model()


class CurrentTruthObjectTests(SimpleTestCase):
    def test_found_serializes_to_fact_dict(self):
        ct = CurrentTruth.found("health", "steps_yesterday", 8123, F.CURRENT,
                                unit="steps", source="DailyHealthQueries",
                                detail={"for_date": "2026-06-26"})
        d = ct.to_fact_dict()
        self.assertEqual(d["value"], 8123)
        self.assertEqual(d["freshness"], F.CURRENT)
        self.assertEqual(d["for_date"], "2026-06-26")

    def test_absent_serializes_to_unknown(self):
        ct = CurrentTruth.absent("health", "sleep_last_night", F.MISSING, reason="none")
        d = ct.to_fact_dict()
        self.assertEqual(d["status"], "unknown")
        self.assertEqual(d["freshness"], F.MISSING)


def _sleep(user, night_date, hours):
    mins = int(hours * 60)
    bed = timezone.now()
    SleepEntry.objects.create(user=user, sleep_date=night_date, bedtime=bed,
                              wake_time=bed + timedelta(minutes=mins),
                              total_duration_minutes=mins, asleep_duration_minutes=mins)


class CurrentHealthConsumerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ch@test.com", password="x")
        self.today = get_user_today(self.user)
        self.yest = self.today - timedelta(days=1)

    def test_current_truth_object_carries_value_and_freshness(self):
        StepsEntry.objects.create(user=self.user, count=8123, logged_date=self.yest)
        ct = CurrentHealth.get(self.user, "steps_yesterday")
        self.assertTrue(ct.present)
        self.assertEqual(ct.value, 8123)
        self.assertEqual(ct.freshness, F.CURRENT)
        self.assertEqual(ct.domain, "health")

    def test_partial_for_today_cumulative(self):
        StepsEntry.objects.create(user=self.user, count=3100, logged_date=self.today)
        self.assertEqual(CurrentHealth.get(self.user, "steps_today").freshness, F.PARTIAL)

    def test_absent_when_no_data(self):
        ct = CurrentHealth.get(self.user, "sleep_last_night")
        self.assertFalse(ct.present)
        self.assertEqual(ct.freshness, F.MISSING)


class CurrentFinanceConsumerTests(TestCase):
    """Second domain consuming the SAME platform object — net worth from pre-computed
    SAE state, freshness from BankConnection.last_sync_at (sync shape)."""

    def setUp(self):
        self.user = User.objects.create_user(email="cf@test.com", password="x")

    def test_net_worth_is_a_current_truth_object_with_sync_freshness(self):
        from apps.finance.services.current_finance import CurrentFinance
        state = {"_contract": {"summary": {"net_worth": 42000.0,
                                           "month_spending": 1850.0}}}
        with mock.patch("apps.core.ai_state.state_engine.get_module_state",
                        return_value=state):
            ct = CurrentFinance.net_worth(self.user)
        self.assertTrue(ct.present)
        self.assertEqual(ct.value, 42000.0)
        self.assertEqual(ct.domain, "finance")
        # No bank connection → manually-entered truth is current.
        self.assertEqual(ct.freshness, F.CURRENT)
        self.assertEqual(ct.to_fact_dict()["value"], 42000.0)

    def test_net_worth_absent_without_accounts(self):
        from apps.finance.services.current_finance import CurrentFinance
        with mock.patch("apps.core.ai_state.state_engine.get_module_state",
                        return_value={"_contract": {"summary": {}}}):
            ct = CurrentFinance.net_worth(self.user)
        self.assertFalse(ct.present)
