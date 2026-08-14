# ==============================================================================
# File: apps/ai/tests/test_domain_consistency.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Model Interface — the CONSISTENCY branch. Verifies the catalog-driven
#   get_consistency surface measures the regularity (spread) of a repeated observation,
#   handles clock times on a 24h ring (the midnight trap), gives honest statuses, and is
#   wired into the tool + capability index + Question Catalog. Closes the "how consistent
#   has my sleep schedule been" gap (Phase 3a).
# ==============================================================================
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.domain_consistency import (
    consistency_capability_index,
    consistency_capable_domains,
    get_domain_consistency,
)

User = get_user_model()
_UTC = ZoneInfo("UTC")


class DomainConsistencyServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="cons@test.com", password="x")
        # Deterministic clock extraction — pin the user's tz to UTC so a bedtime stored at
        # HH:MM UTC has local minute-of-day HH*60+MM.
        p = cls.user.preferences
        p.timezone = "UTC"
        p.save(update_fields=["timezone"])

    def _night(self, days_ago, bed_hm, wake_hm=(7, 0), *, duration=420,
               source="apple_health"):
        """Create the authoritative SleepEntry for a night `days_ago`, with local bedtime
        `bed_hm`=(h, m) and wake `wake_hm`. The date carried on bedtime is irrelevant to the
        clock-of-day; only the time matters."""
        from apps.core.utils import get_user_today
        from apps.health.models import SleepEntry
        sleep_date = get_user_today(self.user) - timedelta(days=days_ago)
        bed = datetime(2026, 1, 1, bed_hm[0], bed_hm[1], tzinfo=_UTC)
        wake = datetime(2026, 1, 2, wake_hm[0], wake_hm[1], tzinfo=_UTC)
        return SleepEntry.objects.create(
            user=self.user, sleep_date=sleep_date, bedtime=bed, wake_time=wake,
            total_duration_minutes=duration, asleep_duration_minutes=duration,
            source=source)

    # --- capability wiring ---
    def test_sleep_is_consistency_capable(self):
        self.assertIn("health", consistency_capable_domains())
        self.assertIn("sleep", consistency_capability_index()["health"])

    # --- the core deterministic regularity retrieval ---
    def test_consistent_bedtime_low_spread(self):
        for d in range(2, 8):
            self._night(d, (23, 0 + (d % 3)))          # 11:00–11:02 PM every night
        r = get_domain_consistency(self.user, "health", "sleep", period="last_7_days")
        self.assertEqual(r["status"], "ready")
        bed = r["fields"]["bedtime"]
        self.assertTrue(bed["present"])
        self.assertLess(bed["std_dev"], 10)
        self.assertEqual(bed["typical_time"].split(":")[0], "11")
        self.assertEqual(r["granularity"], "consistency")

    def test_midnight_crossing_is_tight_not_a_day(self):
        # 11:50 PM, 12:10 AM, 11:55 PM, 12:05 AM, 11:58 PM — clustered around midnight.
        for i, hm in enumerate([(23, 50), (0, 10), (23, 55), (0, 5), (23, 58)]):
            self._night(2 + i, hm)
        r = get_domain_consistency(self.user, "health", "sleep", period="last_7_days")
        self.assertEqual(r["status"], "ready")
        bed = r["fields"]["bedtime"]
        self.assertLess(bed["std_dev"], 30)             # NOT the ~700 a linear var gives
        self.assertLessEqual(bed["max_deviation"], 30)

    def test_variable_bedtime_high_spread(self):
        for i, hm in enumerate([(20, 0), (23, 0), (2, 0), (22, 0), (1, 0), (23, 30)]):
            self._night(2 + i, hm)
        r = get_domain_consistency(self.user, "health", "sleep", period="last 30 days")
        self.assertEqual(r["status"], "ready")
        self.assertGreater(r["fields"]["bedtime"]["std_dev"], 60)

    def test_duration_regularity_is_linear(self):
        for i, dur in enumerate([400, 470, 410, 480, 420, 460]):
            self._night(2 + i, (23, 0), duration=dur)
        r = get_domain_consistency(self.user, "health", "sleep", period="last 30 days")
        dur = r["fields"]["duration"]
        self.assertEqual(dur["kind"], "linear")
        self.assertTrue(dur["present"])
        self.assertGreater(dur["std_dev"], 0)
        self.assertNotIn("typical_time", dur)

    def test_authoritative_record_one_per_night(self):
        # Two entries for the SAME night: a manual estimate + an Apple reading. Only the
        # authoritative (Apple) one is used, so the night is a single observation.
        self._night(2, (22, 0), source="manual")
        self._night(2, (23, 0), source="apple_health")
        self._night(3, (23, 5), source="apple_health")
        r = get_domain_consistency(self.user, "health", "sleep", period="last_7_days")
        self.assertEqual(r["nights_with_data"], 2)          # two nights, not three rows
        # The 22:00 manual entry lost to the 23:00 Apple one → typical near 11 PM.
        self.assertEqual(r["fields"]["bedtime"]["typical_time"].split(":")[0], "11")

    # --- honest statuses ---
    def test_insufficient_data_is_empty_not_perfect(self):
        self._night(2, (23, 0))                              # one night only
        r = get_domain_consistency(self.user, "health", "sleep", period="last_7_days")
        self.assertEqual(r["status"], "empty")

    def test_no_data_is_empty(self):
        r = get_domain_consistency(self.user, "health", "sleep", period="last_7_days")
        self.assertEqual(r["status"], "empty")

    def test_unsupported_metric(self):
        r = get_domain_consistency(self.user, "health", "glucose", period="last_month")
        self.assertEqual(r["status"], "unsupported")

    def test_unsupported_domain(self):
        r = get_domain_consistency(self.user, "not_a_domain", "sleep")
        self.assertEqual(r["status"], "unsupported_domain")

    def test_unresolvable_period(self):
        self._night(2, (23, 0)); self._night(3, (23, 5))
        r = get_domain_consistency(self.user, "health", "sleep", period="qwerty")
        self.assertEqual(r["status"], "unsupported")

    def test_deterministic_reproducible(self):
        for d in range(2, 8):
            self._night(d, (23, d % 5))
        a = get_domain_consistency(self.user, "health", "sleep", period="last_7_days")
        b = get_domain_consistency(self.user, "health", "sleep", period="last_7_days")
        self.assertEqual(a["fields"]["bedtime"]["std_dev"],
                         b["fields"]["bedtime"]["std_dev"])
        self.assertEqual(a["fields"]["bedtime"]["typical_minutes"],
                         b["fields"]["bedtime"]["typical_minutes"])
