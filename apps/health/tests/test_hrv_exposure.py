# ==============================================================================
# File: apps/health/tests/test_hrv_exposure.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: HRV exposure (Phase 3d, P4). The canonical overnight HRV (SleepEntry
#   .hrv_value, SDNN ms) is exposed as a Health history metric so it inherits Trend /
#   Comparison / Analysis. Verifies units/source/ordering, missing≠zero, honest empty, the
#   inherited trend, and that the legacy recovery_score verdict is NOT exposed as truth.
# ==============================================================================
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

User = get_user_model()
_UTC = ZoneInfo("UTC")


class HRVExposureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="hrv@test.com", password="x")

    def _night(self, days_ago, hrv, *, duration=420):
        from apps.health.models import SleepEntry
        from apps.core.utils import get_user_today
        d = get_user_today(self.user) - timedelta(days=days_ago)
        bed = datetime(2026, 1, 1, 23, 0, tzinfo=_UTC)
        wake = datetime(2026, 1, 2, 6, 0, tzinfo=_UTC)
        return SleepEntry.objects.create(
            user=self.user, sleep_date=d, bedtime=bed, wake_time=wake,
            total_duration_minutes=duration, asleep_duration_minutes=duration,
            hrv_value=(None if hrv is None else Decimal(str(hrv))), source="apple_health")

    # --- registration ---
    def test_hrv_is_a_health_history_metric(self):
        from apps.core.truth.domain import get_domain_truth
        truth = get_domain_truth(self.user, "health")
        self.assertIn("hrv", truth.history_metrics)
        self.assertIn("hrv", truth.supports()["history"])

    # --- canonical value / unit / source ---
    def test_history_preserves_ms_and_reads_sleepentry(self):
        from apps.health.services.health_history import HealthHistory
        self._night(3, 48.0)
        self._night(2, 52.0)
        self._night(1, 55.0)
        s = HealthHistory.hrv(self.user, period="last_7_days")
        self.assertEqual(s.unit, "ms")
        self.assertEqual([p.value for p in s.points], [48.0, 52.0, 55.0])   # date-ordered
        self.assertEqual(s.metric, "hrv")

    # --- missing HRV is EXCLUDED, never zero ---
    def test_missing_nights_are_excluded_not_zeroed(self):
        from apps.health.services.health_history import HealthHistory
        self._night(4, 50.0)
        self._night(3, None)            # a night slept but no HRV recorded
        self._night(2, None)
        self._night(1, 60.0)
        s = HealthHistory.hrv(self.user, period="last_7_days")
        self.assertEqual([p.value for p in s.points], [50.0, 60.0])   # the 2 null nights gone
        self.assertEqual(s.count(), 2)
        self.assertNotIn(0.0, [p.value for p in s.points])           # never fabricated 0
        # average is over the 2 REAL nights, not dragged down by the missing ones.
        self.assertEqual(s.average(), 55.0)

    # --- honest empty (no HRV data at all) ---
    def test_no_hrv_is_empty_via_history_service(self):
        from apps.ai.cos_services.domain_history import get_domain_history
        self._night(1, None)            # slept, but no HRV
        env = get_domain_history(self.user, "health", "hrv", period="last_7_days")
        self.assertEqual(env["status"], "empty")    # no HRV points → honest empty, not zero
        self.assertEqual(env.get("count", 0), 0)

    # --- inherited Trend (no hrv_trend built — it rides HistorySeries.change) ---
    def test_trend_is_inherited(self):
        from apps.ai.cos_services.domain_history import get_domain_history
        from apps.core.utils import get_user_today
        for i, v in enumerate([40, 43, 45, 48, 52, 55, 58, 60]):   # rising HRV
            self._night(8 - i, float(v))
        today = get_user_today(self.user)
        env = get_domain_history(self.user, "health", "hrv",
                                 start=(today - timedelta(days=30)).isoformat(),
                                 end=today.isoformat())
        self.assertTrue(env["present"])
        self.assertEqual(env["unit"], "ms")
        self.assertIsNotNone(env["change"])
        self.assertEqual(env["change"]["direction"], "rising")     # arithmetic, not a verdict

    # --- inherited Comparison (rides history; no hrv_comparison built) ---
    def test_comparison_is_inherited(self):
        from apps.ai.cos_services.domain_comparison import comparison_capability_index
        self.assertIn("hrv", comparison_capability_index().get("health", ()))

    # --- the legacy recovery_score verdict is NOT exposed as canonical truth ---
    def test_recovery_score_verdict_not_exposed_as_history(self):
        from apps.core.truth.domain import get_domain_truth
        truth = get_domain_truth(self.user, "health")
        self.assertNotIn("recovery_score", truth.history_metrics)
        self.assertNotIn("recovery", truth.history_metrics)
        self.assertNotIn("readiness", truth.history_metrics)

    def test_deterministic(self):
        for i, v in enumerate([50, 48, 55, 52, 60, 58]):
            self._night(6 - i, float(v))
        from apps.health.services.health_history import HealthHistory
        a = HealthHistory.hrv(self.user, period="last_7_days").to_dict()
        b = HealthHistory.hrv(self.user, period="last_7_days").to_dict()
        self.assertEqual(a, b)
